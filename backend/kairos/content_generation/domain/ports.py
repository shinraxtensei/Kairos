"""Ports for Content Generation.

One port per capability rather than one fat ImageService, so the paid pieces
(generation, upscaling) can be swapped or switched off independently of the free
one (rembg, run locally).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from kairos.content_generation.domain.generated_asset import GeneratedAsset
from kairos.content_generation.domain.value_objects import AssetVariant, PrintSpecification


class ImageGeneratorError(RuntimeError):
    """Vendor failures are translated to this at the adapter boundary."""


class ImageGenerator(ABC):
    """DEC-02 picks the implementation. FLUX.1 [dev] is disqualified — its
    licence forbids commercial use, and every design here is sold."""

    @property
    @abstractmethod
    def cost_per_image(self) -> str:
        """Decimal string, so Budgeting can price a run before starting it."""

    @abstractmethod
    def generate(self, prompt: str, variant: AssetVariant) -> GeneratedAsset: ...


class BackgroundRemover(ABC):
    @abstractmethod
    def remove_background(self, asset: GeneratedAsset) -> GeneratedAsset: ...


class Upscaler(ABC):
    @abstractmethod
    def upscale(self, asset: GeneratedAsset, target: PrintSpecification) -> GeneratedAsset: ...
