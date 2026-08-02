"""FastAPI entrypoint. Run: uvicorn kairos.app:app --reload"""

from fastapi import FastAPI
from sqlalchemy import text

from kairos.config import get_settings
from kairos.db import engine

app = FastAPI(title="Kairos", version="0.1.0")


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
