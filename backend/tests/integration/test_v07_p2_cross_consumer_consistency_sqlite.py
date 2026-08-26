"""V0.7 P2 cross-consumer consistency integration tests (SQLite)."""

from __future__ import annotations

import copy
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
        "SQLite V0.7 P2 consistency tests cannot run on PostgreSQL",
        allow_module_level=True,
    )

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.v05_local_sample import hydrate_engineering_input_bundle
from cold_storage.modules.orchestration.infrastructure.orm import SourceBindingRecord
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord
from tests.integration.v05_p4_acceptance_fixtures import execute_five_stage
from tests.integration.v07_p2_consistency_evidence import (
    CANONICAL_CALCULATORS,
    assert_authoritative_hash_parity,
    assert_canonical_five_present,
    assert_identity_parity,
    assert_known_drift_recorded,
    assert_matches_golden,
    assert_numeric_projection_parity,
    assert_zero_canonical_rows,
    collect_cross_consumer_evidence,
    execute_missing_key_bundle,
    load_golden_artifact,
    load_v07_manifest,
    seed_v07_consistency_project,
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


def test_p2_authoritative_parity_across_consumers(migrated_client) -> None:
    client, service, engine = migrated_client
    project_id, version_number, version_id = seed_v07_consistency_project(client)
    evidence = collect_cross_consumer_evidence(
        client,
        service,
        engine,
        project_id=project_id,
        version_number=version_number,
        version_id=version_id,
    )
    assert_canonical_five_present(evidence)
    assert_authoritative_hash_parity(evidence)
    assert_identity_parity(evidence)
    assert_numeric_projection_parity(evidence)
    assert_known_drift_recorded(evidence)


def test_p2_idempotent_replay_stable_hashes(migrated_client) -> None:
    client, service, engine = migrated_client
    project_id, version_number, version_id = seed_v07_consistency_project(client)
    manifest = load_v07_manifest()
    bundle = hydrate_engineering_input_bundle(
        manifest,
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    replay = execute_five_stage(
        client,
        project_id=project_id,
        version_number=version_number,
        bundle=bundle,
        idempotency_key=manifest["five_stage_execution"]["idempotency_key"],
    )
    assert replay.get("idempotent_replay") is True
    assert replay.get("success") is True

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        canonical_count = session.scalar(
            select(func.count())
            .select_from(CalculationRunRecord)
            .where(
                CalculationRunRecord.project_version_id == version_id,
                CalculationRunRecord.calculator_name.in_(CANONICAL_CALCULATORS),
            )
        )
        assert canonical_count == 5

    first = collect_cross_consumer_evidence(
        client,
        service,
        engine,
        project_id=project_id,
        version_number=version_number,
        version_id=version_id,
    )
    assert_authoritative_hash_parity(first)


def test_p2_restart_reopen_preserves_ids_and_hashes(migrated_client) -> None:
    client, service, engine = migrated_client
    project_id, version_number, version_id = seed_v07_consistency_project(client)
    first = collect_cross_consumer_evidence(
        client,
        service,
        engine,
        project_id=project_id,
        version_number=version_number,
        version_id=version_id,
    )

    with TestClient(create_app(project_service=service)) as reopened:
        second = collect_cross_consumer_evidence(
            reopened,
            service,
            engine,
            project_id=project_id,
            version_number=version_number,
            version_id=version_id,
        )
    for name in CANONICAL_CALCULATORS:
        first_row = first.api_by_calculator[name]
        second_row = second.api_by_calculator[name]
        assert second_row["calculation_id"] == first_row["calculation_id"]
        assert second_row["result_hash"] == first_row["result_hash"]


def test_p2_missing_condensing_temperature_fails_closed(migrated_client) -> None:
    client, _service, engine = migrated_client
    created = client.post(
        "/api/v1/projects",
        json={
            "name": f"V07-P2 missing cond {uuid.uuid4().hex[:8]}",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version_number = created["current_version_number"]
    version_id = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()["id"]

    response = execute_missing_key_bundle(
        client,
        project_id=project_id,
        version_number=version_number,
        version_id=version_id,
        dotted_path="equipment_inputs.condensing_temperature_c",
    )
    assert response["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        assert_zero_canonical_rows(session, version_id)


def test_p2_missing_cooling_geometry_fails_closed(migrated_client) -> None:
    client, _service, engine = migrated_client
    created = client.post(
        "/api/v1/projects",
        json={
            "name": f"V07-P2 missing geom {uuid.uuid4().hex[:8]}",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version_number = created["current_version_number"]
    version_id = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()["id"]

    response = execute_missing_key_bundle(
        client,
        project_id=project_id,
        version_number=version_number,
        version_id=version_id,
        dotted_path="cooling_load_inputs.zones[0].zone_area",
    )
    assert response["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        assert_zero_canonical_rows(session, version_id)


def test_p2_sqlite_matches_cross_backend_golden(migrated_client) -> None:
    client, service, engine = migrated_client
    project_id, version_number, version_id = seed_v07_consistency_project(client)
    evidence = collect_cross_consumer_evidence(
        client,
        service,
        engine,
        project_id=project_id,
        version_number=version_number,
        version_id=version_id,
    )
    golden = load_golden_artifact()
    assert_matches_golden(evidence, golden)


def test_p2_idempotency_payload_conflict_fails_closed(migrated_client) -> None:
    client, _service, engine = migrated_client
    manifest = load_v07_manifest()
    created = client.post(
        "/api/v1/projects",
        json={
            "name": f"V07-P2 idem conflict {uuid.uuid4().hex[:8]}",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version_number = created["current_version_number"]
    version_id = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()["id"]
    bundle = hydrate_engineering_input_bundle(
        manifest,
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    idempotency_key = f"v07-p2-conflict-{uuid.uuid4().hex[:8]}"
    first = execute_five_stage(
        client,
        project_id=project_id,
        version_number=version_number,
        bundle=bundle,
        idempotency_key=idempotency_key,
    )
    assert "error" not in first, first

    conflicting = copy.deepcopy(bundle)
    conflicting["zone_planning_inputs"]["daily_inbound_mass_kg"]["value"] = "25000"
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
