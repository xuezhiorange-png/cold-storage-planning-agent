"""Current failed doorway/union geometry -> bounded incident-room event targets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from cold_storage.modules.layout.domain.access_authority import resolve_access_profile
from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.dimensioning import canonical_hash


def passage_connection_feedback(
    candidate: Mapping[str, Any],
    precheck: Mapping[str, Any],
    requirements: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Only propose coordinates from CURRENT incident rooms and aisle edges.

    Every target must go back through the attachment search and original full
    validation. It is neither a room lock nor a layout/feasibility witness.
    """
    rooms = {q["zone_code"]: q["bbox_mm"] for q in candidate["rooms"]}
    layouts = candidate["equipment"]["layouts"]
    required = {q["identity"]: q for q in requirements}
    rows: dict[str, dict[str, Any]] = {}

    def add(role: str, p: Sequence[int], reason: str, evidence: Mapping[str, Any]) -> None:
        if role == "sorting_packaging_room" or role not in rooms or list(p) == rooms[role][:2]:
            return
        row = {
            "room_targets": {role: [list(p)]},
            "failed_room": role,
            "constraint": reason,
            "room_bbox_mm": rooms[role],
            "current_neighbor_evidence": dict(evidence),
            "source_room_geometry_hash": canonical_hash(rooms),
            "global_infeasibility_proven": False,
        }
        rows.setdefault(canonical_hash([role, p]), row)

    failed = {
        q["requirement_identity"]
        for q in precheck.get("original_predicates", [])
        if q["status"] != "PASS"
    }
    failed.update(
        q["requirement_identity"]
        for q in precheck.get("access_results", [])
        if q.get("status") not in ("PASS", "INPUT_REQUIRED_ACTUAL_VEHICLE_AND_LAND_SITE")
    )
    for identity in sorted(failed):
        req = required[identity]
        fr, to = req["from_ref"], req["to_ref"]
        profile = resolve_access_profile(req["profile_identity"])
        evidence = {
            "requirement_identity": identity,
            "profile_identity": profile.identity,
            "portal_minimum_mm": int(Decimal(profile.portal_clear_width_m) * 1000),
            "corridor_minimum_mm": int(Decimal(profile.corridor_clear_width_m) * 1000),
            "from_room": rooms.get(fr),
            "to_room": rooms.get(to),
        }
        if fr == "main_entrance":
            opening = (
                next(
                    q
                    for q in candidate["original_building"]["openings"]
                    if q["kind"] == "personnel"
                )
                if any(
                    q.get("kind") == "personnel" for q in candidate["original_building"]["openings"]
                )
                else candidate["original_building"]["openings"][1]
            )
            a, b = opening["segment_mm"]
            r = rooms[to]
            w = r[2] - r[0]
            ex, ey = (a[0] + b[0]) // 2, (a[1] + b[1]) // 2
            for x in (ex - w // 2, ex + 2500, ex - w - 2500):
                add(to, (x, ey + 2500), "ACTUAL_ENTRANCE_AND_FAILED_PERSONNEL_CONNECTION", evidence)
            continue
        if fr not in rooms or to not in rooms:
            continue
        a, b = rooms[fr], rooms[to]
        vertical = a[2] == b[0] or b[2] == a[0]
        tangent = 1 if vertical else 0
        # Align an actual service corridor intersection with the other room's
        # legal shared frontage. Bodies, columns and original MUST decide later.
        for role, other in ((to, fr), (fr, to)):
            if role == "sorting_packaging_room":
                continue
            moving = rooms[role]
            for lane in layouts[role]["service_corridors"][:4]:
                for peer in layouts[other]["service_corridors"][:4]:
                    la, lb = lane["bbox_mm"], peer["bbox_mm"]
                    for delta in (lb[tangent] - la[tangent], lb[tangent + 2] - la[tangent + 2]):
                        if abs(delta) > 16000 or delta == 0:
                            continue
                        p = moving[:2].copy()
                        p[tangent] += delta
                        add(
                            role,
                            p,
                            "FAILED_P1_PORTAL_ACTUAL_AISLE_ALIGNMENT",
                            {
                                **evidence,
                                "moving_aisle": la,
                                "neighbor_aisle": lb,
                                "tangent_shift_mm": delta,
                            },
                        )
    for pocket in precheck.get("uncovered_pockets", []):
        b = pocket["bbox_mm"]
        for role, a in sorted(rooms.items()):
            if not positive_intersection([b[0] - 1, b[1] - 1, b[2] + 1, b[3] + 1], a):
                continue
            if a[1] == b[3]:
                add(role, (a[0], b[1]), "ACTUAL_UNION_POCKET_CONNECTION", pocket)
            if a[3] == b[1]:
                add(role, (a[0], b[3] - (a[3] - a[1])), "ACTUAL_UNION_POCKET_CONNECTION", pocket)
            if a[0] == b[2]:
                add(role, (b[0], a[1]), "ACTUAL_UNION_POCKET_CONNECTION", pocket)
            if a[2] == b[0]:
                add(role, (b[2] - (a[2] - a[0]), a[1]), "ACTUAL_UNION_POCKET_CONNECTION", pocket)
    return list(rows.values())
