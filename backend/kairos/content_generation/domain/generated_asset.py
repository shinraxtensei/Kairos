"""The GeneratedAsset aggregate — one design and its processing state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from kairos.content_generation.domain.events import (
    AssetGenerated,
    AssetGenerationFailed,
    AssetPackaged,
    AssetProcessed,
)
from kairos.content_generation.domain.value_objects import (
    AssetVariant,
    DeliveryPackage,
    GenerationFailure,
    PrintSpecification,
    ProcessingStage,
    stage_follows,
)
from kairos.shared_kernel.money import Money

AssetEvent = AssetGenerated | AssetProcessed | AssetPackaged | AssetGenerationFailed


class ProcessingOrderError(RuntimeError):
    """A stage was skipped or repeated. Upscaling before background removal
    bakes the background into the print at full resolution."""


@dataclass(eq=False, slots=True)
class GeneratedAsset:
    asset_id: UUID
    niche_keyword: str
    variant: AssetVariant
    stage: ProcessingStage = ProcessingStage.GENERATED
    print_spec: PrintSpecification | None = None
    delivery: DeliveryPackage | None = None
    # Recorded per asset because the number that matters is cost per *winning*
    # design — roughly 20-100 of these — not cost per image (CONTEXT.md §6).
    generation_cost: Money | None = None
    failure: GenerationFailure | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    events: list[AssetEvent] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.niche_keyword.strip():
            raise ValueError("a generated asset must know which niche it belongs to")

    @classmethod
    def generated(
        cls,
        *,
        niche_keyword: str,
        variant: AssetVariant,
        cost: Money | None = None,
        asset_id: UUID | None = None,
    ) -> GeneratedAsset:
        asset = cls(
            asset_id=asset_id or uuid4(),
            niche_keyword=niche_keyword.strip().lower(),
            variant=variant,
            generation_cost=cost,
        )
        asset.events.append(
            AssetGenerated(
                asset_id=asset.asset_id,
                niche_keyword=asset.niche_keyword,
                variant_index=variant.index,
                cost_amount=str(cost.amount) if cost else None,
                cost_currency=cost.currency if cost else None,
            )
        )
        return asset

    @property
    def is_failed(self) -> bool:
        return self.failure is not None

    @property
    def is_ready_for_review(self) -> bool:
        """Curation only sees finished assets (CONTEXT.md §4.4 policy)."""
        return self.stage is ProcessingStage.PACKAGED and not self.is_failed

    def advance_to(self, stage: ProcessingStage) -> None:
        self._guard_not_failed()
        if not stage_follows(self.stage, stage):
            raise ProcessingOrderError(
                f"cannot go from {self.stage.value} to {stage.value} — stages run in order"
            )
        if stage is ProcessingStage.PACKAGED:
            raise ProcessingOrderError("use package() so the delivery files are recorded")
        self.stage = stage
        self.events.append(AssetProcessed(asset_id=self.asset_id, stage=stage))

    def package(self, package: DeliveryPackage, print_spec: PrintSpecification) -> None:
        """Final step. Carries the files Etsy will actually receive."""
        self._guard_not_failed()
        if not stage_follows(self.stage, ProcessingStage.PACKAGED):
            raise ProcessingOrderError(f"cannot package from {self.stage.value} — upscale first")
        self.delivery = package
        self.print_spec = print_spec
        self.stage = ProcessingStage.PACKAGED
        self.events.append(
            AssetPackaged(
                asset_id=self.asset_id,
                file_count=len(package.files),
                total_bytes=package.total_bytes,
            )
        )

    def fail(self, reason: GenerationFailure, detail: str = "") -> None:
        self.failure = reason
        self.events.append(
            AssetGenerationFailed(asset_id=self.asset_id, reason=reason, detail=detail)
        )

    def _guard_not_failed(self) -> None:
        if self.is_failed:
            raise ProcessingOrderError(
                f"asset {self.asset_id} failed with {self.failure} and cannot be processed further"
            )

    def pull_events(self) -> list[AssetEvent]:
        drained, self.events = self.events, []
        return drained

    def __eq__(self, other: object) -> bool:
        return isinstance(other, GeneratedAsset) and self.asset_id == other.asset_id

    def __hash__(self) -> int:
        return hash(self.asset_id)
