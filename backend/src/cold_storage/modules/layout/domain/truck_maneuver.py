"""Project-supplied truck maneuver envelope contracts.

This module validates approved, versioned two-dimensional envelope templates and
provides an exact discrete transform.  It deliberately does not derive an
envelope from vehicle parameters, search for a route, or choose a placement.
The geometry boundary reuses the P2A local-Cartesian polygon primitive.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from typing import Any, cast

from cold_storage.modules.layout.domain.dimensioning import (
    GRID,
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
    decimal_value,
)
from cold_storage.modules.layout.domain.project_truck_input import (
    IDENTITY as P1F_TRUCK_INPUT_IDENTITY,
)
from cold_storage.modules.layout.domain.project_truck_input import (
    validate_project_truck_input,
)
from cold_storage.modules.layout.domain.site_geometry import (
    PolygonMM,
    normalize_polygon,
    polygon_to_dict,
)

CONTRACT_IDENTITY = "truck-maneuver-template-contract@1.0.0"
TEMPLATE_SCHEMA_VERSION = "1.0.0"
TEMPLATE_SET_SCHEMA_VERSION = "1.0.0"
REQUIREMENT_SCHEMA_VERSION = "1.0.0"
PROJECT_INPUT_SCHEMA_VERSION = "1.0.0"

TRUCK_REPRESENTATION = "OPTION_C_APPROVED_MANEUVER_TEMPLATES"
OWNER_APPROVED = True
DEFAULT_TRUCK_ALLOWED = False
DEFAULT_MANEUVER_GEOMETRY_ALLOWED = False
KINEMATIC_SOLVER_REQUIRED = False
P2_COMPLETE = False
P3_AUTHORIZED = False

COORDINATE_SYSTEM = "LOCAL_CARTESIAN_METERS"
GRID_M = GRID
REFERENCE_FRAME = "LOCAL_TEMPLATE_FRAME"
FORWARD_AXIS = "POSITIVE_X"
ORIGIN_REFERENCE = "ENTRY_REFERENCE_POINT"
DOCK_FACE_REFERENCE = "shipping_channel.LONG_EDGE_LOADING_FACE"

STRAIGHT_APPROACH = "STRAIGHT_APPROACH"
TURN_90 = "TURN_90"
DOCK_REVERSE = "DOCK_REVERSE"
SUPPORTED_MANEUVER_CLASSES = (STRAIGHT_APPROACH, TURN_90, DOCK_REVERSE)
MANEUVER_CLASSES = frozenset(SUPPORTED_MANEUVER_CLASSES)
MANEUVER_STRAIGHT_APPROACH = True
MANEUVER_90_DEGREE_TURN = True
MANEUVER_DOCK_REVERSE = True
SUPPORTED_TRANSFORM_ROTATIONS = (0, 90, 180, 270)

PROJECT_INPUT = "PROJECT_INPUT"
PROJECT_BINDING_SCHEMA_VERSION = "1.0.0"
P1F_INPUT_CONTRACT_IDENTITY = P1F_TRUCK_INPUT_IDENTITY

_TEMPLATE_KEYS = frozenset(
    {
        "schema_version",
        "project_id",
        "source_authority",
        "template_id",
        "maneuver_class",
        "vehicle_width_m",
        "vehicle_length_m",
        "envelope_geometry",
        "reference",
        "reference_frame",
        "content_sha256",
        "provided_by",
        "turn_direction",
        "dock_face_reference",
        "approach_pose",
        "final_dock_pose",
        "identity",
    }
)
_REFERENCE_KEYS = frozenset(
    {
        "reference_frame",
        "forward_axis",
        "origin_reference",
        "vehicle_reference_point",
        "entry_pose",
        "exit_pose",
    }
)
_POSE_KEYS = frozenset({"x", "y", "rotation_deg"})
_POINT_KEYS = frozenset({"x", "y"})
_SET_KEYS = frozenset(
    {
        "schema_version",
        "project_id",
        "source_authority",
        "templates",
        "content_sha256",
        "provided_by",
        "identity",
    }
)
_REQUIREMENT_KEYS = frozenset(
    {
        "schema_version",
        "project_id",
        "source_authority",
        "required_maneuver_classes",
        "content_sha256",
        "provided_by",
        "identity",
    }
)
_PROJECT_KEYS = frozenset(
    {
        "schema_version",
        "project_id",
        "source_authority",
        "template_set",
        "requirement",
        "content_sha256",
        "provided_by",
        "identity",
    }
)
_BINDING_KEYS = frozenset(
    {
        "schema_version",
        "project_id",
        "source_authority",
        "p1f_input_contract_identity",
        "p1f_input",
        "p1f_input_canonical_hash",
        "maneuver_project_input",
        "content_sha256",
        "provided_by",
        "identity",
    }
)
_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE", field=field)
    return value


def _hash(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None:
        raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE", field=field)
    return value


def _binding_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error("INVALID_TRUCK_MANEUVER_PROJECT_BINDING", field=field)
    return value


def _binding_hash(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None:
        raise _error("INVALID_TRUCK_MANEUVER_PROJECT_BINDING", field=field)
    return value


def _grid_number(value: object, *, field: str, positive: bool) -> Decimal:
    # Template wire values use the same exact decimal/grid boundary as P2A.
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE", field=field)
    try:
        number = decimal_value(value, positive=positive)
    except LayoutAuthorityError:
        raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE", field=field) from None
    with localcontext(Context(prec=80)):
        if number % GRID:
            raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE", field=field, grid_m=str(GRID_M))
    return number


def _coordinate(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise _error("INVALID_TRUCK_MANEUVER_REFERENCE", field=field)
    try:
        number = decimal_value(value)
    except LayoutAuthorityError:
        raise _error("INVALID_TRUCK_MANEUVER_REFERENCE", field=field) from None
    with localcontext(Context(prec=80)):
        if number % GRID:
            raise _error("INVALID_TRUCK_MANEUVER_REFERENCE", field=field, grid_m=str(GRID_M))
    return number


def _rotation(value: object, *, field: str, allowed: tuple[int, ...]) -> int:
    if type(value) is not int or value not in allowed:
        raise _error("INVALID_TRUCK_MANEUVER_REFERENCE", field=field)
    return value


def _point(value: object, *, field: str) -> dict[str, Decimal]:
    if not isinstance(value, Mapping) or set(value) != _POINT_KEYS:
        raise _error("INVALID_TRUCK_MANEUVER_REFERENCE", field=field)
    return {
        "x": _coordinate(value["x"], field=f"{field}.x"),
        "y": _coordinate(value["y"], field=f"{field}.y"),
    }


def _pose(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _POSE_KEYS:
        raise _error("INVALID_TRUCK_MANEUVER_REFERENCE", field=field)
    return {
        "x": _coordinate(value["x"], field=f"{field}.x"),
        "y": _coordinate(value["y"], field=f"{field}.y"),
        "rotation_deg": _rotation(
            value["rotation_deg"],
            field=f"{field}.rotation_deg",
            allowed=SUPPORTED_TRANSFORM_ROTATIONS,
        ),
    }


def _envelope(value: object) -> dict[str, Any]:
    try:
        polygon = normalize_polygon(
            value, error_code="INVALID_MANEUVER_ENVELOPE", allow_numeric_string=True
        )
    except LayoutAuthorityError as error:
        raise _error(
            "INVALID_MANEUVER_ENVELOPE",
            reason=error.details.get("reason", "INVALID_POLYGON"),
        ) from None
    return polygon_to_dict(polygon)


def _reference_frame(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REFERENCE_KEYS:
        raise _error("INVALID_TRUCK_MANEUVER_REFERENCE")
    if (
        value["reference_frame"] != REFERENCE_FRAME
        or value["forward_axis"] != FORWARD_AXIS
        or value["origin_reference"] != ORIGIN_REFERENCE
    ):
        raise _error("INVALID_TRUCK_MANEUVER_REFERENCE")
    frame = {
        "reference_frame": REFERENCE_FRAME,
        "forward_axis": FORWARD_AXIS,
        "origin_reference": ORIGIN_REFERENCE,
        "vehicle_reference_point": _point(
            value["vehicle_reference_point"], field="reference_frame.vehicle_reference_point"
        ),
        "entry_pose": _pose(value["entry_pose"], field="reference_frame.entry_pose"),
        "exit_pose": _pose(value["exit_pose"], field="reference_frame.exit_pose"),
    }
    if frame["vehicle_reference_point"] != {"x": Decimal("0"), "y": Decimal("0")} or frame[
        "entry_pose"
    ] != {"x": Decimal("0"), "y": Decimal("0"), "rotation_deg": 0}:
        raise _error(
            "INVALID_TRUCK_MANEUVER_REFERENCE",
            reason="ENTRY_REFERENCE_ORIGIN_REQUIRED",
        )
    return frame


def _content_payload(normalized: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in normalized.items() if key not in {"identity", "content_sha256"}
    }


def _decode_template_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    """Materialize canonical numeric strings as Decimal values for revalidation."""
    body = dict(value)
    for field in ("vehicle_width_m", "vehicle_length_m"):
        if field in body and isinstance(body[field], str):
            body[field] = Decimal(body[field])
    geometry = body.get("envelope_geometry")
    if isinstance(geometry, Mapping):
        points = geometry.get("points")
        if isinstance(points, list):
            body["envelope_geometry"] = {
                **geometry,
                "points": [
                    {
                        **point,
                        "x": Decimal(point["x"])
                        if isinstance(point.get("x"), str)
                        else point.get("x"),
                        "y": Decimal(point["y"])
                        if isinstance(point.get("y"), str)
                        else point.get("y"),
                    }
                    for point in points
                ],
            }
    frame = body.get("reference_frame")
    if isinstance(frame, Mapping):
        frame_body = dict(frame)
        point = frame_body.get("vehicle_reference_point")
        if isinstance(point, Mapping):
            frame_body["vehicle_reference_point"] = {
                **point,
                "x": Decimal(point["x"]) if isinstance(point.get("x"), str) else point.get("x"),
                "y": Decimal(point["y"]) if isinstance(point.get("y"), str) else point.get("y"),
            }
        for field in ("entry_pose", "exit_pose"):
            pose = frame_body.get(field)
            if isinstance(pose, Mapping):
                frame_body[field] = {
                    **pose,
                    "x": Decimal(pose["x"]) if isinstance(pose.get("x"), str) else pose.get("x"),
                    "y": Decimal(pose["y"]) if isinstance(pose.get("y"), str) else pose.get("y"),
                }
        body["reference_frame"] = frame_body
    for field in ("approach_pose", "final_dock_pose"):
        pose = body.get(field)
        if isinstance(pose, Mapping):
            body[field] = {
                **pose,
                "x": Decimal(pose["x"]) if isinstance(pose.get("x"), str) else pose.get("x"),
                "y": Decimal(pose["y"]) if isinstance(pose.get("y"), str) else pose.get("y"),
            }
    return body


def _decode_template_set_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(value)
    raw_templates = body.get("templates")
    if isinstance(raw_templates, list):
        body["templates"] = [
            _decode_template_payload(template)
            for template in raw_templates
            if isinstance(template, Mapping)
        ]
    return body


def _template_identity(project_id: str, template_id: str) -> str:
    return f"truck-maneuver-template:{project_id}:{template_id}@{TEMPLATE_SCHEMA_VERSION}"


def _normalize_template(source: Mapping[str, Any], *, require_hash: bool) -> dict[str, Any]:
    if set(source) - _TEMPLATE_KEYS:
        raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE", field="unknown_fields")
    required = {
        "schema_version",
        "project_id",
        "source_authority",
        "template_id",
        "maneuver_class",
        "vehicle_width_m",
        "vehicle_length_m",
        "envelope_geometry",
        "reference",
        "reference_frame",
        "provided_by",
    }
    missing = sorted(required - set(source))
    if missing:
        raise _error("TRUCK_MANEUVER_TEMPLATE_REQUIRED", missing_fields=missing)
    if source["schema_version"] != TEMPLATE_SCHEMA_VERSION:
        raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE", field="schema_version")
    if source["source_authority"] != PROJECT_INPUT:
        raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE", field="source_authority")
    project_id = _text(source["project_id"], field="project_id")
    template_id = _text(source["template_id"], field="template_id")
    maneuver_class = source["maneuver_class"]
    if not isinstance(maneuver_class, str) or maneuver_class not in MANEUVER_CLASSES:
        raise _error(
            "UNAUTHORIZED_TRUCK_MANEUVER_CLASS",
            maneuver_class=maneuver_class,
            allowed_classes=list(SUPPORTED_MANEUVER_CLASSES),
        )
    normalized: dict[str, Any] = {
        "schema_version": TEMPLATE_SCHEMA_VERSION,
        "project_id": project_id,
        "source_authority": PROJECT_INPUT,
        "template_id": template_id,
        "maneuver_class": maneuver_class,
        "vehicle_width_m": _grid_number(
            source["vehicle_width_m"], field="vehicle_width_m", positive=True
        ),
        "vehicle_length_m": _grid_number(
            source["vehicle_length_m"], field="vehicle_length_m", positive=True
        ),
        "envelope_geometry": _envelope(source["envelope_geometry"]),
        "reference": _text(source["reference"], field="reference"),
        "reference_frame": _reference_frame(source["reference_frame"]),
        "provided_by": _text(source["provided_by"], field="provided_by"),
    }
    if maneuver_class == TURN_90:
        direction = source.get("turn_direction")
        if direction not in {"LEFT", "RIGHT"}:
            raise _error("TURN_DIRECTION_REQUIRED", maneuver_class=maneuver_class)
        normalized["turn_direction"] = direction
    elif "turn_direction" in source:
        raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE", field="turn_direction")

    if maneuver_class == DOCK_REVERSE:
        dock_fields = {"dock_face_reference", "approach_pose", "final_dock_pose"}
        missing_dock_fields = sorted(dock_fields - set(source))
        if missing_dock_fields:
            raise _error("DOCK_REVERSE_REFERENCE_REQUIRED", missing_fields=missing_dock_fields)
        if source["dock_face_reference"] != DOCK_FACE_REFERENCE:
            raise _error(
                "DOCK_FACE_REFERENCE_MISMATCH",
                expected=DOCK_FACE_REFERENCE,
            )
        normalized["dock_face_reference"] = DOCK_FACE_REFERENCE
        normalized["approach_pose"] = _pose(source["approach_pose"], field="approach_pose")
        normalized["final_dock_pose"] = _pose(source["final_dock_pose"], field="final_dock_pose")
    elif any(
        field in source for field in ("dock_face_reference", "approach_pose", "final_dock_pose")
    ):
        raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE", field="dock_reverse_fields")

    identity = _template_identity(project_id, template_id)
    if "identity" in source and source["identity"] != identity:
        raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE", field="identity")
    normalized["identity"] = identity
    # This is a digest supplied by the project for its source material.  It is
    # deliberately not derived from the normalized template in this module.
    normalized["content_sha256"] = _hash(source.get("content_sha256"), field="content_sha256")
    return normalized


def maneuver_template_payload_with_hash(source: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a template with a project-supplied source-material digest."""
    return _normalize_template(source, require_hash=False)


