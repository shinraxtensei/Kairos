"""Value objects for Budgeting.

The risk being guarded against is real from the very first command the pipeline
runs: burning cash generating designs for niches that never sell (CONTEXT.md
§4.8, RSK-04). Only ~1-5% of listings drive most revenue, so the number that
matters is cost per *winning* design, not cost per image.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from kairos.shared_kernel.money import Money


class CostCategory(StrEnum):
    """What the money went on. Separated so cost per winning design can be
    attributed — a spike in upscaling is a different problem from a spike in
    generation."""

    IMAGE_GENERATION = "image_generation"
    UPSCALING = "upscaling"
    TREND_DATA = "trend_data"
    LISTING_FEE = "listing_fee"
    TRANSACTION_FEE = "transaction_fee"
    ADVERTISING = "advertising"


class BudgetPeriod(StrEnum):
    DAILY = "daily"
    MONTHLY = "monthly"


@dataclass(frozen=True, slots=True)
class CostEvent:
    """One thing that cost money.

    `reference` ties the spend back to whatever caused it — an asset id, a
    listing id — so cost per winning design can be computed later instead of
    estimated.
    """

    category: CostCategory
    amount: Money
    reference: str | None = None
    cost_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.amount.amount < 0:
            raise ValueError("a cost cannot be negative — refunds are not costs")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")

    @property
    def on_day(self) -> date:
        return self.occurred_at.astimezone(UTC).date()


@dataclass(frozen=True, slots=True)
class BudgetLimit:
    """Daily and monthly ceilings.

    Both, not one: a daily cap alone lets a slow leak run all month, and a
    monthly cap alone lets a single runaway loop burn the month in an hour.
    """

    daily: Money
    monthly: Money

    def __post_init__(self) -> None:
        if self.daily.currency != self.monthly.currency:
            raise ValueError("daily and monthly caps must share a currency")
        if self.daily.amount <= 0 or self.monthly.amount <= 0:
            raise ValueError("a budget cap must be positive")
        if self.monthly.amount < self.daily.amount:
            raise ValueError("monthly cap is below the daily cap — the daily one could never bind")

    @property
    def currency(self) -> str:
        return self.daily.currency

    def cap_for(self, period: BudgetPeriod) -> Money:
        return self.daily if period is BudgetPeriod.DAILY else self.monthly
