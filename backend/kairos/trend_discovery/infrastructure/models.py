"""Trend Discovery's own tables. No other context reads these (CONTEXT.md §3.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kairos.db import Base


class TrendSignalRecord(Base):
    __tablename__ = "trend_signals"

    signal_id: Mapped[UUID] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    keyword: Mapped[str] = mapped_column(String(200), index=True)
    search_volume: Mapped[int] = mapped_column(Integer)
    volume_scale: Mapped[str] = mapped_column(String(16))
    competition_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # ENG-21: the untouched vendor response. Cheap now, and the only way to
    # re-score history after the ranking formula changes without re-fetching.
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        Index("ix_trend_signals_platform_keyword_collected", "platform", "keyword", "collected_at"),
    )
