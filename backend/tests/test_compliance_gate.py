"""CMP-06 — the human-approval gate, end to end against real Postgres.

The single most important test file in the project. It asserts that no path
reaches a listing draft, and therefore publication, without a persisted human
approval carrying a completed IP screening (CONTEXT.md §2).

Lives in the shared tests/ root because it drives Curation and Listing Authoring
together, and neither may import the other.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from kairos.curation.application.review_asset import ApproveAsset, RejectAsset
from kairos.curation.domain.value_objects import IpCheck, RejectionReason
from kairos.curation.infrastructure.models import ReviewDecisionRecord
from kairos.curation.infrastructure.repository import SqlAlchemyReviewDecisionRepository
from kairos.db import Base, SessionLocal, engine
from kairos.listing_authoring.application.draft_listing import DraftListing
from kairos.listing_authoring.domain.ports import UnapprovedAssetError
from kairos.listing_authoring.domain.value_objects import (
    AIDisclosure,
    ListingCopy,
    PricingRule,
)
from kairos.listing_authoring.infrastructure.approval_gate import CurationApprovalGate
from kairos.shared_kernel.money import Money

ALL_CHECKS = set(IpCheck)

COPY = ListingCopy(
    title="Moon Phase Print — Printable Wall Art",
    tags=("moon phase", "wall art", "printable", "boho decor"),
    description="A printable moon phase poster for boho interiors. Instant download.",
)
DISCLOSURE = AIDisclosure(
    seller_name="Kairos Studio",
    tool_summary="Artwork developed with AI image tools and curated by hand.",
)
PRICING = PricingRule(Money(Decimal("6.00"), "USD"))


@pytest.fixture(scope="module", autouse=True)
def _require_database() -> None:
    try:
        with engine.connect():
            pass
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"postgres unavailable: {type(exc).__name__}")
    Base.metadata.create_all(engine)


@pytest.fixture
def session() -> Iterator[Session]:
    with SessionLocal() as session:
        session.query(ReviewDecisionRecord).delete()
        session.commit()
        yield session


def _draft_listing(session: Session) -> DraftListing:
    return DraftListing(CurationApprovalGate(session))


def test_given_an_unreviewed_asset_when_drafted_then_refused(session: Session) -> None:
    """The default answer is no. An asset nobody has looked at cannot be listed."""
    with pytest.raises(UnapprovedAssetError, match="must pass Curation"):
        _draft_listing(session)(uuid4(), copy=COPY, disclosure=DISCLOSURE, pricing=PRICING)


def test_given_a_rejected_asset_when_drafted_then_refused(session: Session) -> None:
    asset_id = uuid4()
    RejectAsset(SqlAlchemyReviewDecisionRepository(session))(
        asset_id, reviewer="hamid", reason=RejectionReason.IP_RISK
    )

    with pytest.raises(UnapprovedAssetError):
        _draft_listing(session)(asset_id, copy=COPY, disclosure=DISCLOSURE, pricing=PRICING)


def test_given_an_approved_asset_when_drafted_then_allowed(session: Session) -> None:
    asset_id = uuid4()
    ApproveAsset(SqlAlchemyReviewDecisionRepository(session))(
        asset_id, reviewer="hamid", confirmed_checks=ALL_CHECKS
    )

    draft = _draft_listing(session)(asset_id, copy=COPY, disclosure=DISCLOSURE, pricing=PRICING)

    assert draft.asset_id == asset_id
    assert draft.is_publishable


def test_given_a_half_screened_approval_attempt_when_drafted_then_still_refused(
    session: Session,
) -> None:
    """The two halves of the gate compose.

    An approval that failed screening was never persisted, so Listing Authoring
    refuses independently — without needing to know why Curation said no.
    """
    asset_id = uuid4()
    with pytest.raises(ValueError, match="incomplete"):
        ApproveAsset(SqlAlchemyReviewDecisionRepository(session))(
            asset_id,
            reviewer="hamid",
            confirmed_checks={IpCheck.NO_BRAND_NAME_OR_LOGO},
        )

    with pytest.raises(UnapprovedAssetError):
        _draft_listing(session)(asset_id, copy=COPY, disclosure=DISCLOSURE, pricing=PRICING)


def test_given_a_forged_approval_event_when_drafted_then_still_refused(
    session: Session,
) -> None:
    """AssetApproved is a plain dataclass anyone can construct.

    Constructing one is not approval, because the gate asks the database rather
    than accepting an object. This is the carry-over finding from the ENG-29
    compliance review, asserted rather than assumed.
    """
    from kairos.curation.domain.events import AssetApproved

    asset_id = uuid4()
    AssetApproved(review_id=uuid4(), asset_id=asset_id, reviewer="attacker", screened_by="nobody")

    with pytest.raises(UnapprovedAssetError):
        _draft_listing(session)(asset_id, copy=COPY, disclosure=DISCLOSURE, pricing=PRICING)


def test_given_an_approval_for_a_different_asset_when_drafted_then_refused(
    session: Session,
) -> None:
    """Approval is per-asset. One approved design does not unlock its siblings."""
    approved, other = uuid4(), uuid4()
    ApproveAsset(SqlAlchemyReviewDecisionRepository(session))(
        approved, reviewer="hamid", confirmed_checks=ALL_CHECKS
    )

    with pytest.raises(UnapprovedAssetError):
        _draft_listing(session)(other, copy=COPY, disclosure=DISCLOSURE, pricing=PRICING)


def test_given_a_draft_when_created_then_it_carries_the_required_disclosure(
    session: Session,
) -> None:
    asset_id = uuid4()
    ApproveAsset(SqlAlchemyReviewDecisionRepository(session))(
        asset_id, reviewer="hamid", confirmed_checks=ALL_CHECKS
    )

    draft = _draft_listing(session)(asset_id, copy=COPY, disclosure=DISCLOSURE, pricing=PRICING)

    assert draft.disclosure.attribution == "Designed by Kairos Studio"
    assert "Made by" not in draft.disclosure.as_listing_text()
    ready = draft.pull_events()[-1]
    assert ready.attribution.startswith("Designed by")
