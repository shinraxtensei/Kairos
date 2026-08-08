"""SQLAlchemy persistence for GeneratedAsset."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from kairos.content_generation.domain.generated_asset import GeneratedAsset
from kairos.content_generation.domain.value_objects import (
    AssetFormat,
    AssetVariant,
    DeliveryFile,
    DeliveryPackage,
    GenerationFailure,
    PrintSpecification,
    ProcessingStage,
)
from kairos.content_generation.infrastructure.models import GeneratedAssetRecord
from kairos.shared_kernel.money import Money


def _to_domain(record: GeneratedAssetRecord) -> GeneratedAsset:
    delivery = None
    if record.delivery_files:
        # Rebuilt through the real value objects, so a row that violates Etsy's
        # limits fails here rather than at upload.
        delivery = DeliveryPackage(
            tuple(
                DeliveryFile(f["filename"], f["size_bytes"], AssetFormat(f["format"]))
                for f in record.delivery_files
            )
        )
    return GeneratedAsset(
        asset_id=record.asset_id,
        niche_keyword=record.niche_keyword,
        variant=AssetVariant(index=record.variant_index, seed=record.seed),
        stage=ProcessingStage(record.stage),
        print_spec=(PrintSpecification(**record.print_spec) if record.print_spec else None),
        delivery=delivery,
        generation_cost=(
            Money(Decimal(str(record.cost_amount)), record.cost_currency)
            if record.cost_amount is not None and record.cost_currency
            else None
        ),
        failure=GenerationFailure(record.failure) if record.failure else None,
        created_at=record.created_at,
    )


class SqlAlchemyGeneratedAssetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, asset: GeneratedAsset) -> None:
        row = {
            "asset_id": asset.asset_id,
            "niche_keyword": asset.niche_keyword,
            "variant_index": asset.variant.index,
            "seed": asset.variant.seed,
            "stage": asset.stage.value,
            "failure": asset.failure.value if asset.failure else None,
            "cost_amount": asset.generation_cost.amount if asset.generation_cost else None,
            "cost_currency": asset.generation_cost.currency if asset.generation_cost else None,
            "print_spec": (
                {
                    "width_inches": asset.print_spec.width_inches,
                    "height_inches": asset.print_spec.height_inches,
                    "dpi": asset.print_spec.dpi,
                }
                if asset.print_spec
                else None
            ),
            "delivery_files": (
                [
                    {
                        "filename": f.filename,
                        "size_bytes": f.size_bytes,
                        "format": f.asset_format.value,
                    }
                    for f in asset.delivery.files
                ]
                if asset.delivery
                else None
            ),
            "created_at": asset.created_at,
        }
        statement = insert(GeneratedAssetRecord).values([row])
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["asset_id"],
                set_={
                    key: statement.excluded[key]
                    for key in ("stage", "failure", "print_spec", "delivery_files")
                },
            )
        )
        self._session.commit()

    def get(self, asset_id: UUID) -> GeneratedAsset | None:
        record = self._session.get(GeneratedAssetRecord, asset_id)
        return _to_domain(record) if record else None

    def awaiting_review(self, *, limit: int = 100) -> Sequence[GeneratedAsset]:
        """Packaged, unfailed assets, oldest first.

        Oldest first on purpose: a niche's momentum decays, so the queue should
        drain in the order designs were made rather than showing the newest.
        """
        query = (
            select(GeneratedAssetRecord)
            .where(
                GeneratedAssetRecord.stage == ProcessingStage.PACKAGED.value,
                GeneratedAssetRecord.failure.is_(None),
            )
            .order_by(GeneratedAssetRecord.created_at)
            .limit(limit)
        )
        return [_to_domain(row) for row in self._session.scalars(query)]
