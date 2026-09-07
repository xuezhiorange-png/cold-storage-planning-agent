"""V1.9 per-zone minimum cooling-estimation basis.

This module is a pure additive enrichment boundary for the existing zone plan.
It owns the typed runtime registry; the P0 Markdown/JSON contract is evidence
and is checked by architecture tests, not parsed by runtime code.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

from cold_storage.modules.calculations.domain.errors import CoreCalculationError

AUTHORITY_SOURCE = "CHARLES_CONFIRMED_ENGINEERING_REFERENCE"
MINIMUM_OUTPUT_FIELD = "minimum_estimated_cooling_load_kw_r"
PROVENANCE_FIELD = "cooling_estimation_basis"
AMBIENT_TEMPERATURE_BAND = "常温"


@dataclass(frozen=True, slots=True)
class PerZoneCoolingEstimationRule:
    """Typed, static authority for one frozen V1.9 zone rule."""

    zone_code: str
    basis_type: str
    source_field: str
    source_unit: str
    reference_factor: Decimal | None
    reference_factor_unit: str
    minimum_factor_kw_r: Decimal | None
    authority_source: str = AUTHORITY_SOURCE
    requires_review: bool = True


class PerZoneCoolingEstimationError(CoreCalculationError):
    """Structured fail-closed error raised by the P1 enrichment boundary."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.code = code
        self.details = dict(details or {})
        super().__init__(message)


def _rule(
    *,
    zone_code: str,
    basis_type: str,
    source_field: str,
    source_unit: str,
    reference_factor: str,
    reference_factor_unit: str,
    minimum_factor_kw_r: str,
) -> PerZoneCoolingEstimationRule:
    return PerZoneCoolingEstimationRule(
        zone_code=zone_code,
        basis_type=basis_type,
        source_field=source_field,
        source_unit=source_unit,
        reference_factor=Decimal(reference_factor),
        reference_factor_unit=reference_factor_unit,
        minimum_factor_kw_r=Decimal(minimum_factor_kw_r),
    )


PER_ZONE_COOLING_ESTIMATION_RULES: Mapping[str, PerZoneCoolingEstimationRule] = MappingProxyType(
    {
        "primary_precooling_room": _rule(
            zone_code="primary_precooling_room",
            basis_type="FINAL_POSITION_COUNT",
            source_field="position_count",
            source_unit="position",
            reference_factor="20",
            reference_factor_unit="kW(r)/final position",
            minimum_factor_kw_r="20",
        ),
        "secondary_precooling_room": _rule(
            zone_code="secondary_precooling_room",
            basis_type="FINAL_POSITION_COUNT",
            source_field="position_count",
            source_unit="position",
            reference_factor="15",
            reference_factor_unit="kW(r)/final position",
            minimum_factor_kw_r="15",
        ),
        "raw_fruit_buffer": _rule(
            zone_code="raw_fruit_buffer",
            basis_type="ZONE_AREA",
            source_field="required_area_m2",
            source_unit="m2",
            reference_factor="400",
            reference_factor_unit="W/m2",
            minimum_factor_kw_r="0.40",
        ),
        "sorting_packaging_room": _rule(
            zone_code="sorting_packaging_room",
            basis_type="ZONE_AREA",
            source_field="required_area_m2",
            source_unit="m2",
            reference_factor="300",
            reference_factor_unit="W/m2",
            minimum_factor_kw_r="0.30",
        ),
        "coating_room": _rule(
            zone_code="coating_room",
            basis_type="ZONE_AREA",
            source_field="required_area_m2",
            source_unit="m2",
            reference_factor="300",
            reference_factor_unit="W/m2",
            minimum_factor_kw_r="0.30",
        ),
        "finished_goods_room": _rule(
            zone_code="finished_goods_room",
            basis_type="ZONE_AREA",
            source_field="required_area_m2",
            source_unit="m2",
            reference_factor="300",
            reference_factor_unit="W/m2",
            minimum_factor_kw_r="0.30",
        ),
        "secondary_fruit_buffer": _rule(
            zone_code="secondary_fruit_buffer",
            basis_type="ZONE_AREA",
            source_field="required_area_m2",
            source_unit="m2",
            reference_factor="400",
            reference_factor_unit="W/m2",
            minimum_factor_kw_r="0.40",
        ),
        "frozen_fruit_room": _rule(
            zone_code="frozen_fruit_room",
            basis_type="ZONE_AREA",
            source_field="required_area_m2",
            source_unit="m2",
            reference_factor="550",
            reference_factor_unit="W/m2",
            minimum_factor_kw_r="0.55",
        ),
        "shipping_channel": _rule(
            zone_code="shipping_channel",
            basis_type="ZONE_AREA",
            source_field="required_area_m2",
            source_unit="m2",
            reference_factor="300",
            reference_factor_unit="W/m2",
            minimum_factor_kw_r="0.30",
        ),
    }
)

