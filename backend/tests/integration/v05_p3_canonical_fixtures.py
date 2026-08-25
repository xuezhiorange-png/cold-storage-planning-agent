"""Shared canonical five-stage calculation fixtures for V0.5 P3 tests."""

from __future__ import annotations

from typing import Any

CANONICAL_CALCULATORS = {
    "cold_room_zone_plan",
    "cooling_load",
    "equipment",
    "installed_power",
    "investment_estimate",
}

ZONE_SNAPSHOT: dict[str, Any] = {
    "zone_results": [
        {
            "zone_code": "Z1",
            "zone_name": "冷藏区A",
            "temperature_level": "0~4℃",
            "area_m2": 200.0,
            "position_count": 40,
            "storage_capacity_kg": 20000.0,
            "process_compatibility": "general",
            "hygiene_zone": "standard",
        }
    ],
    "total_daily_throughput_kg_day": 10000.0,
}

INVESTMENT_SNAPSHOT: dict[str, Any] = {
    "total_investment_cny": 5_000_000.0,
    "zone_investments": {},
}

COOLING_LOAD_SNAPSHOT: dict[str, Any] = {
    "design_cooling_load_kw_r": 200.0,
    "sensible_load_kw_r": 150.0,
    "latent_load_kw_r": 30.0,
    "infiltration_load_kw_r": 20.0,
}

EQUIPMENT_SNAPSHOT: dict[str, Any] = {
    "compressor_operating_capacity_kw_r": 180.0,
    "compressor_installed_capacity_kw_r": 220.0,
    "condenser_heat_rejection_kw": 250.0,
    "installed_power_kw_e": 80.0,
}

INSTALLED_POWER_SNAPSHOT: dict[str, Any] = {
    "total_installed_power_kw_e": "200.0",
    "total_estimated_demand_kw": "160.0",
    "equipment_rows": [],
    "summary_rows": [],
    "items": [],
    "assumptions": [],
}

POWER_CONFIGURATION_SNAPSHOT: dict[str, Any] = {
    "total_installed_power_kw_e": "999.0",
    "total_estimated_demand_kw": "800.0",
    "equipment_rows": [],
    "summary_rows": [],
    "items": [],
    "assumptions": [],
}

CANONICAL_SNAPSHOTS: dict[str, dict[str, Any]] = {
    "cold_room_zone_plan": ZONE_SNAPSHOT,
    "cooling_load": COOLING_LOAD_SNAPSHOT,
    "equipment": EQUIPMENT_SNAPSHOT,
    "installed_power": INSTALLED_POWER_SNAPSHOT,
    "investment_estimate": INVESTMENT_SNAPSHOT,
}
