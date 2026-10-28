"""R6 full two-shift protocol audit, with explicit incomplete/blocked outcomes.

All distances use actual H5 rectangles and existing aisle paths. Timings and
human envelopes are reviewable hypotheses, never Authority or capacity approval.
"""

import copy
import math
from dataclasses import asdict, dataclass
from typing import Any

from cold_storage.modules.layout.domain.changing_operation_motion import (
    PASS,
    check_volumes,
    physical,
    portal_crossing,
    transfer,
)
from cold_storage.modules.layout.domain.changing_room_motion import overlap3, standing_person
from cold_storage.modules.layout.domain.functional_room_fit import intersection, rectangle
from cold_storage.modules.layout.domain.practical_changing_layout import H5Hypothesis, validate_use

VERSION = "h5-full-changing-operation-r11-r6@1.0.0"


@dataclass(frozen=True)
class OperationHypothesis:
    seat_motion_allowance_mm: int = 50

    def checked(self) -> None:
        for v in asdict(self).values():
            if type(v) is not int or not 0 <= v <= 500:
                raise ValueError("BOUNDED_EXPLICIT_ACTIVITY_ENVELOPE_REQUIRED")


@dataclass(frozen=True)
class TimingHypothesis:
    walk_mm_per_second: int = 600
    locker_seconds: int = 20
    changing_seconds: int = 90
    seated_seconds: int = 45
    sit_seconds: int = 4
    rise_seconds: int = 4

    def checked(self) -> None:
        if any(type(v) is not int or not 0 < v <= 3600 for v in asdict(self).values()):
            raise ValueError("POSITIVE_REVIEWABLE_TIME_INPUTS_REQUIRED")


def activity_check(result: dict[str, Any], snapshot: dict[str, Any], margin: int) -> dict[str, Any]:
    """Sensitivity of fixed physical positions; expanding envelopes does not move people."""
    errors = []
    people = snapshot["people"]
    for i, o in enumerate(people):
        x, y, r, t = o["bounds_mm"]
        # Sitting remains a distinct support-contact model, not a standing prism.
        volumes = [
            [v[0] - margin, v[1] - margin, v[2], v[3] + margin, v[4] + margin, v[5]]
            for v in o["volumes_mm"]
        ]
        others = people[i + 1 :]
        for other in others:
            expanded = [
                [v[0] - margin, v[1] - margin, v[2], v[3] + margin, v[4] + margin, v[5]]
                for v in other["volumes_mm"]
            ]
            if any(overlap3(a, b) for a in volumes for b in expanded):
                errors.append(
                    dict(
                        code="ACTIVITY_ENVELOPES_OVERLAP",
                        components=[o["id"], other["id"]],
                        bounds_mm=[x - margin, y - margin, r + margin, t + margin],
                    )
                )
        for aisle in snapshot["aisles"]:
            if intersection((x - margin, y - margin, r + margin, t + margin), rectangle(aisle)):
                errors.append(
                    dict(
                        code="ACTIVITY_INTRUDES_RESERVED_AISLE",
                        components=[o["id"]],
                        bounds_mm=[x - margin, y - margin, r + margin, t + margin],
                    )
                )
        bodies = [*result["inventory"]["cabinet_units"], *result["model"]["benches"]]
        # No waiver for expanded bodies touching their bench: an expanded envelope
        # crossing the support plane is a real model conflict, not an ergonomic pass.
        errors += check_volumes(
            volumes, [], bodies, result["model"]["clear"], result["parameters"]["clear_height_mm"]
        )
    return dict(
        margin_mm=margin,
        status=PASS if not errors else "CONFIGURATION_NOT_FIT",
        conflicts=errors,
        actual_human_motion="INPUT_REQUIRED",
    )


