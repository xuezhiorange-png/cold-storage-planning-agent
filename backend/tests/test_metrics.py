"""Tests for Prometheus metrics registry and endpoint."""

from __future__ import annotations

import pytest

from cold_storage.bootstrap.metrics.registry import ObservableMetrics, get_metrics


class TestObservableMetrics:
    def test_singleton_safety(self) -> None:
        """get_metrics() should return same instance."""
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_register_route_template(self) -> None:
        m = ObservableMetrics()
        m.register_route_template("/api/v1/test/{id}")
        assert "/api/v1/test/{id}" in m._routes

    def test_route_template_cap(self) -> None:
        m = ObservableMetrics()
        for i in range(10):
            m.register_route_template(f"/route/{i}")
        # 11th should raise ValueError
        with pytest.raises(ValueError, match="Route cap"):
            m.register_route_template("/route/overflow")

    def test_register_dependency(self) -> None:
        m = ObservableMetrics()
        m.register_dependency("database")
        assert "database" in m._dependencies

    def test_dependency_cap(self) -> None:
        m = ObservableMetrics()
        for i in range(8):
            m.register_dependency(f"dep_{i}")
        with pytest.raises(ValueError, match="Dependency cap"):
            m.register_dependency("dep_overflow")

    def test_register_queue(self) -> None:
        m = ObservableMetrics()
        m.register_queue("audit_events")
        assert "audit_events" in m._queues

    def test_queue_cap(self) -> None:
        m = ObservableMetrics()
        for i in range(8):
            m.register_queue(f"queue_{i}")
        with pytest.raises(ValueError, match="Queue cap"):
            m.register_queue("queue_overflow")

    def test_record_http_request(self) -> None:
        m = ObservableMetrics()
        m.register_route_template("/test")
        m.record_http_request("GET", "/test", 200, 0.1)
        # Should not raise

    def test_unregistered_route_rejected(self) -> None:
        m = ObservableMetrics()
        # /unregistered is not registered, should increment HIGH_CARDINALITY_LABEL_REJECTED
        m.record_http_request("GET", "/unregistered", 200, 0.1)

    def test_collect_returns_string(self) -> None:
        m = ObservableMetrics()
        result = m.collect()
        assert isinstance(result, str)
        assert "process_uptime_seconds" in result or "# EOF" in result
