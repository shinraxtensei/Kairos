"""Budgeting's published interface.

A sibling of the layers, so it may wire this context's repository. Exposes the
two questions other contexts need: may I spend this, and record that I did.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from kairos.budgeting.application.metered_spend import MeteredSpend, RecordSpend
from kairos.budgeting.domain.spend_ledger import SpendLedger
from kairos.budgeting.domain.value_objects import BudgetLimit
from kairos.budgeting.infrastructure.repository import SqlAlchemySpendLedgerRepository
from kairos.config import get_settings
from kairos.shared_kernel.money import Money

__all__ = ["configured_limit", "current_ledger", "metered_spend", "record_spend"]


def configured_limit() -> BudgetLimit:
    settings = get_settings()
    return BudgetLimit(
        daily=Money(Decimal(settings.daily_budget), settings.budget_currency),
        monthly=Money(Decimal(settings.monthly_budget), settings.budget_currency),
    )


def _repository(session: Session) -> SqlAlchemySpendLedgerRepository:
    return SqlAlchemySpendLedgerRepository(session, configured_limit())


def metered_spend(session: Session) -> MeteredSpend:
    """Wrap a paid call so it cannot happen without budget approval."""
    return MeteredSpend(_repository(session))


def record_spend(session: Session) -> RecordSpend:
    return RecordSpend(_repository(session))


def current_ledger(session: Session) -> SpendLedger:
    """Today's ledger, with totals summed from stored cost events."""
    return _repository(session).current()
