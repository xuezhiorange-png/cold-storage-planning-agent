"""Versioned, project-independent structural placement families for P1A.

This module binds existing canonical zone identities to the already frozen
functional groups.  It neither derives new rooms nor changes engineering
dimensions.  The family is a deterministic search policy, not a site template
or an engineering hard constraint.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError

IDENTITY: Final = "structural-composition-family@1.0.0"
SKELETON_IDENTITY: Final = "structural-skeleton@1.0.0"
LINEAR_PROCESS_BAND: Final = "LINEAR_PROCESS_BAND"
CENTRAL_PROCESS_HUB: Final = "CENTRAL_PROCESS_HUB"

RAW_SIDE_GROUP: Final = "RAW_SIDE_GROUP"
PROCESSING_CORE_GROUP: Final = "PROCESSING_CORE_GROUP"
FINISHED_SIDE_GROUP: Final = "FINISHED_SIDE_GROUP"
SUPPORT_GROUP: Final = "SUPPORT_GROUP"
PERSONNEL_GROUP: Final = "PERSONNEL_GROUP"

FUNCTIONAL_GROUPS: Final = {
    RAW_SIDE_GROUP: ("raw_fruit_buffer", "primary_precooling_room"),
    PROCESSING_CORE_GROUP: ("sorting_packaging_room", "coating_room"),
    FINISHED_SIDE_GROUP: (
        "secondary_precooling_room",
        "finished_goods_room",
        "shipping_channel",
    ),
    SUPPORT_GROUP: (
        "packaging_material_storage",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
    ),
    PERSONNEL_GROUP: ("office", "changing_room"),
}

MAIN_PROCESS_ZONE_CODES: Final = (
    "raw_fruit_buffer",
    "primary_precooling_room",
    "sorting_packaging_room",
    "secondary_precooling_room",
    "coating_room",
    "finished_goods_room",
    "shipping_channel",
)
# Skeleton identity includes every main-process rectangle, including the
# shipping interface, as required by the constructive candidate contract.
MAIN_PROCESS_SKELETON_ZONE_CODES: Final = MAIN_PROCESS_ZONE_CODES
MAIN_PROCESS_PREDECESSOR: Final = {
    "primary_precooling_room": "raw_fruit_buffer",
    "sorting_packaging_room": "primary_precooling_room",
    "secondary_precooling_room": "sorting_packaging_room",
    "coating_room": "secondary_precooling_room",
    "finished_goods_room": "coating_room",
    "shipping_channel": "finished_goods_room",
}

# These are placement references only.  MUST adjacency continues to come from
# process_graph(); a missing structural edge falls back to the general P2C
# anchor family and is still judged by the existing P2D authorities.
STRUCTURAL_ANCHOR_REFERENCES: Final = {
    "primary_precooling_room": ("raw_fruit_buffer",),
    "sorting_packaging_room": ("primary_precooling_room", "raw_fruit_buffer"),
    "secondary_precooling_room": ("sorting_packaging_room", "coating_room"),
    "coating_room": ("sorting_packaging_room",),
    "finished_goods_room": ("coating_room", "secondary_precooling_room"),
    "shipping_channel": ("finished_goods_room",),
    "packaging_material_storage": ("sorting_packaging_room",),
    # Every support branch remains attached to the process core or its local
    # packaging store; secondary/frozen rooms cannot extend a support-only tail.
    "secondary_fruit_buffer": (
        "sorting_packaging_room",
        "packaging_material_storage",
        "frozen_fruit_room",
    ),
    "frozen_fruit_room": ("sorting_packaging_room", "packaging_material_storage"),
    "changing_room": ("sorting_packaging_room",),
    # The office remains a personnel-group zone, but its search anchors may
    # align its outer edge with the production mass so the peripheral group
    # does not become a detached appendage.
    "office": ("changing_room", "shipping_channel", "coating_room"),
}


@dataclass(frozen=True)
class StructuralCompositionFamilyV1:
    """A deterministic abstract placement family selected from input facts."""

    family: str
    dominant_axis: str
    dominant_direction: str
    generation_reason: str

    def __post_init__(self) -> None:
        if self.family not in {LINEAR_PROCESS_BAND, CENTRAL_PROCESS_HUB}:
            raise LayoutAuthorityError("STRUCTURAL_COMPOSITION_FAMILY_INVALID")
        if self.dominant_axis not in {"X", "Y"}:
            raise LayoutAuthorityError("STRUCTURAL_COMPOSITION_AXIS_INVALID")
        if self.dominant_direction not in {"POSITIVE", "NEGATIVE", "UNRESOLVED"}:
            raise LayoutAuthorityError("STRUCTURAL_COMPOSITION_DIRECTION_INVALID")
        if not self.generation_reason:
            raise LayoutAuthorityError("STRUCTURAL_COMPOSITION_REASON_REQUIRED")

    def to_dict(self) -> dict[str, str]:
        return {
            "identity": IDENTITY,
            "family": self.family,
            "dominant_axis": self.dominant_axis,
            "dominant_direction": self.dominant_direction,
            "generation_reason": self.generation_reason,
        }


@dataclass(frozen=True)
class StructuralSkeletonV1:
    """A versioned spatial search contract for the three functional bands.

    The skeleton contains ordering and attachment policy only. Exact band
    envelopes are derived from candidate zone rectangles, never from golden
    drawings or copied project coordinates.
    """

    family: StructuralCompositionFamilyV1
    ordering_axis: str
    ordered_groups: tuple[str, str, str]
    core_zone_codes: tuple[str, ...]
    support_root_zone_codes: tuple[str, ...]
    personnel_zone_codes: tuple[str, ...]
    root_anchor_candidates: tuple[tuple[Decimal, Decimal, int], ...] = ()

    def __post_init__(self) -> None:
        if self.ordering_axis not in {"X", "Y"}:
            raise LayoutAuthorityError("STRUCTURAL_SKELETON_AXIS_INVALID")
        if self.ordered_groups != (RAW_SIDE_GROUP, PROCESSING_CORE_GROUP, FINISHED_SIDE_GROUP):
            raise LayoutAuthorityError("STRUCTURAL_SKELETON_GROUP_ORDER_INVALID")
        if not self.core_zone_codes or not self.support_root_zone_codes:
            raise LayoutAuthorityError("STRUCTURAL_SKELETON_ROLE_REQUIRED")

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": SKELETON_IDENTITY,
            "family": self.family.to_dict(),
            "ordering_axis": self.ordering_axis,
            "ordered_groups": list(self.ordered_groups),
            "raw_group_band": {
                "group": RAW_SIDE_GROUP,
                "position": "FIRST",
                "axis": self.ordering_axis,
            },
            "processing_core_envelope": {
                "group": PROCESSING_CORE_GROUP,
                "role": "CORE",
                "axis": self.ordering_axis,
            },
            "finished_group_band": {
                "group": FINISHED_SIDE_GROUP,
                "position": "AFTER_CORE_OR_OPPOSITE_SIDE",
                "axis": self.ordering_axis,
                "terminal_zone_codes": ["finished_goods_room", "shipping_channel"],
                "transition_zone_codes": ["secondary_precooling_room"],
            },
            "support_attachment_region": {
                "placement": "FACES_PERPENDICULAR_TO_PROCESS_BAND_AXIS",
                "process_core_root": "sorting_packaging_room",
                "local_support_root": "packaging_material_storage",
                "maximum_support_chain_depth": 2,
            },
            "personnel_peripheral_region": "BUILDABLE_PERIMETER_AFTER_MAIN_SKELETON",
            "core_zone_codes": list(self.core_zone_codes),
            "support_root_zone_codes": list(self.support_root_zone_codes),
            "personnel_zone_codes": list(self.personnel_zone_codes),
            "root_anchor_candidates": [
                {"x": str(x), "y": str(y), "rotation_deg": rotation}
                for x, y, rotation in self.root_anchor_candidates
            ],
            "authority": "CANDIDATE_SEARCH_POLICY_ONLY",
        }


def structural_skeleton_candidates(
    site_geometry: Mapping[str, object],
    zone_codes: Sequence[str],
    zone_authorities: Mapping[str, Mapping[str, object]] | None = None,
) -> tuple[StructuralSkeletonV1, ...]:
    """Build the three deterministic search lanes from current site facts."""
    groups = bind_functional_groups(zone_codes)
    core_codes = tuple(code for code in FUNCTIONAL_GROUPS[PROCESSING_CORE_GROUP] if code in groups)
    support_roots = tuple(
        code for code in ("sorting_packaging_room", "packaging_material_storage") if code in groups
    )
    personnel_codes = tuple(code for code in FUNCTIONAL_GROUPS[PERSONNEL_GROUP] if code in groups)
    skeletons: list[StructuralSkeletonV1] = []
    for family in composition_family_candidates(site_geometry):
        # A linear band runs on the dominant site axis. A central hub keeps the
        # processing core between raw and finished bands on its transverse axis.
        ordering_axis = family.dominant_axis
        if family.family == CENTRAL_PROCESS_HUB:
            ordering_axis = "Y" if family.dominant_axis == "X" else "X"
        skeletons.append(
            StructuralSkeletonV1(
                family=family,
                ordering_axis=ordering_axis,
                ordered_groups=(RAW_SIDE_GROUP, PROCESSING_CORE_GROUP, FINISHED_SIDE_GROUP),
                core_zone_codes=core_codes,
                support_root_zone_codes=support_roots,
                personnel_zone_codes=personnel_codes,
                root_anchor_candidates=(
                    _skeleton_root_anchor_candidates(
                        site_geometry,
                        family,
                        ordering_axis,
                        zone_authorities,
                    )
                    if zone_authorities is not None
                    else ()
                ),
            )
        )
    return tuple(skeletons)


def _skeleton_root_anchor_candidates(
    site_geometry: Mapping[str, object],
    family: StructuralCompositionFamilyV1,
    ordering_axis: str,
    zone_authorities: Mapping[str, Mapping[str, object]],
) -> tuple[tuple[Decimal, Decimal, int], ...]:
    """Derive process-core root anchors from this site's bounds and P1 sizes."""
    site = site_geometry.get("site")
    boundary = site.get("effective_buildable_boundary") if isinstance(site, Mapping) else None
    points = boundary.get("points") if isinstance(boundary, Mapping) else None
    if not isinstance(points, list) or not points:
        raise LayoutAuthorityError("STRUCTURAL_SITE_GEOMETRY_INVALID")
    xs = tuple(
        _decimal(point.get("x"), field="boundary.x")
        for point in points
        if isinstance(point, Mapping)
    )
    ys = tuple(
        _decimal(point.get("y"), field="boundary.y")
        for point in points
        if isinstance(point, Mapping)
    )
    if len(xs) != len(points) or len(ys) != len(points):
        raise LayoutAuthorityError("STRUCTURAL_SITE_GEOMETRY_INVALID")
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    def dimensions(zone_code: str) -> tuple[Decimal, Decimal]:
        authority = zone_authorities.get(zone_code)
        geometry = authority.get("geometry") if isinstance(authority, Mapping) else None
        if not isinstance(geometry, Mapping):
            raise LayoutAuthorityError(
                "STRUCTURAL_ZONE_DIMENSIONS_UNAVAILABLE", zone_code=zone_code
            )
        return (
            _decimal(geometry.get("width_m"), field=f"{zone_code}.width_m"),
            _decimal(geometry.get("depth_m"), field=f"{zone_code}.depth_m"),
        )

    sorting_width, sorting_depth = dimensions("sorting_packaging_room")
    primary_width, primary_depth = dimensions("primary_precooling_room")
    raw_width, raw_depth = dimensions("raw_fruit_buffer")
    room_variants = (
        (sorting_width, sorting_depth, 0),
        (sorting_depth, sorting_width, 90),
    )
    primary_variants = ((primary_width, primary_depth), (primary_depth, primary_width))
    raw_cross_axis_extents = (raw_width, raw_depth)
    directions = (
        (family.dominant_direction,)
        if family.family == LINEAR_PROCESS_BAND
        else ("POSITIVE", "NEGATIVE")
    )
    anchors: set[tuple[Decimal, Decimal, int]] = set()
    for room_width, room_depth, rotation in room_variants:
        room_axis_extent = room_width if ordering_axis == "X" else room_depth
        for primary_actual_width, primary_actual_depth in primary_variants:
            primary_axis_extent = (
                primary_actual_width if ordering_axis == "X" else primary_actual_depth
            )
            for raw_cross_extent in raw_cross_axis_extents:
                # The orthogonal raw-side group consumes only its transverse
                # projection; primary remains the upstream process interface.
                x = min_x + (raw_cross_extent if ordering_axis == "Y" else Decimal(0))
                y = min_y + (raw_cross_extent if ordering_axis == "X" else Decimal(0))
                for direction in directions:
                    if ordering_axis == "X":
                        x = (
                            min_x + primary_axis_extent
                            if direction == "POSITIVE"
                            else max_x - primary_axis_extent - room_axis_extent
                        )
                    else:
                        y = (
                            min_y + primary_axis_extent
                            if direction == "POSITIVE"
                            else max_y - primary_axis_extent - room_axis_extent
                        )
                    anchors.add((x, y, rotation))
    return tuple(sorted(anchors, key=lambda row: (row[1], row[0], row[2])))


