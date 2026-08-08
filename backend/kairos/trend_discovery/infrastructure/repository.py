"""SQLAlchemy implementation of TrendSignalRepository."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from kairos.trend_discovery.domain.ports import TrendSignalRepository
from kairos.trend_discovery.domain.trend_signal import TrendSignal
from kairos.trend_discovery.domain.value_objects import (
    CompetitionLevel,
    Keyword,
    SearchVolume,
    SourcePlatform,
    VolumeScale,
)
from kairos.trend_discovery.infrastructure.models import TrendSignalRecord


def _to_domain(record: TrendSignalRecord) -> TrendSignal:
    return TrendSignal(
        signal_id=record.signal_id,
        platform=SourcePlatform(record.platform),
        keyword=Keyword(record.keyword),
        search_volume=SearchVolume(record.search_volume, VolumeScale[record.volume_scale]),
        collected_at=record.collected_at,
        competition=(
            CompetitionLevel(record.competition_score)
            if record.competition_score is not None
            else None
        ),
        raw_payload=record.raw_payload or {},
    )


class SqlAlchemyTrendSignalRepository(TrendSignalRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_all(self, signals: Sequence[TrendSignal]) -> None:
        if not signals:
            return
        rows = [
            {
                "signal_id": signal.signal_id,
                "platform": signal.platform.value,
                "keyword": signal.keyword.text,
                "search_volume": signal.search_volume.value,
                "volume_scale": signal.search_volume.scale.name,
                "competition_score": (
                    signal.competition.score if signal.competition is not None else None
                ),
                "collected_at": signal.collected_at,
                "raw_payload": dict(signal.raw_payload),
            }
            for signal in signals
        ]
        # A retried Celery task re-fetches the same window and produces the same
        # ids; collecting twice must not raise or duplicate.
        statement = (
            insert(TrendSignalRecord)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["signal_id"])
        )
        self._session.execute(statement)
        self._session.commit()

    def recent(
        self, *, platform: SourcePlatform | None = None, limit: int = 100
    ) -> Sequence[TrendSignal]:
        query = select(TrendSignalRecord).order_by(TrendSignalRecord.collected_at.desc())
        if platform is not None:
            query = query.where(TrendSignalRecord.platform == platform.value)
        return [_to_domain(row) for row in self._session.scalars(query.limit(limit))]

    def latest_per_keyword_and_platform(self) -> Sequence[TrendSignal]:
        # DISTINCT ON is Postgres-specific and exactly the right tool: one row
        # per group, chosen by the ORDER BY, without a window function or a
        # self-join. The leading ORDER BY columns must match the DISTINCT ON.
        query = (
            select(TrendSignalRecord)
            .distinct(TrendSignalRecord.keyword, TrendSignalRecord.platform)
            .order_by(
                TrendSignalRecord.keyword,
                TrendSignalRecord.platform,
                TrendSignalRecord.collected_at.desc(),
            )
        )
        return [_to_domain(row) for row in self._session.scalars(query)]
