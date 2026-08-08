"""The scoring formula. Kept separate so it can be read, argued with, and retuned."""

from __future__ import annotations

from dataclasses import dataclass

from kairos.niche_ranking.domain.value_objects import (
    MAX_SCORE,
    NicheSignals,
    ProfitabilityScore,
    RankingCriteria,
)


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """Why a niche scored what it did.

    Persisted alongside the score. A formula whose reasoning was not recorded
    cannot be tuned later — you would be left with a number and no way to tell
    whether demand or competition drove it.
    """

    demand_component: float | None
    momentum_component: float | None
    competition_penalty: float | None
    applied_weights: dict[str, float]

    def as_dict(self) -> dict[str, object]:
        return {
            "demand_component": self.demand_component,
            "momentum_component": self.momentum_component,
            "competition_penalty": self.competition_penalty,
            "applied_weights": self.applied_weights,
        }


def _demand_score(volume: int, reference: int) -> float:
    """Map an absolute count onto 0-100, saturating at the reference.

    Linear rather than logarithmic for now: it is easier to reason about, and
    there is no real Etsy data yet to justify a curve. Revisit once ENG-18 shows
    the actual spread of result counts — if they span orders of magnitude, a log
    scale will separate niches that linear scaling flattens together.
    """
    return min(volume / reference, 1.0) * MAX_SCORE


def score_niche(
    signals: NicheSignals, criteria: RankingCriteria | None = None
) -> tuple[ProfitabilityScore, ScoreBreakdown]:
    """Score a niche from whatever signals exist.

    Missing signals are dropped and the remaining weights renormalised, so a
    niche with only momentum is scored on momentum rather than being penalised
    for the sources that stayed silent. The resulting `Confidence` is what marks
    it as a thinner claim — not a lower score.
    """
    criteria = criteria or RankingCriteria()

    contributions: dict[str, tuple[float, float]] = {}

    if signals.demand_volume is not None:
        contributions["demand"] = (
            _demand_score(signals.demand_volume, criteria.demand_reference),
            criteria.demand_weight,
        )
    if signals.momentum_index is not None:
        contributions["momentum"] = (float(signals.momentum_index), criteria.momentum_weight)
    if signals.competition is not None:
        # Inverted: low competition is a good thing, so it contributes positively.
        contributions["competition"] = (
            float(MAX_SCORE - signals.competition),
            criteria.competition_weight,
        )

    total_weight = sum(weight for _, weight in contributions.values())
    if total_weight <= 0:
        # Every present signal carries zero weight — a misconfiguration, not a
        # zero-scoring niche. Say so rather than returning a confident 0.
        raise ValueError("criteria assign zero weight to every available signal")

    applied = {name: weight / total_weight for name, (_, weight) in contributions.items()}
    value = sum(component * applied[name] for name, (component, _) in contributions.items())

    breakdown = ScoreBreakdown(
        demand_component=contributions.get("demand", (None, 0))[0],
        momentum_component=contributions.get("momentum", (None, 0))[0],
        competition_penalty=(
            float(signals.competition) if signals.competition is not None else None
        ),
        applied_weights=applied,
    )
    return ProfitabilityScore(round(value), signals.confidence), breakdown
