"""Integration tests for core calculation API endpoints (Task 4).

Tests the three new API endpoints:
  - POST /api/v1/projects/{id}/versions/{version}/calculations/core
  - GET  /api/v1/projects/{id}/versions/{version}/calculations/core
  - POST /api/v1/calculations/core/preview
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.projects.infrastructure.database import (
    DatabaseProjectService,
)
from cold_storage.modules.projects.infrastructure.orm import Base

# Skip all tests in this module when DATABASE_BACKEND=postgresql
# because the app lifespan tries to connect to PostgreSQL which
# requires asyncpg (not always installed).
pytestmark = pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") == "postgresql",
    reason="Integration tests use SQLite; skip on PostgreSQL CI",
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> TestClient:
    """Create a test client with an in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    service = DatabaseProjectService(engine)
    app = create_app(project_service=service)
    with TestClient(app) as c:
        yield c
    engine.dispose()


def _create_project(client: TestClient) -> dict:
    """Create a project and return the response."""
    resp = client.post(
        "/api/v1/projects",
        json={
            "name": "Test Integration Project",
            "location": "Test Location",
            "product_category": "blueberry",
        },
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Preview endpoint (no persistence required)
# ---------------------------------------------------------------------------


class TestCoreCalculationPreview:
    """POST /api/v1/calculations/core/preview — no project needed."""

    def test_preview_returns_results(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/calculations/core/preview",
            json={
                "inputs": {
                    "daily_inbound_mass_kg": 25000,
                    "working_time_h_per_day": 16,
                    "utilization_factor": 0.85,
                    "turnover_days": 7,
                }
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "throughput" in data
        assert "inventory" in data
        assert data["throughput"]["result"]["required_hourly_throughput_kg_h"] == pytest.approx(
            1562.50
        )

    def test_preview_empty_inputs(self, client: TestClient) -> None:
        """Empty inputs should still return a valid result (all calculators skipped)."""
        resp = client.post(
            "/api/v1/calculations/core/preview",
            json={"inputs": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data

    def test_preview_with_minimal_inputs(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/calculations/core/preview",
            json={
                "inputs": {
                    "daily_inbound_mass_kg": 10000,
                }
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


# ---------------------------------------------------------------------------
# Save endpoint (with persistence)
# ---------------------------------------------------------------------------


class TestCoreCalculationSave:
    """POST /api/v1/projects/{id}/versions/{version}/calculations/core"""

    def test_save_returns_results(self, client: TestClient) -> None:
        project = _create_project(client)
        project_id = project["id"]
        version = project["current_version_number"]

        # First save some inputs
        client.put(
            f"/api/v1/projects/{project_id}/versions/{version}/inputs",
            json={
                "inputs": {
                    "daily_inbound_mass_kg": 25000,
                    "working_time_h_per_day": 16,
                    "utilization_factor": 0.85,
                }
            },
        )

        # Now run core calculations
        resp = client.post(
            f"/api/v1/projects/{project_id}/versions/{version}/calculations/core",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "throughput" in data

    def test_save_empty_inputs(self, client: TestClient) -> None:
        """Save with empty input_snapshot should succeed (no calculators)."""
        project = _create_project(client)
        project_id = project["id"]
        version = project["current_version_number"]

        resp = client.post(
            f"/api/v1/projects/{project_id}/versions/{version}/calculations/core",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


# ---------------------------------------------------------------------------
# Get endpoint (retrieve persisted snapshot)
# ---------------------------------------------------------------------------


class TestCoreCalculationGet:
    """GET /api/v1/projects/{id}/versions/{version}/calculations/core"""

    def test_get_before_save_returns_error(self, client: TestClient) -> None:
        project = _create_project(client)
        project_id = project["id"]
        version = project["current_version_number"]

        resp = client.get(
            f"/api/v1/projects/{project_id}/versions/{version}/calculations/core",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "NO_CALCULATION"

    def test_get_after_save_returns_snapshot(self, client: TestClient) -> None:
        project = _create_project(client)
        project_id = project["id"]
        version = project["current_version_number"]

        # Save inputs
        client.put(
            f"/api/v1/projects/{project_id}/versions/{version}/inputs",
            json={
                "inputs": {
                    "daily_inbound_mass_kg": 25000,
                    "working_time_h_per_day": 16,
                }
            },
        )

        # Run and save calculations
        client.post(
            f"/api/v1/projects/{project_id}/versions/{version}/calculations/core",
        )

        # Retrieve
        resp = client.get(
            f"/api/v1/projects/{project_id}/versions/{version}/calculations/core",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "throughput" in data
        assert data["orchestration_version"] == "1.0.0"


# ---------------------------------------------------------------------------
# Regression baseline: existing endpoints still work
# ---------------------------------------------------------------------------


class TestExistingEndpointsNotBroken:
    """Ensure existing endpoints are unaffected by Task 4 changes."""

    def test_health_endpoints(self, client: TestClient) -> None:
        resp = client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "live"

        resp = client.get("/health/ready")
        assert resp.status_code == 200

    def test_project_crud(self, client: TestClient) -> None:
        # Create
        resp = client.post(
            "/api/v1/projects",
            json={
                "name": "Regression Test",
                "location": "Test",
                "product_category": "blueberry",
            },
        )
        assert resp.status_code == 200
        project_id = resp.json()["id"]

        # List
        resp = client.get("/api/v1/projects")
        assert resp.status_code == 200
        assert any(p["id"] == project_id for p in resp.json())

        # Get
        resp = client.get(f"/api/v1/projects/{project_id}")
        assert resp.status_code == 200

    def test_demo_planning_run(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/demo/planning-run",
            json={
                "daily_inbound_mass_kg": 25000,
                "working_time_h_per_day": 16,
                "utilization_factor": 0.85,
                "storage_days": 7,
                "finished_storage_days": 25,
                "packaging_storage_days": 7,
                "precooling_required_ratio": 0.8,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "zone_plan" in data
        assert "investment_estimate" in data
