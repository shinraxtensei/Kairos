"""Trend Discovery's published interface — the only surface other contexts use.

Deliberately a sibling of the layers rather than part of them: it is this
context's composition root, so it may wire its own application service to its
own repository. `domain/`, `application/` and `infrastructure/` keep their
one-way dependency rule untouched.

Everything here returns plain DTOs. A caller can never reach a `TrendSignal`,
a SQLAlchemy model, or this context's tables — so Trend Discovery stays free to
change all three without breaking anyone.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from kairos.trend_discovery.application.queries import KeywordSignals, LatestSignalsPerKeyword
from kairos.trend_discovery.infrastructure.repository import SqlAlchemyTrendSignalRepository

__all__ = ["KeywordSignals", "latest_signals_per_keyword"]


def latest_signals_per_keyword(session: Session) -> list[KeywordSignals]:
    """Current picture per keyword, collapsed across sources.

    Returns one entry per keyword regardless of how much history exists.
    """
    return LatestSignalsPerKeyword(SqlAlchemyTrendSignalRepository(session))()
