"""Architecture locks for the V2.0 release-closure readiness lane."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CLOSURE_PATH = REPO_ROOT / "docs" / "tasks" / "V2_0-release-closure-readiness.md"
VERSION_PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V2_0-version-plan.md"
ADR_PATH = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "ADR-042-factory-power-estimation-and-presentation-contract.md"
)
CURRENT_STATE_PATH = REPO_ROOT / "docs" / "audit" / "current-state.md"
GAP_ANALYSIS_PATH = REPO_ROOT / "docs" / "audit" / "gap-analysis.md"
DEVELOPMENT_PLAN_PATH = REPO_ROOT / "docs" / "roadmap" / "DEVELOPMENT_PLAN.md"
TECH_DEBT_PATH = REPO_ROOT / "docs" / "TECH_DEBT.md"

ALLOWED_PATHS = {
    "backend/tests/architecture/test_v20_release_closure_readiness.py",
    "backend/tests/architecture/test_v20_p0_factory_power_estimation_and_presentation_contract.py",
    "backend/tests/architecture/test_v20_p1_factory_power_estimation_canonical_result.py",
    "backend/tests/architecture/test_v20_p2_factory_power_read_only_presentation.py",
    "docs/architecture/ADR-042-factory-power-estimation-and-presentation-contract.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/tasks/V2_0-release-closure-readiness.md",
    "docs/tasks/V2_0-version-plan.md",
    "docs/TECH_DEBT.md",
    "backend/tests/architecture/test_v21_p0_factory_power_upstream_authority_doubao_mcp_contract.py",
    "docs/tasks/V2_1-version-plan.md",
    "docs/tasks/V2_1-P0-factory-power-upstream-authority-doubao-mcp-contract.md",
    "docs/architecture/ADR-043-factory-power-upstream-authority-doubao-mcp.md",
}

RUNTIME_PATHS = {
    "backend/src/cold_storage/modules/aily/application/factory_power_table.py",
    "backend/src/cold_storage/modules/calculations/application/factory_power_presentation.py",
    "backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py",
    "frontend/src/features/calculations/model/mapFactoryPowerPresentation.ts",
    "frontend/src/features/calculations/components/FactoryPowerEstimationResults.vue",
}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _changed_paths() -> set[str]:
    merge_base = subprocess.run(
        ["git", "merge-base", "origin/main", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    tracked = subprocess.run(
        ["git", "diff", "--name-only", merge_base, "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return {
        path
        for path in [*tracked, *untracked]
        if path and not path.startswith("backend/artifacts/local/")
    }


def test_release_closure_scope_is_docs_and_architecture_only() -> None:
    changed = _changed_paths()
    assert changed <= ALLOWED_PATHS
    assert not any(path.startswith("backend/src/") for path in changed)
    assert not any(path.startswith("frontend/src/") for path in changed)
    assert not any(path.startswith("backend/alembic/") for path in changed)
    assert not any(path.startswith(".github/workflows/") for path in changed)
    assert not any(path.startswith("deployment/") for path in changed)


def test_release_closure_records_the_merged_v20_state() -> None:
    closure = _text(CLOSURE_PATH)
    required = (
        "TASK_ID=V20_RELEASE_CLOSURE_READINESS_R1",
        "TARGET_RELEASE=v2.0.0",
        "P0_STATUS=MERGED",
        "P1_STATUS=MERGED",
        "P2_STATUS=MERGED",
        "P1_MERGE_COMMIT_SHA=2a1a2797767a52834143a78b3e80193b5752b2e6",
        "P2_MERGE_COMMIT_SHA=5d5a9cad010a629bf52f6534fba37d047c330e00",
        "V20_P2_IMPLEMENTATION_STATUS=MERGED",
        "V20_P2_PR_NUMBER=258",
        "V20_P2_REVIEW_RESULT=PASS",
        "V20_P2_BLOCKER_COUNT=0",
        "V20_P2_FINAL_HEAD_SHA=2759538bcd32f7468de50c740ca17d7fbe18f49b",
        "V20_IMPLEMENTATION_COMPLETE=YES",
        "V20_P3_DEFINED=NO",
        "V20_P3_EXECUTED=NO",
        "V2_0_0_RELEASE_CANDIDATE=YES",
        "V2_0_0_RELEASE_READY=YES",
        "TAG_CREATION_AUTHORIZED=NO",
        "GITHUB_RELEASE_CREATION_AUTHORIZED=NO",
        "DEPLOYMENT_AUTHORIZED=NO",
        "NEXT_FEATURE_LANE_AUTHORIZED=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    )
    for line in required:
        assert line in closure


def test_current_documents_truth_up_p2_without_erasing_history() -> None:
    version_plan = _text(VERSION_PLAN_PATH)
    adr = _text(ADR_PATH)
    current_state = _text(CURRENT_STATE_PATH)
    gap_analysis = _text(GAP_ANALYSIS_PATH)
    development_plan = _text(DEVELOPMENT_PLAN_PATH)
    tech_debt = _text(TECH_DEBT_PATH)

    assert "P2 | **已合并到 main；PR #258 Review PASS**" in version_plan
    assert "等待 P2 独立 Review" not in version_plan
    assert "P2_IMPLEMENTATION_STATUS=MERGED" in version_plan
    assert "V20_P3_DEFINED=NO" in version_plan
    assert "P0 contract frozen, P1 merged, P2 read-only presentation merged" in adr
    assert "release closure active" in adr
    assert "P2_AUTHORIZED=NO" in version_plan
    assert "READY_AUTHORIZED=NO" in version_plan
    assert "MERGE_AUTHORIZED=NO" in version_plan
    assert "P2_AUTHORIZED=NO" in adr
    assert "READY_AUTHORIZED=NO" in adr
    assert "MERGE_AUTHORIZED=NO" in adr
    for text in (current_state, gap_analysis, development_plan, tech_debt):
        assert "V20_IMPLEMENTATION_COMPLETE=YES" in text
        assert "V20_P3_DEFINED=NO" in text
        assert "v2.0.0" in text
        assert "NEXT_FEATURE_LANE_AUTHORIZED=NO" in text


def test_v20_runtime_and_release_boundaries_are_unchanged() -> None:
    for path in RUNTIME_PATHS:
        result = subprocess.run(
            ["git", "diff", "--quiet", "origin/main", "--", path],
            cwd=REPO_ROOT,
            check=False,
        )
        assert result.returncode == 0, f"release closure changed runtime path: {path}"

    closure = _text(CLOSURE_PATH)
    for line in (
        "P1_CANONICAL_IDENTITY=factory_power_estimation@2.0.0-p1",
        "WORKBENCH_READ_ONLY_PRESENTATION=YES",
        "AILY_READ_ONLY_PRESENTATION=YES",
        "WORKBENCH_AND_AILY_READ_SAME_RESULT=YES",
        "FRONTEND_RECALCULATION=NO",
        "AILY_RECALCULATION=NO",
        "INSTALLED_POWER_REPLACED=NO",
        "POWER_CONFIGURATION_USED_AS_V2_AUTHORITY=NO",
        "FIVE_STAGE_CALCULATION_TYPE_CHANGED=NO",
        "DATABASE_MIGRATION_CREATED_FOR_V20=NO",
        "OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED=NO",
        "P0_CONTRACT_CONTRADICTION=NONE",
        "P1_REVIEW_BLOCKER=NONE",
        "P2_REVIEW_BLOCKER=NONE",
        "FACTORY_AREA_AUTHORITY=EXPLICIT",
        "COLD_STORAGE_AREA_AUTHORITY=EXPLICIT",
        "RAW_POSITION_COUNT_FORBIDDEN=YES",
        "MINIMUM_ESTIMATED_COOLING_LOAD_KW_R_AUTHORITY=PRESERVED",
        "POOL_A_B_C_CONTRACT=PRESERVED",
        "MAIN_SYSTEM_COP=3.3",
        "CANONICAL_SOURCE_IDENTITY_PRESERVED=YES",
        "NO_NEW_RELEASE_BLOCKER=YES",
    ):
        assert line in closure


def test_v20_release_semantics_remain_concept_design_only() -> None:
    closure = _text(CLOSURE_PATH)
    assert "概念设计阶段的估算工厂电功率" in closure
    assert "单位为 `kW`" in closure
    for forbidden_semantic in (
        "不是 `kWh`",
        "不是电表计量值",
        "不是月度电费",
        "不是变压器选型",
        "不是正式配电设计",
        "不是短路计算",
        "不是电缆选型",
        "不是保护整定",
    ):
        assert forbidden_semantic in closure
