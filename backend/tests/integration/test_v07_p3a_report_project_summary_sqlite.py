"""V0.7 P3A — operator create_app report composition yields project_summary (SQLite)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cold_storage.bootstrap.v06_sample_loader import trusted_sample_client
from tests.integration.test_v06_p5_controlled_acceptance import (
    _assert_reports_engine_dialect,
    _configure_sqlite_env,
    _create_and_generate_report,
    _export_report_json,
    _isolated_process_state,
    _operator_seed,
    _sqlite_database_url,
)

P3A_CONTRACT = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "tasks"
    / "V0_7-P3A-report-production-composition-contract.md"
)


def _assert_project_summary_matches_seed(
    exported: dict[str, Any],
    *,
    expected_project_name: str,
) -> None:
    content = exported.get("content") or exported
    project_summary = content.get("project_summary")
    assert project_summary is not None, "project_summary must be present after generate"
    assert project_summary.get("project_name") == expected_project_name


def test_v07_p3a_contract_exists() -> None:
    assert P3A_CONTRACT.is_file()
    text = P3A_CONTRACT.read_text(encoding="utf-8")
    assert "TASK=V07_P3A_REPORT_PRODUCTION_COMPOSITION_R1" in text
    assert "TARGET_BRANCH=cursor/v07-p3a-report-production-composition-6c68" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "project_service=get_project_service()" not in text


@pytest.mark.sqlite
def test_v07_p3a_unmodified_create_app_generates_project_summary_sqlite(
    tmp_path: Path,
) -> None:
    database_url, db_path = _sqlite_database_url(tmp_path)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    with _isolated_process_state():
        _configure_sqlite_env(db_path, artifact_dir)
        with trusted_sample_client(database_url, storage_dir=artifact_dir) as (client, _service):
            _assert_reports_engine_dialect("sqlite")
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


@pytest.mark.sqlite
def test_v07_p3a_contract_scans_bootstrap_app_injects_project_service() -> None:
    app_source = (
        Path(__file__).resolve().parents[3]
        / "backend"
        / "src"
        / "cold_storage"
        / "bootstrap"
        / "app.py"
    ).read_text(encoding="utf-8")
    assert "def _get_report_service" in app_source
    assert "project_service=get_project_service()" in app_source
    assert "RealReportDataProvider(" in app_source
