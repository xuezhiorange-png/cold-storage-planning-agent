"""Source-bound drawing topology, not construction/net-area Authority.

No snapping, inferred rectangle, automatic gap bridge or curve flattening.
Reviewed source selections are a reproducible interpretation, not approval tokens.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from fractions import Fraction
from itertools import combinations
from typing import Any

Point = tuple[Fraction, Fraction]
Segment = tuple[Point, Point]


def encode(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()


def rational(value: Any) -> Fraction:
    if type(value) not in (int, float, str, Fraction):
        raise ValueError("INVALID_COORDINATE")
    # Preserve the exact IEEE binary values read from the PDF, not decimal rounding.
    return Fraction(value)


def point(value: Any) -> Point:
    if len(value) != 2:
        raise ValueError("POINT_REQUIRED")
    return rational(value[0]), rational(value[1])


def transform(value: Any, matrix: Any) -> Point:
    x, y = point(value)
    a, b, c, d, e, f = (rational(v) for v in matrix)
    return a * x + c * y + e, b * x + d * y + f


def export_point(value: Point) -> list[str]:
    return [str(v) for v in value]


def source_item(page: dict[str, Any], ref: dict[str, Any]) -> list[Any]:
    for key in ("path_id", "item_id"):
        if type(ref.get(key)) is not int or ref[key] < 0:
            raise ValueError("INVALID_SOURCE_REFERENCE")
    try:
        return list(page["vectors"][ref["path_id"]]["items"][ref["item_id"]])
    except IndexError as exc:
        raise ValueError("SOURCE_REFERENCE_OUT_OF_RANGE") from exc


def source_segment(page: dict[str, Any], ref: dict[str, Any]) -> Segment:
    item = source_item(page, ref)
    if item[0] == "l":
        if "edge" in ref:
            raise ValueError("LINE_HAS_NO_RECTANGLE_EDGE")
        raw = item[1:3]
    elif item[0] == "re":
        edge = ref.get("edge")
        if type(edge) is not int or edge not in range(4):
            raise ValueError("RECTANGLE_EDGE_REQUIRED")
        x0, y0, x1, y1 = item[1]
        corners = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
        raw = [corners[edge], corners[(edge + 1) % 4]]
    else:
        raise ValueError("NONLINEAR_SOURCE_RETAINED_NOT_FLATTENED")
    original = (
        transform(raw[0], page["rotation_matrix"]),
        transform(raw[1], page["rotation_matrix"]),
    )
    ends = list(original)
    for trim in ref.get("source_bound_trims", []):
        if trim["source_ref"].get("source_bound_trims"):
            raise ValueError("NESTED_TRIM_NOT_SUPPORTED")
        if type(trim["end"]) is not int or trim["end"] not in (0, 1):
            raise ValueError("INVALID_TRIM_ENDPOINT")
        if type(trim["source_end"]) is not int or trim["source_end"] not in (0, 1):
            raise ValueError("INVALID_TRIM_SOURCE_ENDPOINT")
        candidate = source_segment(page, trim["source_ref"])[trim["source_end"]]
        if not on_segment(candidate, original):
            raise ValueError("TRIM_POINT_NOT_EXACTLY_ON_ORIGINAL_SOURCE")
        ends[trim["end"]] = candidate
    if ends[0] == ends[1]:
        raise ValueError("TRIM_REMOVES_WHOLE_SEGMENT")
    return ends[0], ends[1]


def ref_key(ref: dict[str, Any]) -> tuple[int, int, int | None]:
    return ref["path_id"], ref["item_id"], ref.get("edge")


def on_segment(p: Point, edge: Segment) -> bool:
    a, b = edge
    cross = (p[0] - a[0]) * (b[1] - a[1]) - (p[1] - a[1]) * (b[0] - a[0])
    return cross == 0 and all(
        min(a[k], b[k]) <= p[k] <= max(a[k], b[k]) for k in (0, 1)
    )


def intersection_kind(first: Segment, second: Segment) -> str | None:
    """Exact test for axis-aligned line pairs, including overlap and T junction."""
    a, b = first
    c, d = second
    horizontal_a, horizontal_b = a[1] == b[1], c[1] == d[1]
    if horizontal_a == horizontal_b:
        fixed = 1 if horizontal_a else 0
        varying = 1 - fixed
        if a[fixed] != c[fixed]:
            return None
        lo = max(min(a[varying], b[varying]), min(c[varying], d[varying]))
        hi = min(max(a[varying], b[varying]), max(c[varying], d[varying]))
        if lo < hi:
            return "COLLINEAR_OVERLAP"
        if lo == hi and not set(first) & set(second):
            return "UNBOUND_TOUCH"
        return None
    h, v = (first, second) if horizontal_a else (second, first)
    p = (v[0][0], h[0][1])
    if on_segment(p, h) and on_segment(p, v) and p not in set(h) & set(v):
        return "CROSSING_OR_T_JUNCTION"
    return None


def topology(edges: list[Segment]) -> dict[str, Any]:
    """Return only an exactly connected simple cycle; never repair endpoints."""
    issues: list[str] = []
    adjacency: dict[Point, list[Point]] = defaultdict(list)
    seen: set[tuple[Point, Point]] = set()
    usable = []
    for edge in edges:
        a, b = edge
        if a == b:
            issues.append("ZERO_LENGTH")
            continue
        if a[0] != b[0] and a[1] != b[1]:
            issues.append("NONORTHOGONAL_UNSUPPORTED_NO_APPROXIMATION")
            continue
        canonical = (min(edge), max(edge))
        if canonical in seen:
            issues.append("DUPLICATE_SEGMENT")
        seen.add(canonical)
        adjacency[a].append(b)
        adjacency[b].append(a)
        usable.append(edge)
    for first, second in combinations(usable, 2):
        kind = intersection_kind(first, second)
        if kind:
            issues.append(kind)
    endpoints = sorted(p for p, neighbours in adjacency.items() if len(neighbours) == 1)
    if any(len(neighbours) != 2 for neighbours in adjacency.values()):
        issues.append("OPEN_ENDPOINT_OR_EXTRA_BRANCH")
    vertices: list[Point] = []
    if adjacency and not issues:
        start = min(adjacency)
        current, previous = start, None
        for _ in range(len(adjacency) + 1):
            vertices.append(current)
            choices = sorted(p for p in adjacency[current] if p != previous)
            following = choices[0]
            if following == start:
                break
            previous, current = current, following
        if len(vertices) != len(adjacency):
            issues.append("MULTIPLE_DISCONNECTED_RINGS")
    if not adjacency:
        issues.append("EMPTY_BOUNDARY")
    area = None
    if not issues:
        area = (
            abs(
                sum(
                    (
                        a[0] * b[1] - b[0] * a[1]
                        for a, b in zip(
                            vertices, vertices[1:] + vertices[:1], strict=True
                        )
                    ),
                    Fraction(),
                )
            )
            / 2
        )
        if area == 0:
            issues.append("ZERO_AREA")
    return {
        "closed": not issues,
        "issues": sorted(set(issues)),
        "unbound_endpoints": [export_point(p) for p in endpoints],
        "vertices": [export_point(p) for p in vertices] if not issues else None,
        "exact_area_pdf_points_squared": str(area) if not issues else None,
        "snap_tolerance": "NONE",
    }


def boundary_result(
    source: dict[str, Any], selection: dict[str, Any], scales: dict[str, Any]
) -> dict[str, Any]:
    if selection["source_sha256"] != source["source_sha256"]:
        raise ValueError("SOURCE_HASH_MISMATCH")
    if selection.get("engineering_approved", False) is not False:
        raise ValueError("CALLER_APPROVAL_NOT_ACCEPTED")
    page_number = selection["source_page"]
    if type(page_number) is not int or not 1 <= page_number <= source["pdf_page_count"]:
        raise ValueError("INVALID_SOURCE_PAGE")
    page = source["pages"][page_number - 1]
    wall_edges, all_edges, records = [], [], []
    selected: dict[tuple[int, int, int | None], Segment] = {}
    for ref in selection["face_refs"]:
        if ref["kind"] not in {
            "WALL_SEGMENT",
            "BOUNDARY_CONTINUATION",
            "COLUMN_GEOMETRY",
        }:
            raise ValueError("NON_BOUNDARY_SEMANTICS")
        if not ref.get("review_basis"):
            raise ValueError("WALL_SEMANTICS_REVIEW_REQUIRED")
        edge = source_segment(page, ref)
        selected[ref_key(ref)] = edge
        all_edges.append(edge)
        if ref["kind"] in {"WALL_SEGMENT", "COLUMN_GEOMETRY"}:
            wall_edges.append(edge)
        records.append(
            {
                **ref,
                "points": [export_point(p) for p in edge],
                "status": "SOURCE_VECTOR_VERIFIED",
            }
        )
    doors = []
    for door in selection.get("doors", []):
        if not door.get("review_basis"):
            raise ValueError("DOOR_EVIDENCE_REVIEW_REQUIRED")
        if door.get("clear_door_width_mm") is not None:
            raise ValueError("DOOR_MARK_IS_NOT_CLEAR_WIDTH_AUTHORITY")
        anchors = []
        for end in ("a", "b"):
            anchor = door[end]
            if (
                ref_key(anchor["ref"]) not in selected
                or type(anchor["end"]) is not int
                or anchor["end"] not in (0, 1)
            ):
                raise ValueError("DOOR_ENDPOINT_NOT_ON_SELECTED_SOURCE_EDGE")
            anchors.append(selected[ref_key(anchor["ref"])][anchor["end"]])
        if (
            source_item(page, door["leaf_ref"])[0] != "l"
            or source_item(page, door["swing_ref"])[0] != "c"
        ):
            raise ValueError("SOURCE_DOOR_LEAF_AND_UNMODIFIED_ARC_REQUIRED")
        a, b = anchors
        if a == b or (a[0] != b[0] and a[1] != b[1]):
            raise ValueError("DOOR_REFERENCE_LINE_NOT_AXIS_ALIGNED")
        edge = (a, b)
        # Endpoints must be actual open endpoints, not a new chord across the room.
        degrees: dict[Point, int] = defaultdict(int)
        for p, q in all_edges:
            degrees[p] += 1
            degrees[q] += 1
        if degrees[a] != 1 or degrees[b] != 1:
            raise ValueError("DOOR_ENDPOINT_IS_NOT_AN_OPEN_END")
        all_edges.append(edge)
        axis = "X" if a[1] == b[1] else "Y"
        measured = (
            None
            if scales.get(axis) is None
            else abs(a[0] - b[0] + a[1] - b[1]) * rational(scales[axis])
        )
        doors.append(
            {
                **door,
                "kind": "DOOR_OPENING_NOT_WALL",
                "points": [export_point(p) for p in edge],
                "derived_source_gap_mm": str(measured)
                if measured is not None
                else None,
                "clear_door_width_mm": None,
                "source_arc_preserved": True,
            }
        )
    wall_check = topology(wall_edges)
    full_check = topology(all_edges)
    metric_area = width = depth = None
    if (
        full_check["closed"]
        and scales.get("X") is not None
        and scales.get("Y") is not None
    ):
        sx, sy = rational(scales["X"]), rational(scales["Y"])
        if sx <= 0 or sy <= 0:
            raise ValueError("INVALID_METRIC_SCALE")
        vertices = [point(p) for p in full_check["vertices"]]
        width = str((max(p[0] for p in vertices) - min(p[0] for p in vertices)) * sx)
        depth = str((max(p[1] for p in vertices) - min(p[1] for p in vertices)) * sy)
        metric_area = str(
            rational(full_check["exact_area_pdf_points_squared"]) * sx * sy / 1000000
        )
    return {
        "contract": "XinzhaoRoomBoundaryV1",
        "room_id": selection["room_id"],
        "source_room_id": selection["source_room_id"],
        "room_name": selection["room_name"],
        "source_pdf_sha256": source["source_sha256"],
        "source_page": page_number,
        "source_roi": selection["source_roi"],
        "roi_used_as_boundary": False,
        "boundary_segments": records,
        "source_path_references": sorted(
            {r["path_id"] for r in records}
            | {d[k]["path_id"] for d in doors for k in ("leaf_ref", "swing_ref")}
        ),
        "door_openings": doors,
        "boundary_vertex_sequence": full_check["vertices"],
        "boundary_closed": full_check["closed"],
        "wall_only_topology": wall_check,
        "reference_topology": full_check,
        "wall_centreline_status": "NOT_EXTRACTED",
        "wall_face_status": "DRAWN_INNER_FACE_REFERENCE_REVIEW_REQUIRED",
        "finished_clear_face_status": "FINISHED_CLEAR_BOUNDARY_UNAVAILABLE",
        "continuous_closed_wall_boundary": wall_check["closed"],
        "net_clear_boundary": None,
        "unresolved_gaps": full_check["unbound_endpoints"],
        "geometric_width_mm": width,
        "geometric_depth_mm": depth,
        "geometric_area_m2": metric_area,
        "area_scope": "GROSS_DRAWN_INNER_FACE_REFERENCE_ENCLOSURE_WITH_EXPLICIT_OPENINGS",
        "wall_envelope_area_m2": None,
        "finished_clear_area_m2": None,
        "usable_floor_area_m2": None,
        "internal_objects": selection.get("internal_objects", []),
        "internal_structure_review": "NO_STRUCTURAL_ABSENCE_OR_FINISHED_FLOOR_CLAIM",
        "engineering_origin_status": "UNVERIFIED_ROOM_LOCAL_RELATIVE_ONLY",
        "local_origin_display_pdf": full_check["vertices"][0]
        if full_check["closed"]
        else None,
        "review_required": True,
        "engineering_approved": False,
        "missing_dimension_evidence": selection["missing_dimension_evidence"],
        "exact_blocker": "FINISH_BUILDUP_DOOR_SCHEDULE_AND_FORMAL_DRAWING_REVIEW_UNAVAILABLE",
        "real_factory_solves": 0,
        "real_truck_searches": 0,
        "native_solver_calls": 0,
        "new_owner_grant": False,
    }


def source_digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
