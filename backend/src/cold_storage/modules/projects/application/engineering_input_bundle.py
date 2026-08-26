"""EngineeringInputBundleV1 validation and execution-snapshot projection.

Implements the frozen P0 contract in
``docs/tasks/V0_5-P0-five-stage-workbench-contract.md`` without embedding
engineering formula values.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, NoReturn

from cold_storage.modules.orchestration.domain.dag import CALCULATOR_BINDINGS
from cold_storage.shared.errors import MissingEngineeringParameterError

BUNDLE_SCHEMA_ID = "EngineeringInputBundleV1"
BUNDLE_SCHEMA_VERSION = "1.0.0"

OPERATOR_PROCESS_SCHEMA_ID = "OperatorProcessInputV1"
OPERATOR_PROCESS_SCHEMA_VERSION = "1.0.0"
LINEAGE_PENDING_STATE = "lineage_pending"

OPERATOR_FIVE_KEY_FIELDS: tuple[str, ...] = (
    "daily_inbound_mass_kg",
    "working_time_h_per_day",
    "finished_storage_days",
    "packaging_storage_days",
    "precooling_required_ratio",
)

_LINEAGE_DEFERRED_COOLING_FIELDS: frozenset[str] = frozenset(
    {
        "zone_code",
        "zone_name",
        "temperature_level",
        "zone_area",
        "floor_area",
    }
)

_KEY_ZONE_FIELDS: tuple[str, ...] = OPERATOR_FIVE_KEY_FIELDS

_KEY_COOLING_ZONE_FIELDS: tuple[str, ...] = (
    "zone_code",
    "zone_name",
    "temperature_level",
    "zone_area",
    "room_height",
    "wall_area",
    "roof_area",
    "floor_area",
    "outdoor_design_temperature",
    "room_design_temperature",
    "operating_hours_per_day",
    "product_mass_per_day",
    "product_entry_temperature",
    "product_target_temperature",
    "cooling_duration",
)

_OPTIONAL_COEFFICIENT_LEAVES: tuple[str, ...] = (
    "u_value_wall",
    "u_value_roof",
    "u_value_floor",
    "product_specific_heat",
)

_KEY_EQUIPMENT_SYSTEM_FIELDS: tuple[str, ...] = (
    "system_code",
    "system_name",
    "design_evaporating_temperature",
)

_KEY_EQUIPMENT_ZONE_FIELDS: tuple[str, ...] = (
    "zone_code",
    "zone_name",
    "evaporator_count",
    "defrost_method",
    "design_cooling_load_kw_r",
)

_KEY_POWER_FIELDS: tuple[str, ...] = (
    "compressor_input_power_kw_e",
    "evaporator_fan_power_kw_e",
    "condenser_fan_power_kw_e",
)

_KEY_INVESTMENT_FIELDS: tuple[str, ...] = (
    "total_area_m2",
    "refrigerated_area_m2",
    "frozen_area_m2",
    "position_count",
    "total_power_kw",
)

_KEY_IDENTITY_FIELDS: tuple[str, ...] = (
    "project_id",
    "project_version_id",
    "version_number",
    "version_status",
    "is_archived",
    "actor_principal",
    "correlation_id",
)


@dataclass(frozen=True, slots=True)
class BundleValidationError:
    code: str
    field_path: str
    message: str


class EngineeringInputBundleValidationError(Exception):
    """Fail-closed bundle validation error surfaced to callers."""

    def __init__(self, error: BundleValidationError) -> None:
        self.error = error
        super().__init__(error.message)


def validate_engineering_input_bundle(
    bundle: Mapping[str, Any],
    *,
    validation_mode: str = "full",
) -> None:
    """Validate ``EngineeringInputBundleV1`` and fail closed on KEY gaps.

    ``validation_mode``:
    - ``full``: require every KEY leaf at submit (V0.5/V0.6/V0.7 compatibility path).
    - ``operator_minimal``: allow lineage-pending leaves for operator-minimal assembly.
    """
    if validation_mode not in {"full", "operator_minimal"}:
        raise ValueError(f"unsupported validation_mode {validation_mode!r}")
    provenance = _input_group_provenance(bundle)
    _validate_schema_identity(bundle)
    _validate_project_version_identity(bundle)
    _validate_zone_planning_inputs(bundle, validation_mode=validation_mode)
    _validate_cooling_load_inputs(
        bundle,
        validation_mode=validation_mode,
        provenance=provenance,
    )
    _validate_equipment_inputs(
        bundle,
        validation_mode=validation_mode,
        provenance=provenance,
    )
    _validate_installed_power_inputs(
        bundle,
        validation_mode=validation_mode,
        provenance=provenance,
    )
    _validate_investment_inputs(
        bundle,
        validation_mode=validation_mode,
        provenance=provenance,
    )
    _validate_coefficient_context(bundle)
    _validate_units_metadata(bundle)
    _validate_source_metadata(bundle)
    _validate_review_metadata(bundle)


def bundle_payload_hash(bundle: Mapping[str, Any]) -> str:
    """Canonical hash of the validated bundle for idempotency comparisons."""
    from cold_storage.modules.orchestration.domain.fingerprint import result_hash

    return result_hash(dict(bundle))


def project_execution_snapshot_from_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Project bundle sections onto the five-stage execution snapshot shape."""
    validation_mode = (
        "operator_minimal"
        if _input_group_provenance(bundle).get("cooling_load_inputs")
        == "persisted_upstream_confirmed"
        else "full"
    )
    validate_engineering_input_bundle(bundle, validation_mode=validation_mode)
    coefficient_context = _coefficient_context_payload(bundle)
    return {
        "zone": _zone_stage_payload(bundle),
        "cooling_load": _cooling_load_stage_payload(bundle, coefficient_context),
        "equipment": _equipment_stage_payload(bundle, coefficient_context),
        "power": _power_stage_payload(bundle),
        "investment": _investment_stage_payload(bundle),
    }


