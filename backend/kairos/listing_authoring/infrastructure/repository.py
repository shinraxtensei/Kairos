"""SQLAlchemy implementation of ListingDraftRepository."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from kairos.listing_authoring.domain.listing_draft import ListingDraft
from kairos.listing_authoring.domain.ports import ListingDraftRepository
from kairos.listing_authoring.domain.value_objects import (
    AIDisclosure,
    ListingCopy,
    PricingRule,
)
from kairos.listing_authoring.infrastructure.models import ListingDraftRecord
from kairos.shared_kernel.money import Money


def _to_domain(record: ListingDraftRecord) -> ListingDraft:
    # Rebuilt through the real value objects. AIDisclosure is a required
    # constructor argument, so a row missing its disclosure cannot rehydrate
    # into a publishable draft — it raises here instead (CONTEXT.md §2).
    return ListingDraft(
        draft_id=record.draft_id,
        asset_id=record.asset_id,
        copy=ListingCopy(
            title=record.title,
            tags=tuple(record.tags),
            description=record.description,
        ),
        disclosure=AIDisclosure(
            seller_name=record.disclosure_seller,
            tool_summary=record.disclosure_tools,
        ),
        pricing=PricingRule(Money(Decimal(str(record.price_amount)), record.price_currency)),
        created_at=record.created_at,
    )


class SqlAlchemyListingDraftRepository(ListingDraftRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, draft: ListingDraft) -> None:
        row = {
            "draft_id": draft.draft_id,
            "asset_id": draft.asset_id,
            "title": draft.copy.title,
            "tags": list(draft.copy.tags),
            "description": draft.copy.description,
            "disclosure_seller": draft.disclosure.seller_name,
            "disclosure_tools": draft.disclosure.tool_summary,
            "price_amount": draft.pricing.price.amount,
            "price_currency": draft.pricing.price.currency,
            "created_at": draft.created_at,
        }
        statement = insert(ListingDraftRecord).values([row])
        # Keyed on asset_id, not draft_id: one approved asset is one draft, and
        # a redrafted asset should replace its draft rather than add a second
        # one that would become a second paid listing.
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["asset_id"],
                set_={
                    key: statement.excluded[key]
                    for key in (
                        "title",
                        "tags",
                        "description",
                        "disclosure_seller",
                        "disclosure_tools",
                        "price_amount",
                        "price_currency",
                    )
                },
            )
        )
        self._session.commit()

    def for_asset(self, asset_id: UUID) -> ListingDraft | None:
        record = self._session.scalars(
            select(ListingDraftRecord).where(ListingDraftRecord.asset_id == asset_id)
        ).first()
        return _to_domain(record) if record else None

    def recent(self, *, limit: int = 50) -> Sequence[ListingDraft]:
        query = (
            select(ListingDraftRecord).order_by(ListingDraftRecord.created_at.desc()).limit(limit)
        )
        return [_to_domain(row) for row in self._session.scalars(query)]
