"""The ReviewDecision aggregate — one human decision about one asset.

`AssetApproved` is the event the entire downstream pipeline hangs off: Listing
Authoring's `DraftListing` requires one to exist for that asset (CONTEXT.md §2).
It can only be produced here, and only with a complete `IpScreening`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from kairos.curation.domain.events import AssetApproved, AssetRejected
from kairos.curation.domain.value_objects import (
    ApprovalDecision,
    IpScreening,
    RejectionReason,
)

ReviewEvent = AssetApproved | AssetRejected


class AlreadyReviewedError(RuntimeError):
    """A decision is final. Re-reviewing would orphan the downstream events."""


@dataclass(eq=False, slots=True)
class ReviewDecision:
    review_id: UUID
    asset_id: UUID
    reviewer: str
    decision: ApprovalDecision | None = None
    screening: IpScreening | None = None
    rejection_reason: RejectionReason | None = None
    decided_at: datetime | None = None
    events: list[ReviewEvent] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.reviewer.strip():
            raise ValueError("a review must record its reviewer")
        # Guarding only inside approve() left the raw constructor wide open:
        #   ReviewDecision(..., decision=ApprovalDecision(approved=True), screening=None)
        # produced a fully approved asset that was never screened, and any
        # repository rehydrating a row would do exactly this. The invariant has
        # to live where the object is built, not only on the happy path.
        if self.decision is not None and self.decision.approved and self.screening is None:
            raise ValueError(
                "an approved review must carry a completed IpScreening — "
                "use ReviewDecision.approve() rather than constructing one directly"
            )

    @classmethod
    def open(cls, asset_id: UUID, reviewer: str, review_id: UUID | None = None) -> ReviewDecision:
        return cls(review_id=review_id or uuid4(), asset_id=asset_id, reviewer=reviewer)

    @property
    def is_decided(self) -> bool:
        return self.decision is not None

    def approve(self, screening: IpScreening, note: str = "") -> None:
        """Approve the asset. Requires a completed IP screening — no default.

        `screening` is a required positional argument on purpose. An optional
        one with a permissive default is how this check quietly stops happening
        eighteen months from now, when someone adds a bulk-approve button.
        """
        self._guard_not_decided()
        # Screening first: if the ApprovalDecision were assigned first and this
        # raised, the aggregate would be left approved-but-unscreened in memory.
        self.screening = screening
        self.decision = ApprovalDecision(approved=True, note=note)
        self.decided_at = datetime.now(UTC)
        self.events.append(
            AssetApproved(
                review_id=self.review_id,
                asset_id=self.asset_id,
                reviewer=self.reviewer,
                screened_by=screening.checked_by,
            )
        )

    def reject(self, reason: RejectionReason, note: str = "") -> None:
        """Reject the asset. No screening needed — nothing proceeds from here."""
        self._guard_not_decided()
        self.decision = ApprovalDecision(approved=False, note=note)
        self.rejection_reason = reason
        self.decided_at = datetime.now(UTC)
        self.events.append(
            AssetRejected(
                review_id=self.review_id,
                asset_id=self.asset_id,
                reviewer=self.reviewer,
                reason=reason,
                note=note,
            )
        )

    def _guard_not_decided(self) -> None:
        if self.is_decided:
            raise AlreadyReviewedError(
                f"asset {self.asset_id} was already reviewed — open a new review instead"
            )

    def pull_events(self) -> list[ReviewEvent]:
        drained, self.events = self.events, []
        return drained

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ReviewDecision) and self.review_id == other.review_id

    def __hash__(self) -> int:
        return hash(self.review_id)
