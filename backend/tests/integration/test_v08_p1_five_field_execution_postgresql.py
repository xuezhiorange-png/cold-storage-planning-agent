"""V0.8 P1 five-field operator execution integration tests (PostgreSQL)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "PostgreSQL V0.8 P1 five-field tests require DATABASE_BACKEND=postgresql",
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


def _operator_process_input() -> dict[str, object]:
    return {
        "schema_id": "OperatorProcessInputV1",
        "schema_version": "1.0.0",
        "zone_planning_inputs": {
            "daily_inbound_mass_kg": {"value": "20000", "unit": "kg/day", "state": "provided"},
            "working_time_h_per_day": {"value": "16", "unit": "h/day", "state": "provided"},
            "finished_storage_days": {"value": "7", "unit": "day", "state": "provided"},
            "packaging_storage_days": {"value": "1", "unit": "day", "state": "provided"},
            "precooling_required_ratio": {"value": "0.6", "unit": "ratio", "state": "provided"},
        },
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
            "name": "V08-P1 Five Field PG",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version_number = created["current_version_number"]
    version = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()
    return project_id, version_number, version["id"]


def test_postgresql_operator_five_field_happy_path(pg_client) -> None:
    client, _service, engine = pg_client
    project_id, version_number, _version_id = _create_project(client)
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={
            "operator_process_input": _operator_process_input(),
            "idempotency_key": "idem-v08-p1-pg-five-field",
        },
    ).json()
    assert "error" not in response, response
    assert response["success"] is True
    assert set(response["calculation_ids"]) == {
        "zone",
        "cooling_load",
        "equipment",
        "power",
        "investment",
    }

    calculations = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/calculations"
    ).json()
    calculator_names = {row["calculator_name"] for row in calculations}
    assert CANONICAL_CALCULATORS.issubset(calculator_names)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        assert session.scalar(select(func.count()).select_from(SourceBindingRecord)) == 1
        assert session.scalar(select(func.count()).select_from(CalculationRunRecord)) == 5


def test_postgresql_full_bundle_path_still_works(pg_client) -> None:
    client, _service, _engine = pg_client
    project_id, version_number, version_id = _create_project(client)
    bundle = build_valid_engineering_input_bundle(
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={"engineering_input_bundle": bundle, "idempotency_key": "idem-v08-p1-pg-full"},
    ).json()
    assert "error" not in response, response
    assert response["success"] is True
