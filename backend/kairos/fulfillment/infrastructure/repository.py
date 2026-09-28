"""SQLAlchemy implementation of ListingRepository."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from kairos.fulfillment.domain.listing import Listing, PublishState
from kairos.fulfillment.domain.ports import ListingRepository
from kairos.fulfillment.infrastructure.models import ListingRecord


def _to_domain(record: ListingRecord) -> Listing:
    return Listing(
        listing_id=record.listing_id,
        draft_id=record.draft_id,
        asset_id=record.asset_id,
        title=record.title,
        channel_name=record.channel_name,
        state=PublishState(record.state),
        external_id=record.external_id,
        external_url=record.external_url,
        failure_reason=record.failure_reason,
        attempts=record.attempts,
        published_at=record.published_at,
        created_at=record.created_at,
    )


class SqlAlchemyListingRepository(ListingRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, listing: Listing) -> None:
        row = {
            "listing_id": listing.listing_id,
            "draft_id": listing.draft_id,
            "asset_id": listing.asset_id,
            "title": listing.title,
            "channel_name": listing.channel_name,
            "state": listing.state.value,
            "external_id": listing.external_id,
            "external_url": listing.external_url,
            "failure_reason": listing.failure_reason,
            "attempts": listing.attempts,
            "published_at": listing.published_at,
            "created_at": listing.created_at,
        }
        statement = insert(ListingRecord).values([row])
        # Upsert on listing_id, which is derived from the draft — a retry
        # updates the attempt in place rather than colliding. `listings.draft_id`
        # is also UNIQUE, so a second row for one draft cannot exist even if
        # this path were bypassed (ENG-34).
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["listing_id"],
                set_={
                    key: statement.excluded[key]
                    for key in (
                        "state",
                        "external_id",
                        "external_url",
                        "failure_reason",
                        "attempts",
                        "published_at",
                    )
                },
            )
        )
        self._session.commit()

    def for_draft(self, draft_id: UUID) -> Listing | None:
        record = self._session.scalars(
            select(ListingRecord).where(ListingRecord.draft_id == draft_id)
        ).first()
        return _to_domain(record) if record else None

    def live(self, *, limit: int = 100) -> Sequence[Listing]:
        """Published listings, newest first — the Live Listings read model."""
        query = (
            select(ListingRecord)
            .where(ListingRecord.state == PublishState.PUBLISHED.value)
            .order_by(ListingRecord.published_at.desc())
            .limit(limit)
        )
        return [_to_domain(row) for row in self._session.scalars(query)]
