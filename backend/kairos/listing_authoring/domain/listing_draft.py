"""The ListingDraft aggregate.

CONTEXT.md §4.6: it must be structurally impossible to construct a publishable
draft without an AIDisclosure. That is done by making it a required constructor
argument rather than an optional field validated later — the difference between
a type error at the call site and a runtime check somebody can forget to run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from kairos.listing_authoring.domain.events import ListingDrafted, ListingReadyToPublish
from kairos.listing_authoring.domain.value_objects import (
    AIDisclosure,
    ListingCopy,
    PricingRule,
)

DraftEvent = ListingDrafted | ListingReadyToPublish


@dataclass(eq=False, slots=True)
class ListingDraft:
    draft_id: UUID
    asset_id: UUID
    copy: ListingCopy
    # Required, not optional. Giving disclosure a default so it could be filled
    # in later would silently reintroduce the exact failure Etsy removes
    # listings for.
    disclosure: AIDisclosure
    pricing: PricingRule
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    events: list[DraftEvent] = field(default_factory=list, repr=False)

    @classmethod
    def draft(
        cls,
        *,
        asset_id: UUID,
        copy: ListingCopy,
        disclosure: AIDisclosure,
        pricing: PricingRule,
        draft_id: UUID | None = None,
    ) -> ListingDraft:
        draft = cls(
            draft_id=draft_id or uuid4(),
            asset_id=asset_id,
            copy=copy,
            disclosure=disclosure,
            pricing=pricing,
        )
        draft.events.append(ListingDrafted(draft_id=draft.draft_id, asset_id=asset_id))
        draft.events.append(
            ListingReadyToPublish(
                draft_id=draft.draft_id,
                asset_id=asset_id,
                title=copy.title,
                attribution=disclosure.attribution,
            )
        )
        return draft

    @property
    def is_publishable(self) -> bool:
        """Always true once constructed — which is the point.

        Kept as an explicit property so Fulfillment can assert it, and so the
        reason it is trivially true stays documented rather than reading like an
        oversight to whoever finds it next.
        """
        return True

    def pull_events(self) -> list[DraftEvent]:
        drained, self.events = self.events, []
        return drained

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ListingDraft) and self.draft_id == other.draft_id

    def __hash__(self) -> int:
        return hash(self.draft_id)