def audit_transition(
    result: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    options: OperationHypothesis,
) -> dict[str, Any]:
    p = H5Hypothesis(**result["parameters"])
    for s in (before, after):
        if validate_use(result["room"], result["inventory"], result["model"], p, s)["conflicts"]:
            return dict(
                from_batch=before["id"],
                to_batch=after["id"],
                shift=before["shift"],
                status="NOT_EVALUATED",
                reason="ENDPOINT_STATIC_REJECTED",
                moves=[],
            )
    current = {v["id"]: copy.deepcopy(v) for v in before["people"]}
    homes = {v["id"]: v for v in before["home_people"]}
    final = {v["id"]: v for v in after["people"]}
    targets = [homes[a["person_id"]] for a in before["actions"]] + [
        final[a["person_id"]] for a in after["actions"]
    ]
    moves = []
    for target in targets:
        if current[target["id"]] == target:
            continue
        proof = transfer(
            current, target, result, before, seat_allowance_mm=options.seat_motion_allowance_mm
        )
        moves.append(proof)
        if proof["status"] != PASS:
            break
    matched = current == final
    return dict(
        from_batch=before["id"],
        to_batch=after["id"],
        shift=before["shift"],
        status=PASS if matched and all(m["status"] == PASS for m in moves) else "BLOCKED",
        endpoint_all_53_match=matched,
        moves=moves,
        diagnostic_scope="INDEPENDENT_PAIR_AUDIT",
        replay_or_native=False,
    )


def _empty(target: dict[str, Any], current: dict[str, Any], key: str) -> bool:
    return not any(
        overlap3(a, b)
        for k, o in current.items()
        if k != key
        for a in target["volumes_mm"]
        for b in o["volumes_mm"]
    )


def _retag(home: dict[str, Any], key: str) -> dict[str, Any]:
    target = copy.deepcopy(home)
    target["id"] = key
    return target


