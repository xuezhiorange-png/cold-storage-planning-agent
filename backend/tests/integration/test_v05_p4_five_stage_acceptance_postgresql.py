"""V0.5 P4 five-stage acceptance integration tests (PostgreSQL)."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "PostgreSQL V0.5 P4 five-stage acceptance tests require DATABASE_BACKEND=postgresql",
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


@pytest.fixture()
def pg_client(pg_engine):
    service = DatabaseProjectService(pg_engine)
    client = TestClient(create_app(project_service=service))
    return client, service, pg_engine


def test_p4_pg_happy_path_sample_seed_persists_canonical_five(pg_client) -> None:
    client, _service, engine = pg_client
    seeded = seed_sample_project(client, load_manifest())
    calculations = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
    ).json()
    by_name = assert_canonical_five_persisted(calculations)
    assert_upstream_lineage_matches_p0(by_name)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        assert session.scalar(select(func.count()).select_from(SourceBindingRecord)) == 1


def test_p4_pg_restart_reopen_returns_same_calculation_ids_and_hashes(pg_client) -> None:
    client, service, _engine = pg_client
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


def test_p4_pg_idempotent_replay_same_key_and_bundle(pg_client) -> None:
    client, _service, engine = pg_client
    manifest = load_manifest()
    seeded = seed_sample_project(client, manifest)
    version_id = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}"
    ).json()["id"]
    bundle = build_bundle_from_manifest(
        manifest,
        project_id=seeded.project_id,
        project_version_id=version_id,
        version_number=seeded.version_number,
    )
    replay = execute_five_stage(
        client,
        project_id=seeded.project_id,
        version_number=seeded.version_number,
        bundle=bundle,
        idempotency_key=manifest["five_stage_execution"]["idempotency_key"],
    )
    assert replay["idempotent_replay"] is True

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


def test_p4_pg_idempotency_payload_conflict_fails_closed(pg_client) -> None:
    client, _service, engine = pg_client
    manifest = load_manifest()
    project_id, version_number, version_id = create_project(client)
    bundle = build_bundle_from_manifest(
        manifest,
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    idempotency_key = f"idem-p4-pg-conflict-{uuid.uuid4().hex[:8]}"
    first = execute_five_stage(
        client,
        project_id=project_id,
        version_number=version_number,
        bundle=bundle,
        idempotency_key=idempotency_key,
    )
    assert "error" not in first, first
    conflicting = dict(bundle)
    conflicting["zone_planning_inputs"] = dict(bundle["zone_planning_inputs"])
    conflicting["zone_planning_inputs"]["daily_inbound_mass_kg"] = dict(
        bundle["zone_planning_inputs"]["daily_inbound_mass_kg"]
    )
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
        assert session.scalar(select(func.count()).select_from(SourceBindingRecord)) == 1


def test_p4_pg_approved_version_locked(pg_client) -> None:
    client, _service, engine = pg_client
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
        idempotency_key=f"idem-p4-pg-approved-{uuid.uuid4().hex[:8]}",
    )
    assert response["error"]["code"] == "PROJECT_VERSION_LOCKED"

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        assert session.scalar(select(func.count()).select_from(CalculationRunRecord)) == 0
        assert session.scalar(select(func.count()).select_from(SourceBindingRecord)) == 0


def test_p4_pg_missing_required_leaf_fails_closed_atomically(pg_client) -> None:
    client, _service, engine = pg_client
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
        idempotency_key=f"idem-p4-pg-missing-{uuid.uuid4().hex[:8]}",
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


def test_p4_pg_workflow_scheme_report_consume_persisted_rows_only(pg_client) -> None:
    client, service, engine = pg_client
    seeded = seed_sample_project(client)
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

    query = ProjectServicePersistedCalculationQuery(service)
    orchestrated = query.get_orchestrated_result(seeded.project_id, version_id)
    assert orchestrated is not None
    assert orchestrated.power_result is not None
    assert orchestrated.power_result.calculator_name == "installed_power"

    sections = read_report_sections_from_persisted(service, seeded.project_id, version_id)
    assert sections
    calculations = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
    ).json()
    persisted_ids = {
        row["calculator_name"]: row["calculation_id"]
        for row in calculations
        if row["calculator_name"] in CANONICAL_CALCULATORS
    }
    section_ids = {section["tool_name"]: section["result_id"] for section in sections}
    assert section_ids.get("installed_power") == persisted_ids["installed_power"]
