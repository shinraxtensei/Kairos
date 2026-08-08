"""Content Generation's own tables."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kairos.db import Base


class GeneratedAssetRecord(Base):
    __tablename__ = "generated_assets"

    asset_id: Mapped[UUID] = mapped_column(primary_key=True)
    niche_keyword: Mapped[str] = mapped_column(String(200), index=True)
    variant_index: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage: Mapped[str] = mapped_column(String(24), index=True)
    failure: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # Numeric, not float — this feeds the SpendLedger.
    cost_amount: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    cost_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    print_spec: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    delivery_files: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # The review queue's only query: packaged, unfailed, oldest first.
    __table_args__ = (Index("ix_generated_assets_stage_failure", "stage", "failure"),)
