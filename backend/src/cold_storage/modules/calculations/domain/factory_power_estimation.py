"""V2.0 P1 deterministic factory-power canonical result calculator.

This module is an additive, pure calculation boundary.  It owns a typed
static registry for the V2.0 P0 rules and emits one deterministic result for
the future workbench/report consumers to read.  It deliberately has no
database, network, ORM, model SDK, or document-parsing dependency.

All arithmetic is performed with :class:`decimal.Decimal`.  The serialized
result uses canonical base-10 strings for power values so repeated replays do
not depend on binary floating-point representation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from types import MappingProxyType
from typing import NoReturn

from cold_storage.modules.calculations.domain.errors import CoreCalculationError

CALCULATOR_ID = "factory_power_estimation"
CALCULATOR_VERSION = "2.0.0-p1"
CALCULATOR_IDENTITY = f"{CALCULATOR_ID}@{CALCULATOR_VERSION}"
RESULT_SCHEMA_VERSION = "2.0.0-p1"
P0_CONTRACT_TASK_ID = "V20_P0_FACTORY_POWER_ESTIMATION_AND_PRESENTATION_CONTRACT_R1"
POWER_UNIT = "kW"

POOL_A = "POOL_A"
POOL_B = "POOL_B"
POOL_C = "POOL_C"
SUPPORTED_POOLS = frozenset({POOL_A, POOL_B, POOL_C})
AMBIENT_TEMPERATURE_BAND = "常温"

MAIN_SYSTEM_ZONE_CODES = (
    "primary_precooling_room",
    "secondary_precooling_room",
    "raw_fruit_buffer",
    "sorting_packaging_room",
    "coating_room",
    "finished_goods_room",
)
DEDICATED_SYSTEM_ZONE_CODES = (
    "frozen_fruit_room",
    "secondary_fruit_buffer",
    "shipping_channel",
)


@dataclass(frozen=True, slots=True)
class FactoryAreaBand:
    """One inclusive/exclusive factory-area band from the P0 matrix."""

    code: str
    lower_bound_exclusive_m2: Decimal | None
    upper_bound_inclusive_m2: Decimal | None


FACTORY_AREA_BANDS = (
    FactoryAreaBand("SMALL", None, Decimal("2500")),
    FactoryAreaBand("MEDIUM", Decimal("2500"), Decimal("5000")),
    FactoryAreaBand("LARGE", Decimal("5000"), None),
)


@dataclass(frozen=True, slots=True)
class PrecoolingConfiguration:
    """The final-scheme geometry required by a pre-cooling zone."""

    scheme_id: str
    positions_per_room: int
    air_coolers_per_room: int
    positions_per_air_cooler: int


PRECOOLING_CONFIGURATIONS: Mapping[str, PrecoolingConfiguration] = MappingProxyType(
    {
        "6_position": PrecoolingConfiguration("6_position", 6, 2, 3),
        "8_position": PrecoolingConfiguration("8_position", 8, 2, 4),
    }
)


@dataclass(frozen=True, slots=True)
class ZoneAirCoolerRule:
    """Static V2.0 rule for one refrigerated zone's air coolers."""

    zone_code: str
    quantity_basis: str
    quantity_formula: str
    motor_kw_per_unit: Decimal
    defrost_kw_per_unit: Decimal
    motor_pool: str
    defrost_pool: str
    source_field: str | None = None
    raw_count_formula: str | None = None
    fixed_quantity: int | None = None
    area_denominator_m2: Decimal | None = None
    axial_fans_per_position: int | None = None
    axial_fan_kw_per_unit: Decimal | None = None
    axial_fan_quantity_formula: str | None = None


def _zone_rule(
    *,
    zone_code: str,
    quantity_basis: str,
    quantity_formula: str | None = None,
    motor_kw_per_unit: str,
    defrost_kw_per_unit: str,
    source_field: str | None = None,
    raw_count_formula: str | None = None,
    fixed_quantity: int | None = None,
    area_denominator_m2: str | None = None,
    axial_fans_per_position: int | None = None,
    axial_fan_kw_per_unit: str | None = None,
    axial_fan_quantity_formula: str | None = None,
) -> ZoneAirCoolerRule:
    if area_denominator_m2 is not None:
        area_formula = f"ceil(required_area_m2 / {area_denominator_m2})"
        if quantity_formula is None:
            quantity_formula = area_formula
        if quantity_formula == "next_even_integer_greater_than_or_equal_to(raw_count)":
            raw_count_formula = raw_count_formula or area_formula
    if quantity_formula is None:
        raise ValueError("quantity_formula is required for non-area rules")
    return ZoneAirCoolerRule(
        zone_code=zone_code,
        quantity_basis=quantity_basis,
        quantity_formula=quantity_formula,
        motor_kw_per_unit=Decimal(motor_kw_per_unit),
        defrost_kw_per_unit=Decimal(defrost_kw_per_unit),
        motor_pool=POOL_B,
        defrost_pool=POOL_A,
        source_field=source_field,
        raw_count_formula=raw_count_formula,
        fixed_quantity=fixed_quantity,
        area_denominator_m2=(
            Decimal(area_denominator_m2) if area_denominator_m2 is not None else None
        ),
        axial_fans_per_position=axial_fans_per_position,
        axial_fan_kw_per_unit=(
            Decimal(axial_fan_kw_per_unit) if axial_fan_kw_per_unit is not None else None
        ),
        axial_fan_quantity_formula=axial_fan_quantity_formula,
    )


