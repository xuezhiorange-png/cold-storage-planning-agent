"""Project-owned truck inputs; completeness is never route feasibility."""

import re
from collections.abc import Mapping
from decimal import Context, Decimal, localcontext
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import (
    GRID,
    LayoutAuthorityError,
    canonical_json,
    decimal_value,
)

IDENTITY = "truck-project-access-input@1.0.0"
SCHEMA_VERSION = "1.0.0"
LENGTH_FIELDS = ("vehicle_width_m", "vehicle_length_m")
REFERENCE_FIELDS = ("turning_envelope", "straight_approach", "loading_operation_clearance")
FIELDS = ("schema_version", "project_id", "source_authority", *LENGTH_FIELDS, *REFERENCE_FIELDS)
REFERENCE_KEYS = (
    "schema_version",
    "source_authority",
    "project_id",
    "reference",
    "content_sha256",
    "provided_by",
)


def _missing(value: Mapping[str, Any], fields: tuple[str, ...], prefix: str = "") -> list[str]:
    return [f"{prefix}{field}" for field in fields if field not in value or value[field] is None]


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _length(value: object) -> Decimal:
    # Wire lengths are JSON numbers, not booleans or implicit string conversions.
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise LayoutAuthorityError("INVALID_PROJECT_TRUCK_INPUT")
    number = decimal_value(value, positive=True)
    with localcontext(Context(prec=80)):
        if number % GRID:
            raise LayoutAuthorityError("INVALID_PROJECT_TRUCK_INPUT")
    return number


def validate_project_truck_input(source: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate explicit project evidence only; no registry, fallback or file/network lookup.

    Three evidence slots preserve the P1E names. No approved scalar/axis or solver
    representation exists for these clear envelopes in that historical contract.
    Hashes identify supplied documents; this function does not authenticate them.
    """
    result: dict[str, Any] = {
        "input_contract_identity": IDENTITY,
        "project_truck_input_complete": False,
        "project_layout_ready": False,
        "project_layout_validated": False,
        "truck_route_validated": False,
        "final_layout_pass_allowed": False,
        "p2a_truck_turning_representation_decision_required": True,
        "requires_review": True,
        "evidence_contents_verified": False,
    }

    def required(fields: list[str]) -> dict[str, Any]:
        return {**result, "status": "PROJECT_INPUT_REQUIRED", "missing_fields": fields}

    def invalid(field: str) -> dict[str, Any]:
        return {**result, "status": "INVALID_PROJECT_TRUCK_INPUT", "field": field}

    if source is None:
        return required(list(FIELDS))
    if not isinstance(source, Mapping):
        return invalid("truck_access")
    if set(source) - set(FIELDS):
        return invalid("unknown_fields")
    missing = _missing(source, FIELDS)
    if missing:
        return required(missing)
    if source["schema_version"] != SCHEMA_VERSION or source["source_authority"] != "PROJECT_INPUT":
        return invalid("schema_version/source_authority")
    if not _text(source["project_id"]):
        return invalid("project_id")
    normalized: dict[str, Any] = dict(source)
    for field in LENGTH_FIELDS:
        try:
            normalized[field] = _length(source[field])
        except LayoutAuthorityError:
            return invalid(field)
    for field in REFERENCE_FIELDS:
        ref = source[field]
        if not isinstance(ref, Mapping) or set(ref) - set(REFERENCE_KEYS):
            return invalid(field)
        missing = _missing(ref, REFERENCE_KEYS, f"{field}.")
        if missing:
            return required(missing)
        if (
            ref["schema_version"] != SCHEMA_VERSION
            or ref["source_authority"] != "PROJECT_INPUT"
            or ref["project_id"] != source["project_id"]
            or not _text(ref["reference"])
            or not _text(ref["provided_by"])
            or not isinstance(ref["content_sha256"], str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", ref["content_sha256"])
        ):
            return invalid(field)
        normalized[field] = dict(ref)
    return {
        **result,
        "status": "COMPLETE",
        "project_truck_input_complete": True,
        "value_source": "PROJECT_INPUT",
        "validated_input_canonical_json": canonical_json(normalized),
    }
