"""Detect persisted V0.9 operator five KEY without importing calculators."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.projects.application.engineering_input_bundle import (
    BUNDLE_SCHEMA_ID,
    OPERATOR_PROCESS_SCHEMA_ID,
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

_ZONE_CALCULATOR_NAME = "cold_room_zone_plan"


def v09_five_keys_are_present(
    *,
    inputs: Mapping[str, Any],
    calc_by_name: Mapping[str, Mapping[str, Any]] | None = None,
) -> bool:
    """Return True when V0.9 five KEY exist on snapshot, bundle, or zone run."""
    if not missing_v09_five_key_fields(inputs):
        return True
    if calc_by_name is None:
        return False
    return _v09_keys_from_zone_calculation(calc_by_name)


def missing_v09_five_key_fields(inputs: Mapping[str, Any]) -> list[str]:
    """Return V0.9 KEY names that are absent from an operator-shaped snapshot."""
    section = _zone_planning_section(inputs)
    if section is None:
        return list(OPERATOR_V09_FIVE_KEY_FIELDS)
    missing: list[str] = []
    for field_name in OPERATOR_V09_FIVE_KEY_FIELDS:
        if not _leaf_has_numeric_value(section.get(field_name)):
            missing.append(field_name)
    return missing


def _zone_planning_section(inputs: Mapping[str, Any]) -> Mapping[str, Any] | None:
    nested = inputs.get("zone_planning_inputs")
    if not isinstance(nested, dict):
        return None
    schema_id = inputs.get("schema_id")
    schema_version = inputs.get("schema_version")
    if schema_id == BUNDLE_SCHEMA_ID:
        return nested
    if schema_id == OPERATOR_PROCESS_SCHEMA_ID:
        if schema_version == "1.0.0":
            return None
        return nested
    if schema_id is None and _looks_like_v09_zone_section(nested):
        return nested
    return None


def _looks_like_v09_zone_section(section: Mapping[str, Any]) -> bool:
    return all(field_name in section for field_name in OPERATOR_V09_FIVE_KEY_FIELDS)


def _v09_keys_from_zone_calculation(
    calc_by_name: Mapping[str, Mapping[str, Any]],
) -> bool:
    record = calc_by_name.get(_ZONE_CALCULATOR_NAME)
    if not isinstance(record, Mapping):
        return False
    snapshot = record.get("input_snapshot")
    if not isinstance(snapshot, Mapping):
        return False
    if not missing_v09_five_key_fields(snapshot):
        return True
    return all(
        _leaf_has_numeric_value(snapshot.get(field)) for field in OPERATOR_V09_FIVE_KEY_FIELDS
    )


def _leaf_has_numeric_value(leaf: object) -> bool:
    if leaf is None:
        return False
    if isinstance(leaf, dict):
        if leaf.get("state") == "missing":
            return False
        value = leaf.get("value")
        return value is not None and value != ""
    if isinstance(leaf, str):
        return leaf.strip() != ""
    return True
