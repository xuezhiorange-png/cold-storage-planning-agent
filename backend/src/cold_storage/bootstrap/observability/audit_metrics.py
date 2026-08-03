"""Audit observability metrics port implementation."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class AuditMetricsRecorder:
    """Records audit observability metrics via the metrics registry.

    This is a thin adapter between the audit domain and the metrics
    registry. It does NOT modify the audit domain itself.
    """

    def __init__(self, metrics: object | None = None) -> None:
        self._metrics = metrics

    def record_chain_integrity(self, status: int) -> None:
        if self._metrics is not None and hasattr(self._metrics, "record_audit_chain_integrity"):
            self._metrics.record_audit_chain_integrity(status)  # type: ignore[union-attr]

    def record_write_duration(self, seconds: float) -> None:
        if self._metrics is not None and hasattr(self._metrics, "record_audit_write_duration"):
            self._metrics.record_audit_write_duration(seconds)  # type: ignore[union-attr]
