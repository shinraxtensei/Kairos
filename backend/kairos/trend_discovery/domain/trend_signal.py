"""The TrendSignal aggregate — one raw signal, from one source, at one time."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from kairos.trend_discovery.domain.events import TrendSignalCollected
from kairos.trend_discovery.domain.value_objects import (
    CompetitionLevel,
    Keyword,
    SearchVolume,
    SourcePlatform,
)

# Clocks drift and third-party APIs report their own timestamps. A little slack
# absorbs that; a lot would let a bad payload poison the momentum window.
FUTURE_TOLERANCE_SECONDS = 300


@dataclass(eq=False, slots=True)
class TrendSignal:
    signal_id: UUID
    platform: SourcePlatform
    keyword: Keyword
    search_volume: SearchVolume
    collected_at: datetime
    competition: CompetitionLevel | None = None
    # Opaque to the domain — kept so a signal can be re-scored later against a
    # changed formula without re-fetching (ENG-21). Never interpreted here.
    raw_payload: Mapping[str, Any] = field(default_factory=dict)
    events: list[TrendSignalCollected] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if self.collected_at.tzinfo is None:
            raise ValueError("collected_at must be timezone-aware — naive datetimes lie")
        object.__setattr__(self, "collected_at", self.collected_at.astimezone(UTC))
        drift = (self.collected_at - datetime.now(UTC)).total_seconds()
        if drift > FUTURE_TOLERANCE_SECONDS:
            raise ValueError(f"collected_at is {drift:.0f}s in the future")
        object.__setattr__(self, "raw_payload", MappingProxyType(dict(self.raw_payload)))

    @classmethod
    def collect(
        cls,
        *,
        platform: SourcePlatform,
        keyword: Keyword,
        search_volume: SearchVolume,
        collected_at: datetime | None = None,
        competition: CompetitionLevel | None = None,
        raw_payload: Mapping[str, Any] | None = None,
        signal_id: UUID | None = None,
    ) -> TrendSignal:
        signal = cls(
            signal_id=signal_id or uuid4(),
            platform=platform,
            keyword=keyword,
            search_volume=search_volume,
            collected_at=collected_at or datetime.now(UTC),
            competition=competition,
            raw_payload=raw_payload or {},
        )
        signal.events.append(
            TrendSignalCollected(signal_id=signal.signal_id, platform=platform, keyword=keyword)
        )
        return signal

    def pull_events(self) -> list[TrendSignalCollected]:
        """Hand the recorded events to the caller and clear them."""
        drained, self.events = self.events, []
        return drained

    def __eq__(self, other: object) -> bool:
        # Aggregate identity is the id, not the field values.
        return isinstance(other, TrendSignal) and self.signal_id == other.signal_id

    def __hash__(self) -> int:
        return hash(self.signal_id)
