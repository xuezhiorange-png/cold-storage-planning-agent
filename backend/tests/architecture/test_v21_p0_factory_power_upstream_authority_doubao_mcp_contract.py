"""Architecture locks for the V2.1 P0 authority and MCP contract freeze.

This test reads the P0 contract and the existing V2.0/V1.8 surfaces.  Its
scope assertion is a historical P0 range so later P1/P2 lanes do not get
misclassified as P0 changes when ``origin/main`` advances.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from cold_storage.modules.calculations.domain.zone_planning import ColdRoomZonePlanner
from cold_storage.modules.orchestration.domain.contracts import CalculationType
from cold_storage.modules.planning.application.service import (
    build_zone_plan_from_inputs,
    demo_inputs,
)
from cold_storage.modules.projects.application.operator_process_input import (
    REFRIGERATED_ZONE_REGISTRY,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = (
    REPO_ROOT / "docs" / "tasks" / "V2_1-P0-factory-power-upstream-authority-doubao-mcp-contract.md"
)
VERSION_PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V2_1-version-plan.md"
ADR_PATH = (
    REPO_ROOT / "docs" / "architecture" / "ADR-043-factory-power-upstream-authority-doubao-mcp.md"
)
V20_VERSION_PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V2_0-version-plan.md"
V20_CLOSURE_PATH = REPO_ROOT / "docs" / "tasks" / "V2_0-release-closure-readiness.md"
ADR042_PATH = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "ADR-042-factory-power-estimation-and-presentation-contract.md"
)
CURRENT_STATE_PATH = REPO_ROOT / "docs" / "audit" / "current-state.md"
GAP_ANALYSIS_PATH = REPO_ROOT / "docs" / "audit" / "gap-analysis.md"
DEVELOPMENT_PLAN_PATH = REPO_ROOT / "docs" / "roadmap" / "DEVELOPMENT_PLAN.md"
TECH_DEBT_PATH = REPO_ROOT / "docs" / "TECH_DEBT.md"

BASE_MAIN_SHA = "a7049ca93d238013c0cf62069fe1e0a89ff834d7"
# Immutable final commit of the merged P0 contract branch.  Keep the P0 scope
# lock on this historical range instead of comparing a follow-on lane with a
# moving origin/main.
P0_REFERENCE_HEAD_SHA = "843c48f55016f0bd993afccc279e5c8a8fc271a7"
GENERATED_ARTIFACT_PREFIX = "backend/artifacts/local/"

EXPECTED_FACTORY_ZONE_CODES = (
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
EXPECTED_FIVE_KEYS = (
    "daily_inbound_mass_kg",
    "finished_storage_days",
    "frozen_storage_days",
    "main_packaging_storage_days",
    "auxiliary_packaging_storage_days",
)
EXPECTED_TOOL_ORDER = (
    "preview_zone_plan",
    "preview_cooling_load",
    "preview_equipment",
    "preview_installed_power",
    "preview_investment",
)
EXPECTED_REFREGISTRY = (
    ("primary_precooling_room", "8~10℃"),
    ("secondary_precooling_room", "1~3℃"),
    ("raw_fruit_buffer", "8~10℃"),
    ("sorting_packaging_room", "8~10℃"),
    ("coating_room", "1~3℃"),
    ("finished_goods_room", "1~3℃"),
    ("secondary_fruit_buffer", "8~10℃"),
    ("frozen_fruit_room", "-18℃"),
    ("shipping_channel", "1~3℃"),
)

V20_RUNTIME_PATHS = (
    "backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py",
    "backend/src/cold_storage/modules/calculations/application/factory_power_presentation.py",
    "backend/src/cold_storage/modules/aily/application/factory_power_table.py",
    "backend/src/cold_storage/modules/aily/application/mcp_stage_preview.py",
    "backend/src/cold_storage/modules/aily/application/mcp_zone_plan.py",
    "frontend/src/features/calculations/model/mapFactoryPowerPresentation.ts",
    "frontend/src/features/calculations/components/FactoryPowerEstimationResults.vue",
)

V18_FROZEN_PATHS = (
    "docs/contracts/aily/v1.8",
    "docs/runbooks/v18-doubao-aily-connector.md",
)

EXPECTED_CHANGED_PATHS = {
    "backend/tests/architecture/test_v21_p0_factory_power_upstream_authority_doubao_mcp_contract.py",
    "backend/tests/architecture/test_v20_p0_factory_power_estimation_and_presentation_contract.py",
    "backend/tests/architecture/test_v20_p1_factory_power_estimation_canonical_result.py",
    "backend/tests/architecture/test_v20_p2_factory_power_read_only_presentation.py",
    "backend/tests/architecture/test_v20_release_closure_readiness.py",
    "docs/tasks/V2_1-version-plan.md",
    "docs/tasks/V2_1-P0-factory-power-upstream-authority-doubao-mcp-contract.md",
    "docs/architecture/ADR-043-factory-power-upstream-authority-doubao-mcp.md",
    "docs/tasks/V2_0-version-plan.md",
    "docs/tasks/V2_0-release-closure-readiness.md",
    "docs/architecture/ADR-042-factory-power-estimation-and-presentation-contract.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/TECH_DEBT.md",
}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _contract_data() -> dict[str, Any]:
    match = re.search(r"~~~json\n(.*?)\n~~~", _text(CONTRACT_PATH), flags=re.DOTALL)
    assert match is not None, "V2.1 P0 contract must contain a JSON matrix"
    data = json.loads(match.group(1))
    assert isinstance(data, dict)
    return data


def _changed_paths() -> set[str]:
    tracked = subprocess.run(
        ["git", "diff", "--name-only", BASE_MAIN_SHA, P0_REFERENCE_HEAD_SHA],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return {
        path.strip()
        for path in tracked
        if path.strip() and not path.strip().startswith(GENERATED_ARTIFACT_PREFIX)
    }


def _git_diff_is_empty(*paths: str) -> bool:
    result = subprocess.run(
        ["git", "diff", "--quiet", "origin/main", "--", *paths],
        cwd=REPO_ROOT,
        check=False,
    )
    return result.returncode == 0


def _runtime_zone_rows() -> tuple[dict[str, Any], ...]:
    zone_plan = build_zone_plan_from_inputs(demo_inputs(), ColdRoomZonePlanner())
    assert zone_plan.success, "canonical ColdRoomZonePlanner fixture must succeed"
    zones = zone_plan.result.get("zones")
    assert isinstance(zones, list)

    rows: list[dict[str, Any]] = []
    for zone in zones:
        assert isinstance(zone, dict)
        zone_code = zone.get("zone_code")
        assert isinstance(zone_code, str)
        rows.append(zone)
    return tuple(rows)


def _runtime_factory_zone_codes() -> tuple[str, ...]:
    return tuple(str(zone["zone_code"]) for zone in _runtime_zone_rows())


def test_v21_p0_scope_is_contract_docs_and_architecture_only() -> None:
    changed = _changed_paths()
    assert changed <= EXPECTED_CHANGED_PATHS
    assert not any(path.startswith("backend/src/") for path in changed)
    assert not any(path.startswith("frontend/src/") for path in changed)
    assert not any(path.startswith("backend/alembic/") for path in changed)
    assert not any(path.startswith(".github/workflows/") for path in changed)
    assert not any(path.startswith("deployment/") for path in changed)


def test_v21_p0_base_release_and_gate_are_explicit() -> None:
    data = _contract_data()
    assert data["contract_id"] == (
        "V21_P0_FACTORY_POWER_UPSTREAM_AUTHORITY_AND_DOUBAO_MCP_CONTRACT_R1"
    )
    assert data["target_version"] == "v2.1.0"
    assert data["base_release"] == "v2.0.0"
    assert data["base_main_sha"] == BASE_MAIN_SHA
    assert (
        subprocess.run(
            ["git", "rev-parse", "v2.0.0^{}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        == BASE_MAIN_SHA
    )
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", BASE_MAIN_SHA, "HEAD"],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        == 0
    )

    gates = data["gates"]
    assert gates["contract_freeze"] is True
    for gate in (
        "runtime_implementation",
        "mcp_implementation",
        "skill_implementation",
        "database_migration",
        "ready",
        "merge",
        "tag",
        "release",
        "deployment",
    ):
        assert gates[gate] is False
    assert gates["no_step_implies_the_next"] is True

    contract = _text(CONTRACT_PATH)
    version_plan = _text(VERSION_PLAN_PATH)
    adr = _text(ADR_PATH)
    for text in (contract, version_plan, adr):
        assert "CONTRACT_FREEZE=YES" in text
        assert "RUNTIME_IMPLEMENTATION=NO" in text
        assert "MCP_IMPLEMENTATION=NO" in text
        assert "SKILL_IMPLEMENTATION=NO" in text
        assert "DATABASE_MIGRATION=NO" in text
        assert "READY=NO" in text
        assert "MERGE=NO" in text
        assert "TAG=NO" in text
        assert "RELEASE=NO" in text
        assert "DEPLOYMENT=NO" in text
        assert "NO_STEP_IMPLIES_THE_NEXT=TRUE" in text


def test_v21_p0_keeps_five_keys_and_rejects_area_inputs() -> None:
    data = _contract_data()
    operator_input = data["operator_input"]
    assert tuple(operator_input["fields"]) == EXPECTED_FIVE_KEYS
    assert operator_input["additional_properties"] is False
    assert set(operator_input["forbidden_fields"]) == {
        "factory_area_m2",
        "cold_storage_area_m2",
        "refrigerated_area_m2",
        "total_area_m2",
    }

    mcp_schema = data["doubao_mcp"]["input_schema"]
    assert mcp_schema["type"] == "object"
    assert tuple(mcp_schema["properties"]) == EXPECTED_FIVE_KEYS
    assert tuple(mcp_schema["required"]) == EXPECTED_FIVE_KEYS
    assert mcp_schema["additionalProperties"] is False
    assert not set(mcp_schema["properties"]) & {
        "factory_area_m2",
        "cold_storage_area_m2",
        "refrigerated_area_m2",
        "total_area_m2",
    }

    contract = _text(CONTRACT_PATH)
    assert "factory_area_m2=9999" in contract
    assert "cold_storage_area_m2" in contract
    assert "refrigerated_area_m2" in contract
    assert "total_area_m2" in contract
    assert "MCP_INPUT_SCHEMA_REJECTED" in contract


def test_v21_p0_binds_factory_area_from_exact_12_zone_set() -> None:
    data = _contract_data()
    factory_area = data["factory_area"]
    assert factory_area["source"] == "zone_plan.result.zones[].required_area_m2"
    assert factory_area["semantic"] == "SUM_ALL_PLANNED_FUNCTIONAL_ZONES"
    assert factory_area["formula"] == (
        "quantize_0_01(SUM(Decimal(str(zone.required_area_m2)) FOR zone IN zones))"
    )
    assert tuple(factory_area["zone_codes"]) == EXPECTED_FACTORY_ZONE_CODES
    assert len(factory_area["zone_codes"]) == 12
    assert tuple(factory_area["total_cross_checks"]) == (
        "total_required_area_m2",
        "total_area_m2",
    )
    assert factory_area["mismatch_error"] == "FACTORY_AREA_TOTAL_MISMATCH"

    contract = _text(CONTRACT_PATH)
    for line in (
        "AREA_COMES_FROM_ZONE_PLAN=YES",
        "AREA_COMES_FROM_USER=NO",
        "AREA_COMES_FROM_LLM=NO",
        "AREA_COMES_FROM_LEGACY_POWER=NO",
        "FACTORY_ZONE_COUNT=12",
        "FACTORY_AREA_SEMANTIC=SUM_ALL_PLANNED_FUNCTIONAL_ZONES",
        "total_required_area_m2 == derived_factory_area",
        "total_area_m2 == derived_factory_area",
        "FACTORY_AREA_TOTAL_MISMATCH",
    ):
        assert line in contract


def test_v21_p0_factory_zone_contract_is_bound_to_runtime_planner() -> None:
    data = _contract_data()
    contract_zone_codes = tuple(data["factory_area"]["zone_codes"])
    runtime_zone_rows = _runtime_zone_rows()
    runtime_zone_codes = tuple(str(zone["zone_code"]) for zone in runtime_zone_rows)

    assert len(runtime_zone_codes) == 12
    assert len(set(runtime_zone_codes)) == len(runtime_zone_codes)
    assert runtime_zone_codes == contract_zone_codes

    runtime_binding = data["runtime_binding"]
    assert runtime_binding["planner"] == "ColdRoomZonePlanner"
    assert runtime_binding["result_path"] == "zone_plan.result.zones[].zone_code"
    assert runtime_binding["contract_equality"] == (
        "CONTRACT_EXPECTED_ZONE_SET == RUNTIME_COLD_ROOM_ZONE_PLANNER_ZONE_SET"
    )
    assert runtime_binding["refrigerated_registry"] == "REFRIGERATED_ZONE_REGISTRY"
    assert runtime_binding["refrigerated_temperature_scope"] == "REFRIGERATED_ONLY"

    runtime_zone_by_code = {
        str(zone["zone_code"]): str(zone["temperature_band"]) for zone in runtime_zone_rows
    }
    runtime_registry = tuple(
        (str(zone_code), runtime_zone_by_code[str(zone_code)])
        for zone_code, _zone_name, _temperature_band in REFRIGERATED_ZONE_REGISTRY
    )
    assert runtime_registry == EXPECTED_REFREGISTRY


def test_v21_p0_binds_cold_storage_area_from_existing_registry() -> None:
    data = _contract_data()
    cold_area = data["cold_storage_area"]
    actual_registry = tuple(
        (str(zone_code), str(temperature_band))
        for zone_code, _zone_name, temperature_band in REFRIGERATED_ZONE_REGISTRY
    )
    documented_registry = tuple(
        (str(entry["zone_code"]), str(entry["temperature_band"]))
        for entry in cold_area["zone_temperature_bands"]
    )
    assert actual_registry == EXPECTED_REFREGISTRY
    assert documented_registry == EXPECTED_REFREGISTRY
    assert tuple(cold_area["included"]) == tuple(zone_code for zone_code, _ in EXPECTED_REFREGISTRY)
    assert set(cold_area["excluded"]) == {
        "office",
        "changing_room",
        "packaging_material_storage",
    }
    assert cold_area["forbidden_substitute"] == "refrigerated_area_m2"
    assert cold_area["registry_source"].endswith(
        "backend/src/cold_storage/modules/projects/application/operator_process_input.py"
    )

    contract = _text(CONTRACT_PATH)
    for line in (
        "REFRIGERATED_ZONE_COUNT=9",
        "FROZEN_FRUIT_ROOM_INCLUDED=YES",
        "SHIPPING_CHANNEL_INCLUDED=YES",
        "AMBIENT_AREA_INCLUDED_IN_COLD_STORAGE_AREA=NO",
        "REFRIGERATED_AREA_M2_IS_V21_AUTHORITY=NO",
        "frozen_fruit_room=-18℃",
        "shipping_channel=1~3℃",
        "REFRIGERATED_AREA_M2_FORBIDDEN_AS_AUTHORITY",
    ):
        assert line in contract


def test_v21_p0_zone_integrity_and_hostile_cases_are_fail_closed() -> None:
    data = _contract_data()
    integrity = data["zone_integrity"]
    assert set(integrity["required"]) == {
        "ZONE_CODE_UNIQUE",
        "EXPECTED_ZONE_SET_EXACT",
        "REQUIRED_AREA_PRESENT",
        "REQUIRED_AREA_NON_NEGATIVE",
        "REFRIGERATED_ZONE_CODE_TEMPERATURE_BAND_EXACT",
    }
    assert set(integrity["errors"]) == {
        "ZONE_AUTHORITY_SET_MISMATCH",
        "DUPLICATE_ZONE_CODE",
        "MISSING_ZONE_REQUIRED_AREA",
        "INVALID_ZONE_REQUIRED_AREA",
        "REFRIGERATED_ZONE_TEMPERATURE_MISMATCH",
        "FACTORY_AREA_TOTAL_MISMATCH",
        "REFRIGERATED_AREA_M2_FORBIDDEN_AS_AUTHORITY",
    }
    cases = {str(case["id"]): str(case["error"]) for case in data["hostile_cases"]}
    assert cases == {
        "A_AREA_INPUT": "MCP_INPUT_SCHEMA_REJECTED",
        "B_TOTAL_MISMATCH": "FACTORY_AREA_TOTAL_MISMATCH",
        "C_FROZEN_TEMPERATURE": "REFRIGERATED_ZONE_TEMPERATURE_MISMATCH",
        "D_FROZEN_MISSING": "ZONE_AUTHORITY_SET_MISMATCH",
        "E_DUPLICATE_ZONE": "DUPLICATE_ZONE_CODE",
        "F_UNKNOWN_ZONE": "ZONE_AUTHORITY_SET_MISMATCH",
        "G_REFRIGERATED_SUBSTITUTE": "REFRIGERATED_AREA_M2_FORBIDDEN_AS_AUTHORITY",
    }
    contract = _text(CONTRACT_PATH)
    for needle in (
        "total_area_m2=9999",
        "frozen_fruit_room.temperature_band=常温",
        "缺失 `frozen_fruit_room`",
        "重复 `zone_code`",
        "fake_factory_area",
        "以 `refrigerated_area_m2` 替代",
    ):
        assert needle in contract


def test_v21_p0_mcp_is_append_only_and_output_is_shared_presentation() -> None:
    data = _contract_data()
    mcp = data["doubao_mcp"]
    assert mcp["new_tool"] == "preview_factory_power"
    assert mcp["position"] == 6
    assert tuple(mcp["existing_five_tool_order"]) == EXPECTED_TOOL_ORDER
    assert mcp["existing_five_tool_order_changed"] is False
    assert set(mcp["output_fields"]) == {
        "reply_kind",
        "available",
        "calculator_identity",
        "canonical_result_hash",
        "details",
        "summary",
        "unit_semantics",
        "review",
        "provenance",
        "assumptions",
    }

    contract = _text(CONTRACT_PATH)
    for line in (
        "NEW_MCP_TOOL=preview_factory_power",
        "NEW_MCP_TOOL_POSITION=6",
        "EXISTING_FIVE_TOOL_ORDER_CHANGED=NO",
        "preview_installed_power",
        "reply_kind=factory_power_estimation_table",
        "canonical_result_hash=sha256:<64 hex>",
        "project_factory_power_table()",
        "requires_review=true",
        "UNIT=kW",
        "estimated_total_power_kw",
    ):
        assert line in contract

    mcp_source = _text(REPO_ROOT / "backend/src/cold_storage/modules/aily/api/mcp_sse.py")
    order_start = mcp_source.index("_PREVIEW_TOOL_ORDER")
    order_text = mcp_source[order_start : mcp_source.index(")", order_start) + 1]
    expected_constant_order = (
        "PREVIEW_ZONE_PLAN_TOOL_NAME",
        "PREVIEW_COOLING_LOAD_TOOL_NAME",
        "PREVIEW_EQUIPMENT_TOOL_NAME",
        "PREVIEW_INSTALLED_POWER_TOOL_NAME",
        "PREVIEW_INVESTMENT_TOOL_NAME",
        "PREVIEW_FACTORY_POWER_TOOL_NAME",
    )
    assert tuple(re.findall(r"PREVIEW_[A-Z_]+_TOOL_NAME", order_text)) == expected_constant_order
    assert mcp_source.count("PREVIEW_FACTORY_POWER_TOOL_NAME") >= 2


def test_v21_p0_preserves_v20_calculator_presentation_and_v18_mcp() -> None:
    for path in V20_RUNTIME_PATHS:
        assert _git_diff_is_empty(path), f"V2.1 P0 changed runtime path: {path}"
    for path in V18_FROZEN_PATHS:
        assert _git_diff_is_empty(path), f"V2.1 P0 changed frozen V1.8 path: {path}"

    assert len(CalculationType) == 5
    contract = _text(CONTRACT_PATH)
    for line in (
        "CALCULATOR_IDENTITY=factory_power_estimation@2.0.0-p1",
        "MAIN_SYSTEM_COP=3.3",
        "POOL_A=DEFROST",
        "POOL_B=OTHER",
        "POOL_C=PRODUCTION",
        "V20_P1_CALCULATOR_UNCHANGED=YES",
        "V20_P2_PRESENTATION_UNCHANGED=YES",
        "FACTORY_POWER_FORMULA_RECUT=NO",
        "INSTALLED_POWER_REPLACED=NO",
        "POWER_CONFIGURATION_REPLACED=NO",
        "FIVE_STAGE_CALCULATION_TYPE_CHANGED=NO",
        "DOUBAO_CARRIES_ENGINEERING_AREA=NO",
        "DOUBAO_CARRIES_ZONE_RESULT_AS_AUTHORITY=NO",
        "BACKEND_STATELESS_ZONE_PLAN_REPLAY_ALLOWED=YES",
    ):
        assert line in contract


def test_v21_p0_global_governance_points_to_the_new_active_lane() -> None:
    global_texts = tuple(
        _text(path)
        for path in (
            CURRENT_STATE_PATH,
            GAP_ANALYSIS_PATH,
            DEVELOPMENT_PLAN_PATH,
            TECH_DEBT_PATH,
        )
    )
    for text in global_texts:
        assert "v2.0.0" in text
        assert "V2.1" in text
        assert "V21_P0_FACTORY_POWER_UPSTREAM_AUTHORITY_AND_DOUBAO_MCP_CONTRACT_R1" in text
        assert "ACTIVE_GOVERNANCE_LANE=V2.1_P0" in text
        assert "NEXT_FEATURE_LANE_AUTHORIZED=NO" in text
        assert "NO_STEP_IMPLIES_THE_NEXT=TRUE" in text

    v20_version_plan = _text(V20_VERSION_PLAN_PATH)
    v20_closure = _text(V20_CLOSURE_PATH)
    adr042 = _text(ADR042_PATH)
    assert "v2.0.0" in v20_version_plan
    assert "已发布" in v20_version_plan
    assert "V2.0 release execution completed" in v20_closure
    assert "v2.0.0 已发布" in adr042
    assert "P2_AUTHORIZED=NO" in v20_version_plan
    assert "READY_AUTHORIZED=NO" in v20_version_plan
    assert "MERGE_AUTHORIZED=NO" in v20_version_plan


def test_v21_p0_product_semantics_and_next_gates_are_locked() -> None:
    contract = _text(CONTRACT_PATH)
    for line in (
        "概念设计阶段估算工厂电功率",
        "单位为 `kW`",
        "kWh",
        "变压器选型",
        "正式配电设计",
        "施工图",
        "短路计算",
        "电缆选型",
        "保护整定",
        "requires_review=true",
        "P1_EXECUTED=NO",
        "P2_EXECUTED=NO",
        "RUNTIME_TEST_CHANGE_REQUIRED=NO",
    ):
        assert line in contract
