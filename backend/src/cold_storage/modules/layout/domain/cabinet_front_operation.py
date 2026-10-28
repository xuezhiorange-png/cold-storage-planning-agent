"""R8 full door/retrieval/change/storage trace on verified interleaved groups.

Actions are parallel within a group. Movement is serial, with every other actual
occupant retained. Timings, body envelopes and the two-opening protocol are demos.
"""

import copy
from dataclasses import asdict, dataclass
from typing import Any

from cold_storage.modules.layout.domain.cabinet_front_schedule import FrontParameters
from cold_storage.modules.layout.domain.changing_operation_motion import (
    PASS,
    portal_crossing,
    transfer,
    validate_live_locker_use,
)
from cold_storage.modules.layout.domain.changing_room_motion import door_hits_box
from cold_storage.modules.layout.domain.full_changing_operation import (
    OperationHypothesis,
    portal_audit,
)
from cold_storage.modules.layout.domain.practical_changing_layout import (
    H5Hypothesis,
    _snapshot,
    validate_use,
)
from cold_storage.modules.layout.domain.standing_changing_operation import activity_proof


@dataclass(frozen=True)
class FrontTiming:
    walk_mm_per_second: int = 600
    open_seconds: int = 3
    retrieve_seconds: int = 20
    close_seconds: int = 3
    changing_seconds: int = 90
    store_seconds: int = 20

    def checked(self) -> None:
        if any(type(v) is not int or not 0 < v <= 3600 for v in asdict(self).values()):
            raise ValueError("POSITIVE_REVIEWABLE_FRONT_TIMES_REQUIRED")


