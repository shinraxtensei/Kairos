"""Ports for Curation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from kairos.curation.domain.review_decision import ReviewDecision


class ReviewDecisionRepository(ABC):
    @abstractmethod
    def save(self, review: ReviewDecision) -> None: ...

    @abstractmethod
    def for_asset(self, asset_id: UUID) -> ReviewDecision | None: ...

    @abstractmethod
    def approval_exists_for(self, asset_id: UUID) -> bool:
        """Whether this asset has a persisted, screened approval.

        This is the query CMP-06 must use. `AssetApproved` is a plain dataclass
        anyone can construct, so receiving one proves nothing — an in-memory
        event is a message, not a credential. Listing Authoring has to ask the
        database whether a real review happened.
        """

    @abstractmethod
    def pending(self, *, limit: int = 50) -> Sequence[ReviewDecision]: ...