ZONE_AIR_COOLER_RULES: Mapping[str, ZoneAirCoolerRule] = MappingProxyType(
    {
        "primary_precooling_room": _zone_rule(
            zone_code="primary_precooling_room",
            quantity_basis="PRECOOLING_SCHEME",
            quantity_formula="room_count * 2",
            motor_kw_per_unit="6.6",
            defrost_kw_per_unit="19.6",
            axial_fans_per_position=4,
            axial_fan_kw_per_unit="0.5",
            axial_fan_quantity_formula="final_position_count * 4",
        ),
        "secondary_precooling_room": _zone_rule(
            zone_code="secondary_precooling_room",
            quantity_basis="PRECOOLING_SCHEME",
            quantity_formula="room_count * 2",
            motor_kw_per_unit="3.0",
            defrost_kw_per_unit="22.0",
            axial_fans_per_position=4,
            axial_fan_kw_per_unit="0.5",
            axial_fan_quantity_formula="final_position_count * 4",
        ),
        "raw_fruit_buffer": _zone_rule(
            zone_code="raw_fruit_buffer",
            quantity_basis="ZONE_AREA",
            source_field="required_area_m2",
            area_denominator_m2="80",
            motor_kw_per_unit="0.5",
            defrost_kw_per_unit="4.0",
        ),
        "sorting_packaging_room": _zone_rule(
            zone_code="sorting_packaging_room",
            quantity_basis="ZONE_AREA",
            quantity_formula="next_even_integer_greater_than_or_equal_to(raw_count)",
            source_field="required_area_m2",
            area_denominator_m2="70",
            motor_kw_per_unit="0.5",
            defrost_kw_per_unit="4.0",
        ),
        "coating_room": _zone_rule(
            zone_code="coating_room",
            quantity_basis="ZONE_AREA",
            source_field="required_area_m2",
            area_denominator_m2="70",
            motor_kw_per_unit="1.5",
            defrost_kw_per_unit="6.0",
        ),
        "finished_goods_room": _zone_rule(
            zone_code="finished_goods_room",
            quantity_basis="ZONE_AREA",
            source_field="required_area_m2",
            area_denominator_m2="70",
            motor_kw_per_unit="1.5",
            defrost_kw_per_unit="6.0",
        ),
        "secondary_fruit_buffer": _zone_rule(
            zone_code="secondary_fruit_buffer",
            quantity_basis="FIXED",
            quantity_formula="1",
            fixed_quantity=1,
            motor_kw_per_unit="1.0",
            defrost_kw_per_unit="8.0",
        ),
        "frozen_fruit_room": _zone_rule(
            zone_code="frozen_fruit_room",
            quantity_basis="FIXED",
            quantity_formula="1",
            fixed_quantity=1,
            motor_kw_per_unit="3.0",
            defrost_kw_per_unit="26.0",
        ),
        "shipping_channel": _zone_rule(
            zone_code="shipping_channel",
            quantity_basis="ZONE_AREA",
            source_field="required_area_m2",
            area_denominator_m2="50",
            motor_kw_per_unit="2.0",
            defrost_kw_per_unit="12.0",
        ),
    }
)


@dataclass(frozen=True, slots=True)
class PublicEquipmentRule:
    """Static public-equipment rule from the P0 matrix."""

    equipment_code: str
    quantity_by_band: Mapping[str, int] | None
    unit_power_kw: Decimal | None
    pool: str
    fixed_quantity: int | None = None
    fixed_installed_power_kw: Decimal | None = None


def _band_quantities(values: Mapping[str, int]) -> Mapping[str, int]:
    return MappingProxyType(dict(values))


PUBLIC_EQUIPMENT_RULES: Mapping[str, PublicEquipmentRule] = MappingProxyType(
    {
        "electric_sliding_door": PublicEquipmentRule(
            "electric_sliding_door",
            _band_quantities({"SMALL": 15, "MEDIUM": 30, "LARGE": 50}),
            Decimal("0.5"),
            POOL_B,
        ),
        "fast_rolling_door": PublicEquipmentRule(
            "fast_rolling_door",
            _band_quantities({"SMALL": 6, "MEDIUM": 10, "LARGE": 16}),
            Decimal("0.5"),
            POOL_B,
        ),
        "air_curtain": PublicEquipmentRule(
            "air_curtain",
            _band_quantities({"SMALL": 4, "MEDIUM": 8, "LARGE": 12}),
            Decimal("0.4"),
            POOL_B,
        ),
        "lift_door_and_loading_platform": PublicEquipmentRule(
            "lift_door_and_loading_platform",
            _band_quantities({"SMALL": 2, "MEDIUM": 3, "LARGE": 4}),
            Decimal("3.0"),
            POOL_B,
        ),
        "ozone_and_humidification": PublicEquipmentRule(
            "ozone_and_humidification",
            None,
            None,
            POOL_B,
            fixed_quantity=1,
            fixed_installed_power_kw=Decimal("30.0"),
        ),
        "floor_heating_cable": PublicEquipmentRule(
            "floor_heating_cable",
            None,
            None,
            POOL_B,
            fixed_quantity=1,
            fixed_installed_power_kw=Decimal("4.0"),
        ),
    }
)


@dataclass(frozen=True, slots=True)
class LightingRule:
    """Static lighting rule whose fields directly drive the calculation."""

    lighting_code: str
    area_source_field: str
    area_divisor_m2: Decimal
    unit_power_kw: Decimal
    pool: str
    quantity_formula: str
    installed_power_formula: str
    forbidden_area_substitute: str


def _lighting_rule(
    *,
    lighting_code: str,
    area_divisor_m2: str,
    unit_power_kw: str,
) -> LightingRule:
    divisor = Decimal(area_divisor_m2)
    unit_power = Decimal(unit_power_kw)
    return LightingRule(
        lighting_code=lighting_code,
        area_source_field="cold_storage_area_m2",
        area_divisor_m2=divisor,
        unit_power_kw=unit_power,
        pool=POOL_B,
        quantity_formula=f"ceil(cold_storage_area_m2 / {area_divisor_m2})",
        installed_power_formula=f"quantity * {unit_power_kw}",
        forbidden_area_substitute="factory_area_m2",
    )


LIGHTING_RULES: Mapping[str, LightingRule] = MappingProxyType(
    {
        "cold_storage_lighting": _lighting_rule(
            lighting_code="cold_storage_lighting",
            area_divisor_m2="10",
            unit_power_kw="0.04",
        ),
        "uv_lighting": _lighting_rule(
            lighting_code="uv_lighting",
            area_divisor_m2="20",
            unit_power_kw="0.08",
        ),
    }
)


DEDICATED_COMPRESSOR_POWER_BY_ZONE: Mapping[str, Mapping[str, Decimal]] = MappingProxyType(
    {
        "frozen_fruit_room": MappingProxyType(
            {"SMALL": Decimal("15.0"), "MEDIUM": Decimal("25.0"), "LARGE": Decimal("40.0")}
        ),
        "secondary_fruit_buffer": MappingProxyType(
            {"SMALL": Decimal("4.0"), "MEDIUM": Decimal("6.0"), "LARGE": Decimal("8.0")}
        ),
        "shipping_channel": MappingProxyType(
            {"SMALL": Decimal("8.0"), "MEDIUM": Decimal("12.0"), "LARGE": Decimal("16.0")}
        ),
    }
)
EVAPORATIVE_CONDENSER_POWER_BY_BAND: Mapping[str, Decimal] = MappingProxyType(
    {"SMALL": Decimal("20.0"), "MEDIUM": Decimal("30.0"), "LARGE": Decimal("40.0")}
)
PRODUCTION_POWER_BY_BAND: Mapping[str, Decimal] = MappingProxyType(
    {"SMALL": Decimal("200.0"), "MEDIUM": Decimal("300.0"), "LARGE": Decimal("400.0")}
)

HISTORICAL_POOL_A_SIMULTANEITY_FACTOR = Decimal("0.30")
DEFROST_SIMULTANEOUS_USE_FACTOR = Decimal("0.20")
POOL_A_SIMULTANEITY_FACTOR = DEFROST_SIMULTANEOUS_USE_FACTOR
POOL_B_SIMULTANEITY_FACTOR_BY_BAND: Mapping[str, Decimal] = MappingProxyType(
    {"SMALL": Decimal("1.00"), "MEDIUM": Decimal("0.90"), "LARGE": Decimal("0.80")}
)
POOL_C_SIMULTANEITY_FACTOR = Decimal("0.85")
MAIN_SYSTEM_COP = Decimal("3.3")


