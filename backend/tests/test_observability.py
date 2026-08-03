"""Tests for observability middleware, ports, and failure classes."""

from __future__ import annotations

from cold_storage.bootstrap.observability.audit_metrics import AuditMetricsRecorder
from cold_storage.bootstrap.observability.failure_classes import (
    ALERTABLE_FAILURE_CLASSES,
    AlertableFailureClass,
)
from cold_storage.bootstrap.observability.health_probe_consumer import (
    HealthProbeConsumer,
)
from cold_storage.bootstrap.observability.outbox_metrics import OutboxMetricsRecorder


class TestFailureClasses:
    def test_ten_classes(self) -> None:
        assert len(AlertableFailureClass) == 10

    def test_all_classes_in_frozenset(self) -> None:
        for fc in AlertableFailureClass:
            assert fc.value in ALERTABLE_FAILURE_CLASSES

    def test_no_dynamic_classes(self) -> None:
        """Failure class labels are frozen at contract time."""
        assert len(ALERTABLE_FAILURE_CLASSES) == 10


class TestHealthProbeConsumer:
    def test_record_health_probe(self) -> None:
        consumer = HealthProbeConsumer()
        # Should not raise
        consumer.record_health_probe("database", healthy=True)

    def test_on_probe_timeout(self) -> None:
        consumer = HealthProbeConsumer()
        consumer.on_probe_timeout("redis")

    def test_on_probe_success(self) -> None:
        consumer = HealthProbeConsumer()
        consumer.on_probe_success("database")


class TestOutboxMetricsRecorder:
    def test_record_backlog(self) -> None:
        recorder = OutboxMetricsRecorder()
        recorder.record_backlog("audit_events", 5)

    def test_record_lag(self) -> None:
        recorder = OutboxMetricsRecorder()
        recorder.record_lag("audit_events", 300.0)

    def test_record_poison_message(self) -> None:
        recorder = OutboxMetricsRecorder()
        recorder.record_poison_message("audit_events")


class TestAuditMetricsRecorder:
    def test_record_chain_integrity(self) -> None:
        recorder = AuditMetricsRecorder()
        recorder.record_chain_integrity(1)

    def test_record_write_duration(self) -> None:
        recorder = AuditMetricsRecorder()
        recorder.record_write_duration(0.05)
