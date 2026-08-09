"""Value objects for Creative Direction.

This context is where CONTEXT.md §2's fourth compliance rule actually bites.
"No templated bulk generation" is not a policy someone remembers — it is a
property of the prompt set this context emits. If a `VariationSet` is fifty
prompts differing only by a swapped keyword, Etsy's detection sees fifty
near-identical listings and removes them together, and no amount of care
downstream repairs that.

So the rule is enforced here, at the only place with enough information to
judge it: a variation must differ along real creative axes, not by index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

MAX_VARIATIONS_PER_SET = 12
MIN_DISTINCT_AXES = 2

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


class StyleAxis(StrEnum):
    """The dimensions a design may genuinely vary along.

    Deliberately not "seed" or "index". Two images from the same prompt with
    different seeds are the same design twice, which is exactly what the
    originality rule exists to prevent.
    """

    PALETTE = "palette"
    COMPOSITION = "composition"
    MOOD = "mood"
    TEXTURE = "texture"
    SUBJECT_TREATMENT = "subject_treatment"


class TemplatedBulkGenerationError(ValueError):
    """A prompt set would produce near-identical designs.

    Named for the Etsy rule rather than for the code condition, so the reason it
    exists survives contact with whoever hits it next.
    """


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """A prompt with named slots, e.g. "a {mood} {palette} moon phase poster".

    Stored rather than hardcoded because these get tuned constantly — the text
    is data, not logic.
    """

    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("a prompt template cannot be blank")
        if not self.slots:
            raise TemplatedBulkGenerationError(
                "a template with no slots can only produce one design repeated — "
                "vary it along at least one StyleAxis"
            )
        unknown = self.slots - {axis.value for axis in StyleAxis}
        if unknown:
            raise ValueError(f"template refers to unknown axes: {', '.join(sorted(unknown))}")

    @property
    def slots(self) -> frozenset[str]:
        return frozenset(_PLACEHOLDER.findall(self.text))

    def render(self, values: dict[StyleAxis, str]) -> str:
        by_name = {axis.value: value for axis, value in values.items()}
        missing = self.slots - by_name.keys()
        if missing:
            raise ValueError(f"no value supplied for: {', '.join(sorted(missing))}")
        return self.text.format(**by_name)


@dataclass(frozen=True, slots=True)
class Variation:
    """One design's position along the style axes."""

    values: MappingProxyType[StyleAxis, str]

    def __init__(self, values: dict[StyleAxis, str]) -> None:
        cleaned = {axis: value.strip() for axis, value in values.items()}
        if not cleaned:
            raise ValueError("a variation must set at least one axis")
        for axis, value in cleaned.items():
            if not value:
                raise ValueError(f"{axis.value} cannot be blank")
        object.__setattr__(self, "values", MappingProxyType(cleaned))

    @property
    def fingerprint(self) -> tuple[tuple[str, str], ...]:
        """Identity by content, so two variations that say the same thing in a
        different order are recognised as the same design."""
        return tuple(sorted((axis.value, value.lower()) for axis, value in self.values.items()))

    def __hash__(self) -> int:
        return hash(self.fingerprint)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Variation) and self.fingerprint == other.fingerprint


@dataclass(frozen=True, slots=True)
class VariationSet:
    """The prompts one niche will produce, checked for genuine variety."""

    variations: tuple[Variation, ...]

    def __post_init__(self) -> None:
        if not self.variations:
            raise ValueError("a variation set needs at least one variation")
        if len(self.variations) > MAX_VARIATIONS_PER_SET:
            raise TemplatedBulkGenerationError(
                f"{len(self.variations)} variations exceeds {MAX_VARIATIONS_PER_SET} for one "
                "niche — volume from a single direction is what bulk-generation detection "
                "looks for"
            )
        fingerprints = {variation.fingerprint for variation in self.variations}
        if len(fingerprints) != len(self.variations):
            raise TemplatedBulkGenerationError(
                "two variations are identical — that is the same design listed twice"
            )
        if len(self.variations) > 1 and len(self.varied_axes) < MIN_DISTINCT_AXES:
            raise TemplatedBulkGenerationError(
                f"variations differ along only {len(self.varied_axes)} axis — a set that "
                f"changes one thing is a template with a swapped word. Vary at least "
                f"{MIN_DISTINCT_AXES}."
            )

    @property
    def varied_axes(self) -> frozenset[StyleAxis]:
        """Axes on which the set actually takes more than one value."""
        return frozenset(
            axis
            for axis in StyleAxis
            if len({v.values.get(axis) for v in self.variations if axis in v.values}) > 1
        )

    def __len__(self) -> int:
        return len(self.variations)
