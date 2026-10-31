"""Certified distances for the existing conditional 90-degree sweep model.

The original collision predicate is unchanged. Its planar model is a closed
quarter disk Minkowski-added to a thickness square [-p,p]^2. Moving that square
to the target gives an expanded target rectangle. Distances to the two radial
segments and circular arc give the exact model distance. Integer square-root
intervals enclose it to 0.001mm; no sampled arc is used as a certificate.
This is not a measured hardware or human clearance.
"""

import math
from typing import Any

from cold_storage.modules.layout.domain.changing_room_motion import door_hits_box
from cold_storage.modules.layout.domain.reverse_sizing_margins import rectangle_gap
from cold_storage.modules.layout.domain.ten_door_locker_sweeps import sweep_box, validate_door_event

SCALE = 1000


def _root_interval(squared: int) -> tuple[int, int]:
    root = math.isqrt(squared)
    return root, root if root * root == squared else root + 1


def _axis_gap(low: int, high: int, other_low: int, other_high: int) -> int:
    return max(low - other_high, other_low - high, 0)


def certified_sweep_distance(door: dict[str, Any], volume: list[int]) -> dict[str, Any]:
    if (
        door["kind"] != "OUTWARD_HINGED_90"
        or door["angle_degrees"] != 90
        or door["direction"] not in ([1, 1], [-1, 1], [1, -1], [-1, -1])
        or len(volume) != 6
        or not all(
            type(v) is int
            for v in [
                *volume,
                *door["hinge_mm"],
                *door["z_interval_mm"],
                door["radius_mm"],
                door["thickness_mm"],
            ]
        )
        or any(volume[i] >= volume[i + 3] for i in range(3))
        or min(door["radius_mm"], door["thickness_mm"]) <= 0
    ):
        raise ValueError("EXPLICIT_SUPPORTED_INTEGER_90_DEGREE_CONDITIONAL_GEOMETRY_REQUIRED")
    hx, hy = door["hinge_mm"]
    ux, vy = door["direction"]
    pad, radius = door["thickness_mm"], door["radius_mm"]
    xx = sorted([(volume[0] - hx) * ux, (volume[3] - hx) * ux])
    yy = sorted([(volume[1] - hy) * vy, (volume[4] - hy) * vy])
    x0, x1, y0, y1 = xx[0] - pad, xx[1] + pad, yy[0] - pad, yy[1] + pad
    certificates: list[dict[str, Any]] = []
    for label, ax, ay in (
        ("VERTICAL_RADIUS", _axis_gap(x0, x1, 0, 0), _axis_gap(y0, y1, 0, radius)),
        ("HORIZONTAL_RADIUS", _axis_gap(x0, x1, 0, radius), _axis_gap(y0, y1, 0, 0)),
    ):
        square = ax * ax + ay * ay
        lo, hi = _root_interval(square * SCALE * SCALE)
        certificates.append(dict(feature=label, squared_mm2=square, lower_um=lo, upper_um=hi))
    if x1 >= 0 and y1 >= 0:
        square = max(0, x0) ** 2 + max(0, y0) ** 2
        lo, hi = _root_interval(square * SCALE * SCALE)
        certificates.append(
            dict(
                feature="CIRCULAR_ARC_OR_INTERIOR",
                squared_mm2=square,
                radius_mm=radius,
                lower_um=max(0, lo - radius * SCALE),
                upper_um=max(0, hi - radius * SCALE),
            )
        )
    planar_lo = min(c["lower_um"] for c in certificates)
    planar_hi = min(c["upper_um"] for c in certificates)
    z0, z1 = door["z_interval_mm"]
    z_gap = _axis_gap(volume[2], volume[5], z0, z1)
    lower, _ = _root_interval(planar_lo**2 + (z_gap * SCALE) ** 2)
    _, upper = _root_interval(planar_hi**2 + (z_gap * SCALE) ** 2)
    bbox = sweep_box(door)
    return dict(
        collision_original_predicate=door_hits_box(door, volume),
        bounding_box_lower_bound_mm=max(
            0,
            rectangle_gap(
                [bbox[0], bbox[1], bbox[3], bbox[4]], [volume[0], volume[1], volume[3], volume[4]]
            ),
        ),
        model_distance_lower_um=lower,
        model_distance_upper_um=upper,
        interval_unit="0.001 mm",
        exact_interval=lower == upper,
        expanded_target_in_hinge_axes_mm=[x0, y0, x1, y1],
        z_separation_mm=z_gap,
        feature_certificates=certificates,
        formula=(
            "distance(Q_radius + [-thickness,thickness]^2, target) = "
            "distance(Q_radius, target + [-thickness,thickness]^2); "
            "combine z gap by Pythagoras"
        ),
        mathematical_scope="EXACT_DISTANCE_TO_ORIGINAL_CONSERVATIVE_THICKNESS_MODEL_ONLY",
        actual_hardware_and_human_clearance="INPUT_REQUIRED",
        sensitivity_50mm_met=lower >= 50 * SCALE,
        normative_minimum_claim=False,
    )