def functional_group_for_zone(zone_code: str) -> str:
    """Return the frozen semantic group for a known canonical zone."""
    matches = [group for group, members in FUNCTIONAL_GROUPS.items() if zone_code in members]
    if len(matches) != 1:
        raise LayoutAuthorityError("STRUCTURAL_ZONE_GROUP_UNMAPPED", zone_code=zone_code)
    return matches[0]


def bind_functional_groups(zone_codes: Sequence[str]) -> dict[str, str]:
    """Bind exactly the supplied existing zone identities; never invent roles."""
    if len(zone_codes) != len(set(zone_codes)):
        raise LayoutAuthorityError("STRUCTURAL_ZONE_SET_INVALID")
    return {code: functional_group_for_zone(code) for code in sorted(zone_codes)}


def structural_anchor_references(
    zone_code: str, placed_zone_codes: Sequence[str]
) -> tuple[str, ...]:
    """Return deterministic already-placed group/process anchors for a zone."""
    placed = set(placed_zone_codes)
    return tuple(
        reference
        for reference in STRUCTURAL_ANCHOR_REFERENCES.get(zone_code, ())
        if reference in placed
    )


def _decimal(value: object, *, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise LayoutAuthorityError("STRUCTURAL_SITE_GEOMETRY_INVALID", field=field) from None
    if not number.is_finite():
        raise LayoutAuthorityError("STRUCTURAL_SITE_GEOMETRY_INVALID", field=field)
    return number


def _site_axis(site_geometry: Mapping[str, object]) -> str:
    site = site_geometry.get("site")
    if not isinstance(site, Mapping):
        raise LayoutAuthorityError("STRUCTURAL_SITE_GEOMETRY_INVALID")
    boundary = site.get("effective_buildable_boundary")
    if not isinstance(boundary, Mapping):
        raise LayoutAuthorityError("STRUCTURAL_SITE_GEOMETRY_INVALID")
    raw_points = boundary.get("points")
    if not isinstance(raw_points, list) or not raw_points:
        raise LayoutAuthorityError("STRUCTURAL_SITE_GEOMETRY_INVALID")
    xs: list[Decimal] = []
    ys: list[Decimal] = []
    for point in raw_points:
        if not isinstance(point, Mapping) or "x" not in point or "y" not in point:
            raise LayoutAuthorityError("STRUCTURAL_SITE_GEOMETRY_INVALID")
        xs.append(_decimal(point["x"], field="x"))
        ys.append(_decimal(point["y"], field="y"))
    boundary_polygon = tuple(zip(xs, ys, strict=True))
    x_events = set(xs)
    y_events = set(ys)
    obstacle_rows: list[tuple[tuple[Decimal, Decimal], ...]] = []
    obstacles = site_geometry.get("obstacles")
    raw_obstacles = obstacles.get("hard_obstacles", []) if isinstance(obstacles, Mapping) else []
    if not isinstance(raw_obstacles, list):
        raise LayoutAuthorityError("STRUCTURAL_SITE_GEOMETRY_INVALID", field="hard_obstacles")
    for row in raw_obstacles:
        footprint = row.get("footprint") if isinstance(row, Mapping) else None
        points = footprint.get("points") if isinstance(footprint, Mapping) else None
        if not isinstance(points, list) or len(points) < 3:
            raise LayoutAuthorityError("STRUCTURAL_SITE_GEOMETRY_INVALID", field="hard_obstacles")
        polygon: list[tuple[Decimal, Decimal]] = []
        for point in points:
            if not isinstance(point, Mapping) or "x" not in point or "y" not in point:
                raise LayoutAuthorityError(
                    "STRUCTURAL_SITE_GEOMETRY_INVALID", field="hard_obstacles"
                )
            x = _decimal(point["x"], field="obstacle.x")
            y = _decimal(point["y"], field="obstacle.y")
            polygon.append((x, y))
            x_events.add(x)
            y_events.add(y)
        obstacle_rows.append(tuple(polygon))

    ordered_x = tuple(sorted(x_events))
    ordered_y = tuple(sorted(y_events))
    if len(ordered_x) < 2 or len(ordered_y) < 2:
        return "X" if max(xs) - min(xs) >= max(ys) - min(ys) else "Y"

    def inside(point: tuple[Decimal, Decimal], polygon: Sequence[tuple[Decimal, Decimal]]) -> bool:
        x, y = point
        result = False
        closed_polygon = tuple(polygon[1:]) + tuple(polygon[:1])
        for (first_x, first_y), (second_x, second_y) in zip(polygon, closed_polygon, strict=True):
            if (first_y > y) != (second_y > y):
                crossing_x = first_x + (y - first_y) * (second_x - first_x) / (second_y - first_y)
                if x < crossing_x:
                    result = not result
        return result

    free_cells: list[list[bool]] = []
    for y_low, y_high in zip(ordered_y, ordered_y[1:], strict=False):
        center_y = (y_low + y_high) / Decimal("2")
        row_free: list[bool] = []
        for x_low, x_high in zip(ordered_x, ordered_x[1:], strict=False):
            center = ((x_low + x_high) / Decimal("2"), center_y)
            row_free.append(
                inside(center, boundary_polygon)
                and not any(inside(center, obstacle) for obstacle in obstacle_rows)
            )
        free_cells.append(row_free)

    largest_area = Decimal("-1")
    largest_width = max(xs) - min(xs)
    largest_height = max(ys) - min(ys)
    for first_row in range(len(free_cells)):
        open_columns = [True] * (len(ordered_x) - 1)
        for last_row in range(first_row, len(free_cells)):
            open_columns = [
                available and current
                for available, current in zip(open_columns, free_cells[last_row], strict=True)
            ]
            column = 0
            while column < len(open_columns):
                if not open_columns[column]:
                    column += 1
                    continue
                first_column = column
                while column < len(open_columns) and open_columns[column]:
                    column += 1
                width = ordered_x[column] - ordered_x[first_column]
                height = ordered_y[last_row + 1] - ordered_y[first_row]
                area = width * height
                if area > largest_area or (
                    area == largest_area and (width, height) > (largest_width, largest_height)
                ):
                    largest_area = area
                    largest_width = width
                    largest_height = height
    return "X" if largest_width >= largest_height else "Y"


def composition_family_candidates(
    site_geometry: Mapping[str, object],
) -> tuple[StructuralCompositionFamilyV1, ...]:
    """Enumerate the three independent families on the site-derived axis.

    Direction remains an explicit pair of candidates; neither truck entrance
    nor loading face is misrepresented as a raw-receiving authority.
    """
    axis = _site_axis(site_geometry)
    return (
        StructuralCompositionFamilyV1(
            LINEAR_PROCESS_BAND,
            axis,
            "POSITIVE",
            "DOMINANT_SITE_AXIS_CANDIDATE",
        ),
        StructuralCompositionFamilyV1(
            LINEAR_PROCESS_BAND,
            axis,
            "NEGATIVE",
            "DOMINANT_SITE_AXIS_CANDIDATE",
        ),
        StructuralCompositionFamilyV1(
            CENTRAL_PROCESS_HUB,
            axis,
            "UNRESOLVED",
            "SORTING_PACKAGING_IS_EXPLICIT_PROCESS_CORE",
        ),
    )


def select_structural_composition_family(
    site_geometry: Mapping[str, object],
    zone_authorities: Mapping[str, Mapping[str, object]],
) -> StructuralCompositionFamilyV1:
    """Select a search family from authoritative role/area facts, not a template.

    When sorting/packaging is the largest main-process zone, the core/hub
    family is first.  Otherwise a direction-enumerated linear band is first;
    both families remain available in the versioned candidate list.
    """
    candidates = composition_family_candidates(site_geometry)
    process_areas: dict[str, Decimal] = {}
    for code in MAIN_PROCESS_ZONE_CODES:
        authority = zone_authorities.get(code)
        if authority is None:
            continue
        value = authority.get("required_area_m2")
        if value is None:
            geometry = authority.get("geometry")
            if isinstance(geometry, Mapping):
                value = geometry.get("required_area_m2")
        if value is not None:
            process_areas[code] = _decimal(value, field=f"{code}.required_area_m2")
    if "sorting_packaging_room" not in process_areas or len(process_areas) < 2:
        raise LayoutAuthorityError("STRUCTURAL_PROCESS_AREA_AUTHORITY_UNAVAILABLE")
    core_area = process_areas["sorting_packaging_room"]
    core_dominant = all(
        core_area >= area
        for code, area in process_areas.items()
        if code != "sorting_packaging_room"
    )
    if core_dominant:
        return candidates[2]
    return candidates[0]


__all__ = [
    "CENTRAL_PROCESS_HUB",
    "FINISHED_SIDE_GROUP",
    "FUNCTIONAL_GROUPS",
    "IDENTITY",
    "LINEAR_PROCESS_BAND",
    "MAIN_PROCESS_ZONE_CODES",
    "MAIN_PROCESS_SKELETON_ZONE_CODES",
    "MAIN_PROCESS_PREDECESSOR",
    "PERSONNEL_GROUP",
    "PROCESSING_CORE_GROUP",
    "RAW_SIDE_GROUP",
    "STRUCTURAL_ANCHOR_REFERENCES",
    "SUPPORT_GROUP",
    "SKELETON_IDENTITY",
    "StructuralCompositionFamilyV1",
    "StructuralSkeletonV1",
    "bind_functional_groups",
    "composition_family_candidates",
    "functional_group_for_zone",
    "select_structural_composition_family",
    "structural_skeleton_candidates",
    "structural_anchor_references",
]
