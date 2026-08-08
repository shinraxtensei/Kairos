"""The one permitted cross-context edge.

Niche Ranking needs Trend Discovery's data. CONTEXT.md §3.1 allows exactly one
route for that, so this adapter calls `trend_discovery.public` — that context's
published facade — and maps its neutral DTO into Niche Ranking's own
`NicheSignals`.

It must never import Trend Discovery's domain models, its repository, or read
the `trend_signals` table. All three would couple the contexts through a shape
neither owns. The first draft of this file did reach for the repository and the
independence contract failed the build, which is the whole point of having it;
the contract now carries an exception for this module and this import only, so a
second edge breaks CI.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from kairos.niche_ranking.domain.ports import TrendSignalReader
from kairos.niche_ranking.domain.value_objects import NicheSignals
from kairos.trend_discovery import public as trend_discovery


class TrendDiscoverySignalReader(TrendSignalReader):
    def __init__(self, session: Session) -> None:
        self._session = session

    def signals_by_keyword(self) -> dict[str, NicheSignals]:
        results: dict[str, NicheSignals] = {}
        for summary in trend_discovery.latest_signals_per_keyword(self._session):
            if (
                summary.momentum_index is None
                and summary.demand_volume is None
                and summary.competition is None
            ):
                # NicheSignals refuses to be built empty; skip rather than raise.
                continue
            results[summary.keyword] = NicheSignals(
                momentum_index=summary.momentum_index,
                demand_volume=summary.demand_volume,
                competition=summary.competition,
            )
        return results
