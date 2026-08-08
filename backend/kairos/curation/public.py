"""Curation's published interface — the only surface other contexts use.

A sibling of the layers rather than one of them, so it may wire this context's
repository without breaking the inward-only dependency rule.

It exposes exactly one question, deliberately: has this asset been approved by a
human, with a completed IP screening, and is that recorded in the database. No
caller can reach a ReviewDecision, an IpScreening, or the review_decisions table.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from kairos.curation.infrastructure.repository import SqlAlchemyReviewDecisionRepository

__all__ = ["asset_is_approved"]


def asset_is_approved(session: Session, asset_id: UUID) -> bool:
    return SqlAlchemyReviewDecisionRepository(session).approval_exists_for(asset_id)
