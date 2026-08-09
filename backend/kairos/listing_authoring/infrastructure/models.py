"""Listing Authoring's own tables."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from kairos.db import Base


class ListingDraftRecord(Base):
    __tablename__ = "listing_drafts"

    draft_id: Mapped[UUID] = mapped_column(primary_key=True)
    # One draft per approved asset. Unique so a retried DraftListing cannot
    # produce two drafts that would each become a paid listing.
    asset_id: Mapped[UUID] = mapped_column(unique=True, index=True)
    title: Mapped[str] = mapped_column(String(140))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(20)))
    description: Mapped[str] = mapped_column(Text)
    # Stored, not regenerated. The disclosure a listing went live with is an
    # audit record; re-deriving it from today's config would rewrite history.
    disclosure_seller: Mapped[str] = mapped_column(String(120))
    disclosure_tools: Mapped[str] = mapped_column(Text)
    price_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    price_currency: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
