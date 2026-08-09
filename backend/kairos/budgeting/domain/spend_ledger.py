"""The SpendLedger aggregate.

Two-step by design: `authorize` before the paid call, `record` after it. A
ledger that only records has already lost the money by the time it notices, so
the guard has to sit in front of the API call, not behind it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from kairos.budgeting.domain.events import BudgetCapReached, PipelinePaused, SpendRecorded
from kairos.budgeting.domain.value_objects import (
    BudgetLimit,
    BudgetPeriod,
    CostCategory,
    CostEvent,
)
from kairos.shared_kernel.money import Money

LedgerEvent = SpendRecorded | BudgetCapReached | PipelinePaused

# Which contexts stop when a cap is hit — the two with recurring paid-API costs
# (CONTEXT.md §4.8). Analytics and Curation keep running: reading data you have
# already paid for costs nothing, and stopping review would strand approved work.
PAUSED_ON_CAP = ("trend_discovery", "content_generation")


class BudgetExceededError(RuntimeError):
    """A spend was refused because it would breach a cap.

    Raised by `authorize`, before any money is spent. Adapters must let this
    propagate rather than calling the paid endpoint anyway.
    """


@dataclass(slots=True)
class SpendLedger:
    limit: BudgetLimit
    spent_today: Money
    spent_this_month: Money
    today: date = field(default_factory=lambda: datetime.now(UTC).date())
    events: list[LedgerEvent] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        for total in (self.spent_today, self.spent_this_month):
            if total.currency != self.limit.currency:
                raise ValueError("ledger totals must match the budget currency")
        if self.spent_today.amount > self.spent_this_month.amount:
            raise ValueError("today's spend cannot exceed the month's")

    @classmethod
    def opened(cls, limit: BudgetLimit) -> SpendLedger:
        zero = Money.zero(limit.currency)
        return cls(limit=limit, spent_today=zero, spent_this_month=zero)

    # -- queries ----------------------------------------------------------

    def remaining(self, period: BudgetPeriod) -> Money:
        spent = self.spent_today if period is BudgetPeriod.DAILY else self.spent_this_month
        return self.limit.cap_for(period) - spent

    @property
    def is_paused(self) -> bool:
        """True once either cap is met. Reached, not exceeded — a ledger sitting
        exactly on its cap has no room for the next call, however small."""
        return any(self.remaining(period).amount <= 0 for period in BudgetPeriod)

    def can_afford(self, amount: Money) -> bool:
        return all((self.remaining(period) - amount).amount >= 0 for period in BudgetPeriod)

    # -- commands ---------------------------------------------------------

    def authorize(self, amount: Money) -> None:
        """Call before spending. Raises rather than returning a boolean nobody
        checks."""
        if amount.currency != self.limit.currency:
            raise ValueError(
                f"cannot authorize {amount.currency} against a {self.limit.currency} budget"
            )
        if amount.amount < 0:
            raise ValueError("cannot authorize a negative spend")
        if self.is_paused:
            raise BudgetExceededError(
                f"pipeline is paused: daily {self.spent_today}/{self.limit.daily}, "
                f"monthly {self.spent_this_month}/{self.limit.monthly}"
            )
        if not self.can_afford(amount):
            raise BudgetExceededError(
                f"{amount} would breach the budget — "
                f"{self.remaining(BudgetPeriod.DAILY)} left today, "
                f"{self.remaining(BudgetPeriod.MONTHLY)} this month"
            )

    def record(self, cost: CostEvent) -> None:
        """Record money already spent. Never refuses — the money is gone, and a
        ledger that rejects reality is worse than one that reports an overspend.
        """
        if cost.amount.currency != self.limit.currency:
            raise ValueError("cost currency does not match the budget")

        was_paused = self.is_paused
        if cost.on_day == self.today:
            self.spent_today = self.spent_today + cost.amount
        self.spent_this_month = self.spent_this_month + cost.amount

        self.events.append(
            SpendRecorded(
                cost_id=cost.cost_id,
                category=cost.category,
                amount=str(cost.amount.amount),
                currency=cost.amount.currency,
                reference=cost.reference,
            )
        )

        # Only on the transition, so a paused pipeline does not re-emit on every
        # late-arriving cost and drown the alert that mattered.
        if self.is_paused and not was_paused:
            breached = next(period for period in BudgetPeriod if self.remaining(period).amount <= 0)
            self.events.append(
                BudgetCapReached(
                    period=breached,
                    cap=str(self.limit.cap_for(breached).amount),
                    spent=str(
                        (
                            self.spent_today
                            if breached is BudgetPeriod.DAILY
                            else self.spent_this_month
                        ).amount
                    ),
                    currency=self.limit.currency,
                )
            )
            self.events.append(PipelinePaused(reason=f"{breached.value} budget cap reached"))

    def roll_to(self, new_day: date) -> None:
        """Advance the ledger's day.

        The daily total always resets. The monthly one resets only when the
        month actually changes — crossing into a new month has to clear it, or
        the monthly cap stays breached forever and the pipeline never restarts.
        """
        if new_day < self.today:
            raise ValueError("cannot roll a ledger backwards")
        if new_day == self.today:
            return
        month_changed = (new_day.year, new_day.month) != (self.today.year, self.today.month)
        self.today = new_day
        self.spent_today = Money.zero(self.limit.currency)
        if month_changed:
            self.spent_this_month = Money.zero(self.limit.currency)

    def pull_events(self) -> list[LedgerEvent]:
        drained, self.events = self.events, []
        return drained


def category_is_metered(category: CostCategory) -> bool:
    """Whether spending in this category is something the caps should gate.

    Etsy's listing and transaction fees are consequences of selling, not
    discretionary spend — pausing the pipeline does not stop them, and counting
    them toward a generation budget would pause generation because something
    sold, which is exactly backwards.
    """
    return category not in (CostCategory.LISTING_FEE, CostCategory.TRANSACTION_FEE)
