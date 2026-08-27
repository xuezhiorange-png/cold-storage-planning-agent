"""Assemble OperatorProcessInputV1 into EngineeringInputBundleV1 (V0.9 P1).

V0.9 compact path: five operator KEY (schema_version 1.1.0) expanded with
catalog/derived leftovers. V0.8 compact path (schema_version 1.0.0 or
omitted-as-V0.8) assembles as today.

Copies existing production authority (dataclass defaults, demo catalog envelopes)
into explicit bundle leaves. Does not invent engineering numbers or recut formulas.
V0.9 P2 registers shipping_channel in REFRIGERATED_ZONE_REGISTRY (1~3℃ demo envelope).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import MISSING, fields
from decimal import Decimal
from typing import Any, NoReturn
from uuid import uuid4

from cold_storage.modules.calculations.domain.equipment import ZoneEquipmentInput
from cold_storage.modules.calculations.domain.power import InstalledPowerCalcInput
from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    DemoZoneCoefficient,
)
from cold_storage.modules.projects.application.engineering_input_bundle import (
    BUNDLE_SCHEMA_ID,
    BUNDLE_SCHEMA_VERSION,
    LINEAGE_PENDING_STATE,
    OPERATOR_PROCESS_SCHEMA_ID,
    OPERATOR_PROCESS_SCHEMA_VERSION_V08,
    OPERATOR_PROCESS_SCHEMA_VERSION_V09,
    OPERATOR_V08_FIVE_KEY_FIELDS,
    OPERATOR_V09_FIVE_KEY_FIELDS,
    BundleValidationError,
    EngineeringInputBundleValidationError,
)
from cold_storage.modules.projects.domain.models import ProjectVersion
from cold_storage.shared.errors import MissingEngineeringParameterError

# Refrigerated zone codes produced by cold_room_zone_plan (常温 zones excluded).
REFRIGERATED_ZONE_REGISTRY: tuple[tuple[str, str, str], ...] = (
    ("primary_precooling_room", "一级预冷间", "8~10℃"),
    ("secondary_precooling_room", "二级预冷间", "1~3℃"),
    ("raw_fruit_buffer", "原果暂存间", "8~10℃"),
    ("sorting_packaging_room", "分选包装间", "8~10℃"),
    ("coating_room", "覆膜间", "1~3℃"),
    ("finished_goods_room", "成品间", "1~3℃"),
    ("secondary_fruit_buffer", "次果暂存间", "8~10℃"),
    ("frozen_fruit_room", "冻果间", "-18℃"),
    ("shipping_channel", "出货通道", "1~3℃"),
)

# V0.9 catalog copies of planner-required leaves that are no longer operator KEY.
# Numbers are existing repo authority (V0.8 sample / V09-E1), not invented.
_V09_WORKING_TIME_H_PER_DAY_CATALOG = "16"
_V09_WORKING_TIME_CATALOG_SOURCE = "samples/v08-process-input/manifest.json"
_V09_PRECOOLING_REQUIRED_RATIO_CATALOG = "1.0"
_V09_PRECOOLING_RATIO_CATALOG_SOURCE = "docs/tasks/V0_9-version-plan.md#V09-E1"

# source_type=demo mapping table; targets are existing TemperatureLevel enum members.
TEMPERATURE_BAND_TO_LEVEL: dict[str, str] = {
    "8~10℃": "precooling",
    "1~3℃": "medium_temperature",
    "-18℃": "low_temperature",
}

# v05 workbench single-zone thermal catalog (samples/v05-local-workbench/manifest.json).
# Applied as global demo leaves to every refrigerated zone (same rule as wall_area / room_height).
_WORKBENCH_PRODUCT_MASS_PER_DAY = "20000.0"
_WORKBENCH_ROOM_DESIGN_TEMPERATURE_C = "-18.0"
_WORKBENCH_PRODUCT_TARGET_TEMPERATURE_C = "-18.0"

SYSTEM_GROUP_BY_BAND: dict[str, tuple[str, str]] = {
    "8~10℃": ("system_8_10c", "8~10℃制冷系统"),
    "1~3℃": ("system_1_3c", "1~3℃制冷系统"),
    "-18℃": ("system_minus_18c", "-18℃制冷系统"),
}

# V0.5/V0.7 workbench single-zone envelope catalog (samples/v05-local-workbench/manifest.json).
_WORKBENCH_ENVELOPE_CATALOG_SOURCE = "samples/v05-local-workbench/manifest.json"

_CONFLICT_ZONE_DEFAULT_FIELDS: frozenset[str] = frozenset(
    {
        "frozen_fruit_ratio",
        "frozen_storage_days",
        "storage_position_capacity_kg",
    }
)

_ZONE_DEFAULT_FIELD_UNITS: dict[str, str | None] = {
    "raw_holding_hours": "h",
    "storage_position_capacity_kg": "kg",
    "secondary_fruit_ratio": "ratio",
    "frozen_fruit_ratio": "ratio",
    "frozen_storage_days": "day",
    "precooling_position_daily_capacity_kg": "kg/day",
    "primary_precooling_pallet_weight_kg": "kg",
    "primary_precooling_hours_per_pallet": "h",
    "primary_precooling_working_hours_per_day": "h/day",
    "secondary_precooling_pallet_weight_kg": "kg",
    "secondary_precooling_hours_per_pallet": "h",
    "secondary_precooling_working_hours_per_day": "h/day",
    "raw_storage_ratio": "ratio",
    "raw_fruit_pallet_weight_kg": "kg",
    "finished_goods_pallet_weight_kg": "kg",
    "frozen_goods_pallet_weight_kg": "kg",
    "secondary_fruit_area_ratio": "ratio",
    "pallet_length_m": "m",
    "pallet_width_m": "m",
    "pallet_longitudinal_gap_m": "m",
    "storage_area_factor": "ratio",
    "precooling_position_area_m2": "m2",
    "packing_pieces_per_person_hour": "count/(person·h)",
    "packing_weight_per_piece_kg": "kg",
    "packing_working_hours_per_day": "h/day",
    "workers_per_packing_table": "count",
    "packing_table_horizontal_spacing_m": "m",
    "packing_table_vertical_spacing_m": "m",
    "packing_area_factor": "ratio",
    "main_packaging_storage_days": "day",
    "auxiliary_packaging_storage_days": "day",
    "packaging_area_factor": "ratio",
    "office_fixed_area_m2": "m2",
    "changing_fixed_area_m2": "m2",
    "coating_fixed_area_m2": "m2",
}


def is_operator_process_input_payload(payload: Mapping[str, Any]) -> bool:
    """Return True when payload is compact OperatorProcessInputV1, not a full bundle."""
    if payload.get("schema_id") == BUNDLE_SCHEMA_ID:
        return False
    if payload.get("schema_id") == OPERATOR_PROCESS_SCHEMA_ID:
        return True
    zone_section = payload.get("zone_planning_inputs")
    if not isinstance(zone_section, dict):
        return False
    return _has_all_operator_keys(
        zone_section, OPERATOR_V08_FIVE_KEY_FIELDS
    ) or _has_all_operator_keys(zone_section, OPERATOR_V09_FIVE_KEY_FIELDS)


def detect_operator_process_path(payload: Mapping[str, Any]) -> str:
    """Return ``v08`` or ``v09`` from schema_version / KEY set. Fail-closed if neither."""
    schema_version = payload.get("schema_version")
    section = payload.get("zone_planning_inputs")
    if not isinstance(section, dict):
        _raise_missing("zone_planning_inputs", "missing zone_planning_inputs section")
    has_v08 = _has_all_operator_keys(section, OPERATOR_V08_FIVE_KEY_FIELDS)
    has_v09 = _has_all_operator_keys(section, OPERATOR_V09_FIVE_KEY_FIELDS)
    if schema_version == OPERATOR_PROCESS_SCHEMA_VERSION_V09:
        return "v09"
    if schema_version == OPERATOR_PROCESS_SCHEMA_VERSION_V08:
        return "v08"
    if schema_version is None:
        if has_v08:
            return "v08"
        if has_v09:
            return "v09"
        _raise_missing(
            "zone_planning_inputs",
            "neither V0.8 nor V0.9 operator five KEY set is complete",
        )
    _raise_missing("schema_version", f"unsupported operator schema_version {schema_version!r}")


def operator_key_fields_for_path(path: str) -> tuple[str, ...]:
    if path == "v09":
        return OPERATOR_V09_FIVE_KEY_FIELDS
    return OPERATOR_V08_FIVE_KEY_FIELDS


def validate_operator_process_input(payload: Mapping[str, Any]) -> None:
    """Validate the five operator KEY leaves before assembly (V0.8 or V0.9 path)."""
    schema_id = payload.get("schema_id")
    if schema_id is not None and schema_id != OPERATOR_PROCESS_SCHEMA_ID:
        _raise_missing("schema_id", f"unsupported operator schema_id {schema_id!r}")
    schema_version = payload.get("schema_version")
    if schema_version is not None and schema_version not in {
        OPERATOR_PROCESS_SCHEMA_VERSION_V08,
        OPERATOR_PROCESS_SCHEMA_VERSION_V09,
    }:
        _raise_missing("schema_version", f"unsupported operator schema_version {schema_version!r}")
    section = payload.get("zone_planning_inputs")
    if not isinstance(section, dict):
        _raise_missing("zone_planning_inputs", "missing zone_planning_inputs section")
    path = detect_operator_process_path(payload)
    for field_name in operator_key_fields_for_path(path):
        _required_operator_numeric_leaf(section, field_name, f"zone_planning_inputs.{field_name}")
    if path == "v09" and "precooling_required_ratio" in section:
        _raise_missing(
            "zone_planning_inputs.precooling_required_ratio",
            "OPERATOR_PRECOOLING_RATIO_KEY is forbidden on the V0.9 operator path",
        )


def assemble_engineering_input_bundle(
    *,
    operator_input: Mapping[str, Any],
    project_id: str,
    version: ProjectVersion,
    actor: str,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Expand operator-minimal input into a complete EngineeringInputBundleV1."""
    validate_operator_process_input(operator_input)
    path = detect_operator_process_path(operator_input)
    key_fields = operator_key_fields_for_path(path)
    zone_section = operator_input["zone_planning_inputs"]
    operator_values = {
        field_name: _operator_numeric_value(zone_section, field_name) for field_name in key_fields
    }
    corr_id = correlation_id or str(uuid4())
    zone_defaults = _zone_plan_input_defaults()
    demo_coefficient_leaves = _demo_zone_coefficient_leaves()
    zone_planning_inputs = _zone_planning_inputs_section(
        operator_values=operator_values,
        zone_defaults=zone_defaults,
        operator_key_fields=key_fields,
    )
    working_time_h_per_day, operating_hours_source_type, operating_hours_source_path = (
        _operating_hours_catalog(path, operator_values, zone_planning_inputs)
    )

    bundle: dict[str, Any] = {
        "schema_id": BUNDLE_SCHEMA_ID,
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "project_version_identity": _project_version_identity(
            project_id=project_id,
            version=version,
            actor=actor,
            correlation_id=corr_id,
        ),
        "zone_planning_inputs": zone_planning_inputs,
        "cooling_load_inputs": _cooling_load_inputs_section(
            working_time_h_per_day=working_time_h_per_day,
            operating_hours_source_type=operating_hours_source_type,
            operating_hours_source_path=operating_hours_source_path,
        ),
        "equipment_inputs": _equipment_inputs_section(),
        "installed_power_inputs": _installed_power_inputs_section(),
        "investment_inputs": _investment_inputs_section(),
        "coefficient_context": {
            "coefficient_context_id": _demo_leaf(
                "operator-minimal-demo-catalog",
                unit=None,
            ),
            "approved_revision_ids": _demo_leaf([], unit=None),
            "demo_coefficient_leaves": demo_coefficient_leaves,
        },
        "units_metadata": {
            "leaf_unit_by_path": _leaf_unit_by_path(operator_values),
        },
        "source_metadata": {
            "input_group_provenance": {
                "zone_planning_inputs": "user_entry",
                "cooling_load_inputs": "persisted_upstream_confirmed",
                "equipment_inputs": "persisted_upstream_confirmed",
                "installed_power_inputs": "persisted_upstream_confirmed",
                "investment_inputs": "persisted_upstream_confirmed",
            }
        },
        "review_metadata": {
            "overall_requires_review": _demo_leaf(True, unit=None, requires_review=True),
            "per_group_requires_review": {
                "zone_planning_inputs": True,
                "cooling_load_inputs": True,
                "equipment_inputs": True,
                "installed_power_inputs": True,
                "investment_inputs": True,
            },
        },
    }
    return bundle


