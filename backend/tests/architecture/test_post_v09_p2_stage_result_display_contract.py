"""Architecture tests for POST-V0.9 P2 stage-result-display contract."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
P2_CONTRACT = REPO_ROOT / "docs" / "tasks" / "POST_V09-P2-stage-result-display-contract.md"

P2_ALLOWLIST = (
    "docs/tasks/POST_V09-P2-stage-result-display-contract.md",
    "backend/tests/architecture/test_post_v09_p2_stage_result_display_contract.py",
    "frontend/src/features/calculations/components/CalculationsPage.vue",
    "frontend/src/features/calculations/components/CalculationSummary.vue",
    "frontend/src/features/five-stage/components/FiveStageProgressPanel.vue",
    "frontend/src/api/contracts/calculations.ts",
    "frontend/src/features/calculations/model/mapPersistedCalculations.ts",
    "frontend/src/features/calculations/model/mapPersistedCalculations.test.ts",
    "frontend/src/features/five-stage/model/mapFiveStageCalculations.ts",
    "frontend/src/features/five-stage/model/fiveStageModel.test.ts",
    "frontend/src/features/calculations/components/CoolingLoadResultsTable.vue",
    "frontend/src/features/calculations/components/CoolingLoadResultsTable.test.ts",
    "frontend/src/features/calculations/components/EquipmentResultsTable.vue",
    "frontend/src/features/calculations/components/EquipmentResultsTable.test.ts",
    "frontend/src/features/calculations/components/InstalledPowerResultsTable.vue",
    "frontend/src/features/calculations/components/InstalledPowerResultsTable.test.ts",
    "frontend/src/features/calculations/components/InvestmentResultsTable.vue",
    "frontend/src/features/calculations/components/InvestmentResultsTable.test.ts",
    "frontend/src/features/calculations/architecture/test_post_v09_p2_stage_result_display.test.ts",
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


def _on_p2_branch() -> bool:
    return "post-v09-p2-stage-result-display" in _current_branch_name()


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


def test_p2_contract_exists_and_authorizes_display_only() -> None:
    assert P2_CONTRACT.is_file()
    text = P2_CONTRACT.read_text(encoding="utf-8")
    assert "BASE_MAIN_SHA=c6f806575a3d100bd00ef22aa7600f3c7109c7ee" in text
    assert "POST_V09_P2_IMPLEMENTATION_AUTHORIZED=YES" in text
    assert "POST_V09_P1_IMPLEMENTATION_AUTHORIZED=NO" in text
    assert "POST_V09_P3_IMPLEMENTATION_AUTHORIZED=NO" in text
    assert "FORMULA_RECUT_AUTHORIZED=NO" in text
    assert "VUE_ENGINEERING_FORMULAS=NO" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "cooling_load" in text
    assert "installed_power" in text


def test_p2_allowlist_in_contract_matches_test_tuple() -> None:
    text = P2_CONTRACT.read_text(encoding="utf-8")
    assert _extract_allowlist_paths(text, "POST_V09_P2_FILE_ALLOWLIST") == set(P2_ALLOWLIST)


@pytest.mark.skipif(not _on_p2_branch(), reason="allowlist applies on the P2 branch only")
def test_p2_changed_paths_are_subset_of_allowlist() -> None:
    assert _changed_interesting_paths() <= set(P2_ALLOWLIST)
