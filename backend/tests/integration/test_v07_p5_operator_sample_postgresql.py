"""V0.7 P5 operator trust-loop integration tests (PostgreSQL)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cold_storage.bootstrap.v07_sample_loader import trusted_sample_client, verify_v07_sample
from tests.integration.v07_p5_operator_fixtures import (
    assert_reports_engine_dialect,
    assert_untrusted_mark_reviewed_fail_closed,
    configure_postgresql_env,
    isolated_process_state,
    operator_seed,
    run_trust_loop_lifecycle,
)

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "P5 PostgreSQL integration tests require DATABASE_BACKEND=postgresql",
        allow_module_level=True,
    )


@pytest.mark.postgresql
def test_v07_p5_unmodified_create_app_trust_loop_postgresql(
    pg_database: str,
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "pg-artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_postgresql_env(pg_database, artifact_dir)
        with trusted_sample_client(pg_database, storage_dir=artifact_dir) as (client, _service):
            assert_reports_engine_dialect("postgresql")
            seeded, _by_name = operator_seed(client)
            lifecycle = run_trust_loop_lifecycle(client, seeded)
            assert_untrusted_mark_reviewed_fail_closed(client, lifecycle["report_id"])


@pytest.mark.postgresql
def test_v07_p5_postgresql_env_and_singletons_isolated_before_create_app(
    pg_database: str,
    tmp_path: Path,
) -> None:
    import cold_storage.bootstrap.dependencies as deps

    artifact_dir = tmp_path / "pg-env-isolation-artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        assert deps._singletons == {}
        configure_postgresql_env(pg_database, artifact_dir)
        assert os.environ.get("COLD_STORAGE_DATABASE_BACKEND") == "postgresql"
        assert os.environ.get("COLD_STORAGE_DATABASE_URL") == pg_database
        with trusted_sample_client(pg_database, storage_dir=artifact_dir) as (client, _service):
            assert_reports_engine_dialect("postgresql")
            assert "engine" in deps._singletons
            seeded, _by_name = operator_seed(client)
            run_trust_loop_lifecycle(client, seeded)


@pytest.mark.postgresql
def test_v07_p5_verify_loader_postgresql(pg_database: str, tmp_path: Path) -> None:
    artifact_dir = tmp_path / "pg-verify-artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_postgresql_env(pg_database, artifact_dir)
        summary = verify_v07_sample(pg_database)
        assert summary["verify_status"] == "ok"
        assert summary["submit_review_status"] == 200
