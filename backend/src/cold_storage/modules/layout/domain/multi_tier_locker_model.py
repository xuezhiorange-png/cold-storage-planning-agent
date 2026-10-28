"""R4 storage identities: floor units, columns, compartments and design users.

Capacity is deterministic; no dimension, concurrency or hygiene approval follows
from counting compartments. R3's one-person/one-floor-locker model is untouched.
"""

from dataclasses import asdict, dataclass
from typing import Any

from cold_storage.modules.layout.domain.functional_room_fit import integer

VERSION = "multi-tier-locker-model-r11-r4@1.0.0"
TIERS = 5
SCENARIOS = ("INTERNAL_PARTITION", "TWO_COMPARTMENTS")


def storage_demand(
    shift_users: list[int], simultaneous_users: int, scenario: str
) -> dict[str, Any]:
    if len(shift_users) != 2 or scenario not in SCENARIOS:
        raise ValueError("TWO_SHIFTS_AND_EXPLICIT_SEPARATION_SCENARIO_REQUIRED")
    for count in shift_users:
        integer(count, 1)
        if count > 256:
            raise ValueError("BOUNDED_REVIEW_REQUIRED")
    integer(simultaneous_users, 1)
    if simultaneous_users != max(shift_users):
        raise ValueError("ROOM_OCCUPANCY_MUST_PRESERVE_PROJECT_DESIGN_BASIS")
    factor = 1 if scenario == "INTERNAL_PARTITION" else 2
    required = [n * factor for n in shift_users]
    columns = [(n + TIERS - 1) // TIERS for n in required]
    capacity = [n * TIERS for n in columns]
    return dict(
        version=VERSION,
        scenario=scenario,
        shift_users=shift_users,
        simultaneous_room_users=simultaneous_users,
        compartments_per_person=factor,
        tiers_per_column=TIERS,
        required_compartments_per_shift=required,
        columns_per_shift=columns,
        total_columns=sum(columns),
        capacity_per_shift=capacity,
        total_capacity=sum(capacity),
        spare_per_shift=[c - n for c, n in zip(capacity, required, strict=True)],
        physical_cabinet_unit_count="INPUT_REQUIRED",
        cabinet_front_concurrent_users="INPUT_REQUIRED",
        separation_satisfied="INPUT_REQUIRED",
        source_label="ENGINEERING_DERIVED",
        review_status="CAPACITY_ARITHMETIC_ONLY",
        formulas=[
            "required_compartments_i = design_users_i * compartments_per_person",
            "columns_i = ceil(required_compartments_i / 5); no cross-shift spare borrowing",
            "capacity_i = 5 * columns_i",
            "cabinet floor units depend on the selected manufacturer's column grouping",
        ],
        units="people; columns; independently assigned compartments",
        assumptions=["Dedicated column allocation for each shift in this working model"],
        warnings=["300mm compartment height is a reference, not approved cabinet dimensions"],
    )


@dataclass(frozen=True)
class MultiTierHypothesis:
    """Explicit sensitivity parameters; never a catalogue of reviewed facts."""

    arrangement: str = "OPPOSED"
    column_width_mm: int = 400
    column_depth_mm: int = 500
    cabinet_height_mm: int = 1800
    compartment_clear_height_mm: int = 300
    plinth_mm: int = 100
    shelf_mm: int = 20
    columns_per_unit: int = 1
    aisle_mm: int = 1200
    front_clearance_mm: int = 600
    person_width_mm: int = 400
    person_depth_mm: int = 600
    front_concurrent_users: int | None = None
    cabinet_door_sweep_mm: int | None = None
    room_door_sweep_mm: int | None = None
    bench_count: int = 0
    bench_width_mm: int = 1200
    bench_depth_mm: int = 400
    bench_operation_mm: int = 500
    finish_inset_mm: int = 0
    clear_height_mm: int = 3000
    reach_low_mm: int = 100
    reach_high_mm: int = 1700

    def checked(self) -> None:
        if self.arrangement not in {"OPPOSED", "SINGLE_SIDE"}:
            raise ValueError("EXPLICIT_ROW_TEMPLATE_REQUIRED")
        optional = {"front_concurrent_users", "cabinet_door_sweep_mm", "room_door_sweep_mm"}
        zero = {
            "plinth_mm",
            "shelf_mm",
            "bench_count",
            "finish_inset_mm",
            "reach_low_mm",
            "cabinet_door_sweep_mm",
            "room_door_sweep_mm",
        }
        for name, value in asdict(self).items():
            if name == "arrangement" or value is None and name in optional:
                continue
            integer(value, 0 if name in zero else 1)
            if value > 60000:
                raise ValueError("BOUNDED_HYPOTHESIS_REQUIRED")
        if self.columns_per_unit > 6 or self.bench_count > 10:
            raise ValueError("BOUNDED_HYPOTHESIS_REQUIRED")
        if self.reach_low_mm >= self.reach_high_mm:
            raise ValueError("EXPLICIT_REACH_INTERVAL_REQUIRED")


def storage_inventory(demand: dict[str, Any], p: MultiTierHypothesis) -> dict[str, Any]:
    """Enumerate all objects and spare compartments, including 3-D elevations.

    Unit aggregation is an explicit hypothetical manufacturing choice. A short last
    unit is identified as such, not silently treated as an available catalogue item.
    """
    p.checked()
    units: list[dict[str, Any]] = []
    columns: list[dict[str, Any]] = []
    compartments: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    for shift, count in enumerate(demand["columns_per_shift"], 1):
        shift_cells = []
        for start in range(0, count, p.columns_per_unit):
            n = min(p.columns_per_unit, count - start)
            unit_id = f"S{shift}-U{start // p.columns_per_unit + 1:02}"
            unit = dict(
                id=unit_id,
                shift=shift,
                role="CABINET_UNIT",
                column_ids=[],
                dimensions_mm=[n * p.column_width_mm, p.column_depth_mm, p.cabinet_height_mm],
                partial_unit=n != p.columns_per_unit,
                source_label="HYPOTHETICAL_NOT_APPROVED",
            )
            units.append(unit)
            for j in range(n):
                column_id = f"S{shift}-C{start + j + 1:02}"
                unit["column_ids"].append(column_id)
                column: dict[str, Any] = dict(
                    id=column_id,
                    unit_id=unit_id,
                    shift=shift,
                    offset_x_mm=j * p.column_width_mm,
                    dimensions_mm=[p.column_width_mm, p.column_depth_mm, p.cabinet_height_mm],
                    compartment_ids=[],
                )
                columns.append(column)
                for level in range(TIERS):
                    cell_id = f"{column_id}-T{level + 1}"
                    z0 = p.plinth_mm + level * (p.compartment_clear_height_mm + p.shelf_mm)
                    cell = dict(
                        id=cell_id,
                        column_id=column_id,
                        unit_id=unit_id,
                        shift=shift,
                        tier=level + 1,
                        elevation_bounds_mm=[
                            j * p.column_width_mm,
                            z0,
                            (j + 1) * p.column_width_mm,
                            z0 + p.compartment_clear_height_mm,
                        ],
                        independent_door_id=cell_id + "-door",
                        assigned_person_id=None,
                        purpose="SPARE",
                        internal_partition_status="INPUT_REQUIRED",
                    )
                    column["compartment_ids"].append(cell_id)
                    compartments.append(cell)
                    shift_cells.append(cell)
        factor = demand["compartments_per_person"]
        for number in range(demand["shift_users"][shift - 1]):
            person_id = f"S{shift}-P{number + 1:03}"
            selected = shift_cells[number * factor : (number + 1) * factor]
            for idx, cell in enumerate(selected):
                cell["assigned_person_id"] = person_id
                cell["purpose"] = (
                    "WORK_AND_PRIVATE_PARTITION_REQUIRED"
                    if factor == 1
                    else ("WORK_CLOTHES", "PRIVATE_CLOTHES")[idx]
                )
            assignments.append(
                dict(
                    person_id=person_id,
                    shift=shift,
                    compartment_ids=[c["id"] for c in selected],
                    identity_kind="DESIGN_SLOT_NOT_EMPLOYEE_ROSTER",
                )
            )
    return dict(
        cabinet_units=units,
        vertical_columns=columns,
        compartments=compartments,
        person_assignments=assignments,
        hypothetical_floor_unit_count=len(units),
        source_label="HYPOTHETICAL_NOT_APPROVED",
    )


def service_waves(
    inventory: dict[str, Any], shift: int, concurrency: int
) -> list[list[dict[str, str]]]:
    """One operator per column at a time; others remain among the 53 room users.

    Each assigned compartment gets a service action. No duration, queue throughput,
    transition-path or ergonomics approval is inferred from this finite schedule.
    """
    integer(concurrency, 1)
    pending = [
        dict(person_id=c["assigned_person_id"], compartment_id=c["id"], column_id=c["column_id"])
        for c in inventory["compartments"]
        if c["shift"] == shift and c["assigned_person_id"]
    ]
    waves = []
    while pending:
        wave: list[dict[str, str]] = []
        people: set[str] = set()
        columns: set[str] = set()
        for action in pending:
            if action["person_id"] in people or action["column_id"] in columns:
                continue
            wave.append(action)
            people.add(action["person_id"])
            columns.add(action["column_id"])
            if len(wave) == concurrency:
                break
        waves.append(wave)
        pending = [a for a in pending if a not in wave]
    return waves
