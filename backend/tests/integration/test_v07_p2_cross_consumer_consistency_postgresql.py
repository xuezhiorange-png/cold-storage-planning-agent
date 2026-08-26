"""V0.7 P2 cross-consumer consistency integration tests (PostgreSQL)."""

from __future__ import annotations

import copy
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "PostgreSQL V0.7 P2 consistency tests require DATABASE_BACKEND=postgresql",
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

pytestmark = pytest.mark.postgresql


@pytest.fixture()
def pg_client(pg_engine):
    service = DatabaseProjectService(pg_engine)
    with TestClient(create_app(project_service=service)) as client:
        yield client, service, pg_engine


def test_p2_pg_authoritative_parity_across_consumers(pg_client) -> None:
    client, service, engine = pg_client
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


def test_p2_pg_matches_cross_backend_golden(pg_client) -> None:
    client, service, engine = pg_client
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


def test_p2_pg_idempotent_replay_stable_hashes(pg_client) -> None:
    client, service, engine = pg_client
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

    evidence = collect_cross_consumer_evidence(
        client,
        service,
        engine,
        project_id=project_id,
        version_number=version_number,
        version_id=version_id,
    )
    assert_authoritative_hash_parity(evidence)


def test_p2_pg_missing_key_fails_closed(pg_client) -> None:
    client, _service, engine = pg_client
    created = client.post(
        "/api/v1/projects",
        json={
            "name": f"V07-P2 PG missing {uuid.uuid4().hex[:8]}",
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


def test_p2_pg_idempotency_payload_conflict_fails_closed(pg_client) -> None:
    client, _service, engine = pg_client
    manifest = load_v07_manifest()
    created = client.post(
        "/api/v1/projects",
        json={
            "name": f"V07-P2 PG idem {uuid.uuid4().hex[:8]}",
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
    idempotency_key = f"v07-p2-pg-conflict-{uuid.uuid4().hex[:8]}"
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
