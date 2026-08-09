"""AmazonSignalAdapter — Keepa API behind the TrendSource port.

Amazon is never scraped (CONTEXT.md §5). Keepa is the authorized route, and the
one serious sellers use: Amazon's terms forbid scraping, and its anti-bot stack
turns a scraper into a permanent infrastructure job rather than a feature.

**This adapter is paid and off by default.** At the entry plan it costs roughly
$31/month, which is 78% of the current $40 monthly cap and leaves $8.68 for
generation — about 6.6 winning designs a month at a 3% winner rate, and a
cost-per-winning-design of $6.08. Turning it on before the shop has traffic buys
signal that cannot be acted on. Enable it when revenue justifies it, and set
DEC-03's caps first.

Because it costs money per call, every fetch goes through Budgeting's
`metered()` — this is the first adapter where ENG-38's guard does real work.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx

from kairos.trend_discovery.domain.ports import TrendSource, TrendSourceError
from kairos.trend_discovery.domain.trend_signal import TrendSignal
from kairos.trend_discovery.domain.value_objects import (
    Keyword,
    SearchVolume,
    SourcePlatform,
)

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.keepa.com/search"
SIGNAL_NAMESPACE = uuid5(NAMESPACE_URL, "https://kairos.local/trend-signal")

# Keepa bills in tokens rather than currency. This is the amortised cost of one
# product query on the entry plan, used to price a run before it starts. Retune
# it against a real invoice rather than trusting the arithmetic here.
COST_PER_QUERY = Decimal("0.0035")

# Amazon sales rank is unbounded and category-relative: rank 1 is the best
# seller in its category, rank 500,000 is nowhere. Beyond this the difference
# stops meaning anything, so the curve is flattened rather than extended.
RANK_FLOOR = 500_000


class SpendGuard(Protocol):
    """The slice of Budgeting this adapter needs.

    Declared structurally rather than imported as a class, so Trend Discovery
    does not depend on Budgeting's types — only on the shape of the call.
    """

    def __call__(self, estimated_cost: Decimal, reference: str) -> Any: ...


def deterministic_signal_id(keyword: Keyword, observed_on: str) -> UUID:
    return uuid5(SIGNAL_NAMESPACE, f"{SourcePlatform.AMAZON.value}|{keyword.text}|{observed_on}")


def rank_to_index(sales_rank: int) -> int:
    """Turn a sales rank into a 0-100 relative index, best-seller high.

    A rank is not a volume, and pretending otherwise would let Niche Ranking
    average it with Etsy's absolute counts. Inverting it into a RELATIVE_INDEX
    keeps the scale honest — `VolumeScale` then stops the two being mixed.
    """
    if sales_rank <= 0:
        raise ValueError("sales rank must be positive")
    clamped = min(sales_rank, RANK_FLOOR)
    return round((1 - (clamped - 1) / RANK_FLOOR) * 100)


class AmazonSignalAdapter(TrendSource):
    def __init__(
        self,
        api_key: str,
        *,
        http: httpx.Client | None = None,
        domain: int = 1,  # 1 = amazon.com
        spend_guard: SpendGuard | None = None,
    ) -> None:
        self._api_key = api_key
        self._domain = domain
        self._http = http or httpx.Client(timeout=30.0)
        self._spend_guard = spend_guard

    @property
    def platform(self) -> SourcePlatform:
        return SourcePlatform.AMAZON

    def fetch(self, seeds: Sequence[Keyword]) -> Sequence[TrendSignal]:
        collected_at = datetime.now(UTC)
        observed_on = collected_at.date().isoformat()
        signals: list[TrendSignal] = []

        for keyword in seeds:
            # Budget check before the paid call, never after. If the cap is
            # reached this raises and the request is never made.
            if self._spend_guard is not None:
                self._spend_guard(COST_PER_QUERY, f"keepa:{keyword.text}")

            payload = self._search(keyword)
            rank = self._best_sales_rank(payload)
            if rank is None:
                logger.info("keepa returned no ranked product for %r", keyword.text)
                continue

            signals.append(
                TrendSignal.collect(
                    signal_id=deterministic_signal_id(keyword, observed_on),
                    platform=self.platform,
                    keyword=keyword,
                    search_volume=SearchVolume.relative_index(rank_to_index(rank)),
                    collected_at=collected_at,
                    raw_payload={
                        "best_sales_rank": rank,
                        "domain": self._domain,
                        "observed_on": observed_on,
                        "products_considered": len(payload.get("products", [])),
                    },
                )
            )
        return signals

    def _search(self, keyword: Keyword) -> dict[str, Any]:
        try:
            response = self._http.get(
                SEARCH_URL,
                params={
                    "key": self._api_key,
                    "domain": self._domain,
                    "type": "product",
                    "term": keyword.text,
                },
            )
            response.raise_for_status()
            result: dict[str, Any] = response.json()
        except Exception as exc:
            raise TrendSourceError(f"keepa search failed for {keyword.text!r}: {exc}") from exc
        return result

    @staticmethod
    def _best_sales_rank(payload: dict[str, Any]) -> int | None:
        """Best (lowest) rank across returned products.

        A term's opportunity is set by how well the leaders do, not by the
        average across a long tail of dead listings.
        """
        ranks = [
            int(product["salesRankReference"])
            for product in payload.get("products", [])
            if isinstance(product.get("salesRankReference"), int)
            and product["salesRankReference"] > 0
        ]
        return min(ranks) if ranks else None
