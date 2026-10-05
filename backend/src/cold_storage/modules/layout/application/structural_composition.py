"""Bind server-validated P1/site authorities to structural compositions.

This application boundary exposes no caller-created site-facts input.  It
validates the existing P1 integrity chain, derives categorical orientation
facts from the authenticated site geometry, then emits composition-only plans
and geometry-free placement-intent handoffs.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.application.layout_authority_binding import (
    P1_HANDOFF_IDENTITY,
    bind_layout_authority,
    validate_canonical_zone_plan,
)
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES
from cold_storage.modules.layout.domain.composition_handoff import (
    IDENTITY as PLACEMENT_HANDOFF_IDENTITY,
)
from cold_storage.modules.layout.domain.composition_handoff import (
    SCHEMA_VERSION as PLACEMENT_HANDOFF_SCHEMA_VERSION,
)
from cold_storage.modules.layout.domain.composition_handoff import (
    CompositionRelationshipIntentV1,
    DimensionAuthorityReferenceV1,
    PeripheralDomainIntentV1,
    PrincipalBandIntentV1,
    StructuralCompositionPlacementHandoffV1,
    ZoneRolePlacementIntentV1,
)
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.layout.domain.site_geometry import (
    IDENTITY as SITE_GEOMETRY_IDENTITY,
)
from cold_storage.modules.layout.domain.site_geometry import (
    SCHEMA_VERSION as SITE_GEOMETRY_SCHEMA_VERSION,
)
from cold_storage.modules.layout.domain.site_geometry import (
    SegmentMM,
    normalize_polygon,
    normalize_segment,
    segment_on_polygon_boundary,
    segments_share_positive_length,
)
from cold_storage.modules.layout.domain.structural_composition import (
    CardinalSideV1,
    CompositionFamilyV2,
    ProcessAxisV1,
    SiteOrientationFactsV1,
    StructuralCompositionPlanV2,
    enumerate_structural_compositions,
    family_coverage_evidence,
)

IDENTITY = "structural-composition-application@1.0.0"
SCHEMA_VERSION = "1.0.0"
ZONE_PLAN_CALCULATOR_NAME = "cold_room_zone_plan"
ZONE_PLAN_CALCULATOR_VERSION = "1.0.0"
DOMINANT_SITE_AXIS_POLICY_ID = "EFFECTIVE_BUILDABLE_BOUNDARY_BBOX_LONG_AXIS@1.0.0"
_CARDINAL_SIDES = frozenset(side.value for side in CardinalSideV1)
_FAMILY_COVERAGE_ORDER = tuple(family.value for family in CompositionFamilyV2)


def _authority_error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _required_mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _authority_error("STRUCTURAL_COMPOSITION_AUTHORITY_INVALID", field=field)
    return value


def _numeric_segment(value: object) -> SegmentMM:
    if not isinstance(value, Mapping) or set(value) != {"start", "end"}:
        raise _authority_error("SITE_BOUNDARY_SIDE_UNRESOLVED", reason="INVALID_SEGMENT")
    points: dict[str, dict[str, Decimal]] = {}
    for endpoint in ("start", "end"):
        raw_point = value[endpoint]
        if not isinstance(raw_point, Mapping) or set(raw_point) != {"x", "y"}:
            raise _authority_error("SITE_BOUNDARY_SIDE_UNRESOLVED", reason="INVALID_SEGMENT")
        point: dict[str, Decimal] = {}
        for axis in ("x", "y"):
            coordinate = raw_point[axis]
            if isinstance(coordinate, bool) or not isinstance(
                coordinate, (int, float, str, Decimal)
            ):
                raise _authority_error("SITE_BOUNDARY_SIDE_UNRESOLVED", reason="INVALID_SEGMENT")
            try:
                point[axis] = Decimal(str(coordinate))
            except (InvalidOperation, TypeError, ValueError):
                raise _authority_error(
                    "SITE_BOUNDARY_SIDE_UNRESOLVED", reason="INVALID_SEGMENT"
                ) from None
        points[endpoint] = point
    try:
        return normalize_segment(points, error_code="SITE_BOUNDARY_SIDE_UNRESOLVED")
    except LayoutAuthorityError:
        raise _authority_error("SITE_BOUNDARY_SIDE_UNRESOLVED", reason="INVALID_SEGMENT") from None


def derive_boundary_side(
    entrance_segment: Mapping[str, Any], boundary: Mapping[str, Any]
) -> CardinalSideV1:
    """Resolve an entrance's outward cardinal side from a validated polygon.

    Invalid/non-boundary segments fail closed.  A valid diagonal, corner-spanning,
    or otherwise ambiguous boundary segment is explicitly ``UNSPECIFIED``.
    Polygon winding is normalized by computing the outward normal from its area.
    """
    try:
        polygon = normalize_polygon(
            boundary, error_code="SITE_BOUNDARY_SIDE_UNRESOLVED", allow_numeric_string=True
        )
        segment = _numeric_segment(entrance_segment)
    except LayoutAuthorityError:
        raise
    if not segment_on_polygon_boundary(segment[0], segment[1], polygon):
        raise _authority_error("SITE_BOUNDARY_SIDE_UNRESOLVED", reason="NOT_ON_BOUNDARY")

    twice_signed_area = sum(
        polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
        - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
        for index in range(len(polygon))
    )
    if twice_signed_area == 0:
        raise _authority_error("SITE_BOUNDARY_SIDE_UNRESOLVED", reason="ZERO_AREA")
    winding = 1 if twice_signed_area > 0 else -1
    sides: set[CardinalSideV1] = set()
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        if not segments_share_positive_length(segment[0], segment[1], start, end):
            continue
        dx, dy = end[0] - start[0], end[1] - start[1]
        if dx == 0:
            outward_x = winding * dy
            sides.add(CardinalSideV1.EAST if outward_x > 0 else CardinalSideV1.WEST)
        elif dy == 0:
            outward_y = -winding * dx
            sides.add(CardinalSideV1.NORTH if outward_y > 0 else CardinalSideV1.SOUTH)
    return next(iter(sides)) if len(sides) == 1 else CardinalSideV1.UNSPECIFIED


def _derive_site_orientation_facts(
    geometry: ValidatedSiteGeometryV1,
) -> SiteOrientationFactsV1:
    if not isinstance(geometry, ValidatedSiteGeometryV1) or not geometry._is_authoritative():
        raise _authority_error("INVALID_SITE_GEOMETRY_RESULT", reason="UNVERIFIED_GEOMETRY_RESULT")
    body = geometry.to_dict()
    if (
        body.get("identity") != SITE_GEOMETRY_IDENTITY
        or body.get("schema_version") != SITE_GEOMETRY_SCHEMA_VERSION
        or body.get("validation_status") != "VALIDATED_GEOMETRY_FOUNDATION"
        or body.get("source_p1_handoff_identity") != P1_HANDOFF_IDENTITY
        or not isinstance(body.get("source_p1_handoff_hash"), str)
        or canonical_json(body) != geometry.canonical_json()
        or canonical_hash(body) != geometry.canonical_result_hash
    ):
        raise _authority_error("INVALID_SITE_GEOMETRY_RESULT", reason="SITE_GEOMETRY_INTEGRITY")
    site = _required_mapping(body.get("site"), field="site")
    entrances = _required_mapping(body.get("entrances"), field="entrances")
    effective_boundary = site.get("effective_buildable_boundary")
    site_boundary = site.get("site_boundary")
    if not isinstance(effective_boundary, Mapping) or not isinstance(site_boundary, Mapping):
        raise _authority_error("INVALID_SITE_GEOMETRY_RESULT", field="boundary")
    dominant_axis = _dominant_site_axis(effective_boundary)
    main_side = derive_boundary_side(
        _required_mapping(entrances.get("main_entrance"), field="main_entrance"),
        site_boundary,
    )
    truck_side = derive_boundary_side(
        _required_mapping(entrances.get("truck_entrance"), field="truck_entrance"),
        site_boundary,
    )
    raw_loading_side = site.get("preferred_loading_side")
    if raw_loading_side == "NEAREST_TRUCK_ENTRANCE":
        loading_side = truck_side
    elif isinstance(raw_loading_side, str) and raw_loading_side in _CARDINAL_SIDES:
        loading_side = CardinalSideV1(raw_loading_side)
    else:
        raise _authority_error("SITE_ORIENTATION_FACTS_INVALID", field="preferred_loading_side")
    return SiteOrientationFactsV1(
        source_geometry_identity=str(body["identity"]),
        source_geometry_hash=geometry.canonical_result_hash,
        validation_status=str(body["validation_status"]),
        dominant_site_axis=dominant_axis,
        main_entrance_side=main_side,
        truck_entrance_side=truck_side,
        preferred_loading_side=loading_side,
    )


def _dominant_site_axis(boundary: Mapping[str, Any]) -> ProcessAxisV1:
    effective = normalize_polygon(
        boundary,
        error_code="INVALID_SITE_GEOMETRY_RESULT",
        allow_numeric_string=True,
    )
    x_values = [point[0] for point in effective]
    y_values = [point[1] for point in effective]
    x_span = max(x_values) - min(x_values)
    y_span = max(y_values) - min(y_values)
    # Frozen policy: equal spans deterministically select X.
    return ProcessAxisV1.X if x_span >= y_span else ProcessAxisV1.Y


@dataclass(frozen=True)
class StructuralCompositionEnumerationResultV1:
    identity: str
    schema_version: str
    source_zone_plan_hash: str
    source_p1_handoff_hash: str
    source_site_geometry_hash: str
    site_orientation_facts: SiteOrientationFactsV1
    dominant_site_axis_policy_id: str
    composition_count: int
    family_count: int
    family_coverage_order: tuple[str, ...]
    family_first_round_complete: bool
    family_enumeration_count_by_family: tuple[tuple[str, int], ...]
    composition_count_by_family: tuple[tuple[str, int], ...]
    compositions: tuple[StructuralCompositionPlanV2, ...]
    placement_handoffs: tuple[StructuralCompositionPlacementHandoffV1, ...]
    project_layout_validated_claimed: bool = False
    exact_placement_performed: bool = False
    access_routing_performed: bool = False
    truck_validation_performed: bool = False
    p2d_performed: bool = False

    def __post_init__(self) -> None:
        if self.identity != IDENTITY or self.schema_version != SCHEMA_VERSION:
            raise ValueError("UNSUPPORTED_STRUCTURAL_COMPOSITION_RESULT")
        if self.composition_count != len(self.compositions) or len(self.compositions) != len(
            self.placement_handoffs
        ):
            raise ValueError("STRUCTURAL_COMPOSITION_RESULT_COUNT_MISMATCH")
        if self.family_count != len({plan.family for plan in self.compositions}):
            raise ValueError("STRUCTURAL_COMPOSITION_RESULT_FAMILY_COUNT_MISMATCH")
        if self.family_first_round_complete is not (
            self.family_coverage_order == _FAMILY_COVERAGE_ORDER
        ):
            raise ValueError("STRUCTURAL_COMPOSITION_FAMILY_COVERAGE_INVALID")
        if (
            self.project_layout_validated_claimed
            or self.exact_placement_performed
            or self.access_routing_performed
            or self.truck_validation_performed
            or self.p2d_performed
        ):
            raise ValueError("STRUCTURAL_COMPOSITION_RESULT_SCOPE_VIOLATION")

    def _body(self) -> dict[str, Any]:
        result = asdict(self)
        result["family_enumeration_count_by_family"] = dict(self.family_enumeration_count_by_family)
        result["composition_count_by_family"] = dict(self.composition_count_by_family)
        result["compositions"] = [plan.to_dict() for plan in self.compositions]
        result["placement_handoffs"] = [item.to_dict() for item in self.placement_handoffs]
        return result

    @property
    def canonical_result_hash(self) -> str:
        return canonical_hash(self._body())

    def to_dict(self) -> dict[str, Any]:
        result = self._body()
        result["canonical_result_hash"] = self.canonical_result_hash
        return cast(dict[str, Any], json.loads(canonical_json(result)))


def _handoff_for_composition(
    plan: StructuralCompositionPlanV2,
    *,
    zone_plan_hash: str,
    p1_handoff_hash: str,
    site_geometry_hash: str,
    dimension_authority_identity: str,
) -> StructuralCompositionPlacementHandoffV1:
    role_domains: dict[str, list[str]] = {role: [] for role in ZONE_CODES}
    for domain in plan.peripheral_domains:
        for role in domain.zone_roles:
            role_domains[role].append(domain.domain_id.value)
    assignments = tuple(
        ZoneRolePlacementIntentV1(
            zone_role=item.zone_role,
            dimension_authority_ref=DimensionAuthorityReferenceV1(
                authority_identity=dimension_authority_identity,
                zone_code=item.zone_role,
                source_p1_handoff_hash=p1_handoff_hash,
            ),
            composition_group=item.group_id.value,
            composition_band=item.band_id,
            topology_role=item.topology_role,
            peripheral_domain_membership=tuple(role_domains[item.zone_role]),
        )
        for item in plan.zone_role_assignment
    )
    bands = tuple(
        PrincipalBandIntentV1(
            band_id=band.band_id,
            topology=band.topology,
            group_ids=tuple(group.value for group in band.group_ids),
            zone_roles=band.zone_roles,
            axis_relation=band.axis_relation,
            sequence_index=band.sequence_index,
            relative_position=band.relative_position,
        )
        for band in plan.principal_bands
    )
    domains = tuple(
        PeripheralDomainIntentV1(
            domain_id=domain.domain_id.value,
            zone_roles=domain.zone_roles,
            relative_side=domain.relative_side,
            group_relationship=domain.group_relationship,
            band_relationship=domain.band_relationship,
            topology=domain.topology,
            engineering_authority=False,
        )
        for domain in plan.peripheral_domains
    )
    relations = tuple(
        CompositionRelationshipIntentV1(
            relation_kind=relation.relation_kind.value,
            source=relation.source,
            target=relation.target,
            topology_intent=relation.topology_intent,
            engineering_authority=False,
        )
        for relation in plan.composition_adjacency_intent
    )
    return StructuralCompositionPlacementHandoffV1(
        identity=PLACEMENT_HANDOFF_IDENTITY,
        schema_version=PLACEMENT_HANDOFF_SCHEMA_VERSION,
        composition_identity=plan.identity,
        composition_signature=plan.signature.key,
        family=plan.family,
        process_axis=plan.process_axis,
        process_direction=plan.process_direction,
        zone_role_assignment=assignments,
        principal_band_intents=bands,
        peripheral_domain_intents=domains,
        dominant_axis_family=plan.dominant_axis_family,
        site_orientation_intent=plan.site_orientation_intent,
        composition_relationships=relations,
        source_composition_hash=canonical_hash(plan.to_dict()),
        source_zone_plan_hash=zone_plan_hash,
        source_p1_handoff_hash=p1_handoff_hash,
        source_site_geometry_hash=site_geometry_hash,
        dimension_authority_identity=dimension_authority_identity,
    )


def build_structural_compositions(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: ZoneDimensioningResultV1 | Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
) -> StructuralCompositionEnumerationResultV1:
    """Build compositions from server-owned zone, P1 and validated-site inputs.

    Caller-created ``SiteOrientationFactsV1`` is intentionally not an input to
    this public application API.  P1 checks are delegated to the existing P2C
    integrity validator; this boundary does not recalculate dimensions.
    """
    validate_canonical_zone_plan(canonical_zone_plan)
    if not isinstance(site_geometry, ValidatedSiteGeometryV1):
        raise _authority_error("INVALID_SITE_GEOMETRY_RESULT", reason="UNVERIFIED_GEOMETRY_RESULT")

    binding = bind_layout_authority(canonical_zone_plan, p1_handoff, site_geometry)
    p1_body = dict(binding.p1_body)
    p1_handoff_hash = binding.p1_handoff_hash
    if p1_body.get("p2_authorized") is not False:
        raise _authority_error("P1_HANDOFF_NOT_COMPLETE", field="p2_authorized")
    historical = _required_mapping(
        p1_body.get("p1e_historical_handoff"), field="p1e_historical_handoff"
    )
    dimension = _required_mapping(historical.get("dimension_handoff"), field="dimension_handoff")
    dimension_authority_identity = dimension.get("calculator_identity")
    if not isinstance(dimension_authority_identity, str) or not dimension_authority_identity:
        raise _authority_error("P1_HANDOFF_IDENTITY_INVALID", field="dimension_authority_identity")

    site_facts = _derive_site_orientation_facts(site_geometry)
    plans = enumerate_structural_compositions(site_facts)
    coverage = family_coverage_evidence(plans)
    family_counts = Counter(plan.family.value for plan in plans)
    family_order = tuple(cast(list[str], coverage["family_coverage_order"]))
    enumeration_counts = tuple(
        (key, int(value))
        for key, value in cast(
            dict[str, int], coverage["family_enumeration_count_by_family"]
        ).items()
    )
    composition_counts = tuple((key, int(value)) for key, value in sorted(family_counts.items()))
    zone_plan_hash = binding.canonical_zone_plan_hash
    geometry_hash = binding.site_geometry_hash
    handoffs = tuple(
        _handoff_for_composition(
            plan,
            zone_plan_hash=zone_plan_hash,
            p1_handoff_hash=p1_handoff_hash,
            site_geometry_hash=geometry_hash,
            dimension_authority_identity=dimension_authority_identity,
        )
        for plan in plans
    )
    return StructuralCompositionEnumerationResultV1(
        identity=IDENTITY,
        schema_version=SCHEMA_VERSION,
        source_zone_plan_hash=zone_plan_hash,
        source_p1_handoff_hash=p1_handoff_hash,
        source_site_geometry_hash=geometry_hash,
        site_orientation_facts=site_facts,
        dominant_site_axis_policy_id=DOMINANT_SITE_AXIS_POLICY_ID,
        composition_count=len(plans),
        family_count=len({plan.family for plan in plans}),
        family_coverage_order=family_order,
        family_first_round_complete=coverage["family_first_round_complete"] is True,
        family_enumeration_count_by_family=enumeration_counts,
        composition_count_by_family=composition_counts,
        compositions=plans,
        placement_handoffs=handoffs,
    )