@dataclass(frozen=True, slots=True)
class FactoryPowerSchemeInput:
    """One scheme row from a zone-plan result."""

    scheme_id: str
    room_count: int | None
    position_count: int | None
    required_area_m2: Decimal | None

    def to_dict(self) -> dict[str, object]:
        return {
            "scheme_id": self.scheme_id,
            "room_count": self.room_count,
            "position_count": self.position_count,
            "required_area_m2": _decimal_or_none(self.required_area_m2),
        }


@dataclass(frozen=True, slots=True)
class FactoryPowerZoneInput:
    """Canonical zone authority consumed by the V2 calculator."""

    zone_code: str
    temperature_band: str | None = None
    required_area_m2: Decimal | None = None
    minimum_estimated_cooling_load_kw_r: Decimal | None = None
    cooling_estimation_basis: str | None = None
    reporting_scheme_id: str | None = None
    schemes: tuple[FactoryPowerSchemeInput, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "zone_code": self.zone_code,
            "temperature_band": self.temperature_band,
            "required_area_m2": _decimal_or_none(self.required_area_m2),
            "minimum_estimated_cooling_load_kw_r": _decimal_or_none(
                self.minimum_estimated_cooling_load_kw_r
            ),
            "cooling_estimation_basis": self.cooling_estimation_basis,
            "reporting_scheme_id": self.reporting_scheme_id,
            "schemes": [scheme.to_dict() for scheme in self.schemes],
        }


@dataclass(frozen=True, slots=True)
class FactoryPowerEstimationInput:
    """Typed canonical input; both area authorities are mandatory."""

    factory_area_m2: Decimal
    cold_storage_area_m2: Decimal
    zones: tuple[FactoryPowerZoneInput, ...]


class FactoryPowerEstimationError(CoreCalculationError):
    """Structured fail-closed blocker raised by the V2 boundary."""

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
            "calculator": {
                "id": CALCULATOR_ID,
                "version": CALCULATOR_VERSION,
                "identity": CALCULATOR_IDENTITY,
            },
            "blocker": {
                "code": self.code,
                "message": str(self),
                "details": self.details,
            },
        }


@dataclass(frozen=True, slots=True)
class FactoryPowerDetail:
    """One auditable installed/coincident component in the result."""

    equipment_or_zone: str
    basis: str
    configured_quantity: int
    unit_power_kw: Decimal
    installed_power_kw: Decimal
    pool: str
    simultaneity_factor: Decimal
    coincident_power_kw: Decimal

    def to_dict(self) -> dict[str, object]:
        return {
            "equipment_or_zone": self.equipment_or_zone,
            "basis": self.basis,
            "configured_quantity": self.configured_quantity,
            "unit_power_kw": _decimal_text(self.unit_power_kw),
            "installed_power_kw": _decimal_text(self.installed_power_kw),
            "pool": self.pool,
            "simultaneity_factor": _decimal_text(self.simultaneity_factor),
            "coincident_power_kw": _decimal_text(self.coincident_power_kw),
        }


@dataclass(frozen=True, slots=True)
class FactoryPowerSummary:
    """Three-pool and total summary required by the P0 presentation contract."""

    defrost_installed_power_kw: Decimal
    defrost_coincident_power_kw: Decimal
    other_installed_power_kw: Decimal
    other_coincident_power_kw: Decimal
    production_equipment_installed_power_kw: Decimal
    production_equipment_coincident_power_kw: Decimal
    total_installed_power_kw: Decimal
    estimated_total_power_kw: Decimal

    def to_dict(self) -> dict[str, object]:
        return {
            "defrost_installed_power_kw": _decimal_text(self.defrost_installed_power_kw),
            "defrost_coincident_power_kw": _decimal_text(self.defrost_coincident_power_kw),
            "other_installed_power_kw": _decimal_text(self.other_installed_power_kw),
            "other_coincident_power_kw": _decimal_text(self.other_coincident_power_kw),
            "production_equipment_installed_power_kw": _decimal_text(
                self.production_equipment_installed_power_kw
            ),
            "production_equipment_coincident_power_kw": _decimal_text(
                self.production_equipment_coincident_power_kw
            ),
            "total_installed_power_kw": _decimal_text(self.total_installed_power_kw),
            "estimated_total_power_kw": _decimal_text(self.estimated_total_power_kw),
        }


@dataclass(frozen=True, slots=True)
class FactoryPowerEstimationResult:
    """Single deterministic backend canonical result."""

    factory_area_band: str
    input_snapshot: Mapping[str, object]
    provenance: Mapping[str, object]
    assumptions: tuple[str, ...]
    details: tuple[FactoryPowerDetail, ...]
    summary: FactoryPowerSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "result_kind": "factory_power_canonical_result",
            "success": True,
            "calculator": {
                "id": CALCULATOR_ID,
                "version": CALCULATOR_VERSION,
                "identity": CALCULATOR_IDENTITY,
            },
            "input_authority": dict(self.input_snapshot),
            "factory_area_band": self.factory_area_band,
            "unit_semantics": {
                "power_unit": POWER_UNIT,
                "energy_unit": "kWh",
                "not_energy": True,
                "not_metered_electricity": True,
                "not_daily_electricity_consumption": True,
            },
            "provenance": dict(self.provenance),
            "assumptions": list(self.assumptions),
            "review": {
                "requires_review": True,
                "status": "REQUIRES_ENGINEERING_REVIEW",
            },
            "details": [detail.to_dict() for detail in self.details],
            "summary": self.summary.to_dict(),
        }

    def canonical_json(self) -> str:
        """Serialize without timestamps or UUIDs for deterministic replay."""
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def _decimal_or_none(value: Decimal | None) -> str | None:
    return _decimal_text(value) if value is not None else None


def _fail(code: str, message: str, **details: object) -> NoReturn:
    raise FactoryPowerEstimationError(code, message, details)


def _parse_decimal(
    value: object,
    *,
    field_name: str,
    missing_code: str,
    invalid_code: str,
) -> Decimal:
    if value is None:
        _fail(missing_code, f"{field_name} is required and must be authoritative", field=field_name)
    if isinstance(value, bool):
        _fail(invalid_code, f"{field_name} must be numeric", field=field_name, value=repr(value))
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FactoryPowerEstimationError(
            invalid_code,
            f"{field_name} must be numeric",
            {"field": field_name, "value": repr(value)},
        ) from exc
    if not parsed.is_finite():
        _fail(invalid_code, f"{field_name} must be finite", field=field_name, value=repr(value))
    if parsed < 0:
        _fail(invalid_code, f"{field_name} cannot be negative", field=field_name, value=repr(value))
    return parsed