def open_door_activity_proof(g: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
    """Sensitivity only: keeping the actual assigned leaves open during dressing."""
    proof: dict[str, Any] = copy.deepcopy(s["front_activity_evaluation"])
    for o in proof["activity_volumes"]:
        for d in s["doors"]:
            if any(door_hits_box(d, v) for v in o["volumes_mm"]):
                proof["conflicts"].append(
                    dict(
                        code="OPEN_DOOR_DRESSING_COLLISION",
                        person_id=o["id"],
                        door_id=d["id"],
                        volume_mm=o["volumes_mm"][0],
                    )
                )
    proof["status"] = PASS if not proof["conflicts"] else "CONFIGURATION_NOT_FIT"
    proof["doors"] = s["doors"]
    proof["scope"] = "OPEN_DURING_CHANGING_NOT_THE_CLOSED_DOOR_PROTOCOL"
    return proof


def simulate_front_shift(
    g: dict[str, Any], shift: int, cfg: FrontParameters, timing: FrontTiming | None
) -> dict[str, Any]:
    p = cfg.standing()
    if shift not in (1, 2) or g["front_parameters"] != asdict(cfg):
        raise ValueError("EXACT_FRONT_TEMPLATE_AND_SHIFT_REQUIRED")
    if timing is not None:
        timing.checked()
    if (
        g["model"]["benches"]
        or g["model"]["changing_zone"] is not None
        or g["parameters"]["bench_count"] != 0
    ):
        raise ValueError("CURRENT_PROJECT_HAS_NO_BENCH_OR_SEPARATE_CHANGING_STATION")
    seq = [s for s in g["snapshots"] if s["shift"] == shift]
    expected = {a["person_id"] for a in g["inventory"]["person_assignments"] if a["shift"] == shift}
    current: dict[str, Any] = {}
    departed: set[str] = set()
    served: set[str] = set()
    completed_batches: list[str] = []
    events: list[dict[str, Any]] = []
    routes = dict.fromkeys(sorted(expected), 0)
    service_seconds = dict.fromkeys(sorted(expected), 0.0)
    arrival: dict[str, float] = {}
    departure: dict[str, float] = {}
    total = 0.0
    durations: dict[str, float] = {}
    blocker = None
    entry = None

    def record(
        op: str,
        proof: dict[str, Any],
        batch: str | None = None,
        active: list[str] | None = None,
        seconds: float | None = None,
    ) -> bool:
        nonlocal total, blocker
        people = active or ([proof["person_id"]] if "person_id" in proof else [])
        okay = bool(proof["status"] == PASS)
        if "people_before" not in proof:
            proof = dict(proof, people_before=copy.deepcopy(list(current.values())))
        length = proof.get("length_mm", 0)
        if okay and proof.get("person_id") in routes:
            routes[proof["person_id"]] += length
        duration = None
        if timing and okay:
            duration = seconds if seconds is not None else length / timing.walk_mm_per_second
        if (
            timing
            and okay
            and op == "ENTER_AND_REACH_WAITING_POSITION"
            and "interior_person" in proof
        ):
            arrival[proof["person_id"]] = total
        events.append(
            dict(
                index=len(events),
                operation=op,
                batch=batch,
                active_people=people,
                start_seconds=total if timing else None,
                end_seconds=total + duration if duration is not None else None,
                duration_seconds=duration,
                proof=proof,
                inside_people=len(current),
                departed_people=len(departed),
                not_entered_people=len(expected - set(current) - departed),
                accounted_users=len(expected),
            )
        )
        if duration is not None:
            total += duration
            durations[op] = durations.get(op, 0.0) + duration
            if active:
                for key in active:
                    service_seconds[key] += duration
            if op == "EXIT_PORTAL":
                departure[proof["person_id"]] = total
        if not okay:
            blocker = dict(operation=op, batch=batch, conflicts=proof.get("conflicts", []))
        return okay

    def output() -> dict[str, Any]:
        complete = (
            departed == expected and served == expected and len(completed_batches) == len(seq)
        )
        hist: dict[str, int] = {}
        for e in events:
            if e["operation"] == "PARALLEL_STANDING_CHANGE" and e["proof"]["status"] == PASS:
                n = str(len(e["active_people"]))
                hist[n] = hist.get(n, 0) + 1
        personal = {}
        for key in sorted(expected):
            done = key in departed
            residence = departure[key] - arrival[key] if timing and done else None
            walk = routes[key] / timing.walk_mm_per_second if timing else None
            wait = (
                residence - walk - service_seconds[key]
                if residence is not None and walk is not None
                else None
            )
            if wait is not None and wait < -1e-6:
                raise ValueError("INVALID_PERSON_TIME_PARTITION")
            personal[key] = dict(
                completed=done,
                route_mm=routes[key],
                walking_seconds=walk,
                action_seconds=service_seconds[key] if timing else None,
                residence_seconds=residence,
                serial_waiting_seconds=wait,
                scope="FROM_OWN_ENTRY_CROSSING_TO_OWN_EXIT; OUTSIDE_QUEUE_NOT_VALIDATED",
            )
        return dict(
            shift=shift,
            status=PASS if complete else "BLOCKED",
            mode="CABINET_FRONT",
            design_users=53,
            initial_service_occupancy=53 if entry and entry["status"] == PASS else 0,
            completed_users=len(departed),
            completed_person_ids=sorted(departed),
            served_person_ids=sorted(served),
            remaining_inside=sorted(current),
            not_entered_people=sorted(expected - set(current) - departed),
            expected_batches=len(seq),
            completed_batches=completed_batches,
            completed_batch_boundaries=max(0, len(completed_batches) - 1),
            requested_concurrency=cfg.requested_concurrency,
            actual_peak_concurrency=max(map(int, hist), default=0),
            concurrency_histogram=hist,
            events=events,
            entry=entry,
            blocker=blocker,
            personnel_time_and_route=personal,
            personnel_route_mm=routes,
            total_route_mm=sum(routes.values()),
            total_route_m=sum(routes.values()) / 1000,
            full_shift_seconds=total if complete and timing else None,
            full_shift_minutes=total / 60 if complete and timing else None,
            completed_prefix_seconds=total if timing else None,
            duration_by_operation_seconds=durations,
            wall_walking_seconds=sum(
                durations.get(op, 0.0)
                for op in (
                    "ENTER_AND_REACH_WAITING_POSITION",
                    "TO_PERSONAL_LOCKER",
                    "TO_PACKAGING_PORTAL",
                    "EXIT_PORTAL",
                )
            )
            if timing
            else None,
            wall_parallel_action_seconds=sum(
                value
                for op, value in durations.items()
                if op
                not in {
                    "ENTER_AND_REACH_WAITING_POSITION",
                    "TO_PERSONAL_LOCKER",
                    "TO_PACKAGING_PORTAL",
                    "EXIT_PORTAL",
                }
            )
            if timing
            else None,
            max_completed_person_waiting_seconds=max(
                (
                    v["serial_waiting_seconds"]
                    for v in personal.values()
                    if v["serial_waiting_seconds"] is not None
                ),
                default=None,
            ),
            concurrency_model="VERIFIED_PARALLEL_CABINET_ACTIONS_SERIAL_MOVEMENT",
            movement_parallelism=1,
            protocol_approval="INPUT_REQUIRED",
            actual_throughput_satisfied="INPUT_REQUIRED",
            project_functional_status="INPUT_REQUIRED",
        )

    hp = H5Hypothesis(**g["parameters"])
    base = _snapshot(g["room"], g["inventory"], g["model"], hp, shift, [], "ALL_WAITING")
    errors = (
        list(g["hierarchy_failures"])
        + validate_use(g["room"], g["inventory"], g["model"], hp, base)["conflicts"]
    )
    for s in seq:
        errors += validate_use(g["room"], g["inventory"], g["model"], hp, s)["conflicts"]
    scheduled = [a["person_id"] for s in seq for a in s["actions"]]
    if errors or len(expected) != 53 or set(scheduled) != expected or len(scheduled) != 53:
        blocker = dict(
            operation="STATIC_TEMPLATE_OR_INCOMPLETE_SCHEDULE",
            conflicts=errors,
            scheduling=g["schedule_diagnostics"],
        )
        return output()
    entry = portal_audit(g, shift, OperationHypothesis(seat_motion_allowance_mm=0), entering=True)
    for move in entry["moves"]:
        if not record("ENTER_AND_REACH_WAITING_POSITION", move):
            return output()
        current[move["person_id"]] = copy.deepcopy(move.get("target", move.get("interior_person")))
    if entry["status"] != PASS or current != {o["id"]: o for o in seq[0]["home_people"]}:
        blocker = dict(
            operation="ENTRY", conflicts=[dict(code="ALL_53_MUST_REACH_WAITING_POSITIONS")]
        )
        return output()
    for s in seq:
        active = [a["person_id"] for a in s["actions"]]
        targets = {o["id"]: o for o in s["people"]}
        if set(current) | departed != expected or set(current) & departed or set(active) & served:
            raise ValueError("COMPLETE_ROSTER_AND_ONCE_ONLY_SERVICE_REQUIRED")
        for key in active:
            proof = transfer(current, targets[key], g, s, seat_allowance_mm=0, exited=departed)
            if not record("TO_PERSONAL_LOCKER", proof, s["id"]):
                return output()
        # No person moves during each three-step door-use phase, so its same full
        # quarter-disk proof is reusable for opening, access and closing. Recheck
        # after changing before the second opening, against actual remaining people.
        for phase in ("RETRIEVE", "CHANGE", "STORE"):
            if phase == "CHANGE":
                proof = activity_proof(g, s, current, active, p)
                if not record(
                    "PARALLEL_STANDING_CHANGE",
                    proof,
                    s["id"],
                    active,
                    timing.changing_seconds if timing else None,
                ):
                    return output()
                continue
            conflicts = validate_live_locker_use(g, s, current, departed)
            proof = dict(
                status=PASS if not conflicts else "CONFIGURATION_NOT_FIT",
                conflicts=conflicts,
                doors=s["doors"],
                actions=s["actions"],
                people_before=copy.deepcopy(list(current.values())),
            )
            action_time = (
                (timing.retrieve_seconds if phase == "RETRIEVE" else timing.store_seconds)
                if timing
                else None
            )
            for op, secs in [
                ("OPEN_FOR_" + phase, timing.open_seconds if timing else None),
                (phase + "_CLOTHES", action_time),
                ("CLOSE_AFTER_" + phase, timing.close_seconds if timing else None),
            ]:
                if not record(op, proof, s["id"], active, secs):
                    return output()
        served.update(active)
        for key in active:
            cross = portal_crossing(
                current[key],
                g["room"]["portals"][1],
                g,
                [v for k, v in current.items() if k != key],
                entering=False,
            )
            if cross["status"] != PASS:
                record("EXIT_PORTAL", cross, s["id"])
                return output()
            proof = transfer(
                current, cross["interior_person"], g, s, seat_allowance_mm=0, exited=departed
            )
            if not record("TO_PACKAGING_PORTAL", proof, s["id"]) or not record(
                "EXIT_PORTAL", cross, s["id"]
            ):
                return output()
            del current[key]
            departed.add(key)
        completed_batches.append(s["id"])
    return output()
