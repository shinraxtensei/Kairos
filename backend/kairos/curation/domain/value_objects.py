"""Value objects for Curation — the compliance boundary (CONTEXT.md §2, §4.5).

The rules here are the ones that protect the shop's existence. Etsy honours DMCA
takedowns without investigating, strikes accumulate, and a *pattern* of
infringement means permanent suspension — you are liable for a design you did
not know was infringing. So IP screening is not a checkbox on a form; it is a
precondition the type system refuses to let an approval skip.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MAX_NOTE_LENGTH = 2000


class RejectionReason(StrEnum):
    """Why an asset was rejected. Recorded so Creative Direction can learn.

    `IP_RISK` is deliberately distinct from `OFF_BRIEF` — a design rejected for
    trademark risk must never be quietly re-rolled into the same prompt set.
    """

    IP_RISK = "ip_risk"
    POOR_QUALITY = "poor_quality"
    OFF_BRIEF = "off_brief"
    DUPLICATE = "duplicate"
    OTHER = "other"


class IpCheck(StrEnum):
    """The CMP-04 screening checklist, as structure rather than prose.

    Each is a distinct way to lose the shop. They are separate members so a
    reviewer confirms them individually — a single "looks fine" checkbox is a
    checkbox nobody reads.
    """

    NO_BRAND_NAME_OR_LOGO = "no_brand_name_or_logo"
    NO_COPYRIGHTED_CHARACTER = "no_copyrighted_character"
    NO_CELEBRITY_LIKENESS = "no_celebrity_likeness"
    NO_SPORTS_TEAM_OR_UNIVERSITY = "no_sports_team_or_university"
    NO_SONG_LYRIC_OR_QUOTE = "no_song_lyric_or_quote"
    NO_TRADEMARKED_PHRASE = "no_trademarked_phrase"


@dataclass(frozen=True, slots=True)
class IpScreening:
    """A completed IP screening. Cannot be constructed half-done.

    `cleared` must name every `IpCheck`. Anything less raises, so there is no
    representable state of "approved, screening partly done" — the aggregate
    below can then depend on this type alone rather than re-validating.
    """

    cleared: frozenset[IpCheck]
    checked_by: str

    def __post_init__(self) -> None:
        if not self.checked_by.strip():
            raise ValueError("IP screening must record who performed it")
        missing = set(IpCheck) - set(self.cleared)
        if missing:
            names = ", ".join(sorted(check.value for check in missing))
            raise ValueError(f"IP screening incomplete — not cleared: {names}")

    @classmethod
    def cleared_by(cls, reviewer: str) -> IpScreening:
        """All checks confirmed. Explicit at the call site, by design."""
        return cls(frozenset(IpCheck), reviewer)


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    approved: bool
    note: str = ""

    def __post_init__(self) -> None:
        if len(self.note) > MAX_NOTE_LENGTH:
            raise ValueError(f"note exceeds {MAX_NOTE_LENGTH} characters")
