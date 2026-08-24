"""Unit tests for persisted workbench stage bridge and mapping."""

from cold_storage.modules.projects.application.workbench_result_mapping import (
    power_configuration_to_legacy,
)
from cold_storage.modules.projects.application.workbench_stage_bridge import (
    build_cooling_load_raw_inputs,
    build_equipment_raw_inputs,
    build_power_raw_inputs,
    run_cooling_load_stage,
    run_equipment_stage,
    run_power_stage,
)


def _sample_zones() -> list[dict[str, object]]:
    return [
        {
            "zone_code": "finished_goods",
            "zone_name": "成品冷藏",
            "temperature_band": "1~3℃",
            "required_area_m2": 450,
            "position_count": 120,
        },
        {
            "zone_code": "frozen_goods",
            "zone_name": "冻果暂存",
            "temperature_band": "-18℃",
            "required_area_m2": 200,
            "position_count": 40,
        },
    ]


def test_workbench_stage_bridge_runs_five_stage_chain() -> None:
    project_inputs = {
        "daily_inbound_mass_kg": 25_000,
        "working_time_h_per_day": 16,
    }
    zones = _sample_zones()

    cooling_raw = build_cooling_load_raw_inputs(zones, project_inputs)
    cooling_result = run_cooling_load_stage(cooling_raw)
    assert cooling_result.success is True
    assert cooling_result.calculator_name == "cooling_load"

    equipment_raw = build_equipment_raw_inputs(cooling_result, zones)
    equipment_result = run_equipment_stage(equipment_raw)
    assert equipment_result.success is True
    assert equipment_result.calculator_name == "equipment"

    power_raw = build_power_raw_inputs(equipment_result, cooling_result)
    power_result = run_power_stage(power_raw)
    assert power_result.success is True
    assert power_result.calculator_name == "installed_power"


def test_power_configuration_legacy_mapping_preserves_equipment_rows() -> None:
    power_config = {
        "equipment_rows": [{"sequence": 1, "name": "冷风机", "area": "成品库", "quantity": 3,
                            "defrost_power_kw": None, "defrost_total_power_kw": None,
                            "running_power_kw": 2.5, "total_power_kw": 7.5}],
        "summary_rows": [],
        "items": [],
        "total_installed_power_kw": 7.5,
        "total_estimated_demand_kw": 7.5,
        "requires_review": True,
    }
    legacy = power_configuration_to_legacy(power_config)
    assert legacy.calculator_name == "power_configuration"
    assert legacy.result["equipment_rows"][0]["name"] == "冷风机"
    assert legacy.requires_review is True
