"""ReviewAsset, ApproveAsset, RejectAsset — the commands from CONTEXT.md §4.5.

Named for the business vocabulary, not CRUD. `ApproveAsset`, never
`UpdateStatus`.
"""

from __future__ import annotations

import logging
from uuid import UUID

from kairos.curation.domain.ports import ReviewDecisionRepository
from kairos.curation.domain.review_decision import AlreadyReviewedError, ReviewDecision
from kairos.curation.domain.value_objects import IpCheck, IpScreening, RejectionReason

logger = logging.getLogger(__name__)


class ApproveAsset:
    """Approve one asset. Requires every IP check to be confirmed by name.

    `confirmed_checks` is passed explicitly rather than defaulted, so a caller
    cannot approve by omission. `IpScreening` then rejects any incomplete set,
    which is where a partially-filled UI form fails — before anything is saved.
    """

    def __init__(self, repository: ReviewDecisionRepository) -> None:
        self._repository = repository

    def __call__(
        self,
        asset_id: UUID,
        *,
        reviewer: str,
        confirmed_checks: set[IpCheck],
        note: str = "",
    ) -> ReviewDecision:
        existing = self._repository.for_asset(asset_id)
        if existing is not None and existing.is_decided:
            raise AlreadyReviewedError(f"asset {asset_id} was already reviewed")

        screening = IpScreening(frozenset(confirmed_checks), reviewer)
        review = existing or ReviewDecision.open(asset_id, reviewer)
        review.approve(screening, note=note)
        self._repository.save(review)
        logger.info("asset %s approved by %s", asset_id, reviewer)
        return review


class RejectAsset:
    def __init__(self, repository: ReviewDecisionRepository) -> None:
        self._repository = repository

    def __call__(
        self, asset_id: UUID, *, reviewer: str, reason: RejectionReason, note: str = ""
    ) -> ReviewDecision:
        existing = self._repository.for_asset(asset_id)
        if existing is not None and existing.is_decided:
            raise AlreadyReviewedError(f"asset {asset_id} was already reviewed")

        review = existing or ReviewDecision.open(asset_id, reviewer)
        review.reject(reason, note=note)
        self._repository.save(review)
        return review
