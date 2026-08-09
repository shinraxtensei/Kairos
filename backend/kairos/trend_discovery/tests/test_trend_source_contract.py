"""TST-02 — the shared TrendSource contract suite.

Every adapter behind the port runs these same assertions. This is what makes
"swap the adapter" safe (CONTEXT.md §8). Adding an adapter means adding one
entry to ADAPTERS, not writing a new suite.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import httpx
import pandas as pd
import pytest

from kairos.trend_discovery.domain.ports import TrendSource, TrendSourceError
from kairos.trend_discovery.domain.value_objects import Keyword, SourcePlatform, VolumeScale
from kairos.trend_discovery.infrastructure.ebay import EbaySignalAdapter
from kairos.trend_discovery.infrastructure.google_trends import GoogleTrendsAdapter
from kairos.trend_discovery.infrastructure.keepa import AmazonSignalAdapter
from kairos.trend_discovery.tests.fakes import FakeTrendSource

SEEDS = [Keyword("cat sticker"), Keyword("moon phase print")]


class StubPytrends:
    """Stands in for pytrends.TrendReq, shaped like the real response."""

    def __init__(self, frame: pd.DataFrame | None = None, raises: Exception | None = None) -> None:
        self._frame = frame
        self._raises = raises
        self.batches: list[list[str]] = []

    def build_payload(self, terms: list[str], **_: object) -> None:
        if self._raises is not None:
            raise self._raises
        self.batches.append(list(terms))

    def interest_over_time(self) -> pd.DataFrame | None:
        return self._frame


def _frame(*, partial_tail: bool = True) -> pd.DataFrame:
    index = pd.to_datetime(["2026-07-30", "2026-07-31", "2026-08-01"])
    return pd.DataFrame(
        {
            "cat sticker": [40, 55, 99],
            "moon phase print": [10, 12, 90],
            "isPartial": [False, False, partial_tail],
        },
        index=index,
    )


def _google_adapter() -> TrendSource:
    return GoogleTrendsAdapter(request_delay_seconds=0, client=StubPytrends(_frame()))


def _fake_adapter() -> TrendSource:
    return FakeTrendSource(SourcePlatform.ETSY)


def _stub_http(payload: dict[str, object]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _ebay_adapter() -> TrendSource:
    return EbaySignalAdapter("id", "secret", http=_stub_http({"total": 4182}))


def _keepa_adapter() -> TrendSource:
    return AmazonSignalAdapter("key", http=_stub_http({"products": [{"salesRankReference": 1200}]}))


# Register every TrendSource adapter here. Adding one is a single entry, and it
# then has to satisfy the same behavioural contract as the rest — which is what
# makes swapping a source safe. EtsyTrendAdapter joins on ENG-18.
ADAPTERS: list[tuple[str, Callable[[], TrendSource]]] = [
    ("google_trends", _google_adapter),
    ("ebay", _ebay_adapter),
    ("keepa", _keepa_adapter),
    ("fake", _fake_adapter),
]


@pytest.fixture(params=[factory for _, factory in ADAPTERS], ids=[name for name, _ in ADAPTERS])
def adapter(request: pytest.FixtureRequest) -> TrendSource:
    factory: Callable[[], TrendSource] = request.param
    return factory()


class TestTrendSourceContract:
    def test_given_an_adapter_when_asked_then_it_declares_its_platform(
        self, adapter: TrendSource
    ) -> None:
        assert isinstance(adapter.platform, SourcePlatform)

    def test_given_seeds_when_fetched_then_returns_signals_for_that_platform(
        self, adapter: TrendSource
    ) -> None:
        signals = adapter.fetch(SEEDS)
        assert signals
        assert all(signal.platform is adapter.platform for signal in signals)

    def test_given_seeds_when_fetched_then_keywords_come_from_the_seeds(
        self, adapter: TrendSource
    ) -> None:
        signals = adapter.fetch(SEEDS)
        assert {signal.keyword for signal in signals} <= set(SEEDS)

    def test_given_seeds_when_fetched_then_every_signal_carries_a_volume_scale(
        self, adapter: TrendSource
    ) -> None:
        # Without this, ranking cannot tell a 0-100 index from an absolute count.
        for signal in adapter.fetch(SEEDS):
            assert isinstance(signal.search_volume.scale, VolumeScale)

    def test_given_seeds_when_fetched_then_timestamps_are_timezone_aware(
        self, adapter: TrendSource
    ) -> None:
        assert all(signal.collected_at.tzinfo is not None for signal in adapter.fetch(SEEDS))

    def test_given_seeds_when_fetched_then_each_signal_records_its_collection(
        self, adapter: TrendSource
    ) -> None:
        for signal in adapter.fetch(SEEDS):
            assert len(signal.events) == 1

    def test_given_no_seeds_when_fetched_then_returns_nothing_without_raising(
        self, adapter: TrendSource
    ) -> None:
        assert list(adapter.fetch([])) == []

    def test_given_an_adapter_when_asked_then_criticality_is_declared(
        self, adapter: TrendSource
    ) -> None:
        assert isinstance(adapter.is_critical, bool)


class TestGoogleTrendsAdapterSpecifics:
    def test_given_a_partial_final_period_when_fetched_then_it_is_excluded(self) -> None:
        """The live API marks the current period isPartial.

        Counting it reads as a sudden collapse and would drag momentum down for
        every rising keyword — the exact signal this system exists to find.
        """
        adapter = GoogleTrendsAdapter(
            request_delay_seconds=0, client=StubPytrends(_frame(partial_tail=True))
        )
        signals = {s.keyword.text: s for s in adapter.fetch(SEEDS)}
        # Last complete row is 2026-07-31, not the partial 2026-08-01 spike.
        assert signals["cat sticker"].search_volume.value == 55
        assert signals["moon phase print"].search_volume.value == 12

    def test_given_a_complete_final_period_when_fetched_then_it_is_used(self) -> None:
        adapter = GoogleTrendsAdapter(
            request_delay_seconds=0, client=StubPytrends(_frame(partial_tail=False))
        )
        signals = {s.keyword.text: s for s in adapter.fetch(SEEDS)}
        assert signals["cat sticker"].search_volume.value == 99

    def test_given_a_fetch_when_done_then_volumes_are_a_relative_index(self) -> None:
        adapter = GoogleTrendsAdapter(request_delay_seconds=0, client=StubPytrends(_frame()))
        assert all(
            signal.search_volume.scale is VolumeScale.RELATIVE_INDEX
            for signal in adapter.fetch(SEEDS)
        )

    def test_given_a_vendor_error_when_fetched_then_translated_to_trend_source_error(self) -> None:
        adapter = GoogleTrendsAdapter(
            request_delay_seconds=0, client=StubPytrends(raises=ConnectionError("429"))
        )
        with pytest.raises(TrendSourceError, match="google trends fetch failed"):
            adapter.fetch(SEEDS)

    def test_given_an_empty_response_when_fetched_then_returns_nothing(self) -> None:
        adapter = GoogleTrendsAdapter(request_delay_seconds=0, client=StubPytrends(pd.DataFrame()))
        assert adapter.fetch(SEEDS) == []

    def test_given_only_partial_periods_when_fetched_then_returns_nothing(self) -> None:
        frame = pd.DataFrame(
            {"cat sticker": [50], "isPartial": [True]}, index=pd.to_datetime(["2026-08-02"])
        )
        adapter = GoogleTrendsAdapter(request_delay_seconds=0, client=StubPytrends(frame))
        assert adapter.fetch([Keyword("cat sticker")]) == []

    def test_given_several_seeds_when_fetched_then_each_is_requested_alone(self) -> None:
        """One term per request, so the 0-100 index is relative to that keyword only.

        Batching lets Google rescale a term against its batch-mates: in a live
        run "moon phase print" scored 1 beside "cat sticker" purely because they
        shared a request. Scores would then depend on batch composition.
        """
        stub = StubPytrends(_frame())
        adapter = GoogleTrendsAdapter(request_delay_seconds=0, client=stub)
        adapter.fetch([Keyword(f"term {i}") for i in range(3)])
        assert stub.batches == [["term 0"], ["term 1"], ["term 2"]]

    def test_given_the_same_keyword_and_day_when_fetched_twice_then_ids_match(self) -> None:
        """Celery redelivery must not create a second row for the same observation."""
        first = GoogleTrendsAdapter(request_delay_seconds=0, client=StubPytrends(_frame())).fetch(
            SEEDS
        )
        second = GoogleTrendsAdapter(request_delay_seconds=0, client=StubPytrends(_frame())).fetch(
            SEEDS
        )
        assert _ids(first) == _ids(second)


def _ids(signals: Sequence[object]) -> set[str]:
    return {str(getattr(signal, "signal_id")) for signal in signals}  # noqa: B009