def _parse_optional_decimal(
    mapping: Mapping[str, object],
    field_name: str,
    *,
    invalid_code: str,
) -> Decimal | None:
    if field_name not in mapping or mapping[field_name] is None:
        return None
    return _parse_decimal(
        mapping[field_name],
        field_name=field_name,
        missing_code=invalid_code,
        invalid_code=invalid_code,
    )


def _parse_optional_int(
    mapping: Mapping[str, object],
    field_name: str,
    *,
    invalid_code: str,
) -> int | None:
    if field_name not in mapping or mapping[field_name] is None:
        return None
    value = mapping[field_name]
    parsed = _parse_decimal(
        value,
        field_name=field_name,
        missing_code=invalid_code,
        invalid_code=invalid_code,
    )
    if parsed != parsed.to_integral_value():
        _fail(invalid_code, f"{field_name} must be an integer", field=field_name, value=repr(value))
    return int(parsed)


def _extract_zone_rows(raw: Mapping[str, object]) -> Sequence[object]:
    if "zones" in raw:
        rows = raw["zones"]
    else:
        zone_plan = raw.get("zone_plan")
        if not isinstance(zone_plan, Mapping):
            _fail(
                "MISSING_ZONE_PLAN_AUTHORITY",
                "zone_plan.result.zones[] is required",
                source_path="zone_plan.result.zones[]",
            )
        result = zone_plan.get("result")
        if not isinstance(result, Mapping):
            _fail(
                "MISSING_ZONE_PLAN_AUTHORITY",
                "zone_plan.result.zones[] is required",
                source_path="zone_plan.result.zones[]",
            )
        rows = result.get("zones")
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        _fail(
            "INVALID_ZONE_PLAN_AUTHORITY",
            "zone_plan.result.zones[] must be a sequence",
            source_path="zone_plan.result.zones[]",
        )
    return rows


def _build_scheme(row: Mapping[str, object], index: int) -> FactoryPowerSchemeInput:
    scheme_id = row.get("scheme_id")
    if not isinstance(scheme_id, str) or not scheme_id.strip():
        _fail(
            "INVALID_PRECOOLING_SCHEME",
            "scheme_id must be a non-empty string",
            index=index,
        )
    return FactoryPowerSchemeInput(
        scheme_id=scheme_id,
        room_count=_parse_optional_int(
            row,
            "room_count",
            invalid_code="INVALID_SCHEME_ROOM_COUNT",
        ),
        position_count=_parse_optional_int(
            row,
            "position_count",
            invalid_code="INVALID_SCHEME_POSITION_COUNT",
        ),
        required_area_m2=_parse_optional_decimal(
            row,
            "required_area_m2",
            invalid_code="INVALID_SCHEME_REQUIRED_AREA",
        ),
    )


def _build_zone(row: object, index: int) -> FactoryPowerZoneInput:
    if not isinstance(row, Mapping):
        _fail("INVALID_ZONE_ROW", "zone row must be a mapping", index=index)
    zone_code = row.get("zone_code")
    if not isinstance(zone_code, str) or not zone_code.strip():
        _fail("MISSING_ZONE_CODE", "zone_code must be a non-empty string", index=index)
    schemes_raw = row.get("schemes", ())
    if isinstance(schemes_raw, (str, bytes)) or not isinstance(schemes_raw, Sequence):
        _fail(
            "INVALID_PRECOOLING_SCHEMES",
            "schemes must be a sequence",
            zone_code=zone_code,
        )
    schemes: list[FactoryPowerSchemeInput] = []
    for scheme_index, scheme_row in enumerate(schemes_raw):
        if not isinstance(scheme_row, Mapping):
            _fail(
                "INVALID_PRECOOLING_SCHEME",
                "scheme row must be a mapping",
                zone_code=zone_code,
                index=scheme_index,
            )
        schemes.append(_build_scheme(scheme_row, scheme_index))
    reporting_scheme_id = row.get("reporting_scheme_id")
    if reporting_scheme_id is not None and not isinstance(reporting_scheme_id, str):
        _fail(
            "INVALID_REPORTING_SCHEME_ID",
            "reporting_scheme_id must be a string",
            zone_code=zone_code,
        )
    temperature_band = row.get("temperature_band")
    if temperature_band is not None and not isinstance(temperature_band, str):
        _fail(
            "INVALID_ZONE_TEMPERATURE_BAND",
            "temperature_band must be a string",
            zone_code=zone_code,
        )
    cooling_estimation_basis = row.get("cooling_estimation_basis")
    if cooling_estimation_basis is not None and not isinstance(cooling_estimation_basis, str):
        _fail(
            "INVALID_COOLING_ESTIMATION_BASIS",
            "cooling_estimation_basis must be a string",
            zone_code=zone_code,
        )
    return FactoryPowerZoneInput(
        zone_code=zone_code,
        temperature_band=temperature_band,
        required_area_m2=_parse_optional_decimal(
            row,
            "required_area_m2",
            invalid_code="INVALID_REQUIRED_AREA_M2",
        ),
        minimum_estimated_cooling_load_kw_r=_parse_optional_decimal(
            row,
            "minimum_estimated_cooling_load_kw_r",
            invalid_code="INVALID_MINIMUM_ESTIMATED_COOLING_LOAD_KW_R",
        ),
        cooling_estimation_basis=cooling_estimation_basis,
        reporting_scheme_id=reporting_scheme_id,
        schemes=tuple(schemes),
    )


def build_factory_power_estimation_input(
    raw: Mapping[str, object],
) -> FactoryPowerEstimationInput:
    """Build typed input from a raw backend payload without substitutions."""
    if not isinstance(raw, Mapping):
        _fail("INVALID_CANONICAL_INPUT", "canonical input must be a mapping")
    factory_area_m2 = _parse_decimal(
        raw.get("factory_area_m2"),
        field_name="factory_area_m2",
        missing_code="MISSING_FACTORY_AREA_AUTHORITY",
        invalid_code="INVALID_FACTORY_AREA_AUTHORITY",
    )
    cold_storage_area_m2 = _parse_decimal(
        raw.get("cold_storage_area_m2"),
        field_name="cold_storage_area_m2",
        missing_code="MISSING_COLD_STORAGE_AREA_AUTHORITY",
        invalid_code="INVALID_COLD_STORAGE_AREA_AUTHORITY",
    )
    zones = tuple(_build_zone(row, index) for index, row in enumerate(_extract_zone_rows(raw)))
    calculation_input = FactoryPowerEstimationInput(
        factory_area_m2=factory_area_m2,
        cold_storage_area_m2=cold_storage_area_m2,
        zones=zones,
    )
    _validate_canonical_input(calculation_input)
    return calculation_input


