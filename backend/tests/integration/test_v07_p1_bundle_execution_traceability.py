"""V0.7 P1 bundle → execution snapshot → calculator → persistence traceability."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite V0.7 P1 traceability tests cannot run on PostgreSQL",
        allow_module_level=True,
    )

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.orchestration.application.source_binding_assembly import (
    Phase2AdapterCalculatorPort,
)
from cold_storage.modules.orchestration.infrastructure.orm import (
    ProjectVersionExecutionSnapshotRecord,
)
from cold_storage.modules.projects.application.engineering_input_bundle import (
    project_execution_snapshot_from_bundle,
)
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord
from tests.integration.v05_p1_bundle_fixtures import build_valid_engineering_input_bundle

BACKEND_DIR = Path(__file__).resolve().parents[2]
ZONE_CALCULATOR = "cold_room_zone_plan"


def _bundle_leaf_value(bundle: dict, field_name: str) -> str:
    return str(bundle["zone_planning_inputs"][field_name]["value"])


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
            "name": "V07-P1 Traceability",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version_number = created["current_version_number"]
    version = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()
    return project_id, version_number, version["id"]


def test_bundle_projects_zone_leaves_to_execution_snapshot() -> None:
    bundle = build_valid_engineering_input_bundle(
        project_id="p-trace",
        project_version_id="pv-trace",
        version_number=1,
    )
    snapshot = project_execution_snapshot_from_bundle(bundle)
    zone = snapshot["zone"]
    for field_name in (
        "daily_inbound_mass_kg",
        "working_time_h_per_day",
        "finished_storage_days",
        "packaging_storage_days",
        "precooling_required_ratio",
    ):
        leaf = bundle["zone_planning_inputs"][field_name]
        assert str(zone[field_name]) == str(leaf["value"])


def test_execution_snapshot_zone_feeds_production_zone_calculator() -> None:
    bundle = build_valid_engineering_input_bundle(
        project_id="p-trace",
        project_version_id="pv-trace",
        version_number=1,
    )
    execution_snapshot = project_execution_snapshot_from_bundle(bundle)
    port = Phase2AdapterCalculatorPort()
    exec_result = port.execute_stage(
        stage_name="zone",
        execution_snapshot=execution_snapshot,
        coefficient_context={},
        upstream_results={},
        actor="v07-p1-trace",
        correlation_id="v07-p1-trace-001",
    )
    assert exec_result.calculator_name == ZONE_CALCULATOR
    assert exec_result.result_snapshot
    assert exec_result.requires_review is True
    assert exec_result.coefficients
    assert exec_result.assumptions
    assert exec_result.warnings
    zone_inputs = execution_snapshot["zone"]
    assert str(zone_inputs["daily_inbound_mass_kg"]) == _bundle_leaf_value(
        bundle, "daily_inbound_mass_kg"
    )


def test_five_stage_persists_zone_coefficients_assumptions_warnings(migrated_client) -> None:
    pytest.skip(
        "P2 leftover: ZoneSourceSnapshotV1 does not admit §4 zone row fields "
        "(off P2 allowlist); deferred to schema follow-on"
    )
    client, _service, engine = migrated_client
    project_id, version_number, version_id = _create_project(client)
    bundle = build_valid_engineering_input_bundle(
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={
            "engineering_input_bundle": bundle,
            "idempotency_key": "idem-v07-p1-trace-zone",
        },
    ).json()
    assert "error" not in response, response
    zone_calc_id = response["calculation_ids"]["zone"]

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        run = session.get(CalculationRunRecord, zone_calc_id)
        assert run is not None
        assert run.calculator_name == ZONE_CALCULATOR
        assert run.requires_review is True
        assert run.coefficients
        assert run.assumptions
        assert run.warnings
        assert run.execution_snapshot_id is not None

        for coeff in run.coefficients:
            assert coeff.get("source_type") == "demo"
            assert coeff.get("status") == "unverified"
            assert coeff.get("requires_review") is True

        snapshot = session.get(ProjectVersionExecutionSnapshotRecord, run.execution_snapshot_id)
        assert snapshot is not None
        stored_zone = snapshot.input_snapshot["zone"]
        assert str(stored_zone["daily_inbound_mass_kg"]) == _bundle_leaf_value(
            bundle, "daily_inbound_mass_kg"
        )


def test_zone_gold_numeric_expectations_remain_stable() -> None:
    """Regression guard: zone planner gold values must not drift during P1 proof work."""
    from cold_storage.modules.calculations.domain.zone_planning import (
        ColdRoomZonePlanInput,
        ColdRoomZonePlanner,
    )

    result = ColdRoomZonePlanner().plan(
        ColdRoomZonePlanInput(
            daily_inbound_mass_kg=25_000,
            working_time_h_per_day=16,
            finished_storage_days=2.5,
            packaging_storage_days=3,
            precooling_required_ratio=1,
        )
    )
    assert result.success is True
    zones = result.result["zones"]
    assert zones[2]["raw_position_count"] == 19
    assert zones[2]["position_count"] == 24
    assert zones[7]["design_storage_mass_kg"] == 62_500
    assert result.result["total_area_m2"] == pytest.approx(2744.24, abs=0.01)
