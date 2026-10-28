"""Continuous same-body yaw/translation adapter for R9 rotated waiting poses.

Original transfer, Portal, body, aisle and door validators remain unchanged.
Yaw uses a conservative full-diagonal square, not sampled body orientations.
"""

import copy
import math
from typing import Any

from cold_storage.modules.layout.domain.changing_operation_motion import (
    PASS,
    center,
    check_volumes,
    transfer,
)
from cold_storage.modules.layout.domain.changing_room_motion import (
    prism,
    standing_person,
    swept_segments,
)
from cold_storage.modules.layout.domain.functional_room_fit import covered, rectangle
from cold_storage.modules.layout.domain.practical_changing_layout import H5Hypothesis


def _shape(person: dict[str, Any]) -> tuple[int, int]:
    x, y, r, t = person["bounds_mm"]
    return r - x, t - y


def relayout_transfer(
    current: dict[str, Any],
    target: dict[str, Any],
    g: dict[str, Any],
    s: dict[str, Any],
    *,
    exited: set[str],
) -> dict[str, Any]:
    p = H5Hypothesis(**g["parameters"])
    source = current[target["id"]]
    normal, rotated = (p.person_width_mm, p.person_depth_mm), (p.person_depth_mm, p.person_width_mm)
    if _shape(source) == normal and _shape(target) == normal:
        return transfer(current, target, g, s, seat_allowance_mm=0, exited=exited)
    if (_shape(source), _shape(target)) not in {(rotated, normal), (normal, rotated)}:
        raise ValueError("EXPLICIT_SAME_BODY_NORMAL_ROTATED_TRANSITION_REQUIRED")
    key = target["id"]
    expected = {
        a["person_id"] for a in g["inventory"]["person_assignments"] if a["shift"] == s["shift"]
    }
    if set(current) & exited or set(current) | exited != expected:
        raise ValueError("COMPLETE_53_PERSON_ROSTER_REQUIRED")
    for obj in (source, target):
        if obj["volumes_mm"] != [prism(obj["bounds_mm"], 0, p.standing_height_mm)]:
            raise ValueError("FULL_HEIGHT_ACTUAL_WAITING_BODY_REQUIRED")
    before = copy.deepcopy(current)
    work = copy.deepcopy(current)
    waiting = source if _shape(source) == rotated else target
    wx, wy = center(waiting)
    branch = s["branch_centerline_mm"]
    stage_y = s["branch_y"] if branch[0][0] <= wx <= branch[1][0] else s["main_y"]
    stage = [wx, stage_y]

    def body(w: int, d: int) -> dict[str, Any]:
        return standing_person(
            key,
            [wx - w // 2, stage_y - d // 2, wx + w - w // 2, stage_y + d - d // 2],
            p.standing_height_mm,
            "AISLE_YAW_STAGING",
        )

    others = [v for k, v in work.items() if k != key]
    bodies = g["inventory"]["cabinet_units"]
    # Every intermediate angle lies within this closed square about the same center.
    radius = (math.isqrt(p.person_width_mm**2 + p.person_depth_mm**2) + 2) // 2
    square = [wx - radius, stage_y - radius, wx + radius, stage_y + radius]
    volume = prism(square, 0, p.standing_height_mm)
    errors = check_volumes([volume], others, bodies, g["model"]["clear"], p.clear_height_mm)
    if not covered(rectangle(square), [rectangle(a) for a in s["aisles"]]):
        errors.append(dict(code="FULL_YAW_SWEEP_OUTSIDE_RESERVED_AISLE", volume_mm=volume))
    turn = dict(
        operation="YAW_90_IN_EXISTING_AISLE",
        status=PASS if not errors else "CONFIGURATION_NOT_FIT",
        conflicts=errors,
        swept_volumes_mm=[volume],
        center_mm=stage,
        bounding_square_side_mm=radius * 2,
        original_body_mm=list(normal),
        rotated_body_mm=list(rotated),
        motion_model="CONSERVATIVE_CONTINUOUS_FULL_DIAGONAL_SQUARE; NOT_ERGONOMIC_APPROVAL",
        people_before=copy.deepcopy(list(work.values())),
        length_mm=0,
    )
    points = [[wx, wy], stage] if _shape(source) == rotated else [stage, [wx, wy]]
    sweep = swept_segments(points, *rotated, p.standing_height_mm)
    errors = check_volumes(sweep, others, bodies, g["model"]["clear"], p.clear_height_mm)
    # This is the explicit endpoint approach; other translations use the original network.
    approach = dict(
        operation="ROTATED_WAITING_APPROACH",
        status=PASS if not errors else "CONFIGURATION_NOT_FIT",
        conflicts=errors,
        points_mm=points,
        swept_volumes_mm=sweep,
        people_before=copy.deepcopy(list(work.values())),
        length_mm=abs(wy - stage_y),
        fixed_body_mm=list(rotated),
        doors="CLOSED",
    )
    legs: list[dict[str, Any]] = []

    def add_pose_step(proof: dict[str, Any], destination: dict[str, Any]) -> bool:
        proof = dict(
            proof,
            source=copy.deepcopy(work[key]),
            target=copy.deepcopy(destination),
            people_before=copy.deepcopy(list(work.values())),
        )
        legs.append(proof)
        if proof["status"] == PASS:
            work[key] = copy.deepcopy(destination)
            return True
        return False

    proceed = True
    if _shape(source) == rotated:
        proceed = add_pose_step(approach, body(*rotated))
        if proceed:
            proceed = add_pose_step(turn, body(*normal))
    if proceed:
        leg = transfer(
            work,
            target if _shape(target) == normal else body(*normal),
            g,
            s,
            seat_allowance_mm=0,
            exited=exited,
        )
        legs.append(dict(leg, operation="ORIGINAL_AISLE_TRANSFER"))
        proceed = leg["status"] == PASS
    if proceed and _shape(target) == rotated:
        proceed = add_pose_step(turn, body(*rotated))
        if proceed:
            add_pose_step(approach, target)
    failures = [dict(e, leg=v["operation"]) for v in legs for e in v["conflicts"]]
    okay = not failures and len(legs) == 3
    if okay:
        current[key] = copy.deepcopy(target)
    return dict(
        person_id=key,
        status=PASS if okay else "CONFIGURATION_NOT_FIT",
        conflicts=failures,
        source=copy.deepcopy(source),
        target=copy.deepcopy(target),
        people_before=list(before.values()),
        legs=legs,
        length_mm=sum(v["length_mm"] for v in legs),
        yaw_turn_count=1,
        swept_volumes_mm=[b for v in legs for b in v.get("swept_volumes_mm", [])],
        accounted_people=len(current) + len(exited),
        doors="CLOSED",
    )
