"""Architecture tests for V0.9 P2 zone formula recut contract."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
P2_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_9-P2-zone-formula-recut-contract.md"
P0_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_9-P0-version-contract.md"
ZONE_PLANNING = REPO_ROOT / "backend/src/cold_storage/modules/calculations/domain/zone_planning.py"

# P2 allowlist = P0 §7.3 ∪ living-test ∪ snapshot-schema ∪ shipping-channel-registry ∪ v07-golden.
P2_ALLOWLIST = (
    "docs/tasks/V0_9-P2-zone-formula-recut-contract.md",
    "backend/src/cold_storage/modules/calculations/domain/zone_planning.py",
    "backend/tests/unit/test_zone_planner.py",
    "backend/tests/unit/test_v09_p2_zone_planning.py",
    "backend/tests/architecture/test_v09_p2_zone_formula_contract.py",
    "backend/tests/integration/test_v07_p1_bundle_execution_traceability.py",
    "backend/tests/test_v03_p1_report_unit_quality.py",
    "backend/tests/integration/test_project_api_persistence.py",
    "backend/tests/unit/test_demo_overview.py",
    "backend/src/cold_storage/modules/orchestration/application/source_snapshots.py",
    "backend/tests/unit/test_transaction_b_source_snapshots.py",
    "backend/src/cold_storage/modules/projects/application/operator_process_input.py",
    "backend/tests/architecture/test_v09_p1_operator_key_contract.py",
    "backend/tests/unit/test_v09_p1_operator_process_input_assembler.py",
    "backend/tests/unit/test_v08_p1_operator_process_input_assembler.py",
    "backend/tests/golden/v07_cross_consumer_v1.json",
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


def _on_p2_branch() -> bool:
    return "v09-p2-zone-formula" in _current_branch_name()


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


def test_p2_contract_exists_and_authorizes_formula_recut() -> None:
    assert P2_CONTRACT.is_file()
    text = P2_CONTRACT.read_text(encoding="utf-8")
    assert "BASE_MAIN_SHA=e9514c59ab6882f59c979191aa6b4ab33c9bfdaa" in text
    assert "V09_P2_IMPLEMENTATION_AUTHORIZED=YES" in text
    assert "FORMULA_RECUT_AUTHORIZED=YES" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "shipping_channel" in text
    assert "REFRIGERATED_ZONE_REGISTRY" in text


def test_p0_may_still_record_formula_recut_no() -> None:
    p0 = P0_CONTRACT.read_text(encoding="utf-8")
    assert "FORMULA_RECUT_AUTHORIZED=NO" in p0


def test_p2_allowlist_matches_contract_and_files_exist() -> None:
    p0 = P0_CONTRACT.read_text(encoding="utf-8")
    p2 = P2_CONTRACT.read_text(encoding="utf-8")
    p0_paths = _extract_allowlist_paths(p0, "V09_P2_FILE_ALLOWLIST")
    p2_paths = _extract_allowlist_paths(p2, "V09_P2_FILE_ALLOWLIST")
    # P2 allowlist = P0 §7.3 ∪ Charles-authorized living-test files.
    assert p0_paths <= p2_paths
    assert set(P2_ALLOWLIST) == p2_paths
    for path in P2_ALLOWLIST:
        assert (REPO_ROOT / path).is_file(), path


@pytest.mark.skipif(not _on_p2_branch(), reason="P2 allowlist diff only enforced on v09-p2-zone-formula branch")
def test_p2_diff_stays_on_allowlist() -> None:
    changed = _changed_interesting_paths()
    allowlist = set(P2_ALLOWLIST)
    extra = sorted(changed - allowlist)
    assert extra == [], f"P2 diff off allowlist: {extra}"


def test_zone_planning_is_only_production_formula_file_changed() -> None:
    changed = _changed_interesting_paths()
    # P2 snapshot-schema admit may also touch source_snapshots.py (off formula recut).
    allowed_non_formula_src = {
        "backend/src/cold_storage/modules/orchestration/application/source_snapshots.py",
        "backend/src/cold_storage/modules/projects/application/operator_process_input.py",
    }
    production_formula_files = {
        path
        for path in changed
        if path.startswith("backend/src/")
        and path.endswith(".py")
        and "zone_planning.py" not in path
        and path not in allowed_non_formula_src
    }
    assert production_formula_files == set()
    assert "backend/src/cold_storage/modules/calculations/domain/zone_planning.py" in changed


def test_no_vue_changes_in_p2_diff() -> None:
    changed = _changed_interesting_paths()
    vue_changes = {path for path in changed if path.startswith("frontend/src/")}
    assert vue_changes == set()


def test_zone_planning_emits_shipping_channel_and_dual_precool() -> None:
    content = ZONE_PLANNING.read_text(encoding="utf-8")
    assert 'VERSION = "1.0.0"' in content
    assert '"shipping_channel"' in content
    assert '"6_position"' in content
    assert '"8_position"' in content
    assert "total_area_m2_8_position_scheme" in content
    assert "precooling_position_area_m2" not in content.split("def plan")[1]
