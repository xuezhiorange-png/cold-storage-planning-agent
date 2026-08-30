"""Shared in-memory lineage bind semantics for preview and workbench.

Reuses the same field-copy rules as Transaction B lineage without SQLAlchemy or
calculator imports. Callers translate :class:`LineageBindFailure` to their own
error types.

V1.5 envelope geometry (demo / unverified / requires_review) lives here, not in
``cooling_load.py``: roof equals floor; wall is square-plan
``room_height × 4 × √floor_area``. Missing room height fails closed.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from cold_storage.modules.projects.application.operator_process_input import (
    TEMPERATURE_BAND_TO_LEVEL,
)

SQUARE_PLAN_WALL_SIDES = Decimal("4")
ENVELOPE_GEOMETRY_SOURCE_TYPE = "demo"
ENVELOPE_GEOMETRY_VALIDITY_STATUS = "unverified"
ENVELOPE_GEOMETRY_REQUIRES_REVIEW = True


class LineageBindFailure(Exception):
    """Typed bind failure. Callers map this onto Transaction B or Aily errors."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        field_path: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field_path = field_path
        self.details = dict(details or {})


def decimalize(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def square_plan_wall_area_m2(*, floor_area_m2: Decimal, room_height_m: Decimal) -> Decimal:
    """Demo square-plan wall area: height × 4 × √floor. Not the cooling kernel."""
    return room_height_m * SQUARE_PLAN_WALL_SIDES * floor_area_m2.sqrt()


def bind_cooling_identity_and_plan_area_from_zone(
    *,
    zone_payload: Mapping[str, Any],
    cooling_inputs: dict[str, Any],
) -> None:
    """Bind zone required_area_m2 into cooling floor/zone/roof/wall areas."""
    zones_raw = zone_payload.get("zones")
    if not isinstance(zones_raw, (list, tuple)) or not zones_raw:
        raise LineageBindFailure(
            code="UPSTREAM_LINEAGE_BIND_FAILED",
            message="cooling lineage binding requires zone-plan zones",
            field_path="zone.result_snapshot.zones",
            details={"reason": "missing_zone_zones"},
        )
    cooling_zones = cooling_inputs.get("zones")
    if not isinstance(cooling_zones, (list, tuple)):
        raise LineageBindFailure(
            code="UPSTREAM_LINEAGE_BIND_FAILED",
            message="cooling lineage binding requires cooling_load zones",
            field_path="cooling_load_inputs.zones",
        )
    templates_by_code: dict[str, dict[str, Any]] = {}
    for template in cooling_zones:
        if not isinstance(template, dict):
            continue
        expected = template.get("_assembler_expected_zone_code") or template.get("zone_code")
        if expected:
            templates_by_code[str(expected)] = template
    bound_zones: list[dict[str, Any]] = []
    for zone in zones_raw:
        if not isinstance(zone, dict):
            continue
        temperature_band = str(zone.get("temperature_band", ""))
        if temperature_band == "常温":
            continue
        zone_code = zone.get("zone_code")
        if zone_code is None:
            raise LineageBindFailure(
                code="UPSTREAM_LINEAGE_BIND_FAILED",
                message="cooling lineage binding requires zone_code on zone-plan zones",
                field_path="zone.result_snapshot.zones[].zone_code",
                details={"zone": zone},
            )
        zone_code_str = str(zone_code)
        temperature_level = TEMPERATURE_BAND_TO_LEVEL.get(temperature_band)
        if temperature_level is None:
            raise LineageBindFailure(
                code="UPSTREAM_LINEAGE_BIND_FAILED",
                message=(
                    "cooling lineage binding could not map temperature_band "
                    f"{temperature_band!r} to TemperatureLevel"
                ),
                field_path="cooling_load_inputs.zones[].temperature_level",
                details={"temperature_band": temperature_band, "zone_code": zone_code_str},
            )
        template = templates_by_code.get(zone_code_str)
        if template is None:
            raise LineageBindFailure(
                code="UPSTREAM_LINEAGE_BIND_FAILED",
                message=(
                    f"cooling lineage binding could not match zone-plan zone_code {zone_code_str!r}"
                ),
                field_path="cooling_load_inputs.zones[].zone_code",
                details={
                    "zone_code": zone_code_str,
                    "available_zone_codes": sorted(templates_by_code),
                },
            )
        required_area = zone.get("required_area_m2")
        if required_area is None:
            raise LineageBindFailure(
                code="UPSTREAM_LINEAGE_BIND_FAILED",
                message="cooling lineage binding requires required_area_m2 on zone-plan zones",
                field_path="zone.result_snapshot.zones[].required_area_m2",
                details={"zone_code": zone_code_str},
            )
        bound_zone = dict(template)
        bound_zone["zone_code"] = zone_code_str
        bound_zone["zone_name"] = str(zone.get("zone_name", ""))
        bound_zone["temperature_level"] = temperature_level
        area_text = str(decimalize(required_area))
        floor_area = decimalize(required_area)
        room_height = _require_positive_room_height(
            bound_zone.get("room_height"),
            zone_code=zone_code_str,
        )
        wall_area = square_plan_wall_area_m2(
            floor_area_m2=floor_area,
            room_height_m=room_height,
        )
        bound_zone["zone_area"] = area_text
        bound_zone["floor_area"] = area_text
        bound_zone["roof_area"] = area_text
        bound_zone["wall_area"] = str(wall_area)
        bound_zone["envelope_geometry_source_type"] = ENVELOPE_GEOMETRY_SOURCE_TYPE
        bound_zone["envelope_geometry_validity_status"] = ENVELOPE_GEOMETRY_VALIDITY_STATUS
        bound_zone["envelope_geometry_requires_review"] = ENVELOPE_GEOMETRY_REQUIRES_REVIEW
        bound_zone.pop("_assembler_expected_zone_code", None)
        bound_zones.append(bound_zone)
    if not bound_zones:
        raise LineageBindFailure(
            code="UPSTREAM_LINEAGE_BIND_FAILED",
            message="cooling lineage binding requires at least one refrigerated zone",
            field_path="cooling_load_inputs.zones",
            details={"reason": "no_refrigerated_zones"},
        )
    cooling_inputs["zones"] = bound_zones


def _require_positive_room_height(value: Any, *, zone_code: str) -> Decimal:
    """Fail closed when catalog height is missing; do not guess 5.0 m."""
    raw = value
    if isinstance(value, Mapping) and "value" in value:
        if value.get("state") == "missing":
            raw = None
        else:
            raw = value.get("value")
    if raw is None or raw == "":
        raise LineageBindFailure(
            code="UPSTREAM_LINEAGE_BIND_FAILED",
            message="cooling lineage binding requires room_height on refrigerated zones",
            field_path="cooling_load_inputs.zones[].room_height",
            details={"zone_code": zone_code, "reason": "missing_room_height"},
        )
    try:
        height = decimalize(raw)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise LineageBindFailure(
            code="UPSTREAM_LINEAGE_BIND_FAILED",
            message="cooling lineage binding requires a numeric room_height",
            field_path="cooling_load_inputs.zones[].room_height",
            details={"zone_code": zone_code, "reason": "invalid_room_height"},
        ) from exc
    if height <= 0:
        raise LineageBindFailure(
            code="UPSTREAM_LINEAGE_BIND_FAILED",
            message="cooling lineage binding requires a positive room_height",
            field_path="cooling_load_inputs.zones[].room_height",
            details={"zone_code": zone_code, "reason": "non_positive_room_height"},
        )
    return height


def bind_power_compressor_from_equipment(
    *,
    equipment_payload: Mapping[str, Any],
    power_inputs: dict[str, Any],
    captured_compressor_kw_e: str | None = None,
) -> str:
    """Bind equipment electrical compressor kW(e) onto installed-power inputs."""
    compressor_power = captured_compressor_kw_e
    if compressor_power is None:
        electrical = equipment_payload.get("total_compressor_input_power_kw_e")
        if electrical is not None:
            compressor_power = str(decimalize(electrical))
    if compressor_power is None:
        raise LineageBindFailure(
            code="UPSTREAM_LINEAGE_BIND_FAILED",
            message="power lineage binding requires equipment total_compressor_input_power_kw_e",
            field_path="equipment.result_snapshot.total_compressor_input_power_kw_e",
        )
    power_inputs["compressor_input_power_kw_e"] = compressor_power
    return compressor_power


def bind_investment_from_zone_and_power(
    *,
    zone_payload: Mapping[str, Any],
    power_payload: Mapping[str, Any],
    investment_inputs: dict[str, Any],
    operator_minimal: bool = True,
) -> None:
    """Bind zone totals and installed power into investment inputs."""
    total_area = zone_payload.get("total_area_m2") or zone_payload.get("total_required_area_m2")
    if total_area is not None:
        investment_inputs["total_area_m2"] = decimalize(total_area)
    position_count = sum_position_count(zone_payload)
    if position_count is not None:
        investment_inputs["position_count"] = position_count
    total_power = power_payload.get("total_installed_power_kw_e")
    if total_power is not None:
        investment_inputs["total_power_kw"] = decimalize(total_power)
    if operator_minimal:
        refrigerated_area = sum_required_area_by_bands(
            zone_payload,
            ("8~10℃", "1~3℃"),
        )
        frozen_area = sum_required_area_by_bands(zone_payload, ("-18℃",))
        if refrigerated_area is not None:
            investment_inputs["refrigerated_area_m2"] = decimalize(refrigerated_area)
        if frozen_area is not None:
            investment_inputs["frozen_area_m2"] = decimalize(frozen_area)


def sum_position_count(zone_payload: Mapping[str, Any]) -> int | None:
    zones = zone_payload.get("zones")
    if not isinstance(zones, (list, tuple)):
        return None
    total = 0
    found = False
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        count = zone.get("position_count")
        if count is None:
            continue
        total += int(count)
        found = True
    return total if found else None


def sum_required_area_by_bands(
    zone_payload: Mapping[str, Any],
    bands: tuple[str, ...],
) -> Decimal | None:
    zones = zone_payload.get("zones")
    if not isinstance(zones, (list, tuple)):
        return None
    total = Decimal("0")
    found = False
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        band = str(zone.get("temperature_band", ""))
        if band not in bands:
            continue
        area = zone.get("required_area_m2")
        if area is None:
            continue
        total += decimalize(area)
        found = True
    return total if found else None
