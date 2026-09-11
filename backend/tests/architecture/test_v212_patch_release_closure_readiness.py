"""Durable architecture locks for the V2.1.2 patch release closure."""

from __future__ import annotations

import json
import subprocess
from decimal import Decimal
from pathlib import Path

from cold_storage.modules.aily.api.mcp_sse import _PREVIEW_TOOL_ORDER
from cold_storage.modules.calculations.domain.factory_power_estimation import (
    CALCULATOR_IDENTITY,
    CALCULATOR_VERSION,
    DEFROST_SIMULTANEOUS_USE_FACTOR,
    RESULT_SCHEMA_VERSION,
)
from cold_storage.modules.calculations.domain.zone_planning import (
    FORMULA_AUTHORITY,
    PRIMARY_PRECOOL_BATCHES_PER_DAY,
    PRIMARY_PRECOOL_Q_D_KG_DAY,
    SORTING_PACKAGING_AREA_FACTOR,
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType

REPO_ROOT = Path(__file__).resolve().parents[3]

BASE_RELEASE_SHA = "c9ce6e7399ec2a163ab4c7c7339b828a86abbf08"
PATCH_TARGET_SHA = "bdbedf885b8b42a3ca18aec9df2746a9505fee33"
V20_TAG_TARGET = "a7049ca93d238013c0cf62069fe1e0a89ff834d7"
V21_0_TAG_TARGET = "2221077d4ebe0ee90e218b8869ccb3bb000b1d60"
V21_1_TAG_TARGET = BASE_RELEASE_SHA

# This immutable candidate snapshot contains the closure docs and truth-up.
# The architecture evidence file is intentionally added in the following
# commit, and checks this snapshot plus its ancestry rather than using a
# moving origin/main or the current HEAD as a historical diff endpoint.
CLOSURE_SCOPE_BASE_SHA = PATCH_TARGET_SHA
CLOSURE_SCOPE_CANDIDATE_SHA = "555d0b9cba047fcd90c2a8aaf9398371a175d731"

CLOSURE_PATH = REPO_ROOT / "docs/tasks/V2_1_2-patch-release-closure-readiness.md"
HISTORICAL_P1_GOLDEN_PATH = (
    REPO_ROOT / "backend/tests/golden/v20_factory_power_canonical_result_v1.json"
)

CLOSURE_SCOPE_ALLOWED_PATHS = {
    "docs/TECH_DEBT.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/tasks/V2_1-version-plan.md",
    "docs/tasks/V2_1_2-patch-release-closure-readiness.md",
}
FROZEN_SCOPE_PREFIXES = (
    "backend/src",
    "frontend/src",
    "backend/alembic",
    ".github/workflows",
    "deployment",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _git_stdout(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _assert_ancestor(ancestor: str, descendant: str = "HEAD") -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, f"{ancestor} must be an ancestor of {descendant}"


def _historical_changed_paths() -> set[str]:
    _assert_ancestor(CLOSURE_SCOPE_CANDIDATE_SHA)
    output = _git_stdout(
        "diff",
        "--name-only",
        CLOSURE_SCOPE_BASE_SHA,
        CLOSURE_SCOPE_CANDIDATE_SHA,
    )
    return {path for path in output.splitlines() if path}


def _representative_current_input() -> ColdRoomZonePlanInput:
    return ColdRoomZonePlanInput(
        daily_inbound_mass_kg=20_000,
        working_time_h_per_day=16,
        finished_storage_days=7,
        packaging_storage_days=3,
        precooling_required_ratio=1,
        frozen_storage_days=10,
        main_packaging_storage_days=4,
        auxiliary_packaging_storage_days=12,
    )


def test_v212_closure_scope_uses_immutable_candidate_snapshot() -> None:
    changed = _historical_changed_paths()
    assert changed <= CLOSURE_SCOPE_ALLOWED_PATHS
    assert not any(
        path == prefix or path.startswith(prefix + "/")
        for path in changed
        for prefix in FROZEN_SCOPE_PREFIXES
    )

    closure = _text(CLOSURE_PATH)
    assert f"CLOSURE_SCOPE_BASE_SHA={CLOSURE_SCOPE_BASE_SHA}" in closure
    assert "CLOSURE_SCOPE_CANDIDATE_SHA_RECORDED_IN_ARCHITECTURE_TEST=YES" in closure
    assert "CLOSURE_SCOPE_TARGET_IS_IMMUTABLE=YES" in closure
    assert "CURRENT_HEAD_USED_ONLY_FOR_LINEAGE=YES" in closure
    assert "ORIGIN_MAIN_DYNAMIC_SCOPE_DIFF=NO" in closure
    assert "origin/main ==" not in closure


def test_v212_release_lineage_and_exact_main_ci_are_recorded() -> None:
    _assert_ancestor(BASE_RELEASE_SHA)
    _assert_ancestor(PATCH_TARGET_SHA)
    assert _git_stdout("rev-parse", "v2.0.0^{}") == V20_TAG_TARGET
    assert _git_stdout("rev-parse", "v2.1.0^{}") == V21_0_TAG_TARGET
    assert _git_stdout("rev-parse", "v2.1.1^{}") == V21_1_TAG_TARGET

    closure = _text(CLOSURE_PATH)
    for marker in (
        "TASK_ID=V2_1_2_PATCH_RELEASE_CLOSURE_R1",
        "BASE_RELEASE=v2.1.1",
        f"BASE_RELEASE_SHA={BASE_RELEASE_SHA}",
        "PATCH_SOURCE_PR=266",
        f"PATCH_SOURCE_MERGE_SHA={PATCH_TARGET_SHA}",
        "PATCH_TARGET=v2.1.2",
        f"PATCH_TARGET_SHA={PATCH_TARGET_SHA}",
        "MAIN_CI_RUN_ID=34567481057",
        "MAIN_CI_RUN_NUMBER=2352",
        f"MAIN_CI_SHA={PATCH_TARGET_SHA}",
        "MAIN_CI_SHA_MATCH=YES",
        "MAIN_CI_RESULT=SUCCESS",
        "V2_1_2_RELEASE_CANDIDATE=YES",
        "V2_1_2_RELEASE_READY=YES",
        "TAG_AUTHORIZED=NO",
        "GITHUB_RELEASE_AUTHORIZED=NO",
        "DEPLOYMENT_AUTHORIZED=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    ):
        assert marker in closure


def test_v212_current_representative_result_is_canonical_replay() -> None:
    result = ColdRoomZonePlanner().plan(_representative_current_input())

    assert result.success is True
    assert FORMULA_AUTHORITY == "POST-V2.1.1-charles-engineering-rule-adjustments"
    assert result.result["planning_parameters"]["formula_authority"] == FORMULA_AUTHORITY

    zones = {zone["zone_code"]: zone for zone in result.result["zones"]}
    primary = zones["primary_precooling_room"]
    secondary = zones["secondary_precooling_room"]
    sorting = zones["sorting_packaging_room"]

    assert PRIMARY_PRECOOL_BATCHES_PER_DAY == 7
    assert PRIMARY_PRECOOL_Q_D_KG_DAY == 1540
    assert primary["required_area_m2"] == 126
    assert primary["position_daily_capacity_kg_day"] == 1540

    assert secondary["working_hours_per_day"] == 14
    assert secondary["position_daily_capacity_kg_day"] == 2800
    assert secondary["required_area_m2"] == 84

    assert sorting["person_daily_capacity_kg_day"] == 336
    assert sorting["raw_required_area_m2"] == 565.76
    assert sorting["sorting_packaging_area_factor"] == SORTING_PACKAGING_AREA_FACTOR
    assert sorting["required_area_m2"] == 622.34
    assert result.result["total_area_m2"] == 2194.59

    closure = _text(CLOSURE_PATH)
    for marker in (
        "PRIMARY_PRECOOL_AREA_20T_M2=126.00",
        "SECONDARY_PRECOOL_AREA_20T_M2=84.00",
        "SORTING_PACKAGING_RAW_AREA_20T_M2=565.76",
        "SORTING_PACKAGING_FINAL_AREA_20T_M2=622.34",
        "TOTAL_AREA_20T_M2=2194.59",
        "REPRESENTATIVE_CANONICAL_REPLAY=PASS",
    ):
        assert marker in closure


def test_v212_current_factory_power_and_consumer_boundaries_are_locked() -> None:
    assert CALCULATOR_VERSION == "2.0.0-p2"
    assert CALCULATOR_IDENTITY == "factory_power_estimation@2.0.0-p2"
    assert RESULT_SCHEMA_VERSION == "2.0.0-p1"
    assert Decimal("0.20") == DEFROST_SIMULTANEOUS_USE_FACTOR
    assert _PREVIEW_TOOL_ORDER == (
        "preview_zone_plan",
        "preview_cooling_load",
        "preview_equipment",
        "preview_installed_power",
        "preview_investment",
        "preview_factory_power",
    )
    assert len(CalculationType) == 5

    closure = _text(CLOSURE_PATH)
    for marker in (
        "FACTORY_POWER_CALCULATOR_VERSION=2.0.0-p2",
        "FACTORY_POWER_CALCULATOR_IDENTITY=factory_power_estimation@2.0.0-p2",
        "RESULT_SCHEMA_VERSION=2.0.0-p1",
        "MCP_TOOL_COUNT=6",
        "MCP_CONTRACT_CHANGED=NO",
        "DOUBAO_SKILL_CHANGED=NO",
        "DATABASE_MIGRATION_CHANGED=NO",
        "DEPLOYMENT_CHANGED=NO",
        "PRODUCTION_CODE_CHANGED=NO",
        "FRONTEND_PRODUCTION_CODE_CHANGED=NO",
    ):
        assert marker in closure


def test_v212_historical_p1_golden_and_tags_remain_immutable() -> None:
    golden = json.loads(_text(HISTORICAL_P1_GOLDEN_PATH))
    assert golden["schema_version"] == "2.0.0-p1"
    assert golden["calculator"]["version"] == "2.0.0-p1"
    assert golden["calculator"]["identity"] == "factory_power_estimation@2.0.0-p1"
    assert Decimal(golden["summary"]["defrost_coincident_power_kw"]) / Decimal(
        golden["summary"]["defrost_installed_power_kw"]
    ) == Decimal("0.30")

    golden_relative_path = HISTORICAL_P1_GOLDEN_PATH.relative_to(REPO_ROOT).as_posix()
    result = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            "v2.0.0",
            PATCH_TARGET_SHA,
            "--",
            golden_relative_path,
        ],
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, "historical V2.0 factory-power golden must not change"

    closure = _text(CLOSURE_PATH)
    for marker in (
        "V2_1_0_TAG_TARGET=2221077d4ebe0ee90e218b8869ccb3bb000b1d60",
        "V2_1_0_TAG_UNCHANGED=YES",
        "V2_1_1_TAG_TARGET=c9ce6e7399ec2a163ab4c7c7339b828a86abbf08",
        "V2_1_1_TAG_UNCHANGED=YES",
        "HISTORICAL_FACTORY_POWER_CALCULATOR_IDENTITY=factory_power_estimation@2.0.0-p1",
        "HISTORICAL_DEFROST_SIMULTANEOUS_FACTOR=0.30",
        "HISTORICAL_GOLDEN_CHANGED=NO",
        "V20_RELEASE_EVIDENCE_CHANGED=NO",
        "V21_RELEASE_EVIDENCE_CHANGED=NO",
        "V211_RELEASE_EVIDENCE_CHANGED=NO",
    ):
        assert marker in closure


def test_v212_closure_preserves_release_execution_boundaries() -> None:
    closure = _text(CLOSURE_PATH)
    for marker in (
        "TAG_CREATED=NO",
        "GITHUB_RELEASE_CREATED=NO",
        "DEPLOYMENT_EXECUTED=NO",
        "READY_AUTHORIZED=NO",
        "MERGE_AUTHORIZED=NO",
        "TAG_CREATION_AUTHORIZED=NO",
        "GITHUB_RELEASE_CREATION_AUTHORIZED=NO",
        "DEPLOYMENT_AUTHORIZED=NO",
        "NEXT_FEATURE_LANE_AUTHORIZED=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    ):
        assert marker in closure