def full_shift(
    result: dict[str, Any],
    shift: int,
    options: OperationHypothesis,
    timing: TimingHypothesis | None,
) -> dict[str, Any]:
    """Execute one conservative serial protocol. On first conflict keep the prefix.

    53 users remain inside throughout all service cycles. Only after all 53 finish
    are departures evaluated. An unsuccessful relocation never changes state.
    """
    seq = [s for s in result["snapshots"] if s["shift"] == shift]
    p = H5Hypothesis(**result["parameters"])
    first = seq[0]
    current = {o["id"]: copy.deepcopy(o) for o in first["home_people"]}
    homes = {o["id"]: copy.deepcopy(o) for o in first["home_people"]}
    events: list[dict[str, Any]] = []
    completed: list[str] = []
    elapsed: float | None = 0.0 if timing else None
    blocked: dict[str, Any] | None = None

    def record(
        kind: str, key: str, batch: str, proof: dict[str, Any], seconds: float | None
    ) -> bool:
        nonlocal elapsed, blocked
        proof.setdefault("people_before", copy.deepcopy(list(current.values())))
        event = dict(
            index=len(events) + 1,
            operation=kind,
            person_id=key,
            batch=batch,
            start_seconds=elapsed,
            duration_seconds=seconds,
            status=proof["status"],
            proof=proof,
        )
        events.append(event)
        if proof["status"] != PASS:
            blocked = dict(
                operation=kind, person_id=key, batch=batch, conflicts=proof.get("conflicts", [])
            )
            event["end_seconds"] = None
            return False
        if elapsed is not None and seconds is not None:
            elapsed += seconds
        event["end_seconds"] = elapsed
        return True

    def move(target: dict[str, Any], batch: str, kind: str) -> bool:
        if current[target["id"]] == target:
            return True
        proof = transfer(
            current, target, result, first, seat_allowance_mm=options.seat_motion_allowance_mm
        )
        seconds = (
            None
            if not timing
            else proof["length_mm"] / timing.walk_mm_per_second
            + sum(
                timing.rise_seconds if v["action"] == "RISE" else timing.sit_seconds
                for v in proof["pose_checks"]
            )
        )
        return record(kind, target["id"], batch, proof, seconds)

    def vacate(target: dict[str, Any], actor: str, batch: str) -> bool:
        occupants = [
            o["id"]
            for k, o in current.items()
            if k != actor
            and any(overlap3(a, b) for a in target["volumes_mm"] for b in o["volumes_mm"])
        ]
        for occupant in occupants:
            candidates = [_retag(h, occupant) for h in homes.values() if h["pose"] == "STANDING"]
            selected = next(
                (
                    c
                    for c in candidates
                    if _empty(c, current, occupant)
                    and not any(
                        overlap3(a, b) for a in c["volumes_mm"] for b in target["volumes_mm"]
                    )
                ),
                None,
            )
            if selected is None:
                return record(
                    "VACATE_SERVICE_AREA",
                    occupant,
                    batch,
                    dict(
                        status="BLOCKED",
                        conflicts=[dict(code="NO_VACANT_REVIEWED_WAITING_POSITION")],
                        service_area_mm=target["bounds_mm"],
                    ),
                    None,
                )
            if not move(selected, batch, "VACATE_SERVICE_AREA"):
                return False
        return True

    entry = portal_audit(result, shift, options, entering=True)
    if entry["status"] != PASS:
        record(
            "ENTRY_ROSTER_OR_GEOMETRY",
            "ALL",
            "ENTRY",
            dict(status="BLOCKED", conflicts=entry.get("conflicts", [])),
            None,
        )
    for proof in entry["moves"]:
        seconds = (
            None
            if not timing
            else proof["length_mm"] / timing.walk_mm_per_second
            + sum(
                timing.rise_seconds if v["action"] == "RISE" else timing.sit_seconds
                for v in proof.get("pose_checks", [])
            )
        )
        if not record("ENTRY_TO_HOME", proof["person_id"], "ENTRY", proof, seconds):
            break
    for s in seq:
        if blocked:
            break
        if validate_use(result["room"], result["inventory"], result["model"], p, s)["conflicts"]:
            record(
                "BATCH_STATIC_AUDIT",
                "ALL",
                s["id"],
                dict(status="BLOCKED", conflicts=s["evaluation"]["conflicts"]),
                None,
            )
            break
        desired = {o["id"]: o for o in s["people"]}
        for a in s["actions"]:
            if not move(desired[a["person_id"]], s["id"], "TO_ASSIGNED_LOCKER"):
                break
        if blocked:
            break
        actual = {**s, "people": list(current.values())}
        validation = validate_use(result["room"], result["inventory"], result["model"], p, actual)
        if not record(
            "LOCKER_OPEN_USE_CLOSE",
            ",".join(a["person_id"] for a in s["actions"]),
            s["id"],
            dict(
                status=PASS if not validation["conflicts"] else "BLOCKED",
                conflicts=validation["conflicts"],
                actions=s["actions"],
                doors=s["doors"],
                people_before=copy.deepcopy(list(current.values())),
            ),
            timing.locker_seconds if timing else None,
        ):
            break
        for a in s["actions"]:
            key = a["person_id"]
            zone = standing_person(
                key, result["model"]["changing_zone"], p.standing_height_mm, "CHANGING_OPERATOR"
            )
            zone["pose"] = "CHANGING_OPERATION_ENVELOPE"
            if not vacate(zone, key, s["id"]):
                break
            body = physical(zone, p)
            if not move(body, s["id"], "LOCKER_TO_CHANGING_ZONE"):
                break
            issues = check_volumes(
                zone["volumes_mm"],
                [v for k, v in current.items() if k != key],
                [*result["inventory"]["cabinet_units"], *result["model"]["benches"]],
                result["model"]["clear"],
                p.clear_height_mm,
            )
            if not record(
                "CHANGE_CLOTHES",
                key,
                s["id"],
                dict(
                    status=PASS if not issues else "BLOCKED",
                    conflicts=issues,
                    activity_volume_mm=zone["volumes_mm"],
                    people_before=copy.deepcopy(list(current.values())),
                ),
                timing.changing_seconds if timing else None,
            ):
                break
            seats = [_retag(h, key) for h in homes.values() if h["pose"] == "SEATED"]
            seat = next((t for t in seats if _empty(t, current, key)), seats[0] if seats else None)
            if seat is None or not vacate(seat, key, s["id"]):
                if seat is None:
                    record(
                        "BENCH_REQUIRED",
                        key,
                        s["id"],
                        dict(status="BLOCKED", conflicts=[dict(code="NO_BENCH_SEAT")]),
                        None,
                    )
                break
            if not move(seat, s["id"], "CHANGING_TO_BENCH_AND_SIT"):
                break
            record(
                "SEATED_USE",
                key,
                s["id"],
                dict(status=PASS, people_before=copy.deepcopy(list(current.values()))),
                timing.seated_seconds if timing else None,
            )
            # Reuse an actually empty reviewed home; no disappearance of another person.
            candidates = [_retag(h, key) for h in homes.values()]
            home = next(
                (c for c in candidates if c["pose"] != "SEATED" and _empty(c, current, key)), None
            )
            if home is None:
                record(
                    "RETURN_AFTER_SEAT",
                    key,
                    s["id"],
                    dict(
                        status="BLOCKED",
                        conflicts=[dict(code="NO_VACANT_REVIEWED_WAITING_POSITION")],
                    ),
                    None,
                )
                break
            if not move(home, s["id"], "RISE_AND_RETURN"):
                break
            completed.append(key)
        if blocked:
            break
    exit_result = None
    if len(set(completed)) == 53 and not blocked:
        exit_result = portal_audit(
            result, shift, options, entering=False, people=list(current.values())
        )
        for proof in exit_result["moves"]:
            seconds = (
                None
                if not timing
                else proof["length_mm"] / timing.walk_mm_per_second
                + sum(
                    timing.rise_seconds if v["action"] == "RISE" else timing.sit_seconds
                    for v in proof.get("pose_checks", [])
                )
            )
            if not record("EXIT_AFTER_SERVICE", proof["person_id"], "EXIT", proof, seconds):
                break
    return dict(
        shift=shift,
        status="SERVICE_CYCLES_VERIFIED_UNDER_HYPOTHESES"
        if len(set(completed)) == 53 and not blocked
        else "BLOCKED",
        complete_service_users=len(set(completed)),
        completed_people=completed,
        required_room_users=53,
        initial_people=len(homes),
        entry=entry["status"],
        remaining_inside=exit_result["final_inside"] if exit_result else len(current),
        events=events,
        blocker=blocked,
        final_people=list(current.values()),
        prefix_seconds=elapsed,
        full_shift_seconds=elapsed if exit_result and exit_result["status"] == PASS else None,
        departure=exit_result or "NOT_EVALUATED_SERVICE_SEQUENCE_INCOMPLETE",
        unvisited_people=sorted(set(homes) - set(completed)),
        protocol="SERIAL_WALKING_AND_CHANGING;53_INSIDE_UNTIL_ALL_SERVICE_COMPLETE",
        alternative_schedules="NOT_PROVEN_IMPOSSIBLE",
    )


