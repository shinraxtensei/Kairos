"""Scheduled collection (ENG-22).

Daily is deliberate: nothing about niche discovery is real-time, and every extra
run costs quota against sources that rate-limit.
"""

from __future__ import annotations

import logging
from typing import Any

from kairos.celery_app import celery_app
from kairos.config import get_settings
from kairos.db import SessionLocal
from kairos.trend_discovery.application.fetch_trend_signals import FetchTrendSignals
from kairos.trend_discovery.domain.ports import TrendSource
from kairos.trend_discovery.domain.value_objects import Keyword
from kairos.trend_discovery.infrastructure.ebay import EbaySignalAdapter
from kairos.trend_discovery.infrastructure.google_trends import GoogleTrendsAdapter
from kairos.trend_discovery.infrastructure.keepa import AmazonSignalAdapter
from kairos.trend_discovery.infrastructure.repository import SqlAlchemyTrendSignalRepository

logger = logging.getLogger(__name__)

# Seeds are a placeholder until Niche Ranking feeds them back (M7). Keeping them
# here rather than in config is fine while there is one operator and one shop.
DEFAULT_SEEDS = [
    "cat sticker",
    "moon phase print",
    "boho wall art",
    "digital planner",
    "watercolor clipart",
]


def build_sources() -> list[TrendSource]:
    """Every source with usable credentials. Missing ones are skipped, not faked.

    EtsyTrendAdapter joins on ENG-18 once M0 supplies the API keys.
    """
    settings = get_settings()
    sources: list[TrendSource] = [GoogleTrendsAdapter()]

    if settings.ebay_client_id and settings.ebay_client_secret:
        sources.append(EbaySignalAdapter(settings.ebay_client_id, settings.ebay_client_secret))
    else:
        logger.info("ebay credentials absent — skipping that source")

    # Paid, and deliberately behind a second switch: having a key should not be
    # enough to start spending.
    if settings.keepa_enabled and settings.keepa_api_key:
        sources.append(AmazonSignalAdapter(settings.keepa_api_key))
    elif settings.keepa_api_key:
        logger.info("keepa key present but KAIROS_KEEPA_ENABLED is false — skipping")

    return sources


@celery_app.task(name="kairos.trend_discovery.collect")
def collect_trend_signals(seeds: list[str] | None = None) -> dict[str, Any]:
    keywords = [Keyword(text) for text in (seeds or DEFAULT_SEEDS)]
    with SessionLocal() as session:
        result = FetchTrendSignals(build_sources(), SqlAlchemyTrendSignalRepository(session))(
            keywords
        )

    if result.all_sources_failed:
        # Not raised: retrying immediately would hammer a source that is already
        # failing. OPS-04 alerting picks this up from the log.
        logger.error("trend collection produced nothing — every source failed")

    return {
        "collected": len(result.collected),
        "failures": [f"{f.platform}: {f.reason}" for f in result.failures],
    }
