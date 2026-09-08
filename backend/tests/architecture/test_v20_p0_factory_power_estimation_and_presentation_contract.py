"""Architecture locks for the V2.0 P0 factory-power contract.

This test intentionally validates the Markdown contract and the audited
current boundaries.  It does not import or execute a future V2.0 calculator.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = (
    REPO_ROOT / "docs" / "tasks" / "V2_0-P0-factory-power-estimation-and-presentation-contract.md"
)
VERSION_PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V2_0-version-plan.md"
ADR_PATH = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "ADR-042-factory-power-estimation-and-presentation-contract.md"
)
ZONE_PLAN_PATH = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "calculations"
    / "domain"
    / "zone_planning.py"
)
PER_ZONE_PATH = ZONE_PLAN_PATH.with_name("per_zone_cooling_estimation.py")
POWER_PATH = ZONE_PLAN_PATH.with_name("power.py")
EQUIPMENT_PATH = ZONE_PLAN_PATH.with_name("equipment.py")
PLANNING_SERVICE_PATH = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "planning"
    / "application"
    / "service.py"
)
SOURCE_SNAPSHOT_PATH = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "orchestration"
    / "application"
    / "source_snapshots.py"
)
PREVIEW_LINEAGE_PATH = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "projects"
    / "application"
    / "preview_lineage_bind.py"
)

EXPECTED_CHANGED_PATHS = {
    "backend/tests/architecture/test_v20_p0_factory_power_estimation_and_presentation_contract.py",
    "backend/tests/architecture/test_v19_p0_per_zone_cooling_estimation_basis_contract.py",
    "backend/tests/architecture/test_v19_p1_per_zone_cooling_estimation_implementation.py",
    "backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py",
    "backend/tests/architecture/test_v20_p1_factory_power_estimation_canonical_result.py",
    "backend/tests/unit/test_v20_p1_factory_power_estimation.py",
    "docs/architecture/ADR-042-factory-power-estimation-and-presentation-contract.md",
    "docs/tasks/V2_0-P0-factory-power-estimation-and-presentation-contract.md",
    "docs/tasks/V2_0-P1-factory-power-estimation-canonical-result-implementation.md",
    "docs/tasks/V2_0-version-plan.md",
}
GENERATED_ARTIFACT_PREFIX = "backend/artifacts/local/"
OUTBOUND_AILY_AUTHORIZATION_LOCK = "OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED=NO"
HOSTILE_OUTBOUND_AILY_AUTHORIZATION_LOCK = "NO_OUTBOUND_LIVE_AILY_SESSION" + "=NO"

EXPECTED_ZONE_RULES = {
    "primary_precooling_room": {
        "quantity_basis": "PRECOOLING_SCHEME",
        "quantity_formula": "room_count * 2",
        "motor_kw_per_unit": 6.6,
        "defrost_kw_per_unit": 19.6,
        "motor_pool": "POOL_B",
        "defrost_pool": "POOL_A",
    },
    "secondary_precooling_room": {
        "quantity_basis": "PRECOOLING_SCHEME",
        "quantity_formula": "room_count * 2",
        "motor_kw_per_unit": 3.0,
        "defrost_kw_per_unit": 22.0,
        "motor_pool": "POOL_B",
        "defrost_pool": "POOL_A",
    },
    "raw_fruit_buffer": {
        "quantity_basis": "ZONE_AREA",
        "source_field": "required_area_m2",
        "quantity_formula": "ceil(required_area_m2 / 80)",
        "motor_kw_per_unit": 0.5,
        "defrost_kw_per_unit": 4.0,
        "motor_pool": "POOL_B",
        "defrost_pool": "POOL_A",
    },
    "sorting_packaging_room": {
        "quantity_basis": "ZONE_AREA",
        "source_field": "required_area_m2",
        "raw_count_formula": "ceil(required_area_m2 / 70)",
        "quantity_formula": "next_even_integer_greater_than_or_equal_to(raw_count)",
        "motor_kw_per_unit": 0.5,
        "defrost_kw_per_unit": 4.0,
        "motor_pool": "POOL_B",
        "defrost_pool": "POOL_A",
    },
    "coating_room": {
        "quantity_basis": "ZONE_AREA",
        "source_field": "required_area_m2",
        "quantity_formula": "ceil(required_area_m2 / 70)",
        "motor_kw_per_unit": 1.5,
        "defrost_kw_per_unit": 6.0,
        "motor_pool": "POOL_B",
        "defrost_pool": "POOL_A",
    },
    "finished_goods_room": {
        "quantity_basis": "ZONE_AREA",
        "source_field": "required_area_m2",
        "quantity_formula": "ceil(required_area_m2 / 70)",
        "motor_kw_per_unit": 1.5,
        "defrost_kw_per_unit": 6.0,
        "motor_pool": "POOL_B",
        "defrost_pool": "POOL_A",
    },
    "secondary_fruit_buffer": {
        "quantity_basis": "FIXED",
        "quantity": 1,
        "quantity_formula": "1",
        "motor_kw_per_unit": 1.0,
        "defrost_kw_per_unit": 8.0,
        "motor_pool": "POOL_B",
        "defrost_pool": "POOL_A",
    },
    "frozen_fruit_room": {
        "quantity_basis": "FIXED",
        "quantity": 1,
        "quantity_formula": "1",
        "motor_kw_per_unit": 3.0,
        "defrost_kw_per_unit": 26.0,
        "motor_pool": "POOL_B",
        "defrost_pool": "POOL_A",
    },
    "shipping_channel": {
        "quantity_basis": "ZONE_AREA",
        "source_field": "required_area_m2",
        "quantity_formula": "ceil(required_area_m2 / 50)",
        "motor_kw_per_unit": 2.0,
        "defrost_kw_per_unit": 12.0,
        "motor_pool": "POOL_B",
        "defrost_pool": "POOL_A",
    },
}


def _contract_text() -> str:
    return CONTRACT_PATH.read_text(encoding="utf-8")


def _contract_data() -> dict[str, object]:
    match = re.search(r"~~~json\n(.*?)\n~~~", _contract_text(), flags=re.DOTALL)
    assert match is not None, "P0 contract must contain one canonical JSON matrix"
    parsed = json.loads(match.group(1))
    assert isinstance(parsed, dict)
    return parsed


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


def test_v20_p0_documents_are_present_and_docs_only() -> None:
    assert CONTRACT_PATH.is_file()
    assert VERSION_PLAN_PATH.is_file()
    assert ADR_PATH.is_file()
    changed = _changed_paths()
    assert changed <= EXPECTED_CHANGED_PATHS
    assert {path for path in changed if path.startswith("backend/src/")} <= {
        "backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py"
    }
    assert not any(path.startswith("frontend/") for path in changed)
    assert not any(path.startswith("backend/alembic/") for path in changed)


def test_v20_p0_document_authorization_locks_are_consistent() -> None:
    data = _contract_data()
    assert data["task_id"] == "V20_P0_FACTORY_POWER_ESTIMATION_AND_PRESENTATION_CONTRACT_R1"
    assert data["status"] == "P0_CONTRACT_FROZEN"
    assert data["direction"] == "FACTORY_POWER_ESTIMATION_AND_PRESENTATION_CONTRACT"

    expected_authorization = {
        "MODE": "DOCS_CONTRACT_ARCHITECTURE_TEST_ONLY",
        "RUNTIME_CODE_CHANGE": "NO",
        "FRONTEND_CODE_CHANGE": "NO",
        "AILY_RUNTIME_CHANGE": "NO",
        "OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED": "NO",
        "DATABASE_MIGRATION": "NO",
        "EQUIPMENT_MODEL_SELECTION": "NO",
        "TRANSFORMER_SIZING": "NO",
        "KWH_ESTIMATION": "NO",
        "ELECTRICITY_PRICE": "NO",
        "MONTHLY_BILL": "NO",
        "READY_AUTHORIZED": "NO",
        "MERGE_AUTHORIZED": "NO",
        "P1_AUTHORIZED": "NO",
        "P2_AUTHORIZED": "NO",
        "NO_STEP_IMPLIES_THE_NEXT": "TRUE",
    }
    assert data["authorization"] == expected_authorization
    for path in (VERSION_PLAN_PATH, ADR_PATH):
        text = path.read_text(encoding="utf-8")
        assert "RUNTIME_IMPLEMENTATION_AUTHORIZED=NO" in text
        assert "FRONTEND_IMPLEMENTATION_AUTHORIZED=NO" in text
        assert "AILY_IMPLEMENTATION_AUTHORIZED=NO" in text
        assert "NO_STEP_IMPLIES_THE_NEXT=TRUE" in text


def test_factory_area_bands_have_the_lower_band_inclusive_boundaries() -> None:
    data = _contract_data()
    assert data["factory_area_bands"] == [
        {
            "code": "SMALL",
            "predicate": "factory_area_m2 <= 2500",
            "lower_bound_exclusive_m2": None,
            "upper_bound_inclusive_m2": 2500,
        },
        {
            "code": "MEDIUM",
            "predicate": "2500 < factory_area_m2 <= 5000",
            "lower_bound_exclusive_m2": 2500,
            "upper_bound_inclusive_m2": 5000,
        },
        {
            "code": "LARGE",
            "predicate": "factory_area_m2 > 5000",
            "lower_bound_exclusive_m2": 5000,
            "upper_bound_inclusive_m2": None,
        },
    ]
    audit = data["authority_audit"]
    assert audit["factory_area"]["current_literal_field"] is None
    assert audit["factory_area"]["status"] == "UNRESOLVED"
    assert audit["factory_area"]["required_behavior"] == (
        "fail_closed_until_authoritative_factory_area_is_mapped"
    )
    assert "total_area_m2" in audit["factory_area"]["forbidden_substitutes"]
    assert "refrigerated_area_m2" in audit["factory_area"]["forbidden_substitutes"]


def test_current_area_and_precooling_authority_audit_is_explicit() -> None:
    data = _contract_data()
    audit = data["authority_audit"]
    assert audit["zone_area"] == {
        "canonical_field": "required_area_m2",
        "semantic": "PLANNED_ZONE_AREA",
        "source_path": "zone_plan.result.zones[]",
        "status": "PRESENT",
    }
    cold_storage_area = audit["cold_storage_area"]
    assert cold_storage_area["target_field"] == "cold_storage_area_m2"
    assert cold_storage_area["current_literal_field"] is None
    assert cold_storage_area["current_equivalent_field"] == "refrigerated_area_m2"
    assert cold_storage_area["mapping_status"] == "AMBIGUOUS_EXISTING_DERIVATIONS"
    assert cold_storage_area["forbidden_substitute"] == "total_area_m2"
    assert "planning_application" in cold_storage_area["candidate_derivations"]
    assert "operator_minimal_lineage" in cold_storage_area["candidate_derivations"]
    assert "-18℃" in cold_storage_area["candidate_derivations"]["planning_application"]
    assert "excludes -18℃" in cold_storage_area["candidate_derivations"]["operator_minimal_lineage"]
    assert cold_storage_area["required_resolution"] == (
        "freeze whether cold_storage_area_m2 includes -18℃ and publish one canonical derivation"
    )

    precooling = audit["precooling_output"]
    assert precooling["current_reporting_scheme"] == "6_position"
    assert precooling["alternate_scheme"] == "8_position"
    assert precooling["forbidden_source_field"] == "raw_position_count"
    assert set(precooling["required_fields"]) == {
        "reporting_scheme_id",
        "schemes[].room_count",
        "schemes[].position_count",
        "schemes[].required_area_m2",
        "position_count",
    }

    configurations = data["precooling_configurations"]
    assert configurations["6_position"] == {
        "positions_per_room": 6,
        "air_coolers_per_room": 2,
        "positions_per_air_cooler": 3,
        "air_cooler_quantity_formula": "room_count * 2",
    }
    assert configurations["8_position"] == {
        "positions_per_room": 8,
        "air_coolers_per_room": 2,
        "positions_per_air_cooler": 4,
        "air_cooler_quantity_formula": "room_count * 2",
    }
    assert configurations["position_source_field"] == "position_count"
    assert configurations["forbidden_position_source_field"] == "raw_position_count"


def test_nine_zone_air_cooler_rules_are_frozen_exactly() -> None:
    rules = _contract_data()["zone_rules"]
    assert isinstance(rules, list)
    by_zone = {rule["zone_code"]: rule for rule in rules}
    assert set(by_zone) == set(EXPECTED_ZONE_RULES)
    assert len(by_zone) == 9
    for zone_code, expected in EXPECTED_ZONE_RULES.items():
        rule = by_zone[zone_code]
        for key, value in expected.items():
            assert rule[key] == value

    for zone_code in ("primary_precooling_room", "secondary_precooling_room"):
        rule = by_zone[zone_code]
        assert rule["axial_fans_per_position"] == 4
        assert rule["axial_fan_kw_per_unit"] == 0.5
        assert rule["axial_fan_quantity_formula"] == "final_position_count * 4"

    area_rules = {
        "raw_fruit_buffer": 80,
        "coating_room": 70,
        "finished_goods_room": 70,
        "shipping_channel": 50,
    }
    for zone_code, denominator in area_rules.items():
        assert by_zone[zone_code]["quantity_formula"] == (f"ceil(required_area_m2 / {denominator})")

    sorting = by_zone["sorting_packaging_room"]
    assert sorting["raw_count_formula"] == "ceil(required_area_m2 / 70)"
    assert sorting["quantity_formula"] == ("next_even_integer_greater_than_or_equal_to(raw_count)")


def test_public_equipment_and_lighting_rules_are_frozen() -> None:
    contract_text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "冷库电动平移门" in contract_text
    assert "电动" + "滑升门" not in contract_text

    public = _contract_data()["public_equipment"]
    assert isinstance(public, list)
    by_code = {item["equipment_code"]: item for item in public}
    assert set(by_code) == {
        "electric_sliding_door",
        "fast_rolling_door",
        "air_curtain",
        "lift_door_and_loading_platform",
        "ozone_and_humidification",
        "floor_heating_cable",
    }
    assert by_code["electric_sliding_door"]["quantity_by_band"] == {
        "SMALL": 15,
        "MEDIUM": 30,
        "LARGE": 50,
    }
    assert by_code["electric_sliding_door"]["unit_power_kw"] == 0.5
    assert by_code["fast_rolling_door"]["quantity_by_band"] == {
        "SMALL": 6,
        "MEDIUM": 10,
        "LARGE": 16,
    }
    assert by_code["fast_rolling_door"]["unit_power_kw"] == 0.5
    assert by_code["air_curtain"]["quantity_by_band"] == {
        "SMALL": 4,
        "MEDIUM": 8,
        "LARGE": 12,
    }
    assert by_code["air_curtain"]["unit_power_kw"] == 0.4
    assert by_code["lift_door_and_loading_platform"]["quantity_by_band"] == {
        "SMALL": 2,
        "MEDIUM": 3,
        "LARGE": 4,
    }
    assert by_code["lift_door_and_loading_platform"]["unit_power_kw"] == 3.0
    assert by_code["ozone_and_humidification"]["fixed_installed_power_kw"] == 30.0
    assert by_code["floor_heating_cable"]["fixed_installed_power_kw"] == 4.0
    assert all(item["pool"] == "POOL_B" for item in public)

    lighting = _contract_data()["lighting"]
    assert lighting["area_source_field"] == "cold_storage_area_m2"
    assert lighting["area_source_current_equivalent_field"] == "refrigerated_area_m2"
    assert lighting["cold_storage_lighting"] == {
        "quantity_formula": "ceil(cold_storage_area_m2 / 10)",
        "unit_power_kw": 0.04,
        "installed_power_formula": "quantity * 0.04",
        "pool": "POOL_B",
    }
    assert lighting["uv_lighting"] == {
        "quantity_formula": "ceil(cold_storage_area_m2 / 20)",
        "unit_power_kw": 0.08,
        "installed_power_formula": "quantity * 0.08",
        "pool": "POOL_B",
    }
    assert lighting["forbidden_area_substitute"] == "factory_area_m2"


def test_compressor_and_condenser_boundaries_are_frozen_without_double_counting() -> None:
    data = _contract_data()
    compressors = data["compressor_systems"]
    main = compressors["main_system"]
    assert main["included_zone_codes"] == [
        "primary_precooling_room",
        "secondary_precooling_room",
        "raw_fruit_buffer",
        "sorting_packaging_room",
        "coating_room",
        "finished_goods_room",
    ]
    assert main["excluded_zone_codes"] == [
        "frozen_fruit_room",
        "secondary_fruit_buffer",
        "shipping_channel",
    ]
    assert main["cooling_load_source_field"] == "minimum_estimated_cooling_load_kw_r"
    assert main["cooling_load_source_path"] == "zone_plan.result.zones[]"
    assert main["main_system_cop"] == 3.3
    assert main["shaft_power_formula"] == "main_system_cooling_load_kw_r / 3.3"
    assert main["pool"] == "POOL_B"
    assert compressors["no_double_counting_rule"] == (
        "excluded dedicated zones must not enter the main_system COP sum"
    )

    dedicated = {
        item["zone_code"]: item["shaft_power_by_band_kw"]
        for item in compressors["dedicated_systems"]
    }
    assert dedicated == {
        "frozen_fruit_room": {"SMALL": 15.0, "MEDIUM": 25.0, "LARGE": 40.0},
        "secondary_fruit_buffer": {"SMALL": 4.0, "MEDIUM": 6.0, "LARGE": 8.0},
        "shipping_channel": {"SMALL": 8.0, "MEDIUM": 12.0, "LARGE": 16.0},
    }
    assert all(item["pool"] == "POOL_B" for item in compressors["dedicated_systems"])
    assert data["evaporative_condenser"] == {
        "installed_power_by_band_kw": {
            "SMALL": 20.0,
            "MEDIUM": 30.0,
            "LARGE": 40.0,
        },
        "pool": "POOL_B",
    }


def test_production_and_three_power_pools_are_mutually_exclusive() -> None:
    data = _contract_data()
    production = data["production"]
    assert production["installed_power_by_band_kw"] == {
        "SMALL": 200.0,
        "MEDIUM": 300.0,
        "LARGE": 400.0,
    }
    assert production["simultaneity_factor_name"] == ("PRODUCTION_EQUIPMENT_SIMULTANEITY_FACTOR")
    assert production["simultaneity_factor"] == 0.85
    assert production["coincident_power_formula"] == (
        "production_equipment_installed_power_kw * 0.85"
    )
    assert production["pool"] == "POOL_C"
    assert production["must_not_enter_other_pool"] is True

    pools = data["power_pools"]
    assert pools["POOL_A"] == {
        "name": "DEFROST",
        "includes": ["all air-cooler defrost installed power"],
        "includes_only": True,
        "installed_power_formula": "sum(all air-cooler defrost installed power)",
        "simultaneity_factor_name": "DEFROST_SIMULTANEITY_FACTOR",
        "simultaneity_factor": 0.30,
        "coincident_power_formula": "defrost_installed_power_kw * 0.30",
    }
    assert pools["POOL_B"]["name"] == "OTHER"
    assert pools["POOL_B"]["includes_only"] is True
    assert pools["POOL_B"]["excludes"] == [
        "all air-cooler defrost installed power",
        "production equipment",
    ]
    assert pools["POOL_B"]["simultaneity_factor_by_band"] == {
        "SMALL": 1.0,
        "MEDIUM": 0.90,
        "LARGE": 0.80,
    }
    assert pools["POOL_B"]["coincident_power_formula"] == (
        "other_installed_power_kw * other_simultaneity_factor"
    )
    assert pools["POOL_C"] == {
        "name": "PRODUCTION",
        "includes": ["production equipment"],
        "excludes": ["POOL_B"],
        "includes_only": True,
        "installed_power_formula": "production_equipment_installed_power_kw",
        "simultaneity_factor": 0.85,
        "coincident_power_formula": "production_equipment_installed_power_kw * 0.85",
        "must_not_first_enter_other": True,
    }


def test_final_power_and_shared_presentation_contract_are_frozen() -> None:
    data = _contract_data()
    assert data["final_power"] == {
        "estimated_total_power_formula": (
            "estimated_total_power_kw = defrost_coincident_power_kw + "
            "other_coincident_power_kw + production_equipment_coincident_power_kw"
        ),
        "total_installed_power_formula": (
            "total_installed_power_kw = defrost_installed_power_kw + "
            "other_installed_power_kw + production_equipment_installed_power_kw"
        ),
        "estimated_total_power_unit": "kW",
        "total_installed_power_unit": "kW",
    }
    presentation = data["presentation_contract"]
    assert presentation["canonical_source"] == "one_backend_canonical_result"
    assert presentation["workbench_and_aily_read_same_result"] is True
    assert presentation["detail_fields"] == [
        "equipment_or_zone",
        "basis",
        "configured_quantity",
        "unit_power_kw",
        "installed_power_kw",
        "pool",
        "simultaneity_factor",
        "coincident_power_kw",
    ]
    assert presentation["summary_fields"] == [
        "defrost_installed_power_kw",
        "defrost_coincident_power_kw",
        "other_installed_power_kw",
        "other_coincident_power_kw",
        "production_equipment_installed_power_kw",
        "production_equipment_coincident_power_kw",
        "total_installed_power_kw",
        "estimated_total_power_kw",
    ]
    assert set(presentation["recalculation_locks"]) == {
        "NO_AILY_RECALCULATION",
        "NO_FRONTEND_RECALCULATION",
        "NO_OUTBOUND_LIVE_AILY_SESSION",
    }
    assert data["authorization"]["OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED"] == "NO"
    assert data["unit_semantics"] == {
        "power_unit": "kW",
        "estimated_electrical_power": "kW",
        "energy_unit": "kWh",
        "not_energy": True,
        "not_metered_electricity": True,
        "not_daily_electricity_consumption": True,
    }


def test_v19_field_and_existing_calculator_boundary_audit_matches_source() -> None:
    data = _contract_data()
    v19 = data["authority_audit"]["v19_per_zone_cooling_load"]
    assert v19["canonical_field"] == "minimum_estimated_cooling_load_kw_r"
    assert v19["provenance_field"] == "cooling_estimation_basis"
    assert v19["distinct_existing_field"] == ("cooling_load.result.zones[].subtotal_load_kw_r")
    assert v19["mapping_status"] == "MINIMUM_ESTIMATE_AND_SUBTOTAL_ARE_DISTINCT_FIELDS"

    per_zone_text = PER_ZONE_PATH.read_text(encoding="utf-8")
    snapshot_text = SOURCE_SNAPSHOT_PATH.read_text(encoding="utf-8")
    zone_plan_text = ZONE_PLAN_PATH.read_text(encoding="utf-8")
    planning_text = PLANNING_SERVICE_PATH.read_text(encoding="utf-8")
    power_text = POWER_PATH.read_text(encoding="utf-8")
    equipment_text = EQUIPMENT_PATH.read_text(encoding="utf-8")
    preview_text = PREVIEW_LINEAGE_PATH.read_text(encoding="utf-8")

    assert 'MINIMUM_OUTPUT_FIELD = "minimum_estimated_cooling_load_kw_r"' in per_zone_text
    assert 'PROVENANCE_FIELD = "cooling_estimation_basis"' in per_zone_text
    assert "minimum_estimated_cooling_load_kw_r" in snapshot_text
    assert "cooling_estimation_basis" in snapshot_text
    assert "subtotal_load_kw_r" in snapshot_text
    assert 'REPORTING_PRECOOL_SCHEME_ID = "6_position"' in zone_plan_text
    assert "PRECOOL_SIX_POSITIONS_PER_ROOM = 6" in zone_plan_text
    assert "PRECOOL_EIGHT_POSITIONS_PER_ROOM = 8" in zone_plan_text
    assert "schemes" in zone_plan_text
    assert "raw_position_count" in zone_plan_text
    assert "def build_power_configuration" in planning_text
    assert "_ = total_area_m2" in planning_text
    assert "daily_inbound_mass_kg / 25_000" in planning_text
    assert 'row["section"] == "production"' in planning_text
    assert 'CALCULATOR_NAME = "installed_power"' in power_text
    assert "calculate_installed_power" in power_text
    assert "calculate_equipment_capability" in equipment_text
    assert "compressor_cop" in equipment_text
    assert "sum_required_area_by_bands" in preview_text


def test_contract_documents_repeat_the_shared_consumer_and_stop_locks() -> None:
    for path in (CONTRACT_PATH, VERSION_PLAN_PATH, ADR_PATH):
        text = path.read_text(encoding="utf-8")
        assert "NO_AILY_RECALCULATION" in text
        assert "NO_FRONTEND_RECALCULATION" in text
        assert "NO_OUTBOUND_LIVE_AILY_SESSION" in text
        assert OUTBOUND_AILY_AUTHORIZATION_LOCK in text
        assert HOSTILE_OUTBOUND_AILY_AUTHORIZATION_LOCK not in text
        assert "OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED=YES" not in text
        assert "P1_AUTHORIZED=NO" in text
        assert "P2_AUTHORIZED=NO" in text
        assert "MERGE_AUTHORIZED=NO" in text
        assert "READY_AUTHORIZED=NO" in text
