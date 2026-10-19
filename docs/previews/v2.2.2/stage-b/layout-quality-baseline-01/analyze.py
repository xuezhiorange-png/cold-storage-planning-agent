"""Exact, offline quality facts only. No solver, grant, selector or runtime imports."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import combinations
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
VERSION = "offline-layout-quality-facts@1.0.0"
MAJOR = (
    "primary_precooling_room",
    "secondary_precooling_room",
    "sorting_packaging_room",
    "finished_goods_room",
    "packaging_material_storage",
)
CHAIN = (
    "raw_fruit_buffer",
    "primary_precooling_room",
    "sorting_packaging_room",
    "secondary_precooling_room",
    "coating_room",
    "finished_goods_room",
    "shipping_channel",
)
Box = tuple[int, int, int, int]
Point = tuple[int, int]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def number(value: Fraction | int) -> str:
    with localcontext() as context:
        context.prec = 40
        return (
            format(Decimal(value.numerator) / Decimal(value.denominator), "f")
            .rstrip("0")
            .rstrip(".")
            if Fraction(value).denominator != 1
            else str(value.numerator)
        )


def mm(value: Any) -> int:
    exact = Fraction(str(value)) * 1000
    if exact.denominator != 1:
        raise ValueError("not on authoritative integer-mm grid")
    return exact.numerator


def point(value: dict[str, Any]) -> Point:
    return mm(value["x"]), mm(value["y"])


def box(zone: dict[str, Any]) -> Box:
    x, y = point(zone)
    w, d = mm(zone["width_m"]), mm(zone["depth_m"])
    if zone["rotation_deg"] == 90:
        w, d = d, w
    elif zone["rotation_deg"] != 0:
        raise ValueError("unsupported rotation")
    if min(w, d) <= 0:
        raise ValueError("degenerate room")
    return x, y, x + w, y + d


def contact(a: Box, b: Box) -> tuple[str | None, int]:
    x0, y0, x1, y1 = a
    u0, v0, u1, v1 = b
    height = max(0, min(y1, v1) - max(y0, v0))
    width = max(0, min(x1, u1) - max(x0, u0))
    if x1 == u0 and height:
        return "E", height
    if x0 == u1 and height:
        return "W", height
    if y1 == v0 and width:
        return "N", width
    if y0 == v1 and width:
        return "S", width
    return None, 0


def grid_facts(boxes: dict[str, Box]) -> dict[str, Any]:
    # Same positive-shared-wall primary axes as the frozen P0A offline helper.
    xs, ys = set(), set()
    for a, b in combinations([boxes[k] for k in MAJOR], 2):
        direction, _ = contact(a, b)
        if direction == "E":
            xs.add(a[2])
        elif direction == "W":
            xs.add(a[0])
        elif direction == "N":
            ys.add(a[3])
        elif direction == "S":
            ys.add(a[1])
    numerator = sum(int(v in xs) for k in MAJOR for v in (boxes[k][0], boxes[k][2]))
    numerator += sum(int(v in ys) for k in MAJOR for v in (boxes[k][1], boxes[k][3]))
    return {
        "aligned_incidences": numerator,
        "total_incidences": 20,
        "primary_x_axes_mm": sorted(xs),
        "primary_y_axes_mm": sorted(ys),
    }


def depth_exclusions(roles: dict[str, Any]) -> list[dict[str, Any]]:
    """P0C depth-pair@1.0.0: unique dissimilar roles are not a repeated room bank."""
    excluded = []
    special = {"secondary_precooling_room", "finished_goods_room"}
    for a, b in combinations(MAJOR, 2):
        if {a, b} != special:
            reason = "DISSIMILAR_ROLES_NOT_A_REPEATED_BANK; P0C depth-pair@1.0.0"
        elif (
            roles[a]["composition_group"] != roles[b]["composition_group"]
            or roles[a]["composition_band"] != roles[b]["composition_band"]
        ):
            reason = "SECONDARY_FINISHED_NOT_IN_SAME_CURRENT_P1A_GROUP_AND_BAND"
        else:
            raise ValueError("Potential eligible depth pair needs actual local band authority")
        excluded.append({"pair": [a, b], "eligible": False, "reason": reason})
    return excluded


def inside(p: tuple[Fraction, Fraction], vertices: list[Point]) -> bool:
    x, y = p
    result = False
    for a, b in zip(vertices, vertices[1:] + vertices[:1], strict=True):
        if (a[1] > y) != (b[1] > y):
            cross_x = Fraction(b[0] - a[0], b[1] - a[1]) * (y - a[1]) + a[0]
            if x < cross_x:
                result = not result
    return result


def components(cells: set[tuple[int, int]]) -> int:
    cells = cells.copy()
    count = 0
    while cells:
        count += 1
        pending = [cells.pop()]
        while pending:
            x, y = pending.pop()
            for q in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if q in cells:
                    cells.remove(q)
                    pending.append(q)
    return count


def outline(vertices: list[Point]) -> dict[str, Any]:
    if vertices[0] == vertices[-1]:
        vertices = vertices[:-1]
    if len(vertices) < 4 or len(set(vertices)) != len(vertices):
        raise ValueError("invalid exterior ring")
    twice = 0
    perimeter = 0
    crosses = []
    for i, a in enumerate(vertices):
        b, previous = vertices[(i + 1) % len(vertices)], vertices[i - 1]
        if (a[0] == b[0]) == (a[1] == b[1]):
            raise ValueError("not a nondegenerate orthogonal boundary")
        twice += a[0] * b[1] - b[0] * a[1]
        perimeter += abs(a[0] - b[0]) + abs(a[1] - b[1])
        crosses.append((a[0] - previous[0]) * (b[1] - a[1]) - (a[1] - previous[1]) * (b[0] - a[0]))
    if not twice:
        raise ValueError("zero area")
    xs = sorted({p[0] for p in vertices})
    ys = sorted({p[1] for p in vertices})
    occupied, exterior = set(), set()
    grid_area = 0
    for i, j in ((i, j) for i in range(len(xs) - 1) for j in range(len(ys) - 1)):
        middle = Fraction(xs[i] + xs[i + 1], 2), Fraction(ys[j] + ys[j + 1], 2)
        if inside(middle, vertices):
            occupied.add((i, j))
            grid_area += (xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j])
        else:
            exterior.add((i, j))
    assert grid_area * 2 == abs(twice), "polygon/grid independent area mismatch"
    assert sum(c != 0 for c in crosses) - 2 * sum(c * twice < 0 for c in crosses) == 4
    return {
        "area_mm2": grid_area,
        "perimeter_mm": perimeter,
        "bbox_area_mm2": (xs[-1] - xs[0]) * (ys[-1] - ys[0]),
        "reflex": sum(c * twice < 0 for c in crosses),
        "turns": sum(c != 0 for c in crosses),
        "notches": components(exterior),
        "components": components(occupied),
    }


def route_facts(route: dict[str, Any]) -> dict[str, Any]:
    vertices = [point(p) for p in route["centerline"]]
    headings = []
    length = 0
    for a, b in zip(vertices, vertices[1:], strict=False):
        dx, dy = b[0] - a[0], b[1] - a[1]
        if dx and dy:
            raise ValueError("route is not rectilinear")
        length += abs(dx) + abs(dy)
        if dx or dy:
            headings.append(
                (0 if not dx else (1 if dx > 0 else -1), 0 if not dy else (1 if dy > 0 else -1))
            )
    turns = sum(a != b for a, b in zip(headings, headings[1:], strict=False))
    assert Fraction(str(route["route_length_m"])) == Fraction(length, 1000)
    assert route["turn_count"] == turns
    return {
        "from": route["from_ref"],
        "to": route["to_ref"],
        "length_m": number(Fraction(length, 1000)),
        "turns": turns,
        "topology": route["topology"],
        "flow_kind": route["flow_kind"],
        "clear_width_m": route["clear_width_m"],
        "portal_from": route["portal_from"],
        "portal_to": route["portal_to"],
        "scope": "INTERFACE_OR_EXPLICIT_CORRIDOR_ONLY; NO_IN_ROOM_CONNECTOR",
    }


def envelope_boxes(route: dict[str, Any]) -> list[Box]:
    boxes = []
    for polygon in route["corridor_envelope"]:
        pts = [point(p) for p in polygon["points"]]
        xs, ys = {p[0] for p in pts}, {p[1] for p in pts}
        if len(xs) != 2 or len(ys) != 2 or len(set(pts)) != 4:
            raise ValueError("envelope is not rectangular; do not approximate by bounding box")
        boxes.append((min(xs), min(ys), max(xs), max(ys)))
    return boxes


def envelope_overlap(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    intersections = []
    for first in envelope_boxes(a):
        for second in envelope_boxes(b):
            x0, y0 = max(first[0], second[0]), max(first[1], second[1])
            x1, y1 = min(first[2], second[2]), min(first[3], second[3])
            if x1 >= x0 and y1 >= y0:
                intersections.append(
                    {"box_mm": [x0, y0, x1, y1], "positive_area": x1 > x0 and y1 > y0}
                )
    return {
        "a": a["requirement_identity"],
        "b": b["requirement_identity"],
        "intersections": intersections,
        "scope": "Explicit corridor envelopes only; empty direct interface is not an indoor route",
    }


def centerline_contacts(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Exact closed intersection of recorded axis-aligned segments, including points."""
    contacts = set()
    aa, bb = [point(p) for p in a["centerline"]], [point(p) for p in b["centerline"]]
    for p, q in zip(aa, aa[1:], strict=False):
        for u, v in zip(bb, bb[1:], strict=False):
            x0 = max(min(p[0], q[0]), min(u[0], v[0]))
            y0 = max(min(p[1], q[1]), min(u[1], v[1]))
            x1 = min(max(p[0], q[0]), max(u[0], v[0]))
            y1 = min(max(p[1], q[1]), max(u[1], v[1]))
            if x0 <= x1 and y0 <= y1:
                contacts.add((x0, y0, x1, y1))
    return {
        "a": a["requirement_identity"],
        "b": b["requirement_identity"],
        "closed_contacts_mm": sorted(contacts),
        "scope": "Only recorded interface/corridor centerlines; no invented indoor paths",
    }


