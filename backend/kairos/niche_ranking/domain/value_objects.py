"""Value objects for Niche Ranking.

This context never imports Trend Discovery (CONTEXT.md §3.1). Signals arrive as
`NicheSignals`, built by the application layer from whatever sources reported,
so the scoring rules here depend on no other context's model.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MAX_SCORE = 100


class NicheStatus(StrEnum):
    CANDIDATE = "candidate"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"


class Confidence(StrEnum):
    """How much of the picture the score was built from.

    A niche scored from momentum alone is not the same claim as one scored from
    momentum plus demand plus competition, even when the numbers match. Without
    this, a single-source run produces a leaderboard that looks authoritative
    and is mostly guesswork — which is exactly the state the project is in until
    the Etsy adapter lands (ENG-18).
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class NicheSignals:
    """What the sources reported for one keyword. Any of them may be missing.

    - `momentum_index`: 0-100, current interest against the keyword's own recent
      peak. Google Trends. Says "is this rising", not "is this big".
    - `demand_volume`: absolute result/search count. Etsy. Says "is this big".
    - `competition`: 0-100, higher is more crowded.
    """

    momentum_index: int | None = None
    demand_volume: int | None = None
    competition: int | None = None

    def __post_init__(self) -> None:
        if self.momentum_index is not None and not 0 <= self.momentum_index <= MAX_SCORE:
            raise ValueError("momentum_index must be between 0 and 100")
        if self.competition is not None and not 0 <= self.competition <= MAX_SCORE:
            raise ValueError("competition must be between 0 and 100")
        if self.demand_volume is not None and self.demand_volume < 0:
            raise ValueError("demand_volume cannot be negative")
        if self.is_empty:
            raise ValueError("a niche cannot be scored with no signals at all")

    @property
    def is_empty(self) -> bool:
        return all(
            value is None for value in (self.momentum_index, self.demand_volume, self.competition)
        )

    @property
    def confidence(self) -> Confidence:
        present = sum(
            value is not None
            for value in (self.momentum_index, self.demand_volume, self.competition)
        )
        if present >= 3:
            return Confidence.HIGH
        if present == 2:
            return Confidence.MEDIUM
        return Confidence.LOW


@dataclass(frozen=True, slots=True)
class RankingCriteria:
    """The weighted formula's inputs. Explainable on purpose — no ML until this
    has been tried and demonstrably failed (CONTEXT.md §4.2).

    `demand_reference` is the absolute count that maps to a full demand score.
    It is a scaling constant, not a threshold: doubling it halves every demand
    contribution. Set it from real Etsy result counts once ENG-18 lands.
    """

    demand_weight: float = 0.4
    momentum_weight: float = 0.3
    competition_weight: float = 0.3
    demand_reference: int = 10_000
    shortlist_at: int = 60

    def __post_init__(self) -> None:
        weights = (self.demand_weight, self.momentum_weight, self.competition_weight)
        if any(weight < 0 for weight in weights):
            raise ValueError("weights cannot be negative")
        total = sum(weights)
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"weights must sum to 1.0, got {total}")
        if self.demand_reference <= 0:
            raise ValueError("demand_reference must be positive")
        if not 0 <= self.shortlist_at <= MAX_SCORE:
            raise ValueError("shortlist_at must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class ProfitabilityScore:
    value: int
    confidence: Confidence

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise TypeError("score must be an int")
        if not 0 <= self.value <= MAX_SCORE:
            raise ValueError("score must be between 0 and 100")
