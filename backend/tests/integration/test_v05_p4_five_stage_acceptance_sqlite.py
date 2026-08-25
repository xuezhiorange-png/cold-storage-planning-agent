"""V0.5 P4 five-stage acceptance integration tests (SQLite)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite V0.5 P4 five-stage acceptance tests cannot run on PostgreSQL",
        allow_module_level=True,
    )

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.v05_local_sample import load_manifest
from cold_storage.modules.orchestration.infrastructure.orm import SourceBindingRecord
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord
from cold_storage.modules.reports.application.persisted_calculation_reads import (
    ProjectServicePersistedCalculationQuery,
)
from tests.integration.v05_p4_acceptance_fixtures import (
    CANONICAL_CALCULATORS,
    assert_canonical_five_persisted,
    assert_upstream_lineage_matches_p0,
    assert_workflow_not_blocked_by_missing_canonical_slots,
    build_bundle_from_manifest,
    bundle_with_removed_key,
    create_project,
    execute_five_stage,
    generate_scheme_from_persisted,
    read_report_sections_from_persisted,
    seed_sample_project,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


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


def test_p4_happy_path_sample_seed_persists_canonical_five_with_lineage(migrated_client) -> None:
    client, _service, engine = migrated_client
    manifest = load_manifest()
    seeded = seed_sample_project(client, manifest)
    assert seeded.five_stage_success is True

    calculations = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
    ).json()
    by_name = assert_canonical_five_persisted(calculations)
    assert_upstream_lineage_matches_p0(by_name)
    assert "power_configuration" not in by_name or by_name.get("installed_power") is not None

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        binding_count = session.scalar(select(func.count()).select_from(SourceBindingRecord))
        assert binding_count == 1


def test_p4_restart_reopen_returns_same_calculation_ids_and_hashes(migrated_client) -> None:
    client, service, _engine = migrated_client
    seeded = seed_sample_project(client)
    first = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
    ).json()
    first_by_name = assert_canonical_five_persisted(first)

    with TestClient(create_app(project_service=service)) as reopened:
        second = reopened.get(
            f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
        ).json()
    second_by_name = assert_canonical_five_persisted(second)
    for name in CANONICAL_CALCULATORS:
        assert second_by_name[name]["calculation_id"] == first_by_name[name]["calculation_id"]
        assert second_by_name[name]["result_hash"] == first_by_name[name]["result_hash"]


def test_p4_idempotent_replay_same_key_and_bundle(migrated_client) -> None:
    client, _service, engine = migrated_client
    manifest = load_manifest()
    seeded = seed_sample_project(client, manifest)
    bundle = build_bundle_from_manifest(
        manifest,
        project_id=seeded.project_id,
        project_version_id=client.get(
            f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}"
        ).json()["id"],
        version_number=seeded.version_number,
    )
    idempotency_key = manifest["five_stage_execution"]["idempotency_key"]
    replay = execute_five_stage(
        client,
        project_id=seeded.project_id,
        version_number=seeded.version_number,
        bundle=bundle,
        idempotency_key=idempotency_key,
    )
    assert replay["idempotent_replay"] is True
    assert replay["success"] is True

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        canonical_count = session.scalar(
            select(func.count())
            .select_from(CalculationRunRecord)
            .where(
                CalculationRunRecord.project_version_id
                == client.get(
                    f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}"
                ).json()["id"],
                CalculationRunRecord.calculator_name.in_(CANONICAL_CALCULATORS),
            )
        )
        assert canonical_count == 5


def test_p4_idempotency_payload_conflict_fails_closed(migrated_client) -> None:
    client, _service, engine = migrated_client
    manifest = load_manifest()
    project_id, version_number, version_id = create_project(client)
    bundle = build_bundle_from_manifest(
        manifest,
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    idempotency_key = f"idem-p4-conflict-{uuid.uuid4().hex[:8]}"
    first = execute_five_stage(
        client,
        project_id=project_id,
        version_number=version_number,
        bundle=bundle,
        idempotency_key=idempotency_key,
    )
    assert "error" not in first, first

    conflicting = copy_bundle_edit(
        bundle, "zone_planning_inputs.daily_inbound_mass_kg.value", "25000"
    )
    response = execute_five_stage(
        client,
        project_id=project_id,
        version_number=version_number,
        bundle=conflicting,
        idempotency_key=idempotency_key,
    )
    assert response["error"]["code"] == "IDEMPOTENCY_PAYLOAD_CONFLICT"

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        binding_count = session.scalar(select(func.count()).select_from(SourceBindingRecord))
        assert binding_count == 1


def test_p4_approved_version_locked(migrated_client) -> None:
    client, _service, engine = migrated_client
    manifest = load_manifest()
    project_id, version_number, version_id = create_project(client)
    bundle = build_bundle_from_manifest(
        manifest,
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    client.post(f"/api/v1/projects/{project_id}/versions/{version_number}/submit")
    client.post(f"/api/v1/projects/{project_id}/versions/{version_number}/review")
    client.post(f"/api/v1/projects/{project_id}/versions/{version_number}/approve")

    response = execute_five_stage(
        client,
        project_id=project_id,
        version_number=version_number,
        bundle=bundle,
        idempotency_key=f"idem-p4-approved-{uuid.uuid4().hex[:8]}",
    )
    assert response["error"]["code"] == "PROJECT_VERSION_LOCKED"

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        assert session.scalar(select(func.count()).select_from(CalculationRunRecord)) == 0
        assert session.scalar(select(func.count()).select_from(SourceBindingRecord)) == 0


def test_p4_archived_version_locked(migrated_client) -> None:
    client, _service, engine = migrated_client
    manifest = load_manifest()
    project_id, version_number, version_id = create_project(client)
    bundle = build_bundle_from_manifest(
        manifest,
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    client.post(f"/api/v1/projects/{project_id}/versions/{version_number}/submit")
    client.post(f"/api/v1/projects/{project_id}/versions/{version_number}/review")
    client.post(f"/api/v1/projects/{project_id}/versions/{version_number}/approve")
    client.post(f"/api/v1/projects/{project_id}/versions/{version_number}/archive")

    response = execute_five_stage(
        client,
        project_id=project_id,
        version_number=version_number,
        bundle=bundle,
        idempotency_key=f"idem-p4-archived-{uuid.uuid4().hex[:8]}",
    )
    assert response["error"]["code"] == "PROJECT_VERSION_LOCKED"

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        assert session.scalar(select(func.count()).select_from(CalculationRunRecord)) == 0
        assert session.scalar(select(func.count()).select_from(SourceBindingRecord)) == 0


def test_p4_missing_condensing_temperature_fails_closed_atomically(migrated_client) -> None:
    client, _service, engine = migrated_client
    manifest = load_manifest()
    project_id, version_number, version_id = create_project(client)
    bundle = bundle_with_removed_key(
        build_bundle_from_manifest(
            manifest,
            project_id=project_id,
            project_version_id=version_id,
            version_number=version_number,
        ),
        "equipment_inputs.condensing_temperature_c",
    )
    response = execute_five_stage(
        client,
        project_id=project_id,
        version_number=version_number,
        bundle=bundle,
        idempotency_key=f"idem-p4-missing-cond-{uuid.uuid4().hex[:8]}",
    )
    assert response["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        canonical_count = session.scalar(
            select(func.count())
            .select_from(CalculationRunRecord)
            .where(
                CalculationRunRecord.project_version_id == version_id,
                CalculationRunRecord.calculator_name.in_(CANONICAL_CALCULATORS),
            )
        )
        assert canonical_count == 0
        assert session.scalar(select(func.count()).select_from(SourceBindingRecord)) == 0


def test_p4_missing_cooling_geometry_fails_closed_atomically(migrated_client) -> None:
    client, _service, engine = migrated_client
    manifest = load_manifest()
    project_id, version_number, version_id = create_project(client)
    bundle = bundle_with_removed_key(
        build_bundle_from_manifest(
            manifest,
            project_id=project_id,
            project_version_id=version_id,
            version_number=version_number,
        ),
        "cooling_load_inputs.zones[0].zone_area",
    )
    response = execute_five_stage(
        client,
        project_id=project_id,
        version_number=version_number,
        bundle=bundle,
        idempotency_key=f"idem-p4-missing-geom-{uuid.uuid4().hex[:8]}",
    )
    assert response["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        canonical_count = session.scalar(
            select(func.count())
            .select_from(CalculationRunRecord)
            .where(
                CalculationRunRecord.project_version_id == version_id,
                CalculationRunRecord.calculator_name.in_(CANONICAL_CALCULATORS),
            )
        )
        assert canonical_count == 0


def test_p4_workflow_scheme_report_consume_persisted_rows_only(migrated_client) -> None:
    client, service, engine = migrated_client
    seeded = seed_sample_project(client)
    calculations = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
    ).json()
    assert_canonical_five_persisted(calculations)
    version_id = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}"
    ).json()["id"]

    assert_workflow_not_blocked_by_missing_canonical_slots(
        client, seeded.project_id, seeded.version_number
    )

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        scheme_payload = generate_scheme_from_persisted(
            session, seeded.project_id, seeded.version_number
        )
        assert scheme_payload["status"] == "completed"
        schemes = scheme_payload.get("schemes") or []
        assert schemes
        installed_values = {item.get("installed_power_kw_e") for item in schemes}
        assert "999.0" not in installed_values

    query = ProjectServicePersistedCalculationQuery(service)
    orchestrated = query.get_orchestrated_result(seeded.project_id, version_id)
    assert orchestrated is not None
    assert orchestrated.power_result is not None
    assert orchestrated.power_result.calculator_name == "installed_power"

    sections = read_report_sections_from_persisted(service, seeded.project_id, version_id)
    assert sections
    persisted_ids = {
        row["calculator_name"]: row["calculation_id"]
        for row in calculations
        if row["calculator_name"] in CANONICAL_CALCULATORS
    }
    section_ids = {section["tool_name"]: section["result_id"] for section in sections}
    assert section_ids.get("cold_room_zone_plan") == persisted_ids["cold_room_zone_plan"]
    assert section_ids.get("installed_power") == persisted_ids["installed_power"]


def copy_bundle_edit(bundle: dict, dotted_path: str, value: object) -> dict:
    import copy

    edited = copy.deepcopy(bundle)
    parts = dotted_path.split(".")
    cursor = edited
    for part in parts[:-1]:
        cursor = cursor[part]
    cursor[parts[-1]] = value
    return edited
