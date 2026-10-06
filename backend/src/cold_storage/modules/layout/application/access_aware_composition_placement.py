"""Access-aware composition placement orchestration over existing authorities."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from cold_storage.modules.layout.application.access_critical_construction import (
    build_access_critical_construction_intent,
)
from cold_storage.modules.layout.application.access_routing import route_site_placement
from cold_storage.modules.layout.application.composition_candidate_validation import (
    _adapt_candidate_to_existing_placement,
    validate_composition_candidate,
)
from cold_storage.modules.layout.application.composition_placement import (
    _assert_server_replay,
)
from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.application.layout_authority_binding import (
    LayoutAuthorityBindingV1,
    bind_layout_authority,
)
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.application.structural_composition import (
    build_structural_compositions,
)
from cold_storage.modules.layout.domain.access_critical_construction import (
    AccessCriticalConstructionIntentV1,
)
from cold_storage.modules.layout.domain.access_routing import (
    DEFAULT_ROUTE_NODE_BUDGET,
    _segment_from_mapping,
)
from cold_storage.modules.layout.domain.access_routing import (
    route_access_requirement as validate_access_requirement,
)
from cold_storage.modules.layout.domain.composition_placement import (
    DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET,
    CompositionPlacementCandidateV1,
    CompositionPlacementEnumerationV1,
)
from cold_storage.modules.layout.domain.composition_placement import (
    enumerate_composition_placements as enumerate_domain_placements,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.placement import _loading_face
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    normalize_polygon,
)
from cold_storage.modules.layout.domain.truck_maneuver import (
    BoundTruckManeuverProjectInputV1,
)

NON_TRUCK_ACCESS_REQUIREMENT_COUNT = 11
TRUCK_NODE_BUDGET = 20_000


@dataclass(frozen=True)
class AccessAwareCompositionPlacementResultV1:
    identity: str
    schema_version: str
    source_zone_plan_hash: str
    source_p1_handoff_hash: str
    source_site_geometry_hash: str
    construction_intent: AccessCriticalConstructionIntentV1
    construction_preflight: Mapping[str, str]
    placements: CompositionPlacementEnumerationV1
    candidate_assessments: tuple[Mapping[str, Any], ...]
    complete_candidates_constructed: int
    complete_candidates_access_assessed: int
    candidates_admitted: int
    candidates_selected: int
    best_candidate_hash: str | None
    selected_candidate_hash: str | None
    best_non_truck_access_pass_count: int
    best_non_truck_access_fail_count: int
    selected_non_truck_access_pass_count: int
    selected_non_truck_access_fail_count: int
    packaging_preflight_pass_partial_count: int
    packaging_preflight_pass_complete_candidate_count: int
    packaging_final_access_pass_candidate_count: int
    truck_preflight_complete_candidate_prune_count: int
    access_validation_attempts: int
    truck_validation_attempts: int
    p2d_validation_attempts: int
    truck_preflight: Mapping[str, Any] | None
    final_validation: Mapping[str, Any] | None
    access_routing_performed: bool
    truck_validation_performed: bool
    p2d_performed: bool
    project_layout_validated_claimed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "schema_version": self.schema_version,
            "source_zone_plan_hash": self.source_zone_plan_hash,
            "source_p1_handoff_hash": self.source_p1_handoff_hash,
            "source_site_geometry_hash": self.source_site_geometry_hash,
            "construction_intent": self.construction_intent.to_dict(),
            "construction_preflight": dict(self.construction_preflight),
            "placements": self.placements.to_dict(),
            "candidate_assessments": [dict(row) for row in self.candidate_assessments],
            "complete_candidates_constructed": self.complete_candidates_constructed,
            "complete_candidates_access_assessed": self.complete_candidates_access_assessed,
            "candidates_admitted": self.candidates_admitted,
            "candidates_selected": self.candidates_selected,
            "best_candidate_hash": self.best_candidate_hash,
            "selected_candidate_hash": self.selected_candidate_hash,
            "best_non_truck_access_pass_count": self.best_non_truck_access_pass_count,
            "best_non_truck_access_fail_count": self.best_non_truck_access_fail_count,
            "selected_non_truck_access_pass_count": self.selected_non_truck_access_pass_count,
            "selected_non_truck_access_fail_count": self.selected_non_truck_access_fail_count,
            "packaging_preflight_pass_partial_count": (self.packaging_preflight_pass_partial_count),
            "packaging_preflight_pass_complete_candidate_count": (
                self.packaging_preflight_pass_complete_candidate_count
            ),
            "packaging_final_access_pass_candidate_count": (
                self.packaging_final_access_pass_candidate_count
            ),
            "truck_preflight_complete_candidate_prune_count": (
                self.truck_preflight_complete_candidate_prune_count
            ),
            "access_validation_attempts": self.access_validation_attempts,
            "truck_validation_attempts": self.truck_validation_attempts,
            "p2d_validation_attempts": self.p2d_validation_attempts,
            "truck_preflight": dict(self.truck_preflight) if self.truck_preflight else None,
            "final_validation": dict(self.final_validation) if self.final_validation else None,
            "access_routing_performed": self.access_routing_performed,
            "truck_validation_performed": self.truck_validation_performed,
            "p2d_performed": self.p2d_performed,
            "project_layout_validated_claimed": self.project_layout_validated_claimed,
        }

    @property
    def canonical_result_hash(self) -> str:
        return canonical_hash(self.to_dict())


def _site_validation_context(
    site_geometry: ValidatedSiteGeometryV1,
) -> tuple[Any, tuple[Any, ...], dict[str, Any]]:
    body = site_geometry.to_dict()
    site = body.get("site")
    obstacles_record = body.get("obstacles")
    entrances_record = body.get("entrances")
    if not isinstance(site, Mapping) or not isinstance(obstacles_record, Mapping):
        raise ValueError("ACCESS_AWARE_SITE_GEOMETRY_INVALID")
    boundary = normalize_polygon(
        site.get("effective_buildable_boundary"), allow_numeric_string=True
    )
    raw_obstacles = obstacles_record.get("hard_obstacles")
    if not isinstance(raw_obstacles, list):
        raise ValueError("ACCESS_AWARE_OBSTACLE_AUTHORITY_INVALID")
    obstacles = tuple(
        normalize_polygon(row.get("footprint"), allow_numeric_string=True)
        for row in raw_obstacles
        if isinstance(row, Mapping)
    )
    if not isinstance(entrances_record, Mapping):
        raise ValueError("ACCESS_AWARE_ENTRANCE_AUTHORITY_INVALID")
    entrances = {
        name: _segment_from_mapping(entrances_record.get(name), field=name)
        for name in ("main_entrance", "truck_entrance")
    }
    return boundary, obstacles, entrances


def _dimension_has_portal_capacity(
    authority: Mapping[str, Any], edge_class: str | None, required_width_mm: int
) -> bool | None:
    geometry = authority.get("geometry")
    rotations = authority.get("rotation_allowed")
    if not isinstance(geometry, Mapping) or not isinstance(rotations, list) or not rotations:
        return None
    try:
        width_mm = int(Decimal(str(geometry["width_m"])) * 1000)
        depth_mm = int(Decimal(str(geometry["depth_m"])) * 1000)
    except (ArithmeticError, KeyError, TypeError, ValueError):
        return None
    for rotation in rotations:
        if type(rotation) is not int or rotation not in (0, 90):
            return None
        world_width, world_depth = (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        if edge_class in ("LONG_EDGE", "LONG_EDGE_LOADING_FACE"):
            capacity = max(world_width, world_depth)
        elif edge_class in ("SHORT_EDGE", "SHORT_EDGE_EXIT_SIDE"):
            capacity = min(world_width, world_depth)
        else:
            capacity = max(world_width, world_depth)
        if capacity >= required_width_mm:
            return True
    return False


def _interface_preflight(
    binding: LayoutAuthorityBindingV1,
    intent: AccessCriticalConstructionIntentV1,
) -> dict[str, str]:
    requirements = {str(row.get("identity")): row for row in binding.access_requirements}
    status: dict[str, str] = {}
    for interface in intent.interfaces:
        requirement = requirements.get(interface.requirement_identity)
        endpoints_bound = bool(
            requirement
            and requirement.get("from_ref") == interface.from_ref
            and requirement.get("to_ref") == interface.to_ref
        )
        if not endpoints_bound:
            status[interface.interface_kind] = "UNKNOWN_NOT_PROVEN_IMPOSSIBLE"
        elif interface.interface_kind == "PERSONNEL_INGRESS_INTERFACE":
            entrance_length = sum(
                abs(first - second)
                for first, second in zip(
                    intent.main_entrance_segment_mm[0],
                    intent.main_entrance_segment_mm[1],
                    strict=True,
                )
            )
            minimum_corridor = intent.main_entrance_corridor_half_width_mm * 2
            status[interface.interface_kind] = (
                "PASS_TO_SEARCH"
                if entrance_length >= minimum_corridor
                else "UNKNOWN_NOT_PROVEN_IMPOSSIBLE"
            )
        elif interface.interface_kind == "PACKAGING_SORTING_STRAIGHT_INTERFACE":
            source_capacity = _dimension_has_portal_capacity(
                binding.dimension_authorities[interface.from_ref],
                interface.from_edge_class,
                interface.portal_clear_width_mm or 0,
            )
            target_capacity = _dimension_has_portal_capacity(
                binding.dimension_authorities[interface.to_ref],
                interface.to_edge_class,
                interface.portal_clear_width_mm or 0,
            )
            status[interface.interface_kind] = (
                "UNKNOWN_NOT_PROVEN_IMPOSSIBLE"
                if source_capacity is None or target_capacity is None
                else (
                    "PASS_TO_SEARCH"
                    if source_capacity and target_capacity
                    else "PROVABLY_NO_AUTHORITY_PORTAL_CAPACITY"
                )
            )
        elif interface.interface_kind in (
            "SECONDARY_SORTING_ACCESS_INTERFACE",
            "FROZEN_SORTING_ACCESS_INTERFACE",
        ):
            source_capacity = _dimension_has_portal_capacity(
                binding.dimension_authorities[interface.from_ref],
                None,
                interface.portal_clear_width_mm or 0,
            )
            target_capacity = _dimension_has_portal_capacity(
                binding.dimension_authorities[interface.to_ref],
                None,
                interface.portal_clear_width_mm or 0,
            )
            status[interface.interface_kind] = (
                "UNKNOWN_NOT_PROVEN_IMPOSSIBLE"
                if source_capacity is None or target_capacity is None
                else (
                    "PASS_TO_SEARCH"
                    if source_capacity and target_capacity
                    else "PROVABLY_NO_AUTHORITY_PORTAL_CAPACITY"
                )
            )
        elif interface.interface_kind == "SHIPPING_TRUCK_MANEUVER_INTERFACE":
            status[interface.interface_kind] = (
                "PASS_TO_SEARCH"
                if intent.truck_dock_point_events
                else "UNKNOWN_NOT_PROVEN_IMPOSSIBLE"
            )
        else:
            status[interface.interface_kind] = "PASS_TO_SEARCH"
    return status


def _geometry_signature(zones: Mapping[str, PlacedRectangleV1]) -> str:
    return canonical_hash({role: list(zones[role].bounds_mm) for role in sorted(zones)})


def _truck_necessary_preflight(
    zones: Mapping[str, PlacedRectangleV1],
    intent: AccessCriticalConstructionIntentV1,
    site_body: Mapping[str, Any],
) -> dict[str, Any]:
    site = site_body.get("site")
    shipping = zones.get("shipping_channel")
    if not isinstance(site, Mapping) or shipping is None:
        return {
            "status": "PROVABLY_NO_BASIC_MANEUVER_CAPACITY",
            "truck_validated": False,
            "reason": "MISSING_SHIPPING_OR_VALIDATED_SITE",
        }
    loading_side, loading_segment, _score, _comparison = _loading_face(shipping, site_body)
    start = (int(loading_segment[0][0]), int(loading_segment[0][1]))
    end = (int(loading_segment[1][0]), int(loading_segment[1][1]))
    point_events_on_face = [
        event
        for event in intent.truck_dock_point_events
        if _point_on_segment(event.point_mm, start, end)
    ]
    has_necessary_dock_event = bool(point_events_on_face)
    return {
        "status": (
            "PASS_TO_TRUCK_SEARCH"
            if has_necessary_dock_event
            else "PROVABLY_NO_BASIC_MANEUVER_CAPACITY"
        ),
        "truck_validated": False,
        "reason": None if has_necessary_dock_event else "NO_AUTHORITY_DOCK_POSE_ON_LOADING_FACE",
        "loading_face_side": loading_side,
        "loading_face_segment_mm": [list(start), list(end)],
        "truck_entrance_segment_mm": [
            list(intent.truck_entrance_segment_mm[0]),
            list(intent.truck_entrance_segment_mm[1]),
        ],
        "authoritative_dock_event_count": len(intent.truck_dock_point_events),
        "dock_events_on_loading_face": len(point_events_on_face),
        "no_build_obstacle_count": len(site_body.get("obstacles", {}).get("hard_obstacles", [])),
        "placed_zone_count": len(zones),
        "construction_preflight_is_truck_authority": False,
    }


def _point_on_segment(point: tuple[int, int], start: tuple[int, int], end: tuple[int, int]) -> bool:
    px, py = point
    ax, ay = start
    bx, by = end
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    return cross == 0 and min(ax, bx) <= px <= max(ax, bx) and min(ay, by) <= py <= max(ay, by)


def search_access_aware_composition_placements(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: ZoneDimensioningResultV1 | Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    truck_maneuver_binding: BoundTruckManeuverProjectInputV1 | Mapping[str, Any],
    *,
    node_budget: int = DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET,
    route_node_budget: int = DEFAULT_ROUTE_NODE_BUDGET,
    truck_node_budget: int = TRUCK_NODE_BUDGET,
) -> AccessAwareCompositionPlacementResultV1:
    """Replay authority, build with access intents, and validate complete checkpoints.

    The only geometry construction path is the composition-native engine.
    Every completed hard-subset candidate is retained and assessed by the
    existing 11 non-Truck Access predicates; Access score affects ranking only
    after geometry exists. Truck preflight follows that ranking and cannot
    prune complete candidates. Full P2D is independently replayed only for a
    selected 11/11 non-Truck candidate with a permissive necessary preflight.
    """
    if node_budget != DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET:
        raise ValueError("COMPOSITION_PLACEMENT_NODE_BUDGET_FROZEN")
    if route_node_budget != DEFAULT_ROUTE_NODE_BUDGET:
        raise ValueError("ACCESS_ROUTE_NODE_BUDGET_FROZEN")
    if truck_node_budget != TRUCK_NODE_BUDGET:
        raise ValueError("TRUCK_NODE_BUDGET_FROZEN")
    binding = bind_layout_authority(canonical_zone_plan, p1_handoff, site_geometry)
    composition_result = build_structural_compositions(
        canonical_zone_plan, p1_handoff, site_geometry
    )
    _assert_server_replay(composition_result, binding)
    intent = build_access_critical_construction_intent(
        canonical_zone_plan, p1_handoff, site_geometry, truck_maneuver_binding
    )
    boundary, obstacles, entrances = _site_validation_context(site_geometry)
    relationships = {
        str(row["identity"]): dict(row)
        for row in binding.spatial_relationships
        if isinstance(row.get("identity"), str)
    }
    non_truck = tuple(
        sorted(
            (row for row in binding.access_requirements if row.get("flow_kind") != "TRUCK"),
            key=lambda row: str(row.get("identity")),
        )
    )
    truck_binding_source = truck_maneuver_binding
    if isinstance(truck_binding_source, BoundTruckManeuverProjectInputV1):
        bound_truck = BoundTruckManeuverProjectInputV1.from_mapping(truck_binding_source.to_dict())
    else:
        bound_truck = BoundTruckManeuverProjectInputV1.from_mapping(truck_binding_source)
    assessment_rows: list[dict[str, Any]] = []

    def assess_complete_candidate(
        handoff: Any,
        zones: Mapping[str, PlacedRectangleV1],
        bank_sign: int,
        search_order_lane: str,
        nodes_at_discovery: int,
    ) -> bool:
        signature = _geometry_signature(zones)
        route_results: list[dict[str, Any]] = []
        for requirement in non_truck:
            routed, _corridors = validate_access_requirement(
                requirement,
                relationships=relationships,
                zones=zones,
                boundary=boundary,
                obstacles=obstacles,
                entrances=entrances,
                route_node_budget=route_node_budget,
            )
            route_results.append(
                {
                    "requirement_identity": str(requirement.get("identity", "")),
                    "from_ref": str(requirement.get("from_ref", "")),
                    "to_ref": str(requirement.get("to_ref", "")),
                    "flow_kind": str(requirement.get("flow_kind", "")),
                    "route_shape_constraint": str(requirement.get("route_shape_constraint", "")),
                    **routed,
                }
            )
        pass_count = sum(row.get("status") == "PASS" for row in route_results)
        codes: Counter[str] = Counter(
            str(code)
            for row in route_results
            if row.get("status") != "PASS"
            for code in row.get("codes", [])
        )
        assessment_rows.append(
            {
                "candidate_geometry_hash": signature,
                "composition_identity": handoff.composition_identity,
                "composition_signature": handoff.composition_signature,
                "family": handoff.family.value,
                "process_axis": handoff.process_axis.value,
                "process_direction": handoff.process_direction.value,
                "bank_sign": bank_sign,
                "search_order_lane": search_order_lane,
                "nodes_at_discovery": nodes_at_discovery,
                "zone_bounds_mm": {
                    role: list(rectangle.bounds_mm) for role, rectangle in sorted(zones.items())
                },
                # Reaching a full candidate proves the unchanged CR1 straight
                # interface construction preflight passed for this packaging
                # placement; the Access authority result is recorded separately.
                "packaging_straight_construction_preflight_passed": True,
                "non_truck_access_requirement_count": len(non_truck),
                "non_truck_access_pass_count": pass_count,
                "non_truck_access_fail_count": len(non_truck) - pass_count,
                "access_results": route_results,
                "failure_code_counts": dict(sorted(codes.items())),
                "truck_preflight": {
                    "status": "NOT_RUN_UNTIL_NON_TRUCK_RANKING",
                    "truck_validated": False,
                    "construction_preflight_is_truck_authority": False,
                },
                "access_assessed_before_truck_preflight": True,
                "candidate_admitted_for_access_progress": pass_count > 7,
                "truck_preflight_complete_candidate_prune_count": 0,
            }
        )
        # A complete hard-subset geometry is always observable. Access score
        # affects ranking/admission only after construction; it must not turn a
        # complete candidate into a hidden DFS failure.
        return True

    placements = enumerate_domain_placements(
        composition_result.placement_handoffs,
        binding.dimension_authorities,
        site_geometry.to_dict(),
        source_zone_plan_hash=binding.canonical_zone_plan_hash,
        source_p1_handoff_hash=binding.p1_handoff_hash,
        source_site_geometry_hash=binding.site_geometry_hash,
        node_budget=node_budget,
        access_intent=intent,
        complete_candidate_admission=assess_complete_candidate,
    )

    assessed_candidates: list[tuple[CompositionPlacementCandidateV1, dict[str, Any]]] = []
    for candidate, original_row in zip(placements.candidates, assessment_rows, strict=True):
        zones = {zone.zone_code: zone for zone in candidate.zones}
        row = original_row
        if row["composition_identity"] != candidate.composition_identity or row[
            "candidate_geometry_hash"
        ] != _geometry_signature(zones):
            raise RuntimeError("COMPLETE_CANDIDATE_ASSESSMENT_REPLAY_MISMATCH")
        row["candidate_hash"] = candidate.canonical_result_hash
        row["search_provenance"] = dict(candidate.search_provenance)
        assessed_candidates.append((candidate, row))
    best_pair = max(
        assessed_candidates,
        key=lambda pair: (
            int(pair[1]["non_truck_access_pass_count"]),
            pair[1]["family"] == "LINEAR_BANDED",
            pair[1]["candidate_geometry_hash"],
            pair[1]["search_order_lane"],
        ),
        default=None,
    )
    admitted_pairs = [
        pair for pair in assessed_candidates if int(pair[1]["non_truck_access_pass_count"]) > 7
    ]
    selected_pair = max(
        admitted_pairs,
        key=lambda pair: (
            int(pair[1]["non_truck_access_pass_count"]),
            pair[1]["family"] == "LINEAR_BANDED",
            pair[1]["candidate_geometry_hash"],
            pair[1]["search_order_lane"],
        ),
        default=None,
    )
    selected_candidate = selected_pair[0] if selected_pair else None
    selected_assessment = selected_pair[1] if selected_pair else None
    best_candidate = best_pair[0] if best_pair else None
    best_assessment = best_pair[1] if best_pair else None
    truck_preflight: dict[str, Any] | None = None
    final_validation: Mapping[str, Any] | None = None
    truck_attempts = 0
    p2d_attempts = 0
    if selected_candidate is not None:
        truck_preflight = _truck_necessary_preflight(
            {zone.zone_code: zone for zone in selected_candidate.zones},
            intent,
            site_geometry.to_dict(),
        )
        if selected_assessment is not None:
            selected_assessment["truck_preflight"] = truck_preflight
        if (
            selected_assessment is not None
            and truck_preflight is not None
            and int(selected_assessment["non_truck_access_pass_count"])
            == NON_TRUCK_ACCESS_REQUIREMENT_COUNT
            and truck_preflight["status"] == "PASS_TO_TRUCK_SEARCH"
        ):
            adapted = _adapt_candidate_to_existing_placement(
                selected_candidate,
                dimension_authorities=binding.dimension_authorities,
                site_body=site_geometry.to_dict(),
                source_zone_plan_hash=binding.canonical_zone_plan_hash,
                source_p1_handoff_hash=binding.p1_handoff_hash,
                source_site_geometry_hash=binding.site_geometry_hash,
            )
            full = route_site_placement(
                canonical_zone_plan,
                p1_handoff,
                site_geometry,
                adapted,
                bound_truck,
                route_node_budget=route_node_budget,
                truck_node_budget=truck_node_budget,
            )
            final_validation = full.to_dict()
            truck_attempts = 1
            p2d_attempts = 1

    return AccessAwareCompositionPlacementResultV1(
        identity="access-aware-composition-placement@1.0.0",
        schema_version="1.0.0",
        source_zone_plan_hash=binding.canonical_zone_plan_hash,
        source_p1_handoff_hash=binding.p1_handoff_hash,
        source_site_geometry_hash=binding.site_geometry_hash,
        construction_intent=intent,
        construction_preflight=_interface_preflight(binding, intent),
        placements=placements,
        candidate_assessments=tuple(assessment_rows),
        complete_candidates_constructed=len(placements.candidates),
        complete_candidates_access_assessed=len(assessment_rows),
        candidates_admitted=len(admitted_pairs),
        candidates_selected=1 if selected_candidate is not None else 0,
        best_candidate_hash=(
            best_candidate.canonical_result_hash if best_candidate is not None else None
        ),
        selected_candidate_hash=(
            selected_candidate.canonical_result_hash if selected_candidate else None
        ),
        best_non_truck_access_pass_count=(
            int(best_assessment["non_truck_access_pass_count"]) if best_assessment else 0
        ),
        best_non_truck_access_fail_count=(
            int(best_assessment["non_truck_access_fail_count"]) if best_assessment else 11
        ),
        selected_non_truck_access_pass_count=(
            int(selected_assessment["non_truck_access_pass_count"]) if selected_assessment else 0
        ),
        selected_non_truck_access_fail_count=(
            int(selected_assessment["non_truck_access_fail_count"]) if selected_assessment else 11
        ),
        packaging_preflight_pass_partial_count=sum(
            attempt.packaging_preflight_pass_partial_count for attempt in placements.search_attempts
        ),
        packaging_preflight_pass_complete_candidate_count=sum(
            int(row["packaging_straight_construction_preflight_passed"]) for row in assessment_rows
        ),
        packaging_final_access_pass_candidate_count=sum(
            any(
                row.get("from_ref") == "packaging_material_storage"
                and row.get("to_ref") == "sorting_packaging_room"
                and row.get("status") == "PASS"
                for row in candidate_row["access_results"]
            )
            for candidate_row in assessment_rows
        ),
        truck_preflight_complete_candidate_prune_count=0,
        access_validation_attempts=len(assessment_rows),
        truck_validation_attempts=truck_attempts,
        p2d_validation_attempts=p2d_attempts,
        truck_preflight=truck_preflight,
        final_validation=final_validation,
        access_routing_performed=bool(assessment_rows),
        truck_validation_performed=truck_attempts > 0,
        p2d_performed=p2d_attempts > 0,
        project_layout_validated_claimed=bool(
            final_validation and final_validation.get("project_layout_validated") is True
        ),
    )


def replay_control_candidate(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: ZoneDimensioningResultV1 | Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    truck_maneuver_binding: BoundTruckManeuverProjectInputV1 | Mapping[str, Any],
    *,
    route_node_budget: int = DEFAULT_ROUTE_NODE_BUDGET,
    truck_node_budget: int = TRUCK_NODE_BUDGET,
) -> Mapping[str, Any]:
    """Replay the preserved S4 control candidate through its existing bridge."""
    result = validate_composition_candidate(
        canonical_zone_plan,
        p1_handoff,
        site_geometry,
        truck_maneuver_binding,
        "sha256:4a4b8f6695526ea0bd1cf30238ae4c7c45b35e6d9677b0c4bd8f98228e8f3c47",
        route_node_budget=route_node_budget,
        truck_node_budget=truck_node_budget,
    )
    return result.to_dict()
