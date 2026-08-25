"""V0.5 P1 five-stage execution integration tests (PostgreSQL)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "PostgreSQL V0.5 P1 five-stage tests require DATABASE_BACKEND=postgresql",
        allow_module_level=True,
    )

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.orchestration.infrastructure.orm import SourceBindingRecord
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord
from tests.integration.v05_p1_bundle_fixtures import build_valid_engineering_input_bundle

CANONICAL_CALCULATORS = {
    "cold_room_zone_plan",
    "cooling_load",
    "equipment",
    "installed_power",
    "investment_estimate",
}


@pytest.fixture()
def pg_client(pg_engine):
    service = DatabaseProjectService(pg_engine)
    client = TestClient(create_app(project_service=service))
    return client, service, pg_engine


def _create_project(client: TestClient) -> tuple[str, int, str]:
    created = client.post(
        "/api/v1/projects",
        json={
            "name": "V05-P1 Five Stage PG",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version_number = created["current_version_number"]
    version = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()
    return project_id, version_number, version["id"]


def test_postgresql_five_stage_happy_path(pg_client) -> None:
    client, _service, engine = pg_client
    project_id, version_number, version_id = _create_project(client)
    bundle = build_valid_engineering_input_bundle(
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={"engineering_input_bundle": bundle, "idempotency_key": "idem-v05-p1-pg-happy"},
    ).json()
    assert "error" not in response, response
    assert response["success"] is True

    calculations = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/calculations"
    ).json()
    calculator_names = {row["calculator_name"] for row in calculations}
    assert CANONICAL_CALCULATORS.issubset(calculator_names)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        assert session.scalar(select(func.count()).select_from(SourceBindingRecord)) == 1


def test_postgresql_missing_cooling_geometry_atomicity(pg_client) -> None:
    client, _service, engine = pg_client
    project_id, version_number, version_id = _create_project(client)
    bundle = build_valid_engineering_input_bundle(
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
        omit_cooling_geometry=True,
    )
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={"engineering_input_bundle": bundle, "idempotency_key": "idem-v05-p1-pg-fail"},
    ).json()
    assert response["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        assert session.scalar(select(func.count()).select_from(CalculationRunRecord)) == 0
        assert session.scalar(select(func.count()).select_from(SourceBindingRecord)) == 0
