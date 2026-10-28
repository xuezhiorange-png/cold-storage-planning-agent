"""R3-only per-shift use proof on top of the unchanged R11 functional oracle."""

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.layout.domain.functional_room_fit import (
    BODY_ROLES,
    STATES,
    covered,
    intersection,
    rectangle,
)

VERSION = "r3-shift-functional-validation@1.0.0"
PLAN_FIELD = "r3_shift_operation_plan"
EXCLUSIVE_SPACES = frozenset(
    {"PERSON", "CHAIR", "OPERATION", "MAINTENANCE", "BUFFER", "DOOR_OPERATION"}
)


def _at_front(person: tuple[int, int, int, int], locker: Mapping[str, Any]) -> bool:
    x, y, r, t = rectangle(locker["bounds_mm"])
    a, b, c, d = person
    return bool(
        locker.get("front") == "N"
        and b == t
        and min(c, r) > max(a, x)
        or locker.get("front") == "S"
        and d == y
        and min(c, r) > max(a, x)
        or locker.get("front") == "E"
        and a == r
        and min(d, t) > max(b, y)
        or locker.get("front") == "W"
        and c == x
        and min(d, t) > max(b, y)
    )


def validate_shift_use(
    room: Mapping[str, Any],
    witness: Mapping[str, Any],
    legacy: Mapping[str, Any],
    shift: int,
    locker_counts: list[int],
    plan: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Prove the supplied shift separately; people may use their own operation zone.

    Every declared AISLE/route envelope must remain unoccupied. Opening motions
    need an explicit, reviewed exclusion model; inactive lockers are not silently
    assumed closed. These checks reject this witness, not all room arrangements.
    """
    missing: list[str] = []
    conflicts: list[dict[str, Any]] = []
    states: dict[str, Any] = {}
    result = dict(
        version=VERSION,
        shift=shift,
        missing_inputs=missing,
        conflicts=conflicts,
        state_results=states,
        status="INPUT_REQUIRED",
    )
    if legacy["functional_status"] == "INPUT_REQUIRED":
        missing.append("COMPLETE_REVIEWED_R11_INPUTS_AND_WITNESS_REQUIRED")
        return result
    if not isinstance(plan, Mapping) or set(plan) != set(STATES):
        missing.append("REVIEWED_FOUR_STATE_OPERATION_PLAN_REQUIRED")
        return result

    def fail(code: str, state: str, *items: str) -> None:
        conflicts.append(dict(code=code, state=state, components=list(items)))

    try:
        components = witness["components"]
        lockers = {c["id"]: c for c in components if c["role"] == "LOCKER"}
        owned = {key for key, c in lockers.items() if c.get("shift") == shift}
        if len(lockers) != sum(locker_counts) or any(
            sum(c.get("shift") == i for c in lockers.values()) != n
            for i, n in enumerate(locker_counts, 1)
        ):
            fail("R3_INDEPENDENT_SHIFT_LOCKER_ALLOCATION_MISMATCH", "ALL")
        portal_ids = {p["id"] for p in room["portals"]}
        if len(portal_ids) != 2:
            missing.append("TWO_ORIGINAL_PORTALS_REQUIRED")
        for state in STATES:
            config = plan[state]
            if not isinstance(config, Mapping):
                missing.append(state + ":reviewed_operation_plan")
                continue
            active_list = config.get("active_locker_ids")
            if not isinstance(active_list, list) or not all(
                isinstance(v, str) for v in active_list
            ):
                missing.append(state + ":active_locker_ids")
                continue
            active = set(active_list)
            if len(active) != len(active_list) or not active <= set(lockers):
                fail("OPERATION_PLAN_LOCKER_IDENTITIES_INVALID", state)
            if state in {"USE", "SHIFT_CHANGE"} and not owned <= active:
                fail("ALL_CURRENT_SHIFT_LOCKERS_MUST_BE_ACTIVE", state)
            if active != set(lockers) and config.get("inactive_lockers_closed") is not True:
                missing.append(state + ":reviewed_inactive_locker_closure")
            if (
                not isinstance(config.get("door_motion_basis"), str)
                or not config["door_motion_basis"].strip()
            ):
                missing.append(state + ":reviewed_locker_door_motion_basis")
            doors = config.get("locker_door_motion")
            if not isinstance(doors, Mapping) or set(doors) != active:
                missing.append(state + ":reviewed_door_motion_for_each_active_locker")
                continue
            objects = [c for c in components if state in c["states"]]
            people = [c for c in objects if c["role"] == "PERSON"]
            if state in {"USE", "SHIFT_CHANGE"}:
                served = [c.get("serves") for c in people]
                if (
                    len(people) != locker_counts[shift - 1]
                    or set(served) != owned
                    or len(set(served)) != len(served)
                    or any(c.get("shift") != shift for c in people)
                ):
                    fail("SHIFT_PERSON_LOCKER_BIJECTION_REQUIRED", state)
            for person in people:
                target = lockers.get(person.get("serves"))
                if (
                    target is None
                    or target.get("shift") != shift
                    or not _at_front(rectangle(person["bounds_mm"]), target)
                ):
                    fail("PERSON_NOT_AT_OWN_SHIFT_LOCKER_FRONT", state, person["id"])
            prior = legacy["state_results"].get(state)
            if not prior:
                missing.append(state + ":original_r11_validation")
                continue
            route_rows = prior["route_results"]
            reached = {p for r in route_rows if r["valid"] for p in r["portal_ids"]}
            if not portal_ids <= reached or not all(r["valid"] for r in route_rows):
                fail("BOTH_ORIGINAL_PORTALS_MUST_BE_REACHABLE", state)
            net = [
                (c["id"], rectangle(c["bounds_mm"]), "AISLE")
                for c in objects
                if c["role"] == "AISLE"
            ]
            net += [
                (r["id"], rectangle(env), "ROUTE") for r in route_rows for env in r["envelopes_mm"]
            ]
            operations = [
                r
                for r in prior["operation_clearance_rectangles"]
                if r["serves"] not in lockers or r["serves"] in active
            ]
            for c in objects:
                if c["role"] not in EXCLUSIVE_SPACES:
                    continue
                bounds = rectangle(c["bounds_mm"])
                for identifier, reserved, kind in net:
                    if intersection(bounds, reserved):
                        fail("OCCUPIED_SPACE_INTRUDES_NET_" + kind, state, c["id"], identifier)
                if c["role"] == "PERSON":
                    for op in operations:
                        if op["serves"] != c.get("serves") and intersection(
                            bounds, rectangle(op["bounds_mm"])
                        ):
                            fail(
                                "PERSON_CONFLICTS_WITH_OTHER_ACTIVE_OPERATION",
                                state,
                                c["id"],
                                op["serves"],
                            )
                    for other in objects:
                        if (
                            other["role"] in EXCLUSIVE_SPACES - {"PERSON"}
                            and other.get("serves") != c.get("serves")
                            and intersection(bounds, rectangle(other["bounds_mm"]))
                        ):
                            fail(
                                "PERSON_CONFLICTS_WITH_OTHER_FUNCTIONAL_SPACE",
                                state,
                                c["id"],
                                other["id"],
                            )
                elif c["role"] in {"DOOR_OPERATION", "OPERATION", "MAINTENANCE"}:
                    for op in operations:
                        if op["serves"] != c.get("serves") and intersection(
                            bounds, rectangle(op["bounds_mm"])
                        ):
                            fail(
                                "EXCLUSIVE_SPACE_CONFLICTS_ACTIVE_OPERATION",
                                state,
                                c["id"],
                                op["serves"],
                            )
            for operation in operations:
                for identifier, reserved, kind in net:
                    if intersection(rectangle(operation["bounds_mm"]), reserved):
                        fail(
                            "ACTIVE_OPERATION_INTRUDES_NET_" + kind,
                            state,
                            operation["serves"],
                            identifier,
                        )
            for locker_id, motion in doors.items():
                mode, regions = motion.get("mode"), motion.get("exclusions_mm")
                if (
                    mode not in {"NO_FLOOR_SWEEP", "EXCLUSION_RECTANGLES"}
                    or not isinstance(regions, list)
                    or (mode == "NO_FLOOR_SWEEP" and regions)
                    or (mode == "EXCLUSION_RECTANGLES" and not regions)
                ):
                    missing.append(state + ":explicit_door_exclusion:" + locker_id)
                    continue
                for raw in regions:
                    sweep = rectangle(raw)
                    if not covered(sweep, [rectangle(legacy["finished_clear_bounds_mm"])]):
                        fail("LOCKER_DOOR_SWEEP_OUTSIDE_FINISHED_ROOM", state, locker_id)
                    for identifier, reserved, kind in net:
                        if intersection(sweep, reserved):
                            fail(
                                "LOCKER_DOOR_SWEEP_INTRUDES_NET_" + kind,
                                state,
                                locker_id,
                                identifier,
                            )
                    for c in objects:
                        if (
                            c["id"] != locker_id
                            and c["role"] in BODY_ROLES | EXCLUSIVE_SPACES
                            and intersection(sweep, rectangle(c["bounds_mm"]))
                        ):
                            fail("LOCKER_DOOR_SWEEP_CONFLICT", state, locker_id, c["id"])
                    for op in operations:
                        if op["serves"] != locker_id and intersection(
                            sweep, rectangle(op["bounds_mm"])
                        ):
                            fail(
                                "LOCKER_DOOR_SWEEP_CONFLICTS_OTHER_OPERATION",
                                state,
                                locker_id,
                                op["serves"],
                            )
            states[state] = dict(
                people_count=len(people),
                owned_locker_ids=sorted(owned),
                person_to_locker={c["id"]: c.get("serves") for c in people},
                active_operation_locker_ids=sorted(active),
                closed_locker_ids=sorted(set(lockers) - active),
                proven_portal_ids=sorted(reached),
                net_passage_regions=[dict(id=k, bounds_mm=r, kind=t) for k, r, t in net],
                route_results=route_rows,
            )
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        missing.append("COMPLETE_R3_SHIFT_WITNESS_REQUIRED:" + str(exc))
    result["status"] = (
        "INPUT_REQUIRED"
        if missing
        else "CONFIGURATION_NOT_FIT"
        if conflicts or legacy["functional_status"] != "CONDITIONAL_FIT"
        else "SHIFT_USE_VALIDATED"
    )
    return result