def _validated_authority_decimal(
    value: object,
    *,
    field_name: str,
    missing_code: str,
    invalid_code: str,
) -> Decimal:
    if value is None:
        _fail(missing_code, f"{field_name} is required and must be authoritative", field=field_name)
    _validate_typed_decimal(value, field_name=field_name, invalid_code=invalid_code)
    assert isinstance(value, Decimal)
    return value


def _validate_typed_decimal(
    value: object,
    *,
    field_name: str,
    invalid_code: str,
) -> None:
    """Validate a Decimal field after the mapping adapter has built typed input."""
    if not isinstance(value, Decimal):
        _fail(
            invalid_code,
            f"{field_name} must be a Decimal",
            field=field_name,
            value=repr(value),
        )
    if not value.is_finite():
        _fail(
            invalid_code,
            f"{field_name} must be finite",
            field=field_name,
            value=repr(value),
        )
    if value < 0:
        _fail(
            invalid_code,
            f"{field_name} cannot be negative",
            field=field_name,
            value=repr(value),
        )


def _validate_optional_typed_decimal(
    value: object,
    *,
    field_name: str,
    invalid_code: str,
) -> None:
    if value is not None:
        _validate_typed_decimal(value, field_name=field_name, invalid_code=invalid_code)


def _validate_optional_typed_int(
    value: object,
    *,
    field_name: str,
    invalid_code: str,
) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(
            invalid_code,
            f"{field_name} must be an integer",
            field=field_name,
            value=repr(value),
        )
    if value < 0:
        _fail(
            invalid_code,
            f"{field_name} cannot be negative",
            field=field_name,
            value=repr(value),
        )


def _validate_typed_string(
    value: object,
    *,
    field_name: str,
    invalid_code: str,
    require_non_empty: bool = False,
) -> None:
    if not isinstance(value, str) or (require_non_empty and not value.strip()):
        _fail(
            invalid_code,
            f"{field_name} must be a non-empty string"
            if require_non_empty
            else f"{field_name} must be a string",
            field=field_name,
            value=repr(value),
        )


def _validate_typed_scheme(
    scheme: object,
    *,
    zone_code: str,
    index: int,
) -> None:
    if not isinstance(scheme, FactoryPowerSchemeInput):
        _fail(
            "INVALID_PRECOOLING_SCHEME",
            "typed pre-cooling scheme is required",
            zone_code=zone_code,
            index=index,
        )
    _validate_typed_string(
        scheme.scheme_id,
        field_name="scheme_id",
        invalid_code="INVALID_PRECOOLING_SCHEME",
        require_non_empty=True,
    )
    _validate_optional_typed_int(
        scheme.room_count,
        field_name="room_count",
        invalid_code="INVALID_SCHEME_ROOM_COUNT",
    )
    _validate_optional_typed_int(
        scheme.position_count,
        field_name="position_count",
        invalid_code="INVALID_SCHEME_POSITION_COUNT",
    )
    _validate_optional_typed_decimal(
        scheme.required_area_m2,
        field_name="required_area_m2",
        invalid_code="INVALID_SCHEME_REQUIRED_AREA",
    )


def _validate_typed_zone(zone: object, *, index: int) -> None:
    if not isinstance(zone, FactoryPowerZoneInput):
        _fail("INVALID_ZONE_ROW", "typed zone row is required", index=index)
    _validate_typed_string(
        zone.zone_code,
        field_name="zone_code",
        invalid_code="MISSING_ZONE_CODE",
        require_non_empty=True,
    )
    if zone.temperature_band is not None:
        _validate_typed_string(
            zone.temperature_band,
            field_name="temperature_band",
            invalid_code="INVALID_ZONE_TEMPERATURE_BAND",
        )
    _validate_optional_typed_decimal(
        zone.required_area_m2,
        field_name="required_area_m2",
        invalid_code="INVALID_REQUIRED_AREA_M2",
    )
    _validate_optional_typed_decimal(
        zone.minimum_estimated_cooling_load_kw_r,
        field_name="minimum_estimated_cooling_load_kw_r",
        invalid_code="INVALID_MINIMUM_ESTIMATED_COOLING_LOAD_KW_R",
    )
    if zone.cooling_estimation_basis is not None:
        _validate_typed_string(
            zone.cooling_estimation_basis,
            field_name="cooling_estimation_basis",
            invalid_code="INVALID_COOLING_ESTIMATION_BASIS",
        )
    if zone.reporting_scheme_id is not None:
        _validate_typed_string(
            zone.reporting_scheme_id,
            field_name="reporting_scheme_id",
            invalid_code="INVALID_REPORTING_SCHEME_ID",
            require_non_empty=True,
        )
    if not isinstance(zone.schemes, tuple):
        _fail(
            "INVALID_PRECOOLING_SCHEMES",
            "typed schemes must be a tuple",
            zone_code=zone.zone_code,
        )
    for scheme_index, scheme in enumerate(zone.schemes):
        _validate_typed_scheme(scheme, zone_code=zone.zone_code, index=scheme_index)


def _validate_canonical_input(calculation_input: object) -> None:
    """Validate every public typed field before any calculation arithmetic."""
    if not isinstance(calculation_input, FactoryPowerEstimationInput):
        _fail("INVALID_CANONICAL_INPUT", "FactoryPowerEstimationInput is required")
    _validated_authority_decimal(
        calculation_input.factory_area_m2,
        field_name="factory_area_m2",
        missing_code="MISSING_FACTORY_AREA_AUTHORITY",
        invalid_code="INVALID_FACTORY_AREA_AUTHORITY",
    )
    _validated_authority_decimal(
        calculation_input.cold_storage_area_m2,
        field_name="cold_storage_area_m2",
        missing_code="MISSING_COLD_STORAGE_AREA_AUTHORITY",
        invalid_code="INVALID_COLD_STORAGE_AREA_AUTHORITY",
    )
    if not isinstance(calculation_input.zones, tuple):
        _fail("INVALID_ZONE_PLAN_AUTHORITY", "typed zones must be a tuple")
    for index, zone in enumerate(calculation_input.zones):
        _validate_typed_zone(zone, index=index)


def _select_factory_area_band(factory_area_m2: Decimal) -> FactoryAreaBand:
    for band in FACTORY_AREA_BANDS:
        if (
            band.lower_bound_exclusive_m2 is not None
            and factory_area_m2 <= band.lower_bound_exclusive_m2
        ):
            continue
        if (
            band.upper_bound_inclusive_m2 is not None
            and factory_area_m2 > band.upper_bound_inclusive_m2
        ):
            continue
        return band
    _fail(
        "INVALID_FACTORY_AREA_AUTHORITY",
        "factory_area_m2 does not match a supported area band",
        field="factory_area_m2",
        value=_decimal_text(factory_area_m2),
    )


