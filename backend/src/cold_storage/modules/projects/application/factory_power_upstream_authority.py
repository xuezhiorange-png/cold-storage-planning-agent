"""V2.1 P1 factory-power upstream authority adapter.

This application boundary binds the canonical ``cold_room_zone_plan`` result
to the explicit area authorities required by the existing V2.0 factory-power
calculator.  It owns no factory-power formulas: after validation it forwards
the original canonical zone rows to the calculations domain.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import NoReturn

from cold_storage.modules.calculations.domain.factory_power_estimation import (
    FactoryPowerEstimationResult,
    calculate_factory_power_estimation_from_mapping,
)
from cold_storage.modules.projects.application.operator_process_input import (
    REFRIGERATED_ZONE_REGISTRY,
)

ZONE_PLAN_CALCULATOR_ID = "cold_room_zone_plan"
ZONE_PLAN_CALCULATOR_VERSION = "1.0.0"
ZONE_PLAN_CALCULATOR_IDENTITY = f"{ZONE_PLAN_CALCULATOR_ID}@{ZONE_PLAN_CALCULATOR_VERSION}"
AREA_QUANTUM = Decimal("0.01")

EXPECTED_FACTORY_ZONE_CODES: tuple[str, ...] = (
    "office",
    "changing_room",
    "primary_precooling_room",
    "secondary_precooling_room",
    "raw_fruit_buffer",
    "sorting_packaging_room",
    "coating_room",
    "finished_goods_room",
    "secondary_fruit_buffer",
    "frozen_fruit_room",
    "packaging_material_storage",
    "shipping_channel",
)
EXPECTED_FACTORY_ZONE_CODE_SET = frozenset(EXPECTED_FACTORY_ZONE_CODES)
REFRIGERATED_ZONE_CODES: tuple[str, ...] = tuple(
    str(zone_code) for zone_code, _zone_name, _temperature_band in REFRIGERATED_ZONE_REGISTRY
)


class FactoryPowerUpstreamAuthorityError(ValueError):
    """Structured fail-closed error raised before V2.0 calculation."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.code = code
        self.details = dict(details or {})
        super().__init__(message)

    def to_blocker(self) -> dict[str, object]:
        return {
            "success": False,
            "blocker": {
                "code": self.code,
                "message": str(self),
                "details": dict(self.details),
            },
        }


@dataclass(frozen=True, slots=True)
class FactoryPowerUpstreamAuthority:
    """Validated area authorities and the unchanged canonical zone rows."""

    factory_area_m2: Decimal
    cold_storage_area_m2: Decimal
    zones: tuple[Mapping[str, object], ...]

    def to_calculator_mapping(self) -> dict[str, object]:
        """Build only the payload required by the existing V2.0 calculator.

        V1.9 serializes ``cooling_estimation_basis`` as a structured provenance
        mapping, while the unchanged V2.0 input boundary accepts its optional
        representation as text.  The deterministic JSON text below preserves
        that provenance; it does not derive, replace, or default any authority
        field.
        """
        return {
            "factory_area_m2": self.factory_area_m2,
            "cold_storage_area_m2": self.cold_storage_area_m2,
            "zone_plan": {
                "result": {
                    "zones": [_calculator_zone_row(zone) for zone in self.zones],
                }
            },
        }


def _fail(code: str, message: str, **details: object) -> NoReturn:
    raise FactoryPowerUpstreamAuthorityError(code, message, details)


def _require_canonical_zone_plan(
    zone_plan_snapshot: Mapping[str, object],
) -> tuple[Mapping[str, object], Sequence[object]]:
    if zone_plan_snapshot.get("success") is not True:
        _fail(
            "ZONE_PLAN_NOT_SUCCESSFUL",
            "canonical zone-plan authority must be successful",
            source_calculator_identity=ZONE_PLAN_CALCULATOR_IDENTITY,
        )

    if (
        zone_plan_snapshot.get("calculator_name") != ZONE_PLAN_CALCULATOR_ID
        or zone_plan_snapshot.get("calculator_version") != ZONE_PLAN_CALCULATOR_VERSION
    ):
        _fail(
            "ZONE_PLAN_CALCULATOR_IDENTITY_MISMATCH",
            "zone-plan authority calculator identity is not cold_room_zone_plan@1.0.0",
            expected=ZONE_PLAN_CALCULATOR_IDENTITY,
            actual=(
                f"{zone_plan_snapshot.get('calculator_name')}@"
                f"{zone_plan_snapshot.get('calculator_version')}"
            ),
        )

    for field_name in ("factory_area_m2", "cold_storage_area_m2"):
        if field_name in zone_plan_snapshot:
            _fail(
                "INVALID_ZONE_PLAN_AUTHORITY",
                "zone-plan snapshot cannot supply downstream area authority",
                field=field_name,
            )
    if "refrigerated_area_m2" in zone_plan_snapshot:
        _fail(
            "REFRIGERATED_AREA_M2_FORBIDDEN_AS_AUTHORITY",
            "refrigerated_area_m2 cannot replace canonical zone rows",
            field="refrigerated_area_m2",
        )

    result = zone_plan_snapshot.get("result")
    if not isinstance(result, Mapping):
        _fail(
            "INVALID_ZONE_PLAN_AUTHORITY",
            "successful zone-plan snapshot must contain a result mapping",
            source_path="zone_plan.result",
        )
    for field_name in ("factory_area_m2", "cold_storage_area_m2"):
        if field_name in result:
            _fail(
                "INVALID_ZONE_PLAN_AUTHORITY",
                "zone-plan result cannot supply downstream area authority",
                source_path=f"zone_plan.result.{field_name}",
            )
    if "refrigerated_area_m2" in result:
        _fail(
            "REFRIGERATED_AREA_M2_FORBIDDEN_AS_AUTHORITY",
            "refrigerated_area_m2 cannot replace canonical zone rows",
            source_path="zone_plan.result.refrigerated_area_m2",
        )

    rows = result.get("zones")
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        _fail(
            "INVALID_ZONE_PLAN_AUTHORITY",
            "zone-plan authority must contain result.zones[]",
            source_path="zone_plan.result.zones[]",
        )
    return result, rows