def maneuver_template_content_hash(source: Mapping[str, Any]) -> str:
    """Return the project-supplied source-material digest."""
    return cast(str, maneuver_template_payload_with_hash(source)["content_sha256"])


def maneuver_template_canonical_hash(source: Mapping[str, Any]) -> str:
    """Return the derived integrity hash of the complete template."""
    return validate_truck_maneuver_template(source).canonical_template_hash


@dataclass(frozen=True, init=False)
class TruckManeuverTemplateV1:
    """Validated immutable serialization of one project maneuver template."""

    payload_json: str

    def __init__(
        self,
        schema_version: str,
        project_id: str,
        source_authority: str,
        template_id: str,
        maneuver_class: str,
        vehicle_width_m: object,
        vehicle_length_m: object,
        envelope_geometry: Mapping[str, Any],
        reference: str,
        reference_frame: Mapping[str, Any],
        content_sha256: str,
        provided_by: str,
        turn_direction: str | None = None,
        dock_face_reference: str | None = None,
        approach_pose: Mapping[str, Any] | None = None,
        final_dock_pose: Mapping[str, Any] | None = None,
    ) -> None:
        source: dict[str, Any] = {
            "schema_version": schema_version,
            "project_id": project_id,
            "source_authority": source_authority,
            "template_id": template_id,
            "maneuver_class": maneuver_class,
            "vehicle_width_m": vehicle_width_m,
            "vehicle_length_m": vehicle_length_m,
            "envelope_geometry": envelope_geometry,
            "reference": reference,
            "reference_frame": reference_frame,
            "content_sha256": content_sha256,
            "provided_by": provided_by,
        }
        if turn_direction is not None:
            source["turn_direction"] = turn_direction
        if dock_face_reference is not None:
            source["dock_face_reference"] = dock_face_reference
        if approach_pose is not None:
            source["approach_pose"] = approach_pose
        if final_dock_pose is not None:
            source["final_dock_pose"] = final_dock_pose
        object.__setattr__(
            self, "payload_json", canonical_json(_normalize_template(source, require_hash=True))
        )

    @classmethod
    def _from_normalized(cls, normalized: Mapping[str, Any]) -> TruckManeuverTemplateV1:
        obj = object.__new__(cls)
        object.__setattr__(obj, "payload_json", canonical_json(dict(normalized)))
        return obj

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> TruckManeuverTemplateV1:
        if not isinstance(source, Mapping):
            raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE")
        return cls._from_normalized(_normalize_template(source, require_hash=True))

    @property
    def identity(self) -> str:
        return cast(str, self.to_dict()["identity"])

    @property
    def schema_version(self) -> str:
        return cast(str, self.to_dict()["schema_version"])

    @property
    def source_authority(self) -> str:
        return cast(str, self.to_dict()["source_authority"])

    @property
    def project_id(self) -> str:
        return cast(str, self.to_dict()["project_id"])

    @property
    def template_id(self) -> str:
        return cast(str, self.to_dict()["template_id"])

    @property
    def maneuver_class(self) -> str:
        return cast(str, self.to_dict()["maneuver_class"])

    @property
    def vehicle_width_m(self) -> Decimal:
        return cast(Decimal, self.to_dict()["vehicle_width_m"])

    @property
    def vehicle_length_m(self) -> Decimal:
        return cast(Decimal, self.to_dict()["vehicle_length_m"])

    @property
    def envelope_geometry(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.to_dict()["envelope_geometry"])

    @property
    def reference(self) -> str:
        return cast(str, self.to_dict()["reference"])

    @property
    def reference_frame(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.to_dict()["reference_frame"])

    @property
    def provided_by(self) -> str:
        return cast(str, self.to_dict()["provided_by"])

    @property
    def turn_direction(self) -> str | None:
        return cast(str | None, self.to_dict().get("turn_direction"))

    @property
    def dock_face_reference(self) -> str | None:
        return cast(str | None, self.to_dict().get("dock_face_reference"))

    @property
    def approach_pose(self) -> dict[str, Any] | None:
        return cast(dict[str, Any] | None, self.to_dict().get("approach_pose"))

    @property
    def final_dock_pose(self) -> dict[str, Any] | None:
        return cast(dict[str, Any] | None, self.to_dict().get("final_dock_pose"))

    @property
    def content_sha256(self) -> str:
        return cast(str, self.to_dict()["content_sha256"])

    def to_dict(self) -> dict[str, Any]:
        return _decode_template_payload(cast(dict[str, Any], json.loads(self.payload_json)))

    def canonical_json(self) -> str:
        return self.payload_json

    @property
    def canonical_result_hash(self) -> str:
        return self.canonical_template_hash

    @property
    def canonical_template_hash(self) -> str:
        """Integrity hash of the complete normalized template serialization."""
        return canonical_hash(self.to_dict())


