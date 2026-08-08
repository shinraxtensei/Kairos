"""Domain events for Content Generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from kairos.content_generation.domain.value_objects import GenerationFailure, ProcessingStage


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class AssetGenerated:
    asset_id: UUID
    niche_keyword: str
    variant_index: int
    # Carried as primitives so Budgeting can record spend without this context
    # and that one sharing a Money import through an event payload.
    cost_amount: str | None = None
    cost_currency: str | None = None
    occurred_at: datetime = field(default_factory=_now)


@dataclass(frozen=True, slots=True)
class AssetProcessed:
    asset_id: UUID
    stage: ProcessingStage
    occurred_at: datetime = field(default_factory=_now)


@dataclass(frozen=True, slots=True)
class AssetPackaged:
    """The asset now has files Etsy will accept, so it may enter Curation."""

    asset_id: UUID
    file_count: int
    total_bytes: int
    occurred_at: datetime = field(default_factory=_now)


@dataclass(frozen=True, slots=True)
class AssetGenerationFailed:
    asset_id: UUID
    reason: GenerationFailure
    detail: str = ""
    occurred_at: datetime = field(default_factory=_now)