def coefficient_context_from_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    validation_mode = (
        "operator_minimal"
        if _input_group_provenance(bundle).get("cooling_load_inputs")
        == "persisted_upstream_confirmed"
        else "full"
    )
    validate_engineering_input_bundle(bundle, validation_mode=validation_mode)
    return _coefficient_context_payload(bundle)


def assert_canonical_power_slot(calculator_name: str) -> None:
    """Reject supplemental ``power_configuration`` masquerading as canonical power."""
    if calculator_name == "power_configuration":
        raise EngineeringInputBundleValidationError(
            BundleValidationError(
                code="INVALID_CANONICAL_POWER_SLOT",
                field_path="canonical_power_slot.calculator_name",
                message=(
                    "power_configuration cannot satisfy the canonical power stage; "
                    "only installed_power is allowed"
                ),
            )
        )
    if calculator_name != CALCULATOR_BINDINGS["power"]:
        raise EngineeringInputBundleValidationError(
            BundleValidationError(
                code="INVALID_CANONICAL_POWER_SLOT",
                field_path="canonical_power_slot.calculator_name",
                message=f"canonical power slot requires {CALCULATOR_BINDINGS['power']!r}",
            )
        )


def _validate_schema_identity(bundle: Mapping[str, Any]) -> None:
    schema_id = _required_leaf(bundle, "schema_id", "schema_id")
    if schema_id != BUNDLE_SCHEMA_ID:
        _raise_missing("schema_id", f"unsupported schema_id {schema_id!r}")
    schema_version = _required_leaf(bundle, "schema_version", "schema_version")
    if schema_version != BUNDLE_SCHEMA_VERSION:
        _raise_missing("schema_version", f"unsupported schema_version {schema_version!r}")


def _validate_project_version_identity(bundle: Mapping[str, Any]) -> None:
    identity = _require_section(bundle, "project_version_identity")
    for field_name in _KEY_IDENTITY_FIELDS:
        _required_leaf(identity, field_name, f"project_version_identity.{field_name}")


def _validate_zone_planning_inputs(
    bundle: Mapping[str, Any],
    *,
    validation_mode: str,
) -> None:
    section = _require_section(bundle, "zone_planning_inputs")
    for field_name in _KEY_ZONE_FIELDS:
        _required_numeric_leaf(section, field_name, f"zone_planning_inputs.{field_name}")


