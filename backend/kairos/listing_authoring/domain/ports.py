"""Ports for Listing Authoring."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID


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
