"""Health probe consumer for dependency_up metric.

Consumes existing health/readiness status without redefining
Slice 2 health semantics. Does NOT create background threads;
provides a testable port that can be called pull-based.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_DEFAULT_POLL_INTERVAL_SECONDS: int = 10


class HealthProbeConsumer:
    """Consumes health/readiness status and updates dependency_up metric.

    Does NOT modify /health/live or /health/ready response schema.
    Does NOT propagate exceptions to business requests.
    """

    def __init__(self, metrics: object | None = None) -> None:
        self._metrics = metrics

    def record_health_probe(
        self,
        dependency: str,
        healthy: bool,
    ) -> None:
        """Record the health status of a dependency.

        Sets dependency_up{dependency=<name>} to 1 (healthy) or 0 (unhealthy).
        """
        if self._metrics is not None and hasattr(self._metrics, "record_dependency_health"):
            self._metrics.record_dependency_health(dependency, healthy)  # type: ignore[union-attr]

    def on_probe_timeout(self, dependency: str) -> None:
        """Handle probe timeout: set dependency_up=0, log WARNING."""
        self.record_health_probe(dependency, healthy=False)
        logger.warning(
            "Health probe timeout for dependency: %s",
            dependency,
            extra={"capability_tags": ["health_probe", "timeout"]},
        )

    def on_probe_success(self, dependency: str) -> None:
        """Handle probe recovery: set dependency_up=1."""
        self.record_health_probe(dependency, healthy=True)