def _zone_planning_inputs_section(
    *,
    operator_values: dict[str, str],
    zone_defaults: dict[str, str],
    operator_key_fields: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    key_fields = operator_key_fields or OPERATOR_V08_FIVE_KEY_FIELDS
    section: dict[str, Any] = {}
    for field_name in key_fields:
        section[field_name] = _user_leaf(
            operator_values[field_name],
            unit=_operator_field_unit(field_name),
        )
    for field_name, value in zone_defaults.items():
        if field_name in key_fields or field_name in section:
            continue
        validity = "conflict" if field_name in _CONFLICT_ZONE_DEFAULT_FIELDS else "unverified"
        section[field_name] = _demo_leaf(
            value,
            unit=_ZONE_DEFAULT_FIELD_UNITS.get(field_name),
            validity_status=validity,
        )
    if "working_time_h_per_day" not in section:
        section["working_time_h_per_day"] = _demo_leaf(
            _V09_WORKING_TIME_H_PER_DAY_CATALOG,
            unit="h/day",
            source_path=_V09_WORKING_TIME_CATALOG_SOURCE,
        )
    if "precooling_required_ratio" not in section:
        section["precooling_required_ratio"] = _demo_leaf(
            _V09_PRECOOLING_REQUIRED_RATIO_CATALOG,
            unit="ratio",
            source_path=_V09_PRECOOLING_RATIO_CATALOG_SOURCE,
        )
    if "packaging_storage_days" not in section:
        if "main_packaging_storage_days" not in operator_values:
            _raise_missing(
                "zone_planning_inputs.main_packaging_storage_days",
                "V0.9 packaging_storage_days is derived from main_packaging_storage_days",
            )
        section["packaging_storage_days"] = _user_leaf(
            operator_values["main_packaging_storage_days"],
            unit="day",
            source_path="zone_planning_inputs.main_packaging_storage_days",
        )
    return section


def _operating_hours_catalog(
    path: str,
    operator_values: dict[str, str],
    zone_planning_inputs: Mapping[str, Any],
) -> tuple[str, str, str]:
    if path == "v08":
        return (
            operator_values["working_time_h_per_day"],
            "user",
            "zone_planning_inputs.working_time_h_per_day",
        )
    leaf = zone_planning_inputs["working_time_h_per_day"]
    value = leaf.get("value") if isinstance(leaf, dict) else leaf
    return (
        _decimalize(value),
        "demo",
        _V09_WORKING_TIME_CATALOG_SOURCE,
    )


def _cooling_load_inputs_section(
    *,
    working_time_h_per_day: str,
    operating_hours_source_type: str = "user",
    operating_hours_source_path: str = "zone_planning_inputs.working_time_h_per_day",
) -> dict[str, Any]:
    zones: list[dict[str, Any]] = []
    for zone_code, _zone_name, temperature_band in REFRIGERATED_ZONE_REGISTRY:
        if temperature_band not in TEMPERATURE_BAND_TO_LEVEL:
            raise EngineeringInputBundleValidationError(
                BundleValidationError(
                    code="UPSTREAM_LINEAGE_BIND_FAILED",
                    field_path="cooling_load_inputs.zones",
                    message=(
                        f"temperature_band {temperature_band!r} has no TemperatureLevel mapping"
                    ),
                )
            )
        zone_entry: dict[str, Any] = {
            "zone_code": _lineage_pending_leaf(unit=None),
            "zone_name": _lineage_pending_leaf(unit=None),
            "temperature_level": _lineage_pending_leaf(unit=None),
            "zone_area": _lineage_pending_leaf(unit="m2"),
            "floor_area": _lineage_pending_leaf(unit="m2"),
            "room_height": _catalog_leaf(
                "5.0", unit="m", source_path=_WORKBENCH_ENVELOPE_CATALOG_SOURCE
            ),
            "wall_area": _catalog_leaf(
                "200.0", unit="m2", source_path=_WORKBENCH_ENVELOPE_CATALOG_SOURCE
            ),
            "roof_area": _catalog_leaf(
                "100.0", unit="m2", source_path=_WORKBENCH_ENVELOPE_CATALOG_SOURCE
            ),
            "outdoor_design_temperature": _catalog_leaf(
                "30.0", unit="C", source_path=_WORKBENCH_ENVELOPE_CATALOG_SOURCE
            ),
            "room_design_temperature": _catalog_leaf(
                _WORKBENCH_ROOM_DESIGN_TEMPERATURE_C,
                unit="C",
                source_path=_WORKBENCH_ENVELOPE_CATALOG_SOURCE,
            ),
            "operating_hours_per_day": _catalog_leaf(
                working_time_h_per_day,
                unit="h/day",
                source_path=operating_hours_source_path,
                source_type=operating_hours_source_type,
            ),
            "product_mass_per_day": _catalog_leaf(
                _WORKBENCH_PRODUCT_MASS_PER_DAY,
                unit="kg/day",
                source_path=_WORKBENCH_ENVELOPE_CATALOG_SOURCE,
            ),
            "product_entry_temperature": _catalog_leaf(
                "20.0", unit="C", source_path=_WORKBENCH_ENVELOPE_CATALOG_SOURCE
            ),
            "product_target_temperature": _catalog_leaf(
                _WORKBENCH_PRODUCT_TARGET_TEMPERATURE_C,
                unit="C",
                source_path=_WORKBENCH_ENVELOPE_CATALOG_SOURCE,
            ),
            "cooling_duration": _catalog_leaf(
                "8.0", unit="h", source_path=_WORKBENCH_ENVELOPE_CATALOG_SOURCE
            ),
            "u_value_wall": _coefficient_leaf(
                "0.25", unit="W/(m2·K)", source_path=_WORKBENCH_ENVELOPE_CATALOG_SOURCE
            ),
            "u_value_roof": _coefficient_leaf(
                "0.20", unit="W/(m2·K)", source_path=_WORKBENCH_ENVELOPE_CATALOG_SOURCE
            ),
            "u_value_floor": _coefficient_leaf(
                "0.30", unit="W/(m2·K)", source_path=_WORKBENCH_ENVELOPE_CATALOG_SOURCE
            ),
            "product_specific_heat": _coefficient_leaf(
                "3.6", unit="kJ/(kg·K)", source_path=_WORKBENCH_ENVELOPE_CATALOG_SOURCE
            ),
        }
        # Stash expected zone_code for lineage matching (not consumed by calculators).
        zone_entry["_assembler_expected_zone_code"] = zone_code
        zones.append(zone_entry)
    return {
        "zones": zones,
        "coefficients": _coefficient_leaf(
            {
                "design_margin_ratio": "1.1",
                "diversity_factor": "0.85",
                "air_change_rate": "0.5",
                "respiration_heat": "0.0",
                "worker_heat_gain": "0.275",
                "motor_efficiency": "0.85",
            },
            unit=None,
            source_path=_WORKBENCH_ENVELOPE_CATALOG_SOURCE,
        ),
    }


def _equipment_inputs_section() -> dict[str, Any]:
    equipment_defaults = _zone_equipment_input_defaults()
    systems_by_band: dict[str, dict[str, Any]] = {}
    for zone_code, zone_name, temperature_band in REFRIGERATED_ZONE_REGISTRY:
        system_code, system_name = SYSTEM_GROUP_BY_BAND[temperature_band]
        system = systems_by_band.setdefault(
            temperature_band,
            {
                "system_code": _demo_leaf(system_code, unit=None),
                "system_name": _demo_leaf(system_name, unit=None),
                "design_evaporating_temperature": _demo_leaf(
                    equipment_defaults["evaporation_temperature_c"],
                    unit="C",
                    source_path="ZoneEquipmentInput.evaporation_temperature_c",
                ),
                "zones": [],
            },
        )
        system["zones"].append(
            {
                "zone_code": _demo_leaf(
                    zone_code, unit=None, source_path="REFRIGERATED_ZONE_REGISTRY"
                ),
                "zone_name": _demo_leaf(
                    zone_name, unit=None, source_path="REFRIGERATED_ZONE_REGISTRY"
                ),
                "evaporator_count": _demo_leaf(
                    equipment_defaults["evaporator_count"],
                    unit="count",
                    source_path="ZoneEquipmentInput.evaporator_count",
                ),
                "defrost_method": _demo_leaf(
                    equipment_defaults["defrost_method"],
                    unit=None,
                    source_path="ZoneEquipmentInput.defrost_method",
                ),
                "design_cooling_load_kw_r": _lineage_pending_leaf(unit="kW(r)"),
            }
        )
    return {
        "condensing_temperature_c": _catalog_leaf(
            "40.0",
            unit="C",
            source_path="samples/v07-trust-loop/manifest.json",
        ),
        "systems": list(systems_by_band.values()),
        "coefficients": _coefficient_leaf(
            {
                "redundancy_ratio": "1.0",
                "evaporator_capacity_margin": "1.1",
                "condenser_capacity_margin": "1.1",
                "compressor_cop": "2.5",
            },
            unit=None,
            source_path=_WORKBENCH_ENVELOPE_CATALOG_SOURCE,
        ),
    }


def _installed_power_inputs_section() -> dict[str, Any]:
    power_defaults = _installed_power_defaults()
    return {
        "compressor_input_power_kw_e": _lineage_pending_leaf(unit="kW(e)"),
        "evaporator_fan_power_kw_e": _demo_leaf(
            power_defaults["evaporator_fan_power_kw_e"],
            unit="kW(e)",
            source_path="InstalledPowerCalcInput.evaporator_fan_power_kw_e",
        ),
        "condenser_fan_power_kw_e": _demo_leaf(
            power_defaults["condenser_fan_power_kw_e"],
            unit="kW(e)",
            source_path="InstalledPowerCalcInput.condenser_fan_power_kw_e",
        ),
    }


def _investment_inputs_section() -> dict[str, Any]:
    return {
        "total_area_m2": _lineage_pending_leaf(unit="m2"),
        "refrigerated_area_m2": _lineage_pending_leaf(unit="m2"),
        "frozen_area_m2": _lineage_pending_leaf(unit="m2"),
        "position_count": _lineage_pending_leaf(unit="count"),
        "total_power_kw": _lineage_pending_leaf(unit="kW(e)"),
    }


def _project_version_identity(
    *,
    project_id: str,
    version: ProjectVersion,
    actor: str,
    correlation_id: str,
) -> dict[str, Any]:
    return {
        "project_id": _persisted_leaf(project_id, unit=None),
        "project_version_id": _persisted_leaf(version.id, unit=None),
        "version_number": _persisted_leaf(version.version_number, unit=None),
        "version_status": _persisted_leaf(version.status, unit=None),
        "is_archived": _persisted_leaf(version.status == "archived", unit=None),
        "actor_principal": _persisted_leaf(actor, unit=None),
        "correlation_id": _persisted_leaf(correlation_id, unit=None),
    }


def _zone_plan_input_defaults() -> dict[str, str]:
    defaults: dict[str, str] = {}
    for field_info in fields(ColdRoomZonePlanInput):
        if field_info.default is not MISSING:
            defaults[field_info.name] = _decimalize(field_info.default)
        elif field_info.default_factory is not MISSING:
            defaults[field_info.name] = _decimalize(field_info.default_factory())
    return defaults


def _demo_zone_coefficient_leaves() -> list[dict[str, Any]]:
    from cold_storage.modules.calculations.domain.zone_planning import ColdRoomZonePlanner

    coefficients = ColdRoomZonePlanner()._coefficients  # noqa: SLF001 — catalog authority
    leaves: list[dict[str, Any]] = []
    for coeff in coefficients.values():
        if isinstance(coeff, DemoZoneCoefficient):
            reference = dict(coeff.to_reference())
            value = reference.get("value")
            if isinstance(value, float):
                reference["value"] = _decimalize(value)
            leaves.append(reference)
    return leaves


def _zone_equipment_input_defaults() -> dict[str, str]:
    field_defaults = {
        field_info.name: field_info.default
        for field_info in fields(ZoneEquipmentInput)
        if field_info.default is not MISSING
    }
    return {
        "evaporator_count": str(field_defaults["evaporator_count"]),
        "evaporation_temperature_c": _decimalize(field_defaults["evaporation_temperature_c"]),
        "defrost_method": str(field_defaults["defrost_method"]),
    }


def _installed_power_defaults() -> dict[str, str]:
    return {
        "evaporator_fan_power_kw_e": _decimalize(
            InstalledPowerCalcInput().evaporator_fan_power_kw_e
        ),
        "condenser_fan_power_kw_e": _decimalize(InstalledPowerCalcInput().condenser_fan_power_kw_e),
    }


def _leaf_unit_by_path(operator_values: dict[str, str]) -> dict[str, str]:
    units = {
        f"zone_planning_inputs.{field_name}": _operator_field_unit(field_name)
        for field_name in operator_values
    }
    units["installed_power_inputs.compressor_input_power_kw_e"] = "kW(e)"
    return units


def _operator_field_unit(field_name: str) -> str:
    return {
        "daily_inbound_mass_kg": "kg/day",
        "working_time_h_per_day": "h/day",
        "finished_storage_days": "day",
        "packaging_storage_days": "day",
        "precooling_required_ratio": "ratio",
        "frozen_storage_days": "day",
        "main_packaging_storage_days": "day",
        "auxiliary_packaging_storage_days": "day",
    }[field_name]


def _user_leaf(value: Any, *, unit: str | None, source_path: str | None = None) -> dict[str, Any]:
    leaf = {
        "value": _decimalize(value),
        "unit": unit,
        "state": "provided",
        "source_type": "user",
        "validity_status": "unverified",
        "requires_review": True,
    }
    if source_path is not None:
        leaf["source_path"] = source_path
    return leaf


def _persisted_leaf(value: Any, *, unit: str | None) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "state": "provided",
        "source_type": "persisted",
        "validity_status": "verified",
        "requires_review": False,
    }


