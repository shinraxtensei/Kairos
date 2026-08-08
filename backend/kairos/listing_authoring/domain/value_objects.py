"""Value objects for Listing Authoring.

`AIDisclosure` is the one that matters. Etsy began enforcing AI disclosure on
2026-01-14 and removed roughly 12,000 listings in Q1 2026, some without warning.
CONTEXT.md §4.6 requires that constructing a publishable draft without one be
structurally impossible — so it is a required field, not a validated one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from kairos.shared_kernel.money import Money

# Etsy listing limits.
MAX_TITLE_LENGTH = 140
MAX_TAGS = 13
MAX_TAG_LENGTH = 20
MIN_DESCRIPTION_LENGTH = 40

_TAG_ALLOWED = re.compile(r"^[\w\s'-]+$", re.UNICODE)


class AttributionStyle(StrEnum):
    """Etsy's required wording. "Made by" claims hand-manufacture, which is
    false for an AI-assisted design and is what gets listings removed."""

    DESIGNED_BY = "designed_by"


@dataclass(frozen=True, slots=True)
class AIDisclosure:
    """Required on every draft. There is no "no AI used" variant here, because
    every asset in this pipeline is AI-assisted by construction."""

    seller_name: str
    tool_summary: str
    style: AttributionStyle = AttributionStyle.DESIGNED_BY

    def __post_init__(self) -> None:
        if not self.seller_name.strip():
            raise ValueError("AI disclosure must name the seller")
        if not self.tool_summary.strip():
            raise ValueError("AI disclosure must say how AI was used")

    @property
    def attribution(self) -> str:
        return f"Designed by {self.seller_name}"

    def as_listing_text(self) -> str:
        return f"{self.attribution}. {self.tool_summary}"


@dataclass(frozen=True, slots=True)
class ListingCopy:
    """Title, tags and description — the entire traffic mechanism (R2 gap).

    A listing without these is compliant and commercially invisible.
    """

    title: str
    tags: tuple[str, ...]
    description: str

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("a listing needs a title")
        if len(self.title) > MAX_TITLE_LENGTH:
            raise ValueError(f"title exceeds Etsy's {MAX_TITLE_LENGTH} characters")
        if len(self.tags) > MAX_TAGS:
            raise ValueError(f"{len(self.tags)} tags exceeds Etsy's limit of {MAX_TAGS}")
        for tag in self.tags:
            if len(tag) > MAX_TAG_LENGTH:
                raise ValueError(f"tag {tag!r} exceeds {MAX_TAG_LENGTH} characters")
            if not _TAG_ALLOWED.match(tag):
                raise ValueError(f"tag {tag!r} contains characters Etsy rejects")
        if len({t.lower() for t in self.tags}) != len(self.tags):
            raise ValueError("duplicate tags waste a limited slot")
        if len(self.description.strip()) < MIN_DESCRIPTION_LENGTH:
            raise ValueError("description is too short to rank or inform")

    @property
    def unused_tag_slots(self) -> int:
        """Every unused tag is discarded reach — all 13 should be filled."""
        return MAX_TAGS - len(self.tags)


@dataclass(frozen=True, slots=True)
class PricingRule:
    price: Money

    # Etsy takes $0.20 to list plus ~6.5% of the sale. Below this a sale can
    # net less than the fees, which is worse than not selling.
    MINIMUM = Decimal("1.00")

    def __post_init__(self) -> None:
        if self.price.amount < self.MINIMUM:
            raise ValueError(
                f"{self.price} is below the {self.MINIMUM} floor — "
                "Etsy's $0.20 listing fee plus ~6.5% would eat the margin"
            )
