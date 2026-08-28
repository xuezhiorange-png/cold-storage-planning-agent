"""Architecture tests for POST-V0.9 P8 frontend-polish contract."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT = REPO_ROOT / "docs" / "tasks" / "POST_V09-P8-frontend-polish-contract.md"

P8_ALLOWLIST = (
    "docs/tasks/POST_V09-P8-frontend-polish-contract.md",
    "backend/tests/architecture/test_post_v09_p8_frontend_polish_contract.py",
    "frontend/src/app/AppShell.vue",
    "frontend/src/app/operator-workbench.css",
    "frontend/src/features/workbench/WorkbenchLayout.vue",
    "frontend/src/features/workbench/architecture/test_post_v09_p1_hide_planning_run_nav.test.ts",
    "frontend/src/features/five-stage/components/EngineeringInputsPage.vue",
    "frontend/src/features/five-stage/components/EngineeringInputBundleForm.vue",
    "frontend/src/features/five-stage/components/BundleLeafField.vue",
    "frontend/src/features/calculations/components/CalculationSummary.vue",
    "frontend/src/features/calculations/components/CalculationSummary.test.ts",
    "frontend/src/features/schemes/components/SchemesPage.vue",
    "frontend/src/features/investment/components/InvestmentPage.vue",
    "frontend/src/features/power/components/PowerPage.vue",
    "frontend/src/features/reports/components/ReportsPage.vue",
    "frontend/src/features/reports/components/ReportExportPanel.vue",
    "frontend/src/features/workbench/architecture/test_post_v09_p8_frontend_polish.test.ts",
)

_INTERESTING_PREFIXES = (
    "docs/",
    "backend/src/",
    "backend/tests/",
    "frontend/src/",
    "frontend/tests/",
)

_FORBIDDEN_ON_P8 = (
    "frontend/src/features/calculations/components/ZoneResultsTable.vue",
    "frontend/src/features/calculations/components/CoolingLoadResultsTable.vue",
    "frontend/src/features/calculations/components/EquipmentResultsTable.vue",
    "frontend/src/features/calculations/components/InstalledPowerResultsTable.vue",
    "frontend/src/features/calculations/components/InvestmentResultsTable.vue",
    "frontend/src/features/five-stage/components/FiveStageProgressPanel.vue",
    "frontend/src/features/five-stage/components/ProductionSchemeRunPanel.vue",
    "frontend/src/features/workflow/components/WorkflowGuidancePanel.vue",
    "backend/src/cold_storage/modules/calculations/domain/zone_planning.py",
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


def _on_p8_branch() -> bool:
    return "post-v09-p8-frontend-polish" in _current_branch_name()


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


def test_p8_contract_exists_and_keeps_operator_nav() -> None:
    assert CONTRACT.is_file()
    text = CONTRACT.read_text(encoding="utf-8")
    assert "BASE_MAIN_SHA=d6c3af953d0d8486fd5762e5797ecd336f44fbf2" in text
    assert "POST_V09_P8_IMPLEMENTATION_AUTHORIZED=YES" in text
    assert "VUE_ENGINEERING_FORMULAS=NO" in text
    assert "FORMULA_RECUT_AUTHORIZED=NO" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "工程输入 | 计算结果" in text
    assert "基本信息" in text
    assert "ZoneResultsTable.vue" in text


def test_p8_allowlist_in_contract_matches_test_tuple() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    assert _extract_allowlist_paths(text, "POST_V09_P8_FILE_ALLOWLIST") == set(P8_ALLOWLIST)
    assert set(_FORBIDDEN_ON_P8).isdisjoint(P8_ALLOWLIST)


@pytest.mark.skipif(not _on_p8_branch(), reason="allowlist applies on the P8 branch only")
def test_p8_changed_paths_are_subset_of_allowlist() -> None:
    changed = _changed_interesting_paths()
    assert changed <= set(P8_ALLOWLIST)
    assert changed.isdisjoint(_FORBIDDEN_ON_P8)
