"""V0.7 P5 operator trust-loop integration tests (SQLite)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cold_storage.bootstrap.v07_sample_loader import trusted_sample_client, verify_v07_sample
from tests.integration.v07_p5_operator_fixtures import (
    P5_CONTRACT,
    assert_reports_engine_dialect,
    assert_untrusted_mark_reviewed_fail_closed,
    configure_sqlite_env,
    isolated_process_state,
    operator_seed,
    run_trust_loop_lifecycle,
    sqlite_database_url,
)

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "P5 SQLite integration tests require DATABASE_BACKEND != postgresql",
        allow_module_level=True,
    )


def test_v07_p5_contract_exists() -> None:
    assert P5_CONTRACT.is_file()
    text = P5_CONTRACT.read_text(encoding="utf-8")
    assert "TASK=V07_P5_OPERATOR_SAMPLE_RUNBOOK_R1" in text
    assert "TARGET_BRANCH=cursor/v07-p5-operator-sample-runbook-6c68" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "wsr-production-default-v1" in text


@pytest.mark.sqlite
def test_v07_p5_unmodified_create_app_trust_loop_sqlite(tmp_path: Path) -> None:
    database_url, db_path = sqlite_database_url(tmp_path)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_sqlite_env(db_path, artifact_dir)
        with trusted_sample_client(database_url, storage_dir=artifact_dir) as (client, _service):
            assert_reports_engine_dialect("sqlite")
            seeded, _by_name = operator_seed(client)
            lifecycle = run_trust_loop_lifecycle(client, seeded)
            assert_untrusted_mark_reviewed_fail_closed(client, lifecycle["report_id"])


@pytest.mark.sqlite
def test_v07_p5_verify_loader_sqlite(tmp_path: Path) -> None:
    database_url, db_path = sqlite_database_url(tmp_path)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_sqlite_env(db_path, artifact_dir)
        summary = verify_v07_sample(database_url)
        assert summary["verify_status"] == "ok"
        assert summary["submit_review_status"] == 200
        assert len(summary["formal_exports"]) == 4
