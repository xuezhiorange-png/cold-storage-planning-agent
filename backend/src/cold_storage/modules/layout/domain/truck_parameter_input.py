"""Additive parameterized Truck preview contract; original V1 contracts unchanged.

Option C consumes supplied swept paths, not a vehicle dynamics simulation.
Uploaded bytes are hashed; declared human approval is not signature authentication.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
from typing import Any, NoReturn

from cold_storage.modules.layout.domain import access_routing as routing
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.project_truck_input import validate_project_truck_input
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    normalize_polygon,
)
from cold_storage.modules.layout.domain.truck_maneuver import (
    transform_maneuver_template,
    validate_truck_maneuver_project_binding,
)

IDENTITY = "parameterized-truck-preview@1.0.0"
FIELDS = frozenset(
    {
        "schema_version",
        "mode",
        "vehicle_type",
        "vehicle_body",
        "vehicle_source_reference",
        "truck_access",
        "truck_maneuver",
        "entrance",
        "shipping_loading_face",
        "loading_face_reference",
        "site_geometry",
        "evidence",
        "approval_reference",
    }
)
MAX_DOCUMENT_BYTES = 1_048_576
MAX_TOTAL_DOCUMENT_BYTES = 8_388_608


def _reject(code: str, **details: object) -> NoReturn:
    raise LayoutAuthorityError(code, **details)


def _object(value: object, fields: set[str], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _reject("INVALID_TRUCK_PREVIEW_INPUT", field=name)
    assert isinstance(value, Mapping)
    missing = sorted(fields - set(value))
    if missing:
        _reject("PROJECT_INPUT_REQUIRED", missing_fields=[name + "." + k for k in missing])
    if set(value) - fields:
        _reject("INVALID_TRUCK_PREVIEW_INPUT", field=name)
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _reject("PROJECT_INPUT_REQUIRED", missing_fields=[field])
    assert isinstance(value, str)
    return value


def _evidence(payload: Mapping[str, Any], references: Mapping[str, str]) -> dict[str, Any]:
    rows = payload["evidence"]
    if not isinstance(rows, list) or len(rows) > 32:
        _reject("INVALID_TRUCK_PREVIEW_INPUT", field="evidence")
    verified: dict[str, Any] = {}
    total = 0
    for raw in rows:
        row = _object(raw, {"reference", "content_sha256", "content_base64"}, "evidence")
        reference = _text(row["reference"], "evidence.reference")
        if reference in verified or not isinstance(row["content_base64"], str):
            _reject("INVALID_TRUCK_PREVIEW_INPUT", field="evidence")
        if len(row["content_base64"]) > 4 * ((MAX_DOCUMENT_BYTES + 2) // 3):
            _reject("TRUCK_DOCUMENT_RESOURCE_LIMIT")
        try:
            content = base64.b64decode(row["content_base64"], validate=True)
        except (ValueError, binascii.Error):
            _reject("INVALID_TRUCK_SOURCE_ENCODING")
        total += len(content)
        if not content or len(content) > MAX_DOCUMENT_BYTES or total > MAX_TOTAL_DOCUMENT_BYTES:
            _reject("TRUCK_DOCUMENT_RESOURCE_LIMIT")
        digest = "sha256:" + sha256(content).hexdigest()
        if row["content_sha256"] != digest:
            _reject("TRUCK_SOURCE_CONTENT_HASH_MISMATCH", reference=reference)
        verified[reference] = {"sha256": digest, "bytes": len(content), "content": content}
    missing = sorted(set(references) - set(verified))
    if missing:
        _reject("PROJECT_INPUT_REQUIRED", missing_fields=["evidence." + r for r in missing])
    for ref, digest in references.items():
        if digest and verified[ref]["sha256"] != digest:
            _reject("TRUCK_SOURCE_CONTENT_HASH_MISMATCH", reference=ref)
    return verified


def _vehicle_body(payload: Mapping[str, Any], width: int, length: int) -> PolygonMM:
    # Explicit offsets from the template's vehicle reference point. No assumed
    # center/rear-axle reference or default safety clearance.
    body = normalize_polygon(payload["vehicle_body"], allow_numeric_string=True)
    bounds = routing._rectangle_bounds(body)
    if bounds is None or bounds[2] - bounds[0] != length or bounds[3] - bounds[1] != width:
        _reject("TRUCK_VEHICLE_BODY_DIMENSION_MISMATCH")
    return body


def _posed_body(body: PolygonMM, pose: Mapping[str, Any]) -> PolygonMM:
    x, y, angle = routing._pose_mm(pose)
    rotations = {
        0: lambda a, b: (a, b),
        90: lambda a, b: (-b, a),
        180: lambda a, b: (-a, -b),
        270: lambda a, b: (b, -a),
    }
    return tuple((x + a, y + b) for a, b in (rotations[angle](*p) for p in body))


def _verify_body_envelopes(binding: Any, body: PolygonMM) -> None:
    for template in binding.maneuver_project_input.template_set.templates:
        transformed = transform_maneuver_template(template, {"x": 0, "y": 0}, 0)
        polygon = normalize_polygon(transformed["envelope_geometry"], allow_numeric_string=True)
        poses = list(transformed["reference_frame"][key] for key in ("entry_pose", "exit_pose"))
        if "final_dock_pose" in transformed:
            poses.append(transformed["final_dock_pose"])
        if any(not routing.polygon_contains_polygon(polygon, _posed_body(body, p)) for p in poses):
            _reject("TRUCK_TEMPLATE_BODY_NOT_COVERED", template=template.identity)


def _preview(payload: Mapping[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(payload) - FIELDS)
    if unknown:
        _reject("INVALID_TRUCK_PREVIEW_INPUT", unknown_fields=unknown)
    missing = sorted(FIELDS - set(payload))
    if missing:
        _reject("PROJECT_INPUT_REQUIRED", missing_fields=missing)
    if payload["schema_version"] != "1.0.0" or payload["mode"] not in (
        "SYNTHETIC_TEST",
        "OWNER_PROJECT",
    ):
        _reject("INVALID_TRUCK_PREVIEW_INPUT", field="schema_version/mode")
    vehicle_type = _text(payload["vehicle_type"], "vehicle_type")
    p1f = validate_project_truck_input(payload["truck_access"])
    if p1f["status"] != "COMPLETE":
        _reject(p1f["status"], missing_fields=p1f.get("missing_fields", []), field=p1f.get("field"))
    binding = validate_truck_maneuver_project_binding(
        payload["truck_access"], payload["truck_maneuver"]
    )
    references: dict[str, str] = {}
    for key in ("turning_envelope", "straight_approach", "loading_operation_clearance"):
        ref = payload["truck_access"][key]
        if ref["reference"] in references and references[ref["reference"]] != ref["content_sha256"]:
            _reject("TRUCK_SOURCE_CONTENT_HASH_MISMATCH", reference=ref["reference"])
        references[ref["reference"]] = ref["content_sha256"]
    for template in binding.maneuver_project_input.template_set.templates:
        if (
            template.reference in references
            and references[template.reference] != template.content_sha256
        ):
            _reject("TRUCK_SOURCE_CONTENT_HASH_MISMATCH", reference=template.reference)
        references[template.reference] = template.content_sha256
    entrance = _object(
        payload["entrance"],
        {
            "locator_segment",
            "clear_opening_segment",
            "clear_width_m",
            "measurement_reference",
            "clearance_reference",
        },
        "entrance",
    )
    for reference in (
        payload["vehicle_source_reference"],
        payload["loading_face_reference"],
        payload["approval_reference"],
        entrance["measurement_reference"],
        entrance["clearance_reference"],
    ):
        references.setdefault(_text(reference, "source_reference"), "")
    verified = _evidence(payload, references)
    approved = False
    if payload["mode"] == "OWNER_PROJECT":
        try:
            approval = json.loads(verified[payload["approval_reference"]]["content"])
        except (ValueError, UnicodeDecodeError):
            _reject("PROJECT_INPUT_REQUIRED", missing_fields=["valid_owner_approval_record"])
        if not isinstance(approval, dict) or (
            approval.get("project_id") != binding.project_id
            or approval.get("status") != "APPROVED"
            or not isinstance(approval.get("reviewed_by"), str)
            or not approval["reviewed_by"].strip()
            or approval.get("approved_input_hash")
            != canonical_hash({k: v for k, v in payload.items() if k != "evidence"})
        ):
            _reject("PROJECT_INPUT_REQUIRED", missing_fields=["matching_owner_approval_record"])
        approved = True
    width = routing._mm(payload["truck_access"]["vehicle_width_m"], field="vehicle_width_m")
    length = routing._mm(payload["truck_access"]["vehicle_length_m"], field="vehicle_length_m")
    body = _vehicle_body(payload, width, length)
    _verify_body_envelopes(binding, body)
    locator = routing._segment_from_mapping(entrance["locator_segment"], field="locator_segment")
    opening = routing._segment_from_mapping(entrance["clear_opening_segment"], field="opening")
    clear = routing._mm(entrance["clear_width_m"], field="clear_width_m")
    if opening[0][0] != opening[1][0] and opening[0][1] != opening[1][1]:
        _reject("INVALID_TRUCK_ENTRANCE_GEOMETRY")
    if clear != routing._segment_length_mm(opening) or clear < width:
        _reject("TRUCK_ENTRANCE_CLEAR_WIDTH_INSUFFICIENT")
    if not all(routing._on_segment(p, *opening) for p in locator):
        _reject("TRUCK_ENTRANCE_LOCATOR_OUTSIDE_OPENING")
    site = _object(
        payload["site_geometry"],
        {"effective_buildable_boundary", "hard_obstacles", "zones", "personnel_corridors"},
        "site_geometry",
    )
    boundary = normalize_polygon(site["effective_buildable_boundary"], allow_numeric_string=True)
    if not any(
        all(routing._on_segment(p, a, b) for p in opening)
        for a, b in zip(boundary, (*boundary[1:], boundary[0]), strict=True)
    ):
        _reject("TRUCK_ENTRANCE_NOT_ON_SITE_BOUNDARY")
    obstacles = tuple(
        normalize_polygon(p, allow_numeric_string=True) for p in site["hard_obstacles"]
    )
    personnel = tuple(
        normalize_polygon(p, allow_numeric_string=True) for p in site["personnel_corridors"]
    )
    zones: dict[str, PlacedRectangleV1] = {}
    for raw in site["zones"]:
        z = _object(raw, {"zone_code", "x", "y", "width_m", "depth_m", "rotation_deg"}, "zones")
        role = _text(z["zone_code"], "zone_code")
        if role in zones:
            _reject("DUPLICATE_TRUCK_CONTEXT_ZONE")
        zones[role] = PlacedRectangleV1(
            role,
            Decimal(str(z["x"])),
            Decimal(str(z["y"])),
            Decimal(str(z["width_m"])),
            Decimal(str(z["depth_m"])),
            z["rotation_deg"],
        )
    if "shipping_channel" not in zones:
        _reject("PROJECT_INPUT_REQUIRED", missing_fields=["shipping_channel"])
    face = routing._segment_from_mapping(payload["shipping_loading_face"], field="loading_face")
    if face not in tuple(
        segment
        for _, edge, segment in routing._edge_segments(zones["shipping_channel"])
        if edge == "LONG_EDGE"
    ):
        _reject("INVALID_SHIPPING_LOADING_FACE")
    for zone in zones.values():
        if not routing.polygon_contains_polygon(boundary, zone.polygon_mm) or any(
            routing._polygon_intersects_closed(zone.polygon_mm, p) for p in obstacles
        ):
            _reject("INVALID_TRUCK_SITE_CONTEXT")
    # Exactly one native bounded search, with its unchanged locator/rotation
    # domain. If its selected chain fails added necessary gate checks, fail
    # closed; do not claim all other chains are impossible.
    result = routing.validate_truck_maneuver_chain(
        binding,
        truck_entrance=locator,
        shipping_loading_face=face,
        boundary=boundary,
        obstacles=obstacles,
        zones=zones,
        node_budget=routing.DEFAULT_TRUCK_NODE_BUDGET,
    )
    vertical = opening[0][0] == opening[1][0]
    if result["truck_route_validated"]:
        first = result["maneuver_chain"][0]
        pose = first["reference_frame"]["entry_pose"]
        angle = routing._pose_mm(pose)[2]
        footprint = _posed_body(body, pose)
        axis = 1 if vertical else 0
        low, high = sorted((opening[0][axis], opening[1][axis]))
        proper_heading = angle in ((0, 180) if vertical else (90, 270))
        swept = normalize_polygon(first["envelope_geometry"], allow_numeric_string=True)
        perpendicular = 1 - axis
        fixed = opening[0][perpendicular]
        crossings: list[Fraction] = []
        for a, b in zip(swept, (*swept[1:], swept[0]), strict=True):
            if a[perpendicular] == b[perpendicular] == fixed:
                crossings.extend((Fraction(a[axis]), Fraction(b[axis])))
            elif a[perpendicular] != b[perpendicular] and min(
                a[perpendicular], b[perpendicular]
            ) <= fixed <= max(a[perpendicular], b[perpendicular]):
                crossings.append(
                    Fraction(a[axis])
                    + Fraction(fixed - a[perpendicular], b[perpendicular] - a[perpendicular])
                    * (b[axis] - a[axis])
                )
        px, py, _ = routing._pose_mm(pose)
        dx, dy = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}[angle]
        if (
            not proper_heading
            or not routing._strict_point_in_polygon((px + dx, py + dy), boundary)
            or not all(low <= p[axis] <= high for p in footprint)
            or not crossings
            or not all(low <= p <= high for p in crossings)
        ):
            return {
                "status": "TRUCK_ENTRANCE_POSE_CLEARANCE_REJECTED",
                "input_complete": True,
                "truck": result,
                "truck_geometry_pass": False,
                "engineering_preview_validated": False,
                "requires_review": True,
                "REAL_PROJECT_APPROVED": False,
                "SYNTHETIC_TEST_ONLY": payload["mode"] == "SYNTHETIC_TEST",
                "engineering_pending": [
                    "Selected native chain rejected; other chains not proven infeasible"
                ],
                "P2_COMPLETE": False,
                "SERVER_REPLAY_ACCEPTED": False,
            }
    envelopes = tuple(
        normalize_polygon(p, allow_numeric_string=True) for p in result["truck_envelopes"]
    )
    interaction = (
        routing.evaluate_personnel_truck_interaction(personnel, envelopes)
        if envelopes
        else {"status": "NOT_EVALUATED", "codes": ["NO_TRUCK_ENVELOPE"]}
    )
    return {
        "status": result["status"]
        if not envelopes or interaction["status"] == "PASS"
        else interaction["status"],
        "input_complete": True,
        "missing_fields": [],
        "vehicle_type": vehicle_type,
        "vehicle_dimensions_defaulted": False,
        "source_contents_verified": True,
        "source_documents": {
            k: {f: v[f] for f in ("sha256", "bytes")} for k, v in verified.items()
        },
        "owner_approval_record_matches_input": approved,
        "approval_signature_authenticated": False,
        "REAL_PROJECT_APPROVED": False,
        "SYNTHETIC_TEST_ONLY": payload["mode"] == "SYNTHETIC_TEST",
        "binding_hash": binding.canonical_result_hash,
        "truck": result,
        "truck_geometry_pass": result["truck_route_validated"],
        "engineering_preview_validated": result["truck_route_validated"]
        and interaction["status"] == "PASS",
        "entrance_geometry_consistent": True,
        "entrance_measurement_source_bytes_verified": True,
        "shipping_long_edge_verified": True,
        "personnel_truck_interaction": interaction,
        "requires_review": True,
        "engineering_pending": [
            "Option C is not vehicle dynamics simulation",
            "Source bytes and matching supplied approval do not authenticate reviewer identity",
            "This standalone preview is not typed-Site/P1/P2D or server replay acceptance",
        ],
        "P2_COMPLETE": False,
        "SERVER_REPLAY_ACCEPTED": False,
    }


def preview_parameterized_truck(payload: object) -> dict[str, Any]:
    """Pure deterministic input-to-result entry; no filesystem/network/default vehicle."""
    try:
        if not isinstance(payload, Mapping):
            _reject("INVALID_TRUCK_PREVIEW_INPUT")
        assert isinstance(payload, Mapping)
        result = _preview(payload)
    except (LayoutAuthorityError, ValueError, TypeError, KeyError, ArithmeticError) as exc:
        result = {
            "status": getattr(exc, "code", "INVALID_TRUCK_PREVIEW_INPUT"),
            "input_complete": False,
            "missing_fields": getattr(exc, "details", {}).get("missing_fields", []),
            "details": getattr(exc, "details", {}),
            "REAL_PROJECT_APPROVED": False,
            "SYNTHETIC_TEST_ONLY": isinstance(payload, Mapping)
            and payload.get("mode") == "SYNTHETIC_TEST",
            "requires_review": True,
            "truck_geometry_pass": False,
            "engineering_preview_validated": False,
            "P2_COMPLETE": False,
            "SERVER_REPLAY_ACCEPTED": False,
        }
    result["identity"] = IDENTITY
    result["canonical_result_hash"] = canonical_hash(result)
    return result
