"""Budgeting's own tables.

Only the individual cost events are stored. Daily and monthly totals are summed
from them on read rather than kept as running counters, because a stored counter
drifts the moment anything is inserted, corrected or backdated outside the one
code path that maintains it — and a budget cap computed from a drifted counter
fails silently in the expensive direction. Summing also makes period rollover
free: a new day is simply a different WHERE clause.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from kairos.db import Base


class CostEventRecord(Base):
    __tablename__ = "cost_events"

    cost_id: Mapped[UUID] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    # Numeric, never float. This is the arithmetic the caps depend on.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    currency: Mapped[str] = mapped_column(String(3))
    # What caused the spend — an asset id, a listing id. Lets cost per *winning*
    # design be computed later instead of estimated (CONTEXT.md §6).
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (Index("ix_cost_events_occurred_category", "occurred_at", "category"),)
