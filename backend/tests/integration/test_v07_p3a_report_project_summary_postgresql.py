"""V0.7 P3A — operator create_app report composition yields project_summary (PostgreSQL)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cold_storage.bootstrap.v06_sample_loader import trusted_sample_client
from tests.integration.test_v06_p5_controlled_acceptance import (
    _assert_reports_engine_dialect,
    _configure_postgresql_env,
    _create_and_generate_report,
    _export_report_json,
    _isolated_process_state,
    _operator_seed,
)
from tests.integration.test_v07_p3a_report_project_summary_sqlite import (
    _assert_project_summary_matches_seed,
)

P3A_CONTRACT = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "tasks"
    / "V0_7-P3A-report-production-composition-contract.md"
)


@pytest.mark.postgresql
def test_v07_p3a_unmodified_create_app_generates_project_summary_postgresql(
    pg_database: str,
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "pg-artifacts"
    artifact_dir.mkdir()
    with _isolated_process_state():
        _configure_postgresql_env(pg_database, artifact_dir)
        with trusted_sample_client(pg_database, storage_dir=artifact_dir) as (client, _service):
            _assert_reports_engine_dialect("postgresql")
            seeded, _by_name = _operator_seed(client)
            report_id, revision_number, _revision = _create_and_generate_report(
                client,
                project_id=seeded.project_id,
                project_version_id=seeded.project_version_id,
            )
            exported = _export_report_json(client, report_id, revision_number)
            _assert_project_summary_matches_seed(
                exported,
                expected_project_name=seeded.project_name,
            )


@pytest.mark.postgresql
def test_v07_p3a_postgresql_env_and_singletons_isolated_before_create_app(
    pg_database: str,
    tmp_path: Path,
) -> None:
    """PostgreSQL backend env must be set before create_app; singletons must be cleared."""
    import cold_storage.bootstrap.dependencies as deps

    artifact_dir = tmp_path / "pg-env-isolation-artifacts"
    artifact_dir.mkdir()
    with _isolated_process_state():
        assert deps._singletons == {}
        _configure_postgresql_env(pg_database, artifact_dir)
        assert __import__("os").environ.get("COLD_STORAGE_DATABASE_BACKEND") == "postgresql"
        assert __import__("os").environ.get("COLD_STORAGE_DATABASE_URL") == pg_database
        with trusted_sample_client(pg_database, storage_dir=artifact_dir) as (client, _service):
            _assert_reports_engine_dialect("postgresql")
            assert "engine" in deps._singletons
            seeded, _by_name = _operator_seed(client)
            report_id, revision_number, _revision = _create_and_generate_report(
                client,
                project_id=seeded.project_id,
                project_version_id=seeded.project_version_id,
            )
            exported = _export_report_json(client, report_id, revision_number)
            _assert_project_summary_matches_seed(
                exported,
                expected_project_name=seeded.project_name,
            )


@pytest.mark.postgresql
def test_v07_p3a_contract_exists_postgresql_matrix() -> None:
    assert P3A_CONTRACT.is_file()
    text = P3A_CONTRACT.read_text(encoding="utf-8")
    assert "PROJECT_SUMMARY_PRESENT_AFTER_GENERATE_POSTGRESQL=PASS" in text
