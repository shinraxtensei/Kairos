"""Read-side API that other contexts call.

This is the *only* thing another context may touch in Trend Discovery. It hands
back a neutral DTO, never a `TrendSignal` — callers must not depend on this
context's domain model (CONTEXT.md §3.1).

Translating `VolumeScale` into named fields happens here, because this context
is the one that knows what its own numbers mean. A caller receiving a bare
number would have to re-derive whether 73 is a momentum index or a result count.
"""

from __future__ import annotations

from dataclasses import dataclass

from kairos.trend_discovery.domain.ports import TrendSignalRepository
from kairos.trend_discovery.domain.value_objects import VolumeScale


@dataclass(frozen=True, slots=True)
class KeywordSignals:
    """What every source currently says about one keyword."""

    keyword: str
    momentum_index: int | None = None
    demand_volume: int | None = None
    competition: int | None = None
    source_count: int = 0


class LatestSignalsPerKeyword:
    """Collapse the signal history into one current picture per keyword."""

    def __init__(self, repository: TrendSignalRepository) -> None:
        self._repository = repository

    def __call__(self) -> list[KeywordSignals]:
        momentum: dict[str, int] = {}
        demand: dict[str, int] = {}
        competition: dict[str, int] = {}
        platforms: dict[str, set[str]] = {}

        # One row per (keyword, platform) already — not a time window, so a
        # keyword with months of history cannot crowd out the others.
        for signal in self._repository.latest_per_keyword_and_platform():
            keyword = signal.keyword.text
            platforms.setdefault(keyword, set()).add(signal.platform.value)

            if signal.search_volume.scale is VolumeScale.RELATIVE_INDEX:
                momentum.setdefault(keyword, signal.search_volume.value)
            else:
                demand.setdefault(keyword, signal.search_volume.value)
            if signal.competition is not None:
                competition.setdefault(keyword, signal.competition.score)

        return [
            KeywordSignals(
                keyword=keyword,
                momentum_index=momentum.get(keyword),
                demand_volume=demand.get(keyword),
                competition=competition.get(keyword),
                source_count=len(sources),
            )
            for keyword, sources in sorted(platforms.items())
        ]
