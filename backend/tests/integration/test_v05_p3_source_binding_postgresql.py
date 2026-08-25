"""V0.5 P3 source-binding alignment integration tests (PostgreSQL)."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "PostgreSQL V0.5 P3 source-binding tests require DATABASE_BACKEND=postgresql",
        allow_module_level=True,
    )

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from cold_storage.modules.reports.application.persisted_calculation_reads import (
    ProjectServicePersistedCalculationQuery,
)
from tests.integration.v05_p1_bundle_fixtures import build_valid_engineering_input_bundle
from tests.integration.v05_p3_canonical_fixtures import CANONICAL_CALCULATORS


@pytest.fixture()
def pg_client(pg_engine):
    service = DatabaseProjectService(pg_engine)
    client = TestClient(create_app(project_service=service))
    return client, service, pg_engine


def _create_project(client: TestClient) -> tuple[str, int, str]:
    created = client.post(
        "/api/v1/projects",
        json={
            "name": "V05-P3 Binding PG",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version_number = created["current_version_number"]
    version = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()
    return project_id, version_number, version["id"]


def test_p3_pg_happy_path_canonical_five_accepted(pg_client) -> None:
    client, service, _engine = pg_client
    project_id, version_number, version_id = _create_project(client)
    bundle = build_valid_engineering_input_bundle(
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    execution = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={"engineering_input_bundle": bundle, "idempotency_key": f"idem-pg-{uuid.uuid4()}"},
    ).json()
    assert "error" not in execution, execution

    calculations = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/calculations"
    ).json()
    assert CANONICAL_CALCULATORS.issubset({row["calculator_name"] for row in calculations})

    workflow = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/workflow"
    ).json()
    calc_step = next(
        step for step in workflow["steps"] if step["step"] == "DETERMINISTIC_CALCULATION"
    )
    assert calc_step["status"] in {"COMPLETED", "REVIEW_REQUIRED"}

    query = ProjectServicePersistedCalculationQuery(service)
    orchestrated = query.get_orchestrated_result(project_id, version_id)
    assert orchestrated is not None
    assert orchestrated.power_result is not None
    assert orchestrated.power_result.calculator_name == "installed_power"
