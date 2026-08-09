"""Domain events for Fulfillment."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ListingPublished:
    """Triggers RecordSpend (the $0.20 listing fee) and schedules the first
    Analytics snapshot (CONTEXT.md §4.7)."""

    listing_id: UUID
    draft_id: UUID
    asset_id: UUID
    external_id: str
    channel_name: str
    occurred_at: datetime = field(default_factory=_now)


@dataclass(frozen=True, slots=True)
class ListingPublishFailed:
    listing_id: UUID
    draft_id: UUID
    reason: str
    attempts: int
    occurred_at: datetime = field(default_factory=_now)
