"""Bind authoritative P1/site inputs to the P2C placement search.

The application boundary validates that the supplied objects are the current
server-owned replay of the canonical zone plan and P1 project handoff.  The
domain search then only places already-approved rectangles and selects sizes
for the three explicitly flexible zones.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.application.layout_authority_binding import (
    bind_layout_authority,
    validate_canonical_zone_plan,
)
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
)
from cold_storage.modules.layout.domain.objective_profile import (
    ObjectiveProfileV1,
    approved_objective_profile,
    validate_objective_profile,
)
from cold_storage.modules.layout.domain.placement import (
    PlacementCandidateEnumerationV1,
    SitePlacementResultV1,
    search_placement,
)
from cold_storage.modules.layout.domain.placement import (
    enumerate_placement_candidates as enumerate_domain_placement_candidates,
)

IDENTITY = "site-constrained-placement-application@1.0.0"


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


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
    return bind_layout_authority(zone_plan, handoff, geometry).as_legacy_tuple()


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
    validate_canonical_zone_plan(canonical_zone_plan)
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


def enumerate_placement_candidates(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: ZoneDimensioningResultV1 | Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    objective_profile: ObjectiveProfileV1 | Mapping[str, object] | None = None,
    *,
    node_budget: int = 50_000,
    complete_candidate_limit: int | None = None,
) -> PlacementCandidateEnumerationV1:
    """Expose complete P2C candidates for downstream P2 validation.

    This is still a P2C-only application boundary: it verifies the same P1
    authority and site inputs as :func:`place_zones`, then delegates to the
    domain's deterministic candidate stream.  It does not invoke P2D routing.
    """
    validate_canonical_zone_plan(canonical_zone_plan)
    _, handoff_hash, authorities, access_requirements, spatial_relationships = (
        _validate_p1_authority(canonical_zone_plan, p1_handoff, site_geometry)
    )
    _, profile_hash = _validated_objective_profile(objective_profile)
    return enumerate_domain_placement_candidates(
        authorities,
        site_geometry.to_dict(),
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
