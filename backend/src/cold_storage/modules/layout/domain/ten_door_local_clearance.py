"""R15 R4 finite local adjustments; original motion and door validators retained.

Only unapproved operating positions/branch organization vary. Cabinet bodies,
room, people envelopes, aisle width, Portal and assignments are immutable.
No coordinates from a successful motion witness are edited into a new proof.
"""

import copy
from typing import Any

from cold_storage.modules.layout.domain.cabinet_front_schedule import FrontParameters, _schedule
from cold_storage.modules.layout.domain.h5_space_relayout import waiting_clearances
from cold_storage.modules.layout.domain.practical_changing_layout import H5Hypothesis, validate_use
from cold_storage.modules.layout.domain.reverse_sizing_geometry import (
    activity_parameters,
    sizing_snapshot,
)
from cold_storage.modules.layout.domain.standing_changing_operation import activity_proof
from cold_storage.modules.layout.domain.ten_door_locker_model import complete_inventory_conflicts
from cold_storage.modules.layout.domain.ten_door_sweep_clearance import certified_sweep_distance

VERSION = "h5-ten-door-local-clearance-r15-r4@1.0.0"
MAX_CANDIDATES = 6


def finite_adjustments() -> list[dict[str, Any]]:
    """Declared before calculation, including control and section-only negative."""
    return [
        dict(id="R4-00", operator_delta_mm=0, branch_delta_mm=0, north="RETAIN", scope="CONTROL"),
        dict(
            id="R4-01",
            operator_delta_mm=35,
            branch_delta_mm=0,
            north="RETAIN",
            scope="SECTION_ONLY",
        ),
        dict(
            id="R4-02", operator_delta_mm=35, branch_delta_mm=35, north="RETAIN", scope="FULL_FLOW"
        ),
        dict(
            id="R4-03", operator_delta_mm=50, branch_delta_mm=50, north="RETAIN", scope="FULL_FLOW"
        ),
        dict(
            id="R4-04",
            operator_delta_mm=50,
            branch_delta_mm=50,
            north="FOLLOW_BRANCH",
            scope="FULL_FLOW",
        ),
        dict(
            id="R4-05",
            operator_delta_mm=80,
            branch_delta_mm=80,
            north="FOLLOW_BRANCH",
            scope="FULL_FLOW",
        ),
    ]


def require_frozen_basis(g: dict[str, Any]) -> None:
    p, c, cfg = g["parameters"], g["conditions"], g["front_parameters"]
    if (
        g["room"]["local_bounds_mm"] != [0, 0, 26331, 3850]
        or (p["person_width_mm"], p["person_depth_mm"], p["standing_height_mm"]) != (450, 650, 1800)
        or (p["aisle_mm"], p["person_gap_mm"], g["spatial_padding_mm"]) != (1300, 200, 100)
        or (cfg["activity_width_mm"], cfg["activity_depth_mm"], cfg["requested_concurrency"])
        != (600, 900, 4)
        or (p["operator_standoff_mm"], p["finish_mm"], c["installation_gap_mm"]) != (480, 30, 40)
        or g["demand"]["shift_users"] != [53, 53]
        or g["demand"]["simultaneous_room_users"] != 53
        or len(g["model"]["homes"]) != 53
        or g["model"]["benches"]
        or g["model"]["changing_zone"] is not None
        or complete_inventory_conflicts(g["inventory"], g["demand"])
        or len(g["inventory"]["cabinet_units"]) != 11
        or any(u["dimensions_mm"] != [850, 390, 1800] for u in g["inventory"]["cabinet_units"])
        or len(g["room"]["portals"]) != 2
        or any(p["clear_width_mm"] != 1500 for p in g["room"]["portals"])
    ):
        raise ValueError("FROZEN_R15_03_3850_53_11_BODY_AISLE_BASIS_REQUIRED")


