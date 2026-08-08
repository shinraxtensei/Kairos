"""Domain events. Past tense, named per CONTEXT.md §4.1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from kairos.trend_discovery.domain.value_objects import Keyword, SourcePlatform


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class TrendSignalCollected:
    signal_id: UUID
    platform: SourcePlatform
    keyword: Keyword
    occurred_at: datetime = field(default_factory=_now)


@dataclass(frozen=True, slots=True)
class TrendSourceSyncFailed:
    """A source failed. The pipeline degrades to the remaining sources.

    ENG-17: pytrends and TikTok Creative Center are both unofficial and will
    break without notice, so a failed source must never halt collection.
    """

    platform: SourcePlatform
    reason: str
    occurred_at: datetime = field(default_factory=_now)
