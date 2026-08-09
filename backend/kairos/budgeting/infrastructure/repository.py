"""SQLAlchemy implementation of SpendLedgerRepository."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from kairos.budgeting.domain.ports import SpendLedgerRepository
from kairos.budgeting.domain.spend_ledger import SpendLedger, category_is_metered
from kairos.budgeting.domain.value_objects import BudgetLimit, CostCategory
from kairos.budgeting.infrastructure.models import CostEventRecord
from kairos.shared_kernel.money import Money

# Categories that count toward a cap. Etsy's fees are excluded: they follow from
# selling rather than from choosing to spend, and metering them would pause
# generation because something sold.
METERED = [c.value for c in CostCategory if category_is_metered(c)]


def month_start(moment: date) -> date:
    return moment.replace(day=1)


class SqlAlchemySpendLedgerRepository(SpendLedgerRepository):
    def __init__(self, session: Session, limit: BudgetLimit) -> None:
        self._session = session
        self._limit = limit

    def _total_since(self, since: date, currency: str) -> Money:
        start = datetime.combine(since, datetime.min.time(), tzinfo=UTC)
        total = self._session.scalar(
            select(func.coalesce(func.sum(CostEventRecord.amount), 0)).where(
                CostEventRecord.occurred_at >= start,
                CostEventRecord.currency == currency,
                CostEventRecord.category.in_(METERED),
            )
        )
        return Money(Decimal(str(total or 0)), currency)

    def current(self) -> SpendLedger:
        """Totals summed from stored events, so the ledger is never stale.

        This is what the port's contract requires: a ledger positioned on the
        wrong day undercounts, and a daily cap that undercounts does not bind.
        Deriving the totals removes the whole class of bug rather than relying
        on someone remembering to roll the ledger forward.
        """
        today = datetime.now(UTC).date()
        currency = self._limit.currency
        return SpendLedger(
            limit=self._limit,
            spent_today=self._total_since(today, currency),
            spent_this_month=self._total_since(month_start(today), currency),
            today=today,
        )

    def save(self, ledger: SpendLedger) -> None:
        """Persist the costs the ledger just recorded.

        The aggregate's totals are not written back — they are derived on read,
        so there is nothing to keep in sync and nothing to drift.
        """
        from kairos.budgeting.domain.events import SpendRecorded

        rows = [
            {
                "cost_id": event.cost_id,
                "category": event.category.value,
                "amount": Decimal(event.amount),
                "currency": event.currency,
                "reference": event.reference,
                "occurred_at": event.occurred_at,
            }
            for event in ledger.events
            if isinstance(event, SpendRecorded)
        ]
        if not rows:
            return
        # A retried Celery task replays the same cost_id; recording twice must
        # not double-charge the budget.
        statement = (
            insert(CostEventRecord).values(rows).on_conflict_do_nothing(index_elements=["cost_id"])
        )
        self._session.execute(statement)
        self._session.commit()
