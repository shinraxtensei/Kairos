"""Budget API, driven through HTTP against real Postgres.

Lives in the shared tests/ root rather than inside Budgeting: it imports
`kairos.app`, which is the composition root and therefore reaches every context.
Putting it in one context's tests/ makes that context import all the others and
breaks the independence contract — which is exactly what happened on the first
attempt.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from kairos.app import app
from kairos.budgeting.application.metered_spend import RecordSpend
from kairos.budgeting.domain.value_objects import BudgetLimit, CostCategory
from kairos.budgeting.infrastructure.models import CostEventRecord
from kairos.budgeting.infrastructure.repository import SqlAlchemySpendLedgerRepository
from kairos.db import Base, SessionLocal, engine
from kairos.shared_kernel.money import Money

client = TestClient(app)


def usd(amount: str) -> Money:
    return Money.of(amount, "USD")


# Matches the configured defaults in Settings, so the dashboard under test is
# the one the app actually serves.
LIMIT = BudgetLimit(daily=usd("2.00"), monthly=usd("40.00"))


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
        session.query(CostEventRecord).delete()
        session.commit()
        yield session


def _record(session: Session) -> RecordSpend:
    return RecordSpend(SqlAlchemySpendLedgerRepository(session, LIMIT))


def test_given_no_spend_when_read_then_no_categories(session: Session) -> None:
    response = client.get("/api/budget")
    assert response.status_code == 200
    assert response.json()["by_category"] == []


def test_given_spend_when_read_then_categories_carry_their_metered_flag(session: Session) -> None:
    record = _record(session)
    record(CostCategory.IMAGE_GENERATION, usd("0.40"))
    record(CostCategory.LISTING_FEE, usd("0.20"))

    rows = {r["label"]: r for r in client.get("/api/budget").json()["by_category"]}

    assert rows["Image generation"]["metered"] is True
    # Carried as a flag rather than left for the client to infer, so a dashboard
    # cannot be misread as "we are closer to the cap than we are".
    assert rows["Etsy listing fee"]["metered"] is False


def test_given_a_breached_cap_when_read_then_reports_paused(session: Session) -> None:
    _record(session)(CostCategory.IMAGE_GENERATION, usd("2.00"))
    assert client.get("/api/budget").json()["paused"] is True


def test_given_the_json_endpoint_when_called_then_reports_both_meters(
    session: Session,
) -> None:
    _record(session)(CostCategory.IMAGE_GENERATION, usd("0.50"))

    payload = client.get("/api/budget").json()

    assert {m["period"] for m in payload["meters"]} == {"daily", "monthly"}
    daily = next(m for m in payload["meters"] if m["period"] == "daily")
    assert daily["spent"] == "0.50 USD"
    assert daily["remaining"] == "1.50 USD"
    assert payload["paused"] is False
