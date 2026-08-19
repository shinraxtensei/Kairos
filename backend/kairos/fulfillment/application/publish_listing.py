"""PublishListing — ENG-34's idempotency enforced where every channel shares it.

CONTEXT.md §4.7. The guard lives here rather than in an adapter, because the
cost of getting it wrong ($0.20 per duplicate, non-refundable) is identical for
Etsy and for Phase 2's POD channels, and one of them would eventually get it
wrong on its own.
"""

from __future__ import annotations

import logging
from uuid import UUID

from kairos.fulfillment.domain.listing import (
    AlreadyPublishedError,
    FulfillmentChannel,
    Listing,
)
from kairos.fulfillment.domain.ports import ListingRepository

logger = logging.getLogger(__name__)


class PublishListing:
    def __init__(self, channel: FulfillmentChannel, repository: ListingRepository) -> None:
        self._channel = channel
        self._repository = repository

    def __call__(
        self, *, draft_id: UUID, asset_id: UUID, title: str, force: bool = False
    ) -> Listing:
        """Publish a drafted listing exactly once.

        `force` exists for the operator, not for retries: it re-raises rather
        than republishing, so there is no argument any caller can pass that
        turns a duplicate into a silent success.
        """
        existing = self._repository.for_draft(draft_id)

        if existing is not None and existing.is_published:
            if force:
                # Deliberately still refused. A "force" that creates a second
                # paid listing is a footgun with a friendly name.
                raise AlreadyPublishedError(
                    f"draft {draft_id} is already live as {existing.external_id}; "
                    "force does not republish — delete the listing on the channel first"
                )
            logger.info(
                "draft %s already published as %s — returning the existing listing",
                draft_id,
                existing.external_id,
            )
            return existing

        listing = existing or Listing.pending(
            draft_id=draft_id,
            asset_id=asset_id,
            title=title,
            channel_name=self._channel.channel_name,
        )

        try:
            result = self._channel.publish(listing)
        except Exception as exc:
            # Recorded, not swallowed: a failed publish stays retryable, and the
            # attempt count is what makes a repeatedly failing draft visible.
            listing.record_failure(f"{type(exc).__name__}: {exc}")
            self._repository.save(listing)
            logger.warning("publish failed for draft %s: %s", draft_id, exc)
            raise

        listing.record_published(result)
        self._repository.save(listing)
        logger.info("published draft %s as %s", draft_id, result.external_id)
        return listing