def _demo_leaf(
    value: Any,
    *,
    unit: str | None,
    source_path: str | None = None,
    validity_status: str = "unverified",
    requires_review: bool = True,
) -> dict[str, Any]:
    if unit is None and isinstance(value, str):
        serialized: Any = value
    elif isinstance(value, (bool, list, dict)):
        serialized = value
    else:
        serialized = _decimalize(value)
    leaf = {
        "value": serialized,
        "unit": unit,
        "state": "provided",
        "source_type": "demo",
        "validity_status": validity_status,
        "requires_review": requires_review,
    }
    if source_path is not None:
        leaf["source_path"] = source_path
    return leaf


def _catalog_leaf(
    value: Any,
    *,
    unit: str | None,
    source_path: str,
    source_type: str = "demo",
) -> dict[str, Any]:
    return {
        "value": _decimalize(value),
        "unit": unit,
        "state": "provided",
        "source_type": source_type,
        "validity_status": "unverified",
        "requires_review": True,
        "source_path": source_path,
    }


def _coefficient_leaf(
    value: Any,
    *,
    unit: str | None,
    source_path: str,
) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "state": "provided",
        "source_type": "coefficient",
        "validity_status": "unverified",
        "requires_review": True,
        "source_path": source_path,
    }


def _lineage_pending_leaf(*, unit: str | None) -> dict[str, Any]:
    return {
        "value": None,
        "unit": unit,
        "state": LINEAGE_PENDING_STATE,
        "source_type": "persisted",
        "validity_status": "unverified",
        "requires_review": True,
    }


