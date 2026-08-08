"""DraftListing — the compliance gate's enforcement point (CMP-06).

CONTEXT.md §2: no code path may reach a draft, and therefore publication,
without a prior AssetApproved for that specific asset. Enforced here in the
application service, not in the UI, and answered from the database rather than
from an event object a caller happened to hand over.
"""

from __future__ import annotations

import logging
from uuid import UUID

from kairos.listing_authoring.domain.listing_draft import ListingDraft
from kairos.listing_authoring.domain.ports import ApprovalGate, UnapprovedAssetError
from kairos.listing_authoring.domain.value_objects import (
    AIDisclosure,
    ListingCopy,
    PricingRule,
)

logger = logging.getLogger(__name__)


class DraftListing:
    def __init__(self, approvals: ApprovalGate) -> None:
        self._approvals = approvals

    def __call__(
        self,
        asset_id: UUID,
        *,
        copy: ListingCopy,
        disclosure: AIDisclosure,
        pricing: PricingRule,
    ) -> ListingDraft:
        # The gate. Checked before anything is built, so there is no partially
        # drafted listing left behind for an unapproved asset.
        if not self._approvals.is_approved(asset_id):
            logger.warning("refused to draft a listing for unapproved asset %s", asset_id)
            raise UnapprovedAssetError(
                f"asset {asset_id} has no persisted human approval — "
                "it must pass Curation before a listing can exist"
            )
        return ListingDraft.draft(
            asset_id=asset_id, copy=copy, disclosure=disclosure, pricing=pricing
        )
