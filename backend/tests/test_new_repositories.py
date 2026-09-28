"""Persistence for the three tables that had schema but no mapping code.

Before this, `style_guides`, `listing_drafts` and `listings` existed in Postgres
and in the migrations, and nothing in the application could read or write them —
dead schema that looked finished.

Lives in the shared tests/ root because it touches three contexts, and none of
them may import the others.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from kairos.creative_direction.domain.style_guide import StyleGuide
from kairos.creative_direction.domain.value_objects import (
    PromptTemplate,
    StyleAxis,
    TemplatedBulkGenerationError,
    Variation,
    VariationSet,
)
from kairos.creative_direction.infrastructure.models import StyleGuideRecord
from kairos.creative_direction.infrastructure.repository import (
    SqlAlchemyStyleGuideRepository,
)
from kairos.db import Base, SessionLocal, engine
from kairos.fulfillment.domain.listing import Listing, PublishResult, PublishState
from kairos.fulfillment.infrastructure.models import ListingRecord
from kairos.fulfillment.infrastructure.repository import SqlAlchemyListingRepository
from kairos.listing_authoring.domain.listing_draft import ListingDraft
from kairos.listing_authoring.domain.value_objects import (
    AIDisclosure,
    ListingCopy,
    PricingRule,
)
from kairos.listing_authoring.infrastructure.models import ListingDraftRecord
from kairos.listing_authoring.infrastructure.repository import (
    SqlAlchemyListingDraftRepository,
)
from kairos.shared_kernel.money import Money

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
    )
)

COPY = ListingCopy(
    title="Moon Phase Print — Printable Wall Art",
    tags=("moon phase", "wall art", "printable"),
    description="A printable moon phase poster for boho interiors. Instant download.",
)
DISCLOSURE = AIDisclosure(
    seller_name="Kairos Studio",
    tool_summary="Artwork developed with AI image tools and curated by hand.",
)
PRICING = PricingRule(Money(Decimal("6.00"), "USD"))


@pytest.fixture(scope="module", autouse=True)
def _require_database() -> None:
    try:
        with engine.connect():
            pass
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"postgres unavailable: {type(exc).__name__}")
    Base.metadata.create_all(engine)


@pytest.fixture
def session() -> Iterator[Session]:
    with SessionLocal() as session:
        session.query(ListingRecord).delete()
        session.query(ListingDraftRecord).delete()
        session.query(StyleGuideRecord).delete()
        session.commit()
        yield session


class TestStyleGuideRepository:
    def test_given_a_guide_when_saved_then_it_round_trips(self, session: Session) -> None:
        repository = SqlAlchemyStyleGuideRepository(session)
        guide = StyleGuide.define(
            niche_keyword="moon phase print", template=TEMPLATE, variations=VARIED
        )

        repository.save(guide)
        loaded = repository.for_niche("Moon Phase Print")

        assert loaded is not None
        assert loaded.niche_keyword == "moon phase print"
        assert loaded.template.text == TEMPLATE.text
        assert len(loaded.variations) == 2
        assert loaded.varied_axes == guide.varied_axes

    def test_given_a_redefined_niche_when_saved_then_it_replaces(self, session: Session) -> None:
        """One niche, one direction. Two rival guides would each generate their
        own paid designs for the same keyword."""
        repository = SqlAlchemyStyleGuideRepository(session)
        guide = StyleGuide.define(
            niche_keyword="moon phase print", template=TEMPLATE, variations=VARIED
        )
        repository.save(guide)

        revised = StyleGuide.define(
            niche_keyword="moon phase print",
            template=TEMPLATE,
            variations=VariationSet(
                (
                    _variation("bold", "neon", "off-centre"),
                    _variation("soft", "sepia", "grid of phases"),
                )
            ),
            style_guide_id=guide.style_guide_id,
        )
        repository.save(revised)

        assert len(repository.recent()) == 1
        loaded = repository.for_niche("moon phase print")
        assert loaded is not None
        assert "bold" in str(loaded.variations.variations[0].values.values())

    def test_given_a_row_violating_originality_when_loaded_then_raises(
        self, session: Session
    ) -> None:
        """A tampered row must not rehydrate into a prompt set that Etsy would
        remove as templated bulk output."""
        repository = SqlAlchemyStyleGuideRepository(session)
        repository.save(
            StyleGuide.define(
                niche_keyword="moon phase print", template=TEMPLATE, variations=VARIED
            )
        )
        record = session.query(StyleGuideRecord).one()
        record.variations = [
            {"mood": "serene", "palette": "pastel", "composition": "centred"},
            {"mood": "dreamy", "palette": "pastel", "composition": "centred"},
        ]
        session.commit()

        with pytest.raises(TemplatedBulkGenerationError):
            repository.for_niche("moon phase print")

    def test_given_no_guide_when_asked_then_none(self, session: Session) -> None:
        assert SqlAlchemyStyleGuideRepository(session).for_niche("nothing") is None


class TestListingDraftRepository:
    def _draft(self, asset_id: object = None) -> ListingDraft:
        return ListingDraft.draft(
            asset_id=asset_id or uuid4(),  # type: ignore[arg-type]
            copy=COPY,
            disclosure=DISCLOSURE,
            pricing=PRICING,
        )

    def test_given_a_draft_when_saved_then_it_round_trips(self, session: Session) -> None:
        repository = SqlAlchemyListingDraftRepository(session)
        draft = self._draft()

        repository.save(draft)
        loaded = repository.for_asset(draft.asset_id)

        assert loaded is not None
        assert loaded.copy.title == COPY.title
        assert loaded.copy.tags == COPY.tags
        assert loaded.pricing.price == Money(Decimal("6.00"), "USD")

    def test_given_a_saved_draft_when_reloaded_then_the_disclosure_survives(
        self, session: Session
    ) -> None:
        """The disclosure a listing went live with is an audit record.

        Re-deriving it from today's config would rewrite history, so it is
        stored and must come back exactly.
        """
        repository = SqlAlchemyListingDraftRepository(session)
        draft = self._draft()
        repository.save(draft)

        loaded = repository.for_asset(draft.asset_id)

        assert loaded is not None
        assert loaded.disclosure.attribution == "Designed by Kairos Studio"
        assert "Made by" not in loaded.disclosure.as_listing_text()

    def test_given_the_same_asset_drafted_twice_then_there_is_one_draft(
        self, session: Session
    ) -> None:
        """Two drafts for one asset would each become a separate paid listing."""
        repository = SqlAlchemyListingDraftRepository(session)
        asset_id = uuid4()

        repository.save(self._draft(asset_id))
        repository.save(self._draft(asset_id))

        assert len(repository.recent()) == 1

    def test_given_no_draft_when_asked_then_none(self, session: Session) -> None:
        assert SqlAlchemyListingDraftRepository(session).for_asset(uuid4()) is None


class TestListingRepository:
    def _listing(self, draft_id: object = None) -> Listing:
        return Listing.pending(
            draft_id=draft_id or uuid4(),  # type: ignore[arg-type]
            asset_id=uuid4(),
            title="Moon Phase Print",
            channel_name="etsy",
        )

    def test_given_a_published_listing_when_saved_then_it_round_trips(
        self, session: Session
    ) -> None:
        repository = SqlAlchemyListingRepository(session)
        listing = self._listing()
        listing.record_published(PublishResult(external_id="etsy-1", external_url="http://x"))

        repository.save(listing)
        loaded = repository.for_draft(listing.draft_id)

        assert loaded is not None
        assert loaded.state is PublishState.PUBLISHED
        assert loaded.external_id == "etsy-1"
        assert loaded.attempts == 1
        assert loaded.published_at is not None

    def test_given_a_retried_publish_when_saved_then_it_updates_in_place(
        self, session: Session
    ) -> None:
        """ENG-34 at the storage layer: a retry must not create a second row."""
        repository = SqlAlchemyListingRepository(session)
        draft_id = uuid4()

        failed = self._listing(draft_id)
        failed.record_failure("ConnectionError: etsy 503")
        repository.save(failed)

        retried = repository.for_draft(draft_id)
        assert retried is not None
        retried.record_published(PublishResult(external_id="etsy-9"))
        repository.save(retried)

        assert len(repository.live()) == 1
        loaded = repository.for_draft(draft_id)
        assert loaded is not None
        assert loaded.state is PublishState.PUBLISHED
        assert loaded.attempts == 2

    def test_given_a_failed_listing_when_live_is_asked_then_it_is_excluded(
        self, session: Session
    ) -> None:
        repository = SqlAlchemyListingRepository(session)
        failed = self._listing()
        failed.record_failure("boom")
        repository.save(failed)

        assert repository.live() == []

    def test_given_no_listing_when_asked_then_none(self, session: Session) -> None:
        assert SqlAlchemyListingRepository(session).for_draft(uuid4()) is None
