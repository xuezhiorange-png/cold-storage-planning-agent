"""R6 continuous body/seat envelopes on the existing H5 aisle network, in mm.

Finite deterministic path checks, never a Native solve or ergonomic approval.
"""

import copy
from typing import Any

from cold_storage.modules.layout.domain.changing_room_motion import (
    network_path,
    overlap3,
    prism,
    standing_person,
    swept_segments,
)
from cold_storage.modules.layout.domain.functional_room_fit import covered, rectangle
from cold_storage.modules.layout.domain.practical_changing_layout import H5Hypothesis

PASS = "VERIFIED_UNDER_HYPOTHESES"


def center(person: dict[str, Any]) -> list[int]:
    b = person["bounds_mm"]
    return [(b[0] + b[2]) // 2, (b[1] + b[3]) // 2]


def physical(person: dict[str, Any], p: H5Hypothesis) -> dict[str, Any]:
    """Separate a changing activity envelope from the person's transport body."""
    q = copy.deepcopy(person)
    if q["pose"] == "CHANGING_OPERATION_ENVELOPE":
        x, y = center(q)
        q = standing_person(
            q["id"],
            [
                x - p.person_width_mm // 2,
                y - p.person_depth_mm // 2,
                x + p.person_width_mm - p.person_width_mm // 2,
                y + p.person_depth_mm - p.person_depth_mm // 2,
            ],
            p.standing_height_mm,
            "WAITING_AT_CHANGING_ZONE",
        )
    return q


def check_volumes(
    boxes: list[list[int]],
    others: list[dict[str, Any]],
    bodies: list[dict[str, Any]],
    clear: list[int],
    height: int,
) -> list[dict[str, Any]]:
    issues = []
    for i, box in enumerate(boxes):
        if (
            box[2] < 0
            or box[5] > height
            or not covered((box[0], box[1], box[3], box[4]), [rectangle(clear)])
        ):
            issues.append(dict(code="SWEPT_BODY_OUTSIDE_CLEAR_ROOM", segment=i, volume_mm=box))
        for o in [*others, *bodies]:
            if any(overlap3(box, v) for v in o["volumes_mm"]):
                issues.append(
                    dict(code="SWEPT_BODY_COLLISION", component=o["id"], segment=i, volume_mm=box)
                )
    return issues


def seat_pose(
    person: dict[str, Any],
    bench: dict[str, Any],
    others: list[dict[str, Any]],
    bodies: list[dict[str, Any]],
    clear: list[int],
    p: H5Hypothesis,
    allowance_mm: int,
) -> dict[str, Any]:
    """Conservative union of sit/rise upper-body and forward-leg envelopes.

    Bench contact is allowed only at its top support plane; the full bench stays in
    collision checks. A reviewed articulation model is still required in real use.
    """
    x, y, r, t = person["bounds_mm"]
    by = bench["bounds_mm"][3]
    if person.get("bench_id") != bench["id"] or person["pose"] != "SEATED":
        raise ValueError("ACTUAL_SEATED_PERSON_AND_BENCH_REQUIRED")
    stand = standing_person(
        person["id"], [x, by, r, by + p.person_depth_mm], p.standing_height_mm, "SEAT_APPROACH"
    )
    boxes = [
        prism(
            [x - allowance_mm, y, r + allowance_mm, by + p.person_depth_mm + allowance_mm],
            bench["height_mm"],
            p.standing_height_mm,
        ),
        prism([x, by, r, by + p.person_depth_mm], 0, bench["height_mm"]),
    ]
    errors = check_volumes(boxes, others, bodies, clear, p.clear_height_mm)
    return dict(
        status=PASS if not errors else "CONFIGURATION_NOT_FIT",
        conflicts=errors,
        swept_volumes_mm=boxes,
        standing=stand,
        seat_id=bench["id"],
        posture_model="CONSERVATIVE_UPPER_BODY_UNION_AND_FRONT_LEGS",
        actual_articulation="INPUT_REQUIRED",
    )


def transfer(
    current: dict[str, dict[str, Any]],
    target: dict[str, Any],
    result: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    seat_allowance_mm: int,
    exited: set[str] | None = None,
) -> dict[str, Any]:
    """One mover; all other currently present people remain in place. No teleport."""
    p = H5Hypothesis(**result["parameters"])
    key = target["id"]
    source = current[key]
    outsiders = exited or set()
    expected = {
        a["person_id"]
        for a in result["inventory"]["person_assignments"]
        if a["shift"] == snapshot["shift"]
    }
    if set(current) & outsiders or set(current) | outsiders != expected:
        raise ValueError("COMPLETE_53_PERSON_ROSTER_REQUIRED")
    others = [v for k, v in current.items() if k != key]
    bodies = [*result["inventory"]["cabinet_units"], *result["model"]["benches"]]
    benches = {b["id"]: b for b in result["model"]["benches"]}
    clear = result["model"]["clear"]
    pose_checks = []
    start, end = physical(source, p), physical(target, p)
    for obj, which in [(start, "RISE"), (end, "SIT")]:
        if obj["pose"] == "SEATED":
            proof = seat_pose(
                obj, benches[obj["bench_id"]], others, bodies, clear, p, seat_allowance_mm
            )
            proof["action"] = which
            pose_checks.append(proof)
            if which == "RISE":
                start = proof["standing"]
            else:
                end = proof["standing"]
    for body in (start, end):
        box = body["bounds_mm"]
        if box[2] - box[0] != p.person_width_mm or box[3] - box[1] != p.person_depth_mm:
            raise ValueError("TRANSPORT_BODY_DIMENSIONS_CHANGED")
    a, b = center(start), center(end)
    sy = snapshot["branch_y"] if start["role"] == "FRONT_OPERATOR" else snapshot["main_y"]
    ey = snapshot["branch_y"] if end["role"] == "FRONT_OPERATOR" else snapshot["main_y"]
    connectors = [[a, [a[0], sy]], [[b[0], ey], b]]
    path = network_path(a, b, [*snapshot["network_lines"], *connectors])
    conflicts = [c for v in pose_checks for c in v["conflicts"]]
    if path is None:
        conflicts.append(dict(code="NO_EXISTING_AISLE_PATH"))
    sweep = (
        swept_segments(path, p.person_width_mm, p.person_depth_mm, p.standing_height_mm)
        if path and len(path) > 1
        else []
    )
    # Endpoint volumes are checked even when the center does not move.
    conflicts += check_volumes(
        [*sweep, *start["volumes_mm"], *end["volumes_mm"]], others, bodies, clear, p.clear_height_mm
    )
    allowed = [
        *snapshot["aisles"],
        *[
            list((v[0], v[1], v[3], v[4]))
            for line in connectors
            if line[0] != line[1]
            for v in swept_segments(
                line, p.person_width_mm, p.person_depth_mm, p.standing_height_mm
            )
        ],
    ]
    for v in sweep:
        if not covered((v[0], v[1], v[3], v[4]), [rectangle(q) for q in allowed]):
            conflicts.append(dict(code="OUTSIDE_EXISTING_AISLE_OR_ENDPOINT_APPROACH", volume_mm=v))
    distance = sum(
        abs(a[0] - b[0]) + abs(a[1] - b[1])
        for a, b in zip(path or [], (path or [])[1:], strict=False)
    )
    proof = dict(
        person_id=key,
        status=PASS if not conflicts else "CONFIGURATION_NOT_FIT",
        conflicts=conflicts,
        points_mm=path or [],
        swept_volumes_mm=sweep,
        pose_checks=pose_checks,
        length_mm=distance,
        people_before=copy.deepcopy(list(current.values())),
        source=copy.deepcopy(source),
        target=copy.deepcopy(target),
        accounted_people=len(current) + len(outsiders),
        inside_people=len(current),
        doors="CLOSED",
        hypothetical_room_doors="OPEN_NON_INTRUDING",
    )
    if not conflicts:
        current[key] = copy.deepcopy(target)
    return proof


def portal_crossing(
    person: dict[str, Any],
    portal: dict[str, Any],
    result: dict[str, Any],
    others: list[dict[str, Any]],
    *,
    entering: bool,
) -> dict[str, Any]:
    """Local actual Portal crossing only; archived external Access is not re-solved."""
    p = H5Hypothesis(**result["parameters"])
    a, b = portal["segment_mm"]
    vertical = a[0] == b[0]
    if portal["clear_width_mm"] != 1500 or portal not in result["room"]["portals"]:
        raise ValueError("ORIGINAL_H5_PORTAL_REQUIRED")
    w, d = p.person_width_mm, p.person_depth_mm
    if vertical:
        y = (a[1] + b[1]) // 2
        inner = [a[0] - p.finish_mm - w // 2, y]
        outer = [a[0] + w - w // 2, y]
        band = [inner[0] - w, min(a[1], b[1]), outer[0] + w, max(a[1], b[1])]
    else:
        x = (a[0] + b[0]) // 2
        inner = [x, p.finish_mm + d // 2]
        outer = [x, -d + d // 2]
        band = [min(a[0], b[0]), outer[1] - d, max(a[0], b[0]), inner[1] + d]
    points = [outer, inner] if entering else [inner, outer]
    boxes = swept_segments(points, w, d, p.standing_height_mm)
    bodies = [*result["inventory"]["cabinet_units"], *result["model"]["benches"]]
    errors = []
    for box in boxes:
        if not covered((box[0], box[1], box[3], box[4]), [tuple(band)]):
            errors.append(dict(code="BODY_DOES_NOT_FIT_ORIGINAL_PORTAL", volume_mm=box))
        for obj in [*others, *bodies]:
            if any(overlap3(box, v) for v in obj["volumes_mm"]):
                errors.append(
                    dict(code="PORTAL_CROSSING_COLLISION", component=obj["id"], volume_mm=box)
                )
    if p.room_door_intrusion_mm or p.standing_height_mm > p.clear_height_mm:
        errors.append(dict(code="PORTAL_DOOR_OR_HEIGHT_UNRESOLVED"))
    interior = standing_person(
        person["id"],
        [inner[0] - w // 2, inner[1] - d // 2, inner[0] + w - w // 2, inner[1] + d - d // 2],
        p.standing_height_mm,
        "PORTAL_TRANSIT",
    )
    return dict(
        status=PASS if not errors else "CONFIGURATION_NOT_FIT",
        conflicts=errors,
        points_mm=points,
        swept_volumes_mm=boxes,
        person_id=person["id"],
        interior_person=interior,
        portal_id=portal["id"],
        original_segment_mm=portal["segment_mm"],
        length_mm=abs(inner[0] - outer[0]) + abs(inner[1] - outer[1]),
        external_continuation="ARCHIVED_ACCESS_REFERENCE_ONLY_NOT_REVALIDATED",
        actual_door_motion="INPUT_REQUIRED",
    )