def _parse_zone_area(row: Mapping[str, object], *, zone_code: str) -> Decimal:
    if "required_area_m2" not in row:
        _fail(
            "MISSING_ZONE_REQUIRED_AREA",
            "canonical zone row must contain required_area_m2",
            zone_code=zone_code,
            source_path=f"zone_plan.result.zones[{zone_code}].required_area_m2",
        )
    raw_value = row["required_area_m2"]
    if raw_value is None or isinstance(raw_value, bool):
        _fail(
            "INVALID_ZONE_REQUIRED_AREA",
            "required_area_m2 must be a finite non-negative number",
            zone_code=zone_code,
            value=repr(raw_value),
        )
    try:
        value = raw_value if isinstance(raw_value, Decimal) else Decimal(str(raw_value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FactoryPowerUpstreamAuthorityError(
            "INVALID_ZONE_REQUIRED_AREA",
            "required_area_m2 must be a finite non-negative number",
            {"zone_code": zone_code, "value": repr(raw_value)},
        ) from exc
    if not value.is_finite() or value < 0:
        _fail(
            "INVALID_ZONE_REQUIRED_AREA",
            "required_area_m2 must be a finite non-negative number",
            zone_code=zone_code,
            value=repr(raw_value),
        )
    return value


def _parse_total_area(result: Mapping[str, object], field_name: str) -> Decimal:
    if field_name not in result:
        _fail(
            "FACTORY_AREA_TOTAL_MISMATCH",
            "zone-plan total area cross-check field is missing",
            field=field_name,
        )
    raw_value = result[field_name]
    if raw_value is None or isinstance(raw_value, bool):
        _fail(
            "FACTORY_AREA_TOTAL_MISMATCH",
            "zone-plan total area cross-check field is invalid",
            field=field_name,
            value=repr(raw_value),
        )
    try:
        value = raw_value if isinstance(raw_value, Decimal) else Decimal(str(raw_value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FactoryPowerUpstreamAuthorityError(
            "FACTORY_AREA_TOTAL_MISMATCH",
            "zone-plan total area cross-check field is invalid",
            {"field": field_name, "value": repr(raw_value)},
        ) from exc
    if not value.is_finite() or value < 0:
        _fail(
            "FACTORY_AREA_TOTAL_MISMATCH",
            "zone-plan total area cross-check field is invalid",
            field=field_name,
            value=repr(raw_value),
        )
    return value


def _quantize_area(value: Decimal) -> Decimal:
    return value.quantize(AREA_QUANTUM, rounding=ROUND_HALF_UP)


def _calculator_zone_row(zone: Mapping[str, object]) -> dict[str, object]:
    """Preserve a zone row while adapting V1.9 provenance representation."""
    copied = deepcopy(dict(zone))
    basis = copied.get("cooling_estimation_basis")
    if isinstance(basis, Mapping):
        try:
            copied["cooling_estimation_basis"] = json.dumps(
                dict(basis),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            _fail(
                "INVALID_COOLING_ESTIMATION_BASIS",
                "cooling_estimation_basis must be deterministically serializable",
                zone_code=zone.get("zone_code"),
            )
    return copied


def build_factory_power_upstream_authority(
    zone_plan_snapshot: Mapping[str, object],
) -> FactoryPowerUpstreamAuthority:
    """Validate a canonical zone plan and bind both V2.1 area authorities."""
    if not isinstance(zone_plan_snapshot, Mapping):
        _fail(
            "INVALID_ZONE_PLAN_AUTHORITY",
            "canonical zone-plan authority must be a mapping",
        )

    result, rows_raw = _require_canonical_zone_plan(zone_plan_snapshot)
    rows: list[dict[str, object]] = []
    rows_by_code: dict[str, dict[str, object]] = {}
    seen_codes: set[str] = set()

    for index, raw_row in enumerate(rows_raw):
        if not isinstance(raw_row, Mapping):
            _fail(
                "ZONE_AUTHORITY_SET_MISMATCH",
                "canonical zone-plan rows must be mappings",
                index=index,
            )
        if "refrigerated_area_m2" in raw_row:
            _fail(
                "REFRIGERATED_AREA_M2_FORBIDDEN_AS_AUTHORITY",
                "refrigerated_area_m2 cannot replace canonical zone rows",
                index=index,
            )
        zone_code = raw_row.get("zone_code")
        if not isinstance(zone_code, str) or not zone_code.strip():
            _fail(
                "ZONE_AUTHORITY_SET_MISMATCH",
                "canonical zone row must contain a non-empty zone_code",
                index=index,
            )
        if zone_code in seen_codes:
            _fail(
                "DUPLICATE_ZONE_CODE",
                "canonical zone-plan zone_code is duplicated",
                zone_code=zone_code,
                index=index,
            )
        seen_codes.add(zone_code)
        copied_row = deepcopy(dict(raw_row))
        rows.append(copied_row)
        rows_by_code[zone_code] = copied_row

    if (
        len(seen_codes) != len(EXPECTED_FACTORY_ZONE_CODES)
        or seen_codes != EXPECTED_FACTORY_ZONE_CODE_SET
    ):
        _fail(
            "ZONE_AUTHORITY_SET_MISMATCH",
            "canonical zone-plan must contain the exact 12-zone authority set",
            expected_zone_codes=list(EXPECTED_FACTORY_ZONE_CODES),
            actual_zone_codes=sorted(seen_codes),
        )

    area_by_code = {
        zone_code: _parse_zone_area(rows_by_code[zone_code], zone_code=zone_code)
        for zone_code in EXPECTED_FACTORY_ZONE_CODES
    }

    registry_by_code = {
        str(zone_code): str(temperature_band)
        for zone_code, _zone_name, temperature_band in REFRIGERATED_ZONE_REGISTRY
    }
    if len(registry_by_code) != len(REFRIGERATED_ZONE_REGISTRY):
        _fail(
            "ZONE_AUTHORITY_SET_MISMATCH",
            "REFRIGERATED_ZONE_REGISTRY contains duplicate zone codes",
        )
    for zone_code, expected_temperature_band in registry_by_code.items():
        if zone_code not in rows_by_code:
            _fail(
                "ZONE_AUTHORITY_SET_MISMATCH",
                "REFRIGERATED_ZONE_REGISTRY zone is absent from canonical zone plan",
                zone_code=zone_code,
            )
        actual_temperature_band = rows_by_code[zone_code].get("temperature_band")
        if actual_temperature_band != expected_temperature_band:
            _fail(
                "REFRIGERATED_ZONE_TEMPERATURE_MISMATCH",
                "refrigerated zone temperature_band does not match the runtime registry",
                zone_code=zone_code,
                expected=expected_temperature_band,
                actual=actual_temperature_band,
            )

    derived_factory_area = _quantize_area(sum(area_by_code.values(), Decimal("0")))
    for field_name in ("total_required_area_m2", "total_area_m2"):
        actual_total = _quantize_area(_parse_total_area(result, field_name))
        if actual_total != derived_factory_area:
            _fail(
                "FACTORY_AREA_TOTAL_MISMATCH",
                "zone-plan total area does not match the exact zone-row sum",
                field=field_name,
                expected=str(derived_factory_area),
                actual=str(actual_total),
            )

    derived_cold_storage_area = _quantize_area(
        sum(
            (area_by_code[zone_code] for zone_code in registry_by_code),
            Decimal("0"),
        )
    )
    return FactoryPowerUpstreamAuthority(
        factory_area_m2=derived_factory_area,
        cold_storage_area_m2=derived_cold_storage_area,
        zones=tuple(rows),
    )


def calculate_factory_power_from_zone_plan(
    zone_plan_snapshot: Mapping[str, object],
) -> FactoryPowerEstimationResult:
    """Bind canonical upstream areas, then invoke the unchanged V2.0 calculator."""
    authority = build_factory_power_upstream_authority(zone_plan_snapshot)
    return calculate_factory_power_estimation_from_mapping(authority.to_calculator_mapping())


__all__ = [
    "AREA_QUANTUM",
    "EXPECTED_FACTORY_ZONE_CODES",
    "EXPECTED_FACTORY_ZONE_CODE_SET",
    "FactoryPowerUpstreamAuthority",
    "FactoryPowerUpstreamAuthorityError",
    "REFRIGERATED_ZONE_CODES",
    "ZONE_PLAN_CALCULATOR_ID",
    "ZONE_PLAN_CALCULATOR_IDENTITY",
    "ZONE_PLAN_CALCULATOR_VERSION",
    "build_factory_power_upstream_authority",
    "calculate_factory_power_from_zone_plan",
]