EXPECTED_REFRIGERATED_ZONE_CODES = frozenset(PER_ZONE_COOLING_ESTIMATION_RULES)


def _fail(code: str, message: str, **details: object) -> PerZoneCoolingEstimationError:
    return PerZoneCoolingEstimationError(code, message, details)


def _as_decimal(value: object, *, zone_code: str, source_field: str) -> Decimal:
    if value is None:
        raise _fail(
            "MISSING_SOURCE_VALUE",
            f"{zone_code}: required source field {source_field!r} is missing or None",
            zone_code=zone_code,
            source_field=source_field,
        )
    if isinstance(value, bool):
        raise _fail(
            "NON_NUMERIC_SOURCE_VALUE",
            f"{zone_code}: source field {source_field!r} must be numeric",
            zone_code=zone_code,
            source_field=source_field,
            value=repr(value),
        )
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise _fail(
            "NON_NUMERIC_SOURCE_VALUE",
            f"{zone_code}: source field {source_field!r} must be numeric",
            zone_code=zone_code,
            source_field=source_field,
            value=repr(value),
        ) from exc
    if not parsed.is_finite():
        raise _fail(
            "NON_FINITE_SOURCE_VALUE",
            f"{zone_code}: source field {source_field!r} must be finite",
            zone_code=zone_code,
            source_field=source_field,
            value=repr(value),
        )
    if parsed < 0:
        raise _fail(
            "NEGATIVE_SOURCE_VALUE",
            f"{zone_code}: source field {source_field!r} cannot be negative",
            zone_code=zone_code,
            source_field=source_field,
            value=repr(value),
        )
    return parsed


def _json_number(value: Decimal) -> int | float:
    """Keep legacy numeric zone payloads while calculating with Decimal."""
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _validate_rule(rule: PerZoneCoolingEstimationRule) -> None:
    if rule.reference_factor is None or rule.minimum_factor_kw_r is None:
        raise _fail(
            "MISSING_REFERENCE_FACTOR",
            f"{rule.zone_code}: V1.9 reference factor is missing",
            zone_code=rule.zone_code,
        )
    if rule.authority_source != AUTHORITY_SOURCE or rule.requires_review is not True:
        raise _fail(
            "INVALID_RULE_METADATA",
            f"{rule.zone_code}: V1.9 rule metadata is invalid",
            zone_code=rule.zone_code,
        )
    if not rule.reference_factor.is_finite() or not rule.minimum_factor_kw_r.is_finite():
        raise _fail(
            "INVALID_RULE_METADATA",
            f"{rule.zone_code}: V1.9 rule factor must be finite",
            zone_code=rule.zone_code,
        )
    if rule.reference_factor < 0 or rule.minimum_factor_kw_r < 0:
        raise _fail(
            "INVALID_RULE_METADATA",
            f"{rule.zone_code}: V1.9 rule factor cannot be negative",
            zone_code=rule.zone_code,
        )


