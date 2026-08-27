"""Architecture tests for V0.9 P3 zone result display contract."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
P3_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_9-P3-zone-result-display-contract.md"
P0_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_9-P0-version-contract.md"

P0_P3_ZONE_TEST_ALIAS = (
    "frontend/tests/features/calculations/ZoneResultsTable.test.ts",
    "frontend/src/features/calculations/components/ZoneResultsTable.test.ts",
)

P3_ALLOWLIST = (
    "docs/tasks/V0_9-P3-zone-result-display-contract.md",
    "frontend/src/features/calculations/components/CalculationsPage.vue",
    "frontend/src/features/calculations/components/ZoneResultsTable.vue",
    "frontend/src/features/calculations/components/ZoneResultsTable.test.ts",
    "frontend/src/features/calculations/model/mapPersistedCalculations.ts",
    "frontend/src/features/calculations/model/mapPersistedCalculations.test.ts",
    "frontend/src/api/contracts/planning.ts",
    "frontend/src/features/calculations/architecture/test_v09_p3_zone_result_display.test.ts",
    "backend/tests/architecture/test_v09_p3_zone_result_display_contract.py",
    "backend/tests/architecture/test_v09_p2_zone_formula_contract.py",
)

_INTERESTING_PREFIXES = (
    "docs/",
    "backend/src/",
    "backend/tests/",
    "frontend/src/",
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


def _on_p3_branch() -> bool:
    return "v09-p3-zone-result" in _current_branch_name()


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


def test_p3_contract_exists_and_authorizes_display_only() -> None:
    assert P3_CONTRACT.is_file()
    text = P3_CONTRACT.read_text(encoding="utf-8")
    assert "BASE_MAIN_SHA=808cbfd755ae85d5f7795baaa2987fb497698ab2" in text
    assert "V09_P3_IMPLEMENTATION_AUTHORIZED=YES" in text
    assert "FORMULA_RECUT_AUTHORIZED=NO" in text
    assert "VUE_ENGINEERING_FORMULAS=NO" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "total_area_m2_8_position_scheme" in text


def test_p0_p3_zone_test_path_aliases_to_co_located_component_test() -> None:
    p0 = P0_CONTRACT.read_text(encoding="utf-8")
    p0_paths = _extract_allowlist_paths(p0, "V09_P3_FILE_ALLOWLIST")
    legacy_path, co_located_path = P0_P3_ZONE_TEST_ALIAS
    assert legacy_path in p0_paths
    assert (REPO_ROOT / co_located_path).is_file()


def test_p0_p3_paths_are_subset_of_p3_allowlist_after_alias() -> None:
    p0 = P0_CONTRACT.read_text(encoding="utf-8")
    p0_paths = _extract_allowlist_paths(p0, "V09_P3_FILE_ALLOWLIST")
    legacy_path, co_located_path = P0_P3_ZONE_TEST_ALIAS
    aliased_p0_paths = (p0_paths - {legacy_path}) | {co_located_path}
    assert aliased_p0_paths <= set(P3_ALLOWLIST)


def test_p3_allowlist_matches_contract_and_files_exist() -> None:
    p3 = P3_CONTRACT.read_text(encoding="utf-8")
    p3_paths = _extract_allowlist_paths(p3, "V09_P3_FILE_ALLOWLIST")
    assert set(P3_ALLOWLIST) == p3_paths
    for path in P3_ALLOWLIST:
        assert (REPO_ROOT / path).is_file(), path


@pytest.mark.skipif(
    not _on_p3_branch(),
    reason=("P3 allowlist diff only enforced on branches whose name contains v09-p3-zone-result"),
)
def test_p3_diff_stays_on_allowlist() -> None:
    changed = _changed_interesting_paths()
    allowlist = set(P3_ALLOWLIST)
    extra = sorted(changed - allowlist)
    assert extra == [], f"P3 diff off allowlist: {extra}"


@pytest.mark.skipif(
    not _on_p3_branch(),
    reason=(
        "P3 backend-src freeze only enforced on branches whose name contains v09-p3-zone-result"
    ),
)
def test_no_backend_src_changes_in_p3_diff() -> None:
    changed = _changed_interesting_paths()
    backend_src_changes = {
        path for path in changed if path.startswith("backend/src/") and path.endswith(".py")
    }
    assert backend_src_changes == set()
