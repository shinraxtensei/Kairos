"""GoogleTrendsAdapter — pytrends behind the TrendSource port.

pytrends is unofficial: no login and no account to ban (CONTEXT.md §5), but it
breaks whenever Google changes its endpoints. It is therefore non-critical by
default — a failure degrades the run rather than stopping it (ENG-17).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pytrends.request import TrendReq

from kairos.trend_discovery.domain.ports import TrendSource, TrendSourceError
from kairos.trend_discovery.domain.trend_signal import TrendSignal
from kairos.trend_discovery.domain.value_objects import Keyword, SearchVolume, SourcePlatform

logger = logging.getLogger(__name__)

# Google Trends accepts up to five terms per request, but rescales the 0-100
# index so that the batch's single highest point becomes 100. A term batched
# against a much more popular one is squashed toward zero: in a live run
# "moon phase print" scored 1 next to "cat sticker" — not because interest was
# low, but because it shared a request. A keyword's score would then depend on
# which other keywords happened to sit beside it, which makes cross-keyword
# ranking meaningless.
#
# Fetching one term per request makes the index relative to that keyword's own
# history instead: "current interest as a share of its own peak this timeframe",
# which is comparable across keywords and is the momentum signal Niche Ranking
# actually wants. Google Trends is the momentum source; Etsy supplies absolute
# demand. The cost is one request per seed — acceptable at a daily cadence with
# a modest seed list, and the reason batching is not worth restoring.
TERMS_PER_REQUEST = 1
DEFAULT_TIMEFRAME = "today 3-m"

# One request per seed means more requests, and Google answers 429 readily —
# it did so during development after only a handful of calls. A pause between
# requests keeps a daily run under the threshold. Tune it against real seed-list
# sizes rather than trusting this default; the hardware here is someone else's
# rate limiter and it is not documented.
DEFAULT_REQUEST_DELAY_SECONDS = 2.0

SIGNAL_NAMESPACE = uuid5(NAMESPACE_URL, "https://kairos.local/trend-signal")


def deterministic_signal_id(platform: SourcePlatform, keyword: Keyword, observed_on: str) -> UUID:
    """Same platform + keyword + observation day always yields the same id.

    Makes re-running a day's collection idempotent, which matters because
    task_acks_late means Celery redelivery is normal operation.
    """
    return uuid5(SIGNAL_NAMESPACE, f"{platform.value}|{keyword.text}|{observed_on}")


def _batched(seeds: Sequence[Keyword], size: int) -> Iterator[Sequence[Keyword]]:
    for start in range(0, len(seeds), size):
        yield seeds[start : start + size]


class GoogleTrendsAdapter(TrendSource):
    def __init__(
        self,
        client: Any | None = None,
        *,
        timeframe: str = DEFAULT_TIMEFRAME,
        geo: str = "",
        request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
    ) -> None:
        self._client = client or TrendReq(hl="en-US", tz=0)
        self._timeframe = timeframe
        self._geo = geo
        self._request_delay_seconds = request_delay_seconds

    @property
    def platform(self) -> SourcePlatform:
        return SourcePlatform.GOOGLE_TRENDS

    def fetch(self, seeds: Sequence[Keyword]) -> Sequence[TrendSignal]:
        signals: list[TrendSignal] = []
        for index, batch in enumerate(_batched(seeds, TERMS_PER_REQUEST)):
            if index and self._request_delay_seconds:
                time.sleep(self._request_delay_seconds)
            signals.extend(self._fetch_batch(batch))
        return signals

    def _fetch_batch(self, batch: Sequence[Keyword]) -> list[TrendSignal]:
        terms = [keyword.text for keyword in batch]
        try:
            self._client.build_payload(terms, timeframe=self._timeframe, geo=self._geo)
            frame = self._client.interest_over_time()
        except Exception as exc:
            # Vendor exceptions never escape the adapter — the application layer
            # handles TrendSourceError and degrades.
            raise TrendSourceError(f"google trends fetch failed for {terms}: {exc}") from exc

        if frame is None or frame.empty:
            logger.info("google trends returned nothing for %s", terms)
            return []

        # The final row is usually a partial period. Counting it reads as a
        # sudden drop and would drag momentum down for every rising keyword.
        if "isPartial" in frame.columns:
            frame = frame[~frame["isPartial"].astype(bool)]
        if frame.empty:
            logger.info("google trends returned only partial periods for %s", terms)
            return []

        latest = frame.iloc[-1]
        observed_on = frame.index[-1].date().isoformat()
        collected_at = datetime.now(UTC)

        signals = []
        for keyword in batch:
            if keyword.text not in frame.columns:
                continue
            signals.append(
                TrendSignal.collect(
                    signal_id=deterministic_signal_id(self.platform, keyword, observed_on),
                    platform=self.platform,
                    keyword=keyword,
                    # 0-100 interest relative to this keyword's own peak over
                    # the timeframe — momentum, not volume. The scale travels
                    # with the number so ranking cannot silently mix it with
                    # Etsy's absolute counts.
                    search_volume=SearchVolume.relative_index(int(latest[keyword.text])),
                    collected_at=collected_at,
                    raw_payload={
                        "observed_on": observed_on,
                        "timeframe": self._timeframe,
                        "geo": self._geo,
                        "batch_terms": terms,
                        "series": [int(value) for value in frame[keyword.text].tolist()],
                    },
                )
            )
        return signals