def _validate_zone_set(
    zones: Sequence[FactoryPowerZoneInput],
) -> Mapping[str, FactoryPowerZoneInput]:
    zone_map: dict[str, FactoryPowerZoneInput] = {}
    for index, zone in enumerate(zones):
        if not isinstance(zone, FactoryPowerZoneInput):
            _fail("INVALID_ZONE_ROW", "typed zone row is required", index=index)
        if zone.zone_code in ZONE_AIR_COOLER_RULES:
            if zone.zone_code in zone_map:
                _fail(
                    "DUPLICATE_REFRIGERATED_ZONE",
                    "refrigerated zone_code is duplicated",
                    zone_code=zone.zone_code,
                    index=index,
                )
            zone_map[zone.zone_code] = zone
        elif zone.temperature_band == AMBIENT_TEMPERATURE_BAND:
            continue
        else:
            _fail(
                "UNKNOWN_REFRIGERATED_ZONE",
                "non-ambient zone has no V2.0 air-cooler rule",
                zone_code=zone.zone_code,
                index=index,
            )
    missing = sorted(set(ZONE_AIR_COOLER_RULES) - set(zone_map))
    if missing:
        _fail(
            "MISSING_REFRIGERATED_ZONE",
            "the nine refrigerated zones are incomplete",
            missing_zone_codes=missing,
        )
    return MappingProxyType(zone_map)


def _selected_scheme(zone: FactoryPowerZoneInput) -> FactoryPowerSchemeInput:
    if not zone.reporting_scheme_id:
        _fail(
            "MISSING_REPORTING_SCHEME_ID",
            "pre-cooling zone requires reporting_scheme_id",
            zone_code=zone.zone_code,
        )
    matches = [scheme for scheme in zone.schemes if scheme.scheme_id == zone.reporting_scheme_id]
    if not matches:
        _fail(
            "UNKNOWN_REPORTING_SCHEME_ID",
            "reporting_scheme_id does not identify a supplied scheme",
            zone_code=zone.zone_code,
            reporting_scheme_id=zone.reporting_scheme_id,
        )
    if len(matches) > 1:
        _fail(
            "DUPLICATE_REPORTING_SCHEME_ID",
            "reporting_scheme_id identifies more than one scheme",
            zone_code=zone.zone_code,
            reporting_scheme_id=zone.reporting_scheme_id,
        )
    scheme = matches[0]
    configuration = PRECOOLING_CONFIGURATIONS.get(scheme.scheme_id)
    if configuration is None:
        _fail(
            "UNKNOWN_REPORTING_SCHEME_ID",
            "reporting_scheme_id is not an authorized V2.0 scheme",
            zone_code=zone.zone_code,
            reporting_scheme_id=scheme.scheme_id,
        )
    if scheme.room_count is None:
        _fail(
            "MISSING_SCHEME_ROOM_COUNT",
            "selected scheme room_count is required",
            zone_code=zone.zone_code,
            reporting_scheme_id=scheme.scheme_id,
        )
    if scheme.position_count is None:
        _fail(
            "MISSING_SCHEME_POSITION_COUNT",
            "selected scheme position_count is required",
            zone_code=zone.zone_code,
            reporting_scheme_id=scheme.scheme_id,
        )
    if scheme.required_area_m2 is None:
        _fail(
            "MISSING_SCHEME_REQUIRED_AREA",
            "selected scheme required_area_m2 is required",
            zone_code=zone.zone_code,
            reporting_scheme_id=scheme.scheme_id,
        )
    expected_positions = scheme.room_count * configuration.positions_per_room
    if scheme.position_count != expected_positions:
        _fail(
            "INVALID_SCHEME_POSITION_COUNT",
            "selected scheme position_count is inconsistent with room_count",
            zone_code=zone.zone_code,
            reporting_scheme_id=scheme.scheme_id,
            expected_position_count=expected_positions,
            actual_position_count=scheme.position_count,
        )
    return scheme


def _zone_area_quantity(rule: ZoneAirCoolerRule, zone: FactoryPowerZoneInput) -> int:
    if rule.quantity_basis == "FIXED":
        if rule.fixed_quantity is None:
            _fail(
                "INVALID_RULE_REGISTRY",
                "fixed rule has no fixed quantity",
                zone_code=rule.zone_code,
            )
        return rule.fixed_quantity
    if zone.required_area_m2 is None:
        _fail(
            "MISSING_REQUIRED_AREA_M2",
            "area-based zone requires required_area_m2",
            zone_code=zone.zone_code,
        )
    if rule.area_denominator_m2 is None:
        _fail("INVALID_RULE_REGISTRY", "area rule has no denominator", zone_code=rule.zone_code)
    raw_count = int(
        (zone.required_area_m2 / rule.area_denominator_m2).to_integral_value(rounding=ROUND_CEILING)
    )
    if rule.zone_code == "sorting_packaging_room" and raw_count % 2:
        return raw_count + 1
    return raw_count


def _required_main_cooling_load(zone: FactoryPowerZoneInput) -> Decimal:
    value = zone.minimum_estimated_cooling_load_kw_r
    if value is None:
        _fail(
            "MISSING_MINIMUM_ESTIMATED_COOLING_LOAD_KW_R",
            "main-system zone requires the V1.9 minimum estimated cooling load",
            zone_code=zone.zone_code,
            source_field="minimum_estimated_cooling_load_kw_r",
        )
    if not value.is_finite() or value < 0:
        _fail(
            "INVALID_MINIMUM_ESTIMATED_COOLING_LOAD_KW_R",
            "minimum estimated cooling load must be finite and non-negative",
            zone_code=zone.zone_code,
            source_field="minimum_estimated_cooling_load_kw_r",
            value=repr(value),
        )
    return value


def _pool_factor(pool: str, band_code: str) -> Decimal:
    if pool == POOL_A:
        return POOL_A_SIMULTANEITY_FACTOR
    if pool == POOL_B:
        return POOL_B_SIMULTANEITY_FACTOR_BY_BAND[band_code]
    if pool == POOL_C:
        return POOL_C_SIMULTANEITY_FACTOR
    _fail("INVALID_POWER_POOL", "unsupported power pool", pool=pool)


def _make_detail(
    *,
    equipment_or_zone: str,
    basis: str,
    configured_quantity: int,
    unit_power_kw: Decimal,
    pool: str,
    band_code: str,
) -> FactoryPowerDetail:
    if configured_quantity < 0:
        _fail(
            "INVALID_CONFIGURED_QUANTITY",
            "configured quantity cannot be negative",
            equipment_or_zone=equipment_or_zone,
        )
    if not unit_power_kw.is_finite() or unit_power_kw < 0:
        _fail(
            "INVALID_UNIT_POWER",
            "unit power must be finite and non-negative",
            equipment_or_zone=equipment_or_zone,
        )
    if pool not in SUPPORTED_POOLS:
        _fail("INVALID_POWER_POOL", "unsupported power pool", pool=pool)
    simultaneity_factor = _pool_factor(pool, band_code)
    installed = Decimal(configured_quantity) * unit_power_kw
    coincident = installed * simultaneity_factor
    return FactoryPowerDetail(
        equipment_or_zone=equipment_or_zone,
        basis=basis,
        configured_quantity=configured_quantity,
        unit_power_kw=unit_power_kw,
        installed_power_kw=installed,
        pool=pool,
        simultaneity_factor=simultaneity_factor,
        coincident_power_kw=coincident,
    )


