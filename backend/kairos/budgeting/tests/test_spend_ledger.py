"""Budgeting domain tests. Pure, no mocks, no I/O.

The threshold cases are the point. A cap that fires one cent late is a cap that
did not hold, and this is the guard against the project's highest-likelihood
failure — burning cash on designs that never sell (RSK-04).
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from kairos.budgeting.domain.events import BudgetCapReached, PipelinePaused, SpendRecorded
from kairos.budgeting.domain.spend_ledger import (
    BudgetExceededError,
    SpendLedger,
    category_is_metered,
)
from kairos.budgeting.domain.value_objects import (
    BudgetLimit,
    BudgetPeriod,
    CostCategory,
    CostEvent,
)
from kairos.shared_kernel.money import Money


def usd(amount: str) -> Money:
    return Money.of(amount, "USD")


LIMIT = BudgetLimit(daily=usd("5.00"), monthly=usd("50.00"))


def _cost(amount: str, **kwargs: object) -> CostEvent:
    return CostEvent(
        category=kwargs.pop("category", CostCategory.IMAGE_GENERATION),  # type: ignore[arg-type]
        amount=usd(amount),
        **kwargs,  # type: ignore[arg-type]
    )


class TestBudgetLimit:
    def test_given_a_monthly_cap_below_the_daily_cap_when_built_then_raises(self) -> None:
        # A daily cap above the monthly one could never bind — a config typo
        # that would silently disable the tighter guard.
        with pytest.raises(ValueError, match="could never bind"):
            BudgetLimit(daily=usd("100.00"), monthly=usd("50.00"))

    def test_given_mismatched_currencies_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="share a currency"):
            BudgetLimit(daily=usd("5.00"), monthly=Money.of("50.00", "EUR"))

    @pytest.mark.parametrize("amount", ["0.00", "-1.00"])
    def test_given_a_non_positive_cap_when_built_then_raises(self, amount: str) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            BudgetLimit(daily=usd(amount), monthly=usd("50.00"))


class TestAuthorization:
    def test_given_room_in_the_budget_when_authorized_then_allowed(self) -> None:
        SpendLedger.opened(LIMIT).authorize(usd("0.04"))

    def test_given_a_spend_that_exactly_fills_the_cap_when_authorized_then_allowed(
        self,
    ) -> None:
        # Spending up to the cap is the point of having one.
        SpendLedger.opened(LIMIT).authorize(usd("5.00"))

    def test_given_a_spend_one_cent_over_the_cap_when_authorized_then_refused(self) -> None:
        with pytest.raises(BudgetExceededError, match="would breach"):
            SpendLedger.opened(LIMIT).authorize(usd("5.01"))

    def test_given_a_ledger_exactly_on_its_cap_when_authorized_then_refused(self) -> None:
        """Reached, not exceeded. A ledger sitting on its cap has no room left
        for the next call, however small."""
        ledger = SpendLedger.opened(LIMIT)
        ledger.record(_cost("5.00"))
        with pytest.raises(BudgetExceededError, match="paused"):
            ledger.authorize(usd("0.01"))

    def test_given_the_monthly_cap_is_the_binding_one_when_authorized_then_refused(
        self,
    ) -> None:
        ledger = SpendLedger(limit=LIMIT, spent_today=usd("0.00"), spent_this_month=usd("49.99"))
        ledger.authorize(usd("0.01"))
        with pytest.raises(BudgetExceededError):
            ledger.authorize(usd("0.02"))

    def test_given_a_foreign_currency_when_authorized_then_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot authorize EUR"):
            SpendLedger.opened(LIMIT).authorize(Money.of("1.00", "EUR"))


class TestRecording:
    def test_given_a_cost_when_recorded_then_totals_move_and_event_emitted(self) -> None:
        ledger = SpendLedger.opened(LIMIT)
        ledger.record(_cost("0.04", reference="asset-1"))

        assert ledger.spent_today == usd("0.04")
        assert ledger.spent_this_month == usd("0.04")
        (event,) = ledger.pull_events()
        assert isinstance(event, SpendRecorded)
        assert event.amount == "0.04"
        assert event.reference == "asset-1"

    def test_given_spend_reaching_exactly_the_cap_when_recorded_then_cap_reached(
        self,
    ) -> None:
        """Fires at exactly the threshold, not one cent past it."""
        ledger = SpendLedger.opened(LIMIT)
        for _ in range(125):
            ledger.record(_cost("0.04"))  # 125 x 0.04 = exactly 5.00

        assert ledger.spent_today == usd("5.00")
        assert ledger.is_paused
        kinds = [type(e).__name__ for e in ledger.pull_events()]
        assert kinds.count("BudgetCapReached") == 1
        assert kinds.count("PipelinePaused") == 1

    def test_given_spend_just_under_the_cap_when_recorded_then_not_paused(self) -> None:
        ledger = SpendLedger.opened(LIMIT)
        for _ in range(124):
            ledger.record(_cost("0.04"))  # 4.96

        assert not ledger.is_paused
        assert not [e for e in ledger.pull_events() if isinstance(e, BudgetCapReached)]

    def test_given_an_already_paused_ledger_when_more_cost_lands_then_no_repeat_alert(
        self,
    ) -> None:
        """A late-arriving cost must not re-emit and drown the alert that mattered."""
        ledger = SpendLedger.opened(LIMIT)
        ledger.record(_cost("5.00"))
        ledger.pull_events()

        ledger.record(_cost("0.04"))

        assert not [
            e for e in ledger.pull_events() if isinstance(e, BudgetCapReached | PipelinePaused)
        ]

    def test_given_an_overspend_when_recorded_then_it_is_accepted_not_refused(self) -> None:
        # The money is already gone; a ledger that rejects reality is worse than
        # one reporting an overspend.
        ledger = SpendLedger.opened(LIMIT)
        ledger.record(_cost("7.50"))
        assert ledger.spent_today == usd("7.50")
        assert ledger.is_paused

    def test_given_a_cost_from_a_previous_day_when_recorded_then_only_month_moves(
        self,
    ) -> None:
        ledger = SpendLedger.opened(LIMIT)
        yesterday = datetime.now(UTC) - timedelta(days=1)
        ledger.record(_cost("1.00", occurred_at=yesterday))

        assert ledger.spent_today == usd("0.00")
        assert ledger.spent_this_month == usd("1.00")

    def test_given_a_negative_cost_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be negative"):
            _cost("-1.00")


class TestPeriodRollover:
    def test_given_a_new_day_when_rolled_then_daily_resets_and_monthly_carries(
        self,
    ) -> None:
        ledger = SpendLedger(
            limit=LIMIT,
            spent_today=usd("5.00"),
            spent_this_month=usd("20.00"),
            today=date(2026, 8, 8),
        )
        assert ledger.is_paused

        ledger.roll_to(date(2026, 8, 9))

        assert ledger.spent_today == usd("0.00")
        assert ledger.spent_this_month == usd("20.00")
        assert not ledger.is_paused

    def test_given_a_new_month_when_rolled_then_monthly_resets_too(self) -> None:
        """Crossing into a new month has to clear the monthly total, or a
        breached monthly cap keeps the pipeline paused forever."""
        ledger = SpendLedger(
            limit=LIMIT,
            spent_today=usd("2.00"),
            spent_this_month=usd("50.00"),
            today=date(2026, 8, 31),
        )
        assert ledger.is_paused

        ledger.roll_to(date(2026, 9, 1))

        assert ledger.spent_this_month == usd("0.00")
        assert not ledger.is_paused

    def test_given_a_past_date_when_rolled_then_raises(self) -> None:
        ledger = SpendLedger.opened(LIMIT)
        with pytest.raises(ValueError, match="backwards"):
            ledger.roll_to(date(2020, 1, 1))


class TestMetering:
    @pytest.mark.parametrize(
        "category",
        [CostCategory.IMAGE_GENERATION, CostCategory.UPSCALING, CostCategory.TREND_DATA],
    )
    def test_given_discretionary_spend_then_it_is_metered(self, category: CostCategory) -> None:
        assert category_is_metered(category)

    @pytest.mark.parametrize("category", [CostCategory.LISTING_FEE, CostCategory.TRANSACTION_FEE])
    def test_given_a_selling_fee_then_it_is_not_metered(self, category: CostCategory) -> None:
        """Etsy's fees are consequences of selling, not discretionary spend.

        Counting them toward a generation cap would pause generation because
        something sold, which is exactly backwards.
        """
        assert not category_is_metered(category)


class TestLedgerInvariants:
    def test_given_totals_in_the_wrong_currency_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="match the budget currency"):
            SpendLedger(
                limit=LIMIT,
                spent_today=Money.of("0.00", "EUR"),
                spent_this_month=usd("0.00"),
            )

    def test_given_daily_above_monthly_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed the month"):
            SpendLedger(limit=LIMIT, spent_today=usd("10.00"), spent_this_month=usd("5.00"))

    def test_given_a_hundred_small_costs_when_summed_then_exact(self) -> None:
        # The arithmetic the whole cap depends on. Float would drift here.
        ledger = SpendLedger.opened(LIMIT)
        for _ in range(100):
            ledger.record(_cost("0.03"))
        assert ledger.spent_today == usd("3.00")

    def test_given_remaining_when_asked_then_reports_both_periods(self) -> None:
        ledger = SpendLedger.opened(LIMIT)
        ledger.record(_cost("1.00"))
        assert ledger.remaining(BudgetPeriod.DAILY) == usd("4.00")
        assert ledger.remaining(BudgetPeriod.MONTHLY) == usd("49.00")
