"""SQLAlchemy implementation of StyleGuideRepository."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from kairos.creative_direction.domain.ports import StyleGuideRepository
from kairos.creative_direction.domain.style_guide import StyleGuide
from kairos.creative_direction.domain.value_objects import (
    PromptTemplate,
    StyleAxis,
    Variation,
    VariationSet,
)
from kairos.creative_direction.infrastructure.models import StyleGuideRecord

# One niche, one style guide — so the id derives from the keyword and a
# re-definition updates in place rather than leaving a rival direction behind,
# each generating its own paid designs.
GUIDE_NAMESPACE = uuid5(NAMESPACE_URL, "https://kairos.local/style-guide")


def _to_domain(record: StyleGuideRecord) -> StyleGuide:
    # Rebuilt through the real value objects, so a row that violates the
    # originality rules fails loudly here instead of generating designs that
    # Etsy would remove as templated bulk output.
    variations = VariationSet(
        tuple(
            Variation({StyleAxis(axis): value for axis, value in entry.items()})
            for entry in record.variations
        )
    )
    return StyleGuide(
        style_guide_id=record.style_guide_id,
        niche_keyword=record.niche_keyword,
        template=PromptTemplate(record.template),
        variations=variations,
        created_at=record.created_at,
    )


class SqlAlchemyStyleGuideRepository(StyleGuideRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, guide: StyleGuide) -> None:
        row = {
            "style_guide_id": guide.style_guide_id,
            "niche_keyword": guide.niche_keyword,
            "template": guide.template.text,
            "variations": [
                {axis.value: value for axis, value in variation.values.items()}
                for variation in guide.variations.variations
            ],
            "created_at": guide.created_at,
        }
        statement = insert(StyleGuideRecord).values([row])
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["style_guide_id"],
                set_={
                    "template": statement.excluded.template,
                    "variations": statement.excluded.variations,
                },
            )
        )
        self._session.commit()

    def for_niche(self, niche_keyword: str) -> StyleGuide | None:
        record = self._session.scalars(
            select(StyleGuideRecord).where(
                StyleGuideRecord.niche_keyword == niche_keyword.strip().lower()
            )
        ).first()
        return _to_domain(record) if record else None

    def recent(self, *, limit: int = 50) -> Sequence[StyleGuide]:
        query = select(StyleGuideRecord).order_by(StyleGuideRecord.created_at.desc()).limit(limit)
        return [_to_domain(row) for row in self._session.scalars(query)]
