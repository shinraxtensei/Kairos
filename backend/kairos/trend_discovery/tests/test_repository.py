"""Repository tests against real Postgres.

JSONB round-tripping and ON CONFLICT DO NOTHING are dialect behaviour — SQLite
would pass while Postgres failed, so these run against the real thing or skip.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from kairos.db import Base, SessionLocal, engine
from kairos.trend_discovery.domain.trend_signal import TrendSignal
from kairos.trend_discovery.domain.value_objects import (
    CompetitionLevel,
    Keyword,
    SearchVolume,
    SourcePlatform,
    VolumeScale,
)
from kairos.trend_discovery.infrastructure.models import TrendSignalRecord
from kairos.trend_discovery.infrastructure.repository import SqlAlchemyTrendSignalRepository


@pytest.fixture(scope="module", autouse=True)
def _require_database() -> None:
    try:
        with engine.connect():
            pass
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"postgres unavailable: {type(exc).__name__}")
    Base.metadata.create_all(engine)


@pytest.fixture
def session() -> Iterator[Session]:
    with SessionLocal() as session:
        session.query(TrendSignalRecord).delete()
        session.commit()
        yield session


def _signal(keyword: str = "cat sticker", **overrides: object) -> TrendSignal:
    defaults: dict[str, object] = {
        "platform": SourcePlatform.GOOGLE_TRENDS,
        "keyword": Keyword(keyword),
        "search_volume": SearchVolume.relative_index(73),
    }
    return TrendSignal.collect(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_given_a_signal_when_saved_then_it_round_trips(session: Session) -> None:
    repository = SqlAlchemyTrendSignalRepository(session)
    original = _signal(
        competition=CompetitionLevel.from_competing_listings(5_000),
        raw_payload={"series": [1, 2, 3], "geo": ""},
    )

    repository.add_all([original])
    (loaded,) = repository.recent()

    assert loaded.signal_id == original.signal_id
    assert loaded.keyword == original.keyword
    assert loaded.search_volume.scale is VolumeScale.RELATIVE_INDEX
    assert loaded.search_volume.value == 73
    assert loaded.competition is not None
    assert loaded.competition.score == original.competition.score  # type: ignore[union-attr]
    assert loaded.raw_payload["series"] == [1, 2, 3]
    assert loaded.collected_at.tzinfo is not None


def test_given_the_same_signal_twice_when_saved_then_it_is_not_duplicated(
    session: Session,
) -> None:
    """task_acks_late means Celery redelivery is normal, not exceptional."""
    repository = SqlAlchemyTrendSignalRepository(session)
    signal = _signal()

    repository.add_all([signal])
    repository.add_all([signal])

    assert len(repository.recent()) == 1


def test_given_signals_from_two_platforms_when_filtered_then_only_one_returns(
    session: Session,
) -> None:
    repository = SqlAlchemyTrendSignalRepository(session)
    repository.add_all(
        [
            _signal("cat sticker", platform=SourcePlatform.GOOGLE_TRENDS),
            _signal("cat sticker", platform=SourcePlatform.ETSY),
        ]
    )

    etsy = repository.recent(platform=SourcePlatform.ETSY)

    assert len(etsy) == 1
    assert etsy[0].platform is SourcePlatform.ETSY


def test_given_several_signals_when_listed_then_newest_first(session: Session) -> None:
    repository = SqlAlchemyTrendSignalRepository(session)
    now = datetime.now(UTC)
    repository.add_all(
        [
            _signal("older", collected_at=now - timedelta(days=2)),
            _signal("newer", collected_at=now - timedelta(hours=1)),
        ]
    )

    assert [s.keyword.text for s in repository.recent()] == ["newer", "older"]


def test_given_no_signals_when_saved_then_does_not_error(session: Session) -> None:
    SqlAlchemyTrendSignalRepository(session).add_all([])
