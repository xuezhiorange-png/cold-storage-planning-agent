"""Legal P1 portals chosen jointly with equipment, plus bounded interior paths.

Uses the original profile and predicates. Wider interior aisles and the doorway
throat have separate witnesses; neither is a forklift kinematic approval.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from cold_storage.modules.layout.domain import access_routing as routing
from cold_storage.modules.layout.domain.access_authority import COLD_ROOM, resolve_access_profile
from cold_storage.modules.layout.domain.access_predicates import _evaluate_bound_requirement
from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.autonomous_process_routes import _inward, _ring
from cold_storage.modules.layout.domain.functional_material_geometry import (
    bounds_inside,
    rectilinear_path,
)
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    SegmentMM,
    polygon_to_dict,
)


def portal_approach(portal: Mapping[str, Any], room: PlacedRectangleV1, depth: int) -> list[int]:
    s = portal["segment"]
    a, b = s["start"], s["end"]
    x, y, r, t = room.bounds_mm
    u, v = round(Decimal(str(a["x"])) * 1000), round(Decimal(str(a["y"])) * 1000)
    z, w = round(Decimal(str(b["x"])) * 1000), round(Decimal(str(b["y"])) * 1000)
    if u == z:
        return (
            [u, min(v, w), u + depth, max(v, w)] if u == x else [u - depth, min(v, w), u, max(v, w)]
        )
    return [min(u, z), v, max(u, z), v + depth] if v == y else [min(u, z), v - depth, max(u, z), v]


def joint_portals(
    rooms: Mapping[str, PlacedRectangleV1],
    requirements: Sequence[Mapping[str, Any]],
    relationships: Sequence[Mapping[str, Any]],
    equipment: Mapping[str, Any],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    entrances: Mapping[str, SegmentMM],
) -> tuple[list[dict[str, Any]], list[PolygonMM], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    envelopes: list[PolygonMM] = []
    checks: list[dict[str, Any]] = []
    relations = {str(r["identity"]): r for r in relationships}

    def clear(portal: Mapping[str, Any], code: str, depth: int) -> bool:
        box = portal_approach(portal, rooms[code], depth)
        bodies = [i["bbox_mm"] for i in equipment["items"] if i["room"] == code]
        bodies += [routing._rectangle_bounds(o) for o in obstacles]
        center = _inward(portal, rooms[code], depth // 2)
        square = [
            center[0] - depth // 2,
            center[1] - depth // 2,
            center[0] + depth // 2,
            center[1] + depth // 2,
        ]
        return bounds_inside(square, rooms[code].bounds_mm) and not any(
            b and (positive_intersection(box, b) or positive_intersection(square, b))
            for b in bodies
        )

    for req in requirements:
        if req["flow_kind"] == "TRUCK":
            results.append(
                {
                    "requirement_identity": req["identity"],
                    "flow_kind": "TRUCK",
                    "status": "INPUT_REQUIRED_ACTUAL_VEHICLE_AND_LAND_SITE",
                    "truck_pass": False,
                }
            )
            continue
        obj = routing._requirement_object(req)
        profile = resolve_access_profile(obj.profile_identity)
        pw = routing._mm(profile.portal_clear_width_m, field="portal")
        if obj.cold_room_refs:
            pw = max(
                pw,
                routing._mm(resolve_access_profile(COLD_ROOM).portal_clear_width_m, field="cold"),
            )
        cw = 2000 if req["flow_kind"] == "PEOPLE" else 2500
        fr, to = obj.from_ref, obj.to_ref
        first, second = rooms.get(fr), rooms[to]
        shared = routing._shared_edge_segment(first, second) if first else None
        candidates: list[dict[str, Any]] = []
        if shared and obj.direct_allowed and first:
            fc, tc = routing._edge_match_for_shared(first, second, shared)
            relation = routing._relation_for(req, relations)
            ef = routing._edge_class(relation.get("from_edge_class")) if relation else None
            et = routing._edge_class(relation.get("to_edge_class")) if relation else None
            if (ef is None or ef == fc) and (et is None or et == tc):
                segments = [shared]
                vertical = shared[0][0] == shared[1][0]
                for code in (fr, to):
                    for aisle in equipment["layouts"][code]["service_corridors"]:
                        x, y, r, t = aisle["bbox_mm"]
                        if vertical and x <= shared[0][0] <= r:
                            lo, hi = max(y, shared[0][1]), min(t, shared[1][1])
                            if hi - lo >= pw:
                                segments.append(((shared[0][0], lo), (shared[0][0], hi)))
                        elif not vertical and y <= shared[0][1] <= t:
                            lo, hi = max(x, shared[0][0]), min(r, shared[1][0])
                            if hi - lo >= pw:
                                segments.append(((lo, shared[0][1]), (hi, shared[0][1])))
                for segment in segments:
                    candidates.extend(
                        routing._portal_candidates(
                            segment, edge_class=fc or "SHARED_EDGE", clear_width_mm=pw
                        )
                    )
                seen = set()
                for portal in candidates:
                    key = portal["segment_mm"]
                    if key in seen:
                        continue
                    seen.add(key)
                    pf = routing._portal_record(req, fr, portal)
                    pt = routing._portal_record(req, to, {**portal, "edge_class": tc})
                    if not clear(pf, fr, cw) or not clear(pt, to, cw):
                        continue
                    observation = {
                        "topology": "DIRECT_SHARED_EDGE",
                        "profile_identity": obj.profile_identity,
                        "transport_mode": profile.transport_mode,
                        "portal_clear_width_m": portal["clear_width_m"],
                        "edge_alignment_verified": True,
                        "route_shape": "STRAIGHT",
                        "turn_count": 0,
                    }
                    predicate = _evaluate_bound_requirement(obj, observation)
                    center = routing._point(routing._portal_center(key))
                    row = {
                        **routing._access_result_base(req),
                        **observation,
                        "portal_from": pf,
                        "portal_to": pt,
                        "centerline": [center, center],
                        "clear_width_m": portal["clear_width_m"],
                        "route_length_m": Decimal(0),
                        "status": predicate["status"],
                        "codes": list(predicate.get("codes", [])),
                        "selection_basis": "LEGAL_SHARED_EDGE_OFFSET_AND_BODY_FREE_APPROACH",
                    }
                    results.append(routing._hashed(row))
                    break
                else:
                    candidates = []
                if (
                    candidates
                    and len(results)
                    and results[-1].get("requirement_identity") == req["identity"]
                ):
                    continue
        hint: list[tuple[int, int]] = []
        external_result = None
        if not shared:
            fo = routing._edge_options(
                first, required_class=None, clear_width_mm=pw, boundary_segment=entrances.get(fr)
            )
            topts = routing._edge_options(second, required_class=None, clear_width_mm=pw)

            def corridor_options(code: str, pw: int = pw, cw: int = cw) -> list[dict[str, Any]]:
                opts: list[dict[str, Any]] = []
                for _, cls, edge in routing._edge_segments(rooms[code]):
                    for aisle in equipment["layouts"][code]["service_corridors"]:
                        x, y, r, t = aisle["bbox_mm"]
                        if edge[0][0] == edge[1][0] and x <= edge[0][0] <= r:
                            lo, hi = max(y, edge[0][1]), min(t, edge[1][1])
                            seg = ((edge[0][0], lo), (edge[0][0], hi))
                        elif edge[0][1] == edge[1][1] and y <= edge[0][1] <= t:
                            lo, hi = max(x, edge[0][0]), min(r, edge[1][0])
                            seg = ((lo, edge[0][1]), (hi, edge[0][1]))
                        else:
                            continue
                        if hi - lo >= pw:
                            opts.extend(
                                routing._portal_candidates(seg, edge_class=cls, clear_width_mm=pw)
                            )
                            trim = max(0, (cw - pw) // 2)
                            if hi - lo >= pw + 2 * trim:
                                inner = (
                                    ((seg[0][0], seg[0][1] + trim), (seg[1][0], seg[1][1] - trim))
                                    if seg[0][0] == seg[1][0]
                                    else (
                                        (seg[0][0] + trim, seg[0][1]),
                                        (seg[1][0] - trim, seg[1][1]),
                                    )
                                )
                                opts.extend(
                                    routing._portal_candidates(
                                        inner, edge_class=cls, clear_width_mm=pw
                                    )
                                )
                return opts

            if first:
                fo = (*corridor_options(fr), *fo)
            topts = (*corridor_options(to), *topts)
            floor = routing._rectangle_bounds(boundary)
            blockers = [q.bounds_mm for q in rooms.values()] + [
                b for o in obstacles if (b := routing._rectangle_bounds(o))
            ]

            def outside(
                p: Mapping[str, Any], code: str, cw: int = cw, req: Mapping[str, Any] = req
            ) -> tuple[int, int]:
                center = routing._portal_center(p["segment_mm"])
                if code in entrances:
                    return routing._boundary_interior_point(
                        center, entrances[code], boundary, cw // 2 + 1
                    )
                rec = routing._portal_record(req, code, p)
                inward = _inward(rec, rooms[code], cw // 2 + 1)
                return 2 * center[0] - inward[0], 2 * center[1] - inward[1]

            for f in fo:
                if first and not clear(routing._portal_record(req, fr, f), fr, cw):
                    continue
                for t in topts:
                    if not clear(routing._portal_record(req, to, t), to, cw) or not floor:
                        continue
                    start, end = outside(f, fr), outside(t, to)
                    path, _ = rectilinear_path(
                        start, end, floor, blockers, cw, cw, node_budget=1500
                    )
                    if path:
                        hint = [
                            routing._portal_center(f["segment_mm"]),
                            *path,
                            routing._portal_center(t["segment_mm"]),
                        ]
                        hint = list(routing._compact_path(hint))
                        safe, _, env = routing._route_is_safe(
                            hint,
                            width_mm=cw,
                            boundary=boundary,
                            obstacles=obstacles,
                            zones=rooms,
                            incident_refs=frozenset((fr, to)),
                        )
                        if not safe:
                            hint = []
                            continue
                        observation = {
                            "topology": "CORRIDOR_MEDIATED",
                            "profile_identity": obj.profile_identity,
                            "transport_mode": profile.transport_mode,
                            "portal_clear_width_m": routing._metres(pw),
                            "corridor_clear_width_m": routing._metres(cw),
                            "edge_alignment_verified": True,
                            "turn_count": routing._turn_count(hint),
                            "route_shape": "STRAIGHT"
                            if routing._turn_count(hint) == 0
                            else "ORTHOGONAL",
                        }
                        predicate = _evaluate_bound_requirement(obj, observation)
                        if predicate["status"] != "PASS":
                            hint = []
                            continue
                        external_result = (
                            routing._hashed(
                                {
                                    **routing._access_result_base(req),
                                    **observation,
                                    "portal_from": routing._portal_record(req, fr, f),
                                    "portal_to": routing._portal_record(req, to, t),
                                    "centerline": [routing._point(p) for p in hint],
                                    "clear_width_m": routing._metres(cw),
                                    "route_length_m": routing._metres(
                                        routing._path_length_mm(hint)
                                    ),
                                    "corridor_envelope": [
                                        polygon_to_dict(e.polygon_mm) for e in env
                                    ],
                                    "status": "PASS",
                                    "codes": [],
                                    "selection_basis": (
                                        "BODY_AWARE_CONTINUOUS_LEGAL_EDGE_OFFSETS_"
                                        "ORIGINAL_FULL_WIDTH_PREDICATES"
                                    ),
                                }
                            ),
                            tuple(e.polygon_mm for e in env),
                        )
                        break
                if external_result:
                    break
        if external_result:
            row, polys = external_result
            results.append(row)
            envelopes.extend(polys)
            continue
        row, polys = routing.route_access_requirement(
            req,
            relationships=relations,
            zones=rooms,
            boundary=boundary,
            obstacles=obstacles,
            entrances=entrances,
            route_node_budget=24,
            route_hint=hint,
        )
        results.append(row)
        envelopes.extend(polys)
    for row in results:
        if row.get("status") != "PASS":
            continue
        depth = 2000 if row["flow_kind"] == "PEOPLE" else 2500
        for side in ("from", "to"):
            code = row[side + "_ref"]
            if code not in rooms:
                continue
            p = row["portal_" + side]
            checks.append(
                {
                    "requirement_identity": row["requirement_identity"],
                    "room": code,
                    "portal": p,
                    "bbox_mm": portal_approach(p, rooms[code], depth),
                    "status": "BODY_FREE_APPROACH"
                    if clear(p, code, depth)
                    else "PORTAL_APPROACH_CONFLICT",
                }
            )
    return results, envelopes, checks


def functional_interior_routes(
    rooms: Mapping[str, PlacedRectangleV1],
    access: Sequence[Mapping[str, Any]],
    equipment: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
    *,
    use_reserved_waypoints: bool = False,
) -> list[dict[str, Any]]:
    ports: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {}
    for row in access:
        if row.get("status") == "PASS":
            for side in ("from", "to"):
                code = row[side + "_ref"]
                if code in rooms:
                    ports.setdefault(code, []).append((row, row["portal_" + side]))
    results = []
    for code, pp in sorted(ports.items()):
        if len(pp) < 2:
            continue
        q = rooms[code]
        bodies = [i["bbox_mm"] for i in equipment["items"] if i["room"] == code] + [
            c["bbox_mm"] for c in columns
        ]
        first = pp[0]
        for other in pp[1:]:
            width = 2000 if "PEOPLE" in (first[0]["flow_kind"], other[0]["flow_kind"]) else 2500
            start, end = _inward(first[1], q, width // 2), _inward(other[1], q, width // 2)
            path, nodes = rectilinear_path(
                start,
                end,
                q.bounds_mm,
                bodies,
                width,
                width,
                node_budget=4000,
                waypoints=[
                    (
                        (a["bbox_mm"][0] + a["bbox_mm"][2]) // 2,
                        (a["bbox_mm"][1] + a["bbox_mm"][3]) // 2,
                    )
                    for a in equipment["layouts"][code]["service_corridors"]
                ]
                if use_reserved_waypoints
                else (),
            )
            safe, reason, envelopes = (
                routing._route_is_safe(
                    path,
                    width_mm=width,
                    boundary=_ring(q.bounds_mm),
                    obstacles=[_ring(b) for b in bodies],
                    zones={},
                    incident_refs=frozenset(),
                )
                if path
                else (False, "BOUNDED_PATH_NOT_FOUND", ())
            )
            results.append(
                {
                    "room": code,
                    "from_access": first[0]["requirement_identity"],
                    "to_access": other[0]["requirement_identity"],
                    "status": "INTERIOR_FULL_WIDTH_PATH_VERIFIED"
                    if safe
                    else "BOUNDED_PATH_NOT_FOUND",
                    "failure_code": reason,
                    "clear_width_mm": width,
                    "centerline_mm": [list(p) for p in path] if safe else [],
                    "length_mm": routing._path_length_mm(path) if safe else None,
                    "envelope_bbox_mm": [list(e.bounds_mm) for e in envelopes] if safe else [],
                    "nodes_used": nodes,
                    "doorway_connector": "SEPARATE_LEGAL_PORTAL_THROAT; NOT_VEHICLE_KINEMATICS",
                    "full_material_handling_or_personnel_pass": False,
                }
            )
    return results


def storage_portal_interfaces(
    rooms: Mapping[str, PlacedRectangleV1],
    access: Sequence[Mapping[str, Any]],
    equipment: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
    *,
    use_reserved_waypoints: bool = False,
) -> list[dict[str, Any]]:
    """Connect each stateful pickup goal to its real cargo portal.

    This supplements stock withdrawal: reaching an isolated aisle would not
    prove an interface to the process chain. Door throat/vehicle turns remain
    separate from this original-predicate 2500mm interior witness.
    """
    results = []
    for stock in equipment["storage"]:
        layout = stock["layout"]
        code = layout["room"]
        q = rooms[code]
        start = tuple(layout["main_point_mm"])
        bodies = [i["bbox_mm"] for i in equipment["items"] if i["room"] == code] + [
            c["bbox_mm"] for c in columns
        ]
        for row in access:
            if row.get("status") != "PASS" or row["flow_kind"] == "PEOPLE":
                continue
            for side in ("from", "to"):
                if row[side + "_ref"] != code:
                    continue
                end = _inward(row["portal_" + side], q, 1250)
                path, nodes = rectilinear_path(
                    start,
                    end,
                    q.bounds_mm,
                    bodies,
                    2500,
                    2500,
                    node_budget=4000,
                    waypoints=[
                        (
                            (a["bbox_mm"][0] + a["bbox_mm"][2]) // 2,
                            (a["bbox_mm"][1] + a["bbox_mm"][3]) // 2,
                        )
                        for a in equipment["layouts"][code]["service_corridors"]
                    ]
                    if use_reserved_waypoints
                    else (),
                )
                safe, reason, env = (
                    routing._route_is_safe(
                        path,
                        width_mm=2500,
                        boundary=_ring(q.bounds_mm),
                        obstacles=[_ring(b) for b in bodies],
                        zones={},
                        incident_refs=frozenset(),
                    )
                    if path
                    else (False, "BOUNDED_PATH_NOT_FOUND", ())
                )
                results.append(
                    {
                        "room": code,
                        "requirement_identity": row["requirement_identity"],
                        "status": "STORAGE_AISLE_TO_REAL_PORTAL_VERIFIED"
                        if safe
                        else "BOUNDED_PATH_NOT_FOUND",
                        "centerline_mm": [list(p) for p in path] if safe else [],
                        "envelope_bbox_mm": [list(e.bounds_mm) for e in env] if safe else [],
                        "clear_width_mm": 2500,
                        "failure_code": reason,
                        "nodes_used": nodes,
                        "doorway_throat": (
                            "SEPARATE_ORIGINAL_PORTAL; VEHICLE_KINEMATICS_INPUT_REQUIRED"
                        ),
                    }
                )
    return results
