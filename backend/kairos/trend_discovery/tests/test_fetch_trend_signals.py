"""Application-layer tests — real ports, fake adapters, no I/O (CONTEXT.md §8)."""

import pytest

from kairos.trend_discovery.application.fetch_trend_signals import FetchTrendSignals
from kairos.trend_discovery.domain.ports import TrendSourceError
from kairos.trend_discovery.domain.value_objects import Keyword, SourcePlatform
from kairos.trend_discovery.tests.fakes import (
    ExplodingRepository,
    FakeTrendSource,
    InMemoryTrendSignalRepository,
)

SEEDS = [Keyword("cat sticker"), Keyword("moon phase print")]


def test_given_two_healthy_sources_when_fetched_then_persists_every_signal() -> None:
    repository = InMemoryTrendSignalRepository()
    sources = [
        FakeTrendSource(SourcePlatform.GOOGLE_TRENDS),
        FakeTrendSource(SourcePlatform.ETSY),
    ]

    result = FetchTrendSignals(sources, repository)(SEEDS)

    assert len(result.collected) == 4
    assert not result.failures
    assert len(repository.signals) == 4


def test_given_one_failing_source_when_fetched_then_the_others_still_collect() -> None:
    """ENG-17. pytrends breaking must not stop Etsy from being collected."""
    repository = InMemoryTrendSignalRepository()
    sources = [
        FakeTrendSource(
            SourcePlatform.GOOGLE_TRENDS, fails_with=TrendSourceError("endpoint moved")
        ),
        FakeTrendSource(SourcePlatform.ETSY),
    ]

    result = FetchTrendSignals(sources, repository)(SEEDS)

    assert result.succeeded_platforms == {SourcePlatform.ETSY}
    assert [f.platform for f in result.failures] == [SourcePlatform.GOOGLE_TRENDS]
    assert len(repository.signals) == 2
    assert not result.all_sources_failed


def test_given_a_source_leaking_a_vendor_exception_when_fetched_then_still_degrades() -> None:
    """An adapter that forgets to translate its errors is a bug, not an outage."""
    repository = InMemoryTrendSignalRepository()
    sources = [
        FakeTrendSource(SourcePlatform.TIKTOK, fails_with=KeyError("unexpected schema")),
        FakeTrendSource(SourcePlatform.ETSY),
    ]

    result = FetchTrendSignals(sources, repository)(SEEDS)

    assert len(result.collected) == 2
    assert "untranslated KeyError" in result.failures[0].reason


def test_given_every_source_failing_when_fetched_then_reports_total_failure() -> None:
    repository = InMemoryTrendSignalRepository()
    sources = [
        FakeTrendSource(SourcePlatform.GOOGLE_TRENDS, fails_with=TrendSourceError("down")),
        FakeTrendSource(SourcePlatform.TIKTOK, fails_with=TrendSourceError("down")),
    ]

    result = FetchTrendSignals(sources, repository)(SEEDS)

    assert result.all_sources_failed
    assert len(result.failures) == 2


def test_given_a_broken_database_when_fetched_then_raises_rather_than_reporting_success() -> None:
    """Degradation covers flaky sources, not a dead database — that must surface."""
    sources = [FakeTrendSource(SourcePlatform.ETSY)]

    with pytest.raises(RuntimeError, match="database is down"):
        FetchTrendSignals(sources, ExplodingRepository())(SEEDS)


def test_given_no_seeds_when_fetched_then_raises() -> None:
    with pytest.raises(ValueError, match="at least one seed"):
        FetchTrendSignals([], InMemoryTrendSignalRepository())([])


def test_given_a_successful_run_when_finished_then_events_are_drained_once() -> None:
    repository = InMemoryTrendSignalRepository()
    sources = [FakeTrendSource(SourcePlatform.ETSY)]

    result = FetchTrendSignals(sources, repository)(SEEDS)

    assert len(result.collected) == 2
    # The aggregate must not still be holding events after they were reported,
    # or a second publish of the same run would double-count.
    assert all(not signal.events for signal in repository.signals.values())
