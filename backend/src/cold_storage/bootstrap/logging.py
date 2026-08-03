"""JSON structured logging with context propagation and redaction.

Produces one JSON object per line (JSON Lines / NDJSON) suitable for
aggregation by Loki, Elasticsearch, CloudWatch Logs, or any structured
log collector.

Fields per line:
    timestamp  – RFC 3339 UTC
    level      – log level name
    name       – logger name
    correlation_id – set via set_correlation_id()
    request_id    – set via set_request_id()
    capability_tags – list of capability tags for the current context
    message    – the log message
"""

from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from cold_storage.bootstrap.configuration_redactor import (
    EmitPoint,
    redact_exception_for_logging,
    redact_for_logging,
)

# ---------------------------------------------------------------------------
# Context variables – per-request / per-correlation identity
# ---------------------------------------------------------------------------

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_capability_tags: ContextVar[list[str] | None] = ContextVar("capability_tags", default=None)


def set_correlation_id(value: str | None) -> None:
    """Bind a correlation ID to the current async context."""
    _correlation_id.set(value)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_request_id(value: str | None) -> None:
    """Bind a request ID to the current async context."""
    _request_id.set(value)


def get_request_id() -> str | None:
    return _request_id.get()


def set_capability_tags(tags: list[str]) -> None:
    """Bind capability tags to the current async context."""
    _capability_tags.set(tags)


def get_capability_tags() -> list[str]:
    return list(_capability_tags.get() or [])


def new_correlation_id() -> str:
    """Generate a new UUIDv4 correlation ID and bind it to the context."""
    cid = uuid.uuid4().hex
    set_correlation_id(cid)
    return cid


def new_request_id() -> str:
    """Generate a new UUIDv4 request ID and bind it to the context."""
    rid = uuid.uuid4().hex
    set_request_id(rid)
    return rid


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------


class _JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line with redacted fields."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        try:
            timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        except (OSError, ValueError, OverflowError):
            timestamp = datetime.now(tz=UTC).isoformat()

        log_record: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "name": record.name,
            "correlation_id": get_correlation_id(),
            "request_id": get_request_id(),
            "capability_tags": get_capability_tags(),
            "message": redact_for_logging(record.getMessage(), emit_point=EmitPoint.LOG),
        }

        # Append exception info if present (redacted).
        if record.exc_info and record.exc_info[1] is not None:
            try:
                log_record["exception"] = redact_exception_for_logging(record.exc_info[1])
            except Exception:  # noqa: BLE001
                log_record["exception"] = "<unavailable>"

        # Include any extra fields attached to the record via **kwargs.
        for key in ("filename", "lineno", "funcName", "module"):
            log_record[key] = getattr(record, key, None)

        # Include extra fields passed via logger.log(..., extra={...}).
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in (
                "name",
                "msg",
                "args",
                "created",
                "relativeCreated",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "msecs",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "thread",
                "threadName",
                "process",
                "processName",
                "taskName",
                "message",
                "asctime",
            ):
                continue
            if key in log_record:
                continue
            log_record[key] = value

        return json.dumps(log_record, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_LOGGING_CONFIGURED: bool = False

_MARKER = "cold_storage_bootstrap_logging_configured"


def configure_logging() -> None:
    """Configure root logger for JSON Lines output.

    Safe to call multiple times – duplicate handlers are never installed.
    """
    global _LOGGING_CONFIGURED  # noqa: PLW0603

    if _LOGGING_CONFIGURED:
        return

    root = logging.getLogger()

    # Prevent duplicate handlers if called again.
    if getattr(root, _MARKER, False):
        return
    setattr(root, _MARKER, True)

    root.setLevel(logging.INFO)

    # Remove any existing handlers so we don't get duplicate output.
    # Only remove handlers that have our marker attribute.
    root.handlers[:] = [h for h in root.handlers if not getattr(h, _MARKER, False)]

    handler = logging.StreamHandler()
    handler.setFormatter(_JSONFormatter())
    setattr(handler, _MARKER, True)
    root.addHandler(handler)

    _LOGGING_CONFIGURED = True

    # Ensure the bootstrap logger itself emits at DEBUG when needed.
    bootstrap_logger = logging.getLogger("cold_storage.bootstrap")
    bootstrap_logger.setLevel(logging.DEBUG)
