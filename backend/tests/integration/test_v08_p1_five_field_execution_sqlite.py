"""V0.8 P1 five-field operator execution integration tests (SQLite)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite V0.8 P1 five-field tests cannot run on PostgreSQL",
        allow_module_level=True,
    )

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.orchestration.infrastructure.orm import SourceBindingRecord
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord
from tests.integration.v05_p1_bundle_fixtures import build_valid_engineering_input_bundle

BACKEND_DIR = Path(__file__).resolve().parents[2]
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
def migrated_client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        db_path.unlink(missing_ok=True)
        pytest.fail(f"Alembic upgrade failed:\n{result.stderr}\n{result.stdout}")
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _rec) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    service = DatabaseProjectService(engine)
    client = TestClient(create_app(project_service=service))
    yield client, service, engine
    engine.dispose()
    db_path.unlink(missing_ok=True)


def _create_project(client: TestClient) -> tuple[str, int, str]:
    created = client.post(
        "/api/v1/projects",
        json={
            "name": "V08-P1 Five Field",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version_number = created["current_version_number"]
    version = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()
    return project_id, version_number, version["id"]


def test_operator_five_field_happy_path_persists_all_stages(migrated_client) -> None:
    client, _service, engine = migrated_client
    project_id, version_number, _version_id = _create_project(client)
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={
            "operator_process_input": _operator_process_input(),
            "idempotency_key": "idem-v08-p1-five-field",
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
        binding_count = session.scalar(select(func.count()).select_from(SourceBindingRecord))
        calc_count = session.scalar(select(func.count()).select_from(CalculationRunRecord))
        assert binding_count == 1
        assert calc_count == 5


def test_full_bundle_path_still_works(migrated_client) -> None:
    client, _service, _engine = migrated_client
    project_id, version_number, version_id = _create_project(client)
    bundle = build_valid_engineering_input_bundle(
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={"engineering_input_bundle": bundle, "idempotency_key": "idem-v08-p1-full-bundle"},
    ).json()
    assert "error" not in response, response
    assert response["success"] is True


def test_missing_operator_key_fails_closed_without_partial_chain(migrated_client) -> None:
    client, _service, engine = migrated_client
    project_id, version_number, _version_id = _create_project(client)
    payload = _operator_process_input()
    payload["zone_planning_inputs"].pop("daily_inbound_mass_kg")
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={"operator_process_input": payload, "idempotency_key": "idem-v08-p1-missing"},
    ).json()
    assert response["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        calc_count = session.scalar(select(func.count()).select_from(CalculationRunRecord))
        binding_count = session.scalar(select(func.count()).select_from(SourceBindingRecord))
        assert calc_count == 0
        assert binding_count == 0
