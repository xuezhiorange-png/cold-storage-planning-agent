"""R10 counterfactual-room full-service adapter; original validation is unchanged.

This adapts the baseline snapshot factory to explicit R10 aisle padding. All 53 enter
before service; actual remaining users are never removed to clear a route.
"""

import copy
from dataclasses import asdict
from typing import Any

from cold_storage.modules.layout.domain.changing_operation_motion import (
    PASS,
    portal_crossing,
    validate_live_locker_use,
)
from cold_storage.modules.layout.domain.h5_relayout_motion import relayout_transfer
from cold_storage.modules.layout.domain.h5_relayout_operation import RelayoutTiming
from cold_storage.modules.layout.domain.h5_space_relayout import waiting_clearances
from cold_storage.modules.layout.domain.practical_changing_layout import (
    H5Hypothesis,
    validate_use,
)
from cold_storage.modules.layout.domain.reverse_sizing_geometry import (
    activity_parameters,
    sizing_snapshot,
)
from cold_storage.modules.layout.domain.standing_changing_operation import activity_proof


def simulate_sizing_shift(
    g: dict[str, Any], shift: int, timing: RelayoutTiming | None
) -> dict[str, Any]:
    if shift not in (1, 2):
        raise ValueError("EXACT_PROJECT_SHIFT_REQUIRED")
    if timing:
        timing.checked()
    hp = H5Hypothesis(**g["parameters"])
    if g["model"]["benches"] or g["model"]["changing_zone"] is not None or hp.bench_count != 0:
        raise ValueError("NO_BENCH_OR_SEPARATE_CHANGING_STATION_REQUIRED")
    expected = {a["person_id"] for a in g["inventory"]["person_assignments"] if a["shift"] == shift}
    seq = [s for s in g["snapshots"] if s["shift"] == shift]
    base = sizing_snapshot(g, shift, [], "ALL_WAITING")
    if base != g["waiting_snapshots"][str(shift)]:
        raise ValueError("WAITING_GEOMETRY_AND_REFERENCE_MUST_MATCH")
    current: dict[str, Any] = {}
    departed: set[str] = set()
    served: set[str] = set()
    events: list[dict[str, Any]] = []
    completed: list[str] = []
    routes = dict.fromkeys(sorted(expected), 0)
    total = 0.0
    durations: dict[str, float] = {}
    blocker = None
    initial = 0

    def record(
        op: str,
        proof: dict[str, Any],
        *,
        batch: str | None = None,
        active: list[str] | None = None,
        seconds: float | None = None,
    ) -> bool:
        nonlocal total, blocker
        okay = bool(proof["status"] == PASS)
        if "people_before" not in proof:
            proof = dict(proof, people_before=copy.deepcopy(list(current.values())))
        length = proof.get("length_mm", 0)
        duration = (
            (
                seconds
                if seconds is not None
                else length / timing.front.walk_mm_per_second
                + proof.get("yaw_turn_count", 0) * timing.yaw_seconds
            )
            if timing and okay
            else None
        )
        events.append(
            dict(
                index=len(events),
                operation=op,
                proof=proof,
                batch=batch,
                active_people=active or [],
                inside_people=len(current),
                departed_people=len(departed),
                not_entered_people=len(expected - set(current) - departed),
                accounted_users=len(expected),
                duration_seconds=duration,
                start_seconds=total if timing else None,
                end_seconds=total + duration if duration is not None else None,
            )
        )
        if okay and proof.get("person_id") in routes:
            routes[proof["person_id"]] += length
        if duration is not None:
            total += duration
            durations[op] = durations.get(op, 0.0) + duration
        if not okay:
            blocker = dict(operation=op, batch=batch, conflicts=proof["conflicts"])
        return okay

    def output() -> dict[str, Any]:
        complete = (
            len(expected) == 53 and departed == expected == served and len(completed) == len(seq)
        )
        return dict(
            shift=shift,
            status=PASS if complete else "BLOCKED",
            design_users=53,
            initial_service_occupancy=initial,
            completed_users=len(departed),
            completed_person_ids=sorted(departed),
            served_person_ids=sorted(served),
            remaining_inside=sorted(current),
            not_entered_people=sorted(expected - set(current) - departed),
            events=events,
            completed_batches=completed,
            expected_batches=len(seq),
            blocker=blocker,
            personnel_route_mm=routes,
            total_route_m=sum(routes.values()) / 1000,
            full_shift_seconds=total if complete and timing else None,
            full_shift_minutes=total / 60 if complete and timing else None,
            duration_by_operation_seconds=durations,
            timing=asdict(timing) if timing else None,
            conditional_time_scope="SERIAL_WALK_AND_YAW_PLUS_PARALLEL_R8_DOOR_AND_CHANGING_ACTIONS",
            actual_throughput_satisfied="INPUT_REQUIRED",
            project_functional_status="INPUT_REQUIRED",
        )

    errors = list(g["hierarchy_failures"]) + waiting_clearances(g)
    for s in [base, *seq]:
        errors += validate_use(g["room"], g["inventory"], g["model"], hp, s)["conflicts"]
    actions = [a["person_id"] for s in seq for a in s["actions"]]
    if errors or len(expected) != 53 or set(actions) != expected or len(actions) != 53:
        blocker = dict(
            operation="STATIC_TEMPLATE_OR_SCHEDULE",
            conflicts=errors,
            scheduling=g["schedule_diagnostics"],
        )
        return output()
    homes = {o["id"]: copy.deepcopy(o) for o in base["home_people"]}
    outside = set(expected)
    for key in sorted(homes, reverse=True):
        proof = portal_crossing(
            homes[key], g["room"]["portals"][0], g, list(current.values()), entering=True
        )
        if not record("ENTER_PORTAL", proof):
            return output()
        current[key] = copy.deepcopy(proof["interior_person"])
        outside.remove(key)
        move = relayout_transfer(current, homes[key], g, base, exited=outside)
        if not record("REACH_WAITING_POSITION", move):
            return output()
    if current != homes:
        raise ValueError("ALL_53_ACTUAL_WAITING_POSITIONS_REQUIRED")
    initial = 53
    for s in seq:
        active = [a["person_id"] for a in s["actions"]]
        targets = {o["id"]: o for o in s["people"]}
        if set(current) | departed != expected or set(current) & departed or set(active) & served:
            raise ValueError("COMPLETE_ROSTER_ONCE_ONLY_SERVICE_REQUIRED")
        for key in active:
            proof = relayout_transfer(current, targets[key], g, s, exited=departed)
            if not record("TO_PERSONAL_LOCKER", proof, batch=s["id"]):
                return output()
        for phase in ("RETRIEVE", "CHANGE", "STORE"):
            if phase == "CHANGE":
                proof = activity_proof(g, s, current, active, activity_parameters(g))
                if not record(
                    "PARALLEL_STANDING_CHANGE",
                    proof,
                    batch=s["id"],
                    active=active,
                    seconds=timing.front.changing_seconds if timing else None,
                ):
                    return output()
            else:
                errors = validate_live_locker_use(g, s, current, departed)
                proof = dict(
                    status=PASS if not errors else "CONFIGURATION_NOT_FIT",
                    conflicts=errors,
                    doors=s["doors"],
                    actions=s["actions"],
                )
                action_time = (
                    (
                        timing.front.retrieve_seconds
                        if phase == "RETRIEVE"
                        else timing.front.store_seconds
                    )
                    if timing
                    else None
                )
                for op, seconds in [
                    ("OPEN_FOR_" + phase, timing.front.open_seconds if timing else None),
                    (phase + "_CLOTHES", action_time),
                    ("CLOSE_AFTER_" + phase, timing.front.close_seconds if timing else None),
                ]:
                    if not record(op, proof, batch=s["id"], active=active, seconds=seconds):
                        return output()
        served.update(active)
        for key in active:
            proof = portal_crossing(
                current[key],
                g["room"]["portals"][1],
                g,
                [v for k, v in current.items() if k != key],
                entering=False,
            )
            if proof["status"] != PASS:
                record("EXIT_PORTAL", proof, batch=s["id"])
                return output()
            move = relayout_transfer(current, proof["interior_person"], g, s, exited=departed)
            if not record("TO_PACKAGING_PORTAL", move, batch=s["id"]) or not record(
                "EXIT_PORTAL", proof, batch=s["id"]
            ):
                return output()
            del current[key]
            departed.add(key)
        completed.append(s["id"])
    return output()
