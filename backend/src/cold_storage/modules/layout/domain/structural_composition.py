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
    "secondary_precooling_room": ("sorting_packaging_room",),
    "coating_room": ("secondary_precooling_room", "sorting_packaging_room"),
    "finished_goods_room": ("coating_room", "secondary_precooling_room"),
    "shipping_channel": ("finished_goods_room",),
    "packaging_material_storage": ("sorting_packaging_room",),
    # Support functions form a subordinate branch rooted at packaging storage;
    # access to sorting is still validated independently by P2D and may be
    # direct or corridor-mediated under its existing authority.
    "secondary_fruit_buffer": ("packaging_material_storage",),
    "frozen_fruit_room": (
        "packaging_material_storage",
        "secondary_fruit_buffer",
    ),
    "changing_room": ("sorting_packaging_room",),
    "office": ("changing_room", "shipping_channel"),
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
    return "X" if max(xs) - min(xs) >= max(ys) - min(ys) else "Y"


def composition_family_candidates(
    site_geometry: Mapping[str, object],
) -> tuple[StructuralCompositionFamilyV1, ...]:
    """Enumerate abstract family/direction policies in stable geometry order.

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
    "MAIN_PROCESS_PREDECESSOR",
    "PERSONNEL_GROUP",
    "PROCESSING_CORE_GROUP",
    "RAW_SIDE_GROUP",
    "STRUCTURAL_ANCHOR_REFERENCES",
    "SUPPORT_GROUP",
    "StructuralCompositionFamilyV1",
    "bind_functional_groups",
    "composition_family_candidates",
    "functional_group_for_zone",
    "select_structural_composition_family",
    "structural_anchor_references",
]
