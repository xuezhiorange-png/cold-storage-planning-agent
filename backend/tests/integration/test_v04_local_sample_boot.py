"""V0.4 P3 boot + sample-load smoke for the local sqlite path."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.v04_local_sample import (
    EXPECTED_PERSISTED_CALCULATORS,
    load_manifest,
    seed_v04_local_sample,
)
from cold_storage.modules.projects.infrastructure.database import create_database_project_service

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture()
def migrated_sqlite_url(tmp_path: Path) -> str:
    db_path = tmp_path / "v04_local_sample.db"
    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    env["COLD_STORAGE_DATABASE_BACKEND"] = "sqlite"
    env["COLD_STORAGE_SQLITE_PATH"] = str(db_path)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stderr}\n{result.stdout}")
    return f"sqlite:///{db_path}"


def test_v04_local_sample_boot_and_load_smoke(migrated_sqlite_url: str) -> None:
    manifest = load_manifest()
    service = create_database_project_service(migrated_sqlite_url)

    with TestClient(create_app(project_service=service)) as client:
        live = client.get("/health/live")
        assert live.status_code == 200
        assert live.json()["status"] == "live"

        seeded = seed_v04_local_sample(client, manifest=manifest)
        assert seeded.sample_id == "v04-local-workbench"
        assert seeded.planning_run_success is True
        assert set(seeded.persisted_calculator_names) >= set(EXPECTED_PERSISTED_CALCULATORS)

        project = client.get(f"/api/v1/projects/{seeded.project_id}").json()
        assert project["name"] == manifest["project"]["name"]
        assert project["current_version_number"] == seeded.version_number

        version = client.get(
            f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}"
        ).json()
        assert (
            version["input_snapshot"]["daily_inbound_mass_kg"]
            == manifest["inputs"]["daily_inbound_mass_kg"]
        )

        calculations = client.get(
            f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
        ).json()
        calculator_names = {item["calculator_name"] for item in calculations}
        assert calculator_names >= set(EXPECTED_PERSISTED_CALCULATORS)

        workflow = client.get(
            f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/workflow"
        ).json()
        assert workflow["project_context"]["project_id"] == seeded.project_id

        # Idempotent re-seed should reuse the same project identity.
        reseeded = seed_v04_local_sample(client, manifest=manifest)
        assert reseeded.project_id == seeded.project_id
        assert reseeded.created is False
