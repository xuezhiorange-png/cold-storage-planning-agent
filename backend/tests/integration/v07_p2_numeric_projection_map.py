"""Test-only numeric projection map for V0.7 P2 cross-consumer consistency.

Mirrors report-domain v1 projection intent without importing private
report infrastructure helpers. Mapping lives in tests only — not in Vue
or report templates.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from cold_storage.modules.orchestration.domain.consumer_bindings import (
    CALCULATOR_NAME_TO_STAGE,
    STAGE_TO_CALCULATOR_NAME,
)

# section_key → list of (snapshot_field, aliases, report_field_path)
_NUMERIC_PROJECTIONS: dict[str, tuple[tuple[str, tuple[str, ...], str], ...]] = {
    "throughput_inventory_area": (
        ("daily_inbound_mass_kg", (), "daily_inbound_mass_kg"),
        ("total_area_m2", (), "total_area_m2"),
        ("storage_capacity_kg", (), "storage_capacity_kg"),
    ),
    "cooling_load": (("total_cooling_load_kw", (), "total_design_refrigeration_load.value"),),
    "equipment_selection": (
        (
            "compressor_installed_capacity_kw",
            ("compressor_capacity_kw",),
            "total_compressor_capacity.value",
        ),
        (
            "condenser_heat_rejection_capacity_kw",
            ("condenser_heat_rejection_kw",),
            "condenser_heat_rejection.value",
        ),
    ),
    "electrical_and_energy": (
        (
            "total_installed_power_kw_e",
            ("total_installed_power_kw",),
            "total_installed_power.value",
        ),
    ),
    "investment_estimate": (("total_investment_cny", (), "total_investment"),),
}

_CALCULATOR_TO_SECTION: dict[str, str] = {
    "cold_room_zone_plan": "throughput_inventory_area",
    "cooling_load": "cooling_load",
    "equipment": "equipment_selection",
    "installed_power": "electrical_and_energy",
    "investment_estimate": "investment_estimate",
}


def _resolve_snapshot_field(snapshot: dict[str, Any], field: str, aliases: tuple[str, ...]) -> Any:
    present: list[str] = []
    for candidate in (field, *aliases):
        if candidate in snapshot:
            present.append(candidate)
    if not present:
        raise KeyError(f"no snapshot field among {field!r} aliases {aliases!r}")
    if len(present) > 1:
        raise ValueError(f"conflicting snapshot fields: {present!r}")
    return snapshot[present[0]]


def _coerce_decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise TypeError("bool is not numeric")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("empty string")
        try:
            return Decimal(stripped)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"non-decimal string: {value!r}") from exc
    raise TypeError(f"unsupported numeric type: {type(value).__name__}")


def _read_report_path(report_data: dict[str, Any], dotted_path: str) -> Any:
    cursor: Any = report_data
    for part in dotted_path.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            raise KeyError(f"missing report path segment {part!r} in {dotted_path!r}")
        cursor = cursor[part]
    return cursor


def extract_snapshot_numerics(calculator_name: str, snapshot: dict[str, Any]) -> dict[str, Decimal]:
    section_key = _CALCULATOR_TO_SECTION[calculator_name]
    extracted: dict[str, Decimal] = {}
    for field, aliases, report_path in _NUMERIC_PROJECTIONS[section_key]:
        try:
            raw = _resolve_snapshot_field(snapshot, field, aliases)
        except KeyError:
            continue
        extracted[report_path] = _coerce_decimal(raw)
    return extracted


def extract_report_numerics(section_key: str, report_data: dict[str, Any]) -> dict[str, Decimal]:
    extracted: dict[str, Decimal] = {}
    for _field, _aliases, report_path in _NUMERIC_PROJECTIONS[section_key]:
        try:
            raw = _read_report_path(report_data, report_path)
        except KeyError:
            continue
        extracted[report_path] = _coerce_decimal(raw)
    return extracted


def assert_snapshot_report_numeric_parity(
    *,
    calculator_name: str,
    snapshot: dict[str, Any],
    report_data: dict[str, Any],
) -> None:
    section_key = _CALCULATOR_TO_SECTION[calculator_name]
    snapshot_values = extract_snapshot_numerics(calculator_name, snapshot)
    report_values = extract_report_numerics(section_key, report_data)
    for path, snapshot_decimal in snapshot_values.items():
        assert path in report_values, f"{calculator_name}: report missing projected field {path!r}"
        assert snapshot_decimal == report_values[path], (
            f"{calculator_name}: numeric drift at {path!r}: "
            f"snapshot={snapshot_decimal!r} report={report_values[path]!r}"
        )


def stage_order() -> tuple[str, ...]:
    return tuple(STAGE_TO_CALCULATOR_NAME.keys())


def calculator_for_stage(stage: str) -> str:
    return STAGE_TO_CALCULATOR_NAME[stage]


def stage_for_calculator(calculator_name: str) -> str:
    return CALCULATOR_NAME_TO_STAGE[calculator_name]
