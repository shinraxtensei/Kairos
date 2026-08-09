"""EbaySignalAdapter — eBay Browse API behind the TrendSource port.

Official and sanctioned (CONTEXT.md §5). No scraping, no anti-bot arms race,
and free at the tier this needs.

What it actually measures: `item_summary/search` returns `total`, the number of
*active listings* for a term. That is a competition signal, not demand — eBay's
sold-item counts live behind Marketplace Insights, which needs a higher account
tier. Reporting it as demand would be a lie the ranking formula cannot detect,
so it is mapped to CompetitionLevel and the volume is left absolute and small.
"""

from __future__ import annotations

import base64
import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx

from kairos.trend_discovery.domain.ports import TrendSource, TrendSourceError
from kairos.trend_discovery.domain.trend_signal import TrendSignal
from kairos.trend_discovery.domain.value_objects import (
    CompetitionLevel,
    Keyword,
    SearchVolume,
    SourcePlatform,
)

logger = logging.getLogger(__name__)

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"

SIGNAL_NAMESPACE = uuid5(NAMESPACE_URL, "https://kairos.local/trend-signal")
# Tokens last two hours; refresh early so a long run cannot expire mid-flight.
TOKEN_SAFETY_MARGIN_SECONDS = 300


def deterministic_signal_id(keyword: Keyword, observed_on: str) -> UUID:
    return uuid5(SIGNAL_NAMESPACE, f"{SourcePlatform.EBAY.value}|{keyword.text}|{observed_on}")


class EbaySignalAdapter(TrendSource):
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        http: httpx.Client | None = None,
        marketplace: str = "EBAY_US",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._marketplace = marketplace
        self._http = http or httpx.Client(timeout=20.0)
        self._token: str | None = None
        self._token_expires_at = 0.0

    @property
    def platform(self) -> SourcePlatform:
        return SourcePlatform.EBAY

    def _access_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        basic = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode()
        try:
            response = self._http.post(
                TOKEN_URL,
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials", "scope": SCOPE},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise TrendSourceError(f"ebay token request failed: {exc}") from exc

        self._token = str(payload["access_token"])
        self._token_expires_at = (
            time.monotonic() + float(payload.get("expires_in", 7200)) - TOKEN_SAFETY_MARGIN_SECONDS
        )
        return self._token

    def _search(self, keyword: Keyword) -> dict[str, Any]:
        try:
            response = self._http.get(
                SEARCH_URL,
                headers={
                    "Authorization": f"Bearer {self._access_token()}",
                    "X-EBAY-C-MARKETPLACE-ID": self._marketplace,
                },
                # limit=1 because only the `total` count is wanted; pulling
                # items would spend quota on data that is thrown away.
                params={"q": keyword.text, "limit": 1},
            )
            response.raise_for_status()
            result: dict[str, Any] = response.json()
        except TrendSourceError:
            raise
        except Exception as exc:
            raise TrendSourceError(f"ebay search failed for {keyword.text!r}: {exc}") from exc
        return result

    def fetch(self, seeds: Sequence[Keyword]) -> Sequence[TrendSignal]:
        collected_at = datetime.now(UTC)
        observed_on = collected_at.date().isoformat()
        signals: list[TrendSignal] = []

        for keyword in seeds:
            payload = self._search(keyword)
            total = int(payload.get("total", 0))
            signals.append(
                TrendSignal.collect(
                    signal_id=deterministic_signal_id(keyword, observed_on),
                    platform=self.platform,
                    keyword=keyword,
                    # Absolute count of competing listings. Not demand — see the
                    # module docstring.
                    search_volume=SearchVolume.absolute(total),
                    competition=CompetitionLevel.from_competing_listings(total),
                    collected_at=collected_at,
                    raw_payload={
                        "total": total,
                        "marketplace": self._marketplace,
                        "observed_on": observed_on,
                    },
                )
            )
        return signals
