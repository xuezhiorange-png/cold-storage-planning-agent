"""Integration tests for observability components."""

from __future__ import annotations

from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app


class TestMetricsEndpoint:
    def test_metrics_returns_prometheus_format(self) -> None:
        app = create_app()
        client = TestClient(app)
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")

    def test_metrics_contains_process_uptime(self) -> None:
        app = create_app()
        client = TestClient(app)
        response = client.get("/metrics")
        assert "process_uptime_seconds" in response.text

    def test_metrics_no_secrets(self) -> None:
        app = create_app()
        client = TestClient(app)
        response = client.get("/metrics")
        # Should not contain any secrets
        assert "password" not in response.text.lower()
        assert "token" not in response.text.lower()


class TestHealthEndpointsUnchanged:
    def test_health_live_unchanged(self) -> None:
        app = create_app()
        client = TestClient(app)
        response = client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "live"

    def test_health_ready_unchanged(self) -> None:
        app = create_app()
        client = TestClient(app)
        response = client.get("/health/ready")
        # Should return 200 or 503, but shape should be compatible
        assert response.status_code in (200, 503)
        data = response.json()
        assert "status" in data
