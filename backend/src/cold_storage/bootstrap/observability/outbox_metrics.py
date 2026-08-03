"""Outbox observability metrics port implementation."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class OutboxMetricsRecorder:
    """Records outbox observability metrics via the metrics registry.

    This is a thin adapter between the outbox domain and the metrics
    registry. It does NOT modify the outbox domain itself.
    """

    def __init__(self, metrics: object | None = None) -> None:
        self._metrics = metrics

    def record_backlog(self, queue: str, count: int) -> None:
        if self._metrics is not None and hasattr(self._metrics, "record_outbox_backlog"):
            self._metrics.record_outbox_backlog(queue, count)  # type: ignore[union-attr]

    def record_lag(self, queue: str, seconds: float) -> None:
        if self._metrics is not None and hasattr(self._metrics, "record_outbox_lag"):
            self._metrics.record_outbox_lag(queue, seconds)  # type: ignore[union-attr]

    def record_delivery_attempt(self, queue: str, attempt: int) -> None:
        if self._metrics is not None and hasattr(self._metrics, "record_outbox_delivery_attempt"):
            self._metrics.record_outbox_delivery_attempt(queue, attempt)  # type: ignore[union-attr]

    def record_delivery_failure(self, queue: str, failure_class: str) -> None:
        if self._metrics is not None and hasattr(self._metrics, "record_outbox_delivery_failure"):
            self._metrics.record_outbox_delivery_failure(queue, failure_class)  # type: ignore[union-attr]

    def record_poison_message(self, queue: str) -> None:
        if self._metrics is not None and hasattr(self._metrics, "record_outbox_poison_message"):
            self._metrics.record_outbox_poison_message(queue)  # type: ignore[union-attr]

    def record_retry_exhaustion(self, queue: str) -> None:
        if self._metrics is not None and hasattr(self._metrics, "record_outbox_retry_exhaustion"):
            self._metrics.record_outbox_retry_exhaustion(queue)  # type: ignore[union-attr]