def _normalize_template_set(source: Mapping[str, Any], *, require_hash: bool) -> dict[str, Any]:
    if set(source) - _SET_KEYS:
        raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE_SET", field="unknown_fields")
    required = _SET_KEYS - {"content_sha256", "identity"}
    missing = sorted(required - set(source))
    if missing:
        raise _error("TRUCK_MANEUVER_TEMPLATE_SET_REQUIRED", missing_fields=missing)
    if source["schema_version"] != TEMPLATE_SET_SCHEMA_VERSION:
        raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE_SET", field="schema_version")
    if source["source_authority"] != PROJECT_INPUT:
        raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE_SET", field="source_authority")
    project_id = _text(source["project_id"], field="project_id")
    raw_templates = source["templates"]
    if not isinstance(raw_templates, (list, tuple)):
        raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE_SET", field="templates")
    templates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in raw_templates:
        normalized = (
            _normalize_template(raw.to_dict(), require_hash=True)
            if isinstance(raw, TruckManeuverTemplateV1)
            else _normalize_template(raw, require_hash=True)
            if isinstance(raw, Mapping)
            else None
        )
        if normalized is None:
            raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE_SET", field="templates")
        if normalized["project_id"] != project_id:
            raise _error("TRUCK_MANEUVER_PROJECT_MISMATCH", field="templates")
        template_id = cast(str, normalized["template_id"])
        if template_id in seen_ids:
            raise _error("DUPLICATE_TRUCK_MANEUVER_TEMPLATE_ID", template_id=template_id)
        seen_ids.add(template_id)
        templates.append(normalized)
    templates.sort(key=lambda row: cast(str, row["identity"]))
    identity = f"truck-maneuver-template-set:{project_id}@{TEMPLATE_SET_SCHEMA_VERSION}"
    if "identity" in source and source["identity"] != identity:
        raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE_SET", field="identity")
    normalized_set: dict[str, Any] = {
        "schema_version": TEMPLATE_SET_SCHEMA_VERSION,
        "project_id": project_id,
        "source_authority": PROJECT_INPUT,
        "templates": templates,
        "provided_by": _text(source["provided_by"], field="provided_by"),
        "identity": identity,
    }
    expected_hash = canonical_hash(_content_payload(normalized_set))
    supplied_hash = source.get("content_sha256")
    if require_hash:
        _hash(supplied_hash, field="content_sha256")
        if supplied_hash != expected_hash:
            raise _error(
                "TRUCK_MANEUVER_TEMPLATE_SET_HASH_MISMATCH",
                expected_hash=expected_hash,
                actual_hash=supplied_hash,
            )
    normalized_set["content_sha256"] = expected_hash
    return normalized_set


