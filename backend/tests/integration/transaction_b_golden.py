"""Shared helpers for cross-backend golden parity tests.

Both SQLite and PostgreSQL integration tests consume the same golden
artifact and compare against identical fixed inputs and deterministic
calculator outputs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_GOLDEN_PATH = (
    Path(__file__).resolve().parent.parent / "golden" / "transaction_b_cross_backend_v1.json"
)

# Fixed calculator outputs — deterministic, identical across SQLite and PG.
_CALCULATOR_OUTPUTS: dict[str, dict[str, Any]] = {
    "zone": {
        "daily_inbound_mass_kg": "25000",
        "design_daily_mass_kg": "30000",
        "total_required_area_m2": "1200",
        "total_area_m2": "1400",
        "planning_parameters": {"safety_factor": "1.2"},
        "zones": [
            {
                "zone_code": "Z1",
                "zone_name": "Pre-cooling",
                "temperature_band": "2~8",
                "function": "precooling",
                "daily_throughput_kg_day": "25000",
                "design_storage_mass_kg": "5000",
                "position_count": 20,
                "required_area_m2": "400",
                "requires_review": False,
            },
            {
                "zone_code": "Z2",
                "zone_name": "Cold Storage",
                "temperature_band": "0~2",
                "function": "storage",
                "daily_throughput_kg_day": "25000",
                "design_storage_mass_kg": "25000",
                "position_count": 100,
                "required_area_m2": "800",
                "requires_review": False,
            },
        ],
    },
    "cooling_load": {
        "total_cooling_load_kw": "350.0",
        "safety_margin_load_kw": "35.0",
        "envelope_heat_transfer_load_kw": "80.0",
        "product_sensible_heat_load_kw": "120.0",
        "packaging_load_kw": "20.0",
        "infiltration_load_kw": "30.0",
        "personnel_load_kw": "15.0",
        "lighting_load_kw": "10.0",
        "evaporator_fan_load_kw": "25.0",
        "defrost_additional_load_kw": "10.0",
        "other_configuration_load_kw": "5.0",
    },
    "equipment": {
        "evaporator_total_cooling_capacity_kw": "500.0",
        "evaporator_quantity": 4,
        "single_evaporator_capacity_kw": "125.0",
        "compressor_operating_capacity_kw": "450.0",
        "standby_capacity_kw": "50.0",
        "condenser_heat_rejection_capacity_kw": "550.0",
        "evaporation_temperature_c": "-10.0",
        "condensing_temperature_c": "40.0",
        "defrost_method": "electric",
        "review_requirement": "",
    },
    "power": {
        "total_installed_power_kw_e": "285.0",
        "compressor_power_kw_e": "200.0",
        "condenser_fan_power_kw_e": "50.0",
        "evaporator_fan_power_kw_e": "25.0",
        "defrost_power_kw_e": "10.0",
        "auxiliary_power_kw_e": "0.0",
    },
    "investment": {
        "total_investment_cny": "12500000",
        "items": [
            {"item_name": "土建部分", "amount_cny": "5000000"},
            {"item_name": "制冷设备", "amount_cny": "4500000"},
            {"item_name": "电气安装", "amount_cny": "1500000"},
            {"item_name": "其他费用", "amount_cny": "1500000"},
        ],
    },
}

# Calculator metadata for golden verification
_CALCULATOR_META: dict[str, dict[str, str]] = {
    "zone": {"calculator_id": "cold_room_zone_plan", "calculator_version": "1.0.0"},
    "cooling_load": {"calculator_id": "cooling_load", "calculator_version": "1.0.0"},
    "equipment": {"calculator_id": "equipment", "calculator_version": "1.0.0"},
    "power": {"calculator_id": "installed_power", "calculator_version": "1.0.0"},
    "investment": {"calculator_id": "investment_estimate", "calculator_version": "1.0.0"},
}


def load_cross_backend_golden() -> dict[str, Any]:
    """Load the golden artifact from disk."""
    return json.loads(_GOLDEN_PATH.read_text())


def get_fixed_inputs() -> dict[str, Any]:
    """Return the fixed identity inputs for golden tests."""
    golden = load_cross_backend_golden()
    return golden["fixed_inputs"]


def get_stage_data() -> dict[str, Any]:
    """Return the stage data (calculator metadata) for golden tests."""
    golden = load_cross_backend_golden()
    return golden["stage_data"]


def get_calculator_output(stage_name: str) -> dict[str, Any]:
    """Return the fixed calculator output for a given stage."""
    return dict(_CALCULATOR_OUTPUTS[stage_name])