def _validate_cooling_load_inputs(
    bundle: Mapping[str, Any],
    *,
    validation_mode: str,
    provenance: dict[str, str],
) -> None:
    section = _require_section(bundle, "cooling_load_inputs")
    zones = _required_leaf(section, "zones", "cooling_load_inputs.zones")
    if not isinstance(zones, list) or not zones:
        _raise_missing(
            "cooling_load_inputs.zones", "cooling_load_inputs.zones must be a non-empty array"
        )
    _required_leaf(section, "coefficients", "cooling_load_inputs.coefficients")
    coefficient_context = bundle.get("coefficient_context", {})
    lineage_deferred = (
        validation_mode == "operator_minimal"
        and provenance.get("cooling_load_inputs") == "persisted_upstream_confirmed"
    )
    for index, zone in enumerate(zones):
        if not isinstance(zone, dict):
            _raise_missing(f"cooling_load_inputs.zones[{index}]", "zone entry must be an object")
        prefix = f"cooling_load_inputs.zones[{index}]"
        for field_name in (
            "zone_code",
            "zone_name",
            "temperature_level",
        ):
            if lineage_deferred and field_name in _LINEAGE_DEFERRED_COOLING_FIELDS:
                _require_lineage_pending_or_provided(zone, field_name, f"{prefix}.{field_name}")
            else:
                _required_leaf(zone, field_name, f"{prefix}.{field_name}")
        for field_name in _KEY_COOLING_ZONE_FIELDS[3:]:
            if lineage_deferred and field_name in _LINEAGE_DEFERRED_COOLING_FIELDS:
                _require_lineage_pending_or_provided(zone, field_name, f"{prefix}.{field_name}")
            else:
                _required_numeric_leaf(zone, field_name, f"{prefix}.{field_name}")
        for coeff_name in _OPTIONAL_COEFFICIENT_LEAVES:
            _require_explicit_or_coefficient_context(
                zone,
                coeff_name,
                f"{prefix}.{coeff_name}",
                coefficient_context,
            )


def _validate_equipment_inputs(
    bundle: Mapping[str, Any],
    *,
    validation_mode: str,
    provenance: dict[str, str],
) -> None:
    section = _require_section(bundle, "equipment_inputs")
    systems = _required_leaf(section, "systems", "equipment_inputs.systems")
    if not isinstance(systems, list) or not systems:
        _raise_missing(
            "equipment_inputs.systems", "equipment_inputs.systems must be a non-empty array"
        )
    _required_leaf(section, "coefficients", "equipment_inputs.coefficients")
    _required_numeric_leaf(
        section,
        "condensing_temperature_c",
        "equipment_inputs.condensing_temperature_c",
    )
    for sys_index, system in enumerate(systems):
        if not isinstance(system, dict):
            _raise_missing(
                f"equipment_inputs.systems[{sys_index}]", "system entry must be an object"
            )
        prefix = f"equipment_inputs.systems[{sys_index}]"
        for field_name in _KEY_EQUIPMENT_SYSTEM_FIELDS[:2]:
            _required_leaf(system, field_name, f"{prefix}.{field_name}")
        _required_numeric_leaf(
            system,
            _KEY_EQUIPMENT_SYSTEM_FIELDS[2],
            f"{prefix}.{_KEY_EQUIPMENT_SYSTEM_FIELDS[2]}",
        )
        zones = system.get("zones")
        if not isinstance(zones, list) or not zones:
            _raise_missing(f"{prefix}.zones", f"{prefix}.zones must be a non-empty array")
        for zone_index, zone in enumerate(zones):
            if not isinstance(zone, dict):
                _raise_missing(f"{prefix}.zones[{zone_index}]", "zone entry must be an object")
            zone_prefix = f"{prefix}.zones[{zone_index}]"
            for field_name in _KEY_EQUIPMENT_ZONE_FIELDS[:3]:
                if field_name == "evaporator_count":
                    _required_numeric_leaf(zone, field_name, f"{zone_prefix}.{field_name}")
                else:
                    _required_leaf(zone, field_name, f"{zone_prefix}.{field_name}")
            _required_leaf(zone, _KEY_EQUIPMENT_ZONE_FIELDS[3], f"{zone_prefix}.defrost_method")
            load_field = _KEY_EQUIPMENT_ZONE_FIELDS[4]
            if (
                validation_mode == "operator_minimal"
                and provenance.get("equipment_inputs") == "persisted_upstream_confirmed"
                and load_field == "design_cooling_load_kw_r"
            ):
                _require_lineage_pending_or_provided(
                    zone, load_field, f"{zone_prefix}.{load_field}"
                )
            else:
                _required_numeric_leaf(zone, load_field, f"{zone_prefix}.{load_field}")