def local_section(g: dict[str, Any], choice: dict[str, Any]) -> dict[str, Any]:
    require_frozen_basis(g)
    if choice not in finite_adjustments():
        raise ValueError("DECLARED_R4_LOCAL_CANDIDATE_REQUIRED")
    s = g["snapshots"][0]
    person = next(p for p in s["people"] if p["id"] == "S1-P001")
    cabinet = next(u for u in g["inventory"]["cabinet_units"] if u["id"] == "U01")
    activity = next(
        a for a in s["front_activity_evaluation"]["activity_volumes"] if a["id"] == person["id"]
    )
    north = [h for h in g["model"]["homes"] if h["region"].startswith("NORTH")]
    east = [h for h in g["model"]["homes"] if h["region"] == "EAST_NORTH_NORMAL"]
    o, b = choice["operator_delta_mm"], choice["branch_delta_mm"]
    half = g["parameters"]["aisle_mm"] // 2
    bottom, top = s["branch_y"] - half + b, s["branch_y"] + half + b
    n = (
        max(
            0,
            max(top + 100, max(h["bounds_mm"][3] for h in east) + 200)
            - min(h["bounds_mm"][1] for h in north),
        )
        if choice["north"] == "FOLLOW_BRANCH"
        else 0
    )
    body = [v + (o if i in (1, 3) else 0) for i, v in enumerate(person["bounds_mm"])]
    act = [v + (o if i in (1, 3) else 0) for i, v in enumerate(activity["bounds_mm"])]
    row_bottom = min(h["bounds_mm"][1] for h in north) + n
    row_top = max(h["bounds_mm"][3] for h in north) + n
    gaps = dict(
        conditional_own_door_mm=body[1] - (cabinet["bounds_mm"][3] + 400 + 15),
        operator_to_branch_mm=bottom - body[3],
        standing_activity_to_branch_mm=bottom - act[3],
        north_home_to_branch_mm=row_bottom - top,
        north_home_to_finished_wall_mm=g["model"]["clear"][3] - row_top,
    )
    return dict(
        scope="NECESSARY_LOCAL_SECTION_ONLY_NOT_FULL_FLOW_OR_ACTUAL_APPROVAL",
        person_id=person["id"],
        door_id="U01-L-T1-DOOR",
        source_event="S1/E110/OPEN_FOR_RETRIEVE",
        body_mm=body,
        activity_mm=act,
        cabinet_mm=cabinet["bounds_mm"],
        branch_south_mm=bottom,
        branch_north_mm=top,
        reserved_aisle_mm=1300,
        north_home_south_mm=row_bottom,
        north_home_north_mm=row_top,
        north_home_delta_mm=n,
        finished_north_mm=g["model"]["clear"][3],
        gaps=gaps,
        all_section_100_met=all(v >= 100 for v in gaps.values()),
        horizontal_reference_remaining_mm=g["parameters"]["reach_horizontal_mm"] - (480 + o),
        formulae=[
            "door=65+operator_delta",
            "activity_to_aisle=100+branch_delta-operator_delta",
            "north_to_aisle=135+north_delta-branch_delta",
            "north_wall=145-north_delta",
        ],
        actual_hardware_human_reach="INPUT_REQUIRED",
        sensitivity_target_mm=100,
    )


