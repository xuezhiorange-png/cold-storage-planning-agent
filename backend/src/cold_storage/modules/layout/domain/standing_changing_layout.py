"""R7 finite standing templates, reusing original cabinet/Portal/aisle checks.

No bench is constructed. No unique changing station is reserved. Body and activity
sizes are separate hypotheses, not an engineering Authority or a placement search.
"""

import copy
from dataclasses import asdict, dataclass
from typing import Any

from cold_storage.modules.layout.domain.functional_room_fit import covered, intersection, rectangle
from cold_storage.modules.layout.domain.multi_tier_locker_layout import inventory_conflicts
from cold_storage.modules.layout.domain.multi_tier_locker_model import (
    MultiTierHypothesis,
    service_waves,
    storage_inventory,
)
from cold_storage.modules.layout.domain.practical_changing_layout import (
    H5Hypothesis,
    _place,
    _snapshot,
    validate_use,
)

VERSION = "h5-no-bench-standing-r11-r7@1.0.0"


@dataclass(frozen=True)
class StandingParameters:
    mode: str = "DISTRIBUTED"
    front_concurrency: int = 4
    person_width_mm: int = 400
    person_depth_mm: int = 600
    person_gap_mm: int = 20
    standing_height_mm: int = 1800
    activity_width_mm: int = 420
    activity_depth_mm: int = 700
    activity_height_mm: int = 1800
    column_width_mm: int = 400
    column_depth_mm: int = 500
    aisle_mm: int = 1200
    room_door_intrusion_mm: int = 0
    door_kind: str = "OUTWARD_HINGED_90"

    def checked(self) -> None:
        if self.mode not in {"CABINET_FRONT", "DISTRIBUTED"}:
            raise ValueError("EXPLICIT_UNAPPROVED_STANDING_MODE_REQUIRED")
        if self.door_kind not in {"OUTWARD_HINGED_90", "NO_PLAN_INTRUSION"}:
            raise ValueError("EXPLICIT_DOOR_HYPOTHESIS_REQUIRED")
        for k, v in asdict(self).items():
            if k in {"mode", "door_kind"}:
                continue
            minimum = 0 if k in {"person_gap_mm", "room_door_intrusion_mm"} else 1
            if type(v) is not int or not minimum <= v <= 6000:
                raise ValueError("BOUNDED_INTEGER_GEOMETRY_HYPOTHESIS_REQUIRED")
        if self.front_concurrency > 11:
            raise ValueError("AT_MOST_ELEVEN_INDEPENDENT_COLUMNS_PER_SHIFT")
        if (
            self.activity_width_mm < self.person_width_mm
            or self.activity_depth_mm < self.person_depth_mm
            or self.activity_height_mm < self.standing_height_mm
        ):
            raise ValueError("ACTIVITY_MUST_CONTAIN_TRANSPORT_BODY")

    def physical_parameters(self) -> H5Hypothesis:
        """Adapter to existing pure geometry functions, not R5's bench protocol.

        R7 validates its own fields above. R5's public evaluator still requires its
        historic bench input and is not called or changed by this adapter.
        """
        self.checked()
        keys = {
            "front_concurrency",
            "person_width_mm",
            "person_depth_mm",
            "person_gap_mm",
            "standing_height_mm",
            "column_width_mm",
            "column_depth_mm",
            "aisle_mm",
            "room_door_intrusion_mm",
            "door_kind",
        }
        return H5Hypothesis(bench_count=0, **{k: v for k, v in asdict(self).items() if k in keys})


def standing_geometry(
    room: dict[str, Any], demand: dict[str, Any], params: StandingParameters
) -> dict[str, Any]:
    p = params.physical_parameters()
    if (
        room["local_bounds_mm"] != [0, 0, 26331, 3250]
        or demand["shift_users"] != [53, 53]
        or demand["simultaneous_room_users"] != 53
        or demand["total_columns"] != 22
        or demand["total_capacity"] != 110
    ):
        raise ValueError("FROZEN_H5_AND_22_COLUMN_DESIGN_REQUIRED")
    inv = storage_inventory(
        demand,
        MultiTierHypothesis(
            column_width_mm=p.column_width_mm,
            column_depth_mm=p.column_depth_mm,
            cabinet_height_mm=p.cabinet_height_mm,
            compartment_clear_height_mm=p.cell_height_mm,
            plinth_mm=p.plinth_mm,
            shelf_mm=p.shelf_mm,
            columns_per_unit=p.columns_per_unit,
        ),
    )
    model = _place(room, inv, p)
    # Only the cabinet/aisle placement is reused. The old single changing station
    # and seat-based home allocation have no meaning in R7.
    model["changing_zone"] = None
    model["homes"] = []
    reference = _snapshot(room, inv, model, p, 1, [], "NETWORK")
    blockers = [
        *reference["aisles"],
        model["landing"],
        *[u["bounds_mm"] for u in inv["cabinet_units"]],
    ]
    for y in [
        model["main_y"] + p.aisle_mm - p.aisle_mm // 2,
        model["main_y"] - p.aisle_mm // 2 - p.person_depth_mm,
    ]:
        for x in range(
            model["waiting_start_x"],
            room["local_bounds_mm"][2],
            p.person_width_mm + p.person_gap_mm,
        ):
            box = [x, y, x + p.person_width_mm, y + p.person_depth_mm]
            if covered(rectangle(box), [rectangle(model["clear"])]) and not any(
                intersection(rectangle(box), rectangle(b)) for b in blockers
            ):
                model["homes"].append(dict(bounds_mm=box, pose="STANDING"))
                if len(model["homes"]) == 53:
                    break
        if len(model["homes"]) == 53:
            break
    snapshots = []
    for shift in (1, 2):
        for i, actions in enumerate(service_waves(inv, shift, p.front_concurrency), 1):
            s = _snapshot(room, inv, model, p, shift, actions, f"S{shift}-W{i:02}")
            s["evaluation"] = validate_use(room, inv, model, p, s)
            snapshots.append(s)
    return dict(
        version=VERSION,
        room=copy.deepcopy(room),
        demand=copy.deepcopy(demand),
        standing_parameters=asdict(params),
        parameters=asdict(p),
        inventory=inv,
        model=model,
        snapshots=snapshots,
        hierarchy_failures=inventory_conflicts(inv, demand),
        metrics=dict(
            columns=22,
            compartments=110,
            bench_count=0,
            seat_count=0,
            home_count=len(model["homes"]),
            batches=len(snapshots),
            static_pass_count=sum(not s["evaluation"]["conflicts"] for s in snapshots),
            cabinet_footprint_mm2=sum(
                u["dimensions_mm"][0] * u["dimensions_mm"][1] for u in inv["cabinet_units"]
            ),
            reserved_aisle_mm=p.aisle_mm,
        ),
        source_type="demo",
        validity_status="unverified",
        requires_review=True,
        project_functional_status="INPUT_REQUIRED",
        native_solves=0,
    )
