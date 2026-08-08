"""FastAPI entrypoint. Run: uvicorn kairos.app:app --reload"""

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from kairos.config import get_settings
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
