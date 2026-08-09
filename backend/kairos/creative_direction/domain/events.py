"""Domain events for Creative Direction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class StyleGuideDrafted:
    style_guide_id: UUID
    niche_keyword: str
    occurred_at: datetime = field(default_factory=_now)


@dataclass(frozen=True, slots=True)
class PromptSetGenerated:
    """Triggers GenerateAsset in Content Generation (CONTEXT.md §4.4 policy).

    `variation_count` is what Budgeting prices the run on, before a single
    paid call is made.
    """

    style_guide_id: UUID
    niche_keyword: str
    variation_count: int
    varied_axes: tuple[str, ...]
    occurred_at: datetime = field(default_factory=_now)