def maneuver_template_set_payload_with_hash(source: Mapping[str, Any]) -> dict[str, Any]:
    return _normalize_template_set(source, require_hash=False)


@dataclass(frozen=True, init=False)
class TruckManeuverTemplateSetV1:
    """Validated project collection; it may intentionally contain fewer than 3 classes."""

    payload_json: str

    def __init__(
        self,
        schema_version: str,
        project_id: str,
        source_authority: str,
        templates: Sequence[TruckManeuverTemplateV1 | Mapping[str, Any]],
        content_sha256: str,
        provided_by: str,
    ) -> None:
        source = {
            "schema_version": schema_version,
            "project_id": project_id,
            "source_authority": source_authority,
            "templates": list(templates),
            "content_sha256": content_sha256,
            "provided_by": provided_by,
        }
        object.__setattr__(
            self, "payload_json", canonical_json(_normalize_template_set(source, require_hash=True))
        )

    @classmethod
    def _from_normalized(cls, normalized: Mapping[str, Any]) -> TruckManeuverTemplateSetV1:
        obj = object.__new__(cls)
        object.__setattr__(obj, "payload_json", canonical_json(dict(normalized)))
        return obj

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> TruckManeuverTemplateSetV1:
        if not isinstance(source, Mapping):
            raise _error("INVALID_TRUCK_MANEUVER_TEMPLATE_SET")
        return cls._from_normalized(_normalize_template_set(source, require_hash=True))

    @property
    def identity(self) -> str:
        return cast(str, self.to_dict()["identity"])

    @property
    def schema_version(self) -> str:
        return cast(str, self.to_dict()["schema_version"])

    @property
    def source_authority(self) -> str:
        return cast(str, self.to_dict()["source_authority"])

    @property
    def project_id(self) -> str:
        return cast(str, self.to_dict()["project_id"])

    @property
    def provided_by(self) -> str:
        return cast(str, self.to_dict()["provided_by"])

    @property
    def content_sha256(self) -> str:
        return cast(str, self.to_dict()["content_sha256"])

    @property
    def templates(self) -> tuple[TruckManeuverTemplateV1, ...]:
        body = self.to_dict()
        raw_templates = body["templates"]
        assert isinstance(raw_templates, list)
        return tuple(TruckManeuverTemplateV1.from_mapping(raw) for raw in raw_templates)

    def to_dict(self) -> dict[str, Any]:
        return _decode_template_set_payload(cast(dict[str, Any], json.loads(self.payload_json)))

    def canonical_json(self) -> str:
        return self.payload_json

    @property
    def canonical_result_hash(self) -> str:
        return canonical_hash(self.to_dict())


def _normalize_requirement(source: Mapping[str, Any], *, require_hash: bool) -> dict[str, Any]:
    if set(source) - _REQUIREMENT_KEYS:
        raise _error("INVALID_TRUCK_MANEUVER_REQUIREMENT", field="unknown_fields")
    required = _REQUIREMENT_KEYS - {"content_sha256", "identity"}
    missing = sorted(required - set(source))
    if missing:
        raise _error("TRUCK_MANEUVER_REQUIREMENT_REQUIRED", missing_fields=missing)
    if source["schema_version"] != REQUIREMENT_SCHEMA_VERSION:
        raise _error("INVALID_TRUCK_MANEUVER_REQUIREMENT", field="schema_version")
    if source["source_authority"] != PROJECT_INPUT:
        raise _error("INVALID_TRUCK_MANEUVER_REQUIREMENT", field="source_authority")
    project_id = _text(source["project_id"], field="project_id")
    raw_classes = source["required_maneuver_classes"]
    if not isinstance(raw_classes, (list, tuple)):
        raise _error("INVALID_TRUCK_MANEUVER_REQUIREMENT", field="required_maneuver_classes")
    classes = list(raw_classes)
    if any(not isinstance(value, str) or value not in MANEUVER_CLASSES for value in classes):
        raise _error("UNAUTHORIZED_TRUCK_MANEUVER_CLASS", field="required_maneuver_classes")
    if len(classes) != len(set(classes)):
        raise _error("DUPLICATE_TRUCK_MANEUVER_CLASS", field="required_maneuver_classes")
    classes.sort()
    identity = f"truck-maneuver-requirement:{project_id}@{REQUIREMENT_SCHEMA_VERSION}"
    if "identity" in source and source["identity"] != identity:
        raise _error("INVALID_TRUCK_MANEUVER_REQUIREMENT", field="identity")
    normalized: dict[str, Any] = {
        "schema_version": REQUIREMENT_SCHEMA_VERSION,
        "project_id": project_id,
        "source_authority": PROJECT_INPUT,
        "required_maneuver_classes": classes,
        "provided_by": _text(source["provided_by"], field="provided_by"),
        "identity": identity,
    }
    expected_hash = canonical_hash(_content_payload(normalized))
    supplied_hash = source.get("content_sha256")
    if require_hash:
        _hash(supplied_hash, field="content_sha256")
        if supplied_hash != expected_hash:
            raise _error(
                "TRUCK_MANEUVER_REQUIREMENT_HASH_MISMATCH",
                expected_hash=expected_hash,
                actual_hash=supplied_hash,
            )
    normalized["content_sha256"] = expected_hash
    return normalized


