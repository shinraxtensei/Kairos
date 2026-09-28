"""Ports for Listing Authoring."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from kairos.listing_authoring.domain.listing_draft import ListingDraft


class ApprovalGate(ABC):
    """Asks whether an asset has a real, persisted human approval.

    Declared here in Listing Authoring's own terms. The adapter calls Curation's
    published facade, so this context never learns Curation's model — and the
    question is answered by the database, never by a passed-in event object.
    """

    @abstractmethod
    def is_approved(self, asset_id: UUID) -> bool: ...


class UnapprovedAssetError(RuntimeError):
    """CONTEXT.md §2: no path reaches a draft without a prior AssetApproved."""


class ListingDraftRepository(ABC):
    @abstractmethod
    def save(self, draft: ListingDraft) -> None: ...

    @abstractmethod
    def for_asset(self, asset_id: UUID) -> ListingDraft | None:
        """The draft for an approved asset, if one exists.

        `listing_drafts.asset_id` is UNIQUE: one approved asset yields one
        draft, so a retried DraftListing cannot produce two drafts that would
        each become a separate paid listing.
        """

    @abstractmethod
    def recent(self, *, limit: int = 50) -> Sequence[ListingDraft]: ...
