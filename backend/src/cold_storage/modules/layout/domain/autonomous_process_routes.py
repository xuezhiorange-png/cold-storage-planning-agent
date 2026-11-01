"""Bounded equipment-aware interior paths using the original access predicate.

These supplement, and never replace, the P1 inter-room access results. Portal
throats, full stock retrieval and multi-person operation remain separate reviews.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from cold_storage.modules.layout.domain.access_routing import _find_route
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1, PolygonMM


def _ring(box: Sequence[int]) -> PolygonMM:
    a, b, c, d = box
    return ((a, b), (c, b), (c, d), (a, d))


def _inward(portal: Mapping[str, Any], room: PlacedRectangleV1, offset: int) -> tuple[int, int]:
    s = portal["segment"]
    x = round((float(s["start"]["x"]) + float(s["end"]["x"])) * 500)
    y = round((float(s["start"]["y"]) + float(s["end"]["y"])) * 500)
    a, b, c, d = room.bounds_mm
    return (
        (x + offset, y)
        if x == a
        else (x - offset, y)
        if x == c
        else ((x, y + offset) if y == b else (x, y - offset))
    )


def route_equipment_aware_interiors(
    rooms: Mapping[str, PlacedRectangleV1],
    access: Sequence[Mapping[str, Any]],
    equipment: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Connect pairs of independently generated room portals, without moving them.

    Fixed 24-node graph budget per path. A failed template is not an engineering
    infeasibility assertion. Half-width inward endpoints deliberately exclude the
    changing-width doorway connector from this full-width aisle certificate.
    """
    by_room: dict[str, list[tuple[str, Mapping[str, Any], str]]] = {}
    for row in access:
        if row.get("status") != "PASS":
            continue
        for side in ("from", "to"):
            code = str(row.get(side + "_ref"))
            portal = row.get("portal_" + side)
            if code in rooms and portal:
                by_room.setdefault(code, []).append(
                    (str(row["requirement_identity"]), portal, str(row["flow_kind"]))
                )
    results = []
    for code, ports in sorted(by_room.items()):
        if len(ports) < 2:
            continue
        q = rooms[code]
        obstacles = [_ring(x["bbox_mm"]) for x in columns]
        obstacles += [_ring(x["bbox_mm"]) for x in equipment["items"] if x["room"] == code]
        first = ports[0]
        for other in ports[1:]:
            width = 2000 if first[2] == other[2] == "PERSONNEL" else 2500
            start, end = _inward(first[1], q, width // 2), _inward(other[1], q, width // 2)
            if start == end:
                continue
            path, reason, envelopes = _find_route(
                start,
                end,
                width_mm=width,
                straight_only=False,
                boundary=_ring(q.bounds_mm),
                obstacles=obstacles,
                zones={},
                incident_refs=frozenset(),
                node_budget=24,
            )
            centerline = [list(p) for p in path] if path else []
            length = sum(
                abs(a[0] - b[0]) + abs(a[1] - b[1])
                for a, b in zip(centerline, centerline[1:], strict=False)
            )
            results.append(
                {
                    "room": code,
                    "from_access": first[0],
                    "to_access": other[0],
                    "status": "INTERIOR_FULL_WIDTH_PATH_VERIFIED"
                    if path
                    else "BOUNDED_PATH_NOT_FOUND",
                    "failure_code": reason or None,
                    "clear_width_mm": width,
                    "centerline_mm": centerline,
                    "length_mm": length if path else None,
                    "envelope_bbox_mm": [list(x.bounds_mm) for x in envelopes],
                    "doorway_connector": "NOT_EVALUATED_VARIABLE_WIDTH_THROAT",
                    "full_material_handling_or_personnel_pass": False,
                    "node_budget": 24,
                }
            )
    return results
