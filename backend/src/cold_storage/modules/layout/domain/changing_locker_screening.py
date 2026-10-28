"""Necessary row tests and explicit hypothetical witnesses, never a placement solver."""

from dataclasses import asdict, dataclass
from typing import Any

from cold_storage.modules.layout.domain.functional_room_fit import (
    STATES,
    integer,
    intersection,
    rectangle,
)

VERSION = "changing-locker-screening@1.1.0"


def _box(values: list[int]) -> tuple[int, int, int, int]:
    return values[0], values[1], values[2], values[3]


@dataclass(frozen=True)
class HypotheticalLockerParameters:
    """Demonstration values only; never produce reviewed BasisValue objects."""

    arrangement: str = "DOUBLE_SIDE"
    locker_width_mm: int = 400
    locker_depth_mm: int = 500
    locker_height_mm: int = 1800
    aisle_mm: int = 1200
    front_clearance_mm: int = 600
    end_space_mm: int = 0
    first_row_count: int = 53
    person_width_mm: int = 400
    person_depth_mm: int = 600
    bench_count: int = 0
    bench_width_mm: int = 1200
    bench_depth_mm: int = 400
    bench_height_mm: int = 450
    bench_operation_mm: int = 500
    finish_inset_mm: int = 0
    active_shift: int = 1

    def checked(self) -> None:
        if self.arrangement not in {"SINGLE_SIDE", "DOUBLE_SIDE"}:
            raise ValueError("EXPLICIT_ROW_TEMPLATE_REQUIRED")
        for name, value in asdict(self).items():
            if name == "arrangement":
                continue
            integer(value, 0 if name in {"bench_count", "end_space_mm", "finish_inset_mm"} else 1)
            if value > 60000:
                raise ValueError("BOUNDED_DEMONSTRATION_REQUIRED")
        if self.bench_count > 10:
            raise ValueError("BOUNDED_BENCH_COUNT_REQUIRED")
        if self.active_shift not in (1, 2):
            raise ValueError("EXPLICIT_ACTIVE_SHIFT_REQUIRED")


def _free_spans(length: int, blocked: list[tuple[int, int]], end: int) -> list[tuple[int, int]]:
    spans = []
    cursor = end
    for lo, hi in sorted(blocked):
        lo, hi = max(end, lo), min(length - end, hi)
        if lo >= hi:
            continue
        if cursor < lo:
            spans.append((cursor, lo))
        cursor = max(cursor, hi)
    if cursor < length - end:
        spans.append((cursor, length - end))
    return spans


