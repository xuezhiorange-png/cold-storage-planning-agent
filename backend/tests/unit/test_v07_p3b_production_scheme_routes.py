"""Unit tests for V0.7 P3B production-scheme public API routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cold_storage.modules.schemes.api.routes import register_scheme_routes
from cold_storage.modules.schemes.application.production_service import ProductionSchemeError
from cold_storage.modules.schemes.domain.errors import (
    ProjectVersionNotFoundError,
    SourceCalculationMissingError,
)
from cold_storage.modules.schemes.domain.models import SchemeRun


@pytest.fixture()
def scheme_service() -> MagicMock:
    service = MagicMock()
    service.resolve_version_id.return_value = "ver-1"
    return service


@pytest.fixture()
def client(scheme_service: MagicMock) -> TestClient:
    app = FastAPI()
    register_scheme_routes(app, lambda: scheme_service)
    return TestClient(app)


def _mock_production_run() -> SchemeRun:
    return SchemeRun(
        id="prod-run-abc",
        project_id="proj-1",
        project_version_id="ver-1",
        weight_set_id="ws-1",
        status="completed",
        generator_version="scheme_generator@1.0.0",
        source_snapshot_hash="combined-hash",
        requires_review=True,
        recommended_scheme_code="balanced",
        database_backend="sqlite",
    )


def test_production_scheme_route_persists_via_production_service(
    client: TestClient,
    scheme_service: MagicMock,
) -> None:
    production_service = MagicMock()
    production_service.generate_production_scheme_run.return_value = _mock_production_run()

    with (
        patch(
            "cold_storage.modules.schemes.api.routes.get_production_scheme_service",
            return_value=production_service,
        ),
        patch(
            "cold_storage.modules.schemes.api.routes._resolve_five_stage_source_binding_id",
            return_value="binding-1",
        ),
        patch(
            "cold_storage.modules.schemes.api.routes.get_settings",
            return_value=MagicMock(database_backend="sqlite"),
        ),
    ):
        response = client.post(
            "/api/v1/projects/proj-1/versions/1/production-scheme-runs",
            json={
                "profile_codes": ["balanced"],
                "weight_set_revision_id": "wrev-1",
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"] == "prod-run-abc"
    assert body["source_mode"] == "production"
    assert body["source_binding_id"] == "binding-1"
    assert body["weight_set_revision_id"] == "wrev-1"
    assert body["combined_source_hash"] == "combined-hash"
    scheme_service.resolve_version_id.assert_called_once_with("proj-1", 1)
    production_service.generate_production_scheme_run.assert_called_once()
    command = production_service.generate_production_scheme_run.call_args.args[0]
    assert command.source_binding_id == "binding-1"
    assert command.weight_set_revision_id == "wrev-1"
    assert command.database_backend == "sqlite"


def test_production_scheme_route_returns_404_for_missing_version(
    client: TestClient,
    scheme_service: MagicMock,
) -> None:
    scheme_service.resolve_version_id.side_effect = ProjectVersionNotFoundError("proj-1", 99)

    response = client.post(
        "/api/v1/projects/proj-1/versions/99/production-scheme-runs",
        json={
            "profile_codes": ["balanced"],
            "weight_set_revision_id": "wrev-1",
        },
    )

    assert response.status_code == 404


def test_production_scheme_route_returns_409_without_source_binding(client: TestClient) -> None:
    with patch(
        "cold_storage.modules.schemes.api.routes._resolve_five_stage_source_binding_id",
        side_effect=SourceCalculationMissingError("missing binding"),
    ):
        response = client.post(
            "/api/v1/projects/proj-1/versions/1/production-scheme-runs",
            json={
                "profile_codes": ["balanced"],
                "weight_set_revision_id": "wrev-1",
            },
        )

    assert response.status_code == 409


def test_production_scheme_route_maps_weight_governance_to_422(client: TestClient) -> None:
    production_service = MagicMock()
    production_service.generate_production_scheme_run.side_effect = ProductionSchemeError(
        "revision_not_found",
        "revision missing",
    )

    with (
        patch(
            "cold_storage.modules.schemes.api.routes.get_production_scheme_service",
            return_value=production_service,
        ),
        patch(
            "cold_storage.modules.schemes.api.routes._resolve_five_stage_source_binding_id",
            return_value="binding-1",
        ),
        patch(
            "cold_storage.modules.schemes.api.routes.get_settings",
            return_value=MagicMock(database_backend="sqlite"),
        ),
    ):
        response = client.post(
            "/api/v1/projects/proj-1/versions/1/production-scheme-runs",
            json={
                "profile_codes": ["balanced"],
                "weight_set_revision_id": "missing-rev",
            },
        )

    assert response.status_code == 422
