from __future__ import annotations

from pathlib import Path

import pytest

from cold_storage.evaluation.errors import StaleEvaluationArtifactsError
from cold_storage.evaluation.manifest import load_and_validate_manifest
from cold_storage.evaluation.pilot_reports import (
    PILOT_CHECK_ID,
    PILOT_RESULT_SCHEMA_VERSION,
    PilotVerificationError,
    verify_multilingual_report_pilot,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "evaluation" / "data"


@pytest.mark.parametrize(
    ("file_name", "suite_id", "backend_value"),
    [
        (
            "task011-pilot-sqlite.v1.json",
            "task011-pilot-multilingual-sqlite",
            "sqlite",
        ),
        (
            "task011-pilot-postgresql.v1.json",
            "task011-pilot-multilingual-postgresql",
            "postgresql",
        ),
    ],
)
def test_backend_pilot_manifests_are_frozen_single_scenario(
    file_name: str,
    suite_id: str,
    backend_value: str,
) -> None:
    manifest = load_and_validate_manifest((DATA_DIR / file_name).resolve())
    assert manifest.schema_version == "1.0"
    assert manifest.suite_id == suite_id
    assert manifest.excluded_paths == ()
    assert len(manifest.scenarios) == 1
    scenario = manifest.scenarios[0]
    assert scenario.scenario_id == "baseline_feasible"
    assert scenario.database_backend.value == backend_value
    assert scenario.fixtures == ()
    assert scenario.comparison_policy.leaves == ()
    assert scenario.expected_output is not None
    assert scenario.expected_output.path == "expected/baseline_feasible.v1.json"
    assert scenario.expected_output.commit_sha == "f274db66fe4bb2de206d12c2d561d1b3549ab6c0"


def test_pilot_public_identity_is_frozen() -> None:
    assert PILOT_CHECK_ID == "multilingual_report_same_revision"
    assert PILOT_RESULT_SCHEMA_VERSION == "task11-pilot-report.v1"


def test_pilot_rejects_relative_output_root_before_service_calls() -> None:
    with pytest.raises(PilotVerificationError) as caught:
        verify_multilingual_report_pilot(
            report_service=None,
            render_service=None,
            template_repository=None,
            project_id="project",
            project_version_id="version",
            source_commit_sha="a" * 40,
            source_manifest_sha="b" * 64,
            output_root=Path("relative"),
            repeat_index=1,
            run_identity={"database_backend": "sqlite"},
            download_artifact=lambda _r, _a, _actor: (b"", {}),
        )
    assert caught.value.code == "UNSAFE_OUTPUT_ROOT"


def test_pilot_rejects_stale_completion_marker_before_service_calls(tmp_path: Path) -> None:
    root = (tmp_path / "run").resolve()
    root.mkdir()
    (root / "pilot-summary.json").write_text("{}", encoding="utf-8")
    with pytest.raises(StaleEvaluationArtifactsError):
        verify_multilingual_report_pilot(
            report_service=None,
            render_service=None,
            template_repository=None,
            project_id="project",
            project_version_id="version",
            source_commit_sha="a" * 40,
            source_manifest_sha="b" * 64,
            output_root=root,
            repeat_index=1,
            run_identity={"database_backend": "sqlite"},
            download_artifact=lambda _r, _a, _actor: (b"", {}),
        )
