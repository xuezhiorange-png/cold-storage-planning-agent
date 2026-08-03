"""Tests for observability configuration validation."""

from __future__ import annotations

import pytest

from cold_storage.bootstrap.metrics.registry import ObservableMetrics
from cold_storage.bootstrap.observability.failure_classes import (
    AlertableFailureClass,
)


class TestMetricsConfigValidation:
    def test_http_route_template_cap(self) -> None:
        m = ObservableMetrics()
        for i in range(10):
            m.register_route_template(f"/path/{i}")
        assert len(m._routes) == 10
        with pytest.raises(ValueError, match="Route cap"):
            m.register_route_template("/path/overflow")

    def test_dependency_cap(self) -> None:
        m = ObservableMetrics()
        for i in range(8):
            m.register_dependency(f"dep_{i}")
        assert len(m._dependencies) == 8
        with pytest.raises(ValueError, match="Dependency cap"):
            m.register_dependency("dep_overflow")

    def test_queue_cap(self) -> None:
        m = ObservableMetrics()
        for i in range(8):
            m.register_queue(f"q_{i}")
        assert len(m._queues) == 8
        with pytest.raises(ValueError, match="Queue cap"):
            m.register_queue("q_overflow")

    def test_collect_returns_string(self) -> None:
        m = ObservableMetrics()
        result = m.collect()
        assert isinstance(result, str)


class TestFailureClassValidation:
    def test_exact_10_classes(self) -> None:
        assert len(AlertableFailureClass) == 10

    def test_expected_class_names(self) -> None:
        expected = {
            "DATABASE_UNREACHABLE",
            "MIGRATION_HEAD_INVALID",
            "REDIS_UNREACHABLE",
            "ARTIFACT_STORAGE_AUTH_FAILED",
            "OUTBOX_RETRY_EXHAUSTED",
            "OUTBOX_POISON_MESSAGE",
            "READINESS_CHECK_TIMEOUT",
            "STARTUP_LIVENESS_STALL",
            "STRICT_ENVIRONMENT_VIOLATION",
            "SECRET_PRESENT_IN_REDACTED_OUTPUT",
        }
        actual = {fc.value for fc in AlertableFailureClass}
        assert actual == expected