def _append_zone_details(
    details: list[FactoryPowerDetail],
    zone: FactoryPowerZoneInput,
    rule: ZoneAirCoolerRule,
    *,
    band_code: str,
) -> None:
    if rule.quantity_basis == "PRECOOLING_SCHEME":
        scheme = _selected_scheme(zone)
        assert scheme.room_count is not None
        assert scheme.position_count is not None
        quantity = (
            scheme.room_count * PRECOOLING_CONFIGURATIONS[scheme.scheme_id].air_coolers_per_room
        )
        final_position_count = scheme.position_count
        details.append(
            _make_detail(
                equipment_or_zone=f"{zone.zone_code}.air_cooler.motor",
                basis=rule.quantity_formula,
                configured_quantity=quantity,
                unit_power_kw=rule.motor_kw_per_unit,
                pool=rule.motor_pool,
                band_code=band_code,
            )
        )
        details.append(
            _make_detail(
                equipment_or_zone=f"{zone.zone_code}.air_cooler.defrost",
                basis=rule.quantity_formula,
                configured_quantity=quantity,
                unit_power_kw=rule.defrost_kw_per_unit,
                pool=rule.defrost_pool,
                band_code=band_code,
            )
        )
        if (
            rule.axial_fans_per_position is None
            or rule.axial_fan_kw_per_unit is None
            or rule.axial_fan_quantity_formula is None
        ):
            _fail(
                "INVALID_RULE_REGISTRY",
                "pre-cooling rule has no axial-fan rule",
                zone_code=zone.zone_code,
            )
        details.append(
            _make_detail(
                equipment_or_zone=f"{zone.zone_code}.precooling_axial_fan",
                basis=rule.axial_fan_quantity_formula,
                configured_quantity=final_position_count * rule.axial_fans_per_position,
                unit_power_kw=rule.axial_fan_kw_per_unit,
                pool=POOL_B,
                band_code=band_code,
            )
        )
        return

    quantity = _zone_area_quantity(rule, zone)
    details.append(
        _make_detail(
            equipment_or_zone=f"{zone.zone_code}.air_cooler.motor",
            basis=rule.quantity_formula,
            configured_quantity=quantity,
            unit_power_kw=rule.motor_kw_per_unit,
            pool=rule.motor_pool,
            band_code=band_code,
        )
    )
    details.append(
        _make_detail(
            equipment_or_zone=f"{zone.zone_code}.air_cooler.defrost",
            basis=rule.quantity_formula,
            configured_quantity=quantity,
            unit_power_kw=rule.defrost_kw_per_unit,
            pool=rule.defrost_pool,
            band_code=band_code,
        )
    )


def _validate_pool_invariants(details: Sequence[FactoryPowerDetail]) -> None:
    names = [detail.equipment_or_zone for detail in details]
    if len(names) != len(set(names)):
        _fail("POOL_INVARIANT_VIOLATION", "one component was assigned more than once")
    for detail in details:
        if detail.pool == POOL_A and not detail.equipment_or_zone.endswith(".defrost"):
            _fail("POOL_INVARIANT_VIOLATION", "POOL_A contains a non-defrost component")
        if detail.pool == POOL_C and detail.equipment_or_zone != "production_equipment":
            _fail("POOL_INVARIANT_VIOLATION", "POOL_C contains a non-production component")
        if detail.pool == POOL_B and (
            detail.equipment_or_zone.endswith(".defrost")
            or detail.equipment_or_zone == "production_equipment"
        ):
            _fail("POOL_INVARIANT_VIOLATION", "POOL_B contains a forbidden component")


def _summary(details: Sequence[FactoryPowerDetail]) -> FactoryPowerSummary:
    installed = {pool: Decimal("0") for pool in SUPPORTED_POOLS}
    coincident = {pool: Decimal("0") for pool in SUPPORTED_POOLS}
    for detail in details:
        installed[detail.pool] += detail.installed_power_kw
        coincident[detail.pool] += detail.coincident_power_kw
    total_installed = installed[POOL_A] + installed[POOL_B] + installed[POOL_C]
    estimated_total = coincident[POOL_A] + coincident[POOL_B] + coincident[POOL_C]
    return FactoryPowerSummary(
        defrost_installed_power_kw=installed[POOL_A],
        defrost_coincident_power_kw=coincident[POOL_A],
        other_installed_power_kw=installed[POOL_B],
        other_coincident_power_kw=coincident[POOL_B],
        production_equipment_installed_power_kw=installed[POOL_C],
        production_equipment_coincident_power_kw=coincident[POOL_C],
        total_installed_power_kw=total_installed,
        estimated_total_power_kw=estimated_total,
    )


