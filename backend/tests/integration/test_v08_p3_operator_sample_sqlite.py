"""V0.8 P3 operator-minimal sample integration tests (SQLite)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from cold_storage.bootstrap.v08_sample_loader import (
    load_manifest,
    trusted_sample_client,
    verify_v08_sample,
)
from cold_storage.modules.orchestration.infrastructure.orm import SourceBindingRecord
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord
from tests.integration.v08_p3_operator_fixtures import (
    P3_CONTRACT,
    assert_five_calculation_runs,
    assert_untrusted_mark_reviewed_fail_closed,
    configure_sqlite_env,
    isolated_process_state,
    operator_process_input_from_manifest,
    operator_seed,
    run_trust_loop_lifecycle,
    sqlite_database_url,
)

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "P3 SQLite integration tests require DATABASE_BACKEND != postgresql",
        allow_module_level=True,
    )


def test_v08_p3_contract_exists() -> None:
    assert P3_CONTRACT.is_file()
    text = P3_CONTRACT.read_text(encoding="utf-8")
    assert "TASK=V08_P3_OPERATOR_SAMPLE_RUNBOOK_R1" in text
    assert "TARGET_BRANCH=cursor/v08-p3-operator-sample-runbook-6c68" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "v08-process-input" in text
    assert "engineering_input_bundle" in text


def test_v08_p3_manifest_has_five_keys_only() -> None:
    p3_manifest = load_manifest()
    assert "engineering_input_bundle" not in p3_manifest
    operator_input = p3_manifest["operator_process_input"]
    assert operator_input["schema_id"] == "OperatorProcessInputV1"
    zone_inputs = operator_input["zone_planning_inputs"]
    assert set(zone_inputs) == {
        "daily_inbound_mass_kg",
        "working_time_h_per_day",
        "finished_storage_days",
        "packaging_storage_days",
        "precooling_required_ratio",
    }


@pytest.mark.sqlite
def test_v08_p3_unmodified_create_app_five_stage_sqlite(tmp_path: Path) -> None:
    database_url, db_path = sqlite_database_url(tmp_path)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_sqlite_env(db_path, artifact_dir)
        with trusted_sample_client(database_url, storage_dir=artifact_dir) as (client, _service):
            seeded, by_name = operator_seed(client)
            assert len(by_name) >= 5
            assert seeded.five_stage_success is True
            lifecycle = run_trust_loop_lifecycle(client, seeded)
            assert_untrusted_mark_reviewed_fail_closed(client, lifecycle["report_id"])


@pytest.mark.sqlite
def test_v08_p3_missing_key_fail_closed_sqlite(tmp_path: Path) -> None:
    p3_manifest = load_manifest()
    database_url, db_path = sqlite_database_url(tmp_path)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_sqlite_env(db_path, artifact_dir)
        with trusted_sample_client(database_url, storage_dir=artifact_dir) as (client, service):
            created = client.post(
                "/api/v1/projects",
                json={
                    "name": "V08-P3 Missing Key",
                    "location": "山东",
                    "product_category": "blueberry",
                },
            )
            assert created.status_code == 200, created.text
            project = created.json()
            project_id = project["id"]
            version_number = project["current_version_number"]

            payload = operator_process_input_from_manifest(p3_manifest)
            payload["zone_planning_inputs"].pop("daily_inbound_mass_kg")
            response = client.post(
                f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
                json={
                    "operator_process_input": payload,
                    "idempotency_key": "idem-v08-p3-missing-key",
                },
            ).json()
            assert response["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"

            engine = service.engine
            with sessionmaker(bind=engine, expire_on_commit=False)() as session:
                calc_count = session.scalar(select(func.count()).select_from(CalculationRunRecord))
                binding_count = session.scalar(
                    select(func.count()).select_from(SourceBindingRecord)
                )
                assert calc_count == 0
                assert binding_count == 0


@pytest.mark.sqlite
def test_v08_p3_verify_loader_sqlite(tmp_path: Path) -> None:
    database_url, db_path = sqlite_database_url(tmp_path)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_sqlite_env(db_path, artifact_dir)
        summary = verify_v08_sample(database_url)
        assert summary["verify_status"] == "ok"
        assert summary["submit_review_status"] == 200
        assert len(summary["formal_exports"]) == 4


@pytest.mark.sqlite
def test_v08_p3_seed_persists_five_calculation_runs_sqlite(tmp_path: Path) -> None:
    database_url, db_path = sqlite_database_url(tmp_path)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_sqlite_env(db_path, artifact_dir)
        with trusted_sample_client(database_url, storage_dir=artifact_dir) as (client, service):
            operator_seed(client)
            assert_five_calculation_runs(service.engine)