def maneuver_requirement_payload_with_hash(source: Mapping[str, Any]) -> dict[str, Any]:
    return _normalize_requirement(source, require_hash=False)


@dataclass(frozen=True, init=False)
class TruckManeuverRequirementV1:
    """Binding of only the maneuver classes required by one project use case."""

    payload_json: str

    def __init__(
        self,
        schema_version: str,
        project_id: str,
        source_authority: str,
        required_maneuver_classes: Sequence[str],
        content_sha256: str,
        provided_by: str,
    ) -> None:
        source = {
            "schema_version": schema_version,
            "project_id": project_id,
            "source_authority": source_authority,
            "required_maneuver_classes": list(required_maneuver_classes),
            "content_sha256": content_sha256,
            "provided_by": provided_by,
        }
        object.__setattr__(
            self, "payload_json", canonical_json(_normalize_requirement(source, require_hash=True))
        )

    @classmethod
    def _from_normalized(cls, normalized: Mapping[str, Any]) -> TruckManeuverRequirementV1:
        obj = object.__new__(cls)
        object.__setattr__(obj, "payload_json", canonical_json(dict(normalized)))
        return obj

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> TruckManeuverRequirementV1:
        if not isinstance(source, Mapping):
            raise _error("INVALID_TRUCK_MANEUVER_REQUIREMENT")
        return cls._from_normalized(_normalize_requirement(source, require_hash=True))

    @property
    def identity(self) -> str:
        return cast(str, self.to_dict()["identity"])

    @property
    def schema_version(self) -> str:
        return cast(str, self.to_dict()["schema_version"])

    @property
    def source_authority(self) -> str:
        return cast(str, self.to_dict()["source_authority"])

    @property
    def project_id(self) -> str:
        return cast(str, self.to_dict()["project_id"])

    @property
    def required_maneuver_classes(self) -> tuple[str, ...]:
        return tuple(cast(list[str], self.to_dict()["required_maneuver_classes"]))

    @property
    def content_sha256(self) -> str:
        return cast(str, self.to_dict()["content_sha256"])

    @property
    def provided_by(self) -> str:
        return cast(str, self.to_dict()["provided_by"])

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.payload_json))

    def canonical_json(self) -> str:
        return self.payload_json

    @property
    def canonical_result_hash(self) -> str:
        return canonical_hash(self.to_dict())


def _normalize_project_input(source: Mapping[str, Any], *, require_hash: bool) -> dict[str, Any]:
    if set(source) - _PROJECT_KEYS:
        raise _error("INVALID_TRUCK_MANEUVER_PROJECT_INPUT", field="unknown_fields")
    missing = sorted(_PROJECT_KEYS - {"content_sha256", "identity"} - set(source))
    if missing:
        raise _error("TRUCK_MANEUVER_PROJECT_INPUT_REQUIRED", missing_fields=missing)
    if source["schema_version"] != PROJECT_INPUT_SCHEMA_VERSION:
        raise _error("INVALID_TRUCK_MANEUVER_PROJECT_INPUT", field="schema_version")
    if source["source_authority"] != PROJECT_INPUT:
        raise _error("INVALID_TRUCK_MANEUVER_PROJECT_INPUT", field="source_authority")
    project_id = _text(source["project_id"], field="project_id")
    template_set = (
        source["template_set"]
        if isinstance(source["template_set"], TruckManeuverTemplateSetV1)
        else TruckManeuverTemplateSetV1.from_mapping(source["template_set"])
        if isinstance(source["template_set"], Mapping)
        else None
    )
    requirement = (
        source["requirement"]
        if isinstance(source["requirement"], TruckManeuverRequirementV1)
        else TruckManeuverRequirementV1.from_mapping(source["requirement"])
        if isinstance(source["requirement"], Mapping)
        else None
    )
    if template_set is None or requirement is None:
        raise _error("INVALID_TRUCK_MANEUVER_PROJECT_INPUT")
    if template_set.project_id != project_id or requirement.project_id != project_id:
        raise _error("TRUCK_MANEUVER_PROJECT_MISMATCH", field="project_id")
    identity = f"truck-maneuver-project-input:{project_id}@{PROJECT_INPUT_SCHEMA_VERSION}"
    if "identity" in source and source["identity"] != identity:
        raise _error("INVALID_TRUCK_MANEUVER_PROJECT_INPUT", field="identity")
    normalized: dict[str, Any] = {
        "schema_version": PROJECT_INPUT_SCHEMA_VERSION,
        "project_id": project_id,
        "source_authority": PROJECT_INPUT,
        "template_set": template_set.to_dict(),
        "requirement": requirement.to_dict(),
        "provided_by": _text(source["provided_by"], field="provided_by"),
        "identity": identity,
    }
    expected_hash = canonical_hash(_content_payload(normalized))
    supplied_hash = source.get("content_sha256")
    if require_hash:
        _hash(supplied_hash, field="content_sha256")
        if supplied_hash != expected_hash:
            raise _error(
                "TRUCK_MANEUVER_PROJECT_INPUT_HASH_MISMATCH",
                expected_hash=expected_hash,
                actual_hash=supplied_hash,
            )
    normalized["content_sha256"] = expected_hash
    return normalized


def maneuver_project_input_payload_with_hash(source: Mapping[str, Any]) -> dict[str, Any]:
    return _normalize_project_input(source, require_hash=False)


