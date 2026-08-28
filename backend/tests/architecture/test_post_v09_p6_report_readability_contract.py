"""Architecture tests for POST-V0.9 P6 report-readability contract."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT = REPO_ROOT / "docs" / "tasks" / "POST_V09-P6-report-readability-contract.md"

P6_ALLOWLIST = (
    "docs/tasks/POST_V09-P6-report-readability-contract.md",
    "backend/tests/architecture/test_post_v09_p6_report_readability_contract.py",
    "backend/src/cold_storage/modules/reports/application/canonical_render_model_builder.py",
    "backend/src/cold_storage/modules/reports/application/render_model_localizer.py",
    "backend/src/cold_storage/modules/reports/localization/zh_cn.py",
    "backend/src/cold_storage/modules/reports/localization/en_us.py",
    "backend/tests/test_reports/test_post_v09_p3_calculation_logic.py",
    "backend/tests/test_reports/test_post_v09_p6_report_readability.py",
    "backend/tests/test_reports/test_localization.py",
    "backend/tests/unit/test_reports_rendering.py",
)

_INTERESTING_PREFIXES = (
    "docs/",
    "backend/src/",
    "backend/tests/",
    "frontend/src/",
    "frontend/tests/",
)


def _current_branch_name() -> str:
    head_ref = os.environ.get("GITHUB_HEAD_REF")
    if head_ref:
        return head_ref
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _on_p6_branch() -> bool:
    return "post-v09-p6-report-readability" in _current_branch_name()


def _extract_allowlist_paths(contract: str, marker: str) -> set[str]:
    start = contract.index(marker)
    fence_start = contract.rfind("```", 0, start)
    fence_end = contract.index("```", start)
    block = contract[fence_start + 3 : fence_end].strip()
    if block.startswith("text"):
        block = block.split("\n", 1)[1].strip()
    paths: set[str] = set()
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped == marker:
            continue
        paths.add(stripped)
    return paths


def _changed_interesting_paths() -> set[str]:
    diff = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    names = {line.strip() for line in diff.stdout.splitlines() if line.strip()}
    names |= {line.strip() for line in untracked.stdout.splitlines() if line.strip()}
    return {name for name in names if name.startswith(_INTERESTING_PREFIXES)}


def test_p6_contract_exists_and_forbids_recalculation() -> None:
    assert CONTRACT.is_file()
    text = CONTRACT.read_text(encoding="utf-8")
    assert "BASE_MAIN_SHA=d6c3af953d0d8486fd5762e5797ecd336f44fbf2" in text
    assert "POST_V09_P6_IMPLEMENTATION_AUTHORIZED=YES" in text
    assert "REPORTS_MUST_NOT_RECALCULATE=YES" in text
    assert "KEEP_REPORT_TYPE_IDENTITY=cold_storage_concept_design@1.0.0" in text
    assert "FORMULA_RECUT_AUTHORIZED=NO" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "Drop `calculation_id` from the rendered table" in text
    assert "zone_name" in text


def test_p6_allowlist_in_contract_matches_test_tuple() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    assert _extract_allowlist_paths(text, "POST_V09_P6_FILE_ALLOWLIST") == set(P6_ALLOWLIST)


@pytest.mark.skipif(not _on_p6_branch(), reason="allowlist applies on the P6 branch only")
def test_p6_changed_paths_are_subset_of_allowlist() -> None:
    assert _changed_interesting_paths() <= set(P6_ALLOWLIST)
