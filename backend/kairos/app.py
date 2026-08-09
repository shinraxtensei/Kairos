"""FastAPI entrypoint. Run: uvicorn kairos.app:app --reload"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from kairos.budgeting import public as budgeting
from kairos.budgeting.domain.spend_ledger import category_is_metered
from kairos.budgeting.domain.value_objects import BudgetPeriod, CostCategory
from kairos.budgeting.infrastructure.models import CostEventRecord
from kairos.config import get_settings
from kairos.content_generation.domain.generated_asset import GeneratedAsset
from kairos.content_generation.infrastructure.repository import (
    SqlAlchemyGeneratedAssetRepository,
)
from kairos.curation.application.review_asset import ApproveAsset, RejectAsset
from kairos.curation.domain.value_objects import IpCheck, RejectionReason
from kairos.curation.infrastructure.repository import SqlAlchemyReviewDecisionRepository
from kairos.db import engine, get_session
from kairos.niche_ranking.infrastructure.repository import SqlAlchemyNicheRepository
from kairos.shared_kernel.money import Money

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


def _pending_assets(session: Session) -> list[GeneratedAsset]:
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


# ---------------------------------------------------------------------------
# JSON read API.
#
# Added so the frontend decision stays open: a React/Next dashboard can be built
# against these without touching the backend, and if it turns out not to earn
# its second runtime, nothing was wasted. The HTML pages above stay the default
# because the review queue is keyboard-driven list navigation, which a SPA does
# not improve (DEC-01).
# ---------------------------------------------------------------------------


@app.get("/api/niches")
def api_niches(
    session: Session = Depends(get_session),  # noqa: B008 - FastAPI's DI idiom
) -> list[dict[str, object]]:
    return [
        {
            "keyword": niche.keyword,
            "score": niche.score.value if niche.score else None,
            "confidence": niche.score.confidence.value if niche.score else None,
            "status": niche.status.value,
            "needs_corroboration": niche.needs_corroboration,
            "breakdown": niche.breakdown.as_dict() if niche.breakdown else None,
            "scored_at": niche.scored_at.isoformat() if niche.scored_at else None,
        }
        for niche in SqlAlchemyNicheRepository(session).leaderboard(limit=50)
    ]


@app.get("/api/review/queue")
def api_review_queue(
    session: Session = Depends(get_session),  # noqa: B008 - FastAPI's DI idiom
) -> dict[str, object]:
    pending = _pending_assets(session)
    return {
        "total": len(pending),
        # Sent so a client cannot invent its own list, drift from the server's,
        # and quietly ship a shorter screening than the domain requires.
        "ip_checks": [
            {"value": check.value, "label": label} for check, label in IP_CHECK_LABELS.items()
        ],
        "rejection_reasons": [
            {"value": reason.value, "label": label} for reason, label in REJECTION_LABELS.items()
        ],
        "assets": [
            {
                "asset_id": str(asset.asset_id),
                "niche_keyword": asset.niche_keyword,
                "variant_index": asset.variant.index,
                "seed": asset.variant.seed,
                "print_spec": (
                    {
                        "width_inches": asset.print_spec.width_inches,
                        "height_inches": asset.print_spec.height_inches,
                        "dpi": asset.print_spec.dpi,
                        "pixel_width": asset.print_spec.pixel_width,
                        "pixel_height": asset.print_spec.pixel_height,
                    }
                    if asset.print_spec
                    else None
                ),
                "files": (
                    [
                        {"filename": f.filename, "size_bytes": f.size_bytes}
                        for f in asset.delivery.files
                    ]
                    if asset.delivery
                    else []
                ),
                "cost": str(asset.generation_cost) if asset.generation_cost else None,
            }
            for asset in pending
        ],
    }


# ---------------------------------------------------------------------------
# Budget dashboard (ENG-39).
# ---------------------------------------------------------------------------

CATEGORY_LABELS = {
    CostCategory.IMAGE_GENERATION: "Image generation",
    CostCategory.UPSCALING: "Upscaling",
    CostCategory.TREND_DATA: "Trend data",
    CostCategory.LISTING_FEE: "Etsy listing fee",
    CostCategory.TRANSACTION_FEE: "Etsy transaction fee",
    CostCategory.ADVERTISING: "Advertising",
}


def _month_start_utc() -> datetime:
    first = datetime.now(UTC).date().replace(day=1)
    return datetime.combine(first, datetime.min.time(), tzinfo=UTC)


def _budget_view(session: Session) -> dict[str, object]:
    ledger = budgeting.current_ledger(session)

    meters = []
    for period in BudgetPeriod:
        cap = ledger.limit.cap_for(period)
        spent = ledger.spent_today if period is BudgetPeriod.DAILY else ledger.spent_this_month
        percent = min(float(spent.amount / cap.amount) * 100, 100.0)
        meters.append(
            {
                "period": period.value,
                "cap": str(cap),
                "spent": str(spent),
                "remaining": str(ledger.remaining(period)),
                "percent": round(percent, 1),
                "state": "over" if percent >= 100 else "warn" if percent >= 75 else "",
            }
        )

    totals = session.execute(
        select(
            CostEventRecord.category,
            func.sum(CostEventRecord.amount),
            func.count(CostEventRecord.cost_id),
        )
        .where(CostEventRecord.occurred_at >= _month_start_utc())
        .group_by(CostEventRecord.category)
        .order_by(func.sum(CostEventRecord.amount).desc())
    ).all()

    return {
        "currency": ledger.limit.currency,
        "paused": ledger.is_paused,
        "meters": meters,
        "by_category": [
            {
                "category": category,
                "label": CATEGORY_LABELS.get(CostCategory(category), category),
                "total": str(Money(Decimal(str(total)), ledger.limit.currency)),
                "count": count,
                "metered": category_is_metered(CostCategory(category)),
            }
            for category, total, count in totals
        ],
    }


@app.get("/budget", response_class=HTMLResponse)
def budget_dashboard(
    request: Request,
    session: Session = Depends(get_session),  # noqa: B008 - FastAPI's DI idiom
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request, name="budget.html", context=_budget_view(session)
    )


@app.get("/api/budget")
def api_budget(
    session: Session = Depends(get_session),  # noqa: B008 - FastAPI's DI idiom
) -> dict[str, object]:
    return _budget_view(session)