def trace_archived_minimum(case: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    minimum = profile["doors"]["minimum_door_clearance_lower_bound"]
    if minimum is None:
        raise ValueError("ARCHIVED_COMPLETE_DOOR_WITNESS_REQUIRED")
    flow = next(f for f in case["closed_door_flows"] if f["shift"] == minimum["shift"])
    event = next(e for e in flow["events"] if e["index"] == minimum["event"])
    snapshot = next(s for s in case["geometry"]["snapshots"] if s["id"] == event["batch"])
    person = next(o for o in event["proof"]["people_before"] if o["id"] == minimum["object"])
    door = next(d for d in profile["doors"]["registry"] if d["id"] == minimum["door"])
    proof = min(
        (certified_sweep_distance(door, v) for v in person["volumes_mm"]),
        key=lambda d: d["model_distance_lower_um"],
    )
    if proof["bounding_box_lower_bound_mm"] != minimum["extra_mm"]:
        raise ValueError("ARCHIVED_CLEARANCE_TRACE_MISMATCH")
    action = next(a for a in snapshot["actions"] if a["person_id"] == person["id"])
    col = next(
        c
        for c in case["geometry"]["inventory"]["vertical_columns"]
        if c["id"] == action["column_id"]
    )
    event_validation = validate_door_event(
        case["geometry"],
        snapshot,
        event["proof"]["people_before"],
        profile["doors"]["registry"],
        expected_people_count=event["inside_people"],
    )
    if event_validation["minimum_clearance_lower_bound"] != {
        k: v for k, v in minimum.items() if k not in {"shift", "event"}
    }:
        raise ValueError("ARCHIVED_EVENT_RECOMPUTED_MINIMUM_MISMATCH")
    return dict(
        case_id=case["id"],
        hinges=profile["hypothesis"]["hinges"],
        shift=flow["shift"],
        event=event["index"],
        operation=event["operation"],
        batch=event["batch"],
        tier=next(
            c["tier"]
            for c in case["geometry"]["inventory"]["compartments"]
            if c["id"] == door["compartment_id"]
        ),
        door=door,
        person=person,
        active_people=event["active_people"],
        people_count=event["inside_people"],
        simultaneous_doors=[
            d
            for d in profile["doors"]["registry"]
            if d["compartment_id"] in {a["compartment_id"] for a in snapshot["actions"]}
        ],
        reserved_aisles_mm=snapshot["aisles"],
        standing_change_envelope_mm=[600, 900, 1800],
        standing_change_phase="DOORS_CLOSED; OPEN_EVENT_BODY_IS_TRANSPORT_450x650x1800",
        cabinet_front_y_mm=col["bounds_mm"][3],
        archived_lower_bound_mm=minimum["extra_mm"],
        distance=proof,
        original_event_revalidation=event_validation,
        inherited_status_unchanged=True,
        actual_status="INPUT_REQUIRED",
    )
