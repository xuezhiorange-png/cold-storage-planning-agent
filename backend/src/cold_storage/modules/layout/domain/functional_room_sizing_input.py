"""Versioned, finite preview input; dimensions are hypotheses, never Authority."""

from dataclasses import asdict, dataclass
from typing import Any

VERSION = "functional-room-reverse-sizing-r11-r10@1.0.0"
PROFILES = ("MIXED", "NORTH_ROTATED_SOUTH_NORMAL", "NORTH_NORMAL_SOUTH_ROTATED")


@dataclass(frozen=True)
class RoomUseConditions:
    column_width_mm: int = 400
    column_depth_mm: int = 500
    cabinet_height_mm: int = 1800
    cell_height_mm: int = 300
    plinth_mm: int = 100
    shelf_mm: int = 20
    columns_per_unit: int = 2
    transport_width_mm: int = 450
    transport_depth_mm: int = 650
    body_height_mm: int = 1800
    activity_width_mm: int = 600
    activity_depth_mm: int = 900
    waiting_gap_mm: int = 100
    aisle_required_mm: int = 1200
    finish_mm: int = 20
    installation_gap_mm: int = 20
    unit_gap_mm: int = 20
    operator_standoff_mm: int = 380
    room_door_intrusion_mm: int = 0
    door_kind: str = "OUTWARD_HINGED_90"

    def checked(self) -> None:
        for name, value in asdict(self).items():
            if name == "door_kind":
                continue
            low = (
                0
                if name
                in {
                    "finish_mm",
                    "installation_gap_mm",
                    "unit_gap_mm",
                    "waiting_gap_mm",
                    "room_door_intrusion_mm",
                }
                else 1
            )
            if type(value) is not int or not low <= value <= 6000:
                raise ValueError("BOUNDED_INTEGER_MM_HYPOTHESES_REQUIRED:" + name)
        if self.door_kind not in {"OUTWARD_HINGED_90", "NO_PLAN_INTRUSION"}:
            raise ValueError("EXPLICIT_SUPPORTED_DOOR_HYPOTHESIS_REQUIRED")
        if self.transport_width_mm < 450 or self.transport_depth_mm < 650:
            raise ValueError("DO_NOT_SHRINK_R10_REFERENCE_BODY_TO_PASS")
        if (
            self.activity_width_mm < self.transport_width_mm
            or self.activity_depth_mm < self.transport_depth_mm
        ):
            raise ValueError("ACTIVITY_MUST_CONTAIN_TRANSPORT_BODY")
        if not 1 <= self.columns_per_unit <= 6 or self.aisle_required_mm < 1200:
            raise ValueError("REVIEW_PROFILE_REQUIRES_ORIGINAL_PASSAGE_AND_BOUNDED_CABINET_UNITS")


@dataclass(frozen=True)
class SizingSearch:
    fixed_length_mm: int = 26331
    widths_mm: tuple[int, ...] = (3250, 3300, 3350, 3400, 3440, 3460, 3500, 3600)
    joint_lengths_mm: tuple[int, ...] = (27000, 28000, 30000)
    joint_widths_mm: tuple[int, ...] = (3250, 3500, 3600, 3750, 4050, 4350)
    margin_targets_mm: tuple[int, ...] = (0, 50, 100, 150)
    profiles: tuple[str, ...] = PROFILES
    length_bounds_mm: tuple[int, int] = (26331, 30000)
    width_bounds_mm: tuple[int, int] = (3250, 4500)
    derived_width_checkpoints: bool = True
    change_review_target_mm: int = 50

    def checked(self) -> None:
        if type(self.derived_width_checkpoints) is not bool:
            raise ValueError("BOOLEAN_DERIVED_CHECKPOINT_OPTION_REQUIRED")
        if len(self.length_bounds_mm) != 2 or len(self.width_bounds_mm) != 2:
            raise ValueError("EXPLICIT_SEARCH_BOUNDARIES_REQUIRED")
        for bounds in (self.length_bounds_mm, self.width_bounds_mm):
            if any(type(v) is not int for v in bounds) or not 1 <= bounds[0] <= bounds[1] <= 60000:
                raise ValueError("FINITE_INTEGER_SEARCH_BOUNDARIES_REQUIRED")
        for points, bounds in (
            (self.widths_mm, self.width_bounds_mm),
            (self.joint_widths_mm, self.width_bounds_mm),
            (self.joint_lengths_mm, self.length_bounds_mm),
            ((self.fixed_length_mm,), self.length_bounds_mm),
        ):
            if (
                not points
                or len(points) > 20
                or len(set(points)) != len(points)
                or any(type(v) is not int or not bounds[0] <= v <= bounds[1] for v in points)
            ):
                raise ValueError("UNIQUE_FINITE_SEARCH_POINTS_INSIDE_DECLARED_BOUNDARIES_REQUIRED")
        if (
            not self.profiles
            or len(set(self.profiles)) != len(self.profiles)
            or not set(self.profiles) <= set(PROFILES)
        ):
            raise ValueError("EXPLICIT_SUPPORTED_SPATIAL_PROFILES_REQUIRED")
        if (
            not self.margin_targets_mm
            or len(self.margin_targets_mm) > 5
            or len(set(self.margin_targets_mm)) != len(self.margin_targets_mm)
            or any(type(m) is not int or not 0 <= m <= 150 for m in self.margin_targets_mm)
        ):
            raise ValueError("BOUNDED_HYPOTHETICAL_MARGIN_TARGETS_REQUIRED")
        if (
            type(self.change_review_target_mm) is not int
            or not 0 <= self.change_review_target_mm <= 150
        ):
            raise ValueError("EXPLICIT_HYPOTHETICAL_CHANGE_REVIEW_TARGET_REQUIRED")


def physical_north_width(c: RoomUseConditions, margin: int, waiting_depth: int) -> int:
    """Cross-section for this padded profile, not a complete-room fit proof."""
    return (
        2 * c.finish_mm
        + c.installation_gap_mm
        + margin
        + c.column_depth_mm
        + c.operator_standoff_mm
        + margin
        + c.transport_depth_mm
        + margin
        + c.aisle_required_mm
        + margin
        + margin
        + waiting_depth
    )


def search_points(c: RoomUseConditions, search: SizingSearch) -> list[dict[str, Any]]:
    c.checked()
    search.checked()
    widths = set(search.widths_mm)
    if search.derived_width_checkpoints:
        for m in search.margin_targets_mm:
            for depth in (c.transport_width_mm, c.transport_depth_mm):
                required = physical_north_width(c, m, depth) + m
                rounded = ((required + 49) // 50) * 50
                if search.width_bounds_mm[0] <= rounded <= search.width_bounds_mm[1]:
                    widths.add(rounded)
    points = []
    for length in sorted({search.fixed_length_mm, *search.joint_lengths_mm}):
        for width in sorted(widths if length == search.fixed_length_mm else search.joint_widths_mm):
            for m in sorted(search.margin_targets_mm):
                for profile in search.profiles:
                    points.append(
                        dict(
                            length_mm=length,
                            width_mm=width,
                            margin_mm=m,
                            profile=profile,
                            mode="A_FIXED_LENGTH"
                            if length == search.fixed_length_mm
                            else "B_JOINT_DIMENSIONS",
                        )
                    )
    if len(points) > 512:
        raise ValueError("FINITE_PREVIEW_LIMIT_512_EXCEEDED")
    return points
