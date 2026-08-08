"""Application-layer tests — real ports, hand-written fakes, no I/O."""

from __future__ import annotations

from collections.abc import Sequence

from kairos.niche_ranking.application.rank_niches import RankNiches
from kairos.niche_ranking.domain.niche import Niche
from kairos.niche_ranking.domain.ports import NicheRepository, TrendSignalReader
from kairos.niche_ranking.domain.value_objects import (
    NicheSignals,
    NicheStatus,
    RankingCriteria,
)


class FakeReader(TrendSignalReader):
    def __init__(self, signals: dict[str, NicheSignals] | None = None) -> None:
        self._signals = signals or {}

    def signals_by_keyword(self) -> dict[str, NicheSignals]:
        return self._signals


class InMemoryNicheRepository(NicheRepository):
    def __init__(self) -> None:
        self.saved: dict[str, Niche] = {}

    def save_all(self, niches: Sequence[Niche]) -> None:
        for niche in niches:
            self.saved[niche.keyword] = niche

    def leaderboard(self, *, limit: int = 50) -> Sequence[Niche]:
        ranked = sorted(
            self.saved.values(), key=lambda n: n.score.value if n.score else 0, reverse=True
        )
        return ranked[:limit]


def test_given_signals_when_ranked_then_every_keyword_is_scored_and_saved() -> None:
    reader = FakeReader(
        {
            "moon phase print": NicheSignals(
                momentum_index=90, demand_volume=8_000, competition=10
            ),
            "saturated thing": NicheSignals(momentum_index=5, demand_volume=50, competition=99),
        }
    )
    repository = InMemoryNicheRepository()

    result = RankNiches(reader, repository)()

    assert len(result.scored) == 2
    assert len(repository.saved) == 2
    assert repository.saved["moon phase print"].status is NicheStatus.SHORTLISTED
    assert repository.saved["saturated thing"].status is NicheStatus.REJECTED


def test_given_no_signals_when_ranked_then_returns_empty_without_saving() -> None:
    repository = InMemoryNicheRepository()
    result = RankNiches(FakeReader(), repository)()
    assert result.scored == []
    assert repository.saved == {}


def test_given_the_same_keyword_ranked_twice_then_the_niche_id_is_stable() -> None:
    """Re-ranking must update the niche, not create a rival row for it."""
    reader = FakeReader({"cat sticker": NicheSignals(momentum_index=80)})
    first = InMemoryNicheRepository()
    second = InMemoryNicheRepository()

    RankNiches(reader, first)()
    RankNiches(reader, second)()

    assert first.saved["cat sticker"].niche_id == second.saved["cat sticker"].niche_id


def test_given_single_source_signals_when_ranked_then_corroboration_is_counted() -> None:
    """The state everything is in until the Etsy adapter lands."""
    reader = FakeReader(
        {"a": NicheSignals(momentum_index=95), "b": NicheSignals(momentum_index=90)}
    )
    result = RankNiches(reader, InMemoryNicheRepository())()

    assert len(result.shortlisted) == 2
    assert result.needs_corroboration == 2


def test_given_fully_corroborated_signals_when_ranked_then_nothing_is_flagged() -> None:
    reader = FakeReader({"a": NicheSignals(momentum_index=95, demand_volume=9_000, competition=5)})
    result = RankNiches(reader, InMemoryNicheRepository())()

    assert len(result.shortlisted) == 1
    assert result.needs_corroboration == 0


def test_given_a_stricter_threshold_when_ranked_then_fewer_shortlisted() -> None:
    reader = FakeReader({"borderline": NicheSignals(momentum_index=65)})

    lenient = RankNiches(reader, InMemoryNicheRepository(), RankingCriteria(shortlist_at=60))()
    strict = RankNiches(reader, InMemoryNicheRepository(), RankingCriteria(shortlist_at=90))()

    assert len(lenient.shortlisted) == 1
    assert len(strict.rejected) == 1
