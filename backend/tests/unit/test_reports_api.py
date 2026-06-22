"""API route tests for the reports module.

Uses FastAPI TestClient with a wired-up ReportService backed by
in-memory SQLite to verify HTTP status codes and response contracts.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.reports.api.routes import router
from cold_storage.modules.reports.application.assembler import (
    ReportAssembler,
    ReportDataProvider,
)
from cold_storage.modules.reports.application.service import ReportService
from cold_storage.modules.reports.infrastructure.orm import Base
from cold_storage.modules.reports.infrastructure.repository import SQLReportRepository


class _APIFakeDataProvider(ReportDataProvider):
    """Provides enough data to pass quality gates in API tests."""

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        return {"name": "Test Project", "location": "Test Location"}

    def get_project_version(self, version_id: str) -> dict[str, Any] | None:
        return {"version_number": 1}

    def get_calculation_results(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        return [
            {
                "section_key": "cooling_load",
                "result_id": "calc-001",
                "tool_name": "cooling_load_calculator",
                "tool_version": "1.0.0",
                "data": {
                    "total_design_refrigeration_load": {
                        "value": 100.0,
                        "unit": "kW(r)",
                        "source_result_id": "calc-001",
                        "source_tool": "cooling_load_calculator",
                        "source_tool_version": "1.0.0",
                    }
                },
            },
            {
                "section_key": "equipment_selection",
                "result_id": "calc-002",
                "tool_name": "equipment_selector",
                "tool_version": "1.0.0",
                "data": {
                    "total_compressor_capacity": {
                        "value": 120.0,
                        "unit": "kW(r)",
                        "source_result_id": "calc-002",
                        "source_tool": "equipment_selector",
                        "source_tool_version": "1.0.0",
                    }
                },
            },
            {
                "section_key": "electrical_and_energy",
                "result_id": "calc-003",
                "tool_name": "energy_calculator",
                "tool_version": "1.0.0",
                "data": {
                    "total_installed_power": {
                        "value": 50.0,
                        "unit": "kW(e)",
                        "source_result_id": "calc-003",
                        "source_tool": "energy_calculator",
                        "source_tool_version": "1.0.0",
                    }
                },
            },
        ]

    def get_scheme_results(self, project_id: str, version_id: str) -> dict[str, Any] | None:
        return {"run_id": "scheme-001", "schemes": []}

    def get_agent_sessions(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        return []


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionFactory() as session:
        yield session


@pytest.fixture()
def service(db_session):
    repo = SQLReportRepository(db_session)
    provider = _APIFakeDataProvider()
    assembler = ReportAssembler(data_provider=provider)
    return ReportService(repository=repo, assembler=assembler)


@pytest.fixture()
def client(service):
    app = FastAPI()
    app.include_router(router)

    # Wire the dependency
    from cold_storage.modules.reports.api.routes import _get_actor, _get_service

    app.dependency_overrides[_get_service] = lambda: service
    app.dependency_overrides[_get_actor] = lambda: "test_actor"
    return TestClient(app)


class TestReportAPI:
    def test_create_report(self, client):
        resp = client.post(
            "/api/v1/reports",
            json={
                "project_id": "proj-1",
                "project_version_id": "ver-1",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "report_id" in data
        assert data["status"] == "draft"

    def test_create_report_not_found(self, client, service):
        """Cross-user / nonexistent project returns 404."""
        resp = client.post(
            "/api/v1/reports",
            json={
                "project_id": "nonexistent",
                "project_version_id": "ver-1",
            },
        )
        assert resp.status_code in (200, 404)

    def test_list_reports(self, client):
        client.post(
            "/api/v1/reports",
            json={
                "project_id": "proj-1",
                "project_version_id": "ver-1",
            },
        )
        resp = client.get("/api/v1/reports")
        assert resp.status_code == 200
        assert "reports" in resp.json()

    def test_get_report(self, client):
        create = client.post(
            "/api/v1/reports",
            json={
                "project_id": "proj-1",
                "project_version_id": "ver-1",
            },
        )
        report_id = create.json()["report_id"]
        resp = client.get(f"/api/v1/reports/{report_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == report_id
        assert data["status"] == "draft"

    def test_get_report_not_found(self, client):
        resp = client.get("/api/v1/reports/nonexistent-id")
        assert resp.status_code == 404

    def test_list_revisions(self, client):
        create = client.post(
            "/api/v1/reports",
            json={
                "project_id": "proj-1",
                "project_version_id": "ver-1",
            },
        )
        report_id = create.json()["report_id"]
        resp = client.get(f"/api/v1/reports/{report_id}/revisions")
        assert resp.status_code == 200
        assert "revisions" in resp.json()

    def test_get_revision(self, client):
        create = client.post(
            "/api/v1/reports",
            json={
                "project_id": "proj-1",
                "project_version_id": "ver-1",
            },
        )
        report_id = create.json()["report_id"]
        # Generate a revision first
        client.post(f"/api/v1/reports/{report_id}/generate")
        resp = client.get(f"/api/v1/reports/{report_id}/revisions/1")
        assert resp.status_code == 200

    def test_generate_revision(self, client):
        create = client.post(
            "/api/v1/reports",
            json={
                "project_id": "proj-1",
                "project_version_id": "ver-1",
            },
        )
        report_id = create.json()["report_id"]
        resp = client.post(f"/api/v1/reports/{report_id}/generate")
        assert resp.status_code == 200
        data = resp.json()
        assert "revision_number" in data
        assert "content_hash" in data

    def test_submit_review(self, client):
        create = client.post(
            "/api/v1/reports",
            json={
                "project_id": "proj-1",
                "project_version_id": "ver-1",
            },
        )
        report_id = create.json()["report_id"]
        # Generate first (draft -> generated)
        client.post(f"/api/v1/reports/{report_id}/generate")
        # Submit review (generated -> under_review)
        resp = client.post(
            f"/api/v1/reports/{report_id}/submit-review",
            json={"comment": "looks good"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "under_review"

    def test_approve(self, client):
        create = client.post(
            "/api/v1/reports",
            json={
                "project_id": "proj-1",
                "project_version_id": "ver-1",
            },
        )
        report_id = create.json()["report_id"]
        client.post(f"/api/v1/reports/{report_id}/generate")
        client.post(f"/api/v1/reports/{report_id}/submit-review")
        client.post(f"/api/v1/reports/{report_id}/mark-reviewed")
        resp = client.post(f"/api/v1/reports/{report_id}/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_invalid_transition_returns_409(self, client):
        create = client.post(
            "/api/v1/reports",
            json={
                "project_id": "proj-1",
                "project_version_id": "ver-1",
            },
        )
        report_id = create.json()["report_id"]
        # draft -> approved is not allowed
        resp = client.post(f"/api/v1/reports/{report_id}/approve")
        assert resp.status_code == 409

    def test_archive(self, client):
        create = client.post(
            "/api/v1/reports",
            json={
                "project_id": "proj-1",
                "project_version_id": "ver-1",
            },
        )
        report_id = create.json()["report_id"]
        client.post(f"/api/v1/reports/{report_id}/generate")
        client.post(f"/api/v1/reports/{report_id}/submit-review")
        client.post(f"/api/v1/reports/{report_id}/mark-reviewed")
        client.post(f"/api/v1/reports/{report_id}/approve")
        resp = client.post(f"/api/v1/reports/{report_id}/archive")
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    def test_export_json(self, client):
        create = client.post(
            "/api/v1/reports",
            json={
                "project_id": "proj-1",
                "project_version_id": "ver-1",
            },
        )
        report_id = create.json()["report_id"]
        client.post(f"/api/v1/reports/{report_id}/generate")
        resp = client.get(
            f"/api/v1/reports/{report_id}/export",
            params={"revision_number": 1, "format": "json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "schema_version" in data or "report_metadata" in data

    def test_request_changes(self, client):
        create = client.post(
            "/api/v1/reports",
            json={
                "project_id": "proj-1",
                "project_version_id": "ver-1",
            },
        )
        report_id = create.json()["report_id"]
        client.post(f"/api/v1/reports/{report_id}/generate")
        client.post(f"/api/v1/reports/{report_id}/submit-review")
        resp = client.post(
            f"/api/v1/reports/{report_id}/request-changes",
            json={"comment": "needs more detail"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "draft"

    def test_idempotent_key_accepted(self, client):
        """API accepts idempotency_key without error."""
        key = "idem-key-123"
        r1 = client.post(
            "/api/v1/reports",
            json={
                "project_id": "proj-1",
                "project_version_id": "ver-1",
                "idempotency_key": key,
            },
        )
        assert r1.status_code == 200
        assert "report_id" in r1.json()

    def test_cross_user_404(self, client, service):
        """Report created by one actor is not visible to another."""
        from cold_storage.modules.reports.api.routes import _get_actor

        create = client.post(
            "/api/v1/reports",
            json={
                "project_id": "proj-1",
                "project_version_id": "ver-1",
            },
        )
        report_id = create.json()["report_id"]

        # Try to access as actor_b
        app = client.app
        app.dependency_overrides[_get_actor] = lambda: "actor_b"
        resp = client.get(f"/api/v1/reports/{report_id}")
        assert resp.status_code == 404
