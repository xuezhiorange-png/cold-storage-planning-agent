"""Integration tests for coefficient registry API routes.

Tests the full HTTP layer including request validation, error handling,
and response serialization.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.coefficients.infrastructure.database import (
    DatabaseCoefficientService,
)
from cold_storage.modules.projects.infrastructure.orm import Base


@pytest.fixture()
def engine():
    """Create an in-memory SQLite engine for testing."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Create all tables from both bases
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def service(engine):
    """Create a DatabaseCoefficientService."""
    return DatabaseCoefficientService(engine)


@pytest.fixture()
def app(service):
    """Create a FastAPI app with coefficient routes."""
    application = create_app()
    # Register coefficient routes
    from cold_storage.modules.coefficients.api.routes import register_coefficient_routes

    register_coefficient_routes(application, service)
    return application


@pytest.fixture()
def client(app):
    """Create a test client."""
    return TestClient(app)


# ===========================================================================
# 1. Definition API tests
# ===========================================================================


class TestDefinitionAPI:
    def test_list_empty(self, client: TestClient) -> None:
        response = client.get("/api/v1/coefficients")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_definition(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/coefficients",
            json={
                "code": "test.code",
                "name": "Test",
                "description": "Desc",
                "category": "area",
                "canonical_unit": "ratio",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "test.code"
        assert data["id"]

    def test_create_duplicate_definition(self, client: TestClient) -> None:
        client.post(
            "/api/v1/coefficients",
            json={
                "code": "test.code",
                "name": "Test",
                "description": "Desc",
                "category": "area",
                "canonical_unit": "ratio",
            },
        )
        response = client.post(
            "/api/v1/coefficients",
            json={
                "code": "test.code",
                "name": "Test2",
                "description": "Desc2",
                "category": "area",
                "canonical_unit": "ratio",
            },
        )
        assert response.status_code == 409

    def test_get_definition(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/v1/coefficients",
            json={
                "code": "test.code",
                "name": "Test",
                "description": "Desc",
                "category": "area",
                "canonical_unit": "ratio",
            },
        )
        definition_id = create_resp.json()["id"]
        response = client.get(f"/api/v1/coefficients/{definition_id}")
        assert response.status_code == 200
        assert response.json()["code"] == "test.code"

    def test_get_definition_not_found(self, client: TestClient) -> None:
        response = client.get("/api/v1/coefficients/nonexistent")
        assert response.status_code == 404

    def test_list_with_category_filter(self, client: TestClient) -> None:
        client.post(
            "/api/v1/coefficients",
            json={
                "code": "area.ratio",
                "name": "Area",
                "description": "Desc",
                "category": "area",
                "canonical_unit": "ratio",
            },
        )
        client.post(
            "/api/v1/coefficients",
            json={
                "code": "power.kw",
                "name": "Power",
                "description": "Desc",
                "category": "power",
                "canonical_unit": "kW",
            },
        )
        response = client.get("/api/v1/coefficients?category=area")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["code"] == "area.ratio"


# ===========================================================================
# 2. Revision API tests
# ===========================================================================


class TestRevisionAPI:
    def _create_definition(self, client: TestClient) -> str:
        response = client.post(
            "/api/v1/coefficients",
            json={
                "code": "test.code",
                "name": "Test",
                "description": "Desc",
                "category": "area",
                "canonical_unit": "ratio",
            },
        )
        return response.json()["id"]

    def test_create_revision(self, client: TestClient) -> None:
        def_id = self._create_definition(client)
        response = client.post(
            f"/api/v1/coefficients/{def_id}/revisions",
            json={"value_decimal": "1.15", "source_type": "demo"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value_decimal"] == "1.15"
        assert data["status"] == "draft"
        assert data["revision_number"] == 1

    def test_create_revision_not_found(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/coefficients/nonexistent/revisions",
            json={"value_decimal": "1.15"},
        )
        assert response.status_code == 404

    def test_list_revisions(self, client: TestClient) -> None:
        def_id = self._create_definition(client)
        client.post(
            f"/api/v1/coefficients/{def_id}/revisions",
            json={"value_decimal": "1.15"},
        )
        response = client.get(f"/api/v1/coefficients/{def_id}/revisions")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_get_revision(self, client: TestClient) -> None:
        def_id = self._create_definition(client)
        create_resp = client.post(
            f"/api/v1/coefficients/{def_id}/revisions",
            json={"value_decimal": "1.15"},
        )
        rev_id = create_resp.json()["id"]
        response = client.get(f"/api/v1/coefficients/{def_id}/revisions/{rev_id}")
        assert response.status_code == 200
        assert response.json()["id"] == rev_id

    def test_get_revision_not_found(self, client: TestClient) -> None:
        def_id = self._create_definition(client)
        response = client.get(f"/api/v1/coefficients/{def_id}/revisions/nonexistent")
        assert response.status_code == 404


# ===========================================================================
# 3. State transition API tests
# ===========================================================================


class TestTransitionAPI:
    def _create_and_get_revision(self, client: TestClient) -> tuple[str, str]:
        def_resp = client.post(
            "/api/v1/coefficients",
            json={
                "code": "test.code",
                "name": "Test",
                "description": "Desc",
                "category": "area",
                "canonical_unit": "ratio",
            },
        )
        def_id = def_resp.json()["id"]
        rev_resp = client.post(
            f"/api/v1/coefficients/{def_id}/revisions",
            json={"value_decimal": "1.15"},
        )
        rev_id = rev_resp.json()["id"]
        return def_id, rev_id

    def test_review(self, client: TestClient) -> None:
        def_id, rev_id = self._create_and_get_revision(client)
        response = client.post(f"/api/v1/coefficients/{def_id}/revisions/{rev_id}/review")
        assert response.status_code == 200
        assert response.json()["status"] == "reviewed"

    def test_approve(self, client: TestClient) -> None:
        def_id, rev_id = self._create_and_get_revision(client)
        client.post(f"/api/v1/coefficients/{def_id}/revisions/{rev_id}/review")
        response = client.post(f"/api/v1/coefficients/{def_id}/revisions/{rev_id}/approve")
        assert response.status_code == 200
        assert response.json()["status"] == "approved"

    def test_withdraw(self, client: TestClient) -> None:
        def_id, rev_id = self._create_and_get_revision(client)
        client.post(f"/api/v1/coefficients/{def_id}/revisions/{rev_id}/review")
        client.post(f"/api/v1/coefficients/{def_id}/revisions/{rev_id}/approve")
        response = client.post(f"/api/v1/coefficients/{def_id}/revisions/{rev_id}/withdraw")
        assert response.status_code == 200
        assert response.json()["status"] == "withdrawn"

    def test_invalid_transition_returns_409(self, client: TestClient) -> None:
        def_id, rev_id = self._create_and_get_revision(client)
        # Try to approve a draft (invalid transition)
        response = client.post(f"/api/v1/coefficients/{def_id}/revisions/{rev_id}/approve")
        assert response.status_code == 409

    def test_approved_immutable(self, client: TestClient) -> None:
        def_id, rev_id = self._create_and_get_revision(client)
        client.post(f"/api/v1/coefficients/{def_id}/revisions/{rev_id}/review")
        client.post(f"/api/v1/coefficients/{def_id}/revisions/{rev_id}/approve")
        # Try to submit for review (invalid transition from approved)
        response = client.post(f"/api/v1/coefficients/{def_id}/revisions/{rev_id}/review")
        assert response.status_code == 409


# ===========================================================================
# 4. Resolution API tests
# ===========================================================================


class TestResolveAPI:
    def test_resolve_empty(self, client: TestClient) -> None:
        response = client.post("/api/v1/coefficients/resolve", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["items"] == {}

    def test_resolve_with_approved(self, client: TestClient) -> None:
        # Create definition and approve a revision
        def_resp = client.post(
            "/api/v1/coefficients",
            json={
                "code": "area.ratio",
                "name": "Area Ratio",
                "description": "Desc",
                "category": "area",
                "canonical_unit": "ratio",
            },
        )
        def_id = def_resp.json()["id"]
        rev_resp = client.post(
            f"/api/v1/coefficients/{def_id}/revisions",
            json={"value_decimal": "1.15"},
        )
        rev_id = rev_resp.json()["id"]
        client.post(f"/api/v1/coefficients/{def_id}/revisions/{rev_id}/review")
        client.post(f"/api/v1/coefficients/{def_id}/revisions/{rev_id}/approve")

        response = client.post("/api/v1/coefficients/resolve", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert "area.ratio" in data["items"]
        assert data["items"]["area.ratio"]["value"] == "1.15"

    def test_resolve_specific_codes(self, client: TestClient) -> None:
        # Create two definitions
        for code in ["area.ratio", "power.kw"]:
            def_resp = client.post(
                "/api/v1/coefficients",
                json={
                    "code": code,
                    "name": code,
                    "description": "Desc",
                    "category": "area" if "area" in code else "power",
                    "canonical_unit": "ratio",
                },
            )
            def_id = def_resp.json()["id"]
            rev_resp = client.post(
                f"/api/v1/coefficients/{def_id}/revisions",
                json={"value_decimal": "1.0"},
            )
            rev_id = rev_resp.json()["id"]
            client.post(f"/api/v1/coefficients/{def_id}/revisions/{rev_id}/review")
            client.post(f"/api/v1/coefficients/{def_id}/revisions/{rev_id}/approve")

        response = client.post(
            "/api/v1/coefficients/resolve",
            json={"codes": ["area.ratio"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert "area.ratio" in data["items"]
