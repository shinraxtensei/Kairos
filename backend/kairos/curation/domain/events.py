"""Domain events for Curation.

`AssetApproved` is the compliance gate's output. Listing Authoring's
`DraftListing` requires one for the asset before a draft can exist, so this
event is the only legitimate route from a generated design to a published one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from kairos.curation.domain.value_objects import RejectionReason


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class AssetApproved:
    """Triggers DraftListing. Carries who screened it, for the audit trail."""

    review_id: UUID
    asset_id: UUID
    reviewer: str
    screened_by: str
    occurred_at: datetime = field(default_factory=_now)


@dataclass(frozen=True, slots=True)
class AssetRejected:
    review_id: UUID
    asset_id: UUID
    reviewer: str
    reason: RejectionReason
    note: str = ""
    occurred_at: datetime = field(default_factory=_now)
