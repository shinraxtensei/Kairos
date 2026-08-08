"""Curation's own tables."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from kairos.db import Base


class ReviewDecisionRecord(Base):
    __tablename__ = "review_decisions"

    review_id: Mapped[UUID] = mapped_column(primary_key=True)
    asset_id: Mapped[UUID] = mapped_column(index=True)
    reviewer: Mapped[str] = mapped_column(String(120))
    approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    # Which IP checks were cleared, and by whom. Stored rather than derived so
    # the audit trail survives a change to the checklist: a design approved
    # under an older, shorter list stays visibly approved under that list, and
    # a newly added check does not retroactively invalidate past approvals.
    ip_checks_cleared: Mapped[list[str] | None] = mapped_column(ARRAY(String(64)), nullable=True)
    screened_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_review_decisions_asset_approved", "asset_id", "approved"),)