def screen_locker_rows(
    room: dict[str, Any],
    count: int,
    simultaneous_users: int,
    parameters: HypotheticalLockerParameters,
) -> dict[str, Any]:
    """Check this long-wall row template; failure says nothing about other templates.

    Physical P2 bounds are an optimistic outer envelope, not finished clear dimensions.
    Body placement reserves actual portal gaps. Interior clear zones are hypotheses.
    No hypothetical result can become CONDITIONAL_FIT.
    """
    parameters.checked()
    integer(count, 1)
    integer(simultaneous_users, 1)
    if count > 512 or simultaneous_users > count or parameters.first_row_count > count:
        raise ValueError("BOUNDED_EXPLICIT_COUNTS_REQUIRED")
    p = parameters
    x0, y0, x1, y1 = rectangle(room["local_bounds_mm"])
    horizontal = x1 - x0 >= y1 - y0
    length, width = (x1 - x0, y1 - y0) if horizontal else (y1 - y0, x1 - x0)
    inset = p.finish_inset_mm
    length, width = length - 2 * inset, width - 2 * inset
    if length <= 0 or width <= 0:
        raise ValueError("HYPOTHETICAL_FINISH_REMOVES_ROOM")
    row_count = 1 if p.arrangement == "SINGLE_SIDE" else 2
    ideal_per_row = count if row_count == 1 else max(p.first_row_count, count - p.first_row_count)
    required_length = ideal_per_row * p.locker_width_mm
    required_width = row_count * p.locker_depth_mm + p.aisle_mm
    reasons = []
    if required_length > length:
        reasons.append("IDEAL_CONTINUOUS_ROW_LENGTH_SHORTFALL")
    if required_width > width:
        reasons.append("CABINETS_AND_CLEAR_AISLE_WIDTH_SHORTFALL")

    def xy(rect: list[int]) -> list[int]:
        a, b, c, d = rect
        return (
            [x0 + inset + a, y0 + inset + b, x0 + inset + c, y0 + inset + d]
            if horizontal
            else [x0 + inset + b, y0 + inset + a, x0 + inset + d, y0 + inset + c]
        )

    portal_envelopes: list[dict[str, Any]] = []
    blocked: list[list[tuple[int, int]]] = [[] for _ in range(row_count)]
    for portal in room["portals"]:
        a, b = portal["segment_mm"]
        ax, ay = a[0] - x0, a[1] - y0
        bx, by = b[0] - x0, b[1] - y0
        if not horizontal:
            ax, ay, bx, by = ay, ax, by, bx
        ax, ay, bx, by = ax - inset, ay - inset, bx - inset, by - inset
        if ay == by and ay in (-inset, width + inset):
            row = 0 if 2 * ay < width else 1
            if row < row_count:
                blocked[row].append((min(ax, bx), max(ax, bx)))
        # An inward passage strip, NOT a fabricated door swing or full route proof.
        (a, b), cw = portal["segment_mm"], portal["clear_width_mm"]
        if a[0] == b[0]:
            west = a[0] == x0
            env = [
                x0 if west else x1 - p.aisle_mm,
                min(a[1], b[1]),
                x0 + p.aisle_mm if west else x1,
                max(a[1], b[1]),
            ]
        else:
            south = a[1] == y0
            env = [
                min(a[0], b[0]),
                y0 if south else y1 - p.aisle_mm,
                max(a[0], b[0]),
                y0 + p.aisle_mm if south else y1,
            ]
        portal_envelopes.append(dict(id=portal["id"], bounds_mm=env, clear_width_mm=cw))

    components: list[dict[str, Any]] = []
    actual_row_counts = []
    targets = [count] if row_count == 1 else [p.first_row_count, count - p.first_row_count]
    for row, target in enumerate(targets):
        placed = 0
        for lo, hi in _free_spans(length, blocked[row], p.end_space_mm):
            for index in range((hi - lo) // p.locker_width_mm):
                if placed == target:
                    break
                identifier = len(components) + 1
                pos = lo + index * p.locker_width_mm
                y = 0 if row == 0 else width - p.locker_depth_mm
                components.append(
                    dict(
                        id=f"locker-{identifier:03}",
                        role="LOCKER",
                        bounds_mm=xy([pos, y, pos + p.locker_width_mm, y + p.locker_depth_mm]),
                        row=row + 1,
                        shift=1 if identifier <= count // 2 else 2,
                        states=list(STATES),
                    )
                )
                placed += 1
        actual_row_counts.append(placed)
    lockers = list(components)
    if len(lockers) < count:
        reasons.append("PORTAL_SEGMENTED_ROW_POSITIONS_INSUFFICIENT")
    active_lockers = [c for c in lockers if c["shift"] == p.active_shift]
    if len(active_lockers) < simultaneous_users:
        reasons.append("ACTIVE_SHIFT_LOCKER_OR_PERSON_POSITIONS_INSUFFICIENT")
    for i, locker in enumerate(active_lockers[:simultaneous_users]):
        r = locker["bounds_mm"]
        if horizontal:
            y = r[3] if locker["row"] == 1 else r[1] - p.person_depth_mm
            rect = [r[0], y, r[0] + p.person_width_mm, y + p.person_depth_mm]
        else:
            x = r[2] if locker["row"] == 1 else r[0] - p.person_depth_mm
            rect = [x, r[1], x + p.person_depth_mm, r[1] + p.person_width_mm]
        components.append(
            dict(
                id=f"person-{i + 1:03}",
                role="PERSON",
                bounds_mm=rect,
                states=["USE", "SHIFT_CHANGE"],
                serves=locker["id"],
            )
        )
    aisle_start = p.locker_depth_mm + max(p.front_clearance_mm, p.person_depth_mm)
    aisle_end = width - (p.locker_depth_mm + p.front_clearance_mm if row_count == 2 else 0)
    operation_width_required = (
        aisle_start
        + p.aisle_mm
        + (p.locker_depth_mm + p.front_clearance_mm if row_count == 2 else 0)
    )
    if aisle_end - aisle_start < p.aisle_mm:
        reasons.append("PERSON_OPERATION_AND_CLEAR_AISLE_SHORTFALL")
    if aisle_end > aisle_start:
        components.append(
            dict(
                id="hypothetical-clear-aisle",
                role="AISLE",
                bounds_mm=xy([0, aisle_start, length, aisle_end]),
                states=list(STATES),
            )
        )
    for i in range(p.bench_count):
        pos = p.end_space_mm + i * (p.bench_width_mm + p.bench_operation_mm)
        top = (width + p.bench_depth_mm) // 2
        components.append(
            dict(
                id=f"bench-{i + 1}",
                role="BENCH",
                bounds_mm=xy(
                    [
                        pos,
                        (width - p.bench_depth_mm) // 2,
                        pos + p.bench_width_mm,
                        (width + p.bench_depth_mm) // 2,
                    ]
                ),
                states=list(STATES),
            )
        )
        components.append(
            dict(
                id=f"bench-operation-{i + 1}",
                role="BENCH_OPERATION",
                bounds_mm=xy([pos, top, pos + p.bench_width_mm, top + p.bench_operation_mm]),
                states=list(STATES),
            )
        )
    conflicts = []
    bounds = (x0 + inset, y0 + inset, x1 - inset, y1 - inset)
    for c in components:
        r = c["bounds_mm"]
        if r[0] < bounds[0] or r[1] < bounds[1] or r[2] > bounds[2] or r[3] > bounds[3]:
            conflicts.append(
                dict(code="COMPONENT_OUTSIDE_HYPOTHETICAL_CLEAR_BOUNDS", components=[c["id"]])
            )
        if c["role"] != "AISLE":
            for portal in portal_envelopes:
                if intersection(_box(r), _box(portal["bounds_mm"])):
                    conflicts.append(
                        dict(
                            code="ACTUAL_PORTAL_PASSAGE_OBSTRUCTED",
                            components=[c["id"], portal["id"]],
                        )
                    )
    for i, a in enumerate(components):
        for b in components[i + 1 :]:
            if a["role"] == b["role"] == "AISLE" or not set(a["states"]) & set(b["states"]):
                continue
            if intersection(_box(a["bounds_mm"]), _box(b["bounds_mm"])):
                conflicts.append(
                    dict(code="SPECIFIED_TEMPLATE_SPACE_OVERLAP", components=[a["id"], b["id"]])
                )
    return dict(
        version=VERSION,
        source_type="demo",
        validity_status="unverified",
        requires_review=True,
        source_label="HYPOTHETICAL_NOT_APPROVED",
        parameters=asdict(p),
        available_length_mm=length,
        available_width_mm=width,
        required_length_mm=required_length,
        required_width_mm=required_width,
        operation_width_required_mm=operation_width_required,
        ideal_single_side_capacity=length // p.locker_width_mm,
        ideal_remaining_aisle_mm=width - row_count * p.locker_depth_mm,
        necessary_condition_status="CONFIGURATION_NOT_FIT"
        if required_length > length or required_width > width
        else "NECESSARY_CONDITIONS_MET_ONLY",
        specified_template_status="CONFIGURATION_NOT_FIT"
        if reasons or conflicts
        else "NO_LISTED_TEMPLATE_CONFLICT_FOUND_NOT_FUNCTIONAL_APPROVAL",
        reasons=reasons,
        components=components,
        portal_envelopes=portal_envelopes,
        placed_lockers=len(lockers),
        placed_person_spaces=sum(c["role"] == "PERSON" for c in components),
        placed_benches=sum(c["role"] == "BENCH" for c in components),
        unplaced_lockers=count - len(lockers),
        actual_row_counts=actual_row_counts,
        conflicts=conflicts,
        full_route_connectivity="NOT_EVALUATED_REVIEWED_WITNESS_REQUIRED",
        door_operation="INPUT_REQUIRED",
        height_validation="INPUT_REQUIRED_CONFIRMED_CLEAR_HEIGHT",
        clean_separation="INPUT_REQUIRED",
        functional_status="INPUT_REQUIRED",
        formulas=[
            "single required length=N*locker_width",
            "opposed required length=max(first_row_count,N-first_row_count)*locker_width",
            "opposed required width=2*locker_depth+clear_aisle",
            "segmented row capacity=sum(floor(free_segment/locker_width))",
        ],
        assumptions=[
            "Specified long-wall row template only; no assertion about unchecked layouts",
            "Physical rectangle used as optimistic envelope; finished clear bounds unknown",
            "Portal segments are archived facts; passage depth is a hypothesis, "
            "not a swing envelope",
            "No real internal route, hygiene or four-state approval from this screening",
        ],
    )