def calculate_factory_power_estimation(
    calculation_input: FactoryPowerEstimationInput,
) -> FactoryPowerEstimationResult:
    """Calculate the V2.0 factory-power canonical result."""
    _validate_canonical_input(calculation_input)
    factory_area_m2 = _validated_authority_decimal(
        calculation_input.factory_area_m2,
        field_name="factory_area_m2",
        missing_code="MISSING_FACTORY_AREA_AUTHORITY",
        invalid_code="INVALID_FACTORY_AREA_AUTHORITY",
    )
    cold_storage_area_m2 = _validated_authority_decimal(
        calculation_input.cold_storage_area_m2,
        field_name="cold_storage_area_m2",
        missing_code="MISSING_COLD_STORAGE_AREA_AUTHORITY",
        invalid_code="INVALID_COLD_STORAGE_AREA_AUTHORITY",
    )
    band = _select_factory_area_band(factory_area_m2)
    zone_map = _validate_zone_set(calculation_input.zones)
    details: list[FactoryPowerDetail] = []

    for zone_code, rule in ZONE_AIR_COOLER_RULES.items():
        zone = zone_map[zone_code]
        _append_zone_details(details, zone, rule, band_code=band.code)

    for equipment_code, public_rule in PUBLIC_EQUIPMENT_RULES.items():
        if public_rule.quantity_by_band is not None:
            quantity = public_rule.quantity_by_band[band.code]
            assert public_rule.unit_power_kw is not None
            unit_power_kw = public_rule.unit_power_kw
            basis = "factory_area_band"
        else:
            if public_rule.fixed_quantity is None or public_rule.fixed_installed_power_kw is None:
                _fail("INVALID_RULE_REGISTRY", "fixed public-equipment rule is incomplete")
            quantity = public_rule.fixed_quantity
            unit_power_kw = public_rule.fixed_installed_power_kw / Decimal(quantity)
            basis = "fixed_installed_power_kw"
        details.append(
            _make_detail(
                equipment_or_zone=f"public.{equipment_code}",
                basis=basis,
                configured_quantity=quantity,
                unit_power_kw=unit_power_kw,
                pool=public_rule.pool,
                band_code=band.code,
            )
        )

    for lighting_code, lighting_rule in LIGHTING_RULES.items():
        if lighting_rule.area_source_field != "cold_storage_area_m2":
            _fail(
                "INVALID_RULE_REGISTRY",
                "lighting rule must use cold_storage_area_m2",
                lighting_code=lighting_code,
            )
        lighting_quantity = int(
            (cold_storage_area_m2 / lighting_rule.area_divisor_m2).to_integral_value(
                rounding=ROUND_CEILING
            )
        )
        details.append(
            _make_detail(
                equipment_or_zone=lighting_code,
                basis=lighting_rule.quantity_formula,
                configured_quantity=lighting_quantity,
                unit_power_kw=lighting_rule.unit_power_kw,
                pool=lighting_rule.pool,
                band_code=band.code,
            )
        )

    main_load = sum(
        (_required_main_cooling_load(zone_map[zone_code]) for zone_code in MAIN_SYSTEM_ZONE_CODES),
        Decimal("0"),
    )
    main_compressor_power = main_load / MAIN_SYSTEM_COP
    details.append(
        _make_detail(
            equipment_or_zone="main_system.compressor_shaft_power",
            basis="sum(exactly six minimum_estimated_cooling_load_kw_r) / 3.3",
            configured_quantity=1,
            unit_power_kw=main_compressor_power,
            pool=POOL_B,
            band_code=band.code,
        )
    )
    for zone_code in DEDICATED_SYSTEM_ZONE_CODES:
        details.append(
            _make_detail(
                equipment_or_zone=f"{zone_code}.dedicated_compressor_shaft_power",
                basis="dedicated compressor shaft power by factory area band",
                configured_quantity=1,
                unit_power_kw=DEDICATED_COMPRESSOR_POWER_BY_ZONE[zone_code][band.code],
                pool=POOL_B,
                band_code=band.code,
            )
        )
    details.append(
        _make_detail(
            equipment_or_zone="evaporative_condenser",
            basis="factory area band",
            configured_quantity=1,
            unit_power_kw=EVAPORATIVE_CONDENSER_POWER_BY_BAND[band.code],
            pool=POOL_B,
            band_code=band.code,
        )
    )
    details.append(
        _make_detail(
            equipment_or_zone="production_equipment",
            basis="production_equipment_installed_power_kw by factory area band",
            configured_quantity=1,
            unit_power_kw=PRODUCTION_POWER_BY_BAND[band.code],
            pool=POOL_C,
            band_code=band.code,
        )
    )

    _validate_pool_invariants(details)
    normalized_zones = [zone_map[code].to_dict() for code in sorted(zone_map)]
    input_snapshot: Mapping[str, object] = MappingProxyType(
        {
            "factory_area_m2": _decimal_text(factory_area_m2),
            "cold_storage_area_m2": _decimal_text(cold_storage_area_m2),
            "zone_source_path": "zone_plan.result.zones[]",
            "zones": normalized_zones,
            "selected_reporting_scheme_ids": {
                code: zone_map[code].reporting_scheme_id
                for code in ("primary_precooling_room", "secondary_precooling_room")
            },
        }
    )
    provenance: Mapping[str, object] = MappingProxyType(
        {
            "rule_authority": P0_CONTRACT_TASK_ID,
            "rule_source": "static_runtime_registry",
            "runtime_document_parsing": False,
            "zone_area_source": "zone_plan.result.zones[].required_area_m2",
            "precooling_scheme_source": "zone_plan.result.zones[].schemes[]",
            "precooling_selection_field": "reporting_scheme_id",
            "cooling_load_source": "zone_plan.result.zones[].minimum_estimated_cooling_load_kw_r",
            "legacy_authority_used": False,
        }
    )
    assumptions = (
        "factory_area_m2 is an explicit canonical authority; no area substitute is permitted",
        (
            "cold_storage_area_m2 is an explicit canonical authority; "
            "its derivation is supplied upstream"
        ),
        "all values are estimated electrical power in kW and require engineering review",
        "the result is not kWh, metered electricity, or daily electricity consumption",
    )
    return FactoryPowerEstimationResult(
        factory_area_band=band.code,
        input_snapshot=input_snapshot,
        provenance=provenance,
        assumptions=assumptions,
        details=tuple(details),
        summary=_summary(details),
    )


def calculate_factory_power_estimation_from_mapping(
    raw: Mapping[str, object],
) -> FactoryPowerEstimationResult:
    """Pure convenience entry point for a backend adapter."""
    return calculate_factory_power_estimation(build_factory_power_estimation_input(raw))


def serialize_factory_power_result(result: FactoryPowerEstimationResult) -> dict[str, object]:
    """Return the one canonical machine-readable payload."""
    return result.to_dict()


__all__ = [
    "CALCULATOR_ID",
    "CALCULATOR_IDENTITY",
    "CALCULATOR_VERSION",
    "DEFROST_SIMULTANEOUS_USE_FACTOR",
    "DEDICATED_COMPRESSOR_POWER_BY_ZONE",
    "DEDICATED_SYSTEM_ZONE_CODES",
    "EVAPORATIVE_CONDENSER_POWER_BY_BAND",
    "FACTORY_AREA_BANDS",
    "FactoryAreaBand",
    "FactoryPowerDetail",
    "FactoryPowerEstimationError",
    "FactoryPowerEstimationInput",
    "FactoryPowerEstimationResult",
    "FactoryPowerSchemeInput",
    "FactoryPowerSummary",
    "FactoryPowerZoneInput",
    "LIGHTING_RULES",
    "LightingRule",
    "MAIN_SYSTEM_COP",
    "MAIN_SYSTEM_ZONE_CODES",
    "HISTORICAL_POOL_A_SIMULTANEITY_FACTOR",
    "POOL_A_SIMULTANEITY_FACTOR",
    "POOL_B_SIMULTANEITY_FACTOR_BY_BAND",
    "POOL_C_SIMULTANEITY_FACTOR",
    "P0_CONTRACT_TASK_ID",
    "PRECOOLING_CONFIGURATIONS",
    "PRODUCTION_POWER_BY_BAND",
    "PUBLIC_EQUIPMENT_RULES",
    "RESULT_SCHEMA_VERSION",
    "ZONE_AIR_COOLER_RULES",
    "build_factory_power_estimation_input",
    "calculate_factory_power_estimation",
    "calculate_factory_power_estimation_from_mapping",
    "serialize_factory_power_result",
]
