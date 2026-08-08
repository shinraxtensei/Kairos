"""The Niche aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from kairos.niche_ranking.domain.events import NicheRejected, NicheScored, NicheShortlisted
from kairos.niche_ranking.domain.scoring import ScoreBreakdown, score_niche
from kairos.niche_ranking.domain.value_objects import (
    Confidence,
    NicheSignals,
    NicheStatus,
    ProfitabilityScore,
    RankingCriteria,
)

NicheEvent = NicheScored | NicheShortlisted | NicheRejected


@dataclass(eq=False, slots=True)
class Niche:
    niche_id: UUID
    keyword: str
    status: NicheStatus = NicheStatus.CANDIDATE
    score: ProfitabilityScore | None = None
    breakdown: ScoreBreakdown | None = None
    scored_at: datetime | None = None
    events: list[NicheEvent] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.keyword.strip():
            raise ValueError("a niche needs a keyword")

    @classmethod
    def candidate(cls, keyword: str, niche_id: UUID | None = None) -> Niche:
        return cls(niche_id=niche_id or uuid4(), keyword=keyword.strip().lower())

    def rank(self, signals: NicheSignals, criteria: RankingCriteria | None = None) -> None:
        """Score, then shortlist or reject against the criteria's threshold."""
        criteria = criteria or RankingCriteria()
        self.score, self.breakdown = score_niche(signals, criteria)
        self.scored_at = datetime.now(UTC)
        self.events.append(
            NicheScored(
                niche_id=self.niche_id,
                keyword=self.keyword,
                score=self.score.value,
                confidence=self.score.confidence,
            )
        )

        if self.score.value >= criteria.shortlist_at:
            self.status = NicheStatus.SHORTLISTED
            self.events.append(
                NicheShortlisted(
                    niche_id=self.niche_id, keyword=self.keyword, score=self.score.value
                )
            )
        else:
            self.status = NicheStatus.REJECTED
            self.events.append(
                NicheRejected(
                    niche_id=self.niche_id,
                    keyword=self.keyword,
                    score=self.score.value,
                    reason=f"scored {self.score.value}, below threshold {criteria.shortlist_at}",
                )
            )

    @property
    def needs_corroboration(self) -> bool:
        """Shortlisted on a thin signal set.

        Not a rejection — a flag. Committing design spend to a niche ranked from
        one source is how the budget gets burned on a guess (RSK-04). Until the
        Etsy adapter lands (ENG-18) every niche is in this state.
        """
        return self.status is NicheStatus.SHORTLISTED and (
            self.score is not None and self.score.confidence is Confidence.LOW
        )

    def pull_events(self) -> list[NicheEvent]:
        drained, self.events = self.events, []
        return drained

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Niche) and self.niche_id == other.niche_id

    def __hash__(self) -> int:
        return hash(self.niche_id)