@dataclass(frozen=True, init=False)
class TruckManeuverProjectInputV1:
    """Independent machine-geometry input; it does not alter P1F truck input."""

    payload_json: str

    def __init__(
        self,
        schema_version: str,
        project_id: str,
        source_authority: str,
        template_set: TruckManeuverTemplateSetV1,
        requirement: TruckManeuverRequirementV1,
        content_sha256: str,
        provided_by: str,
    ) -> None:
        source = {
            "schema_version": schema_version,
            "project_id": project_id,
            "source_authority": source_authority,
            "template_set": template_set,
            "requirement": requirement,
            "content_sha256": content_sha256,
            "provided_by": provided_by,
        }
        object.__setattr__(
            self,
            "payload_json",
            canonical_json(_normalize_project_input(source, require_hash=True)),
        )

    @classmethod
    def _from_normalized(cls, normalized: Mapping[str, Any]) -> TruckManeuverProjectInputV1:
        obj = object.__new__(cls)
        object.__setattr__(obj, "payload_json", canonical_json(dict(normalized)))
        return obj

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> TruckManeuverProjectInputV1:
        if not isinstance(source, Mapping):
            raise _error("INVALID_TRUCK_MANEUVER_PROJECT_INPUT")
        return cls._from_normalized(_normalize_project_input(source, require_hash=True))

    @property
    def identity(self) -> str:
        return cast(str, self.to_dict()["identity"])

    @property
    def schema_version(self) -> str:
        return cast(str, self.to_dict()["schema_version"])

    @property
    def source_authority(self) -> str:
        return cast(str, self.to_dict()["source_authority"])

    @property
    def project_id(self) -> str:
        return cast(str, self.to_dict()["project_id"])

    @property
    def content_sha256(self) -> str:
        return cast(str, self.to_dict()["content_sha256"])

    @property
    def provided_by(self) -> str:
        return cast(str, self.to_dict()["provided_by"])

    @property
    def template_set(self) -> TruckManeuverTemplateSetV1:
        return TruckManeuverTemplateSetV1.from_mapping(self.to_dict()["template_set"])

    @property
    def requirement(self) -> TruckManeuverRequirementV1:
        return TruckManeuverRequirementV1.from_mapping(self.to_dict()["requirement"])

    @property
    def missing_maneuver_classes(self) -> tuple[str, ...]:
        available = {template.maneuver_class for template in self.template_set.templates}
        return tuple(sorted(set(self.requirement.required_maneuver_classes) - available))

    @property
    def template_input_complete(self) -> bool:
        return not self.missing_maneuver_classes

    def require_complete(self) -> TruckManeuverProjectInputV1:
        missing = self.missing_maneuver_classes
        if missing:
            raise _error("TRUCK_MANEUVER_TEMPLATE_REQUIRED", missing_maneuver_classes=list(missing))
        return self

    def to_dict(self) -> dict[str, Any]:
        body = cast(dict[str, Any], json.loads(self.payload_json))
        template_set = body.get("template_set")
        if isinstance(template_set, Mapping):
            body["template_set"] = _decode_template_set_payload(template_set)
        return body

    def canonical_json(self) -> str:
        return self.payload_json

    @property
    def canonical_result_hash(self) -> str:
        return canonical_hash(self.to_dict())


def validate_truck_maneuver_project_input(
    source: Mapping[str, Any] | TruckManeuverProjectInputV1,
) -> TruckManeuverProjectInputV1:
    if isinstance(source, TruckManeuverProjectInputV1):
        # Re-validate the serialized content instead of trusting an object label.
        return TruckManeuverProjectInputV1.from_mapping(source.to_dict())
    return TruckManeuverProjectInputV1.from_mapping(source)


def _validated_p1f_snapshot(source: Mapping[str, Any] | None) -> dict[str, Any]:
    result = validate_project_truck_input(source)
    if result.get("status") != "COMPLETE":
        status = result.get("status")
        if status == "PROJECT_INPUT_REQUIRED":
            raise _error(
                "PROJECT_INPUT_REQUIRED",
                input_contract_identity=P1F_TRUCK_INPUT_IDENTITY,
                missing_fields=result.get("missing_fields", []),
            )
        raise _error(
            "INVALID_PROJECT_TRUCK_INPUT",
            input_contract_identity=P1F_TRUCK_INPUT_IDENTITY,
            field=result.get("field", "truck_access"),
        )
    canonical = result.get("validated_input_canonical_json")
    if not isinstance(canonical, str):
        raise _error(
            "PROJECT_INPUT_REQUIRED",
            input_contract_identity=P1F_TRUCK_INPUT_IDENTITY,
            missing_fields=["validated_input_canonical_json"],
        )
    try:
        snapshot = json.loads(canonical)
    except json.JSONDecodeError:
        raise _error("INVALID_PROJECT_TRUCK_INPUT") from None
    if not isinstance(snapshot, dict):
        raise _error("INVALID_PROJECT_TRUCK_INPUT")
    return snapshot


def _validated_p1f_snapshot_from_canonical(source: object) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        raise _error(
            "PROJECT_INPUT_REQUIRED",
            input_contract_identity=P1F_TRUCK_INPUT_IDENTITY,
            missing_fields=["p1f_input"],
        )
    raw = dict(source)
    for field in ("vehicle_width_m", "vehicle_length_m"):
        if isinstance(raw.get(field), str):
            try:
                raw[field] = Decimal(raw[field])
            except ArithmeticError:
                raise _error("INVALID_PROJECT_TRUCK_INPUT", field=field) from None
    return _validated_p1f_snapshot(raw)


