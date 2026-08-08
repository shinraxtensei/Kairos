"""FetchTrendSignals — the FetchTrendSignals command from CONTEXT.md §4.1."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from kairos.trend_discovery.domain.events import TrendSignalCollected, TrendSourceSyncFailed
from kairos.trend_discovery.domain.ports import (
    TrendSignalRepository,
    TrendSource,
    TrendSourceError,
)
from kairos.trend_discovery.domain.value_objects import Keyword, SourcePlatform

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FetchResult:
    collected: list[TrendSignalCollected] = field(default_factory=list)
    failures: list[TrendSourceSyncFailed] = field(default_factory=list)

    @property
    def succeeded_platforms(self) -> set[SourcePlatform]:
        return {event.platform for event in self.collected}

    @property
    def all_sources_failed(self) -> bool:
        return bool(self.failures) and not self.collected


class FetchTrendSignals:
    """Collects from every configured source and persists what came back.

    ENG-17 — a failing source degrades the run, it does not halt it. pytrends is
    unofficial and TikTok Creative Center is an undocumented internal endpoint;
    both are expected to break, and a run that aborts on the first failure would
    silently stop collecting from the sources that still work.
    """

    def __init__(self, sources: Sequence[TrendSource], repository: TrendSignalRepository) -> None:
        self._sources = sources
        self._repository = repository

    def __call__(self, seeds: Sequence[Keyword]) -> FetchResult:
        if not seeds:
            raise ValueError("at least one seed keyword is required")

        collected: list[TrendSignalCollected] = []
        failures: list[TrendSourceSyncFailed] = []

        for source in self._sources:
            try:
                signals = source.fetch(seeds)
            except TrendSourceError as exc:
                logger.warning("trend source %s failed: %s", source.platform, exc)
                failures.append(TrendSourceSyncFailed(platform=source.platform, reason=str(exc)))
                continue
            except Exception as exc:
                # An adapter that leaks a vendor exception is a bug in that
                # adapter, but it must not take the whole run down with it.
                logger.exception("trend source %s raised an untranslated error", source.platform)
                failures.append(
                    TrendSourceSyncFailed(
                        platform=source.platform,
                        reason=f"untranslated {type(exc).__name__}: {exc}",
                    )
                )
                continue

            if signals:
                self._repository.add_all(signals)
                for signal in signals:
                    collected.extend(signal.pull_events())

        if failures and not collected:
            logger.error("every trend source failed — no signals collected this run")

        return FetchResult(collected=collected, failures=failures)
