"""Offline process-room/portal adapter; immutable R1 reader and R2 exact core.

No geometry kernel, snapping, room inference, route search or approval system.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
R2_MANIFEST = "4915a2ae0d4b8863da700ff772941e68e635b9ae2aabfaaeca32e50defd1e0c0"
EXPECTED_SOURCE_SHA = "a2654279dbdefac8e225d7554e35463902e4abca1b4769418cd83e3a5ff6d139"


@lru_cache
def dependencies() -> tuple[Any, Any]:
    root = HERE.parent / "xinzhao-source-bound-room-boundary-r2"
    raw = (root / "source_manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != R2_MANIFEST:
        raise ValueError("R2_MANIFEST_CHANGED")
    for name, record in json.loads(raw)["files"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("R2_SOURCE_CHANGED:" + name)
    sys.path.insert(0, str(root))
    modules = []
    for name in ("offline_room_boundary", "offline_boundary_review"):
        spec = importlib.util.spec_from_file_location(name, root / (name + ".py"))
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        modules.append(module)
    return modules[0], modules[1]


def encode(value: Any) -> bytes:
    return bytes(dependencies()[0].encode(value))


def side_evidence(
    page: dict[str, Any], room: dict[str, Any], side: dict[str, Any]
) -> Any:
    core, _ = dependencies()
    selected = {
        core.ref_key(r): core.source_segment(page, r) for r in room["face_refs"]
    }
    ends: Counter[Any] = Counter(p for edge in selected.values() for p in edge)
    points = []
    for anchor in (side["a"], side["b"]):
        key = core.ref_key(anchor["ref"])
        if (
            key not in selected
            or type(anchor["end"]) is not int
            or anchor["end"] not in (0, 1)
        ):
            raise ValueError("PORTAL_SIDE_NOT_IN_INDEPENDENT_ROOM_SOURCE_SELECTION")
        p = selected[key][anchor["end"]]
        if ends[p] != 1:
            raise ValueError("PORTAL_SIDE_NOT_AN_OPEN_SOURCE_END")
        points.append(p)
    a, b = points
    if a == b or (a[0] != b[0] and a[1] != b[1]):
        raise ValueError("PORTAL_SIDE_NOT_STRAIGHT_OPENING")
    return tuple(sorted(points))


def portal_result(
    page: dict[str, Any],
    rooms: dict[str, Any],
    portal: dict[str, Any],
    scales: dict[str, Any],
) -> dict[str, Any]:
    core, _ = dependencies()
    if (
        portal.get("engineering_approved", False) is not False
        or portal.get("verified_clear_width_mm") is not None
    ):
        raise ValueError("CALLER_CANNOT_APPROVE_DOOR_OR_NET_WIDTH")
    if not portal.get("review_basis") or not portal.get("door_mark_source_region"):
        raise ValueError("PORTAL_SOURCE_VISUAL_REVIEW_REQUIRED")
    sides = portal["sides"]
    if not 1 <= len(sides) <= 2 or len({s["room_id"] for s in sides}) != len(sides):
        raise ValueError("INDEPENDENT_PORTAL_SIDES_REQUIRED")
    evidence = [side_evidence(page, rooms[s["room_id"]], s) for s in sides]
    a, b = evidence[0]
    axis = 0 if a[1] == b[1] else 1
    for other in evidence[1:]:
        if [p[axis] for p in other] != [a[axis], b[axis]]:
            raise ValueError("CONFLICTING_TWO_SIDE_OPENING_INTERVAL")
    caps = [core.source_segment(page, r) for r in portal["jamb_cap_refs"]]
    if len(caps) != 2 or not all(any(p in cap for cap in caps) for p in (a, b)):
        raise ValueError("SOURCE_JAMB_CAPS_REQUIRED")
    if len(evidence) == 2:
        if not all(
            any(set(cap) == {evidence[0][k], evidence[1][k]} for cap in caps)
            for k in (0, 1)
        ):
            raise ValueError("TWO_SIDE_CAPS_DO_NOT_CONNECT_THE_SELECTED_FACES")
    witness_refs = portal.get("witness_refs", [])
    for ref in witness_refs:
        core.source_item(
            page, ref
        )  # Retain lines/rectangles/cubic arcs verbatim, never flatten.
    if not witness_refs:
        raise ValueError("SOURCE_PANEL_ARC_OR_DOOR_MARK_GLYPH_REQUIRED")
    scale = scales.get("X" if axis == 0 else "Y")
    length = None if scale is None else abs(b[axis] - a[axis]) * core.rational(scale)
    return {
        "contract": "XinzhaoPhysicalPortalV1",
        "portal_id": portal["portal_id"],
        "source_page": 1,
        "source_path_references": portal["jamb_cap_refs"] + witness_refs,
        "door_mark": portal["door_mark"],
        "door_mark_source_region": portal["door_mark_source_region"],
        "door_leaf_reference": portal.get("door_leaf_reference"),
        "door_swing_reference": portal.get("door_swing_reference"),
        "from_physical_room": sides[0]["room_id"],
        "to_physical_room": sides[1]["room_id"] if len(sides) == 2 else None,
        "from_room_binding_status": "SOURCE_EDGE_ENDS_AND_JAMBS_BOUND",
        "to_room_binding_status": "SOURCE_EDGE_ENDS_AND_JAMBS_BOUND"
        if len(sides) == 2
        else "UNVERIFIED",
        "reference_opening_geometry": [
            [core.export_point(p) for p in edge] for edge in evidence
        ],
        "derived_opening_length_mm": str(length) if length is not None else None,
        "verified_clear_width_mm": None,
        "door_type": portal["door_type"],
        "flow_class": "UNVERIFIED",
        "connection_status": "TWO_SIDE_SOURCE_BOUND_REFERENCE"
        if len(sides) == 2
        else "ONE_SIDE_VERIFIED",
        "process_direction": "UNVERIFIED",
        "validated_material_route": False,
        "engineering_approved": False,
    }


def analyze_source(
    source: dict[str, Any], review: dict[str, Any], calibration: dict[str, Any]
) -> dict[str, Any]:
    core, _ = dependencies()
    if source["source_sha256"] != review["source_sha256"]:
        raise ValueError("SOURCE_HASH_MISMATCH")
    if review.get("validated_material_routes"):
        raise ValueError("OFFLINE_DRAWING_TOPOLOGY_CANNOT_VALIDATE_ROUTES")
    page = source["pages"][0]
    originals = review["rooms"]
    ids = [r["physical_room_id"] for r in originals]
    if len(set(ids)) != len(ids):
        raise ValueError("DUPLICATE_PHYSICAL_ROOM_ID")
    rooms = {r["physical_room_id"]: r for r in originals}
    transform = calibration["metric_transform"]
    scales = {
        k: transform[k]["mm_per_pdf_point"] if transform else None for k in ("X", "Y")
    }
    portals = [portal_result(page, rooms, p, scales) for p in review["portals"]]
    for portal in portals:
        portal["source_pdf_reference"] = source["source_sha256"]
    if len({p["portal_id"] for p in portals}) != len(portals):
        raise ValueError("DUPLICATE_PORTAL_ID")
    results = []
    for room in originals:
        if room[
            "physical_room_id"
        ] == "SO2_FUMIGATION_TRANSFER" and "二氧化硫" not in str(
            room["source_room_name"]
        ):
            raise ValueError("SO2_SOURCE_IDENTITY_MUST_NOT_BECOME_CO2")
        if room.get("engineering_approved", False) is not False:
            raise ValueError("CALLER_ROOM_APPROVAL_NOT_ACCEPTED")
        refs = room["face_refs"]
        if any(
            r["kind"]
            not in {"WALL_SEGMENT", "COLUMN_GEOMETRY", "BOUNDARY_CONTINUATION"}
            or not r.get("review_basis")
            for r in refs
        ):
            raise ValueError("UNREVIEWED_WALL_SEMANTICS")
        edges = [core.source_segment(page, r) for r in refs]
        wall_check = core.topology(edges)
        records = [
            {**r, "source_points": [core.export_point(p) for p in e]}
            for r, e in zip(refs, edges, strict=True)
        ]
        related = []
        for p, definition in zip(portals, review["portals"], strict=True):
            for s in definition["sides"]:
                if s["room_id"] == room["physical_room_id"]:
                    edges.append(side_evidence(page, room, s))
                    related.append(p["portal_id"])
        outer = core.topology(edges)
        holes = [
            core.topology([core.source_segment(page, r) for r in ring])
            for ring in room.get("internal_ring_refs", [])
        ]
        # R2 intentionally blocks multi-ring area. Keep its conservative boundary; no new kernel.
        complete = (
            outer["closed"]
            and not holes
            and room.get("selection_scope") == "FULL_REVIEWED_PERIMETER"
        )
        area = width = depth = None
        if complete and transform:
            vertices = [core.point(p) for p in outer["vertices"]]
            sx, sy = core.rational(scales["X"]), core.rational(scales["Y"])
            area = str(
                core.rational(outer["exact_area_pdf_points_squared"])
                * sx
                * sy
                / 1000000
            )
            width = str(
                (max(p[0] for p in vertices) - min(p[0] for p in vertices)) * sx
            )
            depth = str(
                (max(p[1] for p in vertices) - min(p[1] for p in vertices)) * sy
            )
        results.append(
            {
                "physical_room_id": room["physical_room_id"],
                "object_type": room["object_type"],
                "source_room_name": room["source_room_name"],
                "source_pdf_sha256": source["source_sha256"],
                "source_page": 1,
                "source_roi": room["source_roi"],
                "source_label_evidence": room["source_label_evidence"],
                "source_path_references": refs,
                "boundary_source_segments": records,
                "boundary_reference_closed": bool(complete),
                "continuous_wall_closed": wall_check["closed"],
                "inner_face_reference_status": "PARTIAL_SOURCE_REFERENCE_ENGINEERING_REVIEW_REQUIRED",
                "finished_clear_boundary_status": "UNAVAILABLE",
                "reference_width_mm": width,
                "reference_depth_mm": depth,
                "reference_area_m2": area,
                "drawn_reference_enclosure_area_m2": area,
                "wall_face_area_m2": None,
                "finished_clear_area_m2": None,
                "approved_net_area_m2": None,
                "outer_ring_topology": outer,
                "internal_ring_topology": holes,
                "wall_only_topology": wall_check,
                "unresolved_reason": room.get("unresolved_reason"),
                "multi_ring_area_status": "BLOCKED_R2_MULTIRING_NOT_DECOMPOSED"
                if holes
                else "NOT_APPLICABLE",
                "design_temperature": room["design_temperature"],
                "drawing_clear_height": room["drawing_clear_height"],
                "related_portals": related,
                "related_equipment_references": room.get(
                    "related_equipment_references", []
                ),
                "logical_zone_candidates": room["logical_zone_candidates"],
                "mapping_review_status": "MAPPING_REVIEW_REQUIRED",
                "process_direction": "UNVERIFIED",
                "engineering_approved": False,
            }
        )
    edges_out = [
        {
            "type": "SOURCE_BOUND_PORTAL",
            "portal_id": p["portal_id"],
            "from": p["from_physical_room"],
            "to": p["to_physical_room"],
            "route_validated": False,
        }
        for p in portals
        if p["connection_status"] == "TWO_SIDE_SOURCE_BOUND_REFERENCE"
    ]
    for relation in review.get("non_portal_relations", []):
        if relation["type"] not in {
            "SHARED_WALL",
            "DRAWING_ADJACENCY",
            "DECLARED_PROCESS_CONNECTION",
        }:
            raise ValueError("NO_ROUTE_UPGRADE_FROM_DRAWING")
        if not {relation["from"], relation["to"]}.issubset(rooms):
            raise ValueError("UNKNOWN_RELATION_ROOM")
        if relation["type"] == "SHARED_WALL":
            refs = relation["source_refs"]
            if len(refs) != 2 or not relation.get("review_basis"):
                raise ValueError("SHARED_WALL_REQUIRES_REVIEWED_FACE_PAIR")
            for key, ref in zip(("from", "to"), refs, strict=True):
                if core.ref_key(ref) not in {
                    core.ref_key(r) for r in rooms[relation[key]]["face_refs"]
                }:
                    raise ValueError("SHARED_WALL_FACE_NOT_IN_ROOM_SOURCE")
            a, b = [core.source_segment(page, r) for r in refs]
            axis = 1 if a[0][0] == a[1][0] else 0
            if b[0][1 - axis] != b[1][1 - axis] or min(
                max(p[axis] for p in a), max(p[axis] for p in b)
            ) <= max(min(p[axis] for p in a), min(p[axis] for p in b)):
                raise ValueError("SHARED_WALL_FACES_NOT_PARALLEL_OVERLAPPING")
        edges_out.append({**relation, "route_validated": False})
    mapping = [
        {
            "logical_zone_id": zone,
            "physical_room_ids": [
                r["physical_room_id"]
                for r in originals
                if zone in r["logical_zone_candidates"]
            ],
            "mapping_basis": "INDIVIDUAL_SOURCE_LABELS_AND_SOURCE_BOUND_OBJECTS_NOT_PRODUCTION_AUTHORITY",
            "mapping_status": "MAPPING_REVIEW_REQUIRED",
        }
        for zone in sorted({z for r in originals for z in r["logical_zone_candidates"]})
    ]
    return {
        "contract": "XinzhaoProcessRoomTopologyV1",
        "source_sha256": source["source_sha256"],
        "rooms": results,
        "portals": portals,
        "graph": {
            "contract": "PhysicalRoomConnectivityGraphV1",
            "directed": False,
            "nodes": ids,
            "edges": edges_out,
            "validated_material_routes": [],
        },
        "mapping": {
            "contract": "LogicalPhysicalZoneMappingV1",
            "mappings": mapping,
            "unmapped_physical_rooms": [
                r["physical_room_id"]
                for r in originals
                if not r["logical_zone_candidates"]
            ],
        },
        "engineering_approved": False,
        "p2d_full_pass_count": 0,
        "real_factory_solves": 0,
        "real_truck_searches": 0,
        "native_solver_calls": 0,
        "new_owner_grant": False,
    }


def analyze(pdf: Path, review: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    _, reader = dependencies()
    extractor, validator = reader.r1_reader()
    source = extractor.inventory(pdf)
    if source["source_sha256"] != EXPECTED_SOURCE_SHA:
        raise ValueError("OWNER_PINNED_SOURCE_BYTES_REQUIRED")
    if source["pdf_page_count"] != 1:
        raise ValueError("EXPECTED_ONE_REVIEWED_SOURCE_PAGE")
    calibration = validator.calibrate(source["pages"][0], review["anchors"])
    return source, analyze_source(source, review, calibration)
