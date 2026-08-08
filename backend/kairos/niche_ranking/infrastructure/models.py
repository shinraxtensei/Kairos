"""Niche Ranking's own tables. No other context reads these."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kairos.db import Base


class NicheRecord(Base):
    __tablename__ = "niches"

    niche_id: Mapped[UUID] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    score: Mapped[int] = mapped_column(Integer, index=True)
    confidence: Mapped[str] = mapped_column(String(8))
    # The score's reasoning, not just its result. A formula whose inputs were
    # not recorded cannot be retuned later.
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
