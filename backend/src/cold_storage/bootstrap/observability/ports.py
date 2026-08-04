"""Observability ports and bounded registries."""

from __future__ import annotations

from typing import Protocol


class OutboxMetricsPort(Protocol):
    """Port for recording outbox observability metrics."""

    def record_backlog(self, queue: str, count: int) -> None: ...
    def record_lag(self, queue: str, seconds: float) -> None: ...
    def record_delivery_attempt(self, queue: str, attempt: int) -> None: ...
    def record_delivery_failure(self, queue: str, failure_class: str) -> None: ...
    def record_poison_message(self, queue: str) -> None: ...
    def record_retry_exhaustion(self, queue: str) -> None: ...


class AuditMetricsPort(Protocol):
    """Port for recording audit observability metrics."""

    def record_chain_integrity(self, status: int) -> None: ...
    def record_write_duration(self, seconds: float) -> None: ...


class DependencyHealthPort(Protocol):
    """Port for recording dependency health status."""

    def record_dependency_health(self, dependency: str, up: bool) -> None: ...


# Outbox alert thresholds (from D-OBS-009)
OUTBOX_LAG_ALERT_SECONDS: int = 300
POISON_MESSAGE_ALERT_THRESHOLD: int = 0
RETRY_EXHAUSTION_ALERT_THRESHOLD: int = 0
