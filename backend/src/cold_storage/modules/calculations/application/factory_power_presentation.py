"""Read-only presentation boundary for the V2.0 factory-power result.

The P1 calculator owns every engineering value.  This module only validates
the serialized result shape, copies source fields, adds presentation labels,
and derives an integrity hash from the already serialized canonical payload.
It deliberately does not import or execute the calculator.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

FACTORY_POWER_CALCULATOR_ID = "factory_power_estimation"
FACTORY_POWER_CALCULATOR_VERSION = "2.0.0-p2"
FACTORY_POWER_CALCULATOR_IDENTITY = (
    f"{FACTORY_POWER_CALCULATOR_ID}@{FACTORY_POWER_CALCULATOR_VERSION}"
)
FACTORY_POWER_RESULT_SCHEMA_VERSION = "2.0.0-p1"
FACTORY_POWER_RESULT_KIND = "factory_power_canonical_result"
FACTORY_POWER_UNAVAILABLE_CODE = "V20_FACTORY_POWER_CANONICAL_RESULT_UNAVAILABLE"

FACTORY_POWER_DETAIL_FIELDS: tuple[str, ...] = (
    "equipment_or_zone",
    "basis",
    "configured_quantity",
    "unit_power_kw",
    "installed_power_kw",
    "pool",
    "simultaneity_factor",
    "coincident_power_kw",
)
FACTORY_POWER_SUMMARY_FIELDS: tuple[str, ...] = (
    "defrost_installed_power_kw",
    "defrost_coincident_power_kw",
    "other_installed_power_kw",
    "other_coincident_power_kw",
    "production_equipment_installed_power_kw",
    "production_equipment_coincident_power_kw",
    "total_installed_power_kw",
    "estimated_total_power_kw",
)

POOL_DISPLAY_LABELS: dict[str, str] = {
    "POOL_A": "化霜",
    "POOL_B": "其他设备",
    "POOL_C": "生产设备",
}

DETAIL_DISPLAY_LABELS: dict[str, str] = {
    "public.electric_sliding_door": "冷库电动平移门",
    "public.rapid_rolling_door": "快速卷帘门",
    "public.air_curtain": "风幕",
    "public.loading_platform": "装卸平台",
    "public.ozone_humidification": "臭氧与加湿",
    "public.floor_heating": "地坪加热",
    "cold_storage.lighting": "冷间照明",
    "cold_storage.ultraviolet": "冷间紫外线",
    "evaporative_condenser": "蒸发式冷凝器",
    "production_equipment": "生产设备",
}


class FactoryPowerPresentationError(ValueError):
    """The persisted V2.0 result cannot be safely presented."""


JsonObject = dict[str, object]


@dataclass(frozen=True, slots=True)
class FactoryPowerPresentation:
    """Immutable read model shared by the workbench and Aily projectors."""

    schema_version: str
    source_calculator_id: str
    source_calculator_version: str
    source_calculator_identity: str
    canonical_result_hash: str
    factory_area_band: str
    unit_semantics: JsonObject
    review: JsonObject
    provenance: JsonObject
    assumptions: tuple[str, ...]
    details: tuple[JsonObject, ...]
    summary: JsonObject

    @property
    def requires_review(self) -> bool:
        return self.review.get("requires_review") is True

    def to_dict(self) -> JsonObject:
        """Return a detached JSON-shaped copy for any read-only consumer."""
        return {
            "schema_version": self.schema_version,
            "source_calculator_id": self.source_calculator_id,
            "source_calculator_version": self.source_calculator_version,
            "source_calculator_identity": self.source_calculator_identity,
            "canonical_result_hash": self.canonical_result_hash,
            "factory_area_band": self.factory_area_band,
            "unit_semantics": deepcopy(self.unit_semantics),
            "review": deepcopy(self.review),
            "provenance": deepcopy(self.provenance),
            "assumptions": list(self.assumptions),
            "details": deepcopy(list(self.details)),
            "summary": deepcopy(self.summary),
        }


def canonical_result_hash(canonical_result: Mapping[str, Any]) -> str:
    """Hash the serialized P1 canonical JSON without interpreting its values."""
    try:
        canonical_json = json.dumps(
            canonical_result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise FactoryPowerPresentationError("canonical result is not JSON serializable") from exc
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def build_factory_power_presentation(
    canonical_result: Mapping[str, Any],
) -> FactoryPowerPresentation:
    """Validate and project one serialized current result without recalculation."""
    payload = _require_mapping(canonical_result, "canonical_result")
    _require_exact_text(payload, "schema_version", FACTORY_POWER_RESULT_SCHEMA_VERSION)
    _require_exact_text(payload, "result_kind", FACTORY_POWER_RESULT_KIND)
    if payload.get("success") is not True:
        raise FactoryPowerPresentationError("canonical result must be successful")

    calculator = _require_mapping(payload.get("calculator"), "canonical_result.calculator")
    _require_exact_text(calculator, "id", FACTORY_POWER_CALCULATOR_ID)
    _require_exact_text(calculator, "version", FACTORY_POWER_CALCULATOR_VERSION)
    _require_exact_text(calculator, "identity", FACTORY_POWER_CALCULATOR_IDENTITY)

    _require_mapping(payload.get("input_authority"), "canonical_result.input_authority")
    factory_area_band = _require_non_empty_text(
        payload, "factory_area_band", "canonical_result.factory_area_band"
    )
    unit_semantics = _require_mapping(
        payload.get("unit_semantics"), "canonical_result.unit_semantics"
    )
    _require_semantic_unit_fields(unit_semantics)
    provenance = _require_mapping(payload.get("provenance"), "canonical_result.provenance")
    assumptions = _require_string_sequence(
        payload.get("assumptions"), "canonical_result.assumptions"
    )
    review = _require_mapping(payload.get("review"), "canonical_result.review")
    if review.get("requires_review") is not True:
        raise FactoryPowerPresentationError("canonical result must retain requires_review=true")
    _require_non_empty_text(review, "status", "canonical_result.review.status")

    details_raw = _require_sequence(payload.get("details"), "canonical_result.details")
    details = tuple(_project_detail(item, index=index) for index, item in enumerate(details_raw))
    summary = _project_summary(payload.get("summary"))

    return FactoryPowerPresentation(
        schema_version=_require_non_empty_text(
            payload, "schema_version", "canonical_result.schema_version"
        ),
        source_calculator_id=_require_non_empty_text(
            calculator, "id", "canonical_result.calculator.id"
        ),
        source_calculator_version=_require_non_empty_text(
            calculator, "version", "canonical_result.calculator.version"
        ),
        source_calculator_identity=_require_non_empty_text(
            calculator, "identity", "canonical_result.calculator.identity"
        ),
        canonical_result_hash=canonical_result_hash(payload),
        factory_area_band=factory_area_band,
        unit_semantics=deepcopy(dict(unit_semantics)),
        review=deepcopy(dict(review)),
        provenance=deepcopy(dict(provenance)),
        assumptions=tuple(assumptions),
        details=details,
        summary=summary,
    )


def factory_power_presentation_from_record(
    record: Mapping[str, Any],
) -> FactoryPowerPresentation:
    """Read a matching CalculationRun-shaped record and project its snapshot."""
    if not is_factory_power_record(record):
        raise FactoryPowerPresentationError("record is not factory_power_estimation@2.0.0-p2")
    snapshot = _require_mapping(record.get("result_snapshot"), "record.result_snapshot")
    canonical = _canonical_payload_from_snapshot(snapshot)
    return build_factory_power_presentation(canonical)


def select_latest_factory_power_record(
    records: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """Select only the newest exact V2 identity; legacy rows are ignored."""
    candidates = [record for record in records if is_factory_power_record(record)]
    if not candidates:
        return None
    return max(candidates, key=_record_order_key)


def factory_power_presentation_from_records(
    records: Sequence[Mapping[str, Any]],
) -> FactoryPowerPresentation | None:
    """Return a V2 presentation or ``None`` when the result is absent/invalid."""
    record = select_latest_factory_power_record(records)
    if record is None:
        return None
    try:
        return factory_power_presentation_from_record(record)
    except FactoryPowerPresentationError:
        return None


def is_factory_power_record(record: Mapping[str, Any]) -> bool:
    """Match the V2 calculator name and version exactly."""
    return (
        record.get("calculator_name") == FACTORY_POWER_CALCULATOR_ID
        and record.get("calculator_version") == FACTORY_POWER_CALCULATOR_VERSION
    )


def attach_factory_power_presentation(record: Mapping[str, Any]) -> JsonObject:
    """Attach the shared read model to an existing generic calculation row."""
    result = dict(record)
    if not is_factory_power_record(record):
        return result
    try:
        result["factory_power_presentation"] = factory_power_presentation_from_record(
            record
        ).to_dict()
    except FactoryPowerPresentationError:
        result["factory_power_presentation"] = None
    return result


def _project_detail(value: object, *, index: int) -> JsonObject:
    detail = _require_mapping(value, f"canonical_result.details[{index}]")
    projected: JsonObject = {}
    for field_name in FACTORY_POWER_DETAIL_FIELDS:
        field_path = f"canonical_result.details[{index}].{field_name}"
        if field_name == "configured_quantity":
            quantity = detail.get(field_name)
            if isinstance(quantity, bool) or not isinstance(quantity, int):
                raise FactoryPowerPresentationError(f"{field_path} must be an integer")
            projected[field_name] = quantity
        elif field_name == "pool":
            pool = _require_non_empty_text(detail, field_name, field_path)
            if pool not in POOL_DISPLAY_LABELS:
                raise FactoryPowerPresentationError(f"{field_path} has an unknown pool")
            projected[field_name] = pool
        else:
            projected[field_name] = _require_non_empty_text(detail, field_name, field_path)

    equipment_or_zone = cast(str, projected["equipment_or_zone"])
    pool = cast(str, projected["pool"])
    projected["display_label"] = DETAIL_DISPLAY_LABELS.get(equipment_or_zone, equipment_or_zone)
    projected["pool_label"] = POOL_DISPLAY_LABELS[pool]
    return projected


def _project_summary(value: object) -> JsonObject:
    summary = _require_mapping(value, "canonical_result.summary")
    return {
        field_name: _require_non_empty_text(
            summary, field_name, f"canonical_result.summary.{field_name}"
        )
        for field_name in FACTORY_POWER_SUMMARY_FIELDS
    }


def _canonical_payload_from_snapshot(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(snapshot.get("calculator"), Mapping):
        return snapshot
    nested = snapshot.get("result")
    if isinstance(nested, Mapping):
        return nested
    raise FactoryPowerPresentationError(
        "record.result_snapshot does not contain a canonical result"
    )


def _record_order_key(record: Mapping[str, Any]) -> tuple[str, str]:
    created_at = record.get("created_at")
    calculation_id = record.get("calculation_id") or record.get("id") or ""
    return (str(created_at or ""), str(calculation_id))


def _require_mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FactoryPowerPresentationError(f"{path} must be an object")
    return cast(Mapping[str, Any], value)


def _require_sequence(value: object, path: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise FactoryPowerPresentationError(f"{path} must be an array")
    return value


def _require_string_sequence(value: object, path: str) -> tuple[str, ...]:
    sequence = _require_sequence(value, path)
    if not all(isinstance(item, str) for item in sequence):
        raise FactoryPowerPresentationError(f"{path} must contain only strings")
    return tuple(cast(str, item) for item in sequence)


def _require_non_empty_text(mapping: Mapping[str, Any], key: str, path: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise FactoryPowerPresentationError(f"{path} must be a non-empty string")
    return value


def _require_exact_text(mapping: Mapping[str, Any], key: str, expected: str) -> None:
    if mapping.get(key) != expected:
        raise FactoryPowerPresentationError(f"{key} does not match the V2.0 identity")


def _require_semantic_unit_fields(unit_semantics: Mapping[str, Any]) -> None:
    expected = {
        "power_unit",
        "energy_unit",
        "not_energy",
        "not_metered_electricity",
        "not_daily_electricity_consumption",
    }
    if not expected <= set(unit_semantics):
        raise FactoryPowerPresentationError("unit_semantics is incomplete")
    if unit_semantics.get("power_unit") != "kW" or unit_semantics.get("not_energy") is not True:
        raise FactoryPowerPresentationError("unit_semantics is not the V2.0 power contract")


__all__ = [
    "DETAIL_DISPLAY_LABELS",
    "FACTORY_POWER_CALCULATOR_ID",
    "FACTORY_POWER_CALCULATOR_IDENTITY",
    "FACTORY_POWER_CALCULATOR_VERSION",
    "FACTORY_POWER_DETAIL_FIELDS",
    "FACTORY_POWER_RESULT_KIND",
    "FACTORY_POWER_RESULT_SCHEMA_VERSION",
    "FACTORY_POWER_SUMMARY_FIELDS",
    "FACTORY_POWER_UNAVAILABLE_CODE",
    "FactoryPowerPresentation",
    "FactoryPowerPresentationError",
    "POOL_DISPLAY_LABELS",
    "attach_factory_power_presentation",
    "build_factory_power_presentation",
    "canonical_result_hash",
    "factory_power_presentation_from_record",
    "factory_power_presentation_from_records",
    "is_factory_power_record",
    "select_latest_factory_power_record",
]
