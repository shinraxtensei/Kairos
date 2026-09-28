"""The Listing aggregate and the FulfillmentChannel port.

ENG-32 and ENG-34. The domain is not blocked on Etsy credentials — only the
adapter is — and idempotency belongs here rather than inside whichever adapter
happens to publish, or every future channel reimplements it and one gets it
wrong.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

from kairos.fulfillment.domain.events import ListingPublished, ListingPublishFailed

ListingEvent = ListingPublished | ListingPublishFailed

IDEMPOTENCY_NAMESPACE = uuid5(NAMESPACE_URL, "https://kairos.local/listing-publish")


class PublishState(StrEnum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


class AlreadyPublishedError(RuntimeError):
    """A second publish was attempted for a draft that already succeeded.

    Etsy charges $0.20 per listing, non-refundable, and `task_acks_late` makes
    Celery redelivery normal operation rather than an edge case. Without this
    guard a retry quietly creates — and bills for — a duplicate listing.
    """


def idempotency_key(draft_id: UUID) -> str:
    """Stable per draft, so a retry of the same publish is recognisable.

    Derived from the draft rather than generated, because a generated key is
    new on every retry and therefore idempotent against nothing.
    """
    return str(uuid5(IDEMPOTENCY_NAMESPACE, str(draft_id)))


@dataclass(frozen=True, slots=True)
class PublishResult:
    """What a channel returns. External ids are strings — Etsy's are numeric,
    Printful's are not, and the domain should not care."""

    external_id: str
    external_url: str | None = None


class FulfillmentChannel(ABC):
    """One place a listing can be published.

    `EtsyDigitalDownloadAdapter` first; Printful/Printify implement this same
    port in Phase 2 with no upstream changes (CONTEXT.md §4.7).
    """

    @property
    @abstractmethod
    def channel_name(self) -> str: ...

    @abstractmethod
    def publish(self, listing: Listing) -> PublishResult:
        """Publish, keyed on `listing.idempotency_key`.

        Adapters must send that key to the vendor where the vendor supports it,
        and otherwise check for an existing listing before creating one.
        """


@dataclass(eq=False, slots=True)
class Listing:
    listing_id: UUID
    draft_id: UUID
    asset_id: UUID
    title: str
    channel_name: str
    state: PublishState = PublishState.PENDING
    external_id: str | None = None
    external_url: str | None = None
    failure_reason: str | None = None
    attempts: int = 0
    published_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    events: list[ListingEvent] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("a listing needs a title")
        if self.state is PublishState.PUBLISHED and not self.external_id:
            raise ValueError(
                "a published listing must carry the external id it was published under"
            )

    @classmethod
    def pending(
        cls,
        *,
        draft_id: UUID,
        asset_id: UUID,
        title: str,
        channel_name: str,
        listing_id: UUID | None = None,
    ) -> Listing:
        return cls(
            listing_id=listing_id or uuid4_from(draft_id),
            draft_id=draft_id,
            asset_id=asset_id,
            title=title,
            channel_name=channel_name,
        )

    @property
    def idempotency_key(self) -> str:
        return idempotency_key(self.draft_id)

    @property
    def is_published(self) -> bool:
        return self.state is PublishState.PUBLISHED

    def guard_publishable(self) -> None:
        """Raise if this listing has already gone live.

        Called before the channel is touched, so a redelivered task cannot
        reach the vendor at all.
        """
        if self.is_published:
            raise AlreadyPublishedError(
                f"draft {self.draft_id} is already live as {self.external_id} — "
                "publishing again would create a duplicate and charge for it"
            )

    def record_published(self, result: PublishResult) -> None:
        self.guard_publishable()
        self.attempts += 1
        self.state = PublishState.PUBLISHED
        self.external_id = result.external_id
        self.external_url = result.external_url
        self.failure_reason = None
        self.published_at = datetime.now(UTC)
        self.events.append(
            ListingPublished(
                listing_id=self.listing_id,
                draft_id=self.draft_id,
                asset_id=self.asset_id,
                external_id=result.external_id,
                channel_name=self.channel_name,
            )
        )

    def record_failure(self, reason: str) -> None:
        """A failed publish stays retryable — that is the difference between it
        and a successful one, which never is."""
        self.guard_publishable()
        self.attempts += 1
        self.state = PublishState.FAILED
        self.failure_reason = reason
        self.events.append(
            ListingPublishFailed(
                listing_id=self.listing_id,
                draft_id=self.draft_id,
                reason=reason,
                attempts=self.attempts,
            )
        )

    def pull_events(self) -> list[ListingEvent]:
        drained, self.events = self.events, []
        return drained

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Listing) and self.listing_id == other.listing_id

    def __hash__(self) -> int:
        return hash(self.listing_id)


def uuid4_from(draft_id: UUID) -> UUID:
    """One draft is one listing, so the id is derived rather than random.

    A random id would let a retried task insert a second row for the same draft
    before the idempotency guard ever got a chance to look at it.
    """
    return uuid5(IDEMPOTENCY_NAMESPACE, f"listing:{draft_id}")
