"""Money — the one value object genuinely shared across contexts.

Budgeting tracks spend in it, Listing Authoring prices in it, Analytics reports
revenue in it. Keep shared_kernel this small (CONTEXT.md §3.2); anything only
two contexts need belongs to one of them, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


class CurrencyMismatchError(ValueError):
    """Raised when arithmetic mixes two currencies. Never silently convert."""


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("amount must be a Decimal — floats lose cents")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError(f"currency must be a 3-letter ISO 4217 code, got {self.currency!r}")
        object.__setattr__(self, "currency", self.currency.upper())
        object.__setattr__(self, "amount", self.amount.quantize(Decimal("0.01"), ROUND_HALF_UP))

    @classmethod
    def of(cls, amount: str | int | Decimal, currency: str) -> Money:
        """Build from a string or int. Deliberately no float overload."""
        return cls(Decimal(str(amount)), currency)

    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(Decimal("0"), currency)

    def _same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(f"cannot combine {self.currency} and {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: int | Decimal) -> Money:
        if isinstance(factor, float):
            raise TypeError("multiply by Decimal or int, not float")
        return Money(self.amount * Decimal(str(factor)), self.currency)

    def __lt__(self, other: Money) -> bool:
        self._same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._same_currency(other)
        return self.amount <= other.amount

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"
