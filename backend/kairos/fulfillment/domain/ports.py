"""Ports for Fulfillment."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from kairos.fulfillment.domain.listing import Listing


class ListingRepository(ABC):
    @abstractmethod
    def save(self, listing: Listing) -> None: ...

    @abstractmethod
    def for_draft(self, draft_id: UUID) -> Listing | None:
        """The existing listing for a draft, if any.

        The first half of publish idempotency: a redelivered task finds the
        prior attempt here rather than creating a second listing.
        """

    @abstractmethod
    def live(self, *, limit: int = 100) -> Sequence[Listing]: ...
