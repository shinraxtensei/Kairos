"""Fulfillment's own tables."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from kairos.db import Base


class ListingRecord(Base):
    __tablename__ = "listings"

    listing_id: Mapped[UUID] = mapped_column(primary_key=True)
    # Unique: one draft is one listing. This is the database half of ENG-34 —
    # even if the application guard were bypassed, a second row cannot exist,
    # and $0.20 per duplicate is a cost worth defending twice.
    draft_id: Mapped[UUID] = mapped_column(unique=True, index=True)
    asset_id: Mapped[UUID] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(140))
    channel_name: Mapped[str] = mapped_column(String(32), index=True)
    state: Mapped[str] = mapped_column(String(16), index=True)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    external_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
