"""R7 complete standing service; concurrent actions, collision-checked serial moves.

The finite schedule is a conditional witness, not an optimal queue or a throughput
approval. Both shifts start service only after all 53 design users have entered.
"""

import copy
from dataclasses import asdict, dataclass
from typing import Any

from cold_storage.modules.layout.domain.changing_operation_motion import (
    PASS,
    check_volumes,
    portal_crossing,
    transfer,
    validate_live_locker_use,
)
from cold_storage.modules.layout.domain.changing_room_motion import prism
from cold_storage.modules.layout.domain.full_changing_operation import (
    OperationHypothesis,
    portal_audit,
)
from cold_storage.modules.layout.domain.functional_room_fit import intersection, rectangle
from cold_storage.modules.layout.domain.practical_changing_layout import H5Hypothesis, validate_use
from cold_storage.modules.layout.domain.standing_changing_layout import StandingParameters


@dataclass(frozen=True)
class StandingTiming:
    walk_mm_per_second: int = 600
    locker_seconds: int = 20
    changing_seconds: int = 90

    def checked(self) -> None:
        if any(type(v) is not int or not 0 < v <= 3600 for v in asdict(self).values()):
            raise ValueError("POSITIVE_REVIEWABLE_TIME_HYPOTHESES_REQUIRED")


