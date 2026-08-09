"""OPS-07 — structured logging and correlation ids."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest

from kairos.observability import (
    REDACTED,
    JsonFormatter,
    alert,
    configure_logging,
    correlated,
    correlation_id,
)


@pytest.fixture
def json_logs(caplog: pytest.LogCaptureFixture) -> Iterator[JsonFormatter]:
    caplog.set_level(logging.INFO)
    yield JsonFormatter()


def _render(formatter: JsonFormatter, record: logging.LogRecord) -> dict[str, object]:
    return json.loads(formatter.format(record))


def _record(message: str = "hello", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("kairos.test", logging.INFO, __file__, 1, message, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class TestCorrelationId:
    def test_given_no_context_when_asked_then_none(self) -> None:
        assert correlation_id() is None

    def test_given_a_block_when_inside_then_an_id_exists(self) -> None:
        with correlated("collect") as cid:
            assert correlation_id() == cid
            assert cid.startswith("collect-")

    def test_given_a_block_when_left_then_the_id_is_cleared(self) -> None:
        with correlated("collect"):
            pass
        assert correlation_id() is None

    def test_given_nested_blocks_when_inside_then_the_outer_id_wins(self) -> None:
        """A task calling another must not lose the thread mid-pipeline."""
        with correlated("collect") as outer, correlated("rank") as inner:
            assert inner == outer

    def test_given_an_explicit_id_when_supplied_then_it_is_used(self) -> None:
        with correlated("http", cid="req-123") as cid:
            assert cid == "req-123"


class TestJsonFormatter:
    def test_given_a_record_when_formatted_then_it_is_one_json_object(
        self, json_logs: JsonFormatter
    ) -> None:
        payload = _render(json_logs, _record("collected 3 signals"))
        assert payload["message"] == "collected 3 signals"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "kairos.test"
        assert "ts" in payload

    def test_given_a_correlated_block_when_formatted_then_the_id_is_included(
        self, json_logs: JsonFormatter
    ) -> None:
        with correlated("collect") as cid:
            payload = _render(json_logs, _record())
        assert payload["correlation_id"] == cid

    def test_given_extras_when_formatted_then_they_are_carried(
        self, json_logs: JsonFormatter
    ) -> None:
        payload = _render(json_logs, _record(niche="moon phase print", signals=3))
        assert payload["extra"] == {"niche": "moon phase print", "signals": 3}

    def test_given_a_secret_in_extras_when_formatted_then_it_is_redacted(
        self, json_logs: JsonFormatter
    ) -> None:
        """The Etsy refresh token grants publish rights for 90 days. A leak
        would look like nothing was wrong."""
        payload = _render(json_logs, _record(refresh_token="etsy-secret-value"))
        assert payload["extra"]["refresh_token"] == REDACTED  # type: ignore[index]
        assert "etsy-secret-value" not in json.dumps(payload)

    def test_given_a_nested_secret_when_formatted_then_it_is_still_redacted(
        self, json_logs: JsonFormatter
    ) -> None:
        payload = _render(json_logs, _record(config={"api_key": "abc123", "region": "us"}))
        nested = payload["extra"]["config"]  # type: ignore[index]
        assert nested["api_key"] == REDACTED
        assert nested["region"] == "us"

    def test_given_an_exception_when_formatted_then_the_traceback_is_included(
        self, json_logs: JsonFormatter
    ) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = _record("failed")
            record.exc_info = sys.exc_info()
        payload = _render(json_logs, record)
        assert "ValueError: boom" in str(payload["exception"])


class TestConfiguration:
    def test_given_local_when_configured_then_plain_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("KAIROS_ENVIRONMENT", "local")
        configure_logging()
        (handler,) = logging.getLogger().handlers
        assert not isinstance(handler.formatter, JsonFormatter)

    def test_given_production_when_configured_then_json(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("KAIROS_ENVIRONMENT", "production")
        configure_logging()
        (handler,) = logging.getLogger().handlers
        assert isinstance(handler.formatter, JsonFormatter)

    def test_given_configuration_when_repeated_then_handlers_do_not_stack(self) -> None:
        # Duplicate handlers mean duplicate lines, which quietly doubles log cost.
        configure_logging()
        configure_logging()
        assert len(logging.getLogger().handlers) == 1


class TestAlert:
    def test_given_an_alert_when_raised_then_it_is_critical(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Deliberately not calling configure_logging here: it clears root
        # handlers, which removes the one pytest installed to capture with.
        with caplog.at_level(logging.CRITICAL, logger="kairos.alert"):
            alert("trend collection produced nothing", sources_failed=2)
        assert "trend collection produced nothing" in caplog.text

    def test_given_an_alert_with_a_secret_when_raised_then_it_is_redacted(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.CRITICAL, logger="kairos.alert"):
            alert("publish failed", api_key="etsy-key-value")
        (record,) = [r for r in caplog.records if r.name == "kairos.alert"]
        assert record.api_key == REDACTED  # type: ignore[attr-defined]
