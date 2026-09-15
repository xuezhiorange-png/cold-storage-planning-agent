"""Bind authoritative P1/site inputs to the P2C placement search.

The application boundary validates that the supplied objects are the current
server-owned replay of the canonical zone plan and P1 project handoff.  The
domain search then only places already-approved rectangles and selects sizes
for the three explicitly flexible zones.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.layout.domain.objective_profile import (
    ObjectiveProfileV1,
    approved_objective_profile,
    validate_objective_profile,
)
from cold_storage.modules.layout.domain.placement import (
    SitePlacementResultV1,
    search_placement,
)

IDENTITY = "site-constrained-placement-application@1.0.0"
P1_HANDOFF_IDENTITY = "p1-project-access-handoff@1.0.0"
P1_HANDOFF_SCHEMA_VERSION = "1.0.0"
DIMENSION_HANDOFF_IDENTITY = "hybrid_zone_dimension_handoff@1.0.0"
ZONE_PLAN_IDENTITY = "cold_room_zone_plan@1.0.0"
FLEXIBLE_ZONES = frozenset({"coating_room", "changing_room", "office"})
P1_ACCESS_REQUIREMENT_COUNT = 12


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error("PLACEMENT_AUTHORITY_INVALID", field=field)
    return value


def _p1_body(handoff: object) -> tuple[dict[str, Any], str]:
    if isinstance(handoff, ZoneDimensioningResultV1):
        body = handoff.to_dict()
        return body, handoff.canonical_result_hash
    if isinstance(handoff, Mapping):
        body = dict(handoff)
        return body, canonical_hash(body)
    raise _error("P1_HANDOFF_AUTHORITY_REQUIRED")


def _validate_p1_authority(
    zone_plan: Mapping[str, Any],
    handoff: object,
    geometry: ValidatedSiteGeometryV1,
) -> tuple[
    dict[str, Any],
    str,
    dict[str, Mapping[str, Any]],
    tuple[Mapping[str, Any], ...],
    tuple[Mapping[str, Any], ...],
]:
    if not geometry._is_authoritative():
        raise _error("INVALID_SITE_GEOMETRY_RESULT", reason="UNVERIFIED_GEOMETRY_RESULT")
    body, handoff_hash = _p1_body(handoff)
    if (
        body.get("identity") != P1_HANDOFF_IDENTITY
        or body.get("schema_version") != P1_HANDOFF_SCHEMA_VERSION
    ):
        raise _error("P1_HANDOFF_IDENTITY_INVALID")
    status = _mapping(body.get("authority_status"), field="authority_status")
    required_status = (
        "dimension_authority_complete",
        "personnel_access_authority_complete",
        "material_access_authority_complete",
        "truck_access_contract_complete",
        "truck_project_input_contract_complete",
        "p1_complete",
    )
    if any(status.get(key) is not True for key in required_status):
        raise _error("P1_HANDOFF_NOT_COMPLETE", fields=list(required_status))
    if body.get("p1_closure_blockers") != [] or body.get("p2_implemented") is not False:
        raise _error("P1_HANDOFF_NOT_COMPLETE")

    geometry_body = geometry.to_dict()
    if geometry_body.get("source_p1_handoff_hash") != handoff_hash:
        raise _error("P1_HANDOFF_INTEGRITY_MISMATCH")

    historical = _mapping(body.get("p1e_historical_handoff"), field="p1e_historical_handoff")
    if body.get("p1e_historical_handoff_hash") != canonical_hash(historical):
        raise _error("P1_HANDOFF_INTEGRITY_MISMATCH", field="p1e_historical_handoff_hash")
    dimension = _mapping(historical.get("dimension_handoff"), field="dimension_handoff")
    if dimension.get("calculator_identity") != DIMENSION_HANDOFF_IDENTITY:
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="dimension_handoff")
    if dimension.get("source_zone_plan_calculator_identity") != ZONE_PLAN_IDENTITY:
        raise _error("ZONE_PLAN_IDENTITY_INVALID")
    if dimension.get("source_zone_plan_result_hash") != canonical_hash(zone_plan):
        raise _error("P1_HANDOFF_INTEGRITY_MISMATCH", field="source_zone_plan_result_hash")
    graph = process_graph()
    if canonical_json(dimension.get("adjacency_graph")) != canonical_json(asdict(graph)):
        raise _error("P1_HANDOFF_INTEGRITY_MISMATCH", field="adjacency_graph")

    authorities_raw = dimension.get("authorities")
    if not isinstance(authorities_raw, list) or any(
        not isinstance(row, Mapping) for row in authorities_raw
    ):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="authorities")
    authorities = {str(row["zone_code"]): row for row in authorities_raw if "zone_code" in row}
    if set(authorities) != set(ZONE_CODES) or len(authorities) != len(authorities_raw):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="authorities")
    if not all(
        authorities[code].get("dimension_mode") == "FLEXIBLE_RECTANGLE" for code in FLEXIBLE_ZONES
    ):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="flexible_authorities")
    for code in FLEXIBLE_ZONES:
        authority = authorities[code]
        if (
            authority.get("status") != "FLEXIBLE_AUTHORIZED"
            or authority.get("p2_may_select_width_depth") is not True
        ):
            raise _error("P1_HANDOFF_IDENTITY_INVALID", field=code)
        if authority.get("p2_may_change_required_area") is not False:
            raise _error("P1_HANDOFF_IDENTITY_INVALID", field=code)
    concrete = [code for code in authorities if code not in FLEXIBLE_ZONES]
    if any(authorities[code].get("status") != "DIMENSIONED" for code in concrete):
        raise _error("P1_HANDOFF_NOT_COMPLETE", field="concrete_dimensions")
    dimensions = dimension.get("dimensions")
    if not isinstance(dimensions, list) or {
        row.get("zone_code") for row in dimensions if isinstance(row, Mapping)
    } != set(concrete):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="dimensions")
    raw_access_requirements = historical.get("access_requirements")
    if not isinstance(raw_access_requirements, list):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="access_requirements")
    if len(raw_access_requirements) != P1_ACCESS_REQUIREMENT_COUNT:
        raise _error(
            "P1_HANDOFF_IDENTITY_INVALID",
            field="access_requirements",
            expected_count=P1_ACCESS_REQUIREMENT_COUNT,
        )
    required_access_fields = {
        "identity",
        "from_ref",
        "to_ref",
        "flow_kind",
        "access_class",
        "profile_identity",
        "portal_required",
        "corridor_allowed",
        "direct_allowed",
        "edge_orientation_requirement",
        "route_shape_constraint",
    }
    access_requirements: list[Mapping[str, Any]] = []
    access_keys: set[tuple[object, object, object]] = set()
    access_identities: set[str] = set()
    for requirement in raw_access_requirements:
        if not isinstance(requirement, Mapping) or not required_access_fields <= set(requirement):
            raise _error("P1_HANDOFF_IDENTITY_INVALID", field="access_requirements")
        identity = requirement.get("identity")
        from_ref = requirement.get("from_ref")
        to_ref = requirement.get("to_ref")
        flow_kind = requirement.get("flow_kind")
        if (
            not isinstance(identity, str)
            or not isinstance(from_ref, str)
            or not isinstance(to_ref, str)
            or not isinstance(flow_kind, str)
            or identity in access_identities
        ):
            raise _error("P1_HANDOFF_IDENTITY_INVALID", field="access_requirements")
        key = (from_ref, to_ref, flow_kind)
        if key in access_keys:
            raise _error("P1_HANDOFF_IDENTITY_INVALID", field="access_requirements")
        access_identities.add(identity)
        access_keys.add(key)
        access_requirements.append(dict(requirement))
    raw_spatial_relationships = historical.get("spatial_relationships")
    if not isinstance(raw_spatial_relationships, list) or any(
        not isinstance(row, Mapping) for row in raw_spatial_relationships
    ):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="spatial_relationships")
    spatial_relationships = tuple(dict(row) for row in raw_spatial_relationships)
    return (
        body,
        handoff_hash,
        {code: authorities[code] for code in ZONE_CODES},
        tuple(access_requirements),
        spatial_relationships,
    )


def _validated_objective_profile(
    source: ObjectiveProfileV1 | Mapping[str, object] | None,
) -> tuple[ObjectiveProfileV1, str]:
    approved = approved_objective_profile()
    if source is None:
        return approved, approved.canonical_result_hash
    if isinstance(source, ObjectiveProfileV1):
        if source.canonical_json() != approved.canonical_json():
            raise _error("OBJECTIVE_PROFILE_IDENTITY_INVALID")
        return approved, approved.canonical_result_hash
    profile = validate_objective_profile(source)
    return profile, profile.canonical_result_hash


def place_zones(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: ZoneDimensioningResultV1 | Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    objective_profile: ObjectiveProfileV1 | Mapping[str, object] | None = None,
    *,
    node_budget: int = 50_000,
    complete_candidate_limit: int | None = None,
) -> SitePlacementResultV1:
    """Place all canonical zones within a validated site when the finite search finds one."""
    if not isinstance(canonical_zone_plan, Mapping):
        raise _error("ZONE_PLAN_IDENTITY_INVALID")
    if (
        canonical_zone_plan.get("success") is not True
        or canonical_zone_plan.get("calculator_name") != "cold_room_zone_plan"
        or canonical_zone_plan.get("calculator_version") != "1.0.0"
    ):
        raise _error("ZONE_PLAN_IDENTITY_INVALID")
    _, handoff_hash, authorities, access_requirements, spatial_relationships = (
        _validate_p1_authority(canonical_zone_plan, p1_handoff, site_geometry)
    )
    profile, profile_hash = _validated_objective_profile(objective_profile)
    geometry_body = site_geometry.to_dict()
    return search_placement(
        authorities,
        geometry_body,
        process_graph(),
        source_zone_plan_hash=canonical_hash(canonical_zone_plan),
        source_p1_handoff_hash=handoff_hash,
        source_site_geometry_hash=site_geometry.canonical_result_hash,
        objective_profile_hash=profile_hash,
        access_requirements=access_requirements,
        spatial_relationships=spatial_relationships,
        node_budget=node_budget,
        complete_candidate_limit=complete_candidate_limit,
    )


# The name mirrors the P2C task language and is kept as a small public alias;
# both names execute the same authority-bound application path.
calculate_site_placement = place_zones