def activity_proof(
    result: dict[str, Any],
    snapshot: dict[str, Any],
    current: dict[str, Any],
    active: list[str],
    params: StandingParameters,
) -> dict[str, Any]:
    """Simultaneous dressing volumes, kept outside aisles and other actual people.

    Volumes extend away from the reserved aisle. They contain the transport body;
    they do not silently translate it, waive waiting people, or sample collisions.
    """
    params.checked()
    if len(set(active)) != len(active) or not set(active) <= set(current):
        raise ValueError("DISTINCT_PRESENT_ACTIVITY_USERS_REQUIRED")
    volumes: list[dict[str, Any]] = []
    for key in active:
        o = current[key]
        x, y, r, t = o["bounds_mm"]
        extra = params.activity_width_mm - (r - x)
        if extra < 0 or params.activity_depth_mm < t - y:
            raise ValueError("ACTIVITY_MUST_CONTAIN_ACTUAL_BODY")
        bottom = (
            t - params.activity_depth_mm
            if o["role"] == "FRONT_OPERATOR" or y < result["model"]["main_y"]
            else y
        )
        box = [x - extra // 2, bottom, r + extra - extra // 2, bottom + params.activity_depth_mm]
        volumes.append(
            dict(id=key, bounds_mm=box, volumes_mm=[prism(box, 0, params.activity_height_mm)])
        )
    bodies = result["inventory"]["cabinet_units"]
    others = [v for k, v in current.items() if k not in active]
    conflicts: list[dict[str, Any]] = []
    for i, obj in enumerate(volumes):
        errors = check_volumes(
            obj["volumes_mm"],
            [*others, *volumes[i + 1 :]],
            bodies,
            result["model"]["clear"],
            result["parameters"]["clear_height_mm"],
        )
        conflicts.extend(dict(e, person_id=obj["id"]) for e in errors)
        for aisle in snapshot["aisles"]:
            if intersection(rectangle(obj["bounds_mm"]), rectangle(aisle)):
                conflicts.append(
                    dict(
                        code="DRESSING_ACTIVITY_INTRUDES_NET_AISLE",
                        person_id=obj["id"],
                        bounds_mm=obj["bounds_mm"],
                    )
                )
        if intersection(rectangle(obj["bounds_mm"]), rectangle(result["model"]["landing"])):
            conflicts.append(
                dict(
                    code="DRESSING_ACTIVITY_INTRUDES_ENTRANCE_LANDING",
                    person_id=obj["id"],
                    bounds_mm=obj["bounds_mm"],
                )
            )
    return dict(
        status=PASS if not conflicts else "CONFIGURATION_NOT_FIT",
        conflicts=conflicts,
        activity_volumes=volumes,
        active_people=active,
        people_before=copy.deepcopy(list(current.values())),
        cabinet_doors="CLOSED_AFTER_REVIEW_REQUIRED_LOCKER_PHASE",
        activity_basis="HYPOTHETICAL_NOT_APPROVED",
        simultaneous_movers=0,
    )


def simulate_shift(
    result: dict[str, Any],
    shift: int,
    params: StandingParameters,
    timing: StandingTiming | None,
) -> dict[str, Any]:
    params.checked()
    if timing is not None:
        timing.checked()
    if shift not in (1, 2) or result["standing_parameters"] != asdict(params):
        raise ValueError("EXACT_STANDING_TEMPLATE_AND_SHIFT_REQUIRED")
    if result["model"]["benches"] or result["parameters"]["bench_count"] != 0:
        raise ValueError("REVIEWED_NO_BENCH_PROTOCOL_REQUIRED")
    seq = [s for s in result["snapshots"] if s["shift"] == shift]
    events: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    departed: set[str] = set()
    served: set[str] = set()
    completed_batches: list[str] = []
    expected = {
        a["person_id"] for a in result["inventory"]["person_assignments"] if a["shift"] == shift
    }
    total = 0.0
    distances = dict.fromkeys(sorted(expected), 0)
    durations: dict[str, float] = {}
    blocker: dict[str, Any] | None = None
    entry: dict[str, Any] | None = None

    def record(
        operation: str,
        proof: dict[str, Any],
        *,
        batch: str | None = None,
        duration: float | None = None,
        active: list[str] | None = None,
    ) -> bool:
        nonlocal total, blocker
        if "people_before" not in proof:
            proof = dict(proof, people_before=copy.deepcopy(list(current.values())))
        okay = bool(proof["status"] == PASS)
        length = proof.get("length_mm", 0)
        if okay and proof.get("person_id") in distances:
            distances[proof["person_id"]] += length
        if timing is not None and duration is None:
            duration = length / timing.walk_mm_per_second
        elapsed = duration if okay and timing is not None else None
        event = dict(
            index=len(events),
            operation=operation,
            batch=batch,
            proof=proof,
            active_people=active or ([proof["person_id"]] if "person_id" in proof else []),
            start_seconds=total if timing else None,
            end_seconds=total + elapsed if elapsed is not None else None,
            duration_seconds=elapsed,
            inside_people=len(current),
            departed_people=len(departed),
            not_entered_people=len(expected - set(current) - departed),
            accounted_users=len(expected),
        )
        events.append(event)
        if elapsed is not None:
            total += elapsed
            durations[operation] = durations.get(operation, 0.0) + elapsed
        if not okay:
            blocker = dict(operation=operation, batch=batch, conflicts=proof.get("conflicts", []))
        return okay

    def output() -> dict[str, Any]:
        complete = (
            departed == expected and served == expected and len(completed_batches) == len(seq)
        )
        return dict(
            shift=shift,
            mode=params.mode,
            status=PASS if complete else "BLOCKED",
            entry=entry,
            service_started=entry is not None and entry["status"] == PASS,
            initial_service_occupancy=53 if entry and entry["status"] == PASS else 0,
            design_users=53,
            completed_users=len(departed),
            completed_person_ids=sorted(departed),
            served_person_ids=sorted(served),
            remaining_inside=sorted(current),
            not_entered_people=sorted(expected - set(current) - departed),
            expected_batches=len(seq),
            completed_batches=completed_batches,
            completed_batch_boundaries=max(0, len(completed_batches) - 1),
            events=events,
            blocker=blocker,
            personnel_route_mm=distances,
            total_route_mm=sum(distances.values()),
            full_shift_seconds=total if complete and timing else None,
            full_shift_minutes=total / 60 if complete and timing else None,
            total_route_m=sum(distances.values()) / 1000,
            completed_prefix_seconds=total if timing else None,
            duration_by_operation_seconds=durations,
            concurrency_model="BATCH_PARALLEL_ACTIONS_SERIAL_MOVEMENT",
            movement_parallelism=1,
            action_concurrency_limit=params.front_concurrency,
            actual_throughput_satisfied="INPUT_REQUIRED",
            project_functional_status="INPUT_REQUIRED",
            note="No sit/rise/seated use. Unfinished people remain physical obstacles.",
        )

    errors = list(result["hierarchy_failures"])
    for s in seq:
        errors.extend(
            validate_use(
                result["room"],
                result["inventory"],
                result["model"],
                H5Hypothesis(**result["parameters"]),
                s,
            )["conflicts"]
        )
    if errors or len(expected) != 53 or not seq:
        blocker = dict(
            operation="STATIC_TEMPLATE", conflicts=errors or [dict(code="INVALID_53_ROSTER")]
        )
        return output()
    entry = portal_audit(
        result, shift, OperationHypothesis(seat_motion_allowance_mm=0), entering=True
    )
    for move in entry["moves"]:
        if not record("ENTER_AND_REACH_WAITING_POSITION", move):
            return output()
        key = move["person_id"]
        current[key] = copy.deepcopy(move.get("target", move.get("interior_person")))
    if entry["status"] != PASS:
        blocker = dict(operation="ENTRY", conflicts=[dict(code="INCOMPLETE_ENTRY")])
        return output()
    if current != {o["id"]: o for o in seq[0]["home_people"]}:
        raise ValueError("ENTRY_TRACE_MUST_REACH_ALL_53_REVIEWED_POSITIONS")
    homes = copy.deepcopy(current)
    for s in seq:
        active = [a["person_id"] for a in s["actions"]]
        desired = {o["id"]: o for o in s["people"]}
        if set(current) | departed != expected or set(current) & departed or set(active) & served:
            raise ValueError("COMPLETE_ROSTER_AND_SINGLE_SERVICE_REQUIRED")
        for key in active:
            proof = transfer(current, desired[key], result, s, seat_allowance_mm=0, exited=departed)
            if not record("TO_PERSONAL_LOCKER", proof, batch=s["id"]):
                return output()
        conflicts = validate_live_locker_use(result, s, current, departed)
        proof = dict(
            status=PASS if not conflicts else "CONFIGURATION_NOT_FIT",
            conflicts=conflicts,
            doors=s["doors"],
            actions=s["actions"],
            people_before=copy.deepcopy(list(current.values())),
        )
        if not record(
            "PARALLEL_LOCKER_USE_AND_CLOSE",
            proof,
            batch=s["id"],
            active=active,
            duration=timing.locker_seconds if timing else None,
        ):
            return output()
        if params.mode == "DISTRIBUTED":
            for key in active:
                proof = transfer(
                    current, homes[key], result, s, seat_allowance_mm=0, exited=departed
                )
                if not record("TO_DISTRIBUTED_STANDING_POSITION", proof, batch=s["id"]):
                    return output()
        proof = activity_proof(result, s, current, active, params)
        if not record(
            "PARALLEL_STANDING_CHANGE",
            proof,
            batch=s["id"],
            active=active,
            duration=timing.changing_seconds if timing else None,
        ):
            return output()
        served.update(active)
        for key in active:
            cross = portal_crossing(
                current[key],
                result["room"]["portals"][1],
                result,
                [v for k, v in current.items() if k != key],
                entering=False,
            )
            if cross["status"] != PASS:
                record("EXIT_PORTAL", cross, batch=s["id"])
                return output()
            proof = transfer(
                current, cross["interior_person"], result, s, seat_allowance_mm=0, exited=departed
            )
            if not record("TO_PACKAGING_PORTAL", proof, batch=s["id"]):
                return output()
            if not record("EXIT_PORTAL", cross, batch=s["id"]):
                return output()
            del current[key]
            departed.add(key)
        completed_batches.append(s["id"])
    return output()
