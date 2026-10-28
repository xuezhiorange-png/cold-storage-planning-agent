"""Finite, non-Native cabinet-front groups with the original physical checks.

Pairwise activity separation only prunes combinations. Every chosen group still
passes the complete original static/door/Portal checks and R7 activity checks.
"""

import copy
import itertools
from dataclasses import asdict, dataclass, replace
from typing import Any

from cold_storage.modules.layout.domain.changing_operation_motion import PASS
from cold_storage.modules.layout.domain.functional_room_fit import covered, intersection, rectangle
from cold_storage.modules.layout.domain.multi_tier_locker_layout import inventory_conflicts
from cold_storage.modules.layout.domain.multi_tier_locker_model import (
    MultiTierHypothesis,
    storage_inventory,
)
from cold_storage.modules.layout.domain.practical_changing_layout import (
    _place,
    _snapshot,
    validate_use,
)
from cold_storage.modules.layout.domain.standing_changing_layout import StandingParameters
from cold_storage.modules.layout.domain.standing_changing_operation import activity_proof

VERSION = "h5-cabinet-front-interleaved-r11-r8@1.0.0"


@dataclass(frozen=True)
class FrontParameters:
    requested_concurrency: int = 4
    activity_width_mm: int = 600
    activity_depth_mm: int = 900
    person_width_mm: int = 400
    person_depth_mm: int = 600
    person_gap_mm: int = 20
    columns_per_unit: int = 2
    unit_gap_mm: int = 20
    grouping: str = "INTERLEAVED"
    room_door_intrusion_mm: int = 0

    def standing(self) -> StandingParameters:
        for key, value in asdict(self).items():
            if key == "grouping":
                continue
            low = 0 if key in {"unit_gap_mm", "person_gap_mm", "room_door_intrusion_mm"} else 1
            if type(value) is not int or not low <= value <= 6000:
                raise ValueError("BOUNDED_INTEGER_FRONT_HYPOTHESIS_REQUIRED")
        if self.grouping not in {"INTERLEAVED", "CONTIGUOUS_REFERENCE"}:
            raise ValueError("EXPLICIT_FRONT_SCHEDULING_MODE_REQUIRED")
        if not 1 <= self.requested_concurrency <= 11 or not 1 <= self.columns_per_unit <= 6:
            raise ValueError("BOUNDED_CONCURRENCY_AND_PHYSICAL_GROUPING_REQUIRED")
        # A test comparison may enlarge the R7 reference body, never shrink it to fit.
        # This is a comparison-input rule, not a P1 or building design constraint.
        if self.person_width_mm < 400 or self.person_depth_mm < 600:
            raise ValueError("DO_NOT_SHRINK_REFERENCE_BODY_TO_CREATE_A_PASS")
        p = StandingParameters(
            mode="CABINET_FRONT",
            front_concurrency=self.requested_concurrency,
            activity_width_mm=self.activity_width_mm,
            activity_depth_mm=self.activity_depth_mm,
            person_width_mm=self.person_width_mm,
            person_depth_mm=self.person_depth_mm,
            person_gap_mm=self.person_gap_mm,
            room_door_intrusion_mm=self.room_door_intrusion_mm,
        )
        p.checked()
        return p


def group_proof(
    g: dict[str, Any], shift: int, actions: list[dict[str, str]], p: StandingParameters, key: str
) -> dict[str, Any]:
    from cold_storage.modules.layout.domain.practical_changing_layout import H5Hypothesis

    hp = H5Hypothesis(**g["parameters"])
    s = _snapshot(g["room"], g["inventory"], g["model"], hp, shift, actions, key)
    s["evaluation"] = validate_use(g["room"], g["inventory"], g["model"], hp, s)
    current = {o["id"]: o for o in s["people"]}
    proof = activity_proof(g, s, current, [a["person_id"] for a in actions], p)
    s["front_activity_evaluation"] = proof
    s["group_verified"] = not s["evaluation"]["conflicts"] and proof["status"] == PASS
    xs = [current[a["person_id"]]["bounds_mm"][0] for a in actions]
    s["front_group_spaces"] = dict(
        people=[a["person_id"] for a in actions],
        columns=[a["column_id"] for a in actions],
        actual_minimum_column_x_separation_mm=min(
            (abs(a - b) for i, a in enumerate(xs) for b in xs[i + 1 :]), default=None
        ),
        required_activity_width_mm=p.activity_width_mm,
        required_activity_depth_mm=p.activity_depth_mm,
        activity_volume_count=len(proof["activity_volumes"]),
    )
    return s