def _enrich_zone(
    zone: Mapping[str, object],
    rule: PerZoneCoolingEstimationRule,
) -> dict[str, object]:
    _validate_rule(rule)
    if rule.basis_type == "FINAL_POSITION_COUNT" and rule.source_field != "position_count":
        raise _fail(
            "INVALID_RULE_METADATA",
            f"{rule.zone_code}: pre-cooling rule must use position_count",
            zone_code=rule.zone_code,
        )
    if rule.basis_type == "ZONE_AREA" and rule.source_field != "required_area_m2":
        raise _fail(
            "INVALID_RULE_METADATA",
            f"{rule.zone_code}: area rule must use required_area_m2",
            zone_code=rule.zone_code,
        )
    if rule.basis_type not in {"FINAL_POSITION_COUNT", "ZONE_AREA"}:
        raise _fail(
            "INVALID_RULE_METADATA",
            f"{rule.zone_code}: unsupported V1.9 basis type",
            zone_code=rule.zone_code,
        )

    source = _as_decimal(
        zone.get(rule.source_field),
        zone_code=rule.zone_code,
        source_field=rule.source_field,
    )
    assert rule.minimum_factor_kw_r is not None
    minimum = source * rule.minimum_factor_kw_r
    enriched = dict(zone)
    enriched[MINIMUM_OUTPUT_FIELD] = _json_number(minimum)
    enriched[PROVENANCE_FIELD] = {
        "basis_type": rule.basis_type,
        "source_field": rule.source_field,
        "source_value": _json_number(source),
        "source_unit": rule.source_unit,
        "reference_factor": _json_number(rule.reference_factor or Decimal("0")),
        "reference_factor_unit": rule.reference_factor_unit,
        "authority_source": rule.authority_source,
        "requires_review": rule.requires_review,
    }
    return enriched


def apply_per_zone_cooling_estimation(
    zones: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Add the frozen minimum estimate to the nine refrigerated zone rows.

    Ambient rows pass through unchanged.  Any malformed, missing, duplicate,
    or unmapped refrigerated row raises a typed error; no fallback source or
    zero default is permitted.
    """
    enriched: list[dict[str, object]] = []
    seen_refrigerated: set[str] = set()

    for index, zone in enumerate(zones):
        if not isinstance(zone, Mapping):
            raise _fail(
                "INVALID_ZONE_ROW",
                f"zone row at index {index} must be a mapping",
                index=index,
            )
        zone_code = zone.get("zone_code")
        if not isinstance(zone_code, str) or not zone_code:
            raise _fail(
                "MISSING_ZONE_CODE",
                f"zone row at index {index} must contain a non-empty zone_code",
                index=index,
            )

        rule = PER_ZONE_COOLING_ESTIMATION_RULES.get(zone_code)
        if rule is None:
            if zone.get("temperature_band") == AMBIENT_TEMPERATURE_BAND:
                enriched.append(dict(zone))
                continue
            raise _fail(
                "UNMAPPED_REFRIGERATED_ZONE",
                f"{zone_code}: refrigerated zone has no V1.9 rule",
                zone_code=zone_code,
                index=index,
            )
        if zone_code in seen_refrigerated:
            raise _fail(
                "DUPLICATE_REFRIGERATED_ZONE",
                f"{zone_code}: refrigerated zone_code is duplicated",
                zone_code=zone_code,
                index=index,
            )
        seen_refrigerated.add(zone_code)
        enriched.append(_enrich_zone(zone, rule))

    missing = sorted(EXPECTED_REFRIGERATED_ZONE_CODES - seen_refrigerated)
    if missing:
        raise _fail(
            "MISSING_REFRIGERATED_ZONE",
            f"V1.9 refrigerated zone set is incomplete: {missing}",
            missing_zone_codes=missing,
        )
    return enriched
