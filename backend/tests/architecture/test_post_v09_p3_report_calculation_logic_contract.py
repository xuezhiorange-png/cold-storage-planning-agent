"""Architecture tests for POST-V0.9 P3 report-calculation-logic contract."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
P3_CONTRACT = REPO_ROOT / "docs" / "tasks" / "POST_V09-P3-report-calculation-logic-contract.md"
ADR = REPO_ROOT / "docs" / "architecture" / "ADR-030-report-calculation-logic-projection.md"

P3_ALLOWLIST = (
    "docs/tasks/POST_V09-P3-report-calculation-logic-contract.md",
    "docs/architecture/ADR-030-report-calculation-logic-projection.md",
    "backend/tests/architecture/test_post_v09_p3_report_calculation_logic_contract.py",
    "backend/src/cold_storage/modules/reports/domain/schema.py",
    "backend/src/cold_storage/modules/reports/domain/quality.py",
    "backend/src/cold_storage/modules/reports/application/assembler.py",
    "backend/src/cold_storage/modules/reports/application/canonical_render_model_builder.py",
    "backend/src/cold_storage/modules/reports/application/persisted_calculation_reads.py",
    "backend/src/cold_storage/modules/reports/application/render_model_localizer.py",
    "backend/src/cold_storage/modules/reports/infrastructure/real_data_provider.py",
    "backend/src/cold_storage/modules/reports/infrastructure/persisted_calculation_query.py",
    "backend/src/cold_storage/modules/reports/localization/zh_cn.py",
    "backend/src/cold_storage/modules/reports/localization/en_us.py",
    "backend/src/cold_storage/modules/reports/localization/catalog.py",
    "frontend/src/features/reports/components/ReportExportPanel.vue",
    "frontend/src/features/reports/types.ts",
    "frontend/src/features/reports/composables/useReportExport.test.ts",
    "backend/tests/test_reports/test_post_v09_p3_calculation_logic.py",
    "backend/tests/test_reports/test_localization.py",
    "backend/tests/unit/test_reports_rendering.py",
    "backend/tests/test_reports/test_real_production_e2e.py",
    "backend/tests/test_reports/test_real_storage_e2e.py",
    "backend/tests/test_reports/test_scheme_provenance_golden_e2e.py",
    "frontend/src/features/reports/architecture/test_post_v09_p3_report_preview.test.ts",
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


def _on_p3_branch() -> bool:
    return "post-v09-p3-report-calculation-logic" in _current_branch_name()


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


def test_p3_contract_exists_and_authorizes_projection_only() -> None:
    assert P3_CONTRACT.is_file()
    assert ADR.is_file()
    text = P3_CONTRACT.read_text(encoding="utf-8")
    adr = ADR.read_text(encoding="utf-8")
    assert "BASE_MAIN_SHA=c6f806575a3d100bd00ef22aa7600f3c7109c7ee" in text
    assert "POST_V09_P3_IMPLEMENTATION_AUTHORIZED=YES" in text
    assert "POST_V09_P1_IMPLEMENTATION_AUTHORIZED=NO" in text
    assert "POST_V09_P2_IMPLEMENTATION_AUTHORIZED=NO" in text
    assert "REPORTS_MUST_NOT_RECALCULATE=YES" in text
    assert "KEEP_REPORT_TYPE_IDENTITY=cold_storage_concept_design@1.0.0" in text
    assert "VUE_ENGINEERING_FORMULAS=NO" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "calculation_logic" in text
    assert "daily_inbound_mass_kg" in text
    assert "MUST NOT recalculate" in adr or "must not recalculate" in adr.lower()


def test_p3_allowlist_in_contract_matches_test_tuple() -> None:
    text = P3_CONTRACT.read_text(encoding="utf-8")
    assert _extract_allowlist_paths(text, "POST_V09_P3_FILE_ALLOWLIST") == set(P3_ALLOWLIST)


@pytest.mark.skipif(not _on_p3_branch(), reason="allowlist applies on the P3 branch only")
def test_p3_changed_paths_are_subset_of_allowlist() -> None:
    assert _changed_interesting_paths() <= set(P3_ALLOWLIST)
