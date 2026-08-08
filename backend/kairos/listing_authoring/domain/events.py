"""Domain events for Listing Authoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ListingDrafted:
    draft_id: UUID
    asset_id: UUID
    occurred_at: datetime = field(default_factory=_now)


@dataclass(frozen=True, slots=True)
class ListingReadyToPublish:
    """Triggers PublishListing. Carries the attribution so Fulfillment never
    has to reconstruct it and get the wording wrong."""

    draft_id: UUID
    asset_id: UUID
    title: str
    attribution: str
    occurred_at: datetime = field(default_factory=_now)
