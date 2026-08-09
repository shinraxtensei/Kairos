"""Creative Direction domain tests. Pure, no mocks, no I/O.

The originality rules are the point. Etsy removed roughly 12,000 listings in a
single quarter, and templated bulk generation is one of the patterns that gets
a whole shop taken down at once rather than one listing at a time.
"""

import pytest

from kairos.creative_direction.domain.events import PromptSetGenerated, StyleGuideDrafted
from kairos.creative_direction.domain.style_guide import StyleGuide
from kairos.creative_direction.domain.value_objects import (
    MAX_VARIATIONS_PER_SET,
    PromptTemplate,
    StyleAxis,
    TemplatedBulkGenerationError,
    Variation,
    VariationSet,
)

TEMPLATE = PromptTemplate("a {mood} {palette} moon phase poster, {composition}")


def _variation(mood: str, palette: str, composition: str) -> Variation:
    return Variation(
        {
            StyleAxis.MOOD: mood,
            StyleAxis.PALETTE: palette,
            StyleAxis.COMPOSITION: composition,
        }
    )


VARIED = VariationSet(
    (
        _variation("serene", "muted earth tones", "centred single moon"),
        _variation("dramatic", "high contrast monochrome", "diagonal phase sequence"),
        _variation("whimsical", "pastel gradient", "scattered constellation"),
    )
)


class TestPromptTemplate:
    def test_given_a_template_with_slots_when_built_then_lists_them(self) -> None:
        assert TEMPLATE.slots == {"mood", "palette", "composition"}

    def test_given_a_template_with_no_slots_when_built_then_refused(self) -> None:
        """A fixed prompt can only produce one design repeated."""
        with pytest.raises(TemplatedBulkGenerationError, match="repeated"):
            PromptTemplate("a moon phase poster")

    def test_given_an_unknown_slot_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown axes: vibe"):
            PromptTemplate("a {vibe} poster")

    def test_given_values_when_rendered_then_substitutes(self) -> None:
        rendered = TEMPLATE.render(
            {
                StyleAxis.MOOD: "serene",
                StyleAxis.PALETTE: "muted earth tones",
                StyleAxis.COMPOSITION: "centred single moon",
            }
        )
        assert rendered == "a serene muted earth tones moon phase poster, centred single moon"

    def test_given_a_missing_value_when_rendered_then_raises(self) -> None:
        with pytest.raises(ValueError, match="no value supplied for: composition"):
            TEMPLATE.render({StyleAxis.MOOD: "serene", StyleAxis.PALETTE: "pastel"})

    def test_given_a_blank_template_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be blank"):
            PromptTemplate("   ")


class TestOriginality:
    def test_given_genuinely_varied_designs_when_built_then_allowed(self) -> None:
        assert len(VARIED) == 3
        assert VARIED.varied_axes == {
            StyleAxis.MOOD,
            StyleAxis.PALETTE,
            StyleAxis.COMPOSITION,
        }

    def test_given_variations_differing_on_one_axis_when_built_then_refused(self) -> None:
        """The archetypal templated set: one word swapped, everything else the same.

        This is what bulk-generation detection looks for, and it is indefensible
        as original design.
        """
        with pytest.raises(TemplatedBulkGenerationError, match="template with a swapped word"):
            VariationSet(
                (
                    _variation("serene", "pastel gradient", "centred single moon"),
                    _variation("dreamy", "pastel gradient", "centred single moon"),
                    _variation("calm", "pastel gradient", "centred single moon"),
                )
            )

    def test_given_two_identical_variations_when_built_then_refused(self) -> None:
        with pytest.raises(TemplatedBulkGenerationError, match="same design listed twice"):
            VariationSet((_variation("serene", "pastel", "centred"),) * 2)

    def test_given_variations_identical_but_for_case_when_built_then_refused(self) -> None:
        # "Serene" and "serene" are the same creative direction.
        with pytest.raises(TemplatedBulkGenerationError, match="same design listed twice"):
            VariationSet(
                (
                    _variation("serene", "pastel", "centred"),
                    _variation("SERENE", "Pastel", "Centred"),
                )
            )

    def test_given_too_many_variations_for_one_niche_when_built_then_refused(self) -> None:
        """Volume from a single direction is itself the signal."""
        many = tuple(
            _variation(f"mood {i}", f"palette {i}", f"composition {i}")
            for i in range(MAX_VARIATIONS_PER_SET + 1)
        )
        with pytest.raises(TemplatedBulkGenerationError, match="exceeds 12"):
            VariationSet(many)

    def test_given_exactly_the_maximum_when_built_then_allowed(self) -> None:
        many = tuple(
            _variation(f"mood {i}", f"palette {i}", f"composition {i}")
            for i in range(MAX_VARIATIONS_PER_SET)
        )
        assert len(VariationSet(many)) == MAX_VARIATIONS_PER_SET

    def test_given_a_single_variation_when_built_then_allowed(self) -> None:
        # One design is not a bulk pattern, so the multi-axis rule does not apply.
        assert len(VariationSet((_variation("serene", "pastel", "centred"),))) == 1

    def test_given_an_empty_set_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one variation"):
            VariationSet(())

    def test_given_a_blank_axis_value_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="mood cannot be blank"):
            Variation({StyleAxis.MOOD: "  "})


class TestStyleGuide:
    def test_given_a_niche_and_variations_when_defined_then_announces_itself(self) -> None:
        guide = StyleGuide.define(
            niche_keyword="Moon Phase Print", template=TEMPLATE, variations=VARIED
        )
        assert guide.niche_keyword == "moon phase print"
        (event,) = guide.pull_events()
        assert isinstance(event, StyleGuideDrafted)

    def test_given_a_style_guide_when_prompts_generated_then_one_per_variation(self) -> None:
        guide = StyleGuide.define(
            niche_keyword="moon phase print", template=TEMPLATE, variations=VARIED
        )
        guide.pull_events()

        prompts = guide.generate_prompt_set()

        assert len(prompts) == 3
        assert len(set(prompts)) == 3  # and no two are the same string
        assert "serene" in prompts[0]

    def test_given_prompts_generated_then_the_run_size_travels_on_the_event(self) -> None:
        """Budgeting prices the whole run before the first paid call, rather
        than discovering the total halfway through it."""
        guide = StyleGuide.define(
            niche_keyword="moon phase print", template=TEMPLATE, variations=VARIED
        )
        guide.pull_events()
        guide.generate_prompt_set()

        (event,) = guide.pull_events()
        assert isinstance(event, PromptSetGenerated)
        assert event.variation_count == 3
        assert set(event.varied_axes) == {"mood", "palette", "composition"}

    def test_given_a_variation_missing_a_template_slot_when_defined_then_raises(self) -> None:
        """Caught at definition, not halfway through a paid generation run."""
        incomplete = VariationSet(
            (
                Variation({StyleAxis.MOOD: "serene", StyleAxis.PALETTE: "pastel"}),
                Variation({StyleAxis.MOOD: "dramatic", StyleAxis.PALETTE: "monochrome"}),
            )
        )
        with pytest.raises(ValueError, match="supplies no value for: composition"):
            StyleGuide.define(
                niche_keyword="moon phase print", template=TEMPLATE, variations=incomplete
            )

    def test_given_no_niche_when_defined_then_raises(self) -> None:
        with pytest.raises(ValueError, match="belongs to a niche"):
            StyleGuide.define(niche_keyword="  ", template=TEMPLATE, variations=VARIED)