def metric(
    value: Any,
    unit: str,
    status: str,
    source: str,
    method: str,
    evidence: str,
    reason: str | None = None,
    version: str = VERSION,
) -> dict[str, Any]:
    result = {
        "VALUE": value,
        "UNIT": unit,
        "STATUS": status,
        "SOURCE": source,
        "CALCULATION_METHOD": method,
        "DEFINITION_VERSION": version,
        "EVIDENCE_HASH": evidence,
        "UNAVAILABLE_REASON": reason,
    }
    if isinstance(value, Fraction):
        result["EXACT_RATIONAL"] = str(value)
        result["VALUE"] = number(value)
    assert status in {"MEASURED", "DERIVED", "NOT_APPLICABLE", "UNAVAILABLE"}
    assert (value is None) == (status in {"UNAVAILABLE", "NOT_APPLICABLE"})
    return result


def analyze(data: dict[str, Any]) -> dict[str, Any]:
    app, p = data["engineering_validation"], data["provenance"]
    evidence = "sha256:" + p["raw_candidate_sha256"]
    boxes = {z["zone_code"]: box(z) for z in app["zones"]}
    roles = {r["zone_role"]: r for r in data["composition_handoff"]["zone_role_assignment"]}
    assert len(boxes) == len(roles) == 12
    rooms = []
    for z in app["zones"]:
        role = z["zone_code"]
        x0, y0, x1, y1 = boxes[role]
        w, d = x1 - x0, y1 - y0
        area = Fraction(w * d, 1000000)
        assert area == Fraction(z["actual_area_m2"])
        rooms.append(
            {
                "zone": role,
                "x_m": number(Fraction(x0, 1000)),
                "y_m": number(Fraction(y0, 1000)),
                "width_m": number(Fraction(w, 1000)),
                "depth_m": number(Fraction(d, 1000)),
                "area_m2": number(area),
                "nominal_width_m": z["width_m"],
                "nominal_depth_m": z["depth_m"],
                "min_side_m": number(Fraction(min(w, d), 1000)),
                "max_side_m": number(Fraction(max(w, d), 1000)),
                "aspect_ratio": number(Fraction(max(w, d), min(w, d))),
                "aspect_exact": str(Fraction(max(w, d), min(w, d))),
                "rotation_deg": z["rotation_deg"],
                "group": roles[role]["composition_group"],
                "band": roles[role]["composition_band"],
                "topology_role": roles[role]["topology_role"],
                "main_chain_rank": CHAIN.index(role) + 1 if role in CHAIN else None,
                "spatial_relation_to_sorting": {
                    "x": "WEST"
                    if x1 <= boxes["sorting_packaging_room"][0]
                    else "EAST"
                    if x0 >= boxes["sorting_packaging_room"][2]
                    else "OVERLAPPING_RANGE",
                    "y": "SOUTH"
                    if y1 <= boxes["sorting_packaging_room"][1]
                    else "NORTH"
                    if y0 >= boxes["sorting_packaging_room"][3]
                    else "OVERLAPPING_RANGE",
                    "scope": "Bounding interval relation, NOT a transport path",
                },
                "positive_shared_edges": [
                    {
                        "other": other,
                        "face": contact(boxes[role], b)[0],
                        "length_m": number(Fraction(contact(boxes[role], b)[1], 1000)),
                    }
                    for other, b in sorted(boxes.items())
                    if other != role and contact(boxes[role], b)[1]
                ],
            }
        )
    routes = [r for r in app["access_results"] if r["flow_kind"] != "TRUCK"]
    assert len(routes) == 11 and all(r["status"] == "PASS" for r in routes)
    route_rows = [route_facts(r) for r in routes]
    ingress = next(r for r in route_rows if r["from"] == "main_entrance")
    outline_result = outline([point(v) for v in app["building_footprint"]["footprint"]["points"]])
    assert Fraction(outline_result["area_mm2"], 1000000) == Fraction(
        app["building_footprint"]["gross_area_m2"]
    )
    grid = grid_facts(boxes)
    depth = depth_exclusions(roles)

    def m(v: Any, u: str, method: str, status: str = "DERIVED") -> dict[str, Any]:
        return metric(v, u, status, p["candidate_id"] + "/application", method, evidence)

    def unavailable(reason: str, u: str = "status") -> dict[str, Any]:
        return metric(
            None, u, "UNAVAILABLE", p["candidate_id"], "No inference permitted", evidence, reason
        )

    missing_route = (
        "RAW_RECEIVING is not bound; main interfaces do not supply within-room transport "
        "connectors, configured progress bands or a complete directed process route"
    )
    metrics = {
        "ROOM_DIMENSION_FACTS": m(
            rooms, "m,m2,deg", "Physical bounds after 0/90 rotation; integer mm", "MEASURED"
        ),
        "ROOM_ASPECT_RATIO_FACTS": m(
            {r["zone"]: {"exact": r["aspect_exact"], "decimal": r["aspect_ratio"]} for r in rooms},
            "ratio",
            "max(physical width,depth)/min(width,depth)",
        ),
        "ROOM_MIN_SIDE_FACTS": m(
            {r["zone"]: r["min_side_m"] for r in rooms}, "m", "min physical side"
        ),
        "MAJOR_ZONE_GRID_ALIGNMENT_RATE": m(
            Fraction(grid["aligned_incidences"], 20),
            "ratio",
            "P0 section6/P0A positive shared-wall axes; exact incidence/20",
        ),
        "MAJOR_ZONE_DEPTH_ALIGNMENT_RATE": metric(
            None,
            "ratio",
            "NOT_APPLICABLE",
            p["candidate_id"],
            "P0C depth-pair@1.0.0: no repeated bank; special Secondary/Finished pair "
            "has different current P1A group/band; all ten pair exclusions recorded",
            evidence,
            "ZERO_ELIGIBLE_PAIRS_UNDER_CURRENT_P1A_AND_DEPTH_PAIR_POLICY",
        ),
        "MAIN_BUILDING_COMPONENT_COUNT": m(
            outline_result["components"],
            "count",
            "Exact coordinate-compressed footprint interior connectivity",
        ),
        "BOUNDING_RECTANGLE_OCCUPANCY": m(
            Fraction(outline_result["area_mm2"], outline_result["bbox_area_mm2"]),
            "ratio",
            "Exact polygon area / axis-aligned bounding rectangle area",
        ),
        "EXTERIOR_REFLEX_CORNER_COUNT": m(
            outline_result["reflex"],
            "count",
            "Signed cross-product at each orthogonal exterior vertex; orientation independent",
        ),
        "EXTERIOR_NOTCH_COUNT": m(
            outline_result["notches"],
            "count",
            "P0C BUILDING_OUTLINE_CLASSIFIER_V1: edge-connected exterior pockets inside "
            "exact bounding rectangle; vertex-grid decomposition",
        ),
        "ISOLATED_APPENDAGE_COUNT": unavailable(
            "Owner/project purpose evidence for protrusions is absent; "
            "no width or length threshold invented",
            "count",
        ),
        "BUILDING_AREA_M2": m(
            Fraction(outline_result["area_mm2"], 1000000),
            "m2",
            "Shoelace cross-checked against exact grid-cell area and sealed application area",
        ),
        "BUILDING_PERIMETER_M": m(
            Fraction(outline_result["perimeter_mm"], 1000), "m", "Sum exact exterior edge lengths"
        ),
        "EXTERIOR_TURN_COUNT": m(
            outline_result["turns"],
            "count",
            "Count non-collinear exterior vertices; NOT reflex count",
        ),
        "PERSONNEL_ROUTE_LENGTH_M": m(
            ingress["length_m"],
            "m",
            "Sum actual main_entrance->changing centerline segments; no centroid connectors",
        ),
        "PERSONNEL_ROUTE_TURN_COUNT": m(
            ingress["turns"], "count", "Remove zero-length segments; collapse collinear headings"
        ),
        "PERSONNEL_LOGISTICS_SEPARATION": unavailable(
            "Recorded interfaces/envelopes do not describe indoor material paths, Office access, "
            "raw receiving or approved crossing treatment"
        ),
        "SIDE_BRANCH_CROSSES_MAIN_FLOW": unavailable(
            "Complete main product path and in-room branch connectors absent; "
            "corridor subset cannot prove global non-crossing"
        ),
        "FUNCTIONAL_GROUPING_PASS": unavailable(
            "P1A ownership/band intent recorded, but no complete route/group quality acceptance; "
            "P0/P1A Secondary ownership remains versioned"
        ),
        "ENGINEERING_HARD_VALIDATION_SCOPE": m(
            {
                "zone_count": 12,
                "must_pass_count": data["independent_validation"]["must_pass_count"],
                "non_truck_access_pass": 11,
                "independent": data["independent_validation"],
                "native_independent": data["native_independent_validation"],
                "source_site_hash": app["source_site_geometry_hash"],
                "footprint": "SEALED_APPLICATION_FOOTPRINT; OFFLINE_MATH_ONLY; "
                "NO_NEW_P2D_ACCEPTANCE",
            },
            "scope",
            "Read sealed independent/native validation, not inherited from another candidate",
            "MEASURED",
        ),
        "TRUCK_ROUTE_VALIDATED": m(
            app["truck_route_validated"],
            "boolean",
            "Read actual application Truck field",
            "MEASURED",
        ),
        "SHIPPING_LOADING_FACE_FACTS": m(
            {
                "segment": app["shipping_loading_face_segment"],
                "side": app["shipping_loading_face_side"],
                "truck_route_status": app["truck_route_status"],
            },
            "m,side,status",
            "Read sealed actual application face; no approved Truck envelope",
            "MEASURED",
        ),
        "P2D_FULL_PASS": m(
            app["p2_complete"],
            "boolean",
            "Read actual application p2_complete; construction is not full-pass",
            "MEASURED",
        ),
        "PROCESS_FLOW_VALIDATED": unavailable(missing_route),
        "LAYOUT_REGULARITY_VALIDATED": unavailable(
            "Numeric gates not calibrated; required process/functional facts unavailable"
        ),
    }
    for key in (
        "PROCESS_FLOW_ORDER_PASS",
        "MAIN_FLOW_BACKTRACK_COUNT",
        "MAIN_FLOW_TURN_COUNT",
        "MAIN_PROCESS_ROUTE_LENGTH_M",
    ):
        metrics[key] = unavailable(
            missing_route,
            "m" if key.endswith("LENGTH_M") else "status" if key.endswith("PASS") else "count",
        )
    metrics["PROCESS_ROUTE_EFFICIENCY_RATIO"] = unavailable(
        "Complete actual route AND comparable shortest-feasible-route certificate absent", "ratio"
    )
    ratios = []
    for a, b in ((MAJOR[0], MAJOR[2]), (MAJOR[2], MAJOR[1]), (MAJOR[1], MAJOR[3])):
        route = next((r for r in routes if {r["from_ref"], r["to_ref"]} == {a, b}), None)
        if route is None or route["topology"] != "DIRECT_SHARED_EDGE":
            ratios.append(
                {
                    "pair": [a, b],
                    "metric": metric(
                        None,
                        "ratio",
                        "NOT_APPLICABLE",
                        p["candidate_id"],
                        "No authoritative direct interface for this pair "
                        "(Coating remains a main stage); do not invent an adjacency",
                        evidence,
                        "NO_APPLICABLE_DIRECT_PORTAL",
                    ),
                }
            )
        else:
            ratios.append(
                {
                    "pair": [a, b],
                    "metric": m(
                        Fraction(contact(boxes[a], boxes[b])[1], mm(route["clear_width_m"])),
                        "ratio",
                        "shared-positive-edge length / actual portal width; pair-specific",
                    ),
                }
            )
    metrics["REQUIRED_ADJACENCY_SHARED_EDGE_RATIO"] = m(
        ratios, "per-pair ratio", "P0 section7; not an aggregated score"
    )
    comparisons = [
        envelope_overlap(a, b)
        for a in routes
        if a["flow_kind"] == "PEOPLE"
        for b in routes
        if b["flow_kind"] != "PEOPLE"
    ]
    line_contacts = [
        centerline_contacts(a, b)
        for a in routes
        if a["flow_kind"] == "PEOPLE"
        for b in routes
        if b["flow_kind"] != "PEOPLE"
    ]
    metrics["EXPLICIT_INTERFACE_ROUTE_FACTS"] = m(
        route_rows,
        "m,count,m",
        "Actual recorded Portal/centerline only; lengths independently recomputed",
    )
    metrics["RECORDED_CORRIDOR_INTERSECTIONS"] = m(
        comparisons,
        "mm",
        "Exact closed rectangle intersections; positive area distinguished from boundary touch",
    )
    metrics["RECORDED_CENTERLINE_CONTACTS"] = m(
        line_contacts,
        "mm",
        "Exact closed intersection of actual orthogonal interface/corridor segments",
    )
    return {
        "CANDIDATE_ID": p["candidate_id"],
        "SOURCE_HEAD": p["source_head"],
        "SOURCE_GEOMETRY_HASH": p["geometry_hash"],
        "SOURCE_APPLICATION_HASH": app["canonical_result_hash"],
        "APPLICATION_BYTES_PROJECTION_HASH": "sha256:" + sha(encoded(app)),
        "MAJOR_FAMILY_HASH": p["family_hash"],
        "V2_MEANINGFUL_CONSTRUCTION": p["v2_counted"],
        "V2_MEANINGFUL_HASH": p["meaningful_hash"],
        "METRICS": metrics,
        "GRID_AXIS_EVIDENCE": grid,
        "DEPTH_PAIR_ELIGIBILITY": {"eligible_pair_count": 0, "excluded_pairs": depth},
        "INTERFACE_ROUTE_FACTS": route_rows,
        "RECORDED_CORRIDOR_INTERSECTIONS": comparisons,
        "RECORDED_CENTERLINE_CONTACTS": line_contacts,
        "ROOM_ADJACENCY_DIRECTIONS_NOT_ROUTE_TURNS": [
            {"from": a, "to": b, "direction": contact(boxes[a], boxes[b])[0]}
            for a, b in zip(CHAIN, CHAIN[1:], strict=False)
        ],
        "RISK_REGISTER": [
            {
                "classification": "MEASURED_FACT",
                "finding": "Exact room and route values in METRICS; not clearance certification",
            },
            {
                "classification": "ENGINEERING_RISK",
                "finding": "Office/Changing/Coating aspect and short-side facts require equipment, "
                "staffing and operating-clearance review; no new hard aspect threshold",
            },
            {
                "classification": "CALIBRATION_REQUIRED",
                "finding": "Comparable positive room geometry, working envelopes, "
                "receiving/in-room transport and appendage purpose evidence missing",
            },
        ],
        "FORMAL_CONTRACT_VIOLATIONS_PROVEN": [],
        "NUMERIC_CALIBRATION_READY": False,
        "QUALITY_RANKING_PERFORMED": False,
        "NEW_ENGINEERING_ACCEPTANCE_PERFORMED": False,
    }


