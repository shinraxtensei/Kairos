"""RecordSpend and EnforceBudgetCap — CONTEXT.md §4.8.

The important piece is `metered`, a context manager that authorizes before the
paid call and records after it. An adapter that forgets to record still cannot
skip the authorization, because the money never leaves without passing through
here first.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from kairos.budgeting.domain.events import BudgetCapReached, PipelinePaused
from kairos.budgeting.domain.ports import SpendLedgerRepository
from kairos.budgeting.domain.spend_ledger import BudgetExceededError, SpendLedger
from kairos.budgeting.domain.value_objects import CostCategory, CostEvent
from kairos.shared_kernel.money import Money

logger = logging.getLogger(__name__)


class RecordSpend:
    def __init__(self, repository: SpendLedgerRepository) -> None:
        self._repository = repository

    def __call__(
        self, category: CostCategory, amount: Money, reference: str | None = None
    ) -> SpendLedger:
        ledger = self._repository.current()
        ledger.record(CostEvent(category=category, amount=amount, reference=reference))
        self._repository.save(ledger)

        for event in ledger.pull_events():
            if isinstance(event, BudgetCapReached):
                logger.error(
                    "budget cap reached: %s spent of %s %s (%s) — pipeline pausing",
                    event.spent,
                    event.cap,
                    event.currency,
                    event.period.value,
                )
            elif isinstance(event, PipelinePaused):
                logger.error("pipeline paused: %s", event.reason)
        return ledger


class MeteredSpend:
    """Wraps a paid call so it cannot happen without budget approval."""

    def __init__(self, repository: SpendLedgerRepository) -> None:
        self._repository = repository
        self._record = RecordSpend(repository)

    def is_paused(self) -> bool:
        return self._repository.current().is_paused

    @contextmanager
    def metered(
        self, category: CostCategory, estimated: Money, reference: str | None = None
    ) -> Iterator[None]:
        """Authorize, run the paid call, then record what it actually cost.

        Raises BudgetExceededError *before* the body runs. If the body raises —
        the vendor failed — nothing is recorded, because a failed call that was
        not billed should not eat budget.
        """
        self._repository.current().authorize(estimated)
        yield
        self._record(category, estimated, reference)


def guard(ledger: SpendLedger, amount: Money) -> None:
    """Convenience for adapters that cannot use the context manager.

    Deliberately raises rather than returning a bool: a boolean invites a caller
    to check it, log it, and carry on spending anyway.
    """
    ledger.authorize(amount)


__all__ = ["BudgetExceededError", "MeteredSpend", "RecordSpend", "guard"]
