"""Budgeting persistence and the dashboard, against real Postgres.

The interesting property is that totals are *derived* from stored cost events
rather than kept as running counters. That removes a whole class of bug — a
counter that drifts makes a cap fail silently, and always in the expensive
direction.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from kairos.budgeting.application.metered_spend import MeteredSpend, RecordSpend
from kairos.budgeting.domain.spend_ledger import BudgetExceededError
from kairos.budgeting.domain.value_objects import BudgetLimit, CostCategory, CostEvent
from kairos.budgeting.infrastructure.models import CostEventRecord
from kairos.budgeting.infrastructure.repository import SqlAlchemySpendLedgerRepository
from kairos.db import Base, SessionLocal, engine
from kairos.shared_kernel.money import Money


def usd(amount: str) -> Money:
    return Money.of(amount, "USD")


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


def _repo(session: Session) -> SqlAlchemySpendLedgerRepository:
    return SqlAlchemySpendLedgerRepository(session, LIMIT)


def test_given_no_spend_when_read_then_ledger_is_empty(session: Session) -> None:
    ledger = _repo(session).current()
    assert ledger.spent_today == usd("0.00")
    assert not ledger.is_paused


def test_given_recorded_spend_when_reread_then_totals_are_summed_from_events(
    session: Session,
) -> None:
    record = RecordSpend(_repo(session))
    for _ in range(3):
        record(CostCategory.IMAGE_GENERATION, usd("0.04"), reference="asset-1")

    ledger = _repo(session).current()
    assert ledger.spent_today == usd("0.12")
    assert ledger.spent_this_month == usd("0.12")


def test_given_the_same_cost_id_twice_when_saved_then_the_budget_is_not_double_charged(
    session: Session,
) -> None:
    """Celery redelivery replays the same cost. Charging twice would pause the
    pipeline early on money that was never actually spent."""
    repository = _repo(session)
    ledger = repository.current()
    cost = CostEvent(category=CostCategory.IMAGE_GENERATION, amount=usd("0.50"))

    ledger.record(cost)
    repository.save(ledger)
    ledger.record(cost)
    repository.save(ledger)

    assert repository.current().spent_today == usd("0.50")


def test_given_a_selling_fee_when_recorded_then_it_does_not_count_toward_the_cap(
    session: Session,
) -> None:
    """Etsy's fees follow from selling. Metering them would pause generation
    because something sold, which is exactly backwards."""
    record = RecordSpend(_repo(session))
    record(CostCategory.LISTING_FEE, usd("0.20"))
    record(CostCategory.TRANSACTION_FEE, usd("1.90"))

    ledger = _repo(session).current()
    assert ledger.spent_today == usd("0.00")
    assert not ledger.is_paused
    # But the money is still on record for cost-per-winning-design.
    assert session.query(CostEventRecord).count() == 2


def test_given_spend_last_month_when_read_then_it_is_outside_the_monthly_total(
    session: Session,
) -> None:
    repository = _repo(session)
    ledger = repository.current()
    ledger.record(
        CostEvent(
            category=CostCategory.IMAGE_GENERATION,
            amount=usd("30.00"),
            occurred_at=datetime.now(UTC) - timedelta(days=40),
        )
    )
    repository.save(ledger)

    assert repository.current().spent_this_month == usd("0.00")


def test_given_yesterdays_spend_when_read_then_it_leaves_the_daily_total(
    session: Session,
) -> None:
    """Deriving totals is what makes rollover free — a new day is just a
    different WHERE clause, with no ledger to remember to roll forward."""
    repository = _repo(session)
    ledger = repository.current()
    ledger.record(
        CostEvent(
            category=CostCategory.IMAGE_GENERATION,
            amount=usd("1.50"),
            occurred_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    repository.save(ledger)

    reread = repository.current()
    assert reread.spent_today == usd("0.00")
    assert reread.spent_this_month == usd("1.50")


def test_given_the_cap_is_reached_when_metering_then_the_paid_call_is_refused(
    session: Session,
) -> None:
    repository = _repo(session)
    RecordSpend(repository)(CostCategory.IMAGE_GENERATION, usd("2.00"))

    called = False
    with (
        pytest.raises(BudgetExceededError),
        MeteredSpend(repository).metered(CostCategory.IMAGE_GENERATION, usd("0.04")),
    ):
        called = True  # pragma: no cover - must never run

    assert not called
