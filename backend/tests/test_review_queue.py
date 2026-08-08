"""Review queue end to end, through the HTTP layer against real Postgres.

Lives in the shared tests/ root: it drives Content Generation and Curation
together, and neither context may import the other.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from kairos.app import app
from kairos.content_generation.domain.generated_asset import GeneratedAsset
from kairos.content_generation.domain.value_objects import (
    AssetFormat,
    AssetVariant,
    DeliveryFile,
    DeliveryPackage,
    GenerationFailure,
    PrintSpecification,
    ProcessingStage,
)
from kairos.content_generation.infrastructure.models import GeneratedAssetRecord
from kairos.content_generation.infrastructure.repository import (
    SqlAlchemyGeneratedAssetRepository,
)
from kairos.curation.domain.value_objects import IpCheck
from kairos.curation.infrastructure.models import ReviewDecisionRecord
from kairos.curation.infrastructure.repository import SqlAlchemyReviewDecisionRepository
from kairos.db import Base, SessionLocal, engine
from kairos.shared_kernel.money import Money

client = TestClient(app)
ALL_CHECK_VALUES = [check.value for check in IpCheck]


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
        session.query(GeneratedAssetRecord).delete()
        session.commit()
        yield session


def _packaged_asset(session: Session, keyword: str = "moon phase print") -> GeneratedAsset:
    asset = GeneratedAsset.generated(
        niche_keyword=keyword,
        variant=AssetVariant(index=0, seed=7),
        cost=Money(Decimal("0.04"), "USD"),
    )
    asset.advance_to(ProcessingStage.BACKGROUND_REMOVED)
    asset.advance_to(ProcessingStage.UPSCALED)
    asset.package(
        DeliveryPackage((DeliveryFile("poster.jpg", 5_000_000, AssetFormat.JPEG),)),
        PrintSpecification(18, 24),
    )
    SqlAlchemyGeneratedAssetRepository(session).save(asset)
    return asset


def test_given_no_assets_when_queue_opened_then_shows_empty_state(session: Session) -> None:
    response = client.get("/review")
    assert response.status_code == 200
    assert "Nothing awaiting review" in response.text


def test_given_a_packaged_asset_when_queue_opened_then_it_is_shown(session: Session) -> None:
    asset = _packaged_asset(session)
    response = client.get("/review")
    assert response.status_code == 200
    assert str(asset.asset_id) in response.text
    assert "moon phase print" in response.text


def test_given_an_unpackaged_asset_when_queue_opened_then_it_is_not_shown(
    session: Session,
) -> None:
    """Curation only sees finished assets — a half-processed one is not a design."""
    asset = GeneratedAsset.generated(niche_keyword="wip", variant=AssetVariant(0))
    SqlAlchemyGeneratedAssetRepository(session).save(asset)
    assert "Nothing awaiting review" in client.get("/review").text


def test_given_a_failed_asset_when_queue_opened_then_it_is_not_shown(session: Session) -> None:
    asset = GeneratedAsset.generated(niche_keyword="broken", variant=AssetVariant(0))
    asset.fail(GenerationFailure.CONTENT_FILTER)
    SqlAlchemyGeneratedAssetRepository(session).save(asset)
    assert "Nothing awaiting review" in client.get("/review").text


def test_given_the_queue_page_then_no_check_is_pre_ticked(session: Session) -> None:
    """CMP-05. A pre-ticked box is a box nobody reads.

    Asserted against the rendered HTML rather than trusting the template, since
    this is the difference between a real screening and theatre.
    """
    _packaged_asset(session)
    body = client.get("/review").text

    inputs = re.findall(r"<input[^>]*class=\"ip-check\"[^>]*>", body)
    assert len(inputs) == len(IpCheck)
    # Every box unticked. Matched against the tags themselves — a plain
    # `"checked" not in body` also matches `b.checked` in the page's script and
    # would pass whatever the markup did.
    assert not [tag for tag in inputs if "checked" in tag]


def test_given_all_checks_confirmed_when_approved_then_asset_leaves_the_queue(
    session: Session,
) -> None:
    asset = _packaged_asset(session)

    response = client.post(
        f"/review/{asset.asset_id}/approve",
        data={"confirmed": ALL_CHECK_VALUES},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert SqlAlchemyReviewDecisionRepository(session).approval_exists_for(asset.asset_id)
    assert "Nothing awaiting review" in client.get("/review").text


def test_given_a_tampered_form_when_approved_then_it_is_refused(session: Session) -> None:
    """The HTTP layer must not be the gate.

    Disabling the submit button client-side is a convenience. A hand-crafted
    POST with one box ticked — or a client with JavaScript off — must still fail,
    because the domain refuses an incomplete screening.
    """
    asset = _packaged_asset(session)

    with pytest.raises(ValueError, match="incomplete"):
        client.post(
            f"/review/{asset.asset_id}/approve",
            data={"confirmed": [IpCheck.NO_BRAND_NAME_OR_LOGO.value]},
        )

    assert not SqlAlchemyReviewDecisionRepository(session).approval_exists_for(asset.asset_id)


def test_given_an_empty_confirmation_when_approved_then_it_is_refused(
    session: Session,
) -> None:
    asset = _packaged_asset(session)

    with pytest.raises(ValueError, match="incomplete"):
        client.post(f"/review/{asset.asset_id}/approve", data={})

    assert not SqlAlchemyReviewDecisionRepository(session).approval_exists_for(asset.asset_id)


def test_given_a_rejection_when_submitted_then_asset_leaves_without_approval(
    session: Session,
) -> None:
    asset = _packaged_asset(session)

    response = client.post(
        f"/review/{asset.asset_id}/reject",
        data={"reason": "ip_risk", "note": "looks like a band logo"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    repository = SqlAlchemyReviewDecisionRepository(session)
    assert not repository.approval_exists_for(asset.asset_id)
    decision = repository.for_asset(asset.asset_id)
    assert decision is not None and decision.decision is not None
    assert not decision.decision.approved
    assert "Nothing awaiting review" in client.get("/review").text


def test_given_several_assets_when_queued_then_oldest_first_and_counted(
    session: Session,
) -> None:
    for i in range(3):
        _packaged_asset(session, keyword=f"niche {i}")
    body = client.get("/review").text
    assert "1 of 3 pending" in body
    assert "niche 0" in body


def test_given_an_index_when_navigating_then_a_different_asset_is_shown(
    session: Session,
) -> None:
    for i in range(3):
        _packaged_asset(session, keyword=f"niche {i}")
    assert "niche 1" in client.get("/review?i=1").text


def test_given_an_out_of_range_index_when_navigating_then_it_clamps(
    session: Session,
) -> None:
    _packaged_asset(session)
    assert client.get("/review?i=99").status_code == 200
    assert client.get("/review?i=-5").status_code == 200
