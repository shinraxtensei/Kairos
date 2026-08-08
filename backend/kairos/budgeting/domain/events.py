"""Domain events for Budgeting.

Amounts travel as decimal strings rather than Money, so other contexts can
consume these without importing this one's value objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from kairos.budgeting.domain.value_objects import BudgetPeriod, CostCategory


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class SpendRecorded:
    cost_id: UUID
    category: CostCategory
    amount: str
    currency: str
    reference: str | None = None
    occurred_at: datetime = field(default_factory=_now)


@dataclass(frozen=True, slots=True)
class BudgetCapReached:
    """Pauses Trend Discovery and Content Generation until the period rolls
    over or someone overrides it (CONTEXT.md §4.8)."""

    period: BudgetPeriod
    cap: str
    spent: str
    currency: str
    occurred_at: datetime = field(default_factory=_now)


@dataclass(frozen=True, slots=True)
class PipelinePaused:
    reason: str
    occurred_at: datetime = field(default_factory=_now)
