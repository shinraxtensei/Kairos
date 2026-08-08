"""Value objects for Content Generation.

Includes the asset-packaging concern the original domain model missed (R2):
there was no step between "approved design" and "a file Etsy will actually
accept", and Etsy's digital-listing limits are tight enough that print-resolution
output routinely violates them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, auto

# Etsy digital listing limits. Verified against Etsy's seller help — recheck if
# uploads start failing, since these are product policy and can move.
MAX_FILES_PER_LISTING = 5
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILENAME_LENGTH = 70

# Below this, a print looks soft at any useful size. 300 is the industry floor
# for print, not a preference.
MIN_PRINT_DPI = 300


class AssetFormat(StrEnum):
    PNG = "png"
    JPEG = "jpeg"


class ProcessingStage(StrEnum):
    """Ordered. An asset moves forward one step at a time and never backward."""

    GENERATED = "generated"
    BACKGROUND_REMOVED = "background_removed"
    UPSCALED = "upscaled"
    PACKAGED = "packaged"


_STAGE_ORDER = list(ProcessingStage)


def stage_follows(current: ProcessingStage, nxt: ProcessingStage) -> bool:
    return _STAGE_ORDER.index(nxt) == _STAGE_ORDER.index(current) + 1


class GenerationFailure(StrEnum):
    PROVIDER_ERROR = auto()
    CONTENT_FILTER = auto()
    TIMEOUT = auto()
    BUDGET_EXHAUSTED = auto()


@dataclass(frozen=True, slots=True)
class AssetVariant:
    """One variation request within a set. `seed` makes a result reproducible."""

    index: int
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("variant index cannot be negative")


@dataclass(frozen=True, slots=True)
class PrintSpecification:
    """Physical print size plus resolution. Pixel dimensions follow from these."""

    width_inches: float
    height_inches: float
    dpi: int = MIN_PRINT_DPI

    def __post_init__(self) -> None:
        if self.width_inches <= 0 or self.height_inches <= 0:
            raise ValueError("print dimensions must be positive")
        if self.dpi < MIN_PRINT_DPI:
            raise ValueError(f"print output must be at least {MIN_PRINT_DPI} DPI, got {self.dpi}")

    @property
    def pixel_width(self) -> int:
        return round(self.width_inches * self.dpi)

    @property
    def pixel_height(self) -> int:
        return round(self.height_inches * self.dpi)

    @property
    def megapixels(self) -> float:
        return self.pixel_width * self.pixel_height / 1_000_000


@dataclass(frozen=True, slots=True)
class DeliveryFile:
    """One file as the buyer will download it.

    The size limit is the trap. An 18x24" poster at 300 DPI is ~38 megapixels;
    as PNG that is comfortably over Etsy's 20MB ceiling, while the same image as
    quality JPEG lands well under it. The rule lives here so the failure happens
    at packaging time rather than at upload, after generation has been paid for.
    """

    filename: str
    size_bytes: int
    asset_format: AssetFormat

    def __post_init__(self) -> None:
        if not self.filename.strip():
            raise ValueError("a delivery file needs a filename")
        if len(self.filename) > MAX_FILENAME_LENGTH:
            raise ValueError(
                f"filename exceeds Etsy's {MAX_FILENAME_LENGTH}-character limit: {self.filename!r}"
            )
        if self.size_bytes <= 0:
            raise ValueError("a delivery file cannot be empty")
        if self.size_bytes > MAX_FILE_BYTES:
            raise ValueError(
                f"file {self.filename!r} is {self.size_bytes / 1_048_576:.1f}MB, over Etsy's "
                f"{MAX_FILE_BYTES // 1_048_576}MB per-file limit — "
                "consider JPEG rather than PNG at print resolution"
            )


@dataclass(frozen=True, slots=True)
class DeliveryPackage:
    """What gets attached to the listing. Etsy allows at most five files."""

    files: tuple[DeliveryFile, ...]

    def __post_init__(self) -> None:
        if not self.files:
            raise ValueError("a delivery package needs at least one file")
        if len(self.files) > MAX_FILES_PER_LISTING:
            raise ValueError(
                f"{len(self.files)} files exceeds Etsy's limit of {MAX_FILES_PER_LISTING}"
            )
        names = [file.filename for file in self.files]
        if len(set(names)) != len(names):
            raise ValueError("delivery filenames must be unique within a package")

    @property
    def total_bytes(self) -> int:
        return sum(file.size_bytes for file in self.files)
