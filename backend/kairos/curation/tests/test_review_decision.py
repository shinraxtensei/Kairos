"""Curation domain tests — the rules that protect the shop's existence."""

from uuid import uuid4

import pytest

from kairos.curation.domain.events import AssetApproved, AssetRejected
from kairos.curation.domain.review_decision import AlreadyReviewedError, ReviewDecision
from kairos.curation.domain.value_objects import IpCheck, IpScreening, RejectionReason


class TestIpScreening:
    def test_given_every_check_cleared_when_built_then_valid(self) -> None:
        screening = IpScreening.cleared_by("hamid")
        assert screening.cleared == frozenset(IpCheck)

    def test_given_a_missing_check_when_built_then_raises_naming_it(self) -> None:
        partial = frozenset(IpCheck) - {IpCheck.NO_TRADEMARKED_PHRASE}
        with pytest.raises(ValueError, match="no_trademarked_phrase"):
            IpScreening(partial, "hamid")

    def test_given_no_checks_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="incomplete"):
            IpScreening(frozenset(), "hamid")

    def test_given_no_reviewer_when_built_then_raises(self) -> None:
        # An unattributed screening is not an audit trail.
        with pytest.raises(ValueError, match="who performed it"):
            IpScreening(frozenset(IpCheck), "  ")

    def test_given_a_screening_when_inspected_then_it_is_immutable(self) -> None:
        screening = IpScreening.cleared_by("hamid")
        with pytest.raises(AttributeError):
            screening.checked_by = "someone else"  # type: ignore[misc]


class TestApproval:
    def test_given_a_complete_screening_when_approved_then_emits_asset_approved(self) -> None:
        review = ReviewDecision.open(uuid4(), "hamid")
        review.approve(IpScreening.cleared_by("hamid"))

        (event,) = review.pull_events()
        assert isinstance(event, AssetApproved)
        assert event.asset_id == review.asset_id
        assert event.screened_by == "hamid"

    def test_given_an_incomplete_screening_then_it_cannot_reach_approve(self) -> None:
        """The gate is the type, not a check inside approve().

        There is no way to hand `approve` a half-done screening, because a
        half-done `IpScreening` cannot be constructed at all.
        """
        with pytest.raises(ValueError, match="incomplete"):
            IpScreening(frozenset({IpCheck.NO_BRAND_NAME_OR_LOGO}), "hamid")

    def test_given_an_approved_review_when_approved_again_then_raises(self) -> None:
        review = ReviewDecision.open(uuid4(), "hamid")
        review.approve(IpScreening.cleared_by("hamid"))
        with pytest.raises(AlreadyReviewedError):
            review.approve(IpScreening.cleared_by("hamid"))

    def test_given_a_rejected_review_when_approved_then_raises(self) -> None:
        # Flipping a rejection to an approval would strand the AssetRejected
        # event already emitted downstream.
        review = ReviewDecision.open(uuid4(), "hamid")
        review.reject(RejectionReason.IP_RISK)
        with pytest.raises(AlreadyReviewedError):
            review.approve(IpScreening.cleared_by("hamid"))


class TestRejection:
    def test_given_a_reason_when_rejected_then_emits_asset_rejected(self) -> None:
        review = ReviewDecision.open(uuid4(), "hamid")
        review.reject(RejectionReason.IP_RISK, note="looks like a band logo")

        (event,) = review.pull_events()
        assert isinstance(event, AssetRejected)
        assert event.reason is RejectionReason.IP_RISK
        assert "band logo" in event.note

    def test_given_a_rejection_then_no_approval_event_is_emitted(self) -> None:
        review = ReviewDecision.open(uuid4(), "hamid")
        review.reject(RejectionReason.POOR_QUALITY)
        assert not any(isinstance(e, AssetApproved) for e in review.pull_events())

    def test_given_a_rejection_then_no_screening_is_required(self) -> None:
        review = ReviewDecision.open(uuid4(), "hamid")
        review.reject(RejectionReason.OFF_BRIEF)
        assert review.screening is None

    def test_given_an_ip_risk_rejection_then_the_reason_reaches_the_event(self) -> None:
        # Creative Direction must be able to tell trademark risk from "off
        # brief", so an IP rejection is never silently re-rolled into the same
        # prompt set. That only works if the reason survives on the event.
        review = ReviewDecision.open(uuid4(), "hamid")
        review.reject(RejectionReason.IP_RISK)
        (event,) = review.pull_events()
        assert isinstance(event, AssetRejected)
        assert event.reason is RejectionReason.IP_RISK
        assert review.rejection_reason is RejectionReason.IP_RISK


class TestReviewLifecycle:
    def test_given_a_new_review_when_opened_then_undecided(self) -> None:
        assert not ReviewDecision.open(uuid4(), "hamid").is_decided

    def test_given_no_reviewer_when_opened_then_raises(self) -> None:
        with pytest.raises(ValueError, match="reviewer"):
            ReviewDecision.open(uuid4(), "   ")

    def test_given_events_pulled_when_pulled_again_then_empty(self) -> None:
        review = ReviewDecision.open(uuid4(), "hamid")
        review.approve(IpScreening.cleared_by("hamid"))
        review.pull_events()
        assert review.pull_events() == []

    def test_given_an_undecided_review_then_it_emits_nothing(self) -> None:
        """No decision means no AssetApproved, so nothing downstream unlocks."""
        assert ReviewDecision.open(uuid4(), "hamid").pull_events() == []


class TestApprovalCannotBeForged:
    """Found by a compliance review of the first version of this file.

    Guarding only inside approve() left the raw constructor open, and the
    repository that rehydrates rows from the database would have used exactly
    that path.
    """

    def test_given_an_approved_decision_with_no_screening_when_constructed_then_raises(
        self,
    ) -> None:
        from kairos.curation.domain.value_objects import ApprovalDecision

        with pytest.raises(ValueError, match="must carry a completed IpScreening"):
            ReviewDecision(
                review_id=uuid4(),
                asset_id=uuid4(),
                reviewer="attacker",
                decision=ApprovalDecision(approved=True),
                screening=None,
            )

    def test_given_a_rejected_decision_with_no_screening_when_constructed_then_allowed(
        self,
    ) -> None:
        # Rejections need no screening — nothing proceeds from them.
        from kairos.curation.domain.value_objects import ApprovalDecision

        review = ReviewDecision(
            review_id=uuid4(),
            asset_id=uuid4(),
            reviewer="hamid",
            decision=ApprovalDecision(approved=False),
            rejection_reason=RejectionReason.IP_RISK,
        )
        assert review.is_decided

    def test_given_a_valid_approval_when_rehydrated_then_allowed(self) -> None:
        # The shape a repository must reconstruct: approved, with its screening.
        from kairos.curation.domain.value_objects import ApprovalDecision

        review = ReviewDecision(
            review_id=uuid4(),
            asset_id=uuid4(),
            reviewer="hamid",
            decision=ApprovalDecision(approved=True),
            screening=IpScreening.cleared_by("hamid"),
        )
        assert review.is_decided
