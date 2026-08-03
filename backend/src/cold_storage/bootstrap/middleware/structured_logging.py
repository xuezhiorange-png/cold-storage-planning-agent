"""ASGI middleware for structured request/response logging.

Logs incoming requests (method, path, client IP) and responses (status
code, duration) using structured JSON via the standard ``logging`` module.
Integrates the configuration redactor so that sensitive header values are
never emitted.  Attaches ``capability_tags`` to each log record for
downstream log aggregation and metric correlation.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from cold_storage.bootstrap.configuration_redactor import redact_text
from cold_storage.bootstrap.logging import (
    get_correlation_id,
    get_request_id,
)

logger = logging.getLogger(__name__)

# Capability tags emitted with every structured log line so downstream
# consumers (log aggregators, metric pipelines) can filter by feature.
CAPABILITY_TAGS: frozenset[str] = frozenset(
    {
        "cold-storage-api",
        "http",
        "structured-logging",
    }
)


def _extract_client_ip(scope: dict[str, Any]) -> str:
    """Best-effort extraction of the real client IP from the ASGI scope.

    Checks ``x-forwarded-for`` and ``x-real-ip`` headers (common behind
    reverse proxies) before falling back to the ASGI ``client`` tuple.
    """
    raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    headers_dict: dict[bytes, bytes] = dict(raw_headers)

    forwarded_for = headers_dict.get(b"x-forwarded-for")
    if forwarded_for:
        return forwarded_for.decode("latin-1").split(",")[0].strip()

    real_ip = headers_dict.get(b"x-real-ip")
    if real_ip:
        return real_ip.decode("latin-1").strip()

    client = scope.get("client")
    if client:
        return str(client[0])

    return "unknown"


def _safe_path(scope: dict[str, Any]) -> str:
    """Return the request path without query string."""
    return str(scope.get("path", "/"))


def _log_record(
    *,
    level: int,
    event: str,
    extra: dict[str, Any],
) -> None:
    """Emit a structured JSON log record.

    The record includes ``capability_tags`` so that log aggregators can
    filter on it, plus the current ``correlation_id`` and ``request_id``.
    """
    payload: dict[str, Any] = {
        "event": event,
        "capability_tags": sorted(CAPABILITY_TAGS),
        "correlation_id": get_correlation_id(),
        "request_id": get_request_id(),
    }
    payload.update(extra)

    logger.log(
        level,
        json.dumps(payload, default=str, ensure_ascii=False),
        extra={"structured": True},
    )


class StructuredLoggingMiddleware:
    """ASGI middleware that logs requests and responses in structured JSON.

    Usage::

        from cold_storage.bootstrap.middleware.structured_logging import (
            StructuredLoggingMiddleware,
        )

        app.add_middleware(StructuredLoggingMiddleware)
    """

    def __init__(self, app: Any) -> None:  # noqa: ANN401
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,  # noqa: ANN401
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = _safe_path(scope)
        method: str = scope.get("method", "UNKNOWN")
        client_ip = _extract_client_ip(scope)

        _log_record(
            level=logging.INFO,
            event="request_started",
            extra={
                "method": method,
                "path": redact_text(path),
                "client_ip": client_ip,
                "scheme": scope.get("scheme", "http"),
            },
        )

        start_time = time.monotonic()
        status_code = 500

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            _log_record(
                level=logging.ERROR,
                event="request_failed",
                extra={
                    "method": method,
                    "path": redact_text(path),
                    "client_ip": client_ip,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            raise

        duration_ms = round((time.monotonic() - start_time) * 1000, 2)
        log_level = logging.WARNING if status_code >= 400 else logging.INFO
        _log_record(
            level=log_level,
            event="request_completed",
            extra={
                "method": method,
                "path": redact_text(path),
                "client_ip": client_ip,
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
        )
