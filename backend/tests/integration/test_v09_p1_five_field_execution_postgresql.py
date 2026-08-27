"""V0.9 P1 five-field operator execution integration tests (PostgreSQL)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "PostgreSQL V0.9 P1 five-field tests require DATABASE_BACKEND=postgresql",
        allow_module_level=True,
    )

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.orchestration.infrastructure.orm import SourceBindingRecord
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord

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
        "schema_version": "1.1.0",
        "zone_planning_inputs": {
            "daily_inbound_mass_kg": {"value": "20000", "unit": "kg/day", "state": "provided"},
            "finished_storage_days": {"value": "7", "unit": "day", "state": "provided"},
            "frozen_storage_days": {"value": "10", "unit": "day", "state": "provided"},
            "main_packaging_storage_days": {"value": "4", "unit": "day", "state": "provided"},
            "auxiliary_packaging_storage_days": {"value": "12", "unit": "day", "state": "provided"},
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
            "name": "V09-P1 Five Field PG",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version_number = created["current_version_number"]
    version = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()
    return project_id, version_number, version["id"]


def test_postgresql_v09_operator_five_field_happy_path(pg_client) -> None:
    client, _service, engine = pg_client
    project_id, version_number, _version_id = _create_project(client)
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={
            "operator_process_input": _operator_process_input(),
            "idempotency_key": "idem-v09-p1-pg-five-field",
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


def test_postgresql_v09_missing_operator_key_zero_canonical_rows(pg_client) -> None:
    client, _service, engine = pg_client
    project_id, version_number, _version_id = _create_project(client)
    payload = _operator_process_input()
    payload["zone_planning_inputs"].pop("main_packaging_storage_days")
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={"operator_process_input": payload, "idempotency_key": "idem-v09-p1-pg-missing"},
    ).json()
    assert response["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        assert session.scalar(select(func.count()).select_from(CalculationRunRecord)) == 0
        assert session.scalar(select(func.count()).select_from(SourceBindingRecord)) == 0
