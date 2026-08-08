"""Domain tests: pure, no mocks, no I/O (CONTEXT.md §8)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from kairos.trend_discovery.domain.trend_signal import TrendSignal
from kairos.trend_discovery.domain.value_objects import (
    CompetitionBand,
    CompetitionLevel,
    Keyword,
    SearchVolume,
    SourcePlatform,
    VolumeScale,
)


class TestKeyword:
    def test_given_mixed_case_and_padding_when_built_then_normalises(self) -> None:
        assert Keyword("  Cat   STICKER ") == Keyword("cat sticker")

    @pytest.mark.parametrize("text", ["", "   ", "\t\n"])
    def test_given_blank_text_when_built_then_raises(self, text: str) -> None:
        with pytest.raises(ValueError, match="blank"):
            Keyword(text)

    def test_given_an_overlong_term_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="exceeds"):
            Keyword("a" * 201)


class TestSearchVolume:
    def test_given_a_relative_index_above_100_when_built_then_raises(self) -> None:
        # Google Trends is a 0-100 index. A 4,182 here means an absolute count
        # was mislabelled, which would wreck any cross-source comparison.
        with pytest.raises(ValueError, match="cannot exceed 100"):
            SearchVolume.relative_index(4182)

    def test_given_an_absolute_count_when_built_then_allows_large_values(self) -> None:
        assert SearchVolume.absolute(4182).value == 4182

    def test_given_a_negative_value_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            SearchVolume.absolute(-1)

    def test_given_a_bool_when_built_then_raises(self) -> None:
        with pytest.raises(TypeError):
            SearchVolume(True, VolumeScale.ABSOLUTE)

    def test_given_different_scales_when_compared_then_not_comparable(self) -> None:
        assert not SearchVolume.absolute(50).is_comparable_to(SearchVolume.relative_index(50))

    def test_given_same_scale_when_compared_then_comparable(self) -> None:
        assert SearchVolume.absolute(1).is_comparable_to(SearchVolume.absolute(9999))


class TestCompetitionLevel:
    @pytest.mark.parametrize(
        ("count", "band"),
        [
            (0, CompetitionBand.LOW),
            (99, CompetitionBand.LOW),
            (5_000, CompetitionBand.MEDIUM),
            (60_000, CompetitionBand.HIGH),
            (2_000_000, CompetitionBand.HIGH),
        ],
    )
    def test_given_a_listing_count_when_mapped_then_lands_in_expected_band(
        self, count: int, band: CompetitionBand
    ) -> None:
        assert CompetitionLevel.from_competing_listings(count).band is band

    def test_given_a_negative_count_when_mapped_then_raises(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            CompetitionLevel.from_competing_listings(-1)

    @pytest.mark.parametrize("score", [-1, 101])
    def test_given_an_out_of_range_score_when_built_then_raises(self, score: int) -> None:
        with pytest.raises(ValueError, match="between 0 and 100"):
            CompetitionLevel(score)


class TestTrendSignal:
    def _signal(self, **overrides: object) -> TrendSignal:
        defaults: dict[str, object] = {
            "platform": SourcePlatform.GOOGLE_TRENDS,
            "keyword": Keyword("cat sticker"),
            "search_volume": SearchVolume.relative_index(73),
        }
        return TrendSignal.collect(**{**defaults, **overrides})  # type: ignore[arg-type]

    def test_given_a_collected_signal_when_events_pulled_then_reports_collection(self) -> None:
        signal = self._signal()
        events = signal.pull_events()
        assert len(events) == 1
        assert events[0].signal_id == signal.signal_id

    def test_given_events_already_pulled_when_pulled_again_then_empty(self) -> None:
        signal = self._signal()
        signal.pull_events()
        assert signal.pull_events() == []

    def test_given_a_naive_timestamp_when_collected_then_raises(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            self._signal(collected_at=datetime(2026, 8, 1, 12, 0))  # noqa: DTZ001

    def test_given_a_far_future_timestamp_when_collected_then_raises(self) -> None:
        with pytest.raises(ValueError, match="in the future"):
            self._signal(collected_at=datetime.now(UTC) + timedelta(hours=2))

    def test_given_small_clock_drift_when_collected_then_allowed(self) -> None:
        assert self._signal(collected_at=datetime.now(UTC) + timedelta(seconds=30))

    def test_given_a_non_utc_timestamp_when_collected_then_converts_to_utc(self) -> None:
        signal = self._signal(collected_at=datetime.now(tz=timezone(timedelta(hours=2))))
        assert signal.collected_at.tzinfo is UTC

    def test_given_a_raw_payload_when_collected_then_it_cannot_be_mutated(self) -> None:
        signal = self._signal(raw_payload={"series": [1, 2, 3]})
        with pytest.raises(TypeError):
            signal.raw_payload["series"] = []  # type: ignore[index]

    def test_given_two_signals_with_the_same_id_when_compared_then_equal(self) -> None:
        first = self._signal()
        second = self._signal(signal_id=first.signal_id, search_volume=SearchVolume.absolute(1))
        # Identity is the id — an aggregate stays itself as its values change.
        assert first == second