def _schedule(
    g: dict[str, Any], shift: int, cfg: FrontParameters
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    p = cfg.standing()
    columns = {c["id"]: c for c in g["inventory"]["vertical_columns"] if c["shift"] == shift}
    queues: dict[str, list[dict[str, str]]] = {key: [] for key in columns}
    for c in g["inventory"]["compartments"]:
        if c["shift"] == shift and c["assigned_person_id"]:
            queues[c["column_id"]].append(
                dict(
                    person_id=c["assigned_person_id"],
                    compartment_id=c["id"],
                    column_id=c["column_id"],
                )
            )
    counts = dict.fromkeys(columns, 0)
    batches: list[dict[str, Any]] = []
    attempts = 0
    rejected = []
    while any(queues.values()):
        # Least served columns first, then physical x. No historical coordinates or seed.
        keys = sorted(
            (k for k in columns if queues[k]),
            key=lambda k: (counts[k], columns[k]["bounds_mm"][0], k),
        )
        size = min(cfg.requested_concurrency, len(keys))
        chosen = None
        if cfg.grouping == "CONTIGUOUS_REFERENCE":
            actions = [
                queues[k][0] for k in sorted(keys, key=lambda k: columns[k]["bounds_mm"][0])[:size]
            ]
            chosen = group_proof(g, shift, actions, p, f"S{shift}-B{len(batches) + 1:02}")
            attempts += 1
            # Retain this negative control's rejected witness; do not silently repair it.
        else:
            # Physical x separation is a necessary pairwise test, not acceptance.
            for n in range(size, 0, -1):
                for group in itertools.combinations(keys, n):
                    if any(
                        abs(columns[a]["bounds_mm"][0] - columns[b]["bounds_mm"][0])
                        < p.activity_width_mm
                        for a, b in itertools.combinations(group, 2)
                    ):
                        continue
                    actions = [queues[k][0] for k in group]
                    s = group_proof(g, shift, actions, p, f"S{shift}-B{len(batches) + 1:02}")
                    attempts += 1
                    if s["group_verified"]:
                        chosen = s
                        break
                    rejected.append(
                        dict(
                            people=[a["person_id"] for a in actions],
                            conflicts=s["evaluation"]["conflicts"]
                            + s["front_activity_evaluation"]["conflicts"],
                        )
                    )
                if chosen:
                    break
        if chosen is None:
            return batches, dict(
                status="NO_REVIEWED_GROUP_IN_THIS_TEMPLATE",
                checks=attempts,
                rejected_groups=rejected,
                remaining_users=sum(map(len, queues.values())),
            )
        batches.append(chosen)
        if not chosen["group_verified"]:
            rejected.append(
                dict(
                    people=[a["person_id"] for a in chosen["actions"]],
                    conflicts=chosen["evaluation"]["conflicts"]
                    + chosen["front_activity_evaluation"]["conflicts"],
                )
            )
        for action in chosen["actions"]:
            queues[action["column_id"]].pop(0)
            counts[action["column_id"]] += 1
    return batches, dict(
        status="ALL_53_ASSIGNED" if not rejected else "REFERENCE_ASSIGNED_WITH_REJECTED_GROUPS",
        checks=attempts,
        rejected_groups=rejected,
        remaining_users=0,
    )


def front_geometry(
    room: dict[str, Any], demand: dict[str, Any], cfg: FrontParameters
) -> dict[str, Any]:
    p = cfg.standing()
    if (
        room["local_bounds_mm"] != [0, 0, 26331, 3250]
        or demand["shift_users"] != [53, 53]
        or demand["simultaneous_room_users"] != 53
        or demand["total_columns"] != 22
        or demand["total_capacity"] != 110
    ):
        raise ValueError("FROZEN_H5_53_USERS_22_COLUMNS_REQUIRED")
    hp = replace(
        p.physical_parameters(), columns_per_unit=cfg.columns_per_unit, unit_gap_mm=cfg.unit_gap_mm
    )
    inv = storage_inventory(
        demand,
        MultiTierHypothesis(
            column_width_mm=hp.column_width_mm,
            column_depth_mm=hp.column_depth_mm,
            cabinet_height_mm=hp.cabinet_height_mm,
            compartment_clear_height_mm=hp.cell_height_mm,
            plinth_mm=hp.plinth_mm,
            shelf_mm=hp.shelf_mm,
            columns_per_unit=hp.columns_per_unit,
        ),
    )
    model = _place(room, inv, hp)
    model.update(changing_zone=None, homes=[])
    ref = _snapshot(room, inv, model, hp, 1, [], "NETWORK")
    blockers = [*ref["aisles"], model["landing"], *[u["bounds_mm"] for u in inv["cabinet_units"]]]
    # All waiting positions are outside the existing 1200mm aisle and cabinet front.
    for y in [
        model["main_y"] + hp.aisle_mm - hp.aisle_mm // 2,
        model["main_y"] - hp.aisle_mm // 2 - hp.person_depth_mm,
    ]:
        for x in range(
            model["waiting_start_x"],
            room["local_bounds_mm"][2],
            hp.person_width_mm + hp.person_gap_mm,
        ):
            b = [x, y, x + hp.person_width_mm, y + hp.person_depth_mm]
            if covered(rectangle(b), [rectangle(model["clear"])]) and not any(
                intersection(rectangle(b), rectangle(q)) for q in blockers
            ):
                model["homes"].append(dict(bounds_mm=b, pose="STANDING"))
                if len(model["homes"]) == 53:
                    break
        if len(model["homes"]) == 53:
            break
    g: dict[str, Any] = dict(
        version=VERSION,
        room=copy.deepcopy(room),
        demand=copy.deepcopy(demand),
        parameters=asdict(hp),
        standing_parameters=asdict(p),
        front_parameters=asdict(cfg),
        inventory=inv,
        model=model,
        snapshots=[],
        hierarchy_failures=inventory_conflicts(inv, demand),
        source_type="demo",
        validity_status="unverified",
        requires_review=True,
        project_functional_status="INPUT_REQUIRED",
        native_solves=0,
    )
    base = _snapshot(room, inv, model, hp, 1, [], "ALL_WAITING")
    g["waiting_evaluation"] = validate_use(room, inv, model, hp, base)
    g["waiting_snapshots"] = {
        str(s): _snapshot(room, inv, model, hp, s, [], "ALL_WAITING") for s in (1, 2)
    }
    diagnostics = []
    if not g["waiting_evaluation"]["conflicts"] and not g["hierarchy_failures"]:
        for shift in (1, 2):
            batches, diag = _schedule(g, shift, cfg)
            g["snapshots"].extend(batches)
            diagnostics.append(dict(diag, shift=shift))
    g["schedule_diagnostics"] = diagnostics
    first = next(iter(inv["vertical_columns"]))
    # Existing branch aisle is the front-depth boundary, not the whole room width.
    front_depth = base["branch_y"] - hp.aisle_mm // 2 - first["bounds_mm"][3]
    g["metrics"] = dict(
        columns=22,
        compartments=110,
        bench_count=0,
        seat_count=0,
        home_count=len(model["homes"]),
        reserved_aisle_mm=hp.aisle_mm,
        batches=len(g["snapshots"]),
        static_pass_count=sum(not s["evaluation"]["conflicts"] for s in g["snapshots"]),
        verified_front_groups=sum(s["group_verified"] for s in g["snapshots"]),
        activity_width_required_mm=p.activity_width_mm,
        activity_depth_required_mm=p.activity_depth_mm,
        closed_door_front_depth_available_mm=front_depth,
        front_depth_margin_mm=front_depth - p.activity_depth_mm,
        minimum_active_column_x_separation_mm=p.activity_width_mm,
        waiting_positions_missing=max(0, 53 - len(model["homes"])),
        home_generation_limit=53,
        cabinet_run_length_mm=max(u["bounds_mm"][2] for u in inv["cabinet_units"])
        - min(u["bounds_mm"][0] for u in inv["cabinet_units"]),
        waiting_start_x_mm=model["waiting_start_x"],
        cabinet_footprint_mm2=sum(
            u["dimensions_mm"][0] * u["dimensions_mm"][1] for u in inv["cabinet_units"]
        ),
    )
    return g