def _validate_installed_power_inputs(
    bundle: Mapping[str, Any],
    *,
    validation_mode: str,
    provenance: dict[str, str],
) -> None:
    section = _require_section(bundle, "installed_power_inputs")
    for field_name in _KEY_POWER_FIELDS:
        if (
            validation_mode == "operator_minimal"
            and provenance.get("installed_power_inputs") == "persisted_upstream_confirmed"
            and field_name == "compressor_input_power_kw_e"
        ):
            _require_lineage_pending_or_provided(
                section,
                field_name,
                f"installed_power_inputs.{field_name}",
            )
        else:
            _required_numeric_leaf(section, field_name, f"installed_power_inputs.{field_name}")


def _validate_investment_inputs(
    bundle: Mapping[str, Any],
    *,
    validation_mode: str,
    provenance: dict[str, str],
) -> None:
    section = _require_section(bundle, "investment_inputs")
    lineage_deferred = (
        validation_mode == "operator_minimal"
        and provenance.get("investment_inputs") == "persisted_upstream_confirmed"
    )
    for field_name in _KEY_INVESTMENT_FIELDS:
        if lineage_deferred:
            _require_lineage_pending_or_provided(
                section,
                field_name,
                f"investment_inputs.{field_name}",
            )
        else:
            _required_numeric_leaf(section, field_name, f"investment_inputs.{field_name}")


def _validate_coefficient_context(bundle: Mapping[str, Any]) -> None:
    section = _require_section(bundle, "coefficient_context")
    _required_leaf(section, "coefficient_context_id", "coefficient_context.coefficient_context_id")
    _required_leaf(
        section,
        "approved_revision_ids",
        "coefficient_context.approved_revision_ids",
    )


def _validate_units_metadata(bundle: Mapping[str, Any]) -> None:
    section = _require_section(bundle, "units_metadata")
    _required_leaf(section, "leaf_unit_by_path", "units_metadata.leaf_unit_by_path")


def _validate_source_metadata(bundle: Mapping[str, Any]) -> None:
    section = _require_section(bundle, "source_metadata")
    _required_leaf(
        section,
        "input_group_provenance",
        "source_metadata.input_group_provenance",
    )


def _validate_review_metadata(bundle: Mapping[str, Any]) -> None:
    section = _require_section(bundle, "review_metadata")
    _required_leaf(
        section,
        "overall_requires_review",
        "review_metadata.overall_requires_review",
    )
    _required_leaf(
        section,
        "per_group_requires_review",
        "review_metadata.per_group_requires_review",
    )


def _zone_stage_payload(bundle: Mapping[str, Any]) -> dict[str, Any]:
    section = bundle["zone_planning_inputs"]
    return {
        field_name: _decimalize(_required_numeric_leaf(section, field_name, field_name))
        for field_name in _KEY_ZONE_FIELDS
    }


def _cooling_load_stage_payload(
    bundle: Mapping[str, Any],
    coefficient_context: dict[str, Any],
) -> dict[str, Any]:
    section = bundle["cooling_load_inputs"]
    zones_out: list[dict[str, Any]] = []
    for zone in section["zones"]:
        assert isinstance(zone, dict)
        zone_out: dict[str, Any] = {
            "zone_code": _leaf_text(zone, "zone_code"),
            "zone_name": _leaf_text(zone, "zone_name"),
            "temperature_level": _leaf_text(zone, "temperature_level"),
        }
        for field_name in _KEY_COOLING_ZONE_FIELDS[3:]:
            zone_out[field_name] = _decimalize(_snapshot_numeric_leaf(zone, field_name, field_name))
        for coeff_name in _OPTIONAL_COEFFICIENT_LEAVES:
            value = _optional_leaf_value(zone, coeff_name, coefficient_context)
            if value is not None:
                zone_out[coeff_name] = _decimalize(value)
        zones_out.append(zone_out)
    coefficients = _leaf_value(section["coefficients"])
    coeff_payload = dict(coefficients) if isinstance(coefficients, dict) else {}
    coeff_payload.setdefault("revision_ids", {})
    coeff_payload.setdefault("source_types", {})
    coeff_payload.setdefault("revision_statuses", {})
    return {"zones": zones_out, "coefficients": coeff_payload}


