"""SQLAlchemy implementation of ReviewDecisionRepository."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from kairos.curation.domain.ports import ReviewDecisionRepository
from kairos.curation.domain.review_decision import ReviewDecision
from kairos.curation.domain.value_objects import (
    ApprovalDecision,
    IpCheck,
    IpScreening,
    RejectionReason,
)
from kairos.curation.infrastructure.models import ReviewDecisionRecord


def _to_domain(record: ReviewDecisionRecord) -> ReviewDecision:
    screening = None
    if record.ip_checks_cleared is not None and record.screened_by is not None:
        # Rebuilt through IpScreening's own constructor, so a row whose checks
        # were tampered with or truncated fails loudly here rather than
        # rehydrating into an approval that was never fully screened.
        screening = IpScreening(
            frozenset(IpCheck(value) for value in record.ip_checks_cleared),
            record.screened_by,
        )
    decision = (
        ApprovalDecision(approved=record.approved, note=record.note)
        if record.approved is not None
        else None
    )
    return ReviewDecision(
        review_id=record.review_id,
        asset_id=record.asset_id,
        reviewer=record.reviewer,
        decision=decision,
        screening=screening,
        rejection_reason=(
            RejectionReason(record.rejection_reason) if record.rejection_reason else None
        ),
        decided_at=record.decided_at,
    )


class SqlAlchemyReviewDecisionRepository(ReviewDecisionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, review: ReviewDecision) -> None:
        row = {
            "review_id": review.review_id,
            "asset_id": review.asset_id,
            "reviewer": review.reviewer,
            "approved": review.decision.approved if review.decision else None,
            "rejection_reason": (
                review.rejection_reason.value if review.rejection_reason else None
            ),
            "note": review.decision.note if review.decision else "",
            "ip_checks_cleared": (
                sorted(check.value for check in review.screening.cleared)
                if review.screening
                else None
            ),
            "screened_by": review.screening.checked_by if review.screening else None,
            "decided_at": review.decided_at,
        }
        statement = insert(ReviewDecisionRecord).values([row])
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["review_id"],
                set_={
                    key: statement.excluded[key]
                    for key in (
                        "approved",
                        "rejection_reason",
                        "note",
                        "ip_checks_cleared",
                        "screened_by",
                        "decided_at",
                    )
                },
            )
        )
        self._session.commit()

    def for_asset(self, asset_id: UUID) -> ReviewDecision | None:
        record = self._session.scalars(
            select(ReviewDecisionRecord).where(ReviewDecisionRecord.asset_id == asset_id)
        ).first()
        return _to_domain(record) if record else None

    def approval_exists_for(self, asset_id: UUID) -> bool:
        # Deliberately asks for approved-is-true AND a screener on record. An
        # approval row without a screener is not an approval, whatever the
        # boolean says.
        return (
            self._session.scalars(
                select(ReviewDecisionRecord.review_id).where(
                    ReviewDecisionRecord.asset_id == asset_id,
                    ReviewDecisionRecord.approved.is_(True),
                    ReviewDecisionRecord.screened_by.isnot(None),
                )
            ).first()
            is not None
        )

    def pending(self, *, limit: int = 50) -> Sequence[ReviewDecision]:
        query = (
            select(ReviewDecisionRecord)
            .where(ReviewDecisionRecord.approved.is_(None))
            .order_by(ReviewDecisionRecord.review_id)
            .limit(limit)
        )
        return [_to_domain(row) for row in self._session.scalars(query)]
