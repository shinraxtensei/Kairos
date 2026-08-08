"""Content Generation domain tests. Pure, no mocks, no I/O."""

from decimal import Decimal

import pytest

from kairos.content_generation.domain.events import AssetGenerated
from kairos.content_generation.domain.generated_asset import (
    GeneratedAsset,
    ProcessingOrderError,
)
from kairos.content_generation.domain.value_objects import (
    MAX_FILE_BYTES,
    AssetFormat,
    AssetVariant,
    DeliveryFile,
    DeliveryPackage,
    GenerationFailure,
    PrintSpecification,
    ProcessingStage,
)
from kairos.shared_kernel.money import Money

MB = 1024 * 1024


def _file(name: str = "poster.jpg", size: int = 5 * MB) -> DeliveryFile:
    return DeliveryFile(name, size, AssetFormat.JPEG)


def _asset() -> GeneratedAsset:
    return GeneratedAsset.generated(
        niche_keyword="moon phase print",
        variant=AssetVariant(index=0, seed=42),
        cost=Money.of("0.04", "USD"),
    )


class TestPrintSpecification:
    def test_given_inches_and_dpi_when_asked_then_computes_pixels(self) -> None:
        spec = PrintSpecification(18, 24, 300)
        assert (spec.pixel_width, spec.pixel_height) == (5400, 7200)
        assert round(spec.megapixels) == 39

    def test_given_below_print_dpi_when_built_then_raises(self) -> None:
        # 72 DPI looks fine on screen and terrible on paper.
        with pytest.raises(ValueError, match="at least 300 DPI"):
            PrintSpecification(18, 24, 72)

    @pytest.mark.parametrize(("width", "height"), [(0, 24), (18, 0), (-1, 24)])
    def test_given_non_positive_dimensions_when_built_then_raises(
        self, width: float, height: float
    ) -> None:
        with pytest.raises(ValueError, match="positive"):
            PrintSpecification(width, height)


class TestDeliveryFile:
    def test_given_a_file_over_20mb_when_built_then_raises_suggesting_jpeg(self) -> None:
        """The R2 gap made concrete.

        An 18x24" poster at 300 DPI is ~39 megapixels. As PNG that clears
        Etsy's 20MB ceiling comfortably; as JPEG it does not. Catching it here
        means the failure happens at packaging, not at upload — after the
        generation has already been paid for.
        """
        with pytest.raises(ValueError, match="over Etsy's 20MB per-file limit"):
            DeliveryFile("poster.png", MAX_FILE_BYTES + 1, AssetFormat.PNG)

    def test_given_a_file_at_exactly_the_limit_when_built_then_allowed(self) -> None:
        assert DeliveryFile("poster.jpg", MAX_FILE_BYTES, AssetFormat.JPEG)

    def test_given_an_overlong_filename_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="70-character limit"):
            DeliveryFile("a" * 71 + ".jpg", MB, AssetFormat.JPEG)

    def test_given_an_empty_file_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            DeliveryFile("poster.jpg", 0, AssetFormat.JPEG)


class TestDeliveryPackage:
    def test_given_six_files_when_built_then_raises(self) -> None:
        files = tuple(_file(f"page{i}.jpg") for i in range(6))
        with pytest.raises(ValueError, match="exceeds Etsy's limit of 5"):
            DeliveryPackage(files)

    def test_given_five_files_when_built_then_allowed(self) -> None:
        package = DeliveryPackage(tuple(_file(f"page{i}.jpg") for i in range(5)))
        assert package.total_bytes == 5 * 5 * MB

    def test_given_duplicate_filenames_when_built_then_raises(self) -> None:
        # Etsy shows the buyer filenames; two identical ones is a support ticket.
        with pytest.raises(ValueError, match="unique"):
            DeliveryPackage((_file("a.jpg"), _file("a.jpg")))

    def test_given_no_files_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one file"):
            DeliveryPackage(())


class TestProcessingOrder:
    def test_given_a_new_asset_when_created_then_it_is_generated_and_not_reviewable(self) -> None:
        asset = _asset()
        assert asset.stage is ProcessingStage.GENERATED
        assert not asset.is_ready_for_review

    def test_given_the_full_pipeline_when_run_then_it_becomes_reviewable(self) -> None:
        asset = _asset()
        asset.advance_to(ProcessingStage.BACKGROUND_REMOVED)
        asset.advance_to(ProcessingStage.UPSCALED)
        asset.package(DeliveryPackage((_file(),)), PrintSpecification(18, 24))
        assert asset.is_ready_for_review

    def test_given_a_skipped_stage_when_advanced_then_raises(self) -> None:
        """Upscaling before background removal bakes the background into the
        print at full resolution — expensive and unfixable."""
        asset = _asset()
        with pytest.raises(ProcessingOrderError, match="stages run in order"):
            asset.advance_to(ProcessingStage.UPSCALED)

    def test_given_a_repeated_stage_when_advanced_then_raises(self) -> None:
        asset = _asset()
        asset.advance_to(ProcessingStage.BACKGROUND_REMOVED)
        with pytest.raises(ProcessingOrderError):
            asset.advance_to(ProcessingStage.BACKGROUND_REMOVED)

    def test_given_packaging_via_advance_to_when_called_then_raises(self) -> None:
        # Packaging must carry the files, so it cannot go through advance_to.
        asset = _asset()
        asset.advance_to(ProcessingStage.BACKGROUND_REMOVED)
        asset.advance_to(ProcessingStage.UPSCALED)
        with pytest.raises(ProcessingOrderError, match="use package"):
            asset.advance_to(ProcessingStage.PACKAGED)

    def test_given_an_unupscaled_asset_when_packaged_then_raises(self) -> None:
        with pytest.raises(ProcessingOrderError, match="upscale first"):
            _asset().package(DeliveryPackage((_file(),)), PrintSpecification(18, 24))


class TestFailure:
    def test_given_a_failed_asset_when_advanced_then_raises(self) -> None:
        asset = _asset()
        asset.fail(GenerationFailure.CONTENT_FILTER)
        with pytest.raises(ProcessingOrderError, match="cannot be processed further"):
            asset.advance_to(ProcessingStage.BACKGROUND_REMOVED)

    def test_given_a_failed_asset_when_checked_then_never_reviewable(self) -> None:
        asset = _asset()
        asset.fail(GenerationFailure.PROVIDER_ERROR, "502 from provider")
        assert not asset.is_ready_for_review


class TestCost:
    def test_given_a_cost_when_generated_then_it_travels_on_the_event(self) -> None:
        asset = _asset()
        (event,) = asset.pull_events()
        assert isinstance(event, AssetGenerated)
        assert event.cost_amount == "0.04"
        assert event.cost_currency == "USD"

    def test_given_a_run_of_variants_when_summed_then_cost_is_exact(self) -> None:
        # Cost per *winning* design is 20-100 of these, so the arithmetic that
        # feeds the budget cap has to be exact (CONTEXT.md §6).
        total = sum((Money.of("0.04", "USD") for _ in range(50)), start=Money.zero("USD"))
        assert total == Money.of("2.00", "USD")
        assert total.amount == Decimal("2.00")

    def test_given_no_niche_when_generated_then_raises(self) -> None:
        with pytest.raises(ValueError, match="which niche"):
            GeneratedAsset.generated(niche_keyword="  ", variant=AssetVariant(0))