def _equipment_stage_payload(
    bundle: Mapping[str, Any],
    coefficient_context: dict[str, Any],
) -> dict[str, Any]:
    section = bundle["equipment_inputs"]
    systems_out: list[dict[str, Any]] = []
    for system in section["systems"]:
        assert isinstance(system, dict)
        zones_out: list[dict[str, Any]] = []
        for zone in system.get("zones", []):
            assert isinstance(zone, dict)
            zones_out.append(
                {
                    "zone_code": _leaf_text(zone, "zone_code"),
                    "zone_name": _leaf_text(zone, "zone_name"),
                    "evaporator_count": int(
                        _required_numeric_leaf(zone, "evaporator_count", "evaporator_count")
                    ),
                    "defrost_method": _leaf_text(zone, "defrost_method"),
                    "design_cooling_load_kw_r": _decimalize(
                        _snapshot_numeric_leaf(
                            zone,
                            "design_cooling_load_kw_r",
                            "design_cooling_load_kw_r",
                        )
                    ),
                }
            )
        systems_out.append(
            {
                "system_code": _leaf_text(system, "system_code"),
                "system_name": _leaf_text(system, "system_name"),
                "design_evaporating_temperature": _decimalize(
                    _required_numeric_leaf(
                        system,
                        "design_evaporating_temperature",
                        "design_evaporating_temperature",
                    )
                ),
                "zones": zones_out,
            }
        )
    coefficients = _leaf_value(section["coefficients"])
    coeff_payload = dict(coefficients) if isinstance(coefficients, dict) else {}
    coeff_payload.setdefault("revision_ids", {})
    coeff_payload.setdefault("source_types", {})
    coeff_payload.setdefault("revision_statuses", {})
    del coefficient_context  # lineage coefficients are threaded per-stage, not auto-promoted
    return {
        "condensing_temperature_c": _decimalize(
            _required_numeric_leaf(
                section,
                "condensing_temperature_c",
                "equipment_inputs.condensing_temperature_c",
            )
        ),
        "systems": systems_out,
        "coefficients": coeff_payload,
    }


def _power_stage_payload(bundle: Mapping[str, Any]) -> dict[str, Any]:
    section = bundle["installed_power_inputs"]
    return {
        field_name: _decimalize(_snapshot_numeric_leaf(section, field_name, field_name))
        for field_name in _KEY_POWER_FIELDS
    }


def _investment_stage_payload(bundle: Mapping[str, Any]) -> dict[str, Any]:
    section = bundle["investment_inputs"]
    payload: dict[str, Any] = {}
    for field_name in _KEY_INVESTMENT_FIELDS:
        if field_name == "position_count":
            payload[field_name] = int(_snapshot_numeric_leaf(section, field_name, field_name))
        else:
            payload[field_name] = _decimalize(
                _snapshot_numeric_leaf(section, field_name, field_name)
            )
    return payload


def _coefficient_context_payload(bundle: Mapping[str, Any]) -> dict[str, Any]:
    section = bundle["coefficient_context"]
    demo_leaves = section.get("demo_coefficient_leaves", [])
    coefficients: list[dict[str, Any]] = []
    if isinstance(demo_leaves, list):
        for leaf in demo_leaves:
            if isinstance(leaf, dict):
                coefficients.append(dict(leaf))
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "coefficient_context_id": _leaf_text(section, "coefficient_context_id"),
        "approved_revision_ids": _leaf_value(section["approved_revision_ids"]),
        "coefficients": coefficients,
        "source_type": "demo",
        "validity_status": "unverified",
        "requires_review": True,
    }


def _require_section(bundle: Mapping[str, Any], name: str) -> dict[str, Any]:
    section = bundle.get(name)
    if not isinstance(section, dict):
        _raise_missing(name, f"missing required section {name!r}")
    return section


def _required_leaf(section: Mapping[str, Any], field_name: str, field_path: str) -> Any:
    if field_name not in section:
        _raise_missing(field_path)
    leaf = section[field_name]
    if _is_bundle_leaf(leaf):
        if leaf.get("state") == "missing":
            _raise_missing(field_path)
        value = leaf.get("value")
        if value is None and leaf.get("state") != "provided":
            _raise_missing(field_path)
        return value
    if leaf is None:
        _raise_missing(field_path)
    return leaf


def _required_numeric_leaf(section: Mapping[str, Any], field_name: str, field_path: str) -> Any:
    if field_name not in section:
        _raise_missing(field_path)
    leaf = section[field_name]
    if not _is_bundle_leaf(leaf):
        _raise_missing(field_path)
    if leaf.get("state") == "missing":
        _raise_missing(field_path)
    unit = leaf.get("unit")
    if unit in (None, ""):
        _raise_missing(f"{field_path}.unit", "required numeric leaf missing canonical unit")
    value = leaf.get("value")
    if value is None:
        _raise_missing(field_path)
    return value