def _has_all_operator_keys(section: Mapping[str, Any], field_names: tuple[str, ...]) -> bool:
    return all(field_name in section for field_name in field_names)


def _required_operator_numeric_leaf(
    section: Mapping[str, Any],
    field_name: str,
    field_path: str,
) -> None:
    if field_name not in section:
        _raise_missing(field_path)
    leaf = section[field_name]
    if isinstance(leaf, dict) and "value" in leaf:
        if leaf.get("state") == "missing" or leaf.get("value") is None:
            _raise_missing(field_path)
        unit = leaf.get("unit")
        if unit in (None, ""):
            _raise_missing(f"{field_path}.unit")
        return
    if leaf is None:
        _raise_missing(field_path)


def _operator_numeric_value(section: Mapping[str, Any], field_name: str) -> str:
    leaf = section[field_name]
    value = leaf.get("value") if isinstance(leaf, dict) else leaf
    return _decimalize(value)


def _decimalize(value: Any) -> str:
    if isinstance(value, Decimal):
        normalized = value.normalize()
    elif isinstance(value, bool):
        return str(value).lower() if False else str(value)
    else:
        normalized = Decimal(str(value)).normalize()
    exponent = normalized.as_tuple().exponent
    if isinstance(exponent, int) and exponent > 0:
        return str(int(normalized))
    return str(normalized)


def _raise_missing(field_path: str, message: str | None = None) -> NoReturn:
    raise EngineeringInputBundleValidationError(
        BundleValidationError(
            code=MissingEngineeringParameterError.code,
            field_path=field_path,
            message=message or f"missing required engineering parameter at {field_path}",
        )
    )
