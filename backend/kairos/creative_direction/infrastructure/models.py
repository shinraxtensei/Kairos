"""Creative Direction's own tables."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kairos.db import Base


class StyleGuideRecord(Base):
    __tablename__ = "style_guides"

    style_guide_id: Mapped[UUID] = mapped_column(primary_key=True)
    niche_keyword: Mapped[str] = mapped_column(String(200), index=True)
    # Template text is data, not code — it gets tuned constantly, and a tuning
    # change should not need a deploy.
    template: Mapped[str] = mapped_column(String(2000))
    # One JSON object per variation, axis -> value.
    variations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
