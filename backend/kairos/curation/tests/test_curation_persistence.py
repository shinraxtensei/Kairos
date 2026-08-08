"""Curation persistence and use cases, against real Postgres.

`approval_exists_for` is the query CMP-06 will gate publication on, so it gets
tested against the real database rather than a fake.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from kairos.curation.application.review_asset import ApproveAsset, RejectAsset
from kairos.curation.domain.review_decision import AlreadyReviewedError
from kairos.curation.domain.value_objects import IpCheck, RejectionReason
from kairos.curation.infrastructure.models import ReviewDecisionRecord
from kairos.curation.infrastructure.repository import SqlAlchemyReviewDecisionRepository
from kairos.db import Base, SessionLocal, engine

ALL_CHECKS = set(IpCheck)


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


def test_given_an_unreviewed_asset_when_asked_then_no_approval_exists(session: Session) -> None:
    assert not SqlAlchemyReviewDecisionRepository(session).approval_exists_for(uuid4())


def test_given_an_approved_asset_when_asked_then_approval_exists(session: Session) -> None:
    repository = SqlAlchemyReviewDecisionRepository(session)
    asset_id = uuid4()

    ApproveAsset(repository)(asset_id, reviewer="hamid", confirmed_checks=ALL_CHECKS)

    assert repository.approval_exists_for(asset_id)


def test_given_a_rejected_asset_when_asked_then_no_approval_exists(session: Session) -> None:
    """The whole point of the gate: rejection must not unlock publication."""
    repository = SqlAlchemyReviewDecisionRepository(session)
    asset_id = uuid4()

    RejectAsset(repository)(asset_id, reviewer="hamid", reason=RejectionReason.IP_RISK)

    assert not repository.approval_exists_for(asset_id)


def test_given_incomplete_checks_when_approving_then_raises_and_saves_nothing(
    session: Session,
) -> None:
    """A half-filled review form must not leave a partial approval behind."""
    repository = SqlAlchemyReviewDecisionRepository(session)
    asset_id = uuid4()

    with pytest.raises(ValueError, match="incomplete"):
        ApproveAsset(repository)(
            asset_id,
            reviewer="hamid",
            confirmed_checks={IpCheck.NO_BRAND_NAME_OR_LOGO},
        )

    assert repository.for_asset(asset_id) is None
    assert not repository.approval_exists_for(asset_id)


def test_given_an_already_reviewed_asset_when_reviewed_again_then_raises(
    session: Session,
) -> None:
    repository = SqlAlchemyReviewDecisionRepository(session)
    asset_id = uuid4()
    ApproveAsset(repository)(asset_id, reviewer="hamid", confirmed_checks=ALL_CHECKS)

    with pytest.raises(AlreadyReviewedError):
        RejectAsset(repository)(asset_id, reviewer="hamid", reason=RejectionReason.OTHER)


def test_given_an_approval_when_reloaded_then_the_screening_survives(session: Session) -> None:
    repository = SqlAlchemyReviewDecisionRepository(session)
    asset_id = uuid4()
    ApproveAsset(repository)(asset_id, reviewer="hamid", confirmed_checks=ALL_CHECKS, note="clean")

    reloaded = repository.for_asset(asset_id)

    assert reloaded is not None
    assert reloaded.screening is not None
    assert reloaded.screening.cleared == frozenset(IpCheck)
    assert reloaded.screening.checked_by == "hamid"
    assert reloaded.decision is not None
    assert reloaded.decision.note == "clean"


def test_given_a_row_with_a_truncated_screening_when_reloaded_then_raises(
    session: Session,
) -> None:
    """A tampered or corrupt row must not rehydrate into a valid approval.

    This is the database-side version of the forgery hole the compliance review
    found in the aggregate: rebuilding through IpScreening's own constructor is
    what makes the row fail loudly instead of unlocking publication.
    """
    repository = SqlAlchemyReviewDecisionRepository(session)
    asset_id = uuid4()
    ApproveAsset(repository)(asset_id, reviewer="hamid", confirmed_checks=ALL_CHECKS)

    record = session.query(ReviewDecisionRecord).filter_by(asset_id=asset_id).one()
    record.ip_checks_cleared = [IpCheck.NO_BRAND_NAME_OR_LOGO.value]
    session.commit()

    with pytest.raises(ValueError, match="incomplete"):
        repository.for_asset(asset_id)


def test_given_a_rejection_when_reloaded_then_the_reason_survives(session: Session) -> None:
    repository = SqlAlchemyReviewDecisionRepository(session)
    asset_id = uuid4()
    RejectAsset(repository)(
        asset_id, reviewer="hamid", reason=RejectionReason.IP_RISK, note="band logo"
    )

    reloaded = repository.for_asset(asset_id)

    assert reloaded is not None
    assert reloaded.rejection_reason is RejectionReason.IP_RISK
    assert reloaded.screening is None
