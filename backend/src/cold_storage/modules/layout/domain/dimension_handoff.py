"""Hybrid P1 authority, not a site-placement or access compliance result."""

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import GRID, AreaRequirementV1

OWNER = "Charles:V2_2_P1D3_FLEXIBLE_RECTANGLE_HANDOFF_CONTRACT_R1"
FLEXIBLE_ZONES = ("coating_room", "changing_room", "office")


@dataclass(frozen=True)
class EdgeOrientedConnectionV1:
    identity: str = "packaging-sorting-edge-connection@1.0.0"
    from_zone: str = "packaging_material_storage"
    from_edge_class: str = "LONG_EDGE"
    to_zone: str = "sorting_packaging_room"
    to_edge_class: str = "SHORT_EDGE_EXIT_SIDE"
    connection_required: bool = True
    direction_alignment_required: bool = True
    direct_allowed: bool = True
    corridor_allowed: bool = True
    portal_access_profile_required: bool = True
    authority: str = OWNER

    def accepts_topology(self, kind: str) -> bool:
        """Contract membership only; never proves a route, portal or geometry valid."""
        return (kind == "DIRECT_SHARED_EDGE" and self.direct_allowed) or (
            kind == "CORRIDOR_MEDIATED" and self.corridor_allowed
        )


def flexible_authority(code: str, area: Decimal, source_hash: str) -> dict[str, Any]:
    if code not in FLEXIBLE_ZONES:
        raise ValueError("UNAUTHORIZED_FLEXIBLE_ZONE")
    return {
        "zone_code": code,
        "dimension_mode": "FLEXIBLE_RECTANGLE",
        "status": "FLEXIBLE_AUTHORIZED",
        "required_area_m2": area,
        "area_requirement": asdict(AreaRequirementV1(area)),
        "dimension_authority_identity": f"charles-flexible-{code}@1.0.0",
        "source_zone_hash": source_hash,
        "authority": OWNER,
        "grid_m": GRID,
        "rotation_allowed": [0, 90],
        "min_width_m": None,
        "max_width_m": None,
        "min_depth_m": None,
        "max_depth_m": None,
        "aspect_ratio_bounds": None,
        "orientation_constraints": [],
        "required_connection_edges": [],
        "p2_may_select_width_depth": True,
        "p2_may_change_required_area": False,
        "personnel_portal_authorized": False,
    }
