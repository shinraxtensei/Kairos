"""End-to-end M2 pipeline test, against real Postgres.

Lives in the shared tests/ root rather than inside either context, because it
drives both: signals collected by Trend Discovery become ranked niches in Niche
Ranking. Putting it in one context's tests/ would make that context import the
other and break the independence contract — which is exactly what happened on
the first attempt.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from kairos.db import Base, SessionLocal, engine
from kairos.niche_ranking.application.rank_niches import RankNiches
from kairos.niche_ranking.domain.value_objects import Confidence, NicheStatus
from kairos.niche_ranking.infrastructure.models import NicheRecord
from kairos.niche_ranking.infrastructure.repository import SqlAlchemyNicheRepository
from kairos.niche_ranking.infrastructure.trend_signal_reader import TrendDiscoverySignalReader
from kairos.trend_discovery.domain.trend_signal import TrendSignal
from kairos.trend_discovery.domain.value_objects import (
    CompetitionLevel,
    Keyword,
    SearchVolume,
    SourcePlatform,
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
        session.query(NicheRecord).delete()
        session.query(TrendSignalRecord).delete()
        session.commit()
        yield session


def test_given_google_only_signals_when_ranked_then_niches_are_low_confidence(
    session: Session,
) -> None:
    """The live pipeline's current shape: momentum, and nothing else."""
    SqlAlchemyTrendSignalRepository(session).add_all(
        [
            TrendSignal.collect(
                platform=SourcePlatform.GOOGLE_TRENDS,
                keyword=Keyword("cat sticker"),
                search_volume=SearchVolume.relative_index(88),
            )
        ]
    )

    result = RankNiches(TrendDiscoverySignalReader(session), SqlAlchemyNicheRepository(session))()

    assert len(result.scored) == 1
    assert result.needs_corroboration == 1
    (niche,) = SqlAlchemyNicheRepository(session).leaderboard()
    assert niche.keyword == "cat sticker"
    assert niche.score is not None
    assert niche.score.confidence is Confidence.LOW


def test_given_two_sources_for_one_keyword_when_ranked_then_confidence_rises(
    session: Session,
) -> None:
    """What ENG-18 will change: Etsy supplies demand and competition."""
    keyword = Keyword("moon phase print")
    SqlAlchemyTrendSignalRepository(session).add_all(
        [
            TrendSignal.collect(
                platform=SourcePlatform.GOOGLE_TRENDS,
                keyword=keyword,
                search_volume=SearchVolume.relative_index(90),
            ),
            TrendSignal.collect(
                platform=SourcePlatform.ETSY,
                keyword=keyword,
                search_volume=SearchVolume.absolute(7_500),
                competition=CompetitionLevel.from_competing_listings(400),
            ),
        ]
    )

    result = RankNiches(TrendDiscoverySignalReader(session), SqlAlchemyNicheRepository(session))()

    (niche,) = SqlAlchemyNicheRepository(session).leaderboard()
    assert niche.score is not None
    assert niche.score.confidence is Confidence.HIGH
    assert result.needs_corroboration == 0
    assert niche.status is NicheStatus.SHORTLISTED


def test_given_a_niche_ranked_twice_when_saved_then_it_is_updated_not_duplicated(
    session: Session,
) -> None:
    repository = SqlAlchemyNicheRepository(session)
    signals = SqlAlchemyTrendSignalRepository(session)
    reader = TrendDiscoverySignalReader(session)

    signals.add_all(
        [
            TrendSignal.collect(
                platform=SourcePlatform.GOOGLE_TRENDS,
                keyword=Keyword("cat sticker"),
                search_volume=SearchVolume.relative_index(30),
            )
        ]
    )
    RankNiches(reader, repository)()
    first_score = repository.leaderboard()[0].score

    session.query(TrendSignalRecord).delete()
    session.commit()
    signals.add_all(
        [
            TrendSignal.collect(
                platform=SourcePlatform.GOOGLE_TRENDS,
                keyword=Keyword("cat sticker"),
                search_volume=SearchVolume.relative_index(95),
            )
        ]
    )
    RankNiches(reader, repository)()

    board = repository.leaderboard()
    assert len(board) == 1
    assert first_score is not None and board[0].score is not None
    assert board[0].score.value > first_score.value


def test_given_ranked_niches_when_listed_then_ordered_by_score_descending(
    session: Session,
) -> None:
    signals = SqlAlchemyTrendSignalRepository(session)
    signals.add_all(
        [
            TrendSignal.collect(
                platform=SourcePlatform.GOOGLE_TRENDS,
                keyword=Keyword(text),
                search_volume=SearchVolume.relative_index(value),
            )
            for text, value in [("low", 10), ("high", 95), ("mid", 55)]
        ]
    )

    RankNiches(TrendDiscoverySignalReader(session), SqlAlchemyNicheRepository(session))()

    board = SqlAlchemyNicheRepository(session).leaderboard()
    assert [niche.keyword for niche in board] == ["high", "mid", "low"]


def test_given_a_saved_niche_when_reloaded_then_the_breakdown_survives(
    session: Session,
) -> None:
    """The score's reasoning must round-trip, or the formula cannot be retuned."""
    SqlAlchemyTrendSignalRepository(session).add_all(
        [
            TrendSignal.collect(
                platform=SourcePlatform.ETSY,
                keyword=Keyword("cat sticker"),
                search_volume=SearchVolume.absolute(5_000),
                competition=CompetitionLevel.from_competing_listings(20_000),
            )
        ]
    )
    RankNiches(TrendDiscoverySignalReader(session), SqlAlchemyNicheRepository(session))()

    (niche,) = SqlAlchemyNicheRepository(session).leaderboard()
    assert niche.breakdown is not None
    assert niche.breakdown.demand_component == 50  # 5,000 of a 10,000 reference
    assert niche.breakdown.competition_penalty == 75
    assert pytest.approx(sum(niche.breakdown.applied_weights.values())) == 1.0


def test_given_one_keyword_with_long_history_when_read_then_others_are_not_starved(
    session: Session,
) -> None:
    """A busy keyword must not crowd others out of the ranking input.

    The first implementation read a flat window of recent signals and collapsed
    it in memory. At a daily cadence one keyword's history fills that window on
    its own, and every other niche silently stops being ranked as history grows.
    """
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    SqlAlchemyTrendSignalRepository(session).add_all(
        [
            TrendSignal.collect(
                platform=SourcePlatform.GOOGLE_TRENDS,
                keyword=Keyword("noisy"),
                search_volume=SearchVolume.relative_index(50),
                collected_at=now - timedelta(days=day),
            )
            for day in range(60)
        ]
        + [
            TrendSignal.collect(
                platform=SourcePlatform.GOOGLE_TRENDS,
                keyword=Keyword("quiet"),
                search_volume=SearchVolume.relative_index(99),
                collected_at=now - timedelta(days=90),
            )
        ]
    )

    signals = TrendDiscoverySignalReader(session).signals_by_keyword()

    assert set(signals) == {"noisy", "quiet"}
    # And the newest value per keyword wins, not an arbitrary one.
    assert signals["noisy"].momentum_index == 50
    assert signals["quiet"].momentum_index == 99
