"""eBay and Keepa adapters, against stubbed HTTP.

Neither is ever pointed at a live endpoint in the default run: eBay needs app
credentials and Keepa costs money per call.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import pytest

from kairos.trend_discovery.domain.ports import TrendSourceError
from kairos.trend_discovery.domain.value_objects import (
    Keyword,
    SourcePlatform,
    VolumeScale,
)
from kairos.trend_discovery.infrastructure.ebay import EbaySignalAdapter
from kairos.trend_discovery.infrastructure.keepa import (
    COST_PER_QUERY,
    RANK_FLOOR,
    AmazonSignalAdapter,
    rank_to_index,
)

SEEDS = [Keyword("moon phase print")]


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestEbayAdapter:
    def _ok(self, total: int = 4182) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/token"):
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
            return httpx.Response(200, json={"total": total, "itemSummaries": []})

        return _client(handler)

    def test_given_a_search_when_fetched_then_reports_competing_listings(self) -> None:
        adapter = EbaySignalAdapter("id", "secret", http=self._ok(4182))
        (signal,) = adapter.fetch(SEEDS)

        assert signal.platform is SourcePlatform.EBAY
        assert signal.search_volume.value == 4182
        # Absolute, because it is a real count — not a 0-100 index.
        assert signal.search_volume.scale is VolumeScale.ABSOLUTE
        assert signal.competition is not None
        assert signal.raw_payload["total"] == 4182

    def test_given_a_second_fetch_when_called_then_the_token_is_reused(self) -> None:
        """A token request per keyword would triple the call volume for nothing."""
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if request.url.path.endswith("/token"):
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
            return httpx.Response(200, json={"total": 10})

        adapter = EbaySignalAdapter("id", "secret", http=_client(handler))
        adapter.fetch([Keyword("a"), Keyword("b"), Keyword("c")])

        assert sum(1 for path in calls if path.endswith("/token")) == 1

    def test_given_the_same_keyword_and_day_when_fetched_twice_then_ids_match(self) -> None:
        first = EbaySignalAdapter("id", "secret", http=self._ok()).fetch(SEEDS)
        second = EbaySignalAdapter("id", "secret", http=self._ok()).fetch(SEEDS)
        assert first[0].signal_id == second[0].signal_id

    def test_given_an_auth_failure_when_fetched_then_translated(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "invalid_client"})

        adapter = EbaySignalAdapter("bad", "creds", http=_client(handler))
        with pytest.raises(TrendSourceError, match="ebay token request failed"):
            adapter.fetch(SEEDS)

    def test_given_a_search_failure_when_fetched_then_translated(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/token"):
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
            return httpx.Response(500, text="boom")

        adapter = EbaySignalAdapter("id", "secret", http=_client(handler))
        with pytest.raises(TrendSourceError, match="ebay search failed"):
            adapter.fetch(SEEDS)

    def test_given_no_seeds_when_fetched_then_returns_nothing(self) -> None:
        assert EbaySignalAdapter("id", "secret", http=self._ok()).fetch([]) == []


class TestRankConversion:
    def test_given_the_top_rank_when_converted_then_maxes_out(self) -> None:
        assert rank_to_index(1) == 100

    def test_given_a_hopeless_rank_when_converted_then_bottoms_out(self) -> None:
        assert rank_to_index(RANK_FLOOR) == 0

    def test_given_a_rank_past_the_floor_when_converted_then_clamps(self) -> None:
        # Rank 900,000 and rank 5,000,000 are equally irrelevant.
        assert rank_to_index(RANK_FLOOR * 2) == rank_to_index(RANK_FLOOR)

    def test_given_a_better_rank_when_converted_then_scores_higher(self) -> None:
        assert rank_to_index(100) > rank_to_index(50_000)

    def test_given_a_non_positive_rank_when_converted_then_raises(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            rank_to_index(0)


class TestKeepaAdapter:
    def _ok(self, *ranks: int) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"products": [{"salesRankReference": r} for r in ranks]}
            )

        return _client(handler)

    def test_given_products_when_fetched_then_uses_the_best_rank(self) -> None:
        """Opportunity is set by how well the leaders do, not the long tail."""
        adapter = AmazonSignalAdapter("key", http=self._ok(90_000, 1_200, 400_000))
        (signal,) = adapter.fetch(SEEDS)
        assert signal.raw_payload["best_sales_rank"] == 1_200

    def test_given_a_rank_when_fetched_then_the_scale_is_a_relative_index(self) -> None:
        """A rank is not a volume. Marking it absolute would let Niche Ranking
        average it with Etsy's counts."""
        adapter = AmazonSignalAdapter("key", http=self._ok(1_200))
        (signal,) = adapter.fetch(SEEDS)
        assert signal.search_volume.scale is VolumeScale.RELATIVE_INDEX
        assert 0 <= signal.search_volume.value <= 100

    def test_given_no_ranked_products_when_fetched_then_skips_the_keyword(self) -> None:
        adapter = AmazonSignalAdapter("key", http=self._ok())
        assert adapter.fetch(SEEDS) == []

    def test_given_a_vendor_error_when_fetched_then_translated(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="token limit")

        adapter = AmazonSignalAdapter("key", http=_client(handler))
        with pytest.raises(TrendSourceError, match="keepa search failed"):
            adapter.fetch(SEEDS)

    def test_given_a_spend_guard_when_fetched_then_it_is_consulted_per_keyword(self) -> None:
        seen: list[tuple[Decimal, str]] = []

        def guard(estimated_cost: Decimal, reference: str) -> None:
            seen.append((estimated_cost, reference))

        adapter = AmazonSignalAdapter("key", http=self._ok(1_000), spend_guard=guard)
        adapter.fetch([Keyword("a"), Keyword("b")])

        assert [ref for _, ref in seen] == ["keepa:a", "keepa:b"]
        assert all(cost == COST_PER_QUERY for cost, _ in seen)

    def test_given_a_refusing_spend_guard_when_fetched_then_no_paid_call_happens(self) -> None:
        """The whole point of metering a paid adapter: the cap stops the request
        before the money leaves, not after."""
        requests: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))  # pragma: no cover - must not run
            return httpx.Response(200, json={"products": []})

        def guard(estimated_cost: Decimal, reference: str) -> None:
            raise RuntimeError("budget cap reached")

        adapter = AmazonSignalAdapter("key", http=_client(handler), spend_guard=guard)
        with pytest.raises(RuntimeError, match="budget cap reached"):
            adapter.fetch(SEEDS)

        assert requests == []
