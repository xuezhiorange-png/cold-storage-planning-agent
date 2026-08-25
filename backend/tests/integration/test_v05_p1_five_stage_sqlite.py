"""V0.5 P1 five-stage execution integration tests (SQLite)."""

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
        "SQLite V0.5 P1 five-stage tests cannot run on PostgreSQL",
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
            "name": "V05-P1 Five Stage",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version_number = created["current_version_number"]
    version = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()
    return project_id, version_number, version["id"]


def test_five_stage_happy_path_persists_canonical_calculators(migrated_client) -> None:
    client, service, engine = migrated_client
    project_id, version_number, version_id = _create_project(client)
    bundle = build_valid_engineering_input_bundle(
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={"engineering_input_bundle": bundle, "idempotency_key": "idem-v05-p1-happy"},
    ).json()
    assert "error" not in response, response
    assert response["success"] is True
    assert response["idempotent_replay"] is False
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

    for row in calculations:
        if row["calculator_name"] in CANONICAL_CALCULATORS:
            assert row.get("calculation_id")
            assert row.get("result_hash")
            assert "requires_review" in row

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        binding_count = session.scalar(select(func.count()).select_from(SourceBindingRecord))
        assert binding_count == 1


def test_missing_cooling_geometry_fails_closed_without_partial_chain(migrated_client) -> None:
    client, _service, engine = migrated_client
    project_id, version_number, version_id = _create_project(client)
    bundle = build_valid_engineering_input_bundle(
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
        omit_cooling_geometry=True,
    )
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={"engineering_input_bundle": bundle, "idempotency_key": "idem-v05-p1-fail"},
    ).json()
    assert response["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"
    assert "zone_area" in response["error"]["field_path"]

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        calc_count = session.scalar(select(func.count()).select_from(CalculationRunRecord))
        binding_count = session.scalar(select(func.count()).select_from(SourceBindingRecord))
        assert calc_count == 0
        assert binding_count == 0


def test_idempotent_replay_returns_existing_outcome(migrated_client) -> None:
    client, _service, _engine = migrated_client
    project_id, version_number, version_id = _create_project(client)
    bundle = build_valid_engineering_input_bundle(
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    first = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={"engineering_input_bundle": bundle, "idempotency_key": "idem-v05-p1-replay"},
    ).json()
    second = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={"engineering_input_bundle": bundle, "idempotency_key": "idem-v05-p1-replay"},
    ).json()
    assert second["idempotent_replay"] is True
    assert second["source_binding_id"] == first["source_binding_id"]
    assert second["calculation_ids"] == first["calculation_ids"]
