"""Tests for Prometheus metrics registry and endpoint."""

from __future__ import annotations

import re

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


def _parse_capability_value(exposition: str, capability: str) -> float | None:
    """Parse Prometheus exposition and return the agent_capability_status value."""
    pattern = rf'agent_capability_status{{capability="{capability}"}}\s+([\d.]+)'
    m = re.search(pattern, exposition)
    if m:
        return float(m.group(1))
    return None


class TestCapabilityMetrics:
    """Tests for capability metric recording per D-S4-05."""

    def test_register_and_record_capability(self) -> None:
        """Register a capability and record its status."""
        m = ObservableMetrics()
        m.register_capability("model_backed_agent")
        m.record_capability_status("model_backed_agent", is_available=True)
        output = m.collect()
        val = _parse_capability_value(output, "model_backed_agent")
        assert val == 1.0

    def test_unregistered_capability_rejected(self) -> None:
        """Recording an unregistered capability is silently ignored."""
        m = ObservableMetrics()
        m.record_capability_status("nonexistent_capability", is_available=True)
        # Should not raise; metric is simply not recorded

    def test_capability_available_value(self) -> None:
        """LOCAL_METRIC_VALUE=1: capability available records value 1.0."""
        m = ObservableMetrics()
        m.register_capability("model_backed_agent")
        m.record_capability_status("model_backed_agent", is_available=True)
        output = m.collect()
        val = _parse_capability_value(output, "model_backed_agent")
        assert val == 1.0

    def test_capability_unavailable_value(self) -> None:
        """STAGING_METRIC_VALUE=0: capability unavailable records value 0.0."""
        m = ObservableMetrics()
        m.register_capability("model_backed_agent")
        m.record_capability_status("model_backed_agent", is_available=False)
        output = m.collect()
        val = _parse_capability_value(output, "model_backed_agent")
        assert val == 0.0

    def test_capability_mode_matrix_local(self) -> None:
        """LOCAL_METRIC_VALUE=1 via create_app."""
        from cold_storage.bootstrap.app import create_app

        create_app()
        m = get_metrics()
        output = m.collect()
        val = _parse_capability_value(output, "model_backed_agent")
        assert val == 1.0, f"LOCAL mode should record 1.0, got {val}"

    def test_duplicate_registration_idempotent(self) -> None:
        """Registering the same capability twice is idempotent."""
        m = ObservableMetrics()
        m.register_capability("model_backed_agent")
        m.register_capability("model_backed_agent")  # second call
        # Should not raise

    def test_local_then_production_final_value(self) -> None:
        """LOCAL_THEN_PRODUCTION_FINAL_VALUE=0: second write overwrites."""
        m = ObservableMetrics()
        m.register_capability("model_backed_agent")
        m.record_capability_status("model_backed_agent", is_available=True)
        m.record_capability_status("model_backed_agent", is_available=False)
        output = m.collect()
        val = _parse_capability_value(output, "model_backed_agent")
        assert val == 0.0

    def test_production_then_local_final_value(self) -> None:
        """PRODUCTION_THEN_LOCAL_FINAL_VALUE=1: second write overwrites."""
        m = ObservableMetrics()
        m.register_capability("model_backed_agent")
        m.record_capability_status("model_backed_agent", is_available=False)
        m.record_capability_status("model_backed_agent", is_available=True)
        output = m.collect()
        val = _parse_capability_value(output, "model_backed_agent")
        assert val == 1.0

    def test_repeated_same_mode_idempotent(self) -> None:
        """REPEATED_SAME_MODE_IDEMPOTENT: same value written twice = same value."""
        m = ObservableMetrics()
        m.register_capability("model_backed_agent")
        m.record_capability_status("model_backed_agent", is_available=True)
        m.record_capability_status("model_backed_agent", is_available=True)
        output = m.collect()
        val = _parse_capability_value(output, "model_backed_agent")
        assert val == 1.0
