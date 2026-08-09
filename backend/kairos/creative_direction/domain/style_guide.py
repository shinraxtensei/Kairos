"""The StyleGuide aggregate — the visual direction for one shortlisted niche."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from kairos.creative_direction.domain.events import PromptSetGenerated, StyleGuideDrafted
from kairos.creative_direction.domain.value_objects import (
    PromptTemplate,
    StyleAxis,
    VariationSet,
)

StyleGuideEvent = StyleGuideDrafted | PromptSetGenerated


@dataclass(eq=False, slots=True)
class StyleGuide:
    style_guide_id: UUID
    niche_keyword: str
    template: PromptTemplate
    variations: VariationSet
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    events: list[StyleGuideEvent] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.niche_keyword.strip():
            raise ValueError("a style guide belongs to a niche")
        # Every slot the template asks for must be supplied by every variation,
        # or rendering fails halfway through a paid run.
        for index, variation in enumerate(self.variations.variations):
            missing = self.template.slots - {axis.value for axis in variation.values}
            if missing:
                raise ValueError(
                    f"variation {index} supplies no value for: {', '.join(sorted(missing))}"
                )

    @classmethod
    def define(
        cls,
        *,
        niche_keyword: str,
        template: PromptTemplate,
        variations: VariationSet,
        style_guide_id: UUID | None = None,
    ) -> StyleGuide:
        guide = cls(
            style_guide_id=style_guide_id or uuid4(),
            niche_keyword=niche_keyword.strip().lower(),
            template=template,
            variations=variations,
        )
        guide.events.append(
            StyleGuideDrafted(
                style_guide_id=guide.style_guide_id, niche_keyword=guide.niche_keyword
            )
        )
        return guide

    def generate_prompt_set(self) -> list[str]:
        """Render one prompt per variation, and announce the run's size.

        The count travels on the event so Budgeting can price the whole run
        before the first paid call, rather than discovering the total halfway
        through it.
        """
        prompts = [
            self.template.render(dict(variation.values)) for variation in self.variations.variations
        ]
        self.events.append(
            PromptSetGenerated(
                style_guide_id=self.style_guide_id,
                niche_keyword=self.niche_keyword,
                variation_count=len(prompts),
                varied_axes=tuple(sorted(axis.value for axis in self.variations.varied_axes)),
            )
        )
        return prompts

    @property
    def varied_axes(self) -> frozenset[StyleAxis]:
        return self.variations.varied_axes

    def pull_events(self) -> list[StyleGuideEvent]:
        drained, self.events = self.events, []
        return drained

    def __eq__(self, other: object) -> bool:
        return isinstance(other, StyleGuide) and self.style_guide_id == other.style_guide_id

    def __hash__(self) -> int:
        return hash(self.style_guide_id)
