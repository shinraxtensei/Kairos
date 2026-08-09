"""ENG-34 — publish idempotency. Pure domain plus a fake channel, no I/O.

Etsy charges $0.20 per listing, non-refundable, and `task_acks_late` makes
Celery redelivery normal operation. Every duplicate is real money and a real
duplicate listing on a shop whose originality is already under scrutiny.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest

from kairos.fulfillment.application.publish_listing import PublishListing
from kairos.fulfillment.domain.events import ListingPublished
from kairos.fulfillment.domain.listing import (
    AlreadyPublishedError,
    FulfillmentChannel,
    Listing,
    PublishResult,
    PublishState,
    idempotency_key,
)
from kairos.fulfillment.domain.ports import ListingRepository


class FakeChannel(FulfillmentChannel):
    """Counts publishes, so "was the vendor called" is directly assertable."""

    def __init__(self, *, fails: bool = False) -> None:
        self.calls: list[str] = []
        self._fails = fails

    @property
    def channel_name(self) -> str:
        return "fake_etsy"

    def publish(self, listing: Listing) -> PublishResult:
        self.calls.append(listing.idempotency_key)
        if self._fails:
            raise ConnectionError("etsy 503")
        return PublishResult(external_id=f"etsy-{len(self.calls)}")


class InMemoryListingRepository(ListingRepository):
    def __init__(self) -> None:
        self.by_draft: dict[UUID, Listing] = {}

    def save(self, listing: Listing) -> None:
        self.by_draft[listing.draft_id] = listing

    def for_draft(self, draft_id: UUID) -> Listing | None:
        return self.by_draft.get(draft_id)

    def live(self, *, limit: int = 100) -> Sequence[Listing]:
        return [x for x in self.by_draft.values() if x.is_published][:limit]


def _publish(channel: FakeChannel, repo: InMemoryListingRepository) -> PublishListing:
    return PublishListing(channel, repo)


DRAFT, ASSET = uuid4(), uuid4()


class TestIdempotencyKey:
    def test_given_the_same_draft_when_asked_twice_then_the_key_is_stable(self) -> None:
        """A generated key would be new on every retry, and therefore
        idempotent against nothing."""
        assert idempotency_key(DRAFT) == idempotency_key(DRAFT)

    def test_given_different_drafts_when_asked_then_keys_differ(self) -> None:
        assert idempotency_key(uuid4()) != idempotency_key(uuid4())

    def test_given_a_draft_when_a_listing_is_built_then_its_id_is_derived(self) -> None:
        # A random listing id would let a retry insert a second row before the
        # guard ever looked at it.
        first = Listing.pending(draft_id=DRAFT, asset_id=ASSET, title="t", channel_name="c")
        second = Listing.pending(draft_id=DRAFT, asset_id=ASSET, title="t", channel_name="c")
        assert first.listing_id == second.listing_id


class TestPublishOnce:
    def test_given_a_new_draft_when_published_then_it_goes_live(self) -> None:
        channel, repo = FakeChannel(), InMemoryListingRepository()
        listing = _publish(channel, repo)(draft_id=DRAFT, asset_id=ASSET, title="Moon Print")

        assert listing.state is PublishState.PUBLISHED
        assert listing.external_id == "etsy-1"
        assert len(channel.calls) == 1

    def test_given_a_redelivered_task_when_published_then_the_vendor_is_not_called_again(
        self,
    ) -> None:
        """The $0.20 case. A second publish must not reach Etsy at all."""
        channel, repo = FakeChannel(), InMemoryListingRepository()
        publish = _publish(channel, repo)

        first = publish(draft_id=DRAFT, asset_id=ASSET, title="Moon Print")
        second = publish(draft_id=DRAFT, asset_id=ASSET, title="Moon Print")

        assert len(channel.calls) == 1
        assert first.external_id == second.external_id
        assert len(repo.by_draft) == 1

    def test_given_an_already_published_draft_when_forced_then_still_refused(self) -> None:
        """A "force" that creates a second paid listing is a footgun with a
        friendly name."""
        channel, repo = FakeChannel(), InMemoryListingRepository()
        publish = _publish(channel, repo)
        publish(draft_id=DRAFT, asset_id=ASSET, title="Moon Print")

        with pytest.raises(AlreadyPublishedError, match="force does not republish"):
            publish(draft_id=DRAFT, asset_id=ASSET, title="Moon Print", force=True)

        assert len(channel.calls) == 1

    def test_given_the_channel_when_publishing_then_it_receives_the_key(self) -> None:
        channel, repo = FakeChannel(), InMemoryListingRepository()
        _publish(channel, repo)(draft_id=DRAFT, asset_id=ASSET, title="Moon Print")
        assert channel.calls == [idempotency_key(DRAFT)]


class TestFailure:
    def test_given_a_channel_error_when_published_then_recorded_and_reraised(self) -> None:
        channel, repo = FakeChannel(fails=True), InMemoryListingRepository()

        with pytest.raises(ConnectionError):
            _publish(channel, repo)(draft_id=DRAFT, asset_id=ASSET, title="Moon Print")

        listing = repo.for_draft(DRAFT)
        assert listing is not None
        assert listing.state is PublishState.FAILED
        assert "ConnectionError" in (listing.failure_reason or "")
        assert listing.attempts == 1

    def test_given_a_failed_publish_when_retried_then_it_is_attempted_again(self) -> None:
        """A failure is retryable — that is what distinguishes it from success."""
        repo = InMemoryListingRepository()
        with pytest.raises(ConnectionError):
            _publish(FakeChannel(fails=True), repo)(
                draft_id=DRAFT, asset_id=ASSET, title="Moon Print"
            )

        working = FakeChannel()
        listing = _publish(working, repo)(draft_id=DRAFT, asset_id=ASSET, title="Moon Print")

        assert listing.state is PublishState.PUBLISHED
        assert listing.attempts == 2
        assert listing.failure_reason is None

    def test_given_a_published_listing_when_failure_recorded_then_raises(self) -> None:
        listing = Listing.pending(draft_id=DRAFT, asset_id=ASSET, title="t", channel_name="c")
        listing.record_published(PublishResult(external_id="etsy-1"))
        with pytest.raises(AlreadyPublishedError):
            listing.record_failure("late error")


class TestListingInvariants:
    def test_given_a_published_state_without_an_external_id_when_built_then_raises(
        self,
    ) -> None:
        # A row like this is unverifiable: nothing ties it to a real listing.
        with pytest.raises(ValueError, match="external id"):
            Listing(
                listing_id=uuid4(),
                draft_id=DRAFT,
                asset_id=ASSET,
                title="t",
                channel_name="c",
                state=PublishState.PUBLISHED,
            )

    def test_given_a_blank_title_when_built_then_raises(self) -> None:
        with pytest.raises(ValueError, match="needs a title"):
            Listing.pending(draft_id=DRAFT, asset_id=ASSET, title="  ", channel_name="c")

    def test_given_a_publish_when_recorded_then_it_announces_itself(self) -> None:
        listing = Listing.pending(draft_id=DRAFT, asset_id=ASSET, title="t", channel_name="etsy")
        listing.record_published(PublishResult(external_id="etsy-9", external_url="http://x"))

        (event,) = listing.pull_events()
        assert isinstance(event, ListingPublished)
        assert event.external_id == "etsy-9"
        assert event.channel_name == "etsy"
