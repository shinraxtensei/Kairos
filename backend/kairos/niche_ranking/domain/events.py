"""Domain events for Niche Ranking. Past tense, per CONTEXT.md §4.2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from kairos.niche_ranking.domain.value_objects import Confidence


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class NicheScored:
    niche_id: UUID
    keyword: str
    score: int
    confidence: Confidence
    occurred_at: datetime = field(default_factory=_now)


@dataclass(frozen=True, slots=True)
class NicheShortlisted:
    """Triggers DefineStyleGuide in Creative Direction (M4)."""

    niche_id: UUID
    keyword: str
    score: int
    occurred_at: datetime = field(default_factory=_now)


@dataclass(frozen=True, slots=True)
class NicheRejected:
    niche_id: UUID
    keyword: str
    score: int
    reason: str
    occurred_at: datetime = field(default_factory=_now)
