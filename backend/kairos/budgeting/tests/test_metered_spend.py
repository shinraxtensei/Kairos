"""Application-layer tests — real ports, hand-written fake, no I/O."""

from __future__ import annotations

import pytest

from kairos.budgeting.application.metered_spend import MeteredSpend, RecordSpend
from kairos.budgeting.domain.ports import SpendLedgerRepository
from kairos.budgeting.domain.spend_ledger import BudgetExceededError, SpendLedger
from kairos.budgeting.domain.value_objects import BudgetLimit, CostCategory
from kairos.shared_kernel.money import Money


def usd(amount: str) -> Money:
    return Money.of(amount, "USD")


LIMIT = BudgetLimit(daily=usd("1.00"), monthly=usd("30.00"))


class InMemorySpendLedgerRepository(SpendLedgerRepository):
    def __init__(self, ledger: SpendLedger | None = None) -> None:
        self.ledger = ledger or SpendLedger.opened(LIMIT)
        self.saves = 0

    def current(self) -> SpendLedger:
        return self.ledger

    def save(self, ledger: SpendLedger) -> None:
        self.ledger = ledger
        self.saves += 1


class FakeImageApi:
    """Stands in for a paid endpoint, and counts how often it was actually hit."""

    def __init__(self, fails: bool = False) -> None:
        self.calls = 0
        self._fails = fails

    def generate(self) -> str:
        self.calls += 1
        if self._fails:
            raise ConnectionError("provider 502")
        return "image-bytes"


def test_given_budget_available_when_metered_then_the_call_runs_and_spend_records() -> None:
    repository = InMemorySpendLedgerRepository()
    api = FakeImageApi()
    metered = MeteredSpend(repository)

    with metered.metered(CostCategory.IMAGE_GENERATION, usd("0.04"), reference="asset-1"):
        api.generate()

    assert api.calls == 1
    assert repository.ledger.spent_today == usd("0.04")


def test_given_a_breached_cap_when_metered_then_the_paid_call_never_happens() -> None:
    """The whole point. Refusal has to come before the money leaves."""
    repository = InMemorySpendLedgerRepository()
    api = FakeImageApi()
    metered = MeteredSpend(repository)
    RecordSpend(repository)(CostCategory.IMAGE_GENERATION, usd("1.00"))

    with (
        pytest.raises(BudgetExceededError),
        metered.metered(CostCategory.IMAGE_GENERATION, usd("0.04")),
    ):
        api.generate()

    assert api.calls == 0


def test_given_a_spend_that_would_overshoot_when_metered_then_refused_before_calling() -> None:
    repository = InMemorySpendLedgerRepository()
    api = FakeImageApi()
    RecordSpend(repository)(CostCategory.IMAGE_GENERATION, usd("0.98"))

    with (
        pytest.raises(BudgetExceededError),
        MeteredSpend(repository).metered(CostCategory.IMAGE_GENERATION, usd("0.04")),
    ):
        api.generate()

    assert api.calls == 0
    assert repository.ledger.spent_today == usd("0.98")


def test_given_the_vendor_fails_when_metered_then_nothing_is_recorded() -> None:
    """A call that errored was not billed, so it must not eat budget."""
    repository = InMemorySpendLedgerRepository()
    api = FakeImageApi(fails=True)

    with (
        pytest.raises(ConnectionError),
        MeteredSpend(repository).metered(CostCategory.IMAGE_GENERATION, usd("0.04")),
    ):
        api.generate()

    assert repository.ledger.spent_today == usd("0.00")


def test_given_repeated_spend_when_the_cap_is_hit_then_the_pipeline_pauses() -> None:
    repository = InMemorySpendLedgerRepository()
    record = RecordSpend(repository)
    metered = MeteredSpend(repository)

    for _ in range(25):  # 25 x 0.04 = exactly 1.00, the daily cap
        record(CostCategory.IMAGE_GENERATION, usd("0.04"))

    assert metered.is_paused()
    with (
        pytest.raises(BudgetExceededError, match="paused"),
        metered.metered(CostCategory.IMAGE_GENERATION, usd("0.04")),
    ):
        pass


def test_given_a_new_day_when_the_ledger_rolls_then_spending_is_authorized_again() -> None:
    """A daily cap has to stop binding once the day is over."""
    from datetime import timedelta

    repository = InMemorySpendLedgerRepository()
    RecordSpend(repository)(CostCategory.IMAGE_GENERATION, usd("1.00"))
    assert repository.ledger.is_paused

    repository.ledger.roll_to(repository.ledger.today + timedelta(days=1))

    assert not repository.ledger.is_paused
    repository.ledger.authorize(usd("0.04"))  # no longer refused


def test_given_a_stale_ledger_when_a_cost_arrives_then_it_misses_the_daily_total() -> None:
    """Documents a real constraint rather than asserting a bug is fine.

    `record` only adds to `spent_today` when the cost's own date matches the
    ledger's. So a ledger left on yesterday undercounts today's spend, and the
    daily cap silently stops binding. That is why `SpendLedgerRepository.current`
    is specified to roll the ledger forward before returning it — the persistence
    adapter owns that, and this test exists so removing it breaks something.
    """
    from datetime import timedelta

    repository = InMemorySpendLedgerRepository()
    ledger = repository.ledger
    ledger.roll_to(ledger.today + timedelta(days=1))  # ledger now ahead of "now"

    RecordSpend(repository)(CostCategory.IMAGE_GENERATION, usd("0.40"))

    assert ledger.spent_today == usd("0.00")
    assert ledger.spent_this_month == usd("0.40")
