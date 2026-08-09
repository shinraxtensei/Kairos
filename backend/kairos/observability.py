"""OPS-07 and OPS-04 — structured logging with a correlation id, and alerting.

The pipeline is a chain of scheduled tasks: collect, rank, generate, review,
publish. When one produces a wrong result the question is always "what happened
to *this* niche", and without a shared id the answer means grepping timestamps
across four processes. The id is set once at the start of a task or request and
travels on every line after it.

Alerting is deliberately minimal. A solo operator's real failure mode is a
scheduled job that silently stopped running (OPS-04), which no exception tracker
catches because nothing raised.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# Never log these, whatever key they arrive under. The Etsy refresh token is the
# one secret whose leak would be quietly catastrophic — it grants publish rights
# for 90 days and nothing would look wrong.
REDACTED_KEYS = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "keystring",
        "refresh_token",
        "access_token",
        "authorization",
        "shared_secret",
    }
)
REDACTED = "***redacted***"


def correlation_id() -> str | None:
    return _correlation_id.get()


@contextmanager
def correlated(name: str, cid: str | None = None) -> Iterator[str]:
    """Tag every log line inside this block with one id.

    Wrap each scheduled task and each request in it; nested blocks keep the
    outer id, so a task that calls another does not lose the thread.
    """
    existing = _correlation_id.get()
    new = existing or cid or f"{name}-{uuid.uuid4().hex[:12]}"
    token = _correlation_id.set(new)
    try:
        yield new
    finally:
        _correlation_id.reset(token)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (REDACTED if key.lower() in REDACTED_KEYS else _redact(inner))
            for key, inner in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """One JSON object per line — greppable by field rather than by eyeball."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if (cid := correlation_id()) is not None:
            payload["correlation_id"] = cid
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        standard = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
            "message",
            "asctime",
            "taskName",
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in standard}
        if extras:
            payload["extra"] = _redact(extras)

        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None, *, force_json: bool | None = None) -> None:
    """Call once at process start — the app and the Celery worker both do.

    Plain text locally because JSON is unreadable while developing; JSON
    everywhere else, because that is where something will need grepping at an
    hour nobody wants to be awake.
    """
    root = logging.getLogger()
    root.handlers.clear()

    as_json = (
        force_json
        if force_json is not None
        else os.getenv("KAIROS_ENVIRONMENT", "local") != "local"
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter()
        if as_json
        else logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level or os.getenv("KAIROS_LOG_LEVEL") or "INFO")

    # SQLAlchemy and pytrends are chatty enough to bury everything else.
    for noisy in ("sqlalchemy.engine", "urllib3", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def alert(message: str, **context: Any) -> None:
    """OPS-04 — surface something a human must act on.

    Currently a CRITICAL log line, which is honest: there is no pager, and
    pretending otherwise would be worse than the gap. Route it somewhere real
    before the pipeline runs unattended — a dead scheduled job produces no
    exception, so nothing else will notice it stopped.
    """
    logging.getLogger("kairos.alert").critical(message, extra=_redact(context))
