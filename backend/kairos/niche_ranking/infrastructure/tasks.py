"""Ranking runs after collection. Policy: TrendSignalCollected -> RankNiche."""

from __future__ import annotations

from typing import Any

from kairos.celery_app import celery_app
from kairos.db import SessionLocal
from kairos.niche_ranking.application.rank_niches import RankNiches
from kairos.niche_ranking.infrastructure.repository import SqlAlchemyNicheRepository
from kairos.niche_ranking.infrastructure.trend_signal_reader import TrendDiscoverySignalReader
from kairos.observability import correlated


@celery_app.task(name="kairos.niche_ranking.rank")
def rank_niches() -> dict[str, Any]:
    with correlated("rank"), SessionLocal() as session:
        result = RankNiches(
            TrendDiscoverySignalReader(session), SqlAlchemyNicheRepository(session)
        )()

    return {
        "scored": len(result.scored),
        "shortlisted": len(result.shortlisted),
        "rejected": len(result.rejected),
        "needs_corroboration": result.needs_corroboration,
    }
