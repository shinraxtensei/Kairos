"""Ports for Niche Ranking."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from kairos.niche_ranking.domain.niche import Niche
from kairos.niche_ranking.domain.value_objects import NicheSignals


class TrendSignalReader(ABC):
    """Supplies the signals to rank.

    Declared here, in Niche Ranking's own terms, so this context never learns
    Trend Discovery's model. The adapter that calls the other context lives in
    infrastructure/ and is the single permitted cross-context edge.
    """

    @abstractmethod
    def signals_by_keyword(self) -> dict[str, NicheSignals]: ...


class NicheRepository(ABC):
    @abstractmethod
    def save_all(self, niches: Sequence[Niche]) -> None: ...

    @abstractmethod
    def leaderboard(self, *, limit: int = 50) -> Sequence[Niche]: ...
