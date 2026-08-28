"""Architecture tests for POST-V0.9 P4 zone-area recut contract."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT = REPO_ROOT / "docs" / "tasks" / "POST_V09-P4-zone-area-recut-contract.md"

P4_ALLOWLIST = (
    "docs/tasks/POST_V09-P4-zone-area-recut-contract.md",
    "backend/tests/architecture/test_post_v09_p4_zone_area_recut_contract.py",
    "backend/src/cold_storage/modules/calculations/domain/zone_planning.py",
    "backend/tests/unit/test_zone_planner.py",
    "backend/tests/unit/test_v09_p2_zone_planning.py",
    "backend/tests/unit/test_post_v09_p4_zone_area_recut.py",
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


def _on_p4_branch() -> bool:
    return "post-v09-p4-zone-area-recut" in _current_branch_name()


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


def test_p4_contract_exists_and_locks_identity() -> None:
    assert CONTRACT.is_file()
    text = CONTRACT.read_text(encoding="utf-8")
    assert "BASE_MAIN_SHA=d6c3af953d0d8486fd5762e5797ecd336f44fbf2" in text
    assert "POST_V09_P4_IMPLEMENTATION_AUTHORIZED=YES" in text
    assert "KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0" in text
    assert "COOLING_LOAD_FORMULA_RECUT=NO" in text
    assert "VUE_ENGINEERING_FORMULAS=NO" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "PRECOOL" not in text or "42" in text
    assert "sorting_packaging_room" in text
    assert "((n_long − 1)" in text or "n_long − 1" in text or "(n_long - 1)" in text
    assert "2061.85" in text
    assert "50 m² per platform" in text or "50 m²" in text


def test_p4_allowlist_in_contract_matches_test_tuple() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    assert _extract_allowlist_paths(text, "POST_V09_P4_FILE_ALLOWLIST") == set(P4_ALLOWLIST)


@pytest.mark.skipif(not _on_p4_branch(), reason="allowlist applies on the P4 branch only")
def test_p4_changed_paths_are_subset_of_allowlist() -> None:
    assert _changed_interesting_paths() <= set(P4_ALLOWLIST)
