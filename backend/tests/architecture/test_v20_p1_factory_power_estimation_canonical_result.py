"""Architecture locks for the V2.0 P1 factory-power implementation.

The P0 Markdown JSON remains the rule authority.  This test compares that
matrix with the additive runtime registry and also keeps the P1 change scope
away from legacy calculators, consumers, and persistence.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from dataclasses import fields
from decimal import Decimal
from pathlib import Path

from cold_storage.modules.calculations.domain.factory_power_estimation import (
    CALCULATOR_IDENTITY,
    CALCULATOR_VERSION,
    DEDICATED_COMPRESSOR_POWER_BY_ZONE,
    DEDICATED_SYSTEM_ZONE_CODES,
    EVAPORATIVE_CONDENSER_POWER_BY_BAND,
    FACTORY_AREA_BANDS,
    LIGHTING_RULES,
    MAIN_SYSTEM_COP,
    MAIN_SYSTEM_ZONE_CODES,
    POOL_A_SIMULTANEITY_FACTOR,
    POOL_B_SIMULTANEITY_FACTOR_BY_BAND,
    POOL_C_SIMULTANEITY_FACTOR,
    PRECOOLING_CONFIGURATIONS,
    PRODUCTION_POWER_BY_BAND,
    PUBLIC_EQUIPMENT_RULES,
    ZONE_AIR_COOLER_RULES,
    FactoryPowerDetail,
    FactoryPowerEstimationResult,
    FactoryPowerSummary,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType

REPO_ROOT = Path(__file__).resolve().parents[3]
P0_CONTRACT_PATH = (
    REPO_ROOT / "docs" / "tasks" / "V2_0-P0-factory-power-estimation-and-presentation-contract.md"
)
P1_TASK_PATH = (
    REPO_ROOT
    / "docs"
    / "tasks"
    / "V2_0-P1-factory-power-estimation-canonical-result-implementation.md"
)
VERSION_PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V2_0-version-plan.md"
ADR_PATH = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "ADR-042-factory-power-estimation-and-presentation-contract.md"
)
RUNTIME_PATH = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "calculations"
    / "domain"
    / "factory_power_estimation.py"
)

EXPECTED_CHANGED_PATHS = {
    "backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py",
    "backend/tests/architecture/test_v20_p0_factory_power_estimation_and_presentation_contract.py",
    "backend/tests/architecture/test_v20_p1_factory_power_estimation_canonical_result.py",
    "backend/tests/unit/test_v20_p1_factory_power_estimation.py",
    "docs/architecture/ADR-042-factory-power-estimation-and-presentation-contract.md",
    "docs/tasks/V2_0-P1-factory-power-estimation-canonical-result-implementation.md",
    "docs/tasks/V2_0-version-plan.md",
}
P2_DOWNSTREAM_PATHS = {
    "backend/src/cold_storage/modules/projects/application/factory_power_upstream_authority.py",
    "backend/tests/architecture/test_v20_release_closure_readiness.py",
    "backend/src/cold_storage/modules/aily/application/factory_power_table.py",
    "backend/src/cold_storage/modules/calculations/application/factory_power_presentation.py",
    "backend/src/cold_storage/modules/projects/application/factory_power_presentation.py",
    "backend/src/cold_storage/modules/projects/application/service.py",
    "backend/src/cold_storage/modules/projects/infrastructure/database.py",
    "backend/tests/architecture/test_v20_p0_factory_power_estimation_and_presentation_contract.py",
    "backend/tests/architecture/test_v20_p1_factory_power_estimation_canonical_result.py",
    "backend/tests/architecture/test_v20_p2_factory_power_read_only_presentation.py",
    "backend/tests/golden/v20_factory_power_canonical_result_v1.json",
    "backend/tests/unit/test_v20_p2_factory_power_read_only_presentation.py",
    "docs/tasks/V2_0-P2-factory-power-read-only-presentation-alignment.md",
    "docs/tasks/V2_0-release-closure-readiness.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/TECH_DEBT.md",
    "frontend/src/api/contracts/calculations.ts",
    "frontend/src/api/contracts/factoryPower.ts",
    "frontend/src/features/calculations/components/CalculationsPage.vue",
    "frontend/src/features/calculations/components/FactoryPowerEstimationResults.test.ts",
    "frontend/src/features/calculations/components/FactoryPowerEstimationResults.vue",
    "frontend/src/features/calculations/architecture/test_v20_p2_factory_power_read_only_presentation.test.ts",
    "frontend/src/features/calculations/model/mapFactoryPowerPresentation.test.ts",
    "frontend/src/features/calculations/model/mapFactoryPowerPresentation.ts",
    "backend/tests/architecture/test_v21_p0_factory_power_upstream_authority_doubao_mcp_contract.py",
    "backend/tests/architecture/test_v21_p1_factory_power_upstream_authority.py",
    "backend/tests/unit/test_v21_p1_factory_power_upstream_authority.py",
    "docs/tasks/V2_1-version-plan.md",
    "docs/tasks/V2_1-P0-factory-power-upstream-authority-doubao-mcp-contract.md",
    "docs/tasks/V2_1-P1-factory-power-upstream-authority-adapter-implementation.md",
    "docs/architecture/ADR-043-factory-power-upstream-authority-doubao-mcp.md",
    "backend/src/cold_storage/modules/aily/api/mcp_sse.py",
    "backend/src/cold_storage/modules/aily/application/stage_preview.py",
    "backend/src/cold_storage/modules/aily/application/factory_power_preview.py",
    "backend/src/cold_storage/modules/aily/application/mcp_factory_power.py",
    "backend/tests/unit/test_v21_p2_aily_factory_power_preview.py",
    "backend/tests/unit/test_v21_p2_aily_factory_power_mcp.py",
    "backend/tests/integration/test_v21_p2_aily_factory_power_mcp_http.py",
    "backend/tests/architecture/test_v21_p2_factory_power_mcp_doubao_integration.py",
    "backend/tests/unit/test_v11_aily_mcp_protocol.py",
    "backend/tests/unit/test_v12_aily_mcp_protocol.py",
    "backend/tests/integration/test_v11_aily_mcp_sse_http.py",
    "backend/tests/architecture/test_v12_p0_aily_five_stage_preview_contract.py",
    "backend/tests/architecture/test_v13_p0_aily_preview_lineage_contract.py",
    "backend/tests/architecture/test_v14_p0_workbench_debt_contract.py",
    "backend/tests/architecture/test_v15_p0_envelope_geometry_contract.py",
    "backend/tests/architecture/test_v16_p0_power_fan_catalog_contract.py",
    "backend/tests/architecture/test_v17_p0_zone_cooling_surface_contract.py",
    "backend/tests/architecture/test_v18_p0_zone_temperature_height_contract.py",
    "backend/tests/unit/test_v13_aily_preview_lineage.py",
    "backend/tests/unit/test_v15_aily_envelope_geometry.py",
    "backend/tests/unit/test_v16_power_fan_catalog.py",
    "backend/tests/unit/test_v17_zone_cooling_surface.py",
    "backend/tests/unit/test_v18_zone_temperature_height.py",
    "docs/tasks/V2_1-P2-factory-power-mcp-doubao-skill-integration.md",
    "docs/contracts/aily/v2.1/doubao-skill.v1.md",
    "docs/contracts/aily/v2.1/doubao-skill.v1.json",
    "docs/runbooks/v21-doubao-aily-connector.md",
}
GENERATED_ARTIFACT_PREFIX = "backend/artifacts/local/"


def _p0_contract_data() -> dict[str, object]:
    text = P0_CONTRACT_PATH.read_text(encoding="utf-8")
    match = re.search(r"~~~json\n(.*?)\n~~~", text, flags=re.DOTALL)
    assert match is not None, "P0 contract must contain its machine-readable JSON matrix"
    data = json.loads(match.group(1))
    assert isinstance(data, dict)
    return data


def _changed_paths() -> set[str]:
    merge_base = subprocess.run(
        ["git", "merge-base", "origin/main", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert merge_base
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
        path.strip()
        for path in [*tracked, *untracked]
        if path.strip() and not path.strip().startswith(GENERATED_ARTIFACT_PREFIX)
    }


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _area_denominator_from_formula(formula: object) -> Decimal | None:
    if not isinstance(formula, str):
        return None
    match = re.fullmatch(
        r"ceil\((?:required_area_m2|cold_storage_area_m2) / ([0-9]+(?:\.[0-9]+)?)\)",
        formula,
    )
    return None if match is None else _decimal(match.group(1))


def test_v20_p1_scope_is_additive_and_does_not_touch_consumers_or_schema() -> None:
    changed = _changed_paths()
    assert changed <= EXPECTED_CHANGED_PATHS | P2_DOWNSTREAM_PATHS
    assert {path for path in changed if path.startswith("frontend/")} <= P2_DOWNSTREAM_PATHS
    assert not any(path.startswith("backend/alembic/") for path in changed)
    assert not any(
        path.startswith("backend/src/cold_storage/modules/aily/")
        and path not in P2_DOWNSTREAM_PATHS
        for path in changed
    )
    runtime_paths = {path for path in changed if path.startswith("backend/src/")}
    assert runtime_paths <= P2_DOWNSTREAM_PATHS
    assert (
        "backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py"
        not in changed
    )


def test_p1_authorization_is_separate_and_p0_history_is_preserved() -> None:
    p0_data = _p0_contract_data()
    assert p0_data["status"] == "P0_CONTRACT_FROZEN"
    authorization = p0_data["authorization"]
    assert authorization["P1_AUTHORIZED"] == "NO"
    assert authorization["RUNTIME_CODE_CHANGE"] == "NO"

    p1_text = P1_TASK_PATH.read_text(encoding="utf-8")
    version_plan_text = VERSION_PLAN_PATH.read_text(encoding="utf-8")
    assert "P0_CONTRACT_FROZEN=YES" in p1_text
    assert "P1_IMPLEMENTATION_SEPARATELY_AUTHORIZED=YES" in p1_text
    assert "V20_P1_IMPLEMENTATION_AUTHORIZED=YES" in p1_text
    assert "V20_P1_IMPLEMENTATION_EXECUTED=YES" in p1_text
    assert "P1_IMPLEMENTATION_SEPARATELY_AUTHORIZED=YES" in version_plan_text
    assert "V20_P1_IMPLEMENTATION_AUTHORIZED=YES" in version_plan_text
    assert "V20_P1_IMPLEMENTATION_EXECUTED=YES" in version_plan_text
    assert "P1_AUTHORIZED=YES" not in p1_text
    assert "NO_OUTBOUND_LIVE_AILY_SESSION=NO" not in p1_text

    for path in (VERSION_PLAN_PATH, ADR_PATH):
        text = path.read_text(encoding="utf-8")
        assert "P1_AUTHORIZED=NO" in text
        assert "NO_STEP_IMPLIES_THE_NEXT=TRUE" in text
        assert "OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED=YES" not in text


def test_v20_p0_rule_matrix_matches_v20_p1_runtime_registry() -> None:
    data = _p0_contract_data()

    expected_bands = [
        (item["code"], item["lower_bound_exclusive_m2"], item["upper_bound_inclusive_m2"])
        for item in data["factory_area_bands"]
    ]
    actual_bands = [
        (band.code, band.lower_bound_exclusive_m2, band.upper_bound_inclusive_m2)
        for band in FACTORY_AREA_BANDS
    ]
    assert actual_bands == [
        (
            code,
            None if lower is None else _decimal(lower),
            None if upper is None else _decimal(upper),
        )
        for code, lower, upper in expected_bands
    ]

    expected_precooling = data["precooling_configurations"]
    for scheme_id in ("6_position", "8_position"):
        expected = expected_precooling[scheme_id]
        actual = PRECOOLING_CONFIGURATIONS[scheme_id]
        assert actual.positions_per_room == expected["positions_per_room"]
        assert actual.air_coolers_per_room == expected["air_coolers_per_room"]
        assert actual.positions_per_air_cooler == expected["positions_per_air_cooler"]
    assert expected_precooling["position_source_field"] == "position_count"
    assert expected_precooling["room_count_source_field"] == "schemes[].room_count"
    assert expected_precooling["forbidden_position_source_field"] == "raw_position_count"

    expected_zone_rules = {item["zone_code"]: item for item in data["zone_rules"]}
    assert set(ZONE_AIR_COOLER_RULES) == set(expected_zone_rules)
    assert len(ZONE_AIR_COOLER_RULES) == 9
    for zone_code, expected in expected_zone_rules.items():
        actual = ZONE_AIR_COOLER_RULES[zone_code]
        assert actual.quantity_basis == expected["quantity_basis"]
        assert actual.quantity_formula == expected["quantity_formula"]
        assert actual.motor_kw_per_unit == _decimal(expected["motor_kw_per_unit"])
        assert actual.defrost_kw_per_unit == _decimal(expected["defrost_kw_per_unit"])
        assert actual.motor_pool == expected["motor_pool"]
        assert actual.defrost_pool == expected["defrost_pool"]
        assert actual.source_field == expected.get("source_field")
        assert actual.raw_count_formula == expected.get("raw_count_formula")
        assert actual.fixed_quantity == expected.get("quantity")
        expected_area_formula = expected.get("raw_count_formula") or expected.get(
            "quantity_formula"
        )
        expected_denominator = (
            _area_denominator_from_formula(expected_area_formula)
            if expected["quantity_basis"] == "ZONE_AREA"
            else None
        )
        assert actual.area_denominator_m2 == expected_denominator
        assert actual.axial_fans_per_position == expected.get("axial_fans_per_position")
        axial_power = expected.get("axial_fan_kw_per_unit")
        assert actual.axial_fan_kw_per_unit == (
            None if axial_power is None else _decimal(axial_power)
        )
        assert actual.axial_fan_quantity_formula == expected.get("axial_fan_quantity_formula")

    expected_public = {item["equipment_code"]: item for item in data["public_equipment"]}
    assert set(PUBLIC_EQUIPMENT_RULES) == set(expected_public)
    for equipment_code, expected in expected_public.items():
        actual = PUBLIC_EQUIPMENT_RULES[equipment_code]
        expected_quantities = expected.get("quantity_by_band")
        assert dict(actual.quantity_by_band or {}) == (expected_quantities or {})
        expected_unit_power = expected.get("unit_power_kw")
        assert actual.unit_power_kw == (
            None if expected_unit_power is None else _decimal(expected_unit_power)
        )
        assert actual.pool == expected["pool"]
        assert actual.fixed_quantity == expected.get("fixed_quantity")
        expected_fixed_power = expected.get("fixed_installed_power_kw")
        assert actual.fixed_installed_power_kw == (
            None if expected_fixed_power is None else _decimal(expected_fixed_power)
        )

    lighting = data["lighting"]
    expected_lighting = {
        "cold_storage_lighting": lighting["cold_storage_lighting"],
        "uv_lighting": lighting["uv_lighting"],
    }
    assert set(LIGHTING_RULES) == set(expected_lighting)
    for lighting_code, expected in expected_lighting.items():
        actual = LIGHTING_RULES[lighting_code]
        assert actual.area_source_field == lighting["area_source_field"]
        assert actual.area_divisor_m2 == _area_denominator_from_formula(
            expected["quantity_formula"]
        )
        assert actual.unit_power_kw == _decimal(expected["unit_power_kw"])
        assert actual.pool == expected["pool"]
        assert actual.quantity_formula == expected["quantity_formula"]
        assert actual.installed_power_formula == expected["installed_power_formula"]
        assert actual.forbidden_area_substitute == lighting["forbidden_area_substitute"]


def test_v20_p0_system_boundaries_and_power_pools_match_runtime_registry() -> None:
    data = _p0_contract_data()
    compressors = data["compressor_systems"]
    main = compressors["main_system"]
    assert tuple(main["included_zone_codes"]) == MAIN_SYSTEM_ZONE_CODES
    assert tuple(main["excluded_zone_codes"]) == DEDICATED_SYSTEM_ZONE_CODES
    assert _decimal(main["main_system_cop"]) == MAIN_SYSTEM_COP

    expected_dedicated = {
        item["zone_code"]: {
            band: _decimal(power) for band, power in item["shaft_power_by_band_kw"].items()
        }
        for item in compressors["dedicated_systems"]
    }
    assert {
        zone_code: dict(values) for zone_code, values in DEDICATED_COMPRESSOR_POWER_BY_ZONE.items()
    } == expected_dedicated
    assert all(item["pool"] == "POOL_B" for item in compressors["dedicated_systems"])

    expected_condenser = data["evaporative_condenser"]
    assert dict(EVAPORATIVE_CONDENSER_POWER_BY_BAND) == {
        band: _decimal(power)
        for band, power in expected_condenser["installed_power_by_band_kw"].items()
    }
    assert expected_condenser["pool"] == "POOL_B"

    expected_production = data["production"]
    assert dict(PRODUCTION_POWER_BY_BAND) == {
        band: _decimal(power)
        for band, power in expected_production["installed_power_by_band_kw"].items()
    }
    assert _decimal(expected_production["simultaneity_factor"]) == POOL_C_SIMULTANEITY_FACTOR
    assert expected_production["pool"] == "POOL_C"

    pools = data["power_pools"]
    assert _decimal(pools["POOL_A"]["simultaneity_factor"]) == POOL_A_SIMULTANEITY_FACTOR
    assert {
        band: _decimal(factor)
        for band, factor in pools["POOL_B"]["simultaneity_factor_by_band"].items()
    } == dict(POOL_B_SIMULTANEITY_FACTOR_BY_BAND)
    assert _decimal(pools["POOL_C"]["simultaneity_factor"]) == POOL_C_SIMULTANEITY_FACTOR


def test_canonical_result_fields_and_five_stage_boundary_are_locked() -> None:
    assert CALCULATOR_IDENTITY == "factory_power_estimation@2.0.0-p1"
    assert CALCULATOR_VERSION == "2.0.0-p1"
    assert CALCULATOR_IDENTITY != "installed_power@1.0.0"
    assert [member.value for member in CalculationType] == [
        "zone",
        "cooling_load",
        "equipment",
        "power",
        "investment",
    ]
    assert [field.name for field in fields(FactoryPowerDetail)] == [
        "equipment_or_zone",
        "basis",
        "configured_quantity",
        "unit_power_kw",
        "installed_power_kw",
        "pool",
        "simultaneity_factor",
        "coincident_power_kw",
    ]
    assert [field.name for field in fields(FactoryPowerSummary)] == [
        "defrost_installed_power_kw",
        "defrost_coincident_power_kw",
        "other_installed_power_kw",
        "other_coincident_power_kw",
        "production_equipment_installed_power_kw",
        "production_equipment_coincident_power_kw",
        "total_installed_power_kw",
        "estimated_total_power_kw",
    ]
    result_fields = {field.name for field in fields(FactoryPowerEstimationResult)}
    assert result_fields == {
        "factory_area_band",
        "input_snapshot",
        "provenance",
        "assumptions",
        "details",
        "summary",
    }


def test_v20_runtime_has_no_legacy_authority_or_external_side_effect_boundary() -> None:
    source = RUNTIME_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "reference_power_rows",
        "daily_inbound_mass_kg",
        "total_area_m2",
        "total_required_area_m2",
        "refrigerated_area_m2",
        "raw_position_count",
        "subtotal_load_kw_r",
        "installed_power@1.0.0",
    ):
        assert forbidden not in source

    tree = ast.parse(source)
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.append(node.module)
    forbidden_modules = ("fastapi", "sqlalchemy", "redis", "requests", "httpx", "aiohttp")
    assert not any(
        module == forbidden or module.startswith(f"{forbidden}.")
        for module in imported_modules
        for forbidden in forbidden_modules
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"open", "urlopen"}
        for node in ast.walk(tree)
    )
