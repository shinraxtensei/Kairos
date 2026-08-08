"""Value objects for Trend Discovery. Pure — no I/O, no SDKs (CONTEXT.md §3.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, StrEnum, auto

_WHITESPACE = re.compile(r"\s+")

MAX_KEYWORD_LENGTH = 200


class SourcePlatform(StrEnum):
    ETSY = "etsy"
    GOOGLE_TRENDS = "google_trends"
    TIKTOK = "tiktok"
    PINTEREST = "pinterest"
    AMAZON = "amazon"
    EBAY = "ebay"


class VolumeScale(Enum):
    """How a source's numbers should be read.

    This distinction is load-bearing. Google Trends reports a *relative* interest
    index (0-100, rescaled per query), while Etsy reports *absolute* result
    counts. Averaging 73 (Google) with 4,182 (Etsy) is meaningless, so the scale
    travels with the number and Niche Ranking must normalise per-source before
    combining. Collapsing this into a bare int is the quiet way to get a ranking
    formula that looks fine and ranks noise.
    """

    ABSOLUTE = auto()
    RELATIVE_INDEX = auto()


class CompetitionBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class Keyword:
    """A search term. Normalised so the same term from two sources compares equal."""

    text: str

    def __post_init__(self) -> None:
        normalised = _WHITESPACE.sub(" ", self.text).strip().lower()
        if not normalised:
            raise ValueError("keyword cannot be blank")
        if len(normalised) > MAX_KEYWORD_LENGTH:
            raise ValueError(f"keyword exceeds {MAX_KEYWORD_LENGTH} characters")
        object.__setattr__(self, "text", normalised)

    def __str__(self) -> str:
        return self.text


@dataclass(frozen=True, slots=True)
class SearchVolume:
    value: int
    scale: VolumeScale

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise TypeError("search volume must be an int")
        if self.value < 0:
            raise ValueError("search volume cannot be negative")
        if self.scale is VolumeScale.RELATIVE_INDEX and self.value > 100:
            raise ValueError("a relative interest index cannot exceed 100")

    @classmethod
    def absolute(cls, value: int) -> SearchVolume:
        return cls(value, VolumeScale.ABSOLUTE)

    @classmethod
    def relative_index(cls, value: int) -> SearchVolume:
        return cls(value, VolumeScale.RELATIVE_INDEX)

    def is_comparable_to(self, other: SearchVolume) -> bool:
        return self.scale is other.scale


@dataclass(frozen=True, slots=True)
class CompetitionLevel:
    """How crowded a keyword is, normalised to 0-100 where higher means worse."""

    score: int

    def __post_init__(self) -> None:
        if isinstance(self.score, bool) or not isinstance(self.score, int):
            raise TypeError("competition score must be an int")
        if not 0 <= self.score <= 100:
            raise ValueError("competition score must be between 0 and 100")

    @classmethod
    def from_competing_listings(cls, count: int) -> CompetitionLevel:
        """Map a raw competing-listing count onto the 0-100 scale.

        The thresholds are a domain rule, not an adapter detail, so every source
        that can report a listing count maps through the same ladder. They are a
        starting guess and should be retuned once Analytics (M7) shows which
        bands actually correlate with sales.
        """
        if count < 0:
            raise ValueError("competing listing count cannot be negative")
        ladder = ((100, 10), (1_000, 30), (10_000, 55), (50_000, 75), (100_000, 90))
        for threshold, score in ladder:
            if count < threshold:
                return cls(score)
        return cls(100)

    @property
    def band(self) -> CompetitionBand:
        if self.score < 34:
            return CompetitionBand.LOW
        if self.score < 67:
            return CompetitionBand.MEDIUM
        return CompetitionBand.HIGH
