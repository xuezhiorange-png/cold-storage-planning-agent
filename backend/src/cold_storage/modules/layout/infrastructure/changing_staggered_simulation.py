"""Explicit conditional examples, never reviewed project inputs or Native results."""

import copy
from dataclasses import replace
from typing import Any

from cold_storage.modules.layout.domain.changing_locker_screening import (
    HypotheticalLockerParameters,
    screen_locker_rows,
)
from cold_storage.modules.layout.domain.changing_shift_use import validate_shift_use
from cold_storage.modules.layout.domain.functional_room_fit import (
    COMMON,
    REQUIRED,
    STATES,
    BasisValue,
    evaluate_functional_room,
)


def simulate_staggered_h5(
    room: dict[str, Any], design: dict[str, Any], p: HypotheticalLockerParameters
) -> dict[str, Any]:
    """Build two supplied row/route scenarios from real portals, with unapproved assumptions.

    The original engineering result is never replaced. R11 receives a distinct
    hypothetical scope and evaluates those conditional assumptions only.
    """
    result: dict[str, Any] = dict(
        source_type="demo",
        validity_status="unverified",
        requires_review=True,
        source_label="HYPOTHETICAL_NOT_APPROVED",
        project_status="INPUT_REQUIRED",
        simulation_status="NOT_EVALUATED",
        shifts={},
        assumptions=dict(
            room_door_operation="HYPOTHETICAL_OPEN_PORTAL_NO_LEAF",
            locker_door_motion="HYPOTHETICAL_NO_FLOOR_SWEEP",
            inactive_bank="HYPOTHETICAL_CLOSED",
            clear_height_mm=4000,
            clean_separation="HYPOTHETICAL_NOT_REQUIRED",
            finished_clear_inset_mm=p.finish_inset_mm,
            original_portals_unchanged=True,
        ),
    )
    x0, y0, x1, y1 = room["local_bounds_mm"]
    east = [q for q in room["portals"] if all(a[0] == x1 for a in q["segment_mm"])]
    south = [q for q in room["portals"] if all(a[1] == y0 for a in q["segment_mm"])]
    if p.arrangement != "DOUBLE_SIDE" or (x0, y0) != (0, 0) or len(east) != 1 or len(south) != 1:
        result["not_evaluated_reason"] = "THIS_EXPLICIT_H5_EAST_SOUTH_TWO_BANK_TEMPLATE_ONLY"
        return result
    if p.aisle_mm > min(q["clear_width_mm"] for q in room["portals"]):
        result["simulation_status"] = "CONFIGURATION_NOT_FIT"
        result["not_evaluated_reason"] = "HYPOTHETICAL_AISLE_WIDER_THAN_REAL_PORTAL"
        return result
    simulated = copy.deepcopy(room)
    simulated["scope_id"] = "HYPOTHETICAL_NOT_APPROVED:" + room["scope_id"]
    simulated["original_engineering_status"] = "HYPOTHETICAL_NOT_PROJECT_ACCEPTANCE"
    columns = COMMON | REQUIRED["changing_room"]
    for shift in (1, 2):
        s = screen_locker_rows(
            room,
            design["locker_count"],
            design["simultaneous_users"],
            replace(p, active_shift=shift),
        )
        if (
            s["placed_lockers"] != design["locker_count"]
            or s["placed_person_spaces"] != design["simultaneous_users"]
        ):
            result["simulation_status"] = "CONFIGURATION_NOT_FIT"
            result["not_evaluated_reason"] = "THIS_TEMPLATE_CANNOT_SUPPLY_BOTH_SHIFT_POSITIONS"
            return result
        components = []
        for raw in s["components"]:
            if raw["role"] not in {"LOCKER", "PERSON", "BENCH"}:
                continue
            c = copy.deepcopy(raw)
            if c["role"] == "LOCKER":
                c["front"] = "N" if c["row"] == 1 else "S"
            if c["role"] == "PERSON":
                c["shift"] = shift
            if c["role"] == "BENCH":
                c["front"] = "N"
            components.append(c)
        half = p.aisle_mm // 2
        after = p.aisle_mm - half
        entry_center = (east[0]["segment_mm"][0][1] + east[0]["segment_mm"][1][1]) // 2
        active_rows = {
            c["row"] for c in components if c["role"] == "LOCKER" and c["shift"] == shift
        }
        net_low = p.locker_depth_mm + (
            max(p.front_clearance_mm, p.person_depth_mm) if 1 in active_rows else 0
        )
        net_high = (
            y1
            - p.locker_depth_mm
            - (max(p.front_clearance_mm, p.person_depth_mm) if 2 in active_rows else 0)
        )
        if net_high - net_low < p.aisle_mm:
            result["simulation_status"] = "CONFIGURATION_NOT_FIT"
            result["not_evaluated_reason"] = (
                "ACTIVE_BANKS_LEAVE_INSUFFICIENT_NET_AISLE_IN_THIS_TEMPLATE"
            )
            return result
        center = min(max(entry_center, net_low + half), net_high - after)
        sx = (south[0]["segment_mm"][0][0] + south[0]["segment_mm"][1][0]) // 2
        if center - half < 0 or center + after > y1:
            result["simulation_status"] = "CONFIGURATION_NOT_FIT"
            result["not_evaluated_reason"] = "HYPOTHETICAL_CLEAR_ROUTE_OUTSIDE_ROOM"
            return result
        components += [
            dict(
                id="dynamic-net-aisle",
                role="AISLE",
                bounds_mm=[0, net_low, x1, net_high],
                states=list(STATES),
            ),
            dict(
                id="south-portal-net-link",
                role="AISLE",
                bounds_mm=[sx - half, 0, sx + after, center + after],
                states=list(STATES),
            ),
        ]
        witness = dict(
            components=components,
            routes=[
                dict(
                    id="hypothetical-interior-two-portal-route",
                    points_mm=[[sx, 0], [sx, center], [x1, center]],
                    width_mm=p.aisle_mm,
                    states=list(STATES),
                )
            ],
        )
        values = dict(
            finished_clear_bounds_mm=[
                p.finish_inset_mm,
                p.finish_inset_mm,
                x1 - p.finish_inset_mm,
                y1 - p.finish_inset_mm,
            ],
            clear_height_mm=4000,
            aisle_width_mm=p.aisle_mm,
            door_operation="OPEN_PORTAL",
            door_operation_envelopes_mm={q["id"]: [] for q in room["portals"]},
            cleaning_maintenance_basis=(
                "HYPOTHETICAL bank-specific sequential cleaning/maintenance, not approved"
            ),
            simultaneous_users=design["simultaneous_users"],
            shift_locker_counts=design["shift_workers"],
            shift_change_policy="NON_OVERLAPPING",
            locker_model="HYPOTHETICAL_NOT_SELECTED_LOCKER",
            locker_internal_separation_available=True,
            locker_dimensions_mm=[p.locker_width_mm, p.locker_depth_mm, p.locker_height_mm],
            locker_arrangement="DOUBLE_SIDE",
            locker_front_clearance_mm=p.front_clearance_mm,
            person_space_mm=[p.person_width_mm, p.person_depth_mm],
            bench_count=p.bench_count,
            bench_dimensions_mm=[p.bench_width_mm, p.bench_depth_mm, p.bench_height_mm]
            if p.bench_count
            else "NOT_APPLICABLE",
            bench_operation_mm=p.bench_operation_mm if p.bench_count else "NOT_APPLICABLE",
            internal_clothing_separation=True,
            clean_separation="NOT_REQUIRED",
        )
        basis = {
            k: BasisValue(
                v,
                columns[k],
                "ENGINEERING_DERIVED",
                "HYPOTHETICAL_NOT_APPROVED:R3_STAGGERED_ASSUMPTION:" + k,
                simulated["scope_id"],
                k,
            )
            for k, v in values.items()
        }
        legacy = evaluate_functional_room(
            simulated, {k: k for k in basis}, witness, reviewed_basis=basis
        )
        active = [c["id"] for c in components if c["role"] == "LOCKER" and c["shift"] == shift]
        plan = {
            state: dict(
                active_locker_ids=active,
                inactive_lockers_closed=True,
                door_motion_basis=(
                    "HYPOTHETICAL selected locker has no intruding floor sweep; unconfirmed"
                ),
                locker_door_motion={
                    key: dict(mode="NO_FLOOR_SWEEP", exclusions_mm=[]) for key in active
                },
            )
            for state in STATES
        }
        checked = validate_shift_use(
            simulated, witness, legacy, shift, design["shift_workers"], plan
        )
        result["shifts"][str(shift)] = dict(
            witness=witness,
            original_r11=legacy,
            r3=checked,
            route_center_y_mm=center,
            source_label="HYPOTHETICAL_NOT_APPROVED",
        )
    result["simulation_status"] = (
        "GEOMETRY_VALID_ONLY_UNDER_HYPOTHESES"
        if all(v["r3"]["status"] == "SHIFT_USE_VALIDATED" for v in result["shifts"].values())
        else "CONFIGURATION_NOT_FIT"
        if any(
            v["r3"]["conflicts"] or v["original_r11"]["conflicts"]
            for v in result["shifts"].values()
        )
        else "NOT_EVALUATED_INCOMPLETE_SIMULATION"
    )
    return result
