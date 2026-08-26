"""V0.7 P4 consumer hash repair integration tests (SQLite)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite V0.7 P4 hash repair tests cannot run on PostgreSQL",
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

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture()
def migrated_client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    env["PYTHONPATH"] = str(BACKEND_DIR / "src")
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


def test_p4_workflow_and_scheme_hashes_match_api_fingerprint(migrated_client) -> None:
    client, _service, engine = migrated_client
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


def test_p4_no_false_scheme_source_snapshot_mismatch_when_aligned(migrated_client) -> None:
    client, _service, engine = migrated_client
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

    schemes_projection = workflow.get("schemes", {})
    assert schemes_projection.get("source_snapshot_hash") in {"", scheme_combined}
