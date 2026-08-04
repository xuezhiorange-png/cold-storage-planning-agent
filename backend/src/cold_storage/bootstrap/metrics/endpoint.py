"""Prometheus text-exposition endpoint for the metrics registry.

Exposes GET /metrics returning ``text/plain; version=0.0.4`` per the
Prometheus exposition format specification.  The endpoint refreshes the
process uptime gauge before each collection and delegates to
``ObservableMetrics.collect()``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from fastapi import Response

if TYPE_CHECKING:
    from cold_storage.bootstrap.metrics.registry import ObservableMetrics

_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def create_metrics_endpoint(metrics: ObservableMetrics) -> Callable[..., Awaitable[Response]]:
    """Return a FastAPI-compatible route handler for /metrics.

    Usage in the app factory::

        from cold_storage.bootstrap.metrics import ObservableMetrics
        from cold_storage.bootstrap.metrics.endpoint import create_metrics_endpoint

        metrics = ObservableMetrics()
        # ... register routes, dependencies, etc.
        app = FastAPI()
        app.add_api_route("/metrics", create_metrics_endpoint(metrics))
    """

    async def metrics_endpoint() -> Response:
        body = metrics.collect()
        return Response(content=body, media_type=_CONTENT_TYPE)

    return metrics_endpoint
