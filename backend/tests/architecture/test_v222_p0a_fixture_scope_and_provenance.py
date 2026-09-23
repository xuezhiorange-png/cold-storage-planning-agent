"""Scope and provenance lock for the P0A canonical-fixture evidence change."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = "3b90126fc4215460b93d6fd72b619dc507602669"
ALLOWED_PATHS = {
    "backend/tests/architecture/test_v222_p0a_calibration_blocker_evidence.py",
    "backend/tests/architecture/test_v222_p0a_fixture_scope_and_provenance.py",
    "backend/tests/evaluation/test_v222_p0a_xinzhao_canonical_fixture.py",
    "backend/tests/evaluation/v222_p0a_regularity_metrics.py",
    "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json",
    "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.provenance.json",
    "docs/architecture/ADR-047-process-flow-layout-regularity-authority.md",
    "docs/tasks/V2_2-version-plan.md",
    "docs/tasks/V2_2_2-P0-process-flow-layout-regularity-contract.md",
    "docs/tasks/V2_2_2-P0A-canonical-fixture-regularity-calibration.md",
    "docs/tasks/evidence/v2_2_2_p0a/regularity-calibration-matrix.json",
}


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_p0a_changes_are_limited_to_fixture_test_and_evidence_paths() -> None:
    changed = set(_git("diff", "--name-only", f"{BASE}...HEAD").splitlines())
    changed.update(_git("diff", "--name-only").splitlines())
    changed.update(_git("diff", "--cached", "--name-only").splitlines())
    changed.update(_git("ls-files", "--others", "--exclude-standard").splitlines())
    assert changed == ALLOWED_PATHS
    assert not any(
        path.startswith(
            (
                "backend/src/",
                "frontend/",
                "database/",
                "backend/alembic/",
                "backend/src/cold_storage/modules/aily/",
            )
        )
        for path in changed
    )


def test_release_runtime_source_is_identical_to_v221_tag() -> None:
    subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            "64f335bbfbbaf061b9ba08c18f2068db411f8922",
            "HEAD",
            "--",
            "backend/src",
        ],
        cwd=ROOT,
        check=True,
    )
