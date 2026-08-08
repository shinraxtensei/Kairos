#!/usr/bin/env python
"""Seed demo data so the UI can be exercised before the generator adapter exists.

    uv run python scripts/seed_demo.py

Wipes the assets, niches and review tables first, so it is repeatable. Local
development only — it fabricates assets that no image model produced.
"""

from __future__ import annotations

from decimal import Decimal

from kairos.content_generation.domain.generated_asset import GeneratedAsset
from kairos.content_generation.domain.value_objects import (
    AssetFormat,
    AssetVariant,
    DeliveryFile,
    DeliveryPackage,
    PrintSpecification,
    ProcessingStage,
)
from kairos.content_generation.infrastructure.models import GeneratedAssetRecord
from kairos.content_generation.infrastructure.repository import (
    SqlAlchemyGeneratedAssetRepository,
)
from kairos.curation.infrastructure.models import ReviewDecisionRecord
from kairos.db import SessionLocal
from kairos.niche_ranking.infrastructure.models import NicheRecord
from kairos.niche_ranking.infrastructure.tasks import rank_niches
from kairos.shared_kernel.money import Money
from kairos.trend_discovery.domain.trend_signal import TrendSignal
from kairos.trend_discovery.domain.value_objects import (
    CompetitionLevel,
    Keyword,
    SearchVolume,
    SourcePlatform,
)
from kairos.trend_discovery.infrastructure.models import TrendSignalRecord
from kairos.trend_discovery.infrastructure.repository import SqlAlchemyTrendSignalRepository

NICHES = ["moon phase print", "boho wall art", "cat sticker", "digital planner"]


def main() -> None:
    with SessionLocal() as session:
        for model in (ReviewDecisionRecord, GeneratedAssetRecord, NicheRecord, TrendSignalRecord):
            session.query(model).delete()
        session.commit()

        signals = SqlAlchemyTrendSignalRepository(session)
        rows = []
        for i, keyword in enumerate(NICHES):
            rows.append(
                TrendSignal.collect(
                    platform=SourcePlatform.GOOGLE_TRENDS,
                    keyword=Keyword(keyword),
                    search_volume=SearchVolume.relative_index(90 - i * 18),
                )
            )
            # Two sources for one keyword, so the leaderboard shows the
            # difference between a corroborated niche and a momentum-only one.
            if i == 0:
                rows.append(
                    TrendSignal.collect(
                        platform=SourcePlatform.ETSY,
                        keyword=Keyword(keyword),
                        search_volume=SearchVolume.absolute(7_800),
                        competition=CompetitionLevel.from_competing_listings(600),
                    )
                )
        signals.add_all(rows)
        print(f"seeded {len(rows)} trend signals")

        assets = SqlAlchemyGeneratedAssetRepository(session)
        for i, keyword in enumerate(NICHES):
            asset = GeneratedAsset.generated(
                niche_keyword=keyword,
                variant=AssetVariant(index=i, seed=1000 + i),
                cost=Money(Decimal("0.04"), "USD"),
            )
            asset.advance_to(ProcessingStage.BACKGROUND_REMOVED)
            asset.advance_to(ProcessingStage.UPSCALED)
            asset.package(
                DeliveryPackage(
                    (
                        DeliveryFile(
                            f"{keyword.replace(' ', '-')}-18x24.jpg",
                            7_340_032,
                            AssetFormat.JPEG,
                        ),
                    )
                ),
                PrintSpecification(18, 24),
            )
            assets.save(asset)
        print(f"seeded {len(NICHES)} assets awaiting review")

    print("ranked:", rank_niches())
    print("\nNow open:  http://localhost:8000/review  and  http://localhost:8000/niches")


if __name__ == "__main__":
    main()