def portal_audit(
    result: dict[str, Any],
    shift: int,
    options: OperationHypothesis,
    *,
    entering: bool,
    people: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Audit fill/empty sequence separately unless given a completed live service state."""
    seq = [s for s in result["snapshots"] if s["shift"] == shift]
    reference = {p["id"]: copy.deepcopy(p) for p in (people or seq[0]["home_people"])}
    expected = {
        a["person_id"] for a in result["inventory"]["person_assignments"] if a["shift"] == shift
    }
    if set(reference) != expected or len(reference) != 53:
        return dict(
            shift=shift,
            operation="ENTRY" if entering else "EXIT",
            status="NOT_EVALUATED",
            completed_people=0,
            moves=[],
            conflicts=[dict(code="COMPLETE_53_PERSON_ROSTER_REQUIRED")],
            initial_inside=0 if entering else len(reference),
            final_inside=len(reference),
            accounted_people=len(reference),
        )
    current = {} if entering else copy.deepcopy(reference)
    outside = set(reference) if entering else set()
    portal = result["room"]["portals"][0 if entering else 1]
    moves = []
    for key in sorted(reference, reverse=entering):
        cross = portal_crossing(
            reference[key],
            portal,
            result,
            [v for k, v in current.items() if k != key],
            entering=entering,
        )
        cross["people_before"] = copy.deepcopy(list(current.values()))
        cross["inside_people"] = len(current)
        if cross["status"] != PASS:
            moves.append(cross)
            break
        if entering:
            current[key] = cross["interior_person"]
            outside.remove(key)
            moves.append(cross)
            route = transfer(
                current,
                reference[key],
                result,
                seq[0],
                seat_allowance_mm=options.seat_motion_allowance_mm,
                exited=outside,
            )
            moves.append(route)
        else:
            route = transfer(
                current,
                cross["interior_person"],
                result,
                seq[0],
                seat_allowance_mm=options.seat_motion_allowance_mm,
                exited=outside,
            )
            moves.extend([route, cross] if route["status"] == PASS else [route])
        if route["status"] != PASS:
            break
        if not entering:
            del current[key]
            outside.add(key)
    complete = len(current) == (53 if entering else 0) and all(m["status"] == PASS for m in moves)
    return dict(
        shift=shift,
        operation="ENTRY" if entering else "EXIT",
        status=PASS if complete else "BLOCKED",
        moves=moves,
        completed_people=sum(m["status"] == PASS and "target" in m for m in moves)
        if entering
        else len(outside),
        initial_inside=0 if entering else 53,
        final_inside=len(current),
        accounted_people=53,
        scope="INDEPENDENT_PORTAL_SEQUENCE" if people is None else "LIVE_POST_SERVICE_DEPARTURE",
    )


def timing_bounds(result: dict[str, Any], timing: TimingHypothesis | None) -> dict[str, Any]:
    if timing is None:
        return dict(status="INPUT_REQUIRED", complete_shift_seconds=None)
    timing.checked()
    m = result["metrics"]
    if m["bench_seat_capacity"] <= 0:
        return dict(
            status="CONFIGURATION_NOT_FIT",
            reason="NO_BENCH_SERVICE_CAPACITY",
            complete_shift_seconds=None,
            throughput_satisfied="INPUT_REQUIRED",
        )
    bounds = dict(
        locker=math.ceil(53 / result["parameters"]["front_concurrency"]) * timing.locker_seconds,
        changing=53 * timing.changing_seconds,
        bench=math.ceil(53 / m["bench_seat_capacity"])
        * (timing.seated_seconds + timing.sit_seconds + timing.rise_seconds),
    )
    return dict(
        status="HYPOTHETICAL_NOT_APPROVED",
        parameters=asdict(timing),
        ideal_resource_lower_bounds_seconds=bounds,
        bottleneck=max(bounds, key=lambda k: bounds[k]),
        lower_bound_seconds=max(bounds.values()),
        complete_shift_seconds=None,
        formula=(
            "max(ceil(53/front)*locker,53*changing,ceil(53/seats)*(seat+sit+rise)); "
            "excludes walking, blocking and queues"
        ),
        throughput_satisfied="INPUT_REQUIRED",
    )


def evaluate_operation(
    result: dict[str, Any], options: OperationHypothesis, timing: TimingHypothesis | None = None
) -> dict[str, Any]:
    options.checked()
    if timing:
        timing.checked()
    p = result["parameters"]
    if (
        p["arrangement"] != "SINGLE_SIDE"
        or result["metrics"]["columns"] != 22
        or result["metrics"]["compartments"] != 110
    ):
        raise ValueError("R6_SINGLE_SIDE_22_COLUMN_110_CELL_SCOPE_REQUIRED")
    transitions = []
    for shift in (1, 2):
        ss = [s for s in result["snapshots"] if s["shift"] == shift]
        for a, b in zip(ss, ss[1:], strict=False):
            transitions.append(audit_transition(result, a, b, options))
    return dict(
        version=VERSION,
        project_functional_status="INPUT_REQUIRED",
        source_type="demo",
        validity_status="unverified",
        requires_review=True,
        source_label="HYPOTHETICAL_NOT_APPROVED",
        parameters=asdict(options),
        transitions=transitions,
        expected_transitions=len(result["snapshots"]) - 2,
        verified_transitions=sum(t["status"] == PASS for t in transitions),
        full_shifts=[full_shift(result, s, options, timing) for s in (1, 2)],
        portal_sequences=[
            portal_audit(result, s, options, entering=e) for s in (1, 2) for e in (True, False)
        ],
        activity_sensitivity=[
            activity_check(result, result["snapshots"][0], n) for n in (0, 10, 25, 50, 100)
        ],
        timing=timing_bounds(result, timing),
        native_solves=0,
        scope="Independent pair audit is NOT a single continuous full-service trace",
    )
