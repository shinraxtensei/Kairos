"""Domain tests for Niche Ranking. Pure, no mocks, no I/O."""

import pytest

from kairos.niche_ranking.domain.niche import Niche
from kairos.niche_ranking.domain.scoring import score_niche
from kairos.niche_ranking.domain.value_objects import (
    Confidence,
    NicheSignals,
    NicheStatus,
    RankingCriteria,
)


class TestNicheSignals:
    def test_given_no_signals_at_all_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="no signals at all"):
            NicheSignals()

    @pytest.mark.parametrize("momentum", [-1, 101])
    def test_given_an_out_of_range_momentum_when_built_then_raises(self, momentum: int) -> None:
        with pytest.raises(ValueError, match="momentum_index"):
            NicheSignals(momentum_index=momentum)

    def test_given_negative_demand_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="demand_volume"):
            NicheSignals(demand_volume=-5)

    def test_given_only_momentum_when_asked_then_confidence_is_low(self) -> None:
        assert NicheSignals(momentum_index=80).confidence is Confidence.LOW

    def test_given_two_signals_when_asked_then_confidence_is_medium(self) -> None:
        assert NicheSignals(momentum_index=80, demand_volume=5000).confidence is Confidence.MEDIUM

    def test_given_all_three_signals_when_asked_then_confidence_is_high(self) -> None:
        signals = NicheSignals(momentum_index=80, demand_volume=5000, competition=30)
        assert signals.confidence is Confidence.HIGH


class TestRankingCriteria:
    def test_given_weights_that_do_not_sum_to_one_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match=r"sum to 1\.0"):
            RankingCriteria(demand_weight=0.5, momentum_weight=0.5, competition_weight=0.5)

    def test_given_a_negative_weight_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            RankingCriteria(demand_weight=-0.1, momentum_weight=0.6, competition_weight=0.5)

    def test_given_a_zero_demand_reference_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="demand_reference"):
            RankingCriteria(demand_reference=0)


class TestScoring:
    def test_given_a_perfect_niche_when_scored_then_near_maximum(self) -> None:
        signals = NicheSignals(momentum_index=100, demand_volume=10_000, competition=0)
        score, _ = score_niche(signals)
        assert score.value == 100

    def test_given_a_hopeless_niche_when_scored_then_near_zero(self) -> None:
        signals = NicheSignals(momentum_index=0, demand_volume=0, competition=100)
        score, _ = score_niche(signals)
        assert score.value == 0

    def test_given_high_competition_when_scored_then_penalised(self) -> None:
        base = NicheSignals(momentum_index=70, demand_volume=5_000, competition=10)
        crowded = NicheSignals(momentum_index=70, demand_volume=5_000, competition=90)
        assert score_niche(base)[0].value > score_niche(crowded)[0].value

    def test_given_demand_beyond_the_reference_when_scored_then_saturates(self) -> None:
        # A million results is not a hundred times better than ten thousand.
        modest = NicheSignals(demand_volume=10_000, momentum_index=50, competition=50)
        huge = NicheSignals(demand_volume=1_000_000, momentum_index=50, competition=50)
        assert score_niche(modest)[0].value == score_niche(huge)[0].value

    def test_given_only_momentum_when_scored_then_weights_renormalise(self) -> None:
        """A silent source must not act as a zero.

        Momentum 80 alone should score 80, not 80 x 0.3 = 24 — otherwise every
        niche looks terrible whenever a source is down.
        """
        score, breakdown = score_niche(NicheSignals(momentum_index=80))
        assert score.value == 80
        assert breakdown.applied_weights == {"momentum": 1.0}
        assert score.confidence is Confidence.LOW

    def test_given_a_score_when_computed_then_breakdown_records_the_reasoning(self) -> None:
        signals = NicheSignals(momentum_index=70, demand_volume=5_000, competition=20)
        _, breakdown = score_niche(signals)
        assert breakdown.momentum_component == 70
        assert breakdown.demand_component == 50  # 5,000 of a 10,000 reference
        assert breakdown.competition_penalty == 20
        assert pytest.approx(sum(breakdown.applied_weights.values())) == 1.0

    def test_given_criteria_weighting_the_only_signal_at_zero_when_scored_then_raises(self) -> None:
        criteria = RankingCriteria(demand_weight=0.5, momentum_weight=0.0, competition_weight=0.5)
        with pytest.raises(ValueError, match="zero weight"):
            score_niche(NicheSignals(momentum_index=80), criteria)


class TestNiche:
    def test_given_a_strong_niche_when_ranked_then_shortlisted(self) -> None:
        niche = Niche.candidate("moon phase print")
        niche.rank(NicheSignals(momentum_index=90, demand_volume=8_000, competition=10))
        assert niche.status is NicheStatus.SHORTLISTED
        assert [type(e).__name__ for e in niche.pull_events()] == [
            "NicheScored",
            "NicheShortlisted",
        ]

    def test_given_a_weak_niche_when_ranked_then_rejected_with_a_reason(self) -> None:
        niche = Niche.candidate("saturated thing")
        niche.rank(NicheSignals(momentum_index=5, demand_volume=100, competition=95))
        assert niche.status is NicheStatus.REJECTED
        rejected = niche.pull_events()[-1]
        assert "below threshold" in getattr(rejected, "reason", "")

    def test_given_a_score_exactly_at_the_threshold_when_ranked_then_shortlisted(self) -> None:
        # The boundary is inclusive; asserted so a later refactor cannot flip it.
        niche = Niche.candidate("edge")
        niche.rank(NicheSignals(momentum_index=60), RankingCriteria(shortlist_at=60))
        assert niche.status is NicheStatus.SHORTLISTED

    def test_given_a_single_source_shortlist_when_checked_then_needs_corroboration(self) -> None:
        """Until ENG-18 lands, every niche is in exactly this state."""
        niche = Niche.candidate("cat sticker")
        niche.rank(NicheSignals(momentum_index=95))
        assert niche.status is NicheStatus.SHORTLISTED
        assert niche.needs_corroboration

    def test_given_a_fully_corroborated_shortlist_when_checked_then_no_flag(self) -> None:
        niche = Niche.candidate("cat sticker")
        niche.rank(NicheSignals(momentum_index=95, demand_volume=9_000, competition=5))
        assert not niche.needs_corroboration

    def test_given_events_pulled_when_pulled_again_then_empty(self) -> None:
        niche = Niche.candidate("thing")
        niche.rank(NicheSignals(momentum_index=90))
        niche.pull_events()
        assert niche.pull_events() == []

    def test_given_a_blank_keyword_when_created_then_raises(self) -> None:
        with pytest.raises(ValueError, match="needs a keyword"):
            Niche.candidate("   ")