def construct_local_adjustment(base: dict[str, Any], choice: dict[str, Any]) -> dict[str, Any]:
    section = local_section(base, choice)
    if choice["scope"] == "SECTION_ONLY":
        raise ValueError("PERSON_ONLY_NEGATIVE_SECTION_IS_NOT_A_FULL_LAYOUT_CANDIDATE")
    if choice["operator_delta_mm"] != choice["branch_delta_mm"]:
        raise ValueError("ORIGINAL_SNAPSHOT_FACTORY_REQUIRES_COORDINATED_BRANCH")
    g = copy.deepcopy(base)
    g.update(
        version=VERSION,
        local_adjustment=copy.deepcopy(choice),
        snapshots=[],
        schedule_diagnostics=[],
    )
    # Rebuild physical positions from the parameter, never edit archived event proofs.
    g["parameters"]["operator_standoff_mm"] += choice["operator_delta_mm"]
    g["conditions"]["operator_standoff_mm"] += choice["operator_delta_mm"]
    delta = section["north_home_delta_mm"]
    for h in g["model"]["homes"]:
        if h["region"].startswith("NORTH"):
            x, y, r, t = h["bounds_mm"]
            h["bounds_mm"] = [x, y + delta, r, t + delta]
    g["hierarchy_failures"] = complete_inventory_conflicts(g["inventory"], g["demand"])
    hp, cfg = H5Hypothesis(**g["parameters"]), FrontParameters(**g["front_parameters"])
    g["waiting_snapshots"] = {str(s): sizing_snapshot(g, s, [], "ALL_WAITING") for s in (1, 2)}
    g["waiting_evaluation"] = validate_use(
        g["room"], g["inventory"], g["model"], hp, g["waiting_snapshots"]["1"]
    )
    g["waiting_clearance_conflicts"] = waiting_clearances(g)
    static = not (
        g["hierarchy_failures"]
        or g["waiting_evaluation"]["conflicts"]
        or g["waiting_clearance_conflicts"]
    )
    g["static_status"] = "STATIC_GEOMETRY_PASS" if static else "STATIC_GEOMETRY_REJECTED"
    top = g["waiting_snapshots"]["1"]["branch_y"] + hp.aisle_mm // 2
    g["cross_section"].update(
        branch_north_edge_mm=top,
        status="NECESSARY_CONDITIONS_PASS"
        if top <= g["model"]["clear"][3]
        else "SECTION_REJECTED_FOR_THIS_TEMPLATE",
    )
    if static:
        for shift in (1, 2):
            proposed, diagnostic = _schedule(g, shift, cfg)
            for s in proposed:
                q = sizing_snapshot(g, shift, s["actions"], s["id"])
                q["evaluation"] = validate_use(g["room"], g["inventory"], g["model"], hp, q)
                q["front_activity_evaluation"] = activity_proof(
                    g,
                    q,
                    {p["id"]: p for p in q["people"]},
                    [a["person_id"] for a in q["actions"]],
                    activity_parameters(g),
                )
                q["group_verified"] = not (
                    q["evaluation"]["conflicts"] or q["front_activity_evaluation"]["conflicts"]
                )
                g["snapshots"].append(q)
            g["schedule_diagnostics"].append(dict(diagnostic, shift=shift))
    # Existing frozen fields, including actual room and cabinet geometry, are unmodified.
    g["metrics"].update(north_strip_available_mm=g["model"]["clear"][3] - top)
    return g


def analytic_opening_distances(
    g: dict[str, Any], flows: list[dict[str, Any]], door_check: dict[str, Any]
) -> dict[str, Any]:
    """Exact distances to the ORIGINAL conservative model, not actual hardware.

    This avoids relying on the archived positive-quadrant sweep box as a universal
    thickness envelope. Original collision checks are independently still required.
    """
    own = []
    minimum = None
    checked = 0
    for event in door_check["events"]:
        people = event["proof"]["people_count"]
        flow = next(f for f in flows if f["shift"] == event["shift"])
        original = next(e for e in flow["events"] if e["index"] == event["event"])
        objects = [*original["proof"]["people_before"], *g["inventory"]["cabinet_units"]]
        if people != len(original["proof"]["people_before"]):
            raise ValueError("ACTUAL_LIVE_ROSTER_REQUIRED_FOR_DISTANCE")
        for door in event["proof"]["doors"]:
            for obj in objects:
                if obj["id"] == door["unit_id"]:
                    continue
                for volume in obj["volumes_mm"]:
                    proof = certified_sweep_distance(door, volume)
                    checked += 1
                    row = dict(
                        shift=event["shift"],
                        event=event["event"],
                        door_id=door["id"],
                        object_id=obj["id"],
                        distance=proof,
                    )
                    if (
                        minimum is None
                        or proof["model_distance_lower_um"]
                        < minimum["distance"]["model_distance_lower_um"]
                    ):
                        minimum = row
                    if obj.get("compartment_id") == door["compartment_id"]:
                        own.append(row)
    return dict(
        all_object_volume_checks=checked,
        own_person_openings=own,
        minimum=minimum,
        mathematical_scope="ORIGINAL_CONSERVATIVE_THICKNESS_MODEL_ONLY",
        actual_clearance="INPUT_REQUIRED",
    )
