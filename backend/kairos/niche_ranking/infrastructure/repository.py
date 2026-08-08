"""SQLAlchemy implementation of NicheRepository."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from kairos.niche_ranking.domain.niche import Niche
from kairos.niche_ranking.domain.ports import NicheRepository
from kairos.niche_ranking.domain.scoring import ScoreBreakdown
from kairos.niche_ranking.domain.value_objects import (
    Confidence,
    NicheStatus,
    ProfitabilityScore,
)
from kairos.niche_ranking.infrastructure.models import NicheRecord


def _to_domain(record: NicheRecord) -> Niche:
    breakdown = record.breakdown or {}
    return Niche(
        niche_id=record.niche_id,
        keyword=record.keyword,
        status=NicheStatus(record.status),
        score=ProfitabilityScore(record.score, Confidence(record.confidence)),
        breakdown=ScoreBreakdown(
            demand_component=breakdown.get("demand_component"),
            momentum_component=breakdown.get("momentum_component"),
            competition_penalty=breakdown.get("competition_penalty"),
            applied_weights=breakdown.get("applied_weights", {}),
        ),
        scored_at=record.scored_at,
    )


class SqlAlchemyNicheRepository(NicheRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_all(self, niches: Sequence[Niche]) -> None:
        rows = [
            {
                "niche_id": niche.niche_id,
                "keyword": niche.keyword,
                "status": niche.status.value,
                "score": niche.score.value,
                "confidence": niche.score.confidence.value,
                "breakdown": niche.breakdown.as_dict() if niche.breakdown else {},
                "scored_at": niche.scored_at,
            }
            for niche in niches
            if niche.score is not None and niche.scored_at is not None
        ]
        if not rows:
            return

        # Re-ranking a keyword must update it, not insert a rival row — the
        # niche id is derived from the keyword precisely so this is possible.
        statement = insert(NicheRecord).values(rows)
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["niche_id"],
                set_={
                    "status": statement.excluded.status,
                    "score": statement.excluded.score,
                    "confidence": statement.excluded.confidence,
                    "breakdown": statement.excluded.breakdown,
                    "scored_at": statement.excluded.scored_at,
                },
            )
        )
        self._session.commit()

    def leaderboard(self, *, limit: int = 50) -> Sequence[Niche]:
        query = (
            select(NicheRecord).order_by(NicheRecord.score.desc(), NicheRecord.keyword).limit(limit)
        )
        return [_to_domain(row) for row in self._session.scalars(query)]
