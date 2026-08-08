"""RankNiche — the command from CONTEXT.md §4.2.

Policy: whenever `TrendSignalCollected` → trigger `RankNiche`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import NAMESPACE_URL, uuid5

from kairos.niche_ranking.domain.events import NicheRejected, NicheScored, NicheShortlisted
from kairos.niche_ranking.domain.niche import Niche, NicheEvent
from kairos.niche_ranking.domain.ports import NicheRepository, TrendSignalReader
from kairos.niche_ranking.domain.value_objects import RankingCriteria

logger = logging.getLogger(__name__)

# One keyword is one niche, so re-ranking updates the same row instead of
# accumulating a fresh niche every run.
NICHE_NAMESPACE = uuid5(NAMESPACE_URL, "https://kairos.local/niche")


@dataclass(frozen=True, slots=True)
class RankResult:
    scored: list[NicheScored] = field(default_factory=list)
    shortlisted: list[NicheShortlisted] = field(default_factory=list)
    rejected: list[NicheRejected] = field(default_factory=list)
    needs_corroboration: int = 0


class RankNiches:
    def __init__(
        self,
        reader: TrendSignalReader,
        repository: NicheRepository,
        criteria: RankingCriteria | None = None,
    ) -> None:
        self._reader = reader
        self._repository = repository
        self._criteria = criteria or RankingCriteria()

    def __call__(self) -> RankResult:
        signals_by_keyword = self._reader.signals_by_keyword()
        if not signals_by_keyword:
            logger.info("no trend signals to rank")
            return RankResult()

        niches: list[Niche] = []
        events: list[NicheEvent] = []
        thin = 0

        for keyword, signals in sorted(signals_by_keyword.items()):
            niche = Niche.candidate(keyword, niche_id=uuid5(NICHE_NAMESPACE, keyword))
            niche.rank(signals, self._criteria)
            if niche.needs_corroboration:
                thin += 1
            niches.append(niche)
            events.extend(niche.pull_events())

        self._repository.save_all(niches)

        if thin:
            # Not a warning about the code — a warning about the data. Acting on
            # a single-source shortlist is how the budget burns on a guess.
            logger.warning("%d of %d shortlisted niches rest on one source only", thin, len(niches))

        return RankResult(
            scored=[e for e in events if isinstance(e, NicheScored)],
            shortlisted=[e for e in events if isinstance(e, NicheShortlisted)],
            rejected=[e for e in events if isinstance(e, NicheRejected)],
            needs_corroboration=thin,
        )
