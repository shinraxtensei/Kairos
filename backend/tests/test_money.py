"""Domain-layer tests: pure, no mocks, no I/O. CONTEXT.md §8."""

from decimal import Decimal

import pytest

from kairos.shared_kernel.money import CurrencyMismatchError, Money


def test_given_two_amounts_in_same_currency_when_added_then_sums() -> None:
    assert Money.of("10.00", "USD") + Money.of("2.50", "USD") == Money.of("12.50", "USD")


def test_given_different_currencies_when_added_then_raises() -> None:
    with pytest.raises(CurrencyMismatchError):
        Money.of("10.00", "USD") + Money.of("10.00", "EUR")


def test_given_different_currencies_when_compared_then_raises() -> None:
    with pytest.raises(CurrencyMismatchError):
        _ = Money.of("1.00", "USD") < Money.of("1.00", "EUR")


def test_given_a_float_amount_when_constructed_then_raises() -> None:
    # Etsy fees are fractions of a cent; float rounding would quietly corrupt
    # the SpendLedger over thousands of CostEvents.
    with pytest.raises(TypeError):
        Money(0.1, "USD")  # type: ignore[arg-type]


def test_given_a_float_factor_when_multiplied_then_raises() -> None:
    with pytest.raises(TypeError):
        Money.of("1.00", "USD") * 0.065  # type: ignore[operator]


def test_given_sub_cent_precision_when_constructed_then_rounds_half_up() -> None:
    assert Money.of("0.125", "USD").amount == Decimal("0.13")
    assert Money.of("0.124", "USD").amount == Decimal("0.12")


def test_given_a_lowercase_currency_when_constructed_then_normalises() -> None:
    assert Money.of("1.00", "usd").currency == "USD"


@pytest.mark.parametrize("code", ["US", "USDD", "US1", ""])
def test_given_an_invalid_currency_code_when_constructed_then_raises(code: str) -> None:
    with pytest.raises(ValueError):
        Money.of("1.00", code)


def test_given_a_generation_cost_when_multiplied_by_volume_then_exact() -> None:
    # 100 generations at $0.04 — the arithmetic the budget cap depends on.
    assert Money.of("0.04", "USD") * 100 == Money.of("4.00", "USD")
