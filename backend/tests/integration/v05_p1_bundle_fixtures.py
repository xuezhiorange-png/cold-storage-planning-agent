"""Shared EngineeringInputBundleV1 fixtures for V0.5 P1 tests."""

from __future__ import annotations

from typing import Any


def bundle_leaf(
    value: Any,
    *,
    unit: str | None = None,
    state: str = "provided",
    source_type: str = "user",
    requires_review: bool = True,
) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "state": state,
        "source_type": source_type,
        "validity_status": "unverified",
        "requires_review": requires_review,
    }


def build_valid_engineering_input_bundle(
    *,
    project_id: str,
    project_version_id: str,
    version_number: int,
    version_status: str = "draft",
    correlation_id: str = "corr-v05-p1-001",
    actor_principal: str = "test-actor",
    omit_cooling_geometry: bool = False,
) -> dict[str, Any]:
    cooling_zone: dict[str, Any] = {
        "zone_code": bundle_leaf("Z1", unit=None),
        "zone_name": bundle_leaf("Freezer", unit=None),
        "temperature_level": bundle_leaf("low_temperature", unit=None),
        "zone_area": bundle_leaf("100.0", unit="m2"),
        "room_height": bundle_leaf("5.0", unit="m"),
        "wall_area": bundle_leaf("200.0", unit="m2"),
        "roof_area": bundle_leaf("100.0", unit="m2"),
        "floor_area": bundle_leaf("100.0", unit="m2"),
        "outdoor_design_temperature": bundle_leaf("30.0", unit="C"),
        "room_design_temperature": bundle_leaf("-18.0", unit="C"),
        "operating_hours_per_day": bundle_leaf("16.0", unit="h/day"),
        "product_mass_per_day": bundle_leaf("20000.0", unit="kg/day"),
        "product_entry_temperature": bundle_leaf("20.0", unit="C"),
        "product_target_temperature": bundle_leaf("-18.0", unit="C"),
        "cooling_duration": bundle_leaf("8.0", unit="h"),
        "u_value_wall": bundle_leaf("0.25", unit="W/(m2·K)", source_type="coefficient"),
        "u_value_roof": bundle_leaf("0.20", unit="W/(m2·K)", source_type="coefficient"),
        "u_value_floor": bundle_leaf("0.30", unit="W/(m2·K)", source_type="coefficient"),
        "product_specific_heat": bundle_leaf("3.6", unit="kJ/(kg·K)", source_type="coefficient"),
    }
    if omit_cooling_geometry:
        cooling_zone.pop("zone_area")

    return {
        "schema_id": "EngineeringInputBundleV1",
        "schema_version": "1.0.0",
        "project_version_identity": {
            "project_id": bundle_leaf(project_id, unit=None, source_type="persisted", requires_review=False),
            "project_version_id": bundle_leaf(
                project_version_id, unit=None, source_type="persisted", requires_review=False
            ),
            "version_number": bundle_leaf(version_number, unit=None, source_type="persisted", requires_review=False),
            "version_status": bundle_leaf(version_status, unit=None, source_type="persisted", requires_review=False),
            "is_archived": bundle_leaf(False, unit=None, source_type="persisted", requires_review=False),
            "actor_principal": bundle_leaf(actor_principal, unit=None, requires_review=False),
            "correlation_id": bundle_leaf(correlation_id, unit=None, requires_review=False),
        },
        "zone_planning_inputs": {
            "daily_inbound_mass_kg": bundle_leaf("20000", unit="kg/day"),
            "working_time_h_per_day": bundle_leaf("16", unit="h/day"),
            "finished_storage_days": bundle_leaf("7", unit="day"),
            "packaging_storage_days": bundle_leaf("1", unit="day"),
            "precooling_required_ratio": bundle_leaf("0.6", unit="ratio"),
        },
        "cooling_load_inputs": {
            "zones": [cooling_zone],
            "coefficients": bundle_leaf(
                {
                    "design_margin_ratio": "1.1",
                    "diversity_factor": "0.85",
                    "air_change_rate": "0.5",
                    "respiration_heat": "0.0",
                    "worker_heat_gain": "0.275",
                    "motor_efficiency": "0.85",
                },
                unit=None,
                source_type="coefficient",
            ),
        },
        "equipment_inputs": {
            "condensing_temperature_c": bundle_leaf("40.0", unit="C"),
            "systems": [
                {
                    "system_code": bundle_leaf("S1", unit=None),
                    "system_name": bundle_leaf("Frozen system", unit=None),
                    "design_evaporating_temperature": bundle_leaf("-25.0", unit="C"),
                    "zones": [
                        {
                            "zone_code": bundle_leaf("Z1", unit=None),
                            "zone_name": bundle_leaf("Freezer", unit=None),
                            "evaporator_count": bundle_leaf(2, unit="count"),
                            "defrost_method": bundle_leaf("electric", unit=None),
                            "design_cooling_load_kw_r": bundle_leaf(
                                "120.0", unit="kW(r)", source_type="persisted"
                            ),
                        }
                    ],
                }
            ],
            "coefficients": bundle_leaf(
                {
                    "redundancy_ratio": "1.0",
                    "evaporator_capacity_margin": "1.1",
                    "condenser_capacity_margin": "1.1",
                    "compressor_cop": "2.5",
                },
                unit=None,
                source_type="coefficient",
            ),
        },
        "installed_power_inputs": {
            "compressor_input_power_kw_e": bundle_leaf("120.0", unit="kW(e)"),
            "evaporator_fan_power_kw_e": bundle_leaf("10.0", unit="kW(e)"),
            "condenser_fan_power_kw_e": bundle_leaf("8.0", unit="kW(e)"),
        },
        "investment_inputs": {
            "total_area_m2": bundle_leaf("1000.0", unit="m2", source_type="persisted"),
            "refrigerated_area_m2": bundle_leaf("800.0", unit="m2", source_type="persisted"),
            "frozen_area_m2": bundle_leaf("200.0", unit="m2", source_type="persisted"),
            "position_count": bundle_leaf(100, unit="count", source_type="persisted"),
            "total_power_kw": bundle_leaf("150.0", unit="kW(e)", source_type="persisted"),
        },
        "coefficient_context": {
            "coefficient_context_id": bundle_leaf("coeff-demo-001", unit=None, source_type="coefficient"),
            "approved_revision_ids": bundle_leaf(["rev-001"], unit=None, source_type="coefficient"),
            "demo_coefficient_leaves": [],
        },
        "units_metadata": {
            "leaf_unit_by_path": {
                "zone_planning_inputs.daily_inbound_mass_kg": "kg/day",
                "cooling_load_inputs.zones[0].zone_area": "m2",
                "installed_power_inputs.compressor_input_power_kw_e": "kW(e)",
            }
        },
        "source_metadata": {
            "input_group_provenance": {
                "zone_planning_inputs": "user_entry",
                "cooling_load_inputs": "user_entry",
                "equipment_inputs": "user_entry",
                "installed_power_inputs": "user_entry",
                "investment_inputs": "persisted_upstream_confirmed",
            }
        },
        "review_metadata": {
            "overall_requires_review": bundle_leaf(True, unit=None),
            "per_group_requires_review": {
                "zone_planning_inputs": True,
                "cooling_load_inputs": True,
                "equipment_inputs": True,
                "installed_power_inputs": True,
                "investment_inputs": True,
            },
        },
    }