def _vehicle_dimension(value: object, *, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except ArithmeticError:
        raise _error("INVALID_TRUCK_MANEUVER_PROJECT_BINDING", field=field) from None
    if not number.is_finite() or number <= 0:
        raise _error("INVALID_TRUCK_MANEUVER_PROJECT_BINDING", field=field)
    return number


def _binding_identity(project_id: str) -> str:
    return f"truck-maneuver-project-binding:{project_id}@{PROJECT_BINDING_SCHEMA_VERSION}"


def _normalize_binding(source: Mapping[str, Any], *, require_hash: bool) -> dict[str, Any]:
    if set(source) - _BINDING_KEYS:
        raise _error("INVALID_TRUCK_MANEUVER_PROJECT_BINDING", field="unknown_fields")
    required = _BINDING_KEYS - {"content_sha256", "identity"}
    missing = sorted(required - set(source))
    if missing:
        raise _error("PROJECT_INPUT_REQUIRED", missing_fields=missing)
    if source["schema_version"] != PROJECT_BINDING_SCHEMA_VERSION:
        raise _error("INVALID_TRUCK_MANEUVER_PROJECT_BINDING", field="schema_version")
    if source["source_authority"] != PROJECT_INPUT:
        raise _error("INVALID_TRUCK_MANEUVER_PROJECT_BINDING", field="source_authority")
    if source["p1f_input_contract_identity"] != P1F_TRUCK_INPUT_IDENTITY:
        raise _error("INVALID_TRUCK_MANEUVER_PROJECT_BINDING", field="p1f_input_contract_identity")
    project_id = _binding_text(source["project_id"], field="project_id")
    p1f_snapshot = _validated_p1f_snapshot_from_canonical(source["p1f_input"])
    if p1f_snapshot.get("project_id") != project_id:
        raise _error("TRUCK_MANEUVER_PROJECT_MISMATCH", field="p1f_input.project_id")
    p1f_hash = _binding_hash(source["p1f_input_canonical_hash"], field="p1f_input_canonical_hash")
    expected_p1f_hash = canonical_hash(p1f_snapshot)
    if p1f_hash != expected_p1f_hash:
        raise _error(
            "P1F_TRUCK_INPUT_HASH_MISMATCH",
            expected_hash=expected_p1f_hash,
            actual_hash=p1f_hash,
        )
    maneuver_input = source["maneuver_project_input"]
    if isinstance(maneuver_input, (TruckManeuverProjectInputV1, Mapping)):
        maneuver = validate_truck_maneuver_project_input(maneuver_input)
    else:
        raise _error("PROJECT_INPUT_REQUIRED", missing_fields=["maneuver_project_input"])
    if maneuver.project_id != project_id:
        raise _error("TRUCK_MANEUVER_PROJECT_MISMATCH", field="maneuver_project_input.project_id")

    p1f_width = _vehicle_dimension(p1f_snapshot["vehicle_width_m"], field="vehicle_width_m")
    p1f_length = _vehicle_dimension(p1f_snapshot["vehicle_length_m"], field="vehicle_length_m")
    for template in maneuver.template_set.templates:
        if template.vehicle_width_m != p1f_width:
            raise _error(
                "TRUCK_MANEUVER_VEHICLE_DIMENSION_MISMATCH",
                template_id=template.template_id,
                field="vehicle_width_m",
                expected=str(p1f_width),
                actual=str(template.vehicle_width_m),
                p1f_input_contract_identity=P1F_TRUCK_INPUT_IDENTITY,
            )
        if template.vehicle_length_m != p1f_length:
            raise _error(
                "TRUCK_MANEUVER_VEHICLE_DIMENSION_MISMATCH",
                template_id=template.template_id,
                field="vehicle_length_m",
                expected=str(p1f_length),
                actual=str(template.vehicle_length_m),
                p1f_input_contract_identity=P1F_TRUCK_INPUT_IDENTITY,
            )

    identity = _binding_identity(project_id)
    if "identity" in source and source["identity"] != identity:
        raise _error("INVALID_TRUCK_MANEUVER_PROJECT_BINDING", field="identity")
    normalized: dict[str, Any] = {
        "schema_version": PROJECT_BINDING_SCHEMA_VERSION,
        "project_id": project_id,
        "source_authority": PROJECT_INPUT,
        "p1f_input_contract_identity": P1F_TRUCK_INPUT_IDENTITY,
        "p1f_input": p1f_snapshot,
        "p1f_input_canonical_hash": expected_p1f_hash,
        "maneuver_project_input": maneuver.to_dict(),
        "provided_by": _binding_text(source["provided_by"], field="provided_by"),
        "identity": identity,
    }
    expected_hash = canonical_hash(_content_payload(normalized))
    supplied_hash = source.get("content_sha256")
    if require_hash:
        supplied_hash = _binding_hash(supplied_hash, field="content_sha256")
        if supplied_hash != expected_hash:
            raise _error(
                "TRUCK_MANEUVER_PROJECT_BINDING_HASH_MISMATCH",
                expected_hash=expected_hash,
                actual_hash=supplied_hash,
            )
    normalized["content_sha256"] = expected_hash
    return normalized


@dataclass(frozen=True, init=False)
class BoundTruckManeuverProjectInputV1:
    """P1F-bound maneuver input with explicit project vehicle evidence."""

    payload_json: str

    def __init__(
        self,
        truck_project_access_input: Mapping[str, Any],
        truck_maneuver_project_input: Mapping[str, Any] | TruckManeuverProjectInputV1,
        provided_by: str = PROJECT_INPUT,
    ) -> None:
        normalized = _binding_from_sources(
            truck_project_access_input,
            truck_maneuver_project_input,
            provided_by=provided_by,
        )
        object.__setattr__(self, "payload_json", canonical_json(normalized))

    @classmethod
    def _from_normalized(cls, normalized: Mapping[str, Any]) -> BoundTruckManeuverProjectInputV1:
        obj = object.__new__(cls)
        object.__setattr__(obj, "payload_json", canonical_json(dict(normalized)))
        return obj

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> BoundTruckManeuverProjectInputV1:
        if not isinstance(source, Mapping):
            raise _error("INVALID_TRUCK_MANEUVER_PROJECT_BINDING")
        return cls._from_normalized(_normalize_binding(source, require_hash=True))

    @property
    def identity(self) -> str:
        return cast(str, self.to_dict()["identity"])

    @property
    def project_id(self) -> str:
        return cast(str, self.to_dict()["project_id"])

    @property
    def p1f_input_contract_identity(self) -> str:
        return cast(str, self.to_dict()["p1f_input_contract_identity"])

    @property
    def p1f_input(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.to_dict()["p1f_input"])

    @property
    def p1f_input_canonical_hash(self) -> str:
        return cast(str, self.to_dict()["p1f_input_canonical_hash"])

    @property
    def maneuver_project_input(self) -> TruckManeuverProjectInputV1:
        return TruckManeuverProjectInputV1.from_mapping(self.to_dict()["maneuver_project_input"])

    @property
    def content_sha256(self) -> str:
        return cast(str, self.to_dict()["content_sha256"])

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.payload_json))

    def canonical_json(self) -> str:
        return self.payload_json

    @property
    def canonical_result_hash(self) -> str:
        return canonical_hash(self.to_dict())


TruckManeuverProjectBindingV1 = BoundTruckManeuverProjectInputV1


def _binding_from_sources(
    truck_project_access_input: Mapping[str, Any] | None,
    truck_maneuver_project_input: Mapping[str, Any] | TruckManeuverProjectInputV1,
    *,
    provided_by: str,
) -> dict[str, Any]:
    p1f_snapshot = _validated_p1f_snapshot(truck_project_access_input)
    maneuver = validate_truck_maneuver_project_input(truck_maneuver_project_input)
    project_id = _binding_text(p1f_snapshot.get("project_id"), field="project_id")
    source = {
        "schema_version": PROJECT_BINDING_SCHEMA_VERSION,
        "project_id": project_id,
        "source_authority": PROJECT_INPUT,
        "p1f_input_contract_identity": P1F_TRUCK_INPUT_IDENTITY,
        "p1f_input": p1f_snapshot,
        "p1f_input_canonical_hash": canonical_hash(p1f_snapshot),
        "maneuver_project_input": maneuver,
        "provided_by": provided_by,
    }
    return _normalize_binding(source, require_hash=False)


def validate_truck_maneuver_project_binding(
    truck_project_access_input: Mapping[str, Any] | None,
    truck_maneuver_project_input: Mapping[str, Any] | TruckManeuverProjectInputV1,
) -> BoundTruckManeuverProjectInputV1:
    """Bind every maneuver template to the same explicit P1F project vehicle."""
    return BoundTruckManeuverProjectInputV1._from_normalized(
        _binding_from_sources(
            truck_project_access_input,
            truck_maneuver_project_input,
            provided_by=PROJECT_INPUT,
        )
    )


