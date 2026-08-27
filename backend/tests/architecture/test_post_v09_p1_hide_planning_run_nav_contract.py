"""Architecture tests for POST-V0.9 P1 hide-planning-run-nav contract."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
P1_CONTRACT = REPO_ROOT / "docs" / "tasks" / "POST_V09-P1-hide-planning-run-nav-contract.md"

P1_ALLOWLIST = (
    "docs/tasks/POST_V09-P1-hide-planning-run-nav-contract.md",
    "backend/tests/architecture/test_post_v09_p1_hide_planning_run_nav_contract.py",
    "frontend/src/features/workbench/WorkbenchLayout.vue",
    "frontend/src/app/router.ts",
    "frontend/src/app/router.test.ts",
    "frontend/src/app/AppShell.vue",
    "frontend/src/features/investment/components/InvestmentPage.vue",
    "frontend/tests/workbench.test.ts",
    "frontend/src/features/workbench/architecture/test_post_v09_p1_hide_planning_run_nav.test.ts",
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


def _on_p1_branch() -> bool:
    return "post-v09-p1-hide-planning-run-nav" in _current_branch_name()


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


def test_p1_contract_exists_and_authorizes_nav_only() -> None:
    assert P1_CONTRACT.is_file()
    text = P1_CONTRACT.read_text(encoding="utf-8")
    assert "BASE_MAIN_SHA=c6f806575a3d100bd00ef22aa7600f3c7109c7ee" in text
    assert "POST_V09_P1_IMPLEMENTATION_AUTHORIZED=YES" in text
    assert "POST_V09_P2_IMPLEMENTATION_AUTHORIZED=NO" in text
    assert "POST_V09_P3_IMPLEMENTATION_AUTHORIZED=NO" in text
    assert "FORMULA_RECUT_AUTHORIZED=NO" in text
    assert "VUE_ENGINEERING_FORMULAS=NO" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "DEFAULT_LANDING= /workbench/engineering-inputs" in text
    assert "LEFTOVER_ROUTE_KEPT= /workbench/project" in text


def test_p1_allowlist_in_contract_matches_test_tuple() -> None:
    text = P1_CONTRACT.read_text(encoding="utf-8")
    assert _extract_allowlist_paths(text, "POST_V09_P1_FILE_ALLOWLIST") == set(P1_ALLOWLIST)


@pytest.mark.skipif(not _on_p1_branch(), reason="allowlist applies on the P1 branch only")
def test_p1_changed_paths_are_subset_of_allowlist() -> None:
    assert _changed_interesting_paths() <= set(P1_ALLOWLIST)
