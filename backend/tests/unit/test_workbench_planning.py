"""Unit tests for persisted workbench result mapping."""

from cold_storage.modules.projects.application.workbench_result_mapping import (
    power_configuration_to_legacy,
)


def test_power_configuration_legacy_mapping_preserves_equipment_rows() -> None:
    power_config = {
        "equipment_rows": [
            {
                "sequence": 1,
                "name": "冷风机",
                "area": "成品库",
                "quantity": 3,
                "defrost_power_kw": None,
                "defrost_total_power_kw": None,
                "running_power_kw": 2.5,
                "total_power_kw": 7.5,
            }
        ],
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
