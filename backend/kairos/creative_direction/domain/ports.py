"""Ports for Creative Direction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from kairos.creative_direction.domain.style_guide import StyleGuide


class StyleGuideRepository(ABC):
    @abstractmethod
    def save(self, guide: StyleGuide) -> None: ...

    @abstractmethod
    def for_niche(self, niche_keyword: str) -> StyleGuide | None:
        """The current direction for a niche, if one has been defined.

        One niche has one style guide: re-defining replaces it rather than
        accumulating rival directions that would each generate their own designs.
        """

    @abstractmethod
    def recent(self, *, limit: int = 50) -> Sequence[StyleGuide]: ...
