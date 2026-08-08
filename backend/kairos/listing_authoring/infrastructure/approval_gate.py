"""The adapter behind ApprovalGate — the one permitted edge to Curation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from kairos.curation import public as curation
from kairos.listing_authoring.domain.ports import ApprovalGate


class CurationApprovalGate(ApprovalGate):
    def __init__(self, session: Session) -> None:
        self._session = session

    def is_approved(self, asset_id: UUID) -> bool:
        return curation.asset_is_approved(self._session, asset_id)
