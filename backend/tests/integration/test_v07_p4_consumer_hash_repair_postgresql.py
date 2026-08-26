"""V0.7 P4 consumer hash repair integration tests (PostgreSQL)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "PostgreSQL V0.7 P4 hash repair tests require DATABASE_BACKEND=postgresql",
        allow_module_level=True,
    )

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.orchestration.domain.consumer_bindings import CANONICAL_STAGE_ORDER
from cold_storage.modules.orchestration.infrastructure.orm import SourceBindingRecord
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord
from cold_storage.modules.schemes.application.canonical_source_reads import (
    require_canonical_scheme_sources,
)
from tests.integration.v05_p4_acceptance_fixtures import calculations_by_name
from tests.integration.v07_p2_consistency_evidence import (
    generate_production_scheme_run,
    seed_v07_consistency_project,
)
from tests.integration.v07_p2_numeric_projection_map import calculator_for_stage

pytestmark = pytest.mark.postgresql


@pytest.fixture()
def pg_client(pg_engine):
    service = DatabaseProjectService(pg_engine)
    with TestClient(create_app(project_service=service)) as client:
        yield client, service, pg_engine


def _load_scheme_bundle(session, *, project_id: str, version_id: str):
    records = list(
        session.scalars(
            select(CalculationRunRecord).where(
                CalculationRunRecord.project_id == project_id,
                CalculationRunRecord.project_version_id == version_id,
            )
        )
    )
    return require_canonical_scheme_sources(
        records,
        project_id=project_id,
        project_version_id=version_id,
    )


def _workflow_runs_by_calculator(
    client: TestClient, project_id: str, version_number: int
) -> dict[str, dict]:
    workflow = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/workflow"
    ).json()
    runs = workflow.get("calculations", {}).get("runs", [])
    indexed: dict[str, dict] = {}
    for run in runs:
        name = run.get("calculator_name")
        if isinstance(name, str):
            indexed[name] = run
    return indexed


def test_p4_pg_workflow_and_scheme_hashes_match_api_fingerprint(pg_client) -> None:
    client, _service, engine = pg_client
    project_id, version_number, version_id = seed_v07_consistency_project(client)

    api_rows = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/calculations"
    ).json()
    api_by_calculator = calculations_by_name(api_rows)
    workflow_runs = _workflow_runs_by_calculator(client, project_id, version_number)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        scheme_bundle = _load_scheme_bundle(
            session,
            project_id=project_id,
            version_id=version_id,
        )

    for stage in CANONICAL_STAGE_ORDER:
        calculator = calculator_for_stage(stage)
        authoritative = str(api_by_calculator[calculator]["result_hash"])
        assert authoritative, f"{calculator} missing API result_hash"

        workflow_hash = str(workflow_runs[calculator]["result_hash"])
        assert workflow_hash == authoritative, (
            f"workflow result_hash mismatch for {calculator!r}: "
            f"workflow={workflow_hash!r} api={authoritative!r}"
        )

        scheme_hash = scheme_bundle.source_snapshot_hashes[stage]
        assert scheme_hash == authoritative, (
            f"scheme canonical read hash mismatch for {stage!r}: "
            f"scheme={scheme_hash!r} api={authoritative!r}"
        )


def test_p4_pg_no_false_scheme_source_snapshot_mismatch_when_aligned(pg_client) -> None:
    client, _service, engine = pg_client
    project_id, version_number, version_id = seed_v07_consistency_project(client)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        binding = session.scalar(
            select(SourceBindingRecord).where(
                SourceBindingRecord.project_id == project_id,
                SourceBindingRecord.project_version_id == version_id,
            )
        )
        assert binding is not None
        binding_id = binding.id
        binding_combined = str(binding.combined_source_hash)

    scheme_run = generate_production_scheme_run(engine, binding_id=binding_id)
    scheme_combined = str(scheme_run.combined_source_hash or scheme_run.source_snapshot_hash)
    assert scheme_combined == binding_combined

    workflow = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/workflow"
    ).json()
    stale_reasons = workflow.get("project_context", {}).get("revision_stale_reasons", [])
    assert "scheme_source_snapshot_mismatch" not in stale_reasons
