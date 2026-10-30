"""Complete selected cabinets; physical identity never depends on a shift.

All dimensions are integer mm. Outer dimensions are Owner-selected NOMINAL
dimensions, not measured or supplier-reviewed dimensions. Door placement is a
separate explicit sensitivity hypothesis and never an internal-clear-size proof.
"""

from dataclasses import asdict, dataclass
from typing import Any

from cold_storage.modules.layout.domain.multi_tier_locker_layout import inventory_conflicts

VERSION = "h5-complete-ten-door-locker-r11-r14@1.0.0"


@dataclass(frozen=True)
class DoorSensitivity:
    hinges: str
    angle_degrees: int = 90
    leaf_width_mm: int = 400
    leaf_height_mm: int = 320
    leaf_thickness_mm: int = 15
    left_frame_mm: int = 12
    bottom_mm: int = 100
    tier_gap_mm: int = 20

    def checked(self) -> None:
        if self.hinges not in {"ALL_LEFT", "MIRRORED"} or self.angle_degrees != 90:
            raise ValueError(
                "UNSUPPORTED_PHYSICAL_CONFIGURATION:EXPLICIT_90_DEGREE_SENSITIVITY_ONLY"
            )
        for key, value in asdict(self).items():
            if key == "hinges":
                continue
            if type(value) is not int or not 0 <= value <= 1800:
                raise ValueError("INTEGER_MM_DOOR_SENSITIVITY_REQUIRED")
        if min(self.leaf_width_mm, self.leaf_height_mm, self.leaf_thickness_mm) <= 0:
            raise ValueError("POSITIVE_DOOR_LEAF_REQUIRED")
        if self.left_frame_mm + self.leaf_width_mm > 425:
            raise ValueError("DOOR_LEAF_OUTSIDE_CONDITIONAL_COLUMN_FRONT")
        if self.bottom_mm + 5 * self.leaf_height_mm + 4 * self.tier_gap_mm > 1800:
            raise ValueError("FIVE_DOOR_FACES_EXCEED_SELECTED_CABINET_HEIGHT")


def complete_inventory(demand: dict[str, Any], door: DoorSensitivity) -> dict[str, Any]:
    door.checked()
    if (
        demand["shift_users"] != [53, 53]
        or demand["columns_per_shift"] != [11, 11]
        or demand["total_columns"] != 22
        or demand["total_capacity"] != 110
        or demand["compartments_per_person"] != 1
        or demand["simultaneous_room_users"] != 53
    ):
        raise ValueError("FIXED_53_53_106_22_110_PROJECT_BASIS_REQUIRED")
    units: list[dict[str, Any]] = []
    columns: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    for number in range(11):
        uid = f"U{number + 1:02}"
        unit: dict[str, Any] = dict(
            id=uid,
            shift=None,
            role="COMPLETE_TEN_DOOR_CABINET",
            dimensions_mm=[850, 390, 1800],
            dimensions_basis="OWNER_SELECTED_NOMINAL_NOT_SUPPLIER_REVIEWED",
            partial_unit=False,
            column_ids=[],
            allocated_shifts=[],
        )
        units.append(unit)
        for side in range(2):
            index = number * 2 + side
            shift = 1 if index < 11 else 2
            cid = uid + ("-L" if side == 0 else "-R")
            unit["column_ids"].append(cid)
            unit["allocated_shifts"] = sorted(set([*unit["allocated_shifts"], shift]))
            col: dict[str, Any] = dict(
                id=cid,
                unit_id=uid,
                shift=shift,
                offset_x_mm=side * 425,
                dimensions_mm=[425, 390, 1800],
                pitch_basis="HYPOTHETICAL_EQUAL_DIVISION_NOT_NET_WIDTH",
                compartment_ids=[],
            )
            columns.append(col)
            for tier in range(1, 6):
                cellid = f"{cid}-T{tier}"
                z = door.bottom_mm + (tier - 1) * (door.leaf_height_mm + door.tier_gap_mm)
                col["compartment_ids"].append(cellid)
                cells.append(
                    dict(
                        id=cellid,
                        column_id=cid,
                        unit_id=uid,
                        shift=shift,
                        tier=tier,
                        elevation_bounds_mm=[
                            side * 425,
                            z,
                            (side + 1) * 425,
                            z + door.leaf_height_mm,
                        ],
                        elevation_scope="CONDITIONAL_DOOR_FACE_INTERVAL_NOT_NET_CELL_HEIGHT",
                        net_width_mm=None,
                        net_depth_mm=None,
                        net_height_mm=None,
                        net_dimensions_status="INPUT_REQUIRED",
                        independent_door_id=cellid + "-DOOR",
                        assigned_person_id=None,
                        purpose="SPARE",
                        internal_partition_status="INPUT_REQUIRED",
                    )
                )
    for shift in (1, 2):
        owned = [c for c in cells if c["shift"] == shift]
        for index, cell in enumerate(owned[:53], 1):
            pid = f"S{shift}-P{index:03}"
            cell.update(
                assigned_person_id=pid, purpose="WORK_AND_PRIVATE_SEPARATION_INPUT_REQUIRED"
            )
            assignments.append(
                dict(
                    person_id=pid,
                    shift=shift,
                    compartment_ids=[cell["id"]],
                    identity_kind="DESIGN_SLOT_NOT_EMPLOYEE_ROSTER",
                )
            )
    inv = dict(
        cabinet_units=units,
        vertical_columns=columns,
        compartments=cells,
        person_assignments=assignments,
        floor_unit_count=11,
        source_label="OWNER_SELECTED_NOMINAL_WITH_EXPLICIT_UNAPPROVED_GEOMETRY",
    )
    errors = complete_inventory_conflicts(inv, demand)
    if errors:
        raise ValueError("COMPLETE_CABINET_INVENTORY_INVALID:" + ",".join(errors))
    return inv


def complete_inventory_conflicts(inv: dict[str, Any], demand: dict[str, Any]) -> list[str]:
    errors = inventory_conflicts(inv, demand)
    units = inv["cabinet_units"]
    if len(units) != 11 or any(
        u["dimensions_mm"] != [850, 390, 1800]
        or u["partial_unit"]
        or len(u["column_ids"]) != 2
        or u["shift"] is not None
        for u in units
    ):
        errors.append("ELEVEN_COMPLETE_PHYSICAL_UNITS_NOT_SHIFT_SPLIT_OR_HALF_PRODUCTS_REQUIRED")
    for shift in (1, 2):
        cells = [c for c in inv["compartments"] if c["shift"] == shift]
        if len(cells) != 55 or sum(c["assigned_person_id"] is None for c in cells) != 2:
            errors.append("EACH_SHIFT_REQUIRES_55_EXCLUSIVE_CELLS_WITH_TWO_SPARES")
    return sorted(set(errors))


def actual_door_records(inv: dict[str, Any]) -> list[dict[str, Any]]:
    """No nominal door label is promoted to a verified clear opening or hardware."""
    return [
        dict(
            id=c["independent_door_id"],
            compartment_id=c["id"],
            unit_id=c["unit_id"],
            nominal_label_mm=[400, 360, 320],
            nominal_label_semantics="OWNER_REPORTED_IMAGE_LABEL_NOT_INTERNAL_CLEAR_DIMENSIONS",
            actual_hinge=None,
            actual_angle_degrees=None,
            actual_leaf_thickness_mm=None,
            actual_front_frame_mm=None,
            actual_sweep=None,
            actual_status="INPUT_REQUIRED",
        )
        for c in inv["compartments"]
    ]