def bind_truck_maneuver_project_input(
    truck_project_access_input: Mapping[str, Any] | None,
    truck_maneuver_project_input: Mapping[str, Any] | TruckManeuverProjectInputV1,
) -> BoundTruckManeuverProjectInputV1:
    return validate_truck_maneuver_project_binding(
        truck_project_access_input, truck_maneuver_project_input
    )


def _mm_coordinate(value: object, *, field: str) -> int:
    number = _coordinate(value, field=field)
    with localcontext(Context(prec=80)):
        return int(number * 1000)


def _rotate_mm(point: tuple[int, int], rotation_deg: int) -> tuple[int, int]:
    x, y = point
    if rotation_deg == 0:
        return x, y
    if rotation_deg == 90:
        return -y, x
    if rotation_deg == 180:
        return -x, -y
    return y, -x


def _transform_polygon(
    polygon: PolygonMM, translation: tuple[int, int], rotation_deg: int
) -> PolygonMM:
    tx, ty = translation
    points = []
    for point in polygon:
        x, y = _rotate_mm(point, rotation_deg)
        points.append({"x": Decimal(x + tx) / 1000, "y": Decimal(y + ty) / 1000})
    return normalize_polygon(
        {"type": "polygon", "points": points}, error_code="INVALID_TRANSFORMED_MANEUVER_ENVELOPE"
    )


def _transform_point(
    point: Mapping[str, Any], translation: tuple[int, int], rotation_deg: int
) -> dict[str, Decimal]:
    x = _mm_coordinate(point["x"], field="reference.x")
    y = _mm_coordinate(point["y"], field="reference.y")
    transformed_x, transformed_y = _rotate_mm((x, y), rotation_deg)
    return {
        "x": Decimal(transformed_x + translation[0]) / 1000,
        "y": Decimal(transformed_y + translation[1]) / 1000,
    }


def _transform_pose(
    pose: Mapping[str, Any], translation: tuple[int, int], rotation_deg: int
) -> dict[str, Any]:
    point = _transform_point(pose, translation, rotation_deg)
    heading = cast(int, pose["rotation_deg"])
    return {**point, "rotation_deg": (heading + rotation_deg) % 360}


def transform_maneuver_template(
    template: TruckManeuverTemplateV1 | Mapping[str, Any],
    translation: Mapping[str, Any],
    rotation_deg: int,
) -> dict[str, Any]:
    """Transform one validated envelope in exact millimetre arithmetic.

    The result is a placement-ready observation only.  It does not assert that
    the transformed envelope is inside a site, clear of an obstacle, or route
    feasible; those are later placement predicates.
    """
    source = (
        validate_truck_maneuver_template(template)
        if isinstance(template, Mapping)
        else validate_truck_maneuver_template(template)
    )
    if not isinstance(translation, Mapping) or set(translation) != _POINT_KEYS:
        raise _error("INVALID_MANEUVER_TRANSFORM", field="translation")
    translation_mm = (
        _mm_coordinate(translation["x"], field="translation.x"),
        _mm_coordinate(translation["y"], field="translation.y"),
    )
    if type(rotation_deg) is not int or rotation_deg not in SUPPORTED_TRANSFORM_ROTATIONS:
        raise _error(
            "UNAUTHORIZED_MANEUVER_ROTATION",
            rotation_deg=rotation_deg,
            allowed_rotations=list(SUPPORTED_TRANSFORM_ROTATIONS),
        )
    body = source.to_dict()
    reference = cast(dict[str, Any], body["reference_frame"])
    transformed_reference = {
        "reference_frame": reference["reference_frame"],
        "forward_axis": reference["forward_axis"],
        "origin_reference": reference["origin_reference"],
        "vehicle_reference_point": _transform_point(
            reference["vehicle_reference_point"], translation_mm, rotation_deg
        ),
        "entry_pose": _transform_pose(reference["entry_pose"], translation_mm, rotation_deg),
        "exit_pose": _transform_pose(reference["exit_pose"], translation_mm, rotation_deg),
    }
    transformed: dict[str, Any] = {
        "schema_version": TEMPLATE_SCHEMA_VERSION,
        "template_identity": source.identity,
        "source_reference": source.reference,
        "source_content_sha256": source.content_sha256,
        "canonical_template_hash": source.canonical_template_hash,
        "project_id": source.project_id,
        "maneuver_class": source.maneuver_class,
        "coordinate_system": COORDINATE_SYSTEM,
        "grid_m": GRID_M,
        "rotation_deg": rotation_deg,
        "translation": {
            "x": Decimal(translation_mm[0]) / 1000,
            "y": Decimal(translation_mm[1]) / 1000,
        },
        "reference_frame": transformed_reference,
        "envelope_geometry": polygon_to_dict(
            _transform_polygon(
                normalize_polygon(
                    body["envelope_geometry"], error_code="INVALID_MANEUVER_ENVELOPE"
                ),
                translation_mm,
                rotation_deg,
            )
        ),
    }
    if source.maneuver_class == TURN_90:
        transformed["turn_direction"] = body["turn_direction"]
    if source.maneuver_class == DOCK_REVERSE:
        transformed["dock_face_reference"] = body["dock_face_reference"]
        transformed["approach_pose"] = _transform_pose(
            body["approach_pose"], translation_mm, rotation_deg
        )
        transformed["final_dock_pose"] = _transform_pose(
            body["final_dock_pose"], translation_mm, rotation_deg
        )
    transformed["canonical_result_hash"] = canonical_hash(transformed)
    return transformed


def validate_truck_maneuver_template(
    source: Mapping[str, Any] | TruckManeuverTemplateV1,
) -> TruckManeuverTemplateV1:
    if isinstance(source, TruckManeuverTemplateV1):
        return TruckManeuverTemplateV1.from_mapping(source.to_dict())
    return TruckManeuverTemplateV1.from_mapping(source)


def validate_truck_maneuver_template_set(
    source: Mapping[str, Any] | TruckManeuverTemplateSetV1,
) -> TruckManeuverTemplateSetV1:
    if isinstance(source, TruckManeuverTemplateSetV1):
        return TruckManeuverTemplateSetV1.from_mapping(source.to_dict())
    return TruckManeuverTemplateSetV1.from_mapping(source)


def validate_truck_maneuver_requirement(
    source: Mapping[str, Any] | TruckManeuverRequirementV1,
) -> TruckManeuverRequirementV1:
    if isinstance(source, TruckManeuverRequirementV1):
        return TruckManeuverRequirementV1.from_mapping(source.to_dict())
    return TruckManeuverRequirementV1.from_mapping(source)