def run(directory: Path = HERE) -> dict[str, Any]:
    sources = json.loads((directory / "sources.json").read_text())
    assert (
        sha((directory / "inputs/server_authorities.json").read_bytes())
        == sources["authority_sha256"]
    )
    results: list[dict[str, Any]] = []
    room_rows: list[dict[str, Any]] = []
    for row in sources["candidates"]:
        path = directory / row["input"]
        assert sha(path.read_bytes()) == row["projection_sha256"]
        result = analyze(json.loads(path.read_text()))
        results.append(result)
        room_rows.extend(
            {"candidate": result["CANDIDATE_ID"], **r}
            for r in result["METRICS"]["ROOM_DIMENSION_FACTS"]["VALUE"]
        )
    assert len(results) == 8 and len(room_rows) == 96
    assert len({r["SOURCE_GEOMETRY_HASH"] for r in results}) == 8
    assert sum(r["V2_MEANINGFUL_CONSTRUCTION"] for r in results) == 6
    assert len({r["MAJOR_FAMILY_HASH"] for r in results if r["V2_MEANINGFUL_CONSTRUCTION"]}) == 4
    statuses: Counter[str] = Counter()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            if "STATUS" in value:
                statuses[value["STATUS"]] += 1
            for v in value.values():
                collect(v)
        elif isinstance(value, list):
            for v in value:
                collect(v)

    collect(results)
    facts = {
        "definition_version": VERSION,
        "physical_geometries": 8,
        "meaningful_constructions": 6,
        "major_families": 4,
        "p2d_full_pass": 0,
        "numeric_calibration_ready": False,
        "formal_thresholds_changed": False,
        "quality_ranking_performed": False,
        "metric_status_counts": dict(statuses),
        "status_count_method": "Every metric wrapper including three nested per-pair metrics "
        "per candidate; room dimension bundle counted once",
        "real_factory_solves": 0,
        "native_solver_calls": 0,
        "candidates": results,
    }
    (directory / "facts.json").write_bytes(encoded(facts))
    with (directory / "rooms.csv").open("w", newline="") as stream:
        fields = [k for k in room_rows[0] if k != "positive_shared_edges"] + [
            "positive_shared_edges"
        ]
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in room_rows:
            writer.writerow(
                {
                    **row,
                    "positive_shared_edges": json.dumps(
                        row["positive_shared_edges"], sort_keys=True
                    ),
                    "spatial_relation_to_sorting": json.dumps(
                        row["spatial_relation_to_sorting"], sort_keys=True
                    ),
                }
            )
    return facts


if __name__ == "__main__":
    run()