def _optional_leaf_value(
    section: Mapping[str, Any],
    field_name: str,
    coefficient_context: Mapping[str, Any],
) -> Any | None:
    if field_name in section:
        leaf = section[field_name]
        if _is_bundle_leaf(leaf):
            if leaf.get("state") == "provided":
                return leaf.get("value")
            if leaf.get("state") != "missing":
                return leaf.get("value")
    for demo_leaf in coefficient_context.get("demo_coefficient_leaves", []):
        if isinstance(demo_leaf, dict) and demo_leaf.get("code") == field_name:
            return demo_leaf.get("value")
    for coeff in coefficient_context.get("coefficients", []):
        if isinstance(coeff, dict) and coeff.get("code") == field_name:
            return coeff.get("value")
    return None


def _require_explicit_or_coefficient_context(
    section: Mapping[str, Any],
    field_name: str,
    field_path: str,
    coefficient_context: Mapping[str, Any],
) -> None:
    if field_name in section:
        leaf = section[field_name]
        if _is_bundle_leaf(leaf) and leaf.get("state") == "provided":
            unit = leaf.get("unit")
            if unit in (None, ""):
                _raise_missing(f"{field_path}.unit")
            return
    resolved = _optional_leaf_value(section, field_name, coefficient_context)
    if resolved is None:
        _raise_missing(field_path)


def _leaf_value(node: Any) -> Any:
    if _is_bundle_leaf(node):
        return node.get("value")
    return node


def _leaf_text(section: Mapping[str, Any], field_name: str) -> str:
    if field_name in section:
        leaf = section[field_name]
        if _is_bundle_leaf(leaf) and leaf.get("state") == LINEAGE_PENDING_STATE:
            expected = section.get("_assembler_expected_zone_code")
            if isinstance(expected, str) and field_name == "zone_code":
                return expected
            return ""
    value = _required_leaf(section, field_name, field_name)
    return str(value)


def _snapshot_numeric_leaf(section: Mapping[str, Any], field_name: str, field_path: str) -> Any:
    if field_name in section:
        leaf = section[field_name]
        if _is_bundle_leaf(leaf) and leaf.get("state") == LINEAGE_PENDING_STATE:
            return "0"
    return _required_numeric_leaf(section, field_name, field_path)


def _is_bundle_leaf(node: Any) -> bool:
    return isinstance(node, dict) and "state" in node and "value" in node


def _require_lineage_pending_or_provided(
    section: Mapping[str, Any],
    field_name: str,
    field_path: str,
) -> None:
    if field_name not in section:
        _raise_missing(field_path)
    leaf = section[field_name]
    if not _is_bundle_leaf(leaf):
        _raise_missing(field_path)
    state = leaf.get("state")
    if state == LINEAGE_PENDING_STATE:
        unit = leaf.get("unit")
        unit_optional = field_name in {
            "zone_code",
            "zone_name",
            "temperature_level",
            "defrost_method",
        }
        if unit in (None, "") and not unit_optional:
            _raise_missing(f"{field_path}.unit")
        return
    if state == "missing":
        _raise_missing(field_path)
    if leaf.get("value") is None:
        _raise_missing(field_path)


def _input_group_provenance(bundle: Mapping[str, Any]) -> dict[str, str]:
    source_metadata = bundle.get("source_metadata")
    if not isinstance(source_metadata, dict):
        return {}
    provenance = source_metadata.get("input_group_provenance")
    if not isinstance(provenance, dict):
        return {}
    return {str(key): str(value) for key, value in provenance.items()}


def _decimalize(value: Any) -> str | Any:
    if isinstance(value, Decimal):
        normalized = value.normalize()
        exponent = normalized.as_tuple().exponent
        return (
            str(int(normalized)) if isinstance(exponent, int) and exponent > 0 else str(normalized)
        )
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        normalized = Decimal(str(value)).normalize()
        exponent = normalized.as_tuple().exponent
        return (
            str(int(normalized)) if isinstance(exponent, int) and exponent > 0 else str(normalized)
        )
    return value


def _raise_missing(field_path: str, message: str | None = None) -> NoReturn:
    raise EngineeringInputBundleValidationError(
        BundleValidationError(
            code=MissingEngineeringParameterError.code,
            field_path=field_path,
            message=message or f"missing required engineering parameter at {field_path}",
        )
    )
