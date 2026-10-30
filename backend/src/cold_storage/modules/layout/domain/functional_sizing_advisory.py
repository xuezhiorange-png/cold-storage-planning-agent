"""Immutable conditional advice; never a P1 authority or solver instruction."""

import json
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import canonical_hash, canonical_json

IDENTITY = "functional-room-sizing-advisory@1.0.0"
SCHEMA_VERSION = "1.0.0"
CLASSIFICATIONS = (
    "OWNER_CONFIRMED",
    "ENGINEERING_DERIVED",
    "HYPOTHETICAL_NOT_APPROVED",
    "INPUT_REQUIRED",
    "NOT_EVALUATED",
)
APPROVAL_BOUNDARY = MappingProxyType(
    {
        "actual_functional_status": "INPUT_REQUIRED",
        "engineering_approval": "NOT_EVALUATED",
        "whole_factory_fit": "NOT_EVALUATED",
        "authority_effect": "NONE",
        "solver_consumption": "FORBIDDEN_PREVIEW_ONLY",
    }
)
FIELDS = frozenset(
    {
        "identity",
        "schema_version",
        "project",
        "physical_room",
        "p1_requirement",
        "original_room",
        "advised_room",
        "conditions",
        "functional_evidence",
        "margins",
        "external_impact",
        "owner_confirmation_checklist",
        "sources",
        "invalidation_conditions",
        "approval_boundary",
        "comparison_scope",
        "units",
        "calculation_basis",
    }
)


@dataclass(frozen=True)
class FunctionalRoomSizingAdvisoryV1:
    """Canonical value object. Applicability still requires the application precheck.

    A matching hash is content integrity, not approval. Deserializing an arbitrary
    value does not establish evidence or make it suitable for a planning project.
    """

    payload_json: str

    def __post_init__(self) -> None:
        body = json.loads(self.payload_json)
        if (
            not isinstance(body, dict)
            or set(body) != FIELDS
            or body["identity"] != IDENTITY
            or body["schema_version"] != SCHEMA_VERSION
        ):
            raise ValueError("FUNCTIONAL_ADVISORY_SCHEMA_UNSUPPORTED")
        if body["approval_boundary"] != APPROVAL_BOUNDARY:
            raise ValueError("FUNCTIONAL_ADVISORY_APPROVAL_FORBIDDEN")
        if body["conditions"].get("classification") != "HYPOTHETICAL_NOT_APPROVED":
            raise ValueError("FUNCTIONAL_ADVISORY_CONDITION_APPROVAL_FORBIDDEN")
        if body["p1_requirement"].get("modifies_authority") is not False:
            raise ValueError("FUNCTIONAL_ADVISORY_P1_MUTATION_FORBIDDEN")
        if body["physical_room"].get("room_code") != "changing_room":
            raise ValueError("FUNCTIONAL_ADVISORY_ADAPTER_UNSUPPORTED")
        if self.payload_json != canonical_json(body):
            raise ValueError("FUNCTIONAL_ADVISORY_CANONICAL_VALUE_REQUIRED")

    @property
    def canonical_result_hash(self) -> str:
        return canonical_hash(json.loads(self.payload_json))

    def to_dict(self) -> dict[str, Any]:
        return {**json.loads(self.payload_json), "advisory_hash": self.canonical_result_hash}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FunctionalRoomSizingAdvisoryV1":
        body = dict(value)
        claimed = body.pop("advisory_hash", None)
        result = cls(canonical_json(body))
        if claimed is not None and claimed != result.canonical_result_hash:
            raise ValueError("FUNCTIONAL_ADVISORY_HASH_MISMATCH")
        return result


def room_dimensions(bounds: list[int]) -> dict[str, Any]:
    """Integer-mm diagnostic, distinct from the original required P1 area."""
    if len(bounds) != 4 or any(type(v) is not int for v in bounds):
        raise ValueError("INTEGER_ROOM_BOUNDS_REQUIRED")
    width, depth = bounds[2] - bounds[0], bounds[3] - bounds[1]
    if width <= 0 or depth <= 0:
        raise ValueError("POSITIVE_ROOM_DIMENSIONS_REQUIRED")
    area = width * depth
    return dict(
        length_mm=width,
        width_mm=depth,
        area_mm2=area,
        area_m2=area_text(area),
        bounds_mm=list(bounds),
    )


def area_text(area_mm2: int) -> str:
    return format(Decimal(area_mm2) / Decimal(1_000_000), ".6f")


def advisory_json_schema() -> dict[str, Any]:
    """Interchange shape only; applicability must be checked against real evidence."""
    properties: dict[str, Any] = {k: {"type": "object"} for k in sorted(FIELDS)}
    properties.update(
        identity={"const": IDENTITY},
        schema_version={"const": SCHEMA_VERSION},
        advisory_hash={"type": "string", "pattern": "^sha256:[a-f0-9]{64}$"},
        sources={"type": "array", "minItems": 1},
        invalidation_conditions={"type": "array", "minItems": 1, "items": {"type": "string"}},
        owner_confirmation_checklist={"type": "array", "minItems": 1},
        approval_boundary={"const": dict(APPROVAL_BOUNDARY)},
        units={"type": "string"},
        conditions={
            "type": "object",
            "required": ["classification", "parameters", "approval"],
            "properties": {
                "classification": {"const": "HYPOTHETICAL_NOT_APPROVED"},
                "approval": {"const": "INPUT_REQUIRED"},
            },
        },
        physical_room={
            "type": "object",
            "required": ["id", "room_code", "room_count", "aliases"],
            "properties": {"room_code": {"const": "changing_room"}, "room_count": {"const": 1}},
        },
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:cold-storage:functional-room-sizing-advisory:1.0.0",
        "title": "FunctionalRoomSizingAdvisoryV1",
        "description": "Preview-only data. Schema/hash matching is not engineering approval.",
        "type": "object",
        "required": sorted(FIELDS | {"advisory_hash"}),
        "additionalProperties": False,
        "properties": properties,
    }
