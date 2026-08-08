"""FastAPI entrypoint. Run: uvicorn kairos.app:app --reload"""

from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from kairos.config import get_settings
from kairos.content_generation.infrastructure.repository import (
    SqlAlchemyGeneratedAssetRepository,
)
from kairos.curation.application.review_asset import ApproveAsset, RejectAsset
from kairos.curation.domain.value_objects import IpCheck, RejectionReason
from kairos.curation.infrastructure.repository import SqlAlchemyReviewDecisionRepository
from kairos.db import engine, get_session
from kairos.niche_ranking.infrastructure.repository import SqlAlchemyNicheRepository

app = FastAPI(title="Kairos", version="0.1.0")

# DEC-01: server-rendered. The review queue and leaderboard are keyboard-driven
# lists; React would buy nothing and cost a second runtime for a solo operator.
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": get_settings().environment}


@app.get("/health/deep")
def health_deep() -> dict[str, str]:
    """Checks the dependencies a shallow /health would miss."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:
        database = f"unreachable: {type(exc).__name__}"
    return {"status": "ok" if database == "ok" else "degraded", "database": database}


@app.get("/niches", response_class=HTMLResponse)
def leaderboard(
    request: Request,
    session: Session = Depends(get_session),  # noqa: B008 - FastAPI's DI idiom
) -> HTMLResponse:
    """ENG-23 — the Niche Leaderboard read model."""
    niches = SqlAlchemyNicheRepository(session).leaderboard(limit=50)
    return templates.TemplateResponse(
        request=request,
        name="leaderboard.html",
        context={
            "niches": niches,
            "thin_count": sum(1 for niche in niches if niche.needs_corroboration),
        },
    )


# The review queue is the surface Hamid uses daily, and review speed is the
# throughput ceiling for the whole business (RSK-07): at a 1-5% winner rate,
# finding winners means reviewing a lot of designs. Ten seconds per asset
# instead of two is the binding constraint, not generation cost or API limits.
IP_CHECK_LABELS = {
    IpCheck.NO_BRAND_NAME_OR_LOGO: "No brand name or logo",
    IpCheck.NO_COPYRIGHTED_CHARACTER: "No copyrighted character",
    IpCheck.NO_CELEBRITY_LIKENESS: "No celebrity likeness",
    IpCheck.NO_SPORTS_TEAM_OR_UNIVERSITY: "No sports team or university mark",
    IpCheck.NO_SONG_LYRIC_OR_QUOTE: "No song lyric or quoted text",
    IpCheck.NO_TRADEMARKED_PHRASE: "No trademarked phrase",
}

REJECTION_LABELS = {
    RejectionReason.IP_RISK: "IP risk",
    RejectionReason.POOR_QUALITY: "Poor quality",
    RejectionReason.OFF_BRIEF: "Off brief",
    RejectionReason.DUPLICATE: "Duplicate",
    RejectionReason.OTHER: "Other",
}

# Reviewer identity is hardcoded while there is exactly one operator. It becomes
# a real identity when a second person reviews — the audit trail already stores
# it per decision, so only this line changes.
REVIEWER = "hamid"


def _pending_assets(session: Session) -> list[object]:
    """Packaged assets with no decision yet.

    Composed here rather than inside either context: Curation must not import
    Content Generation, and app.py is the composition root.
    """
    reviews = SqlAlchemyReviewDecisionRepository(session)
    return [
        asset
        for asset in SqlAlchemyGeneratedAssetRepository(session).awaiting_review()
        if (existing := reviews.for_asset(asset.asset_id)) is None or not existing.is_decided
    ]


@app.get("/review", response_class=HTMLResponse)
def review_queue(
    request: Request,
    i: int = 0,
    session: Session = Depends(get_session),  # noqa: B008 - FastAPI's DI idiom
) -> HTMLResponse:
    """ENG-30 — the Review Queue. One asset per screen, keyboard-driven."""
    pending = _pending_assets(session)
    index = max(0, min(i, len(pending) - 1)) if pending else 0
    asset = pending[index] if pending else None
    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context={
            "asset": asset,
            "position": index + 1,
            "total": len(pending),
            "next_index": min(index + 1, max(len(pending) - 1, 0)),
            "prev_index": max(index - 1, 0),
            # Never pre-ticked. A pre-ticked box is a box nobody reads (CMP-05).
            "checks": [
                {"value": check.value, "label": label} for check, label in IP_CHECK_LABELS.items()
            ],
            "reasons": [(reason.value, label) for reason, label in REJECTION_LABELS.items()],
        },
    )


@app.post("/review/{asset_id}/approve")
def approve(
    asset_id: UUID,
    confirmed: list[str] = Form(default=[]),  # noqa: B008 - FastAPI's DI idiom
    session: Session = Depends(get_session),  # noqa: B008 - FastAPI's DI idiom
) -> RedirectResponse:
    """Approve. The domain rejects an incomplete screening, so a tampered form
    or a client with JavaScript disabled cannot approve by omission."""
    ApproveAsset(SqlAlchemyReviewDecisionRepository(session))(
        asset_id,
        reviewer=REVIEWER,
        confirmed_checks={IpCheck(value) for value in confirmed},
    )
    return RedirectResponse("/review", status_code=303)


@app.post("/review/{asset_id}/reject")
def reject(
    asset_id: UUID,
    reason: str = Form(...),
    note: str = Form(default=""),
    session: Session = Depends(get_session),  # noqa: B008 - FastAPI's DI idiom
) -> RedirectResponse:
    RejectAsset(SqlAlchemyReviewDecisionRepository(session))(
        asset_id, reviewer=REVIEWER, reason=RejectionReason(reason), note=note
    )
    return RedirectResponse("/review", status_code=303)
