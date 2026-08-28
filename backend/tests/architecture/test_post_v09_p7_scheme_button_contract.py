"""Architecture tests for POST-V0.9 P7 scheme-button contract."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT = REPO_ROOT / "docs" / "tasks" / "POST_V09-P7-scheme-button-contract.md"

P7_ALLOWLIST = (
    "docs/tasks/POST_V09-P7-scheme-button-contract.md",
    "backend/tests/architecture/test_post_v09_p7_scheme_button_contract.py",
    "frontend/src/features/five-stage/components/ProductionSchemeRunPanel.vue",
    "frontend/src/features/workflow/components/WorkflowGuidancePanel.vue",
    "frontend/src/features/five-stage/components/ProductionSchemeRunPanel.test.ts",
    "frontend/src/features/workflow/components/WorkflowGuidancePanel.test.ts",
    "frontend/src/features/workbench/architecture/test_post_v09_p7_scheme_button.test.ts",
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


def _on_p7_branch() -> bool:
    return "post-v09-p7-scheme-button" in _current_branch_name()


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


def test_p7_contract_exists_and_forbids_auto_run() -> None:
    assert CONTRACT.is_file()
    text = CONTRACT.read_text(encoding="utf-8")
    assert "BASE_MAIN_SHA=d6c3af953d0d8486fd5762e5797ecd336f44fbf2" in text
    assert "POST_V09_P7_IMPLEMENTATION_AUTHORIZED=YES" in text
    assert "AUTO_RUN_PRODUCTION_SCHEME=NO" in text
    assert "VUE_ENGINEERING_FORMULAS=NO" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "chainComplete" in text
    assert "COMPLETED" in text
    assert "SCHEME_MISSING" in text


def test_p7_allowlist_in_contract_matches_test_tuple() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    assert _extract_allowlist_paths(text, "POST_V09_P7_FILE_ALLOWLIST") == set(P7_ALLOWLIST)


@pytest.mark.skipif(not _on_p7_branch(), reason="allowlist applies on the P7 branch only")
def test_p7_changed_paths_are_subset_of_allowlist() -> None:
    assert _changed_interesting_paths() <= set(P7_ALLOWLIST)
