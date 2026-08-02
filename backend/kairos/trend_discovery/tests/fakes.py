"""Hand-written fakes implementing the real ports.

Deliberately not unittest.mock: a fake that implements the port breaks when the
port changes, while a mock keeps passing against an interface that no longer
exists (CONTEXT.md §8).
"""

from __future__ import annotations

from collections.abc import Sequence

from kairos.trend_discovery.domain.ports import (
    TrendSignalRepository,
    TrendSource,
    TrendSourceError,
)
from kairos.trend_discovery.domain.trend_signal import TrendSignal
from kairos.trend_discovery.domain.value_objects import Keyword, SearchVolume, SourcePlatform


class FakeTrendSource(TrendSource):
    def __init__(
        self,
        platform: SourcePlatform,
        *,
        fails_with: Exception | None = None,
        volume: int = 50,
    ) -> None:
        self._platform = platform
        self._fails_with = fails_with
        self._volume = volume
        self.calls: list[Sequence[Keyword]] = []

    @property
    def platform(self) -> SourcePlatform:
        return self._platform

    def fetch(self, seeds: Sequence[Keyword]) -> Sequence[TrendSignal]:
        self.calls.append(seeds)
        if self._fails_with is not None:
            raise self._fails_with
        return [
            TrendSignal.collect(
                platform=self._platform,
                keyword=keyword,
                search_volume=SearchVolume.relative_index(self._volume),
            )
            for keyword in seeds
        ]


class InMemoryTrendSignalRepository(TrendSignalRepository):
    def __init__(self) -> None:
        self.signals: dict[str, TrendSignal] = {}

    def add_all(self, signals: Sequence[TrendSignal]) -> None:
        for signal in signals:
            self.signals[str(signal.signal_id)] = signal

    def recent(
        self, *, platform: SourcePlatform | None = None, limit: int = 100
    ) -> Sequence[TrendSignal]:
        rows = sorted(self.signals.values(), key=lambda s: s.collected_at, reverse=True)
        if platform is not None:
            rows = [row for row in rows if row.platform is platform]
        return rows[:limit]


class ExplodingRepository(TrendSignalRepository):
    """Proves persistence failures are not silently swallowed."""

    def add_all(self, signals: Sequence[TrendSignal]) -> None:
        raise RuntimeError("database is down")

    def recent(
        self, *, platform: SourcePlatform | None = None, limit: int = 100
    ) -> Sequence[TrendSignal]:
        raise RuntimeError("database is down")


__all__ = [
    "ExplodingRepository",
    "FakeTrendSource",
    "InMemoryTrendSignalRepository",
    "TrendSourceError",
]
