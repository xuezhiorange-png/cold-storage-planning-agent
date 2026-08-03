"""ASGI middleware for correlation-ID and request-ID propagation.

Extracts ``X-Request-ID`` from incoming request headers.  If the value is
a valid UUIDv4 it is reused as-is; otherwise a fresh lowercase UUIDv4 is
generated.  Both ``correlation_id`` and ``request_id`` are set on the
module-level ContextVars in :mod:`cold_storage.bootstrap.logging`.

Design constraints
------------------
* Does **NOT** persist the correlation ID to the database.
* Does **NOT** expose raw header values as metric labels.
* ``asyncio.create_task()`` automatically inherits ContextVar values on
  Python ≥ 3.12, so no extra context propagation is needed.
* Always resets ContextVars after the request completes, even on error.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from cold_storage.bootstrap.logging import (
    _capability_tags,
    _correlation_id,
    _request_id,
)
from cold_storage.bootstrap.middleware.structured_logging import CAPABILITY_TAGS

logger = logging.getLogger(__name__)

_HEADER_NAME = "x-request-id"
_RESPONSE_HEADER = "X-Request-ID"


def _is_valid_uuid_v4(value: str) -> bool:
    """Return True if *value* is a valid UUIDv4 string."""
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return False
    if parsed.version != 4:
        return False
    return parsed.time_hi_version >> 12 == 4


def _generate_id() -> str:
    """Generate a fresh lowercase UUIDv4."""
    return str(uuid.uuid4()).lower()


class CorrelationIdMiddleware:
    """ASGI middleware that propagates a correlation/request ID per request.

    Usage::

        from cold_storage.bootstrap.middleware.correlation_id import (
            CorrelationIdMiddleware,
        )

        app.add_middleware(CorrelationIdMiddleware)
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

        req_id = self._resolve_request_id(scope)

        token_corr = _correlation_id.set(req_id)
        token_req = _request_id.set(req_id)
        token_tags = _capability_tags.set(sorted(CAPABILITY_TAGS))

        try:
            await self._handle_request(scope, receive, send, req_id)
        finally:
            _correlation_id.reset(token_corr)
            _request_id.reset(token_req)
            _capability_tags.reset(token_tags)

    # -- Internals -----------------------------------------------------------

    def _resolve_request_id(self, scope: dict[str, Any]) -> str:
        """Extract or generate the request ID from the ASGI scope."""
        raw: str | None = None
        headers = scope.get("headers", [])
        for name, value in headers:
            if name == _HEADER_NAME.encode():
                raw = value.decode("latin-1").strip()
                break

        if raw and _is_valid_uuid_v4(raw):
            return raw.lower()

        return _generate_id()

    async def _handle_request(
        self,
        scope: dict[str, Any],
        receive: Any,  # noqa: ANN401
        send: Any,  # noqa: ANN401
        req_id: str,
    ) -> None:
        """Wrap ``send`` to inject the ``X-Request-ID`` response header."""

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                response_headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                response_headers.append((_RESPONSE_HEADER.encode(), req_id.encode()))
                message["headers"] = response_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
