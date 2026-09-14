"""Canonical P1 hybrid handoff; old dimensioning result remains immutable API."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict
from typing import Any

from cold_storage.modules.layout.application.dimension_zones import (
    ZoneDimensioningResultV1,
    dimension_zones,
)
from cold_storage.modules.layout.domain.dimension_handoff import (
    FLEXIBLE_ZONES,
    EdgeOrientedConnectionV1,
    flexible_authority,
)
from cold_storage.modules.layout.domain.dimensioning import (
    GRID,
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
    decimal_value,
)
from cold_storage.modules.layout.domain.packaging_dimensioning import ZONE, dimension_packaging_zone

IDENTITY = "hybrid_zone_dimension_handoff@1.0.0"
SCHEMA_VERSION = "1.0.0"


def build_dimension_handoff(snapshot: Mapping[str, Any] | None) -> ZoneDimensioningResultV1:
    """No user profiles/hashes accepted. Reuse validated backend canonical source."""
    previous = dimension_zones(snapshot)
    body = previous.to_dict()
    geometry = {row["zone_code"]: row for row in body["dimensions"]}
    authorities: list[dict[str, Any]] = []
    matrix = deepcopy(body["authority_matrix"])
    connection = asdict(EdgeOrientedConnectionV1())
    for row in matrix:
        code = row["zone_code"]
        if code in FLEXIBLE_ZONES:
            authority = flexible_authority(
                code, decimal_value(row["required_area_m2"]), row["capacity_geometry_reference"]
            )
            row["dimensioning_result"] = "FLEXIBLE_AUTHORIZED"
            row["block_reason"] = None
            row["dimensioning_profile_available"] = True
        else:
            if code == ZONE:
                try:
                    geometry[code] = dimension_packaging_zone(row["upstream_zone"])
                    row["dimensioning_result"] = "DIMENSIONED"
                    row["block_reason"] = None
                    row["dimensioning_profile_available"] = True
                except LayoutAuthorityError as error:
                    row["block_reason"] = {"code": error.code, "details": error.details}
            mode = (
                "FIXED_RECTANGLE"
                if code in ("primary_precooling_room", "secondary_precooling_room")
                else "DETERMINISTIC_GRID_RECTANGLE"
            )
            concrete = geometry.get(code)
            authority = {
                "zone_code": code,
                "dimension_mode": mode,
                "status": row["dimensioning_result"],
                "required_area_m2": row["required_area_m2"],
                "area_requirement": concrete["area_requirement"] if concrete else None,
                "dimension_authority_identity": concrete["dimensioning_profile_identity"]
                if concrete
                else None,
                "source_zone_hash": row["capacity_geometry_reference"],
                "grid_m": GRID,
                "rotation_allowed": [0, 90],
                "p2_may_select_width_depth": False,
                "p2_may_change_required_area": False,
                "geometry": concrete,
                "required_connection_edges": [],
            }
            if code in (ZONE, "sorting_packaging_room"):
                authority["required_connection_edges"] = [connection["identity"]]
            if code == "sorting_packaging_room":
                authority["material_exit_edge_class"] = "SHORT_EDGE"
                authority["exit_side_selection"] = "P2_RELATIVE_EDGE_SELECTION_REQUIRED"
        authorities.append(authority)
    blocked = [row["zone_code"] for row in matrix if row["dimensioning_result"] == "BLOCKED"]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "calculator_identity": IDENTITY,
        "source_zone_plan_calculator_identity": body["source_zone_plan_calculator_identity"],
        "source_formula_authority": body["source_formula_authority"],
        "source_zone_plan_result_hash": body["source_zone_plan_result_hash"],
        "upstream_dimensioning_identity": body["calculator_identity"],
        "upstream_dimensioning_hash": previous.canonical_result_hash,
        "dimension_authority_model": "HYBRID",
        "status": "PARTIAL_ENGINEERING_AUTHORITY" if blocked else "DIMENSION_AUTHORITY_COMPLETE",
        "authorities": authorities,
        "dimensions": [geometry[code] for code in sorted(geometry)],
        "authority_matrix": matrix,
        "blocked_zones": blocked,
        "adjacency_graph": body["adjacency_graph"],
        "spatial_relationships": [connection],
        "constraint_evaluation": {
            **body["constraint_evaluation"],
            "connection_status": "NOT_EVALUATED_ACCESS_PROFILE_REQUIRED",
        },
        "p1_complete": False,
        "p2_implementation_authorized": False,
        "requires_review": True,
        "warnings": [
            "Dimension authority is not site feasibility, access acceptance or P1 closure."
        ],
    }
    return ZoneDimensioningResultV1(canonical_json(payload))


def validate_handoff_integrity(snapshot: Mapping[str, Any], handoff: Mapping[str, Any]) -> bool:
    """Bind area, resize permissions and geometry to canonical replay, not claimed hash."""
    return canonical_hash(handoff) == build_dimension_handoff(snapshot).canonical_result_hash
