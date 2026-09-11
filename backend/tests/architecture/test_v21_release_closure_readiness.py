"""Durable architecture locks for the V2.1 release-closure readiness lane."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cold_storage.modules.aily.api.mcp_sse import _PREVIEW_TOOL_ORDER
from cold_storage.modules.aily.application.factory_power_preview import (
    PREVIEW_FACTORY_POWER_INPUT_FIELDS,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType
from cold_storage.modules.projects.application.factory_power_upstream_authority import (
    EXPECTED_FACTORY_ZONE_CODES,
    REFRIGERATED_ZONE_CODES,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_MAIN_SHA = "b314f08c74296e23e2a1729dd4f84dc8387c7a4e"
# The V2.1 release-closure scope is the immutable range from the PR #262
# merge commit to the v2.1.0 release merge commit.  Later HEADs are checked
# only for lineage below.
HISTORICAL_TASK_BASE_SHA = BASE_MAIN_SHA
HISTORICAL_TASK_TARGET_SHA = "2221077d4ebe0ee90e218b8869ccb3bb000b1d60"
V20_RELEASE_TARGET_SHA = "a7049ca93d238013c0cf62069fe1e0a89ff834d7"
CLOSURE_PATH = REPO_ROOT / "docs/tasks/V2_1-release-closure-readiness.md"
VERSION_PLAN_PATH = REPO_ROOT / "docs/tasks/V2_1-version-plan.md"
ADR_PATH = REPO_ROOT / "docs/architecture/ADR-043-factory-power-upstream-authority-doubao-mcp.md"
CURRENT_STATE_PATH = REPO_ROOT / "docs/audit/current-state.md"
GAP_ANALYSIS_PATH = REPO_ROOT / "docs/audit/gap-analysis.md"
DEVELOPMENT_PLAN_PATH = REPO_ROOT / "docs/roadmap/DEVELOPMENT_PLAN.md"
TECH_DEBT_PATH = REPO_ROOT / "docs/TECH_DEBT.md"
SKILL_JSON_PATH = REPO_ROOT / "docs/contracts/aily/v2.1/doubao-skill.v1.json"
SKILL_MD_PATH = REPO_ROOT / "docs/contracts/aily/v2.1/doubao-skill.v1.md"
RUNBOOK_PATH = REPO_ROOT / "docs/runbooks/v21-doubao-aily-connector.md"

ALLOWED_PATHS = {
    "backend/tests/architecture/test_v20_p0_factory_power_estimation_and_presentation_contract.py",
    "backend/tests/architecture/test_v20_p1_factory_power_estimation_canonical_result.py",
    "backend/tests/architecture/test_v20_p2_factory_power_read_only_presentation.py",
    "backend/tests/architecture/test_v20_release_closure_readiness.py",
    "backend/tests/architecture/test_v21_p2_factory_power_mcp_doubao_integration.py",
    "backend/tests/architecture/test_v21_p1_factory_power_upstream_authority.py",
    "backend/tests/architecture/test_v21_release_closure_readiness.py",
    "docs/architecture/ADR-043-factory-power-upstream-authority-doubao-mcp.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/tasks/V2_1-release-closure-readiness.md",
    "docs/tasks/V2_1-version-plan.md",
    "docs/TECH_DEBT.md",
}

FROZEN_PATHS = (
    "backend/src",
    "frontend/src",
    "backend/alembic",
    ".github/workflows",
    "deployment",
    "docs/contracts/aily/v1.8",
    "docs/contracts/aily/v2.1",
    "docs/runbooks/v18-doubao-aily-connector.md",
    "docs/runbooks/v21-doubao-aily-connector.md",
)

FIVE_TOOLS = (
    "preview_zone_plan",
    "preview_cooling_load",
    "preview_equipment",
    "preview_installed_power",
    "preview_investment",
)
ALL_TOOLS = (*FIVE_TOOLS, "preview_factory_power")
FACTORY_POWER_INPUTS = (
    "daily_inbound_mass_kg",
    "finished_storage_days",
    "frozen_storage_days",
    "main_packaging_storage_days",
    "auxiliary_packaging_storage_days",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _historical_changed_paths() -> set[str]:
    _assert_historical_target_is_ancestor_of_head()
    tracked = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            HISTORICAL_TASK_BASE_SHA,
            HISTORICAL_TASK_TARGET_SHA,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return {
        path.strip()
        for path in tracked
        if path.strip() and not path.strip().startswith("backend/artifacts/local/")
    }


def _assert_ancestor(ancestor: str, descendant: str = "HEAD") -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, f"{ancestor} must be an ancestor of {descendant}"


def _assert_historical_target_is_ancestor_of_head() -> None:
    _assert_ancestor(HISTORICAL_TASK_TARGET_SHA)


def test_v21_release_closure_scope_is_docs_and_architecture_only() -> None:
    changed = _historical_changed_paths()
    assert changed <= ALLOWED_PATHS
    assert not any(
        path == frozen or path.startswith(frozen + "/")
        for path in changed
        for frozen in FROZEN_PATHS
    )


def test_v21_release_lineage_is_durable_and_not_moving_origin_equality() -> None:
    _assert_ancestor(BASE_MAIN_SHA)
    _assert_ancestor(V20_RELEASE_TARGET_SHA)
    release_target = subprocess.run(
        ["git", "rev-parse", "v2.0.0^{}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert release_target == V20_RELEASE_TARGET_SHA

    closure = _text(CLOSURE_PATH)
    for marker in (
        "BASE_MAIN_SHA=b314f08c74296e23e2a1729dd4f84dc8387c7a4e",
        "V20_RELEASE=v2.0.0",
        "V20_RELEASE_TARGET_SHA=a7049ca93d238013c0cf62069fe1e0a89ff834d7",
        "V20_RELEASE_IS_ANCESTOR_OF_V21_CANDIDATE=YES",
        "BASE_MAIN_SHA_IS_ANCESTOR_OF_HEAD=YES",
        "FUTURE_V21_TAG_TARGET_POLICY=CLOSURE_MERGE_COMMIT_PLUS_EXACT_MAIN_CI_AND_SEPARATE_AUTHORIZATION",
    ):
        assert marker in closure
    assert "origin/main ==" not in closure


def test_v21_release_closure_records_all_merged_stages_and_gates() -> None:
    closure = _text(CLOSURE_PATH)
    required = (
        "TASK_ID=V21_RELEASE_CLOSURE_READINESS_R1",
        "TARGET_RELEASE=v2.1.0",
        "BASE_MAIN_CI_RUN_ID=34349430563",
        "BASE_MAIN_CI_RESULT=SUCCESS",
        "P0_STATUS=MERGED",
        "P1_STATUS=MERGED",
        "P2_STATUS=MERGED",
        "V21_IMPLEMENTATION_COMPLETE=YES",
        "V21_P3_DEFINED=NO",
        "V21_P3_EXECUTED=NO",
        "V21_RELEASE_CANDIDATE=YES",
        "V2_1_0_RELEASE_READY=YES",
        "V21_P0_PR_NUMBER=260",
        "V21_P0_MERGE_COMMIT_SHA=1d0a8e23f550b3c9ced413932fde0995acb227c0",
        "V21_P1_PR_NUMBER=261",
        "V21_P1_MERGE_COMMIT_SHA=95b6cbf839ba584f29f13735b07f8f8309b1cf37",
        "V21_P1_REVIEW_RESULT=PASS",
        "V21_P2_PR_NUMBER=262",
        "V21_P2_FINAL_HEAD_SHA=6c6bb2401b04a59f7b6fef7e02ffd47231bfd08b",
        "V21_P2_MERGE_COMMIT_SHA=b314f08c74296e23e2a1729dd4f84dc8387c7a4e",
        "V21_P2_REVIEW_RESULT=PASS",
        "V21_P2_BLOCKER_COUNT=0",
        "V21_P2_MAIN_CI_RUN_ID=34349430563",
        "V21_P2_MAIN_CI_RESULT=SUCCESS",
        "TAG_CREATION_AUTHORIZED=NO",
        "TAG_MOVEMENT_AUTHORIZED=NO",
        "GITHUB_RELEASE_CREATION_AUTHORIZED=NO",
        "DEPLOYMENT_AUTHORIZED=NO",
        "NEXT_FEATURE_LANE_AUTHORIZED=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    )
    for marker in required:
        assert marker in closure


def test_v21_release_closure_truth_up_preserves_historical_gate_snapshots() -> None:
    version_plan = _text(VERSION_PLAN_PATH)
    adr = _text(ADR_PATH)
    current_state = _text(CURRENT_STATE_PATH)
    gap_analysis = _text(GAP_ANALYSIS_PATH)
    development_plan = _text(DEVELOPMENT_PLAN_PATH)
    tech_debt = _text(TECH_DEBT_PATH)

    assert "P2_STATUS=IMPLEMENTATION_ACTIVE" in version_plan
    assert "P2_STATUS=IMPLEMENTATION_ACTIVE" in adr
    assert "P2_STATUS=IMPLEMENTATION_ACTIVE" in current_state
    assert "P2_STATUS=IMPLEMENTATION_ACTIVE" in gap_analysis
    assert "P2_STATUS=IMPLEMENTATION_ACTIVE" in development_plan
    assert "P2_STATUS=IMPLEMENTATION_ACTIVE" in tech_debt
    assert "RELEASE_CLOSURE=UNAUTHORIZED" in version_plan
    assert "RELEASE_CLOSURE=UNAUTHORIZED" in adr
    assert "RELEASE_CLOSURE=UNAUTHORIZED" in current_state
    assert "RELEASE_CLOSURE=UNAUTHORIZED" in gap_analysis
    assert "RELEASE_CLOSURE=UNAUTHORIZED" in development_plan
    assert "RELEASE_CLOSURE=UNAUTHORIZED" in tech_debt

    for text in (version_plan, adr, current_state, gap_analysis, development_plan, tech_debt):
        assert "V21_IMPLEMENTATION_COMPLETE=YES" in text
        assert "V2_1_0_RELEASE_READY=YES" in text
        assert "ACTIVE_GOVERNANCE_LANE=V2.1_RELEASE_CLOSURE" in text
        assert "NEXT_FEATURE_LANE_AUTHORIZED=NO" in text
        assert "NO_STEP_IMPLIES_THE_NEXT=TRUE" in text

    for debt_id in ("TD-008", "TD-019", "TD-021", "TD-024"):
        assert debt_id in tech_debt


def test_v21_release_closure_preserves_runtime_authorities_and_product_boundaries() -> None:
    _assert_historical_target_is_ancestor_of_head()
    closure = _text(CLOSURE_PATH)
    adapter = _text(
        REPO_ROOT / "backend/src/cold_storage/modules/projects/application/"
        "factory_power_upstream_authority.py"
    )
    concept_preview = _text(
        REPO_ROOT / "backend/src/cold_storage/modules/aily/application/concept_preview.py"
    )

    for marker in (
        "FACTORY_AREA_AUTHORITY=CANONICAL_12_ZONE_ROWS",
        "FACTORY_ZONE_COUNT=12",
        "FACTORY_AREA_FROM_USER=NO",
        "FACTORY_AREA_FROM_DOUBAO=NO",
        "FACTORY_AREA_FROM_LLM=NO",
        "FACTORY_AREA_TOTAL_CROSS_CHECK=YES",
        "COLD_STORAGE_AREA_AUTHORITY=REFRIGERATED_ZONE_REGISTRY",
        "REFRIGERATED_ZONE_COUNT=9",
        "FROZEN_FRUIT_ROOM_INCLUDED=YES",
        "SHIPPING_CHANNEL_INCLUDED=YES",
        "REFRIGERATED_AREA_M2_IS_AUTHORITY=NO",
        "FACTORY_POWER_CALCULATOR_IDENTITY=factory_power_estimation@2.0.0-p1",
        "MAIN_SYSTEM_COP=3.3",
        "POOL_A=DEFROST",
        "POOL_B=OTHER",
        "POOL_C=PRODUCTION",
        "FACTORY_POWER_FORMULA_RECUT=NO",
        "AILY_FACTORY_POWER_ENGINEERING_ENTRYPOINT=P1_ADAPTER_ONLY",
        "RAW_POSITION_COUNT_FORBIDDEN=YES",
        "MINIMUM_ESTIMATED_COOLING_LOAD_KW_R_AUTHORITY=PRESERVED",
        "V20_CALCULATOR_CHANGED=NO",
        "V20_SHARED_PRESENTATION_CHANGED=NO",
        "RUNTIME_CHANGED=NO",
        "DATABASE_MIGRATION_CREATED=NO",
        "DEPLOYMENT_CHANGED=NO",
        "CONCEPT_PREVIEW_STAGE_COUNT=5",
        "CALCULATION_TYPE_COUNT=5",
    ):
        assert marker in closure

    for error_code in (
        "DUPLICATE_ZONE_CODE",
        "ZONE_AUTHORITY_SET_MISMATCH",
        "MISSING_ZONE_REQUIRED_AREA",
        "INVALID_ZONE_REQUIRED_AREA",
        "FACTORY_AREA_TOTAL_MISMATCH",
    ):
        assert error_code in adapter

    assert tuple(EXPECTED_FACTORY_ZONE_CODES) == (
        "office",
        "changing_room",
        "primary_precooling_room",
        "secondary_precooling_room",
        "raw_fruit_buffer",
        "sorting_packaging_room",
        "coating_room",
        "finished_goods_room",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "packaging_material_storage",
        "shipping_channel",
    )
    assert len(EXPECTED_FACTORY_ZONE_CODES) == 12
    assert len(REFRIGERATED_ZONE_CODES) == 9
    assert len(CalculationType) == 5
    assert "factory_power" not in concept_preview

    for path in FROZEN_PATHS:
        result = subprocess.run(
            [
                "git",
                "diff",
                "--quiet",
                HISTORICAL_TASK_BASE_SHA,
                HISTORICAL_TASK_TARGET_SHA,
                "--",
                path,
            ],
            cwd=REPO_ROOT,
            check=False,
        )
        assert result.returncode == 0, f"release closure changed frozen path: {path}"


def test_v21_release_closure_locks_six_tool_flat_five_key_stateless_contract() -> None:
    closure = _text(CLOSURE_PATH)
    skill = json.loads(SKILL_JSON_PATH.read_text(encoding="utf-8"))
    skill_text = _text(SKILL_MD_PATH)
    mcp_source = _text(REPO_ROOT / "backend/src/cold_storage/modules/aily/api/mcp_sse.py")

    assert tuple(_PREVIEW_TOOL_ORDER) == ALL_TOOLS
    assert tuple(PREVIEW_FACTORY_POWER_INPUT_FIELDS) == FACTORY_POWER_INPUTS
    assert skill["governance"]["MCP_TOOL_COUNT"] == 6
    assert skill["governance"]["FACTORY_POWER_ACCEPTS_FLAT_TOP_LEVEL_FIVE_KEY_ONLY"] == "YES"
    assert skill["governance"]["FACTORY_POWER_ZONE_PLANNING_INPUTS_WRAPPER_ALLOWED"] == "NO"
    assert skill["governance"]["FACTORY_POWER_REQUIRES_PRECEDING_ZONE_TOOL_CALL"] == "NO"
    assert skill["factory_power"]["input_shape"] == "flat_top_level_five_keys_only"
    assert skill["factory_power"]["zone_planning_inputs_wrapper_allowed"] is False
    assert skill["factory_power"]["requires_preceding_preview_zone_plan"] is False

    for marker in (
        "MCP_TOOL_COUNT=6",
        "NEW_MCP_TOOL=preview_factory_power",
        "NEW_TOOL_POSITION=6",
        "EXISTING_FIVE_TOOL_ORDER_CHANGED=NO",
        "FACTORY_POWER_INPUT_KEY_COUNT=5",
        "FACTORY_POWER_INPUT_SHAPE=FLAT_TOP_LEVEL_FIVE_KEYS_ONLY",
        "FACTORY_POWER_FLAT_FIVE_KEY_ONLY=YES",
        "FACTORY_POWER_REQUIRES_PRECEDING_ZONE_TOOL_CALL=NO",
        "BACKEND_STATELESS_ZONE_PLAN_REPLAY=YES",
        "DOUBAO_CARRIES_ZONE_RESULT=NO",
        "DOUBAO_CARRIES_ENGINEERING_AREA=NO",
        "FACTORY_POWER_SHARED_PROJECTOR=project_factory_power_table",
        "MCP_ENGINEERING_RECALCULATION=NO",
        "MARKDOWN_ENGINEERING_RECALCULATION=NO",
        "V21_SKILL_STANDALONE_V18_SEMANTIC_SUPERSET=YES",
        "FACTORY_POWER_ZONE_PLANNING_INPUTS_WRAPPER_ALLOWED=NO",
        "AGENT_TO_ENGINEERING_VALUE=NO",
        "AILY_OUTBOUND_LIVE_SESSION=NO",
        "SERVER_SIDE_CHAT_NLP=NO",
    ):
        assert marker in closure

    assert "preview_factory_power" in mcp_source
    assert "installed_power@1.0.0" in skill_text
    assert "preview_factory_power" in skill_text
    assert "preview_factory_power` 只接受五个顶层 KEY" in skill_text
    assert "zone_planning_inputs` 包裹对象" in skill_text
    assert "不适用于 `preview_factory_power`" in skill_text
    assert skill["governance"]["KEEP_AILY_V18_SKILL_FROZEN"] == "YES"
    assert RUNBOOK_PATH.is_file()


def test_v21_release_closure_blocker_audit_and_release_execution_gate_are_explicit() -> None:
    closure = _text(CLOSURE_PATH)
    for marker in (
        "P0_CONTRACT_CONTRADICTION=NONE",
        "P1_REVIEW_BLOCKER=NONE",
        "P2_REVIEW_BLOCKER=NONE",
        "FACTORY_AREA_AUTHORITY=EXPLICIT",
        "COLD_STORAGE_AREA_AUTHORITY=EXPLICIT",
        "V20_CALCULATOR_AUTHORITY=PRESERVED",
        "P1_ADAPTER_AUTHORITY=PRESERVED",
        "MCP_SIX_TOOL_CONTRACT=PASS",
        "FIVE_KEY_INPUT_CONTRACT=PASS",
        "DOUBAO_SKILL_CONTRACT=PASS",
        "CANONICAL_RESULT_HASH_PARITY=PASS",
        "DETAILS_PARITY=PASS",
        "SUMMARY_PARITY=PASS",
        "V18_COMPATIBILITY=PASS",
        "V20_RUNTIME_REGRESSION=PASS",
        "V21_RUNTIME_REGRESSION=PASS",
        "ARCHITECTURE=PASS",
        "MAIN_LINEAGE=PASS",
        "EXACT_MAIN_CI=PASS",
        "NO_NEW_RELEASE_BLOCKER=YES",
        "RELEASE_EXECUTION=NO",
        "TAG_CREATED=NO",
        "TAG_MOVED=NO",
        "GITHUB_RELEASE_CREATED=NO",
        "DEPLOYMENT_EXECUTED=NO",
        "READY_EXECUTED=NO",
        "MERGE_EXECUTED=NO",
        "NEXT_FEATURE_LANE_AUTHORIZED=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    ):
        assert marker in closure

    assert "V2_1_0_TAG_TARGET=b314f08c74296e23e2a1729dd4f84dc8387c7a4e" not in closure
    assert "V2_1_0_TAG_EXISTS_AT_CLOSURE_START=NO" in closure
    assert "V2_1_0_GITHUB_RELEASE_EXISTS_AT_CLOSURE_START=NO" in closure
