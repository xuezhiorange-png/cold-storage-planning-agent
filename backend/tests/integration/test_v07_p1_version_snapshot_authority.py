"""V0.7 P1 version snapshot authority on the five-stage execution path."""

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
        "SQLite V0.7 P1 snapshot authority tests cannot run on PostgreSQL",
        allow_module_level=True,
    )

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.orchestration.infrastructure.orm import (
    ProjectVersionExecutionSnapshotRecord,
)
from cold_storage.modules.projects.application.engineering_input_bundle import (
    BUNDLE_SCHEMA_ID,
    bundle_payload_hash,
    project_execution_snapshot_from_bundle,
    validate_engineering_input_bundle,
)
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from cold_storage.modules.projects.infrastructure.orm import ProjectVersionRecord
from tests.integration.v05_p1_bundle_fixtures import build_valid_engineering_input_bundle

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
    db_path.unlink(missing_ok=True)


def _create_project(client: TestClient) -> tuple[str, int, str]:
    created = client.post(
        "/api/v1/projects",
        json={
            "name": "V07-P1 Snapshot Authority",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version_number = created["current_version_number"]
    version = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()
    return project_id, version_number, version["id"]


def test_engineering_input_bundle_is_required_schema_for_execution() -> None:
    bundle = build_valid_engineering_input_bundle(
        project_id="p-auth",
        project_version_id="pv-auth",
        version_number=1,
    )
    validate_engineering_input_bundle(bundle)
    assert bundle["schema_id"] == BUNDLE_SCHEMA_ID
    assert bundle_payload_hash(bundle)


def test_project_version_input_snapshot_is_not_bundle_complete(migrated_client) -> None:
    client, _service, engine = migrated_client
    project_id, version_number, version_id = _create_project(client)
    bundle = build_valid_engineering_input_bundle(
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        version = session.get(ProjectVersionRecord, version_id)
        assert version is not None
        input_snapshot = dict(version.input_snapshot)
        assert input_snapshot.get("schema_id") != BUNDLE_SCHEMA_ID
        assert "coefficient_context" not in input_snapshot
        assert "review_metadata" not in input_snapshot


def test_five_stage_execution_persists_bundle_projected_snapshot(migrated_client) -> None:
    client, _service, engine = migrated_client
    project_id, version_number, version_id = _create_project(client)
    bundle = build_valid_engineering_input_bundle(
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    projected = project_execution_snapshot_from_bundle(bundle)
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={
            "engineering_input_bundle": bundle,
            "idempotency_key": "idem-v07-p1-snapshot-auth",
        },
    ).json()
    assert "error" not in response, response

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        snapshots = session.scalars(
            select(ProjectVersionExecutionSnapshotRecord).where(
                ProjectVersionExecutionSnapshotRecord.project_version_id == version_id
            )
        ).all()
        assert snapshots, "five-stage execution must persist an execution snapshot"
        stored = snapshots[0].input_snapshot
        assert stored["zone"]["daily_inbound_mass_kg"] == projected["zone"]["daily_inbound_mass_kg"]
        assert "cooling_load" in stored
        assert "equipment" in stored
        assert "power" in stored
        assert "investment" in stored
