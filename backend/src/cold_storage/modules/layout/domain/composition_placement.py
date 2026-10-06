"""Bounded rectangle placement constrained by whole-building composition intent.

This module produces exact rectangle candidates only.  Construction domains are
search organizers, not site/access/Truck engineering authorities.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from decimal import ROUND_CEILING, Decimal
from math import isqrt
from typing import Any

from cold_storage.modules.layout.domain.access_critical_construction import (
    AccessCriticalConstructionIntentV1,
)
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.composition_handoff import (
    StructuralCompositionPlacementHandoffV1,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    normalize_polygon,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
    rectangles_share_positive_edge,
    validate_flexible_candidate,
)
from cold_storage.modules.layout.domain.structural_composition import (
    CompositionFamilyV2,
    ProcessAxisV1,
    ProcessDirectionV1,
)

IDENTITY = "composition-constrained-exact-placement@1.0.0"
SCHEMA_VERSION = "1.0.0"
CONSTRUCTION_DOMAIN_IS_HARD_ENGINEERING_AUTHORITY = False
PLACEMENT_HARD_SCOPE = "SITE_DIMENSIONS_OVERLAP_MUST_ADJACENCY_ONLY"
ACCESS_STATUS = "PENDING_ROUTE_VALIDATION"
FAMILY_ORDER = (
    CompositionFamilyV2.LINEAR_BANDED,
    CompositionFamilyV2.CENTRAL_PROCESS_CORE,
    CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS,
)
DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET = 60_000
MAX_COMPOSITION_PLACEMENT_NODE_BUDGET = DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET
GRID_MM = 1
GENERIC_FALLBACK_ANCHOR_LIMIT_PER_ROLE = 24
ACCESS_VALIDATION_CHECKPOINTS_PER_FAMILY = 3
MAIN_CHAIN_SOURCE = "EXISTING_PROCESS_GRAPH"
FORWARD_CHECK_ENGINEERING_AUTHORITY = False
FORWARD_CHECK_VALIDATION_AUTHORITY = False
FORWARD_CHECK_IS_OPTIMISTIC = True
UNKNOWN_FORWARD_CHECK_CAN_PRUNE = False
FORWARD_CHECK_BUDGET_EXHAUSTION_CAN_PRUNE = False
FORWARD_CHECK_ATTEMPT_SLICE_DIVISOR = 4
# Capacity-consuming branches and Shipping are probed once a meaningful
# main-chain prefix is fixed; chain holes use a separate late checkpoint.
FORWARD_CHECK_TRIGGER_ROLES = frozenset(
    {
        "packaging_material_storage",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "changing_room",
        "office",
        "shipping_channel",
    }
)


@dataclass(frozen=True)
class ConstructionDomainV1:
    """Finite event-derived search domain for one band or peripheral domain."""

    domain_id: str
    zone_roles: tuple[str, ...]
    domain_kind: str
    reference_axis: str
    preferred_interval_mm: tuple[int, int] | None
    preferred_face: str
    origin_event_policy: str
    engineering_authority: bool = False


@dataclass(frozen=True)
class CompositionPlacementCandidateV1:
    identity: str
    schema_version: str
    composition_identity: str
    composition_signature: str
    family: CompositionFamilyV2
    process_axis: ProcessAxisV1
    process_direction: ProcessDirectionV1
    zones: tuple[PlacedRectangleV1, ...]
    zone_count: int
    placement_scope: str
    hard_constraints_passed: bool
    site_valid: bool
    dimension_valid: bool
    non_overlap_valid: bool
    must_adjacency_valid: bool
    must_adjacency_satisfied_count: int
    composition_intent_preserved: bool
    construction_domains: tuple[ConstructionDomainV1, ...]
    source_zone_plan_hash: str
    source_p1_handoff_hash: str
    source_site_geometry_hash: str
    search_provenance: tuple[tuple[str, str], ...]
    access_validation_status: str = ACCESS_STATUS
    access_routing_performed: bool = False
    truck_validation_performed: bool = False
    p2d_performed: bool = False
    project_layout_validated_claimed: bool = False
    p2_complete_claimed: bool = False
    legacy_fallback_used: bool = False

    def __post_init__(self) -> None:
        roles = tuple(zone.zone_code for zone in self.zones)
        if self.identity != IDENTITY or self.schema_version != SCHEMA_VERSION:
            raise ValueError("UNSUPPORTED_COMPOSITION_PLACEMENT_CANDIDATE")
        if len(roles) != len(ZONE_CODES) or set(roles) != set(ZONE_CODES):
            raise ValueError("COMPOSITION_PLACEMENT_ROLE_COVERAGE_INVALID")
        if len(set(roles)) != len(roles) or self.zone_count != len(roles):
            raise ValueError("COMPOSITION_PLACEMENT_ROLE_DUPLICATE")
        if self.placement_scope != PLACEMENT_HARD_SCOPE:
            raise ValueError("COMPOSITION_PLACEMENT_SCOPE_INVALID")
        if not all(
            (
                self.hard_constraints_passed,
                self.site_valid,
                self.dimension_valid,
                self.non_overlap_valid,
                self.must_adjacency_valid,
                self.composition_intent_preserved,
            )
        ):
            raise ValueError("COMPOSITION_PLACEMENT_CANDIDATE_NOT_HARD_VALID")
        if self.must_adjacency_satisfied_count != len(process_graph().must_adjacencies):
            raise ValueError("COMPOSITION_PLACEMENT_MUST_ADJACENCY_INVALID")
        if any(domain.engineering_authority for domain in self.construction_domains):
            raise ValueError("CONSTRUCTION_DOMAIN_AUTHORITY_FORBIDDEN")
        if (
            self.access_validation_status != ACCESS_STATUS
            or self.access_routing_performed
            or self.truck_validation_performed
            or self.p2d_performed
            or self.project_layout_validated_claimed
            or self.p2_complete_claimed
            or self.legacy_fallback_used
        ):
            raise ValueError("COMPOSITION_PLACEMENT_SCOPE_VIOLATION")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["zones"] = [zone.to_dict() for zone in self.zones]
        result["family"] = self.family.value
        result["process_axis"] = self.process_axis.value
        result["process_direction"] = self.process_direction.value
        return result

    @property
    def canonical_result_hash(self) -> str:
        return canonical_hash(self.to_dict())


@dataclass(frozen=True)
class CompositionPlacementSearchAttemptV1:
    family: CompositionFamilyV2
    composition_identity: str
    composition_signature: str
    process_axis: ProcessAxisV1
    process_direction: ProcessDirectionV1
    peripheral_bank_sign: int
    search_order_lane: str
    access_critical_construction_intent_identity: str | None
    construction_domains: tuple[ConstructionDomainV1, ...]
    nodes_allocated: int
    nodes_visited: int
    primary_search_nodes_used: int
    forward_check_nodes_used: int
    forward_check_attempt_node_limit: int
    forward_check_regular_nodes_used: int
    forward_check_chain_hole_nodes_used: int
    forward_check_regular_node_limit: int
    forward_check_chain_hole_node_limit: int
    forward_check_invocation_count: int
    forward_check_pass_count: int
    forward_check_proved_no_completion_count: int
    forward_check_unknown_budget_count: int
    forward_check_unknown_other_count: int
    forward_check_cache_hit_count: int
    forward_check_unique_partial_signature_count: int
    forward_check_sequence_hash: str
    chain_starvation_prune_count_by_trigger_role: tuple[tuple[str, int], ...]
    packaging_local_pass_chain_forward_fail_count: int
    packaging_local_pass_chain_forward_pass_count: int
    secondary_local_pass_chain_forward_fail_count: int
    frozen_local_pass_chain_forward_fail_count: int
    personnel_local_pass_chain_forward_fail_count: int
    forward_check_witnesses: tuple[Mapping[str, Any], ...]
    forward_check_negative_proofs: tuple[Mapping[str, Any], ...]
    deepest_role_attempted: str
    deepest_role_successfully_placed: str
    max_simultaneously_placed_role_count: int
    role_search_funnel: tuple[RoleSearchFunnelV1, ...]
    domain_derived_anchor_count_by_role: tuple[tuple[str, int], ...]
    generic_fallback_anchor_count_by_role: tuple[tuple[str, int], ...]
    generic_fallback_node_count_by_role: tuple[tuple[str, int], ...]
    authority_shape_variant_count_by_role: tuple[tuple[str, int], ...]
    construction_shape_variant_count_by_role: tuple[tuple[str, int], ...]
    shipping_office_interface_preflight_status: str
    shipping_truck_preflight_status: str
    shipping_truck_preflight_counts: tuple[tuple[str, int], ...]
    packaging_preflight_pass_partial_count: int
    packaging_preflight_fail_partial_count: int
    band_capacity_preflight_status: str
    peripheral_capacity_preflight_status: str
    best_partial_placement_witness: PartialPlacementWitnessV1
    node_budget_exhausted: bool
    complete_layout_found: bool
    failure_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "family": self.family.value,
            "composition_identity": self.composition_identity,
            "composition_signature": self.composition_signature,
            "process_axis": self.process_axis.value,
            "process_direction": self.process_direction.value,
            "peripheral_bank_sign": self.peripheral_bank_sign,
            "search_order_lane": self.search_order_lane,
            "access_critical_construction_intent_identity": (
                self.access_critical_construction_intent_identity
            ),
            "construction_domains": [asdict(domain) for domain in self.construction_domains],
            "nodes_allocated": self.nodes_allocated,
            "nodes_visited": self.nodes_visited,
            "primary_search_nodes_used": self.primary_search_nodes_used,
            "forward_check_nodes_used": self.forward_check_nodes_used,
            "forward_check_attempt_node_limit": self.forward_check_attempt_node_limit,
            "forward_check_regular_nodes_used": self.forward_check_regular_nodes_used,
            "forward_check_chain_hole_nodes_used": self.forward_check_chain_hole_nodes_used,
            "forward_check_regular_node_limit": self.forward_check_regular_node_limit,
            "forward_check_chain_hole_node_limit": self.forward_check_chain_hole_node_limit,
            "forward_check_invocation_count": self.forward_check_invocation_count,
            "forward_check_pass_count": self.forward_check_pass_count,
            "forward_check_proved_no_completion_count": (
                self.forward_check_proved_no_completion_count
            ),
            "forward_check_unknown_budget_count": self.forward_check_unknown_budget_count,
            "forward_check_unknown_other_count": self.forward_check_unknown_other_count,
            "forward_check_cache_hit_count": self.forward_check_cache_hit_count,
            "forward_check_unique_partial_signature_count": (
                self.forward_check_unique_partial_signature_count
            ),
            "forward_check_sequence_hash": self.forward_check_sequence_hash,
            "chain_starvation_prune_count_by_trigger_role": dict(
                self.chain_starvation_prune_count_by_trigger_role
            ),
            "packaging_local_pass_chain_forward_fail_count": (
                self.packaging_local_pass_chain_forward_fail_count
            ),
            "packaging_local_pass_chain_forward_pass_count": (
                self.packaging_local_pass_chain_forward_pass_count
            ),
            "secondary_local_pass_chain_forward_fail_count": (
                self.secondary_local_pass_chain_forward_fail_count
            ),
            "frozen_local_pass_chain_forward_fail_count": (
                self.frozen_local_pass_chain_forward_fail_count
            ),
            "personnel_local_pass_chain_forward_fail_count": (
                self.personnel_local_pass_chain_forward_fail_count
            ),
            "forward_check_witnesses": [dict(item) for item in self.forward_check_witnesses],
            "forward_check_negative_proofs": [
                dict(item) for item in self.forward_check_negative_proofs
            ],
            "deepest_role_attempted": self.deepest_role_attempted,
            "deepest_role_successfully_placed": self.deepest_role_successfully_placed,
            "max_simultaneously_placed_role_count": self.max_simultaneously_placed_role_count,
            "role_search_funnel": [item.to_dict() for item in self.role_search_funnel],
            "domain_derived_anchor_count_by_role": dict(self.domain_derived_anchor_count_by_role),
            "generic_fallback_anchor_count_by_role": dict(
                self.generic_fallback_anchor_count_by_role
            ),
            "generic_fallback_used_by_role": {
                role: count > 0 for role, count in self.generic_fallback_node_count_by_role
            },
            "generic_fallback_node_count_by_role": dict(self.generic_fallback_node_count_by_role),
            "domain_derived_anchor_path_is_primary_by_role": {
                role: True for role, _ in self.domain_derived_anchor_count_by_role
            },
            "authority_shape_variant_count_by_role": dict(
                self.authority_shape_variant_count_by_role
            ),
            "construction_shape_variant_count_by_role": dict(
                self.construction_shape_variant_count_by_role
            ),
            "shipping_office_interface_preflight_status": (
                self.shipping_office_interface_preflight_status
            ),
            "packaging_preflight_pass_partial_count": (self.packaging_preflight_pass_partial_count),
            "packaging_preflight_fail_partial_count": (self.packaging_preflight_fail_partial_count),
            "band_capacity_preflight_status": self.band_capacity_preflight_status,
            "peripheral_capacity_preflight_status": self.peripheral_capacity_preflight_status,
            "best_partial_placement_witness": self.best_partial_placement_witness.to_dict(),
            "node_budget_exhausted": self.node_budget_exhausted,
            "complete_layout_found": self.complete_layout_found,
            "failure_reason": self.failure_reason,
        }
        if self.shipping_truck_preflight_status != "NOT_PERFORMED":
            result["shipping_truck_maneuver_necessary_preflight"] = {
                "status": self.shipping_truck_preflight_status,
                "counts": dict(self.shipping_truck_preflight_counts),
                "is_truck_authority": False,
            }
        return result


@dataclass(frozen=True)
class RoleSearchFunnelV1:
    zone_role: str
    role_attempt_count: int
    authority_shape_variant_count: int
    authority_rotation_variant_count: int
    construction_shape_variant_count: int
    shape_variant_attempt_count: int
    domain_derived_anchor_count: int
    generic_fallback_anchor_count: int
    candidate_rectangle_attempt_count: int
    site_rejection_count: int
    obstacle_rejection_count: int
    overlap_rejection_count: int
    domain_side_rejection_count: int
    must_edge_rejection_count: int
    coupled_interface_rejection_count: int
    composition_intent_rejection_count: int
    access_interface_rejection_count: int
    main_chain_forward_check_prune_count: int
    accepted_partial_placement_count: int
    backtrack_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_role": self.zone_role,
            "role_attempt_count": self.role_attempt_count,
            "authority_shape_variant_count": self.authority_shape_variant_count,
            "authority_rotation_variant_count": self.authority_rotation_variant_count,
            "construction_shape_variant_count": self.construction_shape_variant_count,
            "shape_variant_attempt_count": self.shape_variant_attempt_count,
            "domain_derived_anchor_count": self.domain_derived_anchor_count,
            "generic_fallback_anchor_count": self.generic_fallback_anchor_count,
            "candidate_rectangle_attempt_count": self.candidate_rectangle_attempt_count,
            "site_rejection_count": self.site_rejection_count,
            "obstacle_rejection_count": self.obstacle_rejection_count,
            "overlap_rejection_count": self.overlap_rejection_count,
            "domain_side_rejection_count": self.domain_side_rejection_count,
            "must_edge_rejection_count": self.must_edge_rejection_count,
            "coupled_interface_rejection_count": self.coupled_interface_rejection_count,
            "composition_intent_rejection_count": self.composition_intent_rejection_count,
            "access_interface_rejection_count": self.access_interface_rejection_count,
            "main_chain_forward_check_prune_count": self.main_chain_forward_check_prune_count,
            "accepted_partial_placement_count": self.accepted_partial_placement_count,
            "backtrack_count": self.backtrack_count,
        }


@dataclass(frozen=True)
class PartialPlacementWitnessV1:
    composition_identity: str
    placed_roles: tuple[str, ...]
    zone_bounds_mm: tuple[tuple[str, tuple[int, int, int, int]], ...]
    next_role: str
    failure_taxonomy: str
    hard_subset_rejection_count: int
    bank_sign: int
    nodes_used: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "composition_identity": self.composition_identity,
            "placed_roles": list(self.placed_roles),
            "zone_bounds_mm": {role: list(bounds) for role, bounds in self.zone_bounds_mm},
            "next_role": self.next_role,
            "failure_taxonomy": self.failure_taxonomy,
            "hard_subset_rejection_count": self.hard_subset_rejection_count,
            "bank_sign": self.bank_sign,
            "nodes_used": self.nodes_used,
            "is_complete_candidate": False,
        }


@dataclass
class _SearchDiagnostics:
    node_limit: int = 0
    forward_check_node_limit: int = -1
    forward_check_regular_node_limit: int = -1
    forward_check_chain_hole_node_limit: int = -1
    nodes: int = 0
    primary_search_nodes: int = 0
    forward_check_nodes: int = 0
    forward_check_regular_nodes: int = 0
    forward_check_chain_hole_nodes: int = 0
    budget_hit: bool = False
    deepest_attempted: str = "NOT_ATTEMPTED"
    deepest_successfully_placed: str = "NOT_PLACED"
    max_placed: int = 0
    generic_nodes: int = 0
    failure_taxonomy: str = "SEARCH_STARTED"
    shipping_office_status: str = "PASS_TO_SEARCH"
    shipping_truck_preflight_status: str = "NOT_PERFORMED"
    shipping_truck_preflight_counts: dict[str, int] = field(default_factory=dict)
    packaging_preflight_pass_partial_count: int = 0
    packaging_preflight_fail_partial_count: int = 0
    band_capacity_status: str = "UNKNOWN_NOT_PROVEN_IMPOSSIBLE"
    peripheral_capacity_status: str = "UNKNOWN_NOT_PROVEN_IMPOSSIBLE"
    best_witness: PartialPlacementWitnessV1 | None = None
    best_witness_key: tuple[int, int, tuple[tuple[str, tuple[int, int, int, int]], ...]] | None = (
        None
    )
    office_seed_by_shipping: dict[tuple[int, int, int, int], tuple[_Shape, tuple[int, int]]] = (
        field(default_factory=dict)
    )
    funnel: dict[str, dict[str, int]] = field(default_factory=dict)
    domain_anchor_count: dict[str, int] = field(default_factory=dict)
    generic_anchor_count: dict[str, int] = field(default_factory=dict)
    generic_nodes_by_role: dict[str, int] = field(default_factory=dict)
    authority_shape_count: dict[str, int] = field(default_factory=dict)
    construction_shape_count: dict[str, int] = field(default_factory=dict)
    complete_placements: list[tuple[dict[str, PlacedRectangleV1], int]] = field(
        default_factory=list
    )
    forward_check_cache: dict[str, _MainChainForwardCheckResultV1] = field(default_factory=dict)
    forward_check_signatures: set[str] = field(default_factory=set)
    forward_check_sequence: list[tuple[str, str, str, bool]] = field(default_factory=list)
    forward_check_invocation_count: int = 0
    forward_check_pass_count: int = 0
    forward_check_proved_no_completion_count: int = 0
    forward_check_unknown_budget_count: int = 0
    forward_check_unknown_other_count: int = 0
    forward_check_cache_hit_count: int = 0
    chain_starvation_prune_count_by_trigger_role: dict[str, int] = field(default_factory=dict)
    packaging_local_pass_chain_forward_fail_count: int = 0
    packaging_local_pass_chain_forward_pass_count: int = 0
    secondary_local_pass_chain_forward_fail_count: int = 0
    frozen_local_pass_chain_forward_fail_count: int = 0
    personnel_local_pass_chain_forward_fail_count: int = 0
    forward_check_witnesses: list[Mapping[str, Any]] = field(default_factory=list)
    forward_check_negative_proofs: list[Mapping[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.forward_check_node_limit < 0:
            self.forward_check_node_limit = (
                min(
                    self.node_limit,
                    max(1, self.node_limit // FORWARD_CHECK_ATTEMPT_SLICE_DIVISOR),
                )
                if self.node_limit
                else 0
            )
        category_limit = max(1, self.node_limit // 8) if self.node_limit else 0
        if self.forward_check_regular_node_limit < 0:
            self.forward_check_regular_node_limit = category_limit
        if self.forward_check_chain_hole_node_limit < 0:
            self.forward_check_chain_hole_node_limit = category_limit


@dataclass(frozen=True)
class _MainChainForwardCheckResultV1:
    status: str
    partial_geometry_hash: str
    fixed_main_chain_roles: tuple[str, ...]
    unplaced_main_chain_roles: tuple[str, ...]
    witness_role_order: tuple[str, ...]
    witness_zone_bounds_mm: tuple[tuple[str, tuple[int, int, int, int]], ...]
    probe_nodes_used: int
    first_unplaceable_role: str | None
    failure_taxonomy: str
    cache_hit: bool = False
    cached_probe_nodes: int = 0


@dataclass(frozen=True)
class _SearchOutcome:
    solution: dict[str, PlacedRectangleV1] | None
    diagnostics: _SearchDiagnostics
    deepest_attempted: str
    deepest_successfully_placed: str


@dataclass(frozen=True)
class CompositionPlacementEnumerationV1:
    identity: str
    schema_version: str
    node_budget: int
    nodes_used: int
    node_budget_exhausted: bool
    initial_family_budget: int
    continuation_budget: int
    continuation_selection_reason: str
    family_coverage_order: tuple[str, ...]
    family_first_round_complete: bool
    attempt_count_by_family: tuple[tuple[str, int], ...]
    nodes_used_by_family: tuple[tuple[str, int], ...]
    deepest_role_attempted_by_family: tuple[tuple[str, str], ...]
    deepest_role_successfully_placed_by_family: tuple[tuple[str, str], ...]
    max_simultaneously_placed_role_count_by_family: tuple[tuple[str, int], ...]
    best_partial_placement_witness_by_family: tuple[tuple[str, PartialPlacementWitnessV1], ...]
    domain_derived_anchor_count_by_family: tuple[tuple[str, int], ...]
    generic_fallback_anchor_count_by_family: tuple[tuple[str, int], ...]
    generic_fallback_node_count_by_family: tuple[tuple[str, int], ...]
    failure_reason_by_family: tuple[tuple[str, str], ...]
    search_attempts: tuple[CompositionPlacementSearchAttemptV1, ...]
    candidates: tuple[CompositionPlacementCandidateV1, ...]
    exact_placement_performed: bool = True
    access_routing_performed: bool = False
    truck_validation_performed: bool = False
    p2d_performed: bool = False
    project_layout_validated_claimed: bool = False

    def to_dict(self) -> dict[str, Any]:
        lane_counts: dict[str, int] = defaultdict(int)
        for attempt in self.search_attempts:
            lane_counts[attempt.search_order_lane] += 1
        primary_nodes = sum(item.primary_search_nodes_used for item in self.search_attempts)
        forward_nodes = sum(item.forward_check_nodes_used for item in self.search_attempts)
        forward_regular_nodes = sum(
            item.forward_check_regular_nodes_used for item in self.search_attempts
        )
        forward_chain_hole_nodes = sum(
            item.forward_check_chain_hole_nodes_used for item in self.search_attempts
        )
        trigger_prunes: dict[str, int] = defaultdict(int)
        for attempt in self.search_attempts:
            for role, count in attempt.chain_starvation_prune_count_by_trigger_role:
                trigger_prunes[role] += count
        return {
            "identity": self.identity,
            "schema_version": self.schema_version,
            "node_budget": self.node_budget,
            "nodes_used": self.nodes_used,
            "primary_search_nodes_used": primary_nodes,
            "forward_check_nodes_used": forward_nodes,
            "forward_check_regular_nodes_used": forward_regular_nodes,
            "forward_check_chain_hole_nodes_used": forward_chain_hole_nodes,
            "forward_check_regular_node_limit_total": sum(
                item.forward_check_regular_node_limit for item in self.search_attempts
            ),
            "forward_check_chain_hole_node_limit_total": sum(
                item.forward_check_chain_hole_node_limit for item in self.search_attempts
            ),
            "node_accounting_sum_valid": primary_nodes + forward_nodes == self.nodes_used,
            "node_budget_exhausted": self.node_budget_exhausted,
            "initial_family_budget": self.initial_family_budget,
            "continuation_budget": self.continuation_budget,
            "continuation_selection_reason": self.continuation_selection_reason,
            "family_coverage_order": list(self.family_coverage_order),
            "family_first_round_complete": self.family_first_round_complete,
            "attempt_count": len(self.search_attempts),
            "attempt_count_by_search_order_lane": dict(sorted(lane_counts.items())),
            "search_order_lanes_enabled": {
                "ACCESS_AWARE_ORDER": lane_counts.get("ACCESS_AWARE_ORDER", 0) > 0,
                "S3_COMPATIBILITY_ORDER": lane_counts.get("S3_COMPATIBILITY_ORDER", 0) > 0,
            },
            "search_order_is_engineering_authority": False,
            "legacy_placement_fallback_used": False,
            "main_chain_source": MAIN_CHAIN_SOURCE,
            "main_chain_authority_changed": False,
            "forward_check_engineering_authority": FORWARD_CHECK_ENGINEERING_AUTHORITY,
            "forward_check_validation_authority": FORWARD_CHECK_VALIDATION_AUTHORITY,
            "forward_check_is_optimistic": FORWARD_CHECK_IS_OPTIMISTIC,
            "forward_check_attempt_slice_divisor": FORWARD_CHECK_ATTEMPT_SLICE_DIVISOR,
            "forward_check_trigger_roles": sorted(FORWARD_CHECK_TRIGGER_ROLES),
            "unplaced_non_main_roles_ignored": True,
            "unknown_forward_check_can_prune": UNKNOWN_FORWARD_CHECK_CAN_PRUNE,
            "forward_check_budget_exhaustion_can_prune": (
                FORWARD_CHECK_BUDGET_EXHAUSTION_CAN_PRUNE
            ),
            "whole_building_completion_first_class_search_objective": True,
            "forward_check_invocation_count": sum(
                item.forward_check_invocation_count for item in self.search_attempts
            ),
            "forward_check_pass_count": sum(
                item.forward_check_pass_count for item in self.search_attempts
            ),
            "forward_check_proved_no_completion_count": sum(
                item.forward_check_proved_no_completion_count for item in self.search_attempts
            ),
            "forward_check_unknown_budget_count": sum(
                item.forward_check_unknown_budget_count for item in self.search_attempts
            ),
            "forward_check_unknown_other_count": sum(
                item.forward_check_unknown_other_count for item in self.search_attempts
            ),
            "forward_check_cache_hit_count": sum(
                item.forward_check_cache_hit_count for item in self.search_attempts
            ),
            "forward_check_unique_partial_signature_count": sum(
                item.forward_check_unique_partial_signature_count for item in self.search_attempts
            ),
            "chain_starvation_prune_count_by_trigger_role": dict(sorted(trigger_prunes.items())),
            "packaging_local_pass_chain_forward_fail_count": sum(
                item.packaging_local_pass_chain_forward_fail_count for item in self.search_attempts
            ),
            "packaging_local_pass_chain_forward_pass_count": sum(
                item.packaging_local_pass_chain_forward_pass_count for item in self.search_attempts
            ),
            "secondary_local_pass_chain_forward_fail_count": sum(
                item.secondary_local_pass_chain_forward_fail_count for item in self.search_attempts
            ),
            "frozen_local_pass_chain_forward_fail_count": sum(
                item.frozen_local_pass_chain_forward_fail_count for item in self.search_attempts
            ),
            "personnel_local_pass_chain_forward_fail_count": sum(
                item.personnel_local_pass_chain_forward_fail_count for item in self.search_attempts
            ),
            "forward_check_witnesses": [
                dict(row)
                for attempt in self.search_attempts
                for row in attempt.forward_check_witnesses
            ],
            "forward_check_negative_proofs": [
                dict(row)
                for attempt in self.search_attempts
                for row in attempt.forward_check_negative_proofs
            ],
            "forward_check_sequence_hashes": {
                f"{attempt.family.value}:{attempt.composition_identity}:"
                f"{attempt.peripheral_bank_sign}:{attempt.search_order_lane}": (
                    attempt.forward_check_sequence_hash
                )
                for attempt in self.search_attempts
            },
            "attempt_count_by_family": dict(self.attempt_count_by_family),
            "nodes_used_by_family": dict(self.nodes_used_by_family),
            "deepest_role_attempted_by_family": dict(self.deepest_role_attempted_by_family),
            "deepest_role_successfully_placed_by_family": dict(
                self.deepest_role_successfully_placed_by_family
            ),
            "max_simultaneously_placed_role_count_by_family": dict(
                self.max_simultaneously_placed_role_count_by_family
            ),
            "best_partial_placement_witness_by_family": {
                family: witness.to_dict()
                for family, witness in self.best_partial_placement_witness_by_family
            },
            "domain_derived_anchor_count_by_family": dict(
                self.domain_derived_anchor_count_by_family
            ),
            "generic_fallback_anchor_count_by_family": dict(
                self.generic_fallback_anchor_count_by_family
            ),
            "generic_fallback_node_count_by_family": dict(
                self.generic_fallback_node_count_by_family
            ),
            "failure_reason_by_family": dict(self.failure_reason_by_family),
            "search_attempts": [attempt.to_dict() for attempt in self.search_attempts],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "complete_candidates_constructed": len(self.candidates),
            "exact_placement_performed": self.exact_placement_performed,
            "access_routing_performed": self.access_routing_performed,
            "truck_validation_performed": self.truck_validation_performed,
            "p2d_performed": self.p2d_performed,
            "project_layout_validated_claimed": self.project_layout_validated_claimed,
        }


@dataclass(frozen=True)
class _Shape:
    width_mm: int
    depth_mm: int
    rotation_deg: int

    @property
    def world_width_mm(self) -> int:
        return self.depth_mm if self.rotation_deg == 90 else self.width_mm

    @property
    def world_depth_mm(self) -> int:
        return self.width_mm if self.rotation_deg == 90 else self.depth_mm


def _mm(value: object) -> int:
    number = Decimal(str(value))
    if (
        not number.is_finite()
        or number <= 0
        or number * 1000 != (number * 1000).to_integral_value()
    ):
        raise ValueError("INVALID_AUTHORITATIVE_DIMENSION")
    return int(number * 1000)


def _m(value: int) -> Decimal:
    return Decimal(value) / 1000


def _polygon_area_mm2(polygon: PolygonMM) -> int:
    return (
        abs(
            sum(
                first[0] * second[1] - second[0] * first[1]
                for first, second in zip(polygon, polygon[1:] + polygon[:1], strict=True)
            )
        )
        // 2
    )


def _authority_area_mm2(authority: Mapping[str, Any]) -> int:
    required = authority.get("required_area_m2")
    if required is not None:
        return int(Decimal(str(required)) * 1_000_000)
    geometry = authority.get("geometry")
    if not isinstance(geometry, Mapping):
        raise ValueError("DIMENSION_AUTHORITY_AREA_MISSING")
    return _mm(geometry.get("width_m")) * _mm(geometry.get("depth_m"))


def _capacity_preflight_status(
    role_groups: Sequence[Sequence[str]],
    authorities: Mapping[str, Mapping[str, Any]],
    authority_shapes: Mapping[str, Sequence[_Shape]],
    boundary: PolygonMM,
) -> str:
    """Apply only gross-area and bounding-box necessary capacity checks."""
    site_area = _polygon_area_mm2(boundary)
    min_x, max_x = min(point[0] for point in boundary), max(point[0] for point in boundary)
    min_y, max_y = min(point[1] for point in boundary), max(point[1] for point in boundary)
    bbox_width, bbox_depth = max_x - min_x, max_y - min_y
    for role_group in role_groups:
        roles = tuple(role_group)
        if not roles:
            continue
        if sum(_authority_area_mm2(authorities[role]) for role in roles) > site_area:
            return "PROVABLY_EXCEEDS_BUILDABLE_SITE_AREA"
        for role in roles:
            authority = authorities[role]
            if authority.get("dimension_mode") == "FLEXIBLE_RECTANGLE":
                # Area is the only lower bound here; flexible aspect semantics
                # stay owned by the authoritative dimension validator.
                continue
            if not any(
                shape.world_width_mm <= bbox_width and shape.world_depth_mm <= bbox_depth
                for shape in authority_shapes[role]
            ):
                return f"PROVABLY_NO_AUTHORIZED_ORIENTATION_FITS_SITE_BOUNDS:{role}"
    return "PASS_TO_SEARCH_GROSS_AREA_AND_SITE_BOUNDS"


def _shipping_office_interface_preflight_status(
    shipping_shapes: Sequence[_Shape],
    office_shapes: Sequence[_Shape],
    boundary: PolygonMM,
) -> str:
    """Check only whether any authorized shipping/office pair can share an edge
    inside the site bounding box.

    A possible pair is not a placement witness: concavity, obstacles, other
    rooms, and composition domains still belong to exact search. Rejection is
    safe only when no pair of allowed footprints can geometrically fit with a
    positive shared edge even in the larger site bounding box.
    """
    min_x, max_x = min(point[0] for point in boundary), max(point[0] for point in boundary)
    min_y, max_y = min(point[1] for point in boundary), max(point[1] for point in boundary)
    site_width, site_depth = max_x - min_x, max_y - min_y
    for shipping in shipping_shapes:
        shipping_width, shipping_depth = shipping.world_width_mm, shipping.world_depth_mm
        if shipping_width > site_width or shipping_depth > site_depth:
            continue
        for office in office_shapes:
            office_width, office_depth = office.world_width_mm, office.world_depth_mm
            if office_width > site_width or office_depth > site_depth:
                continue
            vertical_pair_fits = (
                shipping_width + office_width <= site_width
                and min(shipping_depth, office_depth) > 0
            )
            horizontal_pair_fits = (
                shipping_depth + office_depth <= site_depth
                and min(shipping_width, office_width) > 0
            )
            if vertical_pair_fits or horizontal_pair_fits:
                return "PASS_TO_SEARCH_SITE_BOUNDS_NECESSARY_CONDITION"
    return "PROVABLY_NO_SHARED_EDGE_CAPACITY_IN_SITE_BOUNDS"


def _shipping_office_candidate_preflight_status(
    shipping: PlacedRectangleV1,
    office_shapes: Sequence[_Shape],
    boundary: PolygonMM,
) -> str:
    """Conservatively check if Office can share any face with this Shipping.

    The site bounding box is intentionally permissive for non-rectangular
    boundaries. A negative result proves impossibility even in that larger box;
    a positive result only admits the exact Office search.
    """
    site_left = min(point[0] for point in boundary)
    site_bottom = min(point[1] for point in boundary)
    site_right = max(point[0] for point in boundary)
    site_top = max(point[1] for point in boundary)
    ship_left, ship_bottom, ship_right, ship_top = shipping.bounds_mm
    site_width, site_depth = site_right - site_left, site_top - site_bottom
    for shape in office_shapes:
        office_width, office_depth = shape.world_width_mm, shape.world_depth_mm
        if office_width > site_width or office_depth > site_depth:
            continue
        vertical_low = max(site_bottom, ship_bottom - office_depth + 1)
        vertical_high = min(site_top - office_depth, ship_top - 1)
        horizontal_low = max(site_left, ship_left - office_width + 1)
        horizontal_high = min(site_right - office_width, ship_right - 1)
        vertical_overlap_possible = vertical_low <= vertical_high
        horizontal_overlap_possible = horizontal_low <= horizontal_high
        if (
            (ship_left - office_width >= site_left and vertical_overlap_possible)
            or (ship_right + office_width <= site_right and vertical_overlap_possible)
            or (ship_bottom - office_depth >= site_bottom and horizontal_overlap_possible)
            or (ship_top + office_depth <= site_top and horizontal_overlap_possible)
        ):
            return "PASS_TO_SEARCH"
    return "PROVABLY_NO_SHARED_EDGE_CAPACITY_IN_SITE_BOUNDS"


def _rectangle(code: str, x: int, y: int, shape: _Shape) -> PlacedRectangleV1:
    return PlacedRectangleV1(
        code,
        _m(x),
        _m(y),
        _m(shape.width_mm),
        _m(shape.depth_mm),
        shape.rotation_deg,
    )


def _authority_shapes(
    authorities: Mapping[str, Mapping[str, Any]],
    boundary: PolygonMM,
    obstacle_polygons: Sequence[PolygonMM],
    access_intent: AccessCriticalConstructionIntentV1 | None = None,
) -> dict[str, tuple[_Shape, ...]]:
    spans = {
        abs(second[0] - first[0])
        for polygon in (boundary, *obstacle_polygons)
        for first, second in zip(polygon, polygon[1:] + polygon[:1], strict=True)
        if first[0] != second[0]
    }
    spans.update(
        abs(second[1] - first[1])
        for polygon in (boundary, *obstacle_polygons)
        for first, second in zip(polygon, polygon[1:] + polygon[:1], strict=True)
        if first[1] != second[1]
    )
    fixed_shapes: dict[str, tuple[int, int]] = {}
    for code, authority in authorities.items():
        geometry = authority.get("geometry")
        if authority.get("dimension_mode") == "FLEXIBLE_RECTANGLE":
            continue
        if not isinstance(geometry, Mapping):
            raise ValueError(f"DIMENSION_AUTHORITY_MISSING:{code}")
        fixed = (_mm(geometry.get("width_m")), _mm(geometry.get("depth_m")))
        fixed_shapes[code] = fixed
        spans.update(fixed)

    min_x, min_y = min(p[0] for p in boundary), min(p[1] for p in boundary)
    max_x, max_y = max(p[0] for p in boundary), max(p[1] for p in boundary)
    spans.update((max_x - min_x, max_y - min_y))
    shapes: dict[str, tuple[_Shape, ...]] = {}
    for code, authority in authorities.items():
        rotations = authority.get("rotation_allowed")
        if (
            not isinstance(rotations, list)
            or not rotations
            or any(type(rotation) is not int or rotation not in (0, 90) for rotation in rotations)
        ):
            raise ValueError(f"DIMENSION_AUTHORITY_ROTATION_INVALID:{code}")
        if authority.get("dimension_mode") != "FLEXIBLE_RECTANGLE":
            width, depth = fixed_shapes[code]
            shapes[code] = tuple(_Shape(width, depth, rotation) for rotation in rotations)
            continue
        required = Decimal(str(authority.get("required_area_m2")))
        required_mm2 = int(required * 1_000_000)
        near = isqrt(required_mm2)
        if near * near < required_mm2:
            near += 1
        widths = set(spans) | {near, near + 1}
        candidates: set[tuple[int, int]] = set()
        for width in widths:
            if width <= 0:
                continue
            for depth in widths:
                if depth <= 0:
                    continue
                try:
                    validate_flexible_candidate(authority, _m(width), _m(depth))
                except Exception as exc:
                    if (
                        getattr(exc, "code", None) == "INVALID_FLEXIBLE_DIMENSION"
                        or getattr(exc, "code", None) == "FLEXIBLE_DIMENSION_AREA_UNSATISFIED"
                    ):
                        continue
                    raise
                candidates.add((width, depth))
        if access_intent is not None and code == "changing_room":
            # The personnel authority's corridor width is a physical shape
            # event, not a new dimension rule. Validate the derived shape
            # through the existing flexible-area authority before admitting it.
            clear_width = access_intent.interface(
                "PERSONNEL_INGRESS_INTERFACE"
            ).corridor_clear_width_mm
            required_area_mm2 = required * Decimal(1_000_000)
            if clear_width is not None and clear_width > 0:
                long_span = int(
                    (required_area_mm2 / Decimal(clear_width)).to_integral_value(
                        rounding=ROUND_CEILING
                    )
                )
                for width, depth in ((long_span, clear_width), (clear_width, long_span)):
                    try:
                        validate_flexible_candidate(authority, _m(width), _m(depth))
                    except Exception as exc:
                        if getattr(exc, "code", None) in (
                            "INVALID_FLEXIBLE_DIMENSION",
                            "FLEXIBLE_DIMENSION_AREA_UNSATISFIED",
                        ):
                            continue
                        raise
                    candidates.add((width, depth))
        if not candidates:
            raise ValueError(f"FLEXIBLE_DIMENSION_DOMAIN_EMPTY:{code}")
        ordered = sorted(
            candidates, key=lambda pair: (abs(pair[0] - pair[1]), pair[0] * pair[1], pair)
        )
        shapes[code] = tuple(
            _Shape(width, depth, rotation) for width, depth in ordered for rotation in rotations
        )
    return shapes


def _canonical_construction_shapes(
    variants: Sequence[_Shape],
) -> tuple[_Shape, ...]:
    """Deduplicate equivalent world footprints without changing authority.

    Each retained item remains an authority-approved width/depth/rotation
    tuple.  This only removes construction-search variants that serialize
    differently but produce the same axis-aligned footprint.
    """
    by_footprint: dict[tuple[int, int], _Shape] = {}
    for shape in variants:
        by_footprint.setdefault((shape.world_width_mm, shape.world_depth_mm), shape)
    return tuple(
        by_footprint[key]
        for key in sorted(
            by_footprint,
            key=lambda pair: (
                abs(pair[0] - pair[1]),
                pair[0] * pair[1],
                max(pair),
                pair,
            ),
        )
    )


def _bounds(rect: PlacedRectangleV1) -> tuple[int, int, int, int]:
    return rect.bounds_mm


def _center(rect: PlacedRectangleV1, axis: str) -> int:
    left, bottom, right, top = _bounds(rect)
    return (left + right) // 2 if axis == "X" else (bottom + top) // 2


def _axis_events(
    *,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    placed: Mapping[str, PlacedRectangleV1],
    width: int,
    depth: int,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    xs = {point[0] for point in boundary}
    ys = {point[1] for point in boundary}
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    xs.update((min_x, max_x - width, (min_x + max_x - width) // 2))
    ys.update((min_y, max_y - depth, (min_y + max_y - depth) // 2))
    for polygon in obstacles:
        for x, y in polygon:
            # No-build predicates treat obstacle boundaries as closed.  The
            # exact legal event is therefore one grid unit beyond the edge;
            # this is a finite obstacle-derived event, not a coordinate sweep.
            xs.update(
                (
                    x - width - GRID_MM,
                    x - width,
                    x - width + GRID_MM,
                    x - GRID_MM,
                    x,
                    x + GRID_MM,
                )
            )
            ys.update(
                (
                    y - depth - GRID_MM,
                    y - depth,
                    y - depth + GRID_MM,
                    y - GRID_MM,
                    y,
                    y + GRID_MM,
                )
            )
        ox = [p[0] for p in polygon]
        oy = [p[1] for p in polygon]
        xs.update((min(ox) - width, max(ox), min(ox), max(ox) - width))
        ys.update((min(oy) - depth, max(oy), min(oy), max(oy) - depth))
    for rectangle in placed.values():
        left, bottom, right, top = _bounds(rectangle)
        xs.update((left - width, right, left, right - width))
        ys.update((bottom - depth, top, bottom, top - depth))
    return tuple(sorted(xs)), tuple(sorted(ys))


def _anchors_at_must_faces(
    code: str,
    shape: _Shape,
    placed: Mapping[str, PlacedRectangleV1],
    must_neighbors: Sequence[str],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
) -> tuple[tuple[int, int], ...]:
    anchors: set[tuple[int, int]] = set()
    width, depth = shape.world_width_mm, shape.world_depth_mm
    x_events, y_events = _axis_events(
        boundary=boundary,
        obstacles=obstacles,
        placed=placed,
        width=width,
        depth=depth,
    )
    for neighbor_code in must_neighbors:
        neighbor = placed[neighbor_code]
        left, bottom, right, top = _bounds(neighbor)
        y_values = {bottom, top - depth, (bottom + top - depth) // 2}
        y_values.update(y for y in y_events if y < top and y + depth > bottom)
        x_values = {left, right - width, (left + right - width) // 2}
        x_values.update(x for x in x_events if x < right and x + width > left)
        for y in y_values:
            anchors.update(((left - width, y), (right, y)))
        for x in x_values:
            anchors.update(((x, bottom - depth), (x, top)))
    return tuple(sorted(anchors))


def _domain_faces(
    handoff: StructuralCompositionPlacementHandoffV1, bank_sign: int
) -> dict[str, tuple[str, int]]:
    axis = handoff.process_axis.value
    cross_axis = "Y" if axis == "X" else "X"
    direction_sign = 1 if handoff.process_direction == ProcessDirectionV1.POSITIVE else -1
    result: dict[str, tuple[str, int]] = {}
    # Process-band side hints are ordering inputs only; group ordering remains
    # the composition-level predicate rather than a new room-by-room rule.
    result["raw_fruit_buffer"] = (axis, -direction_sign)
    result["primary_precooling_room"] = (axis, -direction_sign)
    result["finished_goods_room"] = (axis, direction_sign)
    result["shipping_channel"] = (axis, direction_sign)
    if handoff.family == CompositionFamilyV2.CENTRAL_PROCESS_CORE:
        result["packaging_material_storage"] = (axis, direction_sign)
        result["secondary_fruit_buffer"] = (cross_axis, bank_sign)
        result["frozen_fruit_room"] = (cross_axis, -bank_sign)
        result["changing_room"] = (axis, -direction_sign)
        result["office"] = (axis, -direction_sign)
    else:
        for role in (
            "packaging_material_storage",
            "secondary_fruit_buffer",
            "frozen_fruit_room",
        ):
            result[role] = (cross_axis, bank_sign)
        result["changing_room"] = (cross_axis, -bank_sign)
        result["office"] = (cross_axis, -bank_sign)
    return result


def _domain_arrangement(
    handoff: StructuralCompositionPlacementHandoffV1,
    bank_sign: int,
    boundary: PolygonMM,
    authorities: Mapping[str, Mapping[str, Any]],
) -> tuple[ConstructionDomainV1, ...]:
    axis = handoff.process_axis.value
    cross_axis = "Y" if axis == "X" else "X"
    min_x, max_x = min(p[0] for p in boundary), max(p[0] for p in boundary)
    min_y, max_y = min(p[1] for p in boundary), max(p[1] for p in boundary)
    span = (max_x - min_x) if axis == "X" else (max_y - min_y)
    all_bands = tuple(handoff.principal_band_intents)
    ordered_bands = sorted(
        (item for item in all_bands if item.sequence_index is not None),
        key=lambda item: int(item.sequence_index or 0),
    )
    band_areas = []
    for band in ordered_bands:
        area = sum(
            int(Decimal(str(authorities[role].get("required_area_m2", 0))) * 1_000_000)
            for role in band.zone_roles
        )
        band_areas.append((band, max(1, area)))
    total_area = sum(area for _, area in band_areas) or 1
    cursor = min_x if axis == "X" else min_y
    end = max_x if axis == "X" else max_y
    domains: list[ConstructionDomainV1] = []
    cumulative = 0
    for band, area in band_areas:
        low = cursor + (span * cumulative // total_area)
        cumulative += area
        high = cursor + (span * cumulative // total_area)
        if band == band_areas[-1][0]:
            high = end
        domains.append(
            ConstructionDomainV1(
                domain_id=band.band_id,
                zone_roles=band.zone_roles,
                domain_kind="ORDERED_PRINCIPAL_BAND",
                reference_axis=axis,
                preferred_interval_mm=(low, high),
                preferred_face=band.relative_position,
                origin_event_policy=(
                    "AUTHORITATIVE_DIMENSION_AREA_WEIGHTED_SITE_EVENT_INTERVAL;"
                    "PRIORITY_ONLY_WITH_FULL_SITE_EVENT_FALLBACK"
                ),
            )
        )
    if handoff.process_direction == ProcessDirectionV1.NEGATIVE:
        reflected: list[ConstructionDomainV1] = []
        for domain in domains:
            interval = domain.preferred_interval_mm
            if interval is None:
                reflected.append(domain)
                continue
            low, high = interval
            reflected.append(
                ConstructionDomainV1(
                    domain_id=domain.domain_id,
                    zone_roles=domain.zone_roles,
                    domain_kind=domain.domain_kind,
                    reference_axis=domain.reference_axis,
                    preferred_interval_mm=(min_x + max_x - high, min_x + max_x - low)
                    if axis == "X"
                    else (min_y + max_y - high, min_y + max_y - low),
                    preferred_face=domain.preferred_face,
                    origin_event_policy=domain.origin_event_policy,
                    engineering_authority=domain.engineering_authority,
                )
            )
        domains = reflected
    for band in all_bands:
        if band.sequence_index is not None:
            continue
        domains.append(
            ConstructionDomainV1(
                domain_id=band.band_id,
                zone_roles=band.zone_roles,
                domain_kind="NONSEQUENTIAL_CORE_OR_PERIPHERAL_FACE_DOMAIN",
                reference_axis=axis,
                preferred_interval_mm=None,
                preferred_face=band.relative_position,
                origin_event_policy="COMPOSITION_FACE_AND_SITE_ROOM_EDGE_EVENTS",
            )
        )
    faces = _domain_faces(handoff, bank_sign)
    for peripheral_intent in handoff.peripheral_domain_intents:
        preferred = next(
            (
                ("POSITIVE" if sign > 0 else "NEGATIVE") + f"_{ref_axis}"
                for role, (ref_axis, sign) in faces.items()
                if role in peripheral_intent.zone_roles
            ),
            peripheral_intent.relative_side,
        )
        domains.append(
            ConstructionDomainV1(
                domain_id=peripheral_intent.domain_id,
                zone_roles=peripheral_intent.zone_roles,
                domain_kind="RESERVED_PERIPHERAL_SEARCH_DOMAIN",
                reference_axis=next(
                    (faces[role][0] for role in peripheral_intent.zone_roles if role in faces),
                    cross_axis,
                ),
                preferred_interval_mm=None,
                preferred_face=preferred,
                origin_event_policy=(
                    "COMPOSITION_FACE_RELATION_WITH_SITE_OBSTACLE_ROOM_EDGE_EVENTS"
                ),
            )
        )
    return tuple(domains)


def _preferred_access_bank_sign(
    handoff: StructuralCompositionPlacementHandoffV1,
    intent: AccessCriticalConstructionIntentV1,
) -> int:
    """Choose an alternate peripheral side from the validated entrance side."""
    entrance_faces = intent.face_order("changing_room")
    if not entrance_faces:
        return 1
    side = entrance_faces[0]
    side_axis = "X" if side in ("EAST", "WEST") else "Y"
    cross_axis = "Y" if handoff.process_axis.value == "X" else "X"
    if side_axis != cross_axis:
        return 1
    entrance_sign = 1 if side in ("EAST", "NORTH") else -1
    if handoff.family == CompositionFamilyV2.CENTRAL_PROCESS_CORE:
        return entrance_sign
    # In the linear and spine families, personnel occupy the opposite bank
    # from the room-face sign used by the domain relation.
    return -entrance_sign


def _side_ok(
    role: str,
    rectangle: PlacedRectangleV1,
    sorting: PlacedRectangleV1,
    faces: Mapping[str, tuple[str, int]],
) -> bool:
    if role not in {
        "packaging_material_storage",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "changing_room",
        "office",
    }:
        return True
    side = faces.get(role)
    if side is None:
        return True
    axis, sign = side
    delta = _center(rectangle, axis) - _center(sorting, axis)
    return delta * sign > 0


def _candidate_is_clear(
    candidate: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
) -> bool:
    if not rectangle_inside_polygon(candidate, boundary):
        return False
    if any(rectangle_intersects_closed_obstacle(candidate, obstacle) for obstacle in obstacles):
        return False
    return not any(rectangles_overlap(candidate, existing) for existing in placed.values())


def _packaging_straight_interface_possible(
    packaging: PlacedRectangleV1,
    sorting: PlacedRectangleV1,
    intent: AccessCriticalConstructionIntentV1,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    placed: Mapping[str, PlacedRectangleV1],
) -> bool:
    """Conservatively preflight the frozen straight-only interface geometry."""
    interface = intent.interface("PACKAGING_SORTING_STRAIGHT_INTERFACE")
    portal_width = interface.portal_clear_width_mm
    corridor_width = interface.corridor_clear_width_mm
    if portal_width is None or corridor_width is None:
        return True

    package_left, package_bottom, package_right, package_top = packaging.bounds_mm
    sorting_left, sorting_bottom, sorting_right, sorting_top = sorting.bounds_mm
    candidates: list[tuple[str, str, int, int, int, int]] = []
    if package_right <= sorting_left:
        candidates.append(
            (
                "EAST",
                "WEST",
                sorting_left - package_right,
                max(package_bottom, sorting_bottom),
                min(package_top, sorting_top),
                package_right,
            )
        )
    if sorting_right <= package_left:
        candidates.append(
            (
                "WEST",
                "EAST",
                package_left - sorting_right,
                max(package_bottom, sorting_bottom),
                min(package_top, sorting_top),
                sorting_right,
            )
        )
    if package_top <= sorting_bottom:
        candidates.append(
            (
                "NORTH",
                "SOUTH",
                sorting_bottom - package_top,
                max(package_left, sorting_left),
                min(package_right, sorting_right),
                package_top,
            )
        )
    if sorting_top <= package_bottom:
        candidates.append(
            (
                "SOUTH",
                "NORTH",
                package_bottom - sorting_top,
                max(package_left, sorting_left),
                min(package_right, sorting_right),
                sorting_top,
            )
        )

    for package_side, sorting_side, gap, cross_low, cross_high, normal_start in candidates:
        package_class = _edge_class_for_side(
            package_right - package_left, package_top - package_bottom, package_side
        )
        sorting_class = _edge_class_for_side(
            sorting_right - sorting_left, sorting_top - sorting_bottom, sorting_side
        )
        required_from = interface.from_edge_class
        required_to = interface.to_edge_class
        if required_to == "SHORT_EDGE_EXIT_SIDE":
            required_to = "SHORT_EDGE"
        if (required_from is not None and package_class != required_from) or (
            required_to is not None and sorting_class != required_to
        ):
            continue
        if cross_high - cross_low < portal_width:
            continue
        if gap == 0:
            return True

        center = (cross_low + cross_high) // 2
        if package_side in ("EAST", "WEST"):
            channel = _rectangle(
                "__packaging_straight_preflight__",
                normal_start,
                center - corridor_width // 2,
                _Shape(gap, corridor_width, 0),
            )
        else:
            channel = _rectangle(
                "__packaging_straight_preflight__",
                center - corridor_width // 2,
                normal_start,
                _Shape(corridor_width, gap, 0),
            )
        if not rectangle_inside_polygon(channel, boundary):
            continue
        if any(rectangle_intersects_closed_obstacle(channel, obstacle) for obstacle in obstacles):
            continue
        if any(
            rectangles_overlap(channel, rectangle)
            for role, rectangle in placed.items()
            if role not in ("packaging_material_storage", "sorting_packaging_room")
        ):
            continue
        return True
    return False


def _must_neighbors(code: str) -> tuple[str, ...]:
    return tuple(
        second if first == code else first
        for first, second in process_graph().must_adjacencies
        if code in (first, second)
    )


def _axis_coordinate(rectangle: PlacedRectangleV1, axis: str) -> int:
    return _center(rectangle, axis)


def _intent_preserved(
    handoff: StructuralCompositionPlacementHandoffV1,
    placed: Mapping[str, PlacedRectangleV1],
    faces: Mapping[str, tuple[str, int]],
) -> bool:
    axis = handoff.process_axis.value
    sign = 1 if handoff.process_direction == ProcessDirectionV1.POSITIVE else -1
    sorting = placed["sorting_packaging_room"]
    if any(not _side_ok(role, placed[role], sorting, faces) for role in faces):
        return False
    raw_center = (
        sum(
            _axis_coordinate(placed[role], axis)
            for role in ("raw_fruit_buffer", "primary_precooling_room")
        )
        // 2
    )
    finished_center = (
        sum(
            _axis_coordinate(placed[role], axis)
            for role in ("finished_goods_room", "shipping_channel")
        )
        // 2
    )
    core_center = (
        sum(
            _axis_coordinate(placed[role], axis)
            for role in ("sorting_packaging_room", "secondary_precooling_room", "coating_room")
        )
        // 3
    )
    if handoff.family == CompositionFamilyV2.LINEAR_BANDED:
        return (raw_center - core_center) * sign < 0 and (finished_center - core_center) * sign > 0
    if handoff.family == CompositionFamilyV2.CENTRAL_PROCESS_CORE:
        return (raw_center - _center(sorting, axis)) * sign < 0 and (
            finished_center - _center(sorting, axis)
        ) * sign > 0
    flow = (
        "raw_fruit_buffer",
        "primary_precooling_room",
        "sorting_packaging_room",
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )
    projections = [sign * _axis_coordinate(placed[role], axis) for role in flow]
    return all(first <= second for first, second in zip(projections, projections[1:], strict=False))


def _partial_intent_possible(
    handoff: StructuralCompositionPlacementHandoffV1,
    placed: Mapping[str, PlacedRectangleV1],
    faces: Mapping[str, tuple[str, int]],
) -> bool:
    sorting = placed.get("sorting_packaging_room")
    if sorting is None:
        return True
    if any(
        not _side_ok(role, rectangle, sorting, faces)
        for role, rectangle in placed.items()
        if role in faces
    ):
        return False
    axis = handoff.process_axis.value
    sign = 1 if handoff.process_direction == ProcessDirectionV1.POSITIVE else -1

    def group_center(roles: Sequence[str]) -> int:
        return sum(_axis_coordinate(placed[role], axis) for role in roles) // len(roles)

    raw_roles = ("raw_fruit_buffer", "primary_precooling_room")
    core_roles = ("sorting_packaging_room", "secondary_precooling_room", "coating_room")
    finished_roles = ("finished_goods_room", "shipping_channel")
    if handoff.family == CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS:
        flow = (
            "raw_fruit_buffer",
            "primary_precooling_room",
            "sorting_packaging_room",
            "secondary_precooling_room",
            "coating_room",
            "finished_goods_room",
            "shipping_channel",
        )
        placed_flow = [
            sign * _axis_coordinate(placed[role], axis) for role in flow if role in placed
        ]
        return all(
            first <= second for first, second in zip(placed_flow, placed_flow[1:], strict=False)
        )
    if all(role in placed for role in raw_roles) and all(role in placed for role in core_roles):
        raw_center, core_center = group_center(raw_roles), group_center(core_roles)
        if handoff.family == CompositionFamilyV2.LINEAR_BANDED:
            if (raw_center - core_center) * sign >= 0:
                return False
        elif (raw_center - _center(sorting, axis)) * sign >= 0:
            return False
    if all(role in placed for role in finished_roles) and all(
        role in placed for role in core_roles
    ):
        finished_center, core_center = group_center(finished_roles), group_center(core_roles)
        if handoff.family == CompositionFamilyV2.LINEAR_BANDED:
            return (finished_center - core_center) * sign > 0
        return (finished_center - _center(sorting, axis)) * sign > 0
    return True


def _zone_order(
    handoff: StructuralCompositionPlacementHandoffV1,
    *,
    access_aware: bool = False,
    search_order_lane: str | None = None,
) -> tuple[str, ...]:
    # The lanes change variable ordering only. Both may run with CR1 access
    # intents, anchors, dimensions, site/overlap checks, and MUST predicates.
    lane = search_order_lane or ("ACCESS_AWARE_ORDER" if access_aware else "S3_COMPATIBILITY_ORDER")
    if lane == "ACCESS_AWARE_ORDER":
        return (
            "sorting_packaging_room",
            "packaging_material_storage",
            # Keep a finite entrance-facing personnel footprint available
            # before the support branches consume the site edge.
            "changing_room",
            "primary_precooling_room",
            "raw_fruit_buffer",
            "secondary_precooling_room",
            "secondary_fruit_buffer",
            "frozen_fruit_room",
            "shipping_channel",
            # Build the attached finished/process bridge before selecting the
            # personnel Office attachment. This leaves the existing hard
            # Shipping/Finished MUST edge available while keeping the coupled
            # Shipping/Office preflight early; Office itself remains an
            # independent zone searched after the process bridge. All roles
            # remain in the same whole-building composition DFS.
            "coating_room",
            "finished_goods_room",
            "office",
        )
    if lane != "S3_COMPATIBILITY_ORDER":
        raise ValueError("COMPOSITION_SEARCH_ORDER_LANE_INVALID")
    return (
        "sorting_packaging_room",
        "primary_precooling_room",
        "raw_fruit_buffer",
        "secondary_precooling_room",
        "packaging_material_storage",
        "coating_room",
        "finished_goods_room",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "changing_room",
        "shipping_channel",
        "office",
    )


def _composition_shape_order(
    handoff: StructuralCompositionPlacementHandoffV1,
    shapes: Mapping[str, tuple[_Shape, ...]],
    bank_sign: int,
    access_intent: AccessCriticalConstructionIntentV1 | None = None,
) -> dict[str, tuple[_Shape, ...]]:
    """Order authoritative variants toward their assigned composition band axis.

    This does not remove or alter an authority-approved dimension/orientation.
    It prevents the first bounded search slice from spending its nodes on a
    footprint whose long axis consumes the scarce process or peripheral span.
    Flexible authority variants keep their existing compact-first order.
    """
    faces = _domain_faces(handoff, bank_sign)
    result: dict[str, tuple[_Shape, ...]] = {}
    for role, variants in shapes.items():
        if access_intent is not None and role == "changing_room":
            start, end = access_intent.main_entrance_segment_mm
            entrance_span = abs((end[1] - start[1]) or (end[0] - start[0]))
            vertical_entrance = start[0] == end[0]
            result[role] = tuple(
                sorted(
                    variants,
                    key=lambda shape: (
                        abs(
                            (shape.world_depth_mm if vertical_entrance else shape.world_width_mm)
                            - entrance_span
                        ),
                        shape.world_width_mm * shape.world_depth_mm,
                        shape.world_width_mm,
                        shape.world_depth_mm,
                        shape.rotation_deg,
                    ),
                )
            )
            continue
        if len(variants) != 2:
            result[role] = variants
            continue
        if access_intent is not None and role == "sorting_packaging_room":
            result[role] = tuple(
                sorted(
                    variants,
                    key=lambda shape: (
                        0
                        if shape.world_width_mm >= shape.world_depth_mm
                        and any(
                            package.world_depth_mm > package.world_width_mm
                            for package in shapes["packaging_material_storage"]
                        )
                        else 1,
                        abs(shape.world_width_mm - shape.world_depth_mm),
                        shape.rotation_deg,
                    ),
                )
            )
            continue
        if access_intent is not None and role == "packaging_material_storage":
            sorting = result.get("sorting_packaging_room", shapes["sorting_packaging_room"])[0]
            vertical_sorting_short_face = sorting.world_width_mm >= sorting.world_depth_mm
            result[role] = tuple(
                sorted(
                    variants,
                    key=lambda shape: (
                        0
                        if (shape.world_depth_mm > shape.world_width_mm)
                        == vertical_sorting_short_face
                        else 1,
                        shape.rotation_deg,
                    ),
                )
            )
            continue
        if access_intent is not None and role == "shipping_channel":
            entrance_start, entrance_end = access_intent.truck_entrance_segment_mm
            entrance_is_vertical = entrance_start[0] == entrance_end[0]
            result[role] = tuple(
                sorted(
                    variants,
                    key=lambda shape: (
                        0
                        if (shape.world_depth_mm >= shape.world_width_mm) == entrance_is_vertical
                        else 1,
                        shape.rotation_deg,
                    ),
                )
            )
            continue
        axis = faces.get(role, (handoff.process_axis.value, 1))[0]
        if role == "sorting_packaging_room":
            # Family topology determines the useful core footprint: linear and
            # spine families align the long face with the process axis, while a
            # central core keeps the short face on that axis so opposite
            # process-side domains remain available around the organizer.
            central_core = handoff.family == CompositionFamilyV2.CENTRAL_PROCESS_CORE
            result[role] = tuple(
                sorted(
                    variants,
                    key=lambda shape: (
                        (shape.world_width_mm if axis == "X" else shape.world_depth_mm)
                        * (1 if central_core else -1),
                        shape.rotation_deg,
                    ),
                )
            )
            continue
        result[role] = tuple(
            sorted(
                variants,
                key=lambda shape: (
                    shape.world_width_mm if axis == "X" else shape.world_depth_mm,
                    shape.world_depth_mm if axis == "X" else shape.world_width_mm,
                    shape.rotation_deg,
                ),
            )
        )
    return result


def _domain_interval(
    role: str,
    handoff: StructuralCompositionPlacementHandoffV1,
    domains: Sequence[ConstructionDomainV1],
) -> tuple[str, tuple[int, int] | None]:
    assignment = next(item for item in handoff.zone_role_assignment if item.zone_role == role)
    for domain in domains:
        if domain.domain_id == assignment.composition_band:
            return domain.reference_axis, domain.preferred_interval_mm
    return handoff.process_axis.value, None


def _interval_origin_events(
    interval: tuple[int, int] | None,
    extent: int,
) -> tuple[int, ...]:
    if interval is None:
        return ()
    low, high = interval
    return tuple(sorted({low, low + (high - low - extent) // 2, high - extent}))


def _face_anchors(
    base: PlacedRectangleV1,
    shape: _Shape,
    axis: str,
    sign: int,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    placed: Mapping[str, PlacedRectangleV1],
) -> set[tuple[int, int]]:
    """Finite edge-event origins on a composition-selected face."""
    left, bottom, right, top = _bounds(base)
    width, depth = shape.world_width_mm, shape.world_depth_mm
    xs, ys = _axis_events(
        boundary=boundary,
        obstacles=obstacles,
        placed=placed,
        width=width,
        depth=depth,
    )
    result: set[tuple[int, int]] = set()
    if axis == "X":
        x = right if sign > 0 else left - width
        cross_events = {
            bottom,
            top - depth,
            (bottom + top - depth) // 2,
            *(event for event in ys if event < top and event + depth > bottom),
        }
        for y in cross_events:
            result.add((x, y))
    else:
        y = top if sign > 0 else bottom - depth
        cross_events = {
            left,
            right - width,
            (left + right - width) // 2,
            *(event for event in xs if event < right and event + width > left),
        }
        for x in cross_events:
            result.add((x, y))
    return result


def _edge_class_for_side(width: int, depth: int, side: str) -> str:
    horizontal = side in ("NORTH", "SOUTH")
    horizontal_class = "LONG_EDGE" if width >= depth else "SHORT_EDGE"
    if horizontal:
        return horizontal_class
    return "SHORT_EDGE" if horizontal_class == "LONG_EDGE" else "LONG_EDGE"


def _side_event_origins(
    base: PlacedRectangleV1,
    shape: _Shape,
    side: str,
    *,
    gap_mm: int = 0,
) -> tuple[tuple[int, int], ...]:
    """Finite low/center/high placements on or at an offset from one face."""
    left, bottom, right, top = _bounds(base)
    width, depth = shape.world_width_mm, shape.world_depth_mm
    if side in ("WEST", "EAST"):
        x = left - width - gap_mm if side == "WEST" else right + gap_mm
        low, high = bottom, top
        extent = depth
        return tuple(
            sorted(
                {
                    (x, low),
                    (x, high - extent),
                    (x, (low + high - extent) // 2),
                }
            )
        )
    y = bottom - depth - gap_mm if side == "SOUTH" else top + gap_mm
    low, high = left, right
    extent = width
    return tuple(
        sorted(
            {
                (low, y),
                (high - extent, y),
                ((low + high - extent) // 2, y),
            }
        )
    )


def _access_interface_anchors(
    role: str,
    shape: _Shape,
    handoff: StructuralCompositionPlacementHandoffV1,
    intent: AccessCriticalConstructionIntentV1,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    bank_sign: int,
) -> tuple[tuple[int, int], ...]:
    """Generate finite authority-event origins for access-critical endpoints.

    These are search seeds only.  The injected final Access/Truck authorities
    still decide whether any generated placement is admissible.
    """
    result: set[tuple[int, int]] = set()
    width, depth = shape.world_width_mm, shape.world_depth_mm
    if role == "changing_room":
        start, end = intent.main_entrance_segment_mm
        min_x, max_x = min(point[0] for point in boundary), max(point[0] for point in boundary)
        min_y, max_y = min(point[1] for point in boundary), max(point[1] for point in boundary)
        interface = intent.interface("PERSONNEL_INGRESS_INTERFACE")
        clear_width = interface.corridor_clear_width_mm or 0
        low_y, high_y = sorted((start[1], end[1]))
        low_x, high_x = sorted((start[0], end[0]))
        y_events = {low_y, high_y - depth, (low_y + high_y - depth) // 2}
        x_events = {low_x, high_x - width, (low_x + high_x - width) // 2}
        sorting = placed.get("sorting_packaging_room")
        if sorting is not None:
            left, bottom, right, top = sorting.bounds_mm
            y_events.update((bottom, top - depth, (bottom + top - depth) // 2))
            x_events.update((left, right - width, (left + right - width) // 2))
        personnel_face = _domain_faces(handoff, bank_sign).get(role)
        if personnel_face is None:
            return ()
        axis, sign = personnel_face
        personnel_side = (
            ("WEST" if sign < 0 else "EAST") if axis == "X" else ("SOUTH" if sign < 0 else "NORTH")
        )
        entrance_side: str | None = None
        if start[0] == end[0] and start[0] in (min_x, max_x):
            entrance_side = "WEST" if start[0] == min_x else "EAST"
        elif start[1] == end[1] and start[1] in (min_y, max_y):
            entrance_side = "SOUTH" if start[1] == min_y else "NORTH"

        # Site/boundary and room-face events place personnel in its assigned
        # composition domain; entrance events align the candidate set but do
        # not force a direct or straight route across the product building.
        if axis == "X":
            boundary_x = min_x if sign < 0 else max_x - width
            result.update((boundary_x, y) for y in y_events)
        else:
            boundary_y = min_y if sign < 0 else max_y - depth
            result.update((x, boundary_y) for x in x_events)
        if sorting is not None:
            for gap in (clear_width, 0):
                result.update(_side_event_origins(sorting, shape, personnel_side, gap_mm=gap))
        if entrance_side == personnel_side:
            if entrance_side in ("WEST", "EAST"):
                for gap in (clear_width, 0):
                    x = min_x + gap if entrance_side == "WEST" else max_x - width - gap
                    result.update((x, y) for y in y_events)
            else:
                for gap in (clear_width, 0):
                    y = min_y + gap if entrance_side == "SOUTH" else max_y - depth - gap
                    result.update((x, y) for x in x_events)
        return tuple(sorted(result))

    sorting = placed.get("sorting_packaging_room")
    if (
        role
        in (
            "packaging_material_storage",
            "secondary_fruit_buffer",
            "frozen_fruit_room",
        )
        and sorting is not None
    ):
        interface_kind = {
            "packaging_material_storage": "PACKAGING_SORTING_STRAIGHT_INTERFACE",
            "secondary_fruit_buffer": "SECONDARY_SORTING_ACCESS_INTERFACE",
            "frozen_fruit_room": "FROZEN_SORTING_ACCESS_INTERFACE",
        }[role]
        interface = intent.interface(interface_kind)
        for side in ("NORTH", "SOUTH", "EAST", "WEST"):
            for gap in (0, interface.corridor_clear_width_mm or 0):
                if role == "packaging_material_storage" and gap == 0:
                    package_class = _edge_class_for_side(width, depth, side)
                    sorting_class = _edge_class_for_side(
                        sorting.bounds_mm[2] - sorting.bounds_mm[0],
                        sorting.bounds_mm[3] - sorting.bounds_mm[1],
                        {"NORTH": "SOUTH", "SOUTH": "NORTH", "EAST": "WEST", "WEST": "EAST"}[side],
                    )
                    required_from = interface.from_edge_class
                    required_to = interface.to_edge_class
                    if required_to == "SHORT_EDGE_EXIT_SIDE":
                        required_to = "SHORT_EDGE"
                    if required_from is not None and package_class != required_from:
                        continue
                    if required_to is not None and sorting_class != required_to:
                        continue
                result.update(_side_event_origins(sorting, shape, side, gap_mm=gap))
        return tuple(sorted(result))

    if role == "shipping_channel":
        # Dock-point events are transformed from bound DOCK_REVERSE templates;
        # align the candidate's long face to each event, without claiming a
        # Truck route or PASS.
        for event in intent.truck_dock_point_events:
            px, py = event.point_mm
            if depth >= width:
                for x in (px, px - width):
                    result.update((x, y) for y in (py, py - depth, py - depth // 2))
            else:
                for y in (py, py - depth):
                    result.update((x, y) for x in (px, px - width, px - width // 2))
        if "finished_goods_room" in placed:
            result = {
                point
                for point in result
                if any(
                    rectangles_share_positive_edge(
                        _rectangle("shipping_channel", point[0], point[1], shape),
                        placed[neighbor],
                    )
                    for neighbor in _must_neighbors("shipping_channel")
                    if neighbor in placed
                )
            }
        return tuple(sorted(result))
    return ()


def _domain_derived_anchors(
    role: str,
    shape: _Shape,
    handoff: StructuralCompositionPlacementHandoffV1,
    domains: Sequence[ConstructionDomainV1],
    bank_sign: int,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    access_intent: AccessCriticalConstructionIntentV1 | None = None,
) -> tuple[tuple[int, int], ...]:
    """Construct a bounded role domain from composition and physical events.

    MUST neighbors are used as authoritative attachment events where present;
    branch and personnel roles are instead seeded from their assigned domain
    face relative to Sorting and already-placed members of that bank.
    """
    width, depth = shape.world_width_mm, shape.world_depth_mm
    neighbors = tuple(name for name in _must_neighbors(role) if name in placed)
    if neighbors:
        must_face_anchors = set(
            _anchors_at_must_faces(role, shape, placed, neighbors, boundary, obstacles)
        )
        axis, interval = _domain_interval(role, handoff, domains)
        if interval is not None:
            # The primary domain is an actual finite subset, not merely an
            # ordering preference. Out-of-band MUST-face events remain
            # available through the bounded generic physical-event fallback.
            band_low, band_high = interval

            def center_in_band(point: tuple[int, int]) -> bool:
                projection = point[0] + width // 2 if axis == "X" else point[1] + depth // 2
                return band_low <= projection <= band_high

            must_face_anchors = {point for point in must_face_anchors if center_in_band(point)}
        if access_intent is not None:
            must_face_anchors.update(
                _access_interface_anchors(
                    role, shape, handoff, access_intent, placed, boundary, bank_sign
                )
            )
            must_face_anchors = {
                point
                for point in must_face_anchors
                if any(
                    rectangles_share_positive_edge(
                        _rectangle(role, point[0], point[1], shape), placed[neighbor]
                    )
                    for neighbor in neighbors
                )
            }
        return tuple(sorted(must_face_anchors))

    if role == "sorting_packaging_room":
        axis, interval = _domain_interval(role, handoff, domains)
        min_x, max_x = min(point[0] for point in boundary), max(point[0] for point in boundary)
        min_y, max_y = min(point[1] for point in boundary), max(point[1] for point in boundary)
        x_events, y_events = _axis_events(
            boundary=boundary,
            obstacles=obstacles,
            placed=placed,
            width=width,
            depth=depth,
        )
        longitudinal = _interval_origin_events(interval, width if axis == "X" else depth)
        if not longitudinal:
            physical_axis_events = x_events if axis == "X" else y_events
            axis_low = min_x if axis == "X" else min_y
            axis_high = max_x - width if axis == "X" else max_y - depth
            eligible = tuple(
                event for event in physical_axis_events if axis_low <= event <= axis_high
            )
            midpoint = (axis_low + axis_high) // 2
            ranked = sorted(eligible, key=lambda event: (abs(event - midpoint), event))
            longitudinal = tuple(sorted({axis_low, axis_high, *ranked[:12]}))
        cross = (
            {
                min_y,
                max_y - depth,
                (min_y + max_y - depth) // 2,
                *(y for y in y_events if min_y <= y <= max_y - depth),
            }
            if axis == "X"
            else {
                min_x,
                max_x - width,
                (min_x + max_x - width) // 2,
                *(x for x in x_events if min_x <= x <= max_x - width),
            }
        )
        pairs = (
            {(event, cross_event) for event in longitudinal for cross_event in cross}
            if axis == "X"
            else {(cross_event, event) for event in longitudinal for cross_event in cross}
        )
        return tuple(sorted(pairs))

    interface_anchors: set[tuple[int, int]] = set()
    if access_intent is not None:
        # Access-critical events augment the composition face domain; they do
        # not replace it. This preserves the S3 composition-native search space
        # while still prioritizing CR1 endpoint-derived anchors. Every
        # Packaging candidate continues through the unchanged straight-only
        # preflight below, and final Access remains independently authoritative.
        interface_anchors.update(
            _access_interface_anchors(
                role, shape, handoff, access_intent, placed, boundary, bank_sign
            )
        )

    face = _domain_faces(handoff, bank_sign).get(role)
    if face is None:
        return tuple(sorted(interface_anchors))
    axis, sign = face
    sorting = placed.get("sorting_packaging_room")
    if sorting is None:
        return tuple(sorted(interface_anchors))
    bases = [sorting]
    for other_role, rectangle in placed.items():
        if other_role == "sorting_packaging_room":
            continue
        other_face = _domain_faces(handoff, bank_sign).get(other_role)
        if other_face == face:
            bases.append(rectangle)
    face_anchors: set[tuple[int, int]] = set()
    for base in bases:
        face_anchors.update(_face_anchors(base, shape, axis, sign, boundary, obstacles, placed))
    face_anchors.update(interface_anchors)
    return tuple(sorted(face_anchors))


def _generic_fallback_anchors(
    role: str,
    shape: _Shape,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    *,
    limit: int | None = GENERIC_FALLBACK_ANCHOR_LIMIT_PER_ROLE,
) -> tuple[tuple[int, int], ...]:
    neighbors = tuple(name for name in _must_neighbors(role) if name in placed)
    if neighbors:
        anchors = _anchors_at_must_faces(role, shape, placed, neighbors, boundary, obstacles)
    else:
        width, depth = shape.world_width_mm, shape.world_depth_mm
        xs, ys = _axis_events(
            boundary=boundary,
            obstacles=obstacles,
            placed=placed,
            width=width,
            depth=depth,
        )
        min_x, max_x = min(point[0] for point in boundary), max(point[0] for point in boundary)
        min_y, max_y = min(point[1] for point in boundary), max(point[1] for point in boundary)
        center_x = (min_x + max_x - width) // 2
        center_y = (min_y + max_y - depth) // 2
        anchors_set = {
            (min_x, min_y),
            (max_x - width, min_y),
            (min_x, max_y - depth),
            (max_x - width, max_y - depth),
            (center_x, center_y),
            *((x, center_y) for x in xs),
            *((center_x, y) for y in ys),
            *((x, y) for x, y in zip(xs, ys, strict=False)),
        }
        anchors = tuple(sorted(anchors_set))
    return anchors if limit is None else anchors[:limit]


def _packaging_interface_capacity_remains(
    handoff: StructuralCompositionPlacementHandoffV1,
    shapes: Mapping[str, tuple[_Shape, ...]],
    intent: AccessCriticalConstructionIntentV1,
    domains: Sequence[ConstructionDomainV1],
    bank_sign: int,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
) -> bool:
    """Return whether a finite, still-clear Packaging interface seed remains.

    This is a conservative construction look-ahead used only before the
    Packaging role has been placed.  It reuses the same finite domain and
    physical-event anchor generators as placement and the existing
    straight-interface construction preflight; it neither reserves geometry
    as engineering authority nor asserts an Access PASS.
    """
    sorting = placed.get("sorting_packaging_room")
    if sorting is None:
        return True
    role = "packaging_material_storage"
    for shape in shapes[role]:
        domain_origins = _domain_derived_anchors(
            role,
            shape,
            handoff,
            domains,
            bank_sign,
            placed,
            boundary,
            obstacles,
            intent,
        )
        generic_origins = _generic_fallback_anchors(role, shape, placed, boundary, obstacles)
        for x, y in (*domain_origins, *generic_origins):
            package = _rectangle(role, x, y, shape)
            if _candidate_rejection(package, placed, boundary, obstacles) is not None:
                continue
            if not _side_ok(role, package, sorting, _domain_faces(handoff, bank_sign)):
                continue
            if _packaging_straight_interface_possible(
                package,
                sorting,
                intent,
                boundary,
                obstacles,
                placed,
            ):
                return True
    return False


def _candidate_rejection(
    candidate: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
) -> str | None:
    if not rectangle_inside_polygon(candidate, boundary):
        return "SITE"
    if any(rectangle_intersects_closed_obstacle(candidate, obstacle) for obstacle in obstacles):
        return "OBSTACLE"
    if any(rectangles_overlap(candidate, existing) for existing in placed.values()):
        return "OVERLAP"
    return None


def _main_chain_roles_from_process_graph() -> tuple[str, ...]:
    """Read the ordered mandatory material chain from the existing graph."""
    material_flows = tuple(flow for flow in process_graph().flows if flow.kind == "MATERIAL")
    if not material_flows:
        return ()
    roles = [material_flows[0].from_ref]
    for flow in material_flows:
        if roles[-1] != flow.from_ref:
            return ()
        roles.append(flow.to_ref)
    return tuple(roles)


def _optimistic_main_chain_completion_probe(
    handoff: StructuralCompositionPlacementHandoffV1,
    shapes: Mapping[str, tuple[_Shape, ...]],
    domains: Sequence[ConstructionDomainV1],
    bank_sign: int,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    access_intent: AccessCriticalConstructionIntentV1 | None,
    diagnostics: _SearchDiagnostics,
    trigger_role: str,
    *,
    chain_hole: bool = False,
) -> _MainChainForwardCheckResultV1:
    """Probe an optimistic finite completion of only the existing MATERIAL chain.

    This is construction-search pruning only.  A negative result is returned
    only after every event-derived candidate in the probe's union domain has
    been exhausted.  A shared-slice limit or incomplete input is UNKNOWN.
    """
    chain = _main_chain_roles_from_process_graph()
    fixed_chain = tuple(role for role in chain if role in placed)
    unplaced_chain = tuple(role for role in chain if role not in placed)
    signature = canonical_hash(
        {
            "composition_identity": handoff.composition_identity,
            "composition_signature": handoff.composition_signature,
            "bank_sign": bank_sign,
            "fixed_geometry": {role: list(_bounds(placed[role])) for role in sorted(placed)},
            "main_chain": list(chain),
        }
    )
    diagnostics.forward_check_invocation_count += 1
    diagnostics.forward_check_signatures.add(signature)
    cached = diagnostics.forward_check_cache.get(signature)
    if cached is not None:
        result = replace(
            cached,
            probe_nodes_used=0,
            cache_hit=True,
            cached_probe_nodes=cached.probe_nodes_used,
        )
        diagnostics.forward_check_cache_hit_count += 1
    elif not chain or any(role not in shapes for role in unplaced_chain):
        result = _MainChainForwardCheckResultV1(
            status="UNKNOWN_INCOMPLETE_PROOF",
            partial_geometry_hash=signature,
            fixed_main_chain_roles=fixed_chain,
            unplaced_main_chain_roles=unplaced_chain,
            witness_role_order=(),
            witness_zone_bounds_mm=(),
            probe_nodes_used=0,
            first_unplaceable_role=None,
            failure_taxonomy="MAIN_CHAIN_OR_AUTHORITY_SHAPES_INCOMPLETE",
        )
    else:
        chain_adjacencies = process_graph().must_adjacencies
        fixed_must_conflict = next(
            (
                (first, second)
                for first, second in chain_adjacencies
                if first in placed
                and second in placed
                and not rectangles_share_positive_edge(placed[first], placed[second])
            ),
            None,
        )
        if fixed_must_conflict is not None:
            first, second = fixed_must_conflict
            result = _MainChainForwardCheckResultV1(
                status="PROVED_NO_MAIN_CHAIN_COMPLETION_IN_CURRENT_SEARCH_DOMAIN",
                partial_geometry_hash=signature,
                fixed_main_chain_roles=fixed_chain,
                unplaced_main_chain_roles=unplaced_chain,
                witness_role_order=(),
                witness_zone_bounds_mm=(),
                probe_nodes_used=0,
                first_unplaceable_role=second,
                failure_taxonomy=f"FIXED_MUST_EDGE_CONFLICT:{first}:{second}",
            )
            diagnostics.forward_check_cache[signature] = result
        elif not unplaced_chain:
            result = _MainChainForwardCheckResultV1(
                status="PASS_TO_SEARCH",
                partial_geometry_hash=signature,
                fixed_main_chain_roles=fixed_chain,
                unplaced_main_chain_roles=(),
                witness_role_order=(),
                witness_zone_bounds_mm=(),
                probe_nodes_used=0,
                first_unplaceable_role=None,
                failure_taxonomy="ALL_MAIN_CHAIN_ROLES_ALREADY_FIXED",
            )
            diagnostics.forward_check_cache[signature] = result
        else:
            probe_placed = dict(placed)
            witness_order: list[str] = []
            witness_bounds: dict[str, tuple[int, int, int, int]] = {}
            failure_counts_by_role: dict[str, Counter[str]] = defaultdict(Counter)
            exhausted_roles: set[str] = set()
            nodes_before = diagnostics.nodes
            forward_nodes_before = diagnostics.forward_check_nodes
            category_node_limit = (
                diagnostics.forward_check_chain_hole_node_limit
                if chain_hole
                else diagnostics.forward_check_regular_node_limit
            )
            category_nodes_used = (
                diagnostics.forward_check_chain_hole_nodes
                if chain_hole
                else diagnostics.forward_check_regular_nodes
            )
            forward_slice_remaining = max(
                0,
                diagnostics.forward_check_node_limit - diagnostics.forward_check_nodes,
            )
            category_slice_remaining = max(0, category_node_limit - category_nodes_used)
            forward_probe_slice_limit = min(
                forward_slice_remaining,
                category_slice_remaining,
                max(1, diagnostics.node_limit // (4 * len(unplaced_chain))),
            )
            probe_status = "PROVED_NO_MAIN_CHAIN_COMPLETION_IN_CURRENT_SEARCH_DOMAIN"
            incomplete_proof = False
            probe_budget_exhausted = False

            def candidate_origins(role: str, shape: _Shape) -> tuple[tuple[int, int], ...]:
                origins: set[tuple[int, int]] = set()
                # Union, rather than filter: preserve composition-domain and
                # CR1 interface event anchors while also admitting the full
                # finite physical-event fallback as an optimistic superset.
                origins.update(
                    _domain_derived_anchors(
                        role,
                        shape,
                        handoff,
                        domains,
                        bank_sign,
                        probe_placed,
                        boundary,
                        obstacles,
                    )
                )
                if access_intent is not None:
                    origins.update(
                        _domain_derived_anchors(
                            role,
                            shape,
                            handoff,
                            domains,
                            bank_sign,
                            probe_placed,
                            boundary,
                            obstacles,
                            access_intent,
                        )
                    )
                origins.update(
                    _generic_fallback_anchors(
                        role,
                        shape,
                        probe_placed,
                        boundary,
                        obstacles,
                        limit=None,
                    )
                )
                neighbors = tuple(name for name in _must_neighbors(role) if name in probe_placed)
                if neighbors:
                    origins.update(
                        _anchors_at_must_faces(
                            role, shape, probe_placed, neighbors, boundary, obstacles
                        )
                    )
                return tuple(sorted(origins))

            def visit_next() -> bool | None:
                nonlocal incomplete_proof, probe_budget_exhausted
                role = next((item for item in chain if item not in probe_placed), None)
                if role is None:
                    return True
                if not shapes[role]:
                    incomplete_proof = True
                    return None
                role_had_anchor = False
                role_failure_counts: Counter[str] = Counter()
                for shape in shapes[role]:
                    for x, y in candidate_origins(role, shape):
                        if (
                            diagnostics.nodes >= diagnostics.node_limit
                            or diagnostics.forward_check_nodes - forward_nodes_before
                            >= forward_probe_slice_limit
                        ):
                            probe_budget_exhausted = True
                            return None
                        diagnostics.nodes += 1
                        diagnostics.forward_check_nodes += 1
                        if chain_hole:
                            diagnostics.forward_check_chain_hole_nodes += 1
                        else:
                            diagnostics.forward_check_regular_nodes += 1
                        candidate = _rectangle(role, x, y, shape)
                        rejected = _candidate_rejection(
                            candidate, probe_placed, boundary, obstacles
                        )
                        if rejected is not None:
                            role_failure_counts[rejected] += 1
                            continue
                        neighbors = tuple(
                            name for name in _must_neighbors(role) if name in probe_placed
                        )
                        if any(
                            not rectangles_share_positive_edge(candidate, probe_placed[neighbor])
                            for neighbor in neighbors
                        ):
                            role_failure_counts["MUST_EDGE"] += 1
                            continue
                        role_had_anchor = True
                        probe_placed[role] = candidate
                        witness_order.append(role)
                        witness_bounds[role] = _bounds(candidate)
                        child = visit_next()
                        if child is True:
                            return True
                        probe_placed.pop(role, None)
                        witness_order.pop()
                        witness_bounds.pop(role, None)
                        if child is None and (probe_budget_exhausted or incomplete_proof):
                            return None
                failure_counts_by_role[role].update(role_failure_counts)
                # A role with no safe candidate is a concrete leaf failure;
                # if it had candidates but every suffix failed, the deepest
                # exhausted descendant provides the more precise taxonomy.
                if not role_had_anchor:
                    exhausted_roles.add(role)
                return False

            probe_result = visit_next()
            probe_nodes = diagnostics.nodes - nodes_before
            if probe_result is True:
                probe_status = "PASS_TO_SEARCH"
                result = _MainChainForwardCheckResultV1(
                    status=probe_status,
                    partial_geometry_hash=signature,
                    fixed_main_chain_roles=fixed_chain,
                    unplaced_main_chain_roles=unplaced_chain,
                    witness_role_order=tuple(witness_order),
                    witness_zone_bounds_mm=tuple(
                        (role, witness_bounds[role]) for role in witness_order
                    ),
                    probe_nodes_used=probe_nodes,
                    first_unplaceable_role=None,
                    failure_taxonomy="OPTIMISTIC_MAIN_CHAIN_WITNESS_FOUND",
                )
                diagnostics.forward_check_cache[signature] = result
            elif probe_result is None:
                probe_status = (
                    "UNKNOWN_BUDGET_EXHAUSTED"
                    if probe_budget_exhausted
                    else "UNKNOWN_INCOMPLETE_PROOF"
                )
                result = _MainChainForwardCheckResultV1(
                    status=probe_status,
                    partial_geometry_hash=signature,
                    fixed_main_chain_roles=fixed_chain,
                    unplaced_main_chain_roles=unplaced_chain,
                    witness_role_order=(),
                    witness_zone_bounds_mm=(),
                    probe_nodes_used=probe_nodes,
                    first_unplaceable_role=None,
                    failure_taxonomy=(
                        "SHARED_ATTEMPT_FORWARD_CHECK_SLICE_EXHAUSTED"
                        if probe_status == "UNKNOWN_BUDGET_EXHAUSTED"
                        else "PROBE_INPUT_OR_SEARCH_INCOMPLETE"
                    ),
                )
            else:
                first_unplaceable = max(
                    exhausted_roles,
                    key=chain.index,
                    default=unplaced_chain[-1],
                )
                counts = failure_counts_by_role[first_unplaceable]
                if counts:
                    reason = sorted(counts, key=lambda item: (-counts[item], item))[0]
                    failure_taxonomy = f"{first_unplaceable.upper()}_{reason}_REJECTION"
                else:
                    failure_taxonomy = f"{first_unplaceable.upper()}_NO_FINITE_EVENT_ANCHOR"
                result = _MainChainForwardCheckResultV1(
                    status=probe_status,
                    partial_geometry_hash=signature,
                    fixed_main_chain_roles=fixed_chain,
                    unplaced_main_chain_roles=unplaced_chain,
                    witness_role_order=(),
                    witness_zone_bounds_mm=(),
                    probe_nodes_used=probe_nodes,
                    first_unplaceable_role=first_unplaceable,
                    failure_taxonomy=failure_taxonomy,
                )
                diagnostics.forward_check_cache[signature] = result

    diagnostics.forward_check_sequence.append(
        (trigger_role, result.partial_geometry_hash, result.status, result.cache_hit)
    )
    if result.status == "PASS_TO_SEARCH":
        diagnostics.forward_check_pass_count += 1
        if len(diagnostics.forward_check_witnesses) < 24:
            diagnostics.forward_check_witnesses.append(
                {
                    "trigger_role": trigger_role,
                    "partial_geometry_hash": result.partial_geometry_hash,
                    "fixed_main_chain_roles": list(result.fixed_main_chain_roles),
                    "unplaced_main_chain_roles": list(result.unplaced_main_chain_roles),
                    "witness_role_order": list(result.witness_role_order),
                    "witness_zone_bounds_mm": {
                        role: list(bounds) for role, bounds in result.witness_zone_bounds_mm
                    },
                    "probe_nodes_used": result.probe_nodes_used,
                    "cache_hit": result.cache_hit,
                }
            )
    elif result.status == "PROVED_NO_MAIN_CHAIN_COMPLETION_IN_CURRENT_SEARCH_DOMAIN":
        diagnostics.forward_check_proved_no_completion_count += 1
        if len(diagnostics.forward_check_negative_proofs) < 32:
            diagnostics.forward_check_negative_proofs.append(
                {
                    "trigger_role": trigger_role,
                    "partial_geometry_hash": result.partial_geometry_hash,
                    "fixed_roles": list(result.fixed_main_chain_roles),
                    "remaining_main_chain_roles": list(result.unplaced_main_chain_roles),
                    "forward_check_status": result.status,
                    "probe_nodes_used": result.probe_nodes_used,
                    "probe_budget_exhausted": False,
                    "first_unplaceable_role_or_chain_hole": result.first_unplaceable_role,
                    "failure_taxonomy": result.failure_taxonomy,
                    "cache_hit": result.cache_hit,
                }
            )
    elif result.status == "UNKNOWN_BUDGET_EXHAUSTED":
        diagnostics.forward_check_unknown_budget_count += 1
    else:
        diagnostics.forward_check_unknown_other_count += 1
    return result


def _shipping_office_seed(
    shipping: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    office_shapes: Sequence[_Shape],
    handoff: StructuralCompositionPlacementHandoffV1,
    domains: Sequence[ConstructionDomainV1],
    bank_sign: int,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    diagnostics: _SearchDiagnostics,
) -> tuple[_Shape, tuple[int, int]] | None:
    office_neighbors = tuple(name for name in _must_neighbors("office") if name in placed)
    if "shipping_channel" not in office_neighbors:
        return None
    faces = _domain_faces(handoff, bank_sign)
    domain_origins_by_shape: dict[_Shape, set[tuple[int, int]]] = {}
    for source in ("DOMAIN", "GENERIC"):
        if source == "GENERIC" and diagnostics.generic_nodes >= max(
            1, diagnostics.node_limit // 10
        ):
            break
        for shape in office_shapes:
            if source == "DOMAIN":
                anchors = _domain_derived_anchors(
                    "office", shape, handoff, domains, bank_sign, placed, boundary, obstacles
                )
                diagnostics.domain_anchor_count["office"] = diagnostics.domain_anchor_count.get(
                    "office", 0
                ) + len(anchors)
                diagnostics.funnel["office"]["domain_derived_anchor_count"] += len(anchors)
                domain_origins_by_shape[shape] = set(anchors)
            else:
                anchors = _generic_fallback_anchors("office", shape, placed, boundary, obstacles)
                anchors = tuple(
                    point
                    for point in anchors
                    if point not in domain_origins_by_shape.get(shape, set())
                )
                diagnostics.generic_anchor_count["office"] = diagnostics.generic_anchor_count.get(
                    "office", 0
                ) + len(anchors)
                diagnostics.funnel["office"]["generic_fallback_anchor_count"] += len(anchors)
            for point in anchors:
                if source == "GENERIC" and diagnostics.generic_nodes >= max(
                    1, diagnostics.node_limit // 10
                ):
                    break
                if diagnostics.nodes >= diagnostics.node_limit:
                    diagnostics.budget_hit = True
                    diagnostics.shipping_office_status = "UNRESOLVED_NODE_BUDGET"
                    return None
                diagnostics.nodes += 1
                diagnostics.primary_search_nodes += 1
                funnel = diagnostics.funnel["office"]
                funnel["candidate_rectangle_attempt_count"] += 1
                if source == "GENERIC":
                    diagnostics.generic_nodes += 1
                    diagnostics.generic_nodes_by_role["office"] = (
                        diagnostics.generic_nodes_by_role.get("office", 0) + 1
                    )
                candidate = _rectangle("office", point[0], point[1], shape)
                rejected = _candidate_rejection(candidate, placed, boundary, obstacles)
                if rejected is not None:
                    funnel[f"{rejected.lower()}_rejection_count"] += 1
                    diagnostics.failure_taxonomy = f"OFFICE_{rejected}_REJECTION"
                    continue
                sorting = placed.get("sorting_packaging_room")
                if sorting is not None and not _side_ok("office", candidate, sorting, faces):
                    funnel["domain_side_rejection_count"] += 1
                    diagnostics.failure_taxonomy = "OFFICE_DOMAIN_SIDE_REJECTION"
                    continue
                if not rectangles_share_positive_edge(candidate, shipping):
                    funnel["must_edge_rejection_count"] += 1
                    diagnostics.failure_taxonomy = "OFFICE_SHIPPING_MUST_EDGE_REJECTION"
                    continue
                diagnostics.office_seed_by_shipping[shipping.bounds_mm] = (shape, point)
                diagnostics.shipping_office_status = "PASS"
                return shape, point
    diagnostics.shipping_office_status = "NO_AUTHORITY_VALID_OFFICE_ATTACHMENT"
    return None


def _search_one(
    handoff: StructuralCompositionPlacementHandoffV1,
    shapes: Mapping[str, tuple[_Shape, ...]],
    authority_shapes: Mapping[str, tuple[_Shape, ...]],
    dimension_authorities: Mapping[str, Mapping[str, Any]],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    domains: tuple[ConstructionDomainV1, ...],
    bank_sign: int,
    search_order_lane: str,
    node_limit: int,
    access_intent: AccessCriticalConstructionIntentV1 | None = None,
    complete_candidate_admission: Callable[
        [
            StructuralCompositionPlacementHandoffV1,
            Mapping[str, PlacedRectangleV1],
            int,
            str,
            int,
        ],
        bool,
    ]
    | None = None,
    shipping_candidate_preflight: Callable[
        [StructuralCompositionPlacementHandoffV1, Mapping[str, PlacedRectangleV1]],
        Mapping[str, Any],
    ]
    | None = None,
) -> _SearchOutcome:
    access_aware = access_intent is not None
    order = _zone_order(
        handoff,
        access_aware=access_aware,
        search_order_lane=search_order_lane,
    )
    faces = _domain_faces(handoff, bank_sign)
    shape_order_intent = access_intent if search_order_lane == "ACCESS_AWARE_ORDER" else None
    # S3 compatibility retains the immediately preceding deterministic shape
    # ordering, while still receiving the CR1 intent in every anchor, partial
    # Packaging, and final Access checkpoint.
    ordered_shapes = _composition_shape_order(handoff, shapes, bank_sign, shape_order_intent)
    diagnostics = _SearchDiagnostics(node_limit=node_limit)
    role_rank = {role: index for index, role in enumerate(order)}
    material_flows = tuple(flow for flow in process_graph().flows if flow.kind == "MATERIAL")
    material_chain_roles = _main_chain_roles_from_process_graph()
    material_predecessors = {
        role: tuple(flow.from_ref for flow in material_flows if flow.to_ref == role)
        for role in order
    }
    material_successors = {
        role: tuple(flow.to_ref for flow in material_flows if flow.from_ref == role)
        for role in order
    }
    for role in order:
        diagnostics.funnel[role] = {
            "role_attempt_count": 0,
            "authority_shape_variant_count": len(authority_shapes[role]),
            "authority_rotation_variant_count": len(
                {shape.rotation_deg for shape in authority_shapes[role]}
            ),
            "construction_shape_variant_count": len(ordered_shapes[role]),
            "shape_variant_attempt_count": 0,
            "domain_derived_anchor_count": 0,
            "generic_fallback_anchor_count": 0,
            "candidate_rectangle_attempt_count": 0,
            "site_rejection_count": 0,
            "obstacle_rejection_count": 0,
            "overlap_rejection_count": 0,
            "domain_side_rejection_count": 0,
            "must_edge_rejection_count": 0,
            "coupled_interface_rejection_count": 0,
            "composition_intent_rejection_count": 0,
            "access_interface_rejection_count": 0,
            "main_chain_forward_check_prune_count": 0,
            "accepted_partial_placement_count": 0,
            "backtrack_count": 0,
        }
        diagnostics.authority_shape_count[role] = len(authority_shapes[role])
        diagnostics.construction_shape_count[role] = len(ordered_shapes[role])
        diagnostics.domain_anchor_count[role] = 0
        diagnostics.generic_anchor_count[role] = 0
        diagnostics.generic_nodes_by_role[role] = 0

    # These are conservative gates only. Construction domains do not become
    # engineering authority, so uncertain capacity always proceeds to search.
    required_roles = {item.zone_role for item in handoff.zone_role_assignment}
    diagnostics.shipping_office_status = (
        _shipping_office_interface_preflight_status(
            ordered_shapes["shipping_channel"], ordered_shapes["office"], boundary
        )
        if {"office", "shipping_channel"} <= required_roles
        else "UNKNOWN_ROLE_COVERAGE"
    )
    site_area = _polygon_area_mm2(boundary)
    total_zone_area = sum(_authority_area_mm2(item) for item in dimension_authorities.values())
    principal_band_groups = tuple(
        tuple(role for role in band.zone_roles if role in required_roles)
        for band in handoff.principal_band_intents
    )
    peripheral_groups = tuple(
        tuple(role for role in domain.zone_roles if role in required_roles)
        for domain in handoff.peripheral_domain_intents
        if domain.zone_roles
    )
    diagnostics_band_status = _capacity_preflight_status(
        principal_band_groups,
        dimension_authorities,
        authority_shapes,
        boundary,
    )
    diagnostics_peripheral_status = _capacity_preflight_status(
        peripheral_groups,
        dimension_authorities,
        authority_shapes,
        boundary,
    )
    diagnostics.band_capacity_status = diagnostics_band_status
    diagnostics.peripheral_capacity_status = diagnostics_peripheral_status

    def rejection_count() -> int:
        return sum(
            value
            for role_funnel in diagnostics.funnel.values()
            for key, value in role_funnel.items()
            if key.endswith("_rejection_count")
        )

    def save_witness(placed: Mapping[str, PlacedRectangleV1], next_role: str) -> None:
        role_bounds = tuple((role, _bounds(placed[role])) for role in ZONE_CODES if role in placed)
        key = (-len(placed), rejection_count(), role_bounds)
        if diagnostics.best_witness_key is not None and key >= diagnostics.best_witness_key:
            return
        diagnostics.best_witness_key = key
        diagnostics.best_witness = PartialPlacementWitnessV1(
            composition_identity=handoff.composition_identity,
            placed_roles=tuple(role for role in ZONE_CODES if role in placed),
            zone_bounds_mm=role_bounds,
            next_role=next_role,
            failure_taxonomy=diagnostics.failure_taxonomy,
            hard_subset_rejection_count=rejection_count(),
            bank_sign=bank_sign,
            nodes_used=diagnostics.nodes,
        )

    def set_attempted(role: str, placed: Mapping[str, PlacedRectangleV1]) -> None:
        if diagnostics.deepest_attempted == "NOT_ATTEMPTED" or role_rank[role] > role_rank.get(
            diagnostics.deepest_attempted, -1
        ):
            diagnostics.deepest_attempted = role
        diagnostics.funnel[role]["role_attempt_count"] += 1
        save_witness(placed, role)

    def count_candidate_failure(role: str, reason: str) -> None:
        diagnostics.funnel[role][f"{reason.lower()}_rejection_count"] += 1
        diagnostics.failure_taxonomy = f"{role.upper()}_{reason}_REJECTION"

    def recurse(
        index: int, placed: dict[str, PlacedRectangleV1]
    ) -> dict[str, PlacedRectangleV1] | None:
        if index < len(order):
            set_attempted(order[index], placed)
        if index == len(order):
            must_ok = all(
                rectangles_share_positive_edge(placed[first], placed[second])
                for first, second in process_graph().must_adjacencies
            )
            if must_ok and _intent_preserved(handoff, placed, faces):
                zones_snapshot = dict(placed)
                diagnostics.complete_placements.append((zones_snapshot, diagnostics.nodes))
                stop_search = (
                    True
                    if complete_candidate_admission is None
                    else complete_candidate_admission(
                        handoff,
                        zones_snapshot,
                        bank_sign,
                        search_order_lane,
                        diagnostics.nodes,
                    )
                )
                if stop_search:
                    return zones_snapshot
                diagnostics.failure_taxonomy = "COMPLETE_CANDIDATE_RETAINED_SEARCH_CONTINUED"
                save_witness(placed, "ACCESS_VALIDATION_CHECKPOINT")
                return None
            diagnostics.failure_taxonomy = (
                "FINAL_MUST_ADJACENCY_REJECTION" if not must_ok else "COMPOSITION_INTENT_REJECTION"
            )
            save_witness(placed, "COMPLETE")
            return None
        code = order[index]
        neighbors = tuple(name for name in _must_neighbors(code) if name in placed)
        axis, interval = _domain_interval(code, handoff, domains)

        def ordered_points(
            points: Sequence[tuple[int, int]], shape: _Shape
        ) -> tuple[tuple[int, int], ...]:
            def key(
                point: tuple[int, int],
            ) -> tuple[int, int, int, int, int, int, int, int, int]:
                projection = (
                    point[0] + shape.world_width_mm // 2
                    if axis == "X"
                    else point[1] + shape.world_depth_mm // 2
                )
                process_axis = handoff.process_axis.value
                process_projection = (
                    point[0] + shape.world_width_mm // 2
                    if process_axis == "X"
                    else point[1] + shape.world_depth_mm // 2
                )
                process_sign = 1 if handoff.process_direction == ProcessDirectionV1.POSITIVE else -1
                process_projection *= process_sign
                flow_violation_mm = 0
                if access_intent is not None:
                    previous_flow_positions = [
                        process_sign * _center(placed[predecessor], process_axis)
                        for predecessor in material_predecessors[code]
                        if predecessor in placed
                    ]
                    following_flow_positions = [
                        process_sign * _center(placed[successor], process_axis)
                        for successor in material_successors[code]
                        if successor in placed
                    ]
                    flow_violation_mm = max(
                        [
                            *(
                                position - process_projection
                                for position in previous_flow_positions
                            ),
                            *(
                                process_projection - position
                                for position in following_flow_positions
                            ),
                            0,
                        ]
                    )
                interval_penalty = 0
                if interval is not None:
                    low, high = interval
                    interval_penalty = (
                        0
                        if low <= projection <= high
                        else min(abs(projection - low), abs(projection - high))
                    )
                sorting = placed.get("sorting_packaging_room")
                side_penalty = 0
                cross_penalty = 0
                process_center_penalty = 0
                access_departure_penalty = 0
                if code == "sorting_packaging_room":
                    if handoff.process_axis == ProcessAxisV1.X:
                        process_center = (
                            min(item[0] for item in boundary) + max(item[0] for item in boundary)
                        ) // 2
                        process_center_penalty = abs(projection - process_center)
                        cross_center = point[1] + shape.world_depth_mm // 2
                        site_center = (
                            min(item[1] for item in boundary) + max(item[1] for item in boundary)
                        ) // 2
                    else:
                        process_center = (
                            min(item[1] for item in boundary) + max(item[1] for item in boundary)
                        ) // 2
                        process_center_penalty = abs(projection - process_center)
                        cross_center = point[0] + shape.world_width_mm // 2
                        site_center = (
                            min(item[0] for item in boundary) + max(item[0] for item in boundary)
                        ) // 2
                    cross_penalty = abs(cross_center - site_center)
                    if handoff.family != CompositionFamilyV2.CENTRAL_PROCESS_CORE:
                        process_center_penalty = 0
                if sorting is not None and code in faces:
                    ref_axis, sign = faces[code]
                    coordinate = (
                        point[0] + shape.world_width_mm // 2
                        if ref_axis == "X"
                        else point[1] + shape.world_depth_mm // 2
                    )
                    side_penalty = 0 if (coordinate - _center(sorting, ref_axis)) * sign > 0 else 1
                if (
                    access_aware
                    and code
                    in (
                        "secondary_fruit_buffer",
                        "frozen_fruit_room",
                    )
                    and sorting is not None
                ):
                    # Keep Sorting's hard process faces available where possible;
                    # the exact route authority later decides whether the seeded
                    # finite corridor offset is actually usable.
                    access_departure_penalty = int(
                        rectangles_share_positive_edge(
                            _rectangle(code, point[0], point[1], shape), sorting
                        )
                    )
                return (
                    int(flow_violation_mm > 0),
                    flow_violation_mm,
                    access_departure_penalty,
                    interval_penalty,
                    process_center_penalty,
                    cross_penalty,
                    side_penalty,
                    point[0],
                    point[1],
                )

            return tuple(sorted(set(points), key=key))

        # The complete finite domain-derived set is attempted first across all
        # authority shapes. Generic physical-event anchors are a bounded,
        # explicitly secondary continuation.
        domain_origins_by_shape: dict[_Shape, set[tuple[int, int]]] = {}
        for source in ("DOMAIN", "GENERIC"):
            if source == "GENERIC" and diagnostics.generic_nodes >= max(1, node_limit // 10):
                break
            for shape in ordered_shapes[code]:
                diagnostics.funnel[code]["shape_variant_attempt_count"] += 1
                if source == "DOMAIN":
                    origins = _domain_derived_anchors(
                        code,
                        shape,
                        handoff,
                        domains,
                        bank_sign,
                        placed,
                        boundary,
                        obstacles,
                        access_intent,
                    )
                    cached_office = (
                        diagnostics.office_seed_by_shipping.get(
                            placed["shipping_channel"].bounds_mm
                        )
                        if code == "office" and "shipping_channel" in placed
                        else None
                    )
                    if cached_office is not None and cached_office[0] == shape:
                        origins = (cached_office[1],) + tuple(
                            point for point in origins if point != cached_office[1]
                        )
                    diagnostics.domain_anchor_count[code] += len(origins)
                    diagnostics.funnel[code]["domain_derived_anchor_count"] += len(origins)
                    domain_origins_by_shape[shape] = set(origins)
                else:
                    if diagnostics.generic_nodes >= max(1, node_limit // 10):
                        break
                    origins = _generic_fallback_anchors(code, shape, placed, boundary, obstacles)
                    origins = tuple(
                        point
                        for point in origins
                        if point not in domain_origins_by_shape.get(shape, set())
                    )
                    diagnostics.generic_anchor_count[code] += len(origins)
                    diagnostics.funnel[code]["generic_fallback_anchor_count"] += len(origins)
                for x, y in ordered_points(origins, shape):
                    cached_office = (
                        diagnostics.office_seed_by_shipping.get(
                            placed["shipping_channel"].bounds_mm
                        )
                        if code == "office" and "shipping_channel" in placed
                        else None
                    )
                    reused_office_probe = (
                        source == "DOMAIN"
                        and cached_office is not None
                        and cached_office == (shape, (x, y))
                    )
                    if diagnostics.nodes >= node_limit and not reused_office_probe:
                        diagnostics.budget_hit = True
                        diagnostics.failure_taxonomy = "PLACEMENT_NODE_BUDGET_EXHAUSTED"
                        save_witness(placed, code)
                        return None
                    if source == "GENERIC" and diagnostics.generic_nodes >= max(
                        1, node_limit // 10
                    ):
                        break
                    if not reused_office_probe:
                        diagnostics.nodes += 1
                        diagnostics.primary_search_nodes += 1
                        diagnostics.funnel[code]["candidate_rectangle_attempt_count"] += 1
                    if source == "GENERIC":
                        diagnostics.generic_nodes += 1
                        diagnostics.generic_nodes_by_role[code] += 1
                    candidate = _rectangle(code, x, y, shape)
                    rejected = _candidate_rejection(candidate, placed, boundary, obstacles)
                    if rejected is not None:
                        count_candidate_failure(code, rejected)
                        save_witness(placed, code)
                        continue
                    if (
                        access_intent is not None
                        and code == "packaging_material_storage"
                        and "sorting_packaging_room" in placed
                        and not _packaging_straight_interface_possible(
                            candidate,
                            placed["sorting_packaging_room"],
                            access_intent,
                            boundary,
                            obstacles,
                            placed,
                        )
                    ):
                        diagnostics.funnel[code]["coupled_interface_rejection_count"] += 1
                        diagnostics.failure_taxonomy = (
                            "PACKAGING_SORTING_STRAIGHT_INTERFACE_PREFLIGHT_REJECTION"
                        )
                        save_witness(placed, code)
                        continue
                    if neighbors and any(
                        not rectangles_share_positive_edge(candidate, placed[neighbor])
                        for neighbor in neighbors
                    ):
                        diagnostics.funnel[code]["must_edge_rejection_count"] += 1
                        diagnostics.failure_taxonomy = f"{code.upper()}_MUST_EDGE_REJECTION"
                        save_witness(placed, code)
                        continue
                    sorting = placed.get("sorting_packaging_room")
                    if sorting is not None and not _side_ok(code, candidate, sorting, faces):
                        diagnostics.funnel[code]["domain_side_rejection_count"] += 1
                        diagnostics.failure_taxonomy = f"{code.upper()}_DOMAIN_SIDE_REJECTION"
                        save_witness(placed, code)
                        continue
                    if access_aware and code == "shipping_channel":
                        office_status = _shipping_office_candidate_preflight_status(
                            candidate,
                            ordered_shapes["office"],
                            boundary,
                        )
                        diagnostics.shipping_office_status = office_status
                        if office_status == "PROVABLY_NO_SHARED_EDGE_CAPACITY_IN_SITE_BOUNDS":
                            diagnostics.funnel[code]["coupled_interface_rejection_count"] += 1
                            diagnostics.failure_taxonomy = (
                                "SHIPPING_OFFICE_INTERFACE_PROVED_IMPOSSIBLE_IN_SITE_BOUNDS"
                            )
                            save_witness(placed, code)
                            continue
                    if (
                        not access_aware
                        and code == "shipping_channel"
                        and shipping_candidate_preflight is not None
                    ):
                        partial_zones = dict(placed)
                        partial_zones[code] = candidate
                        preflight = shipping_candidate_preflight(handoff, partial_zones)
                        status = str(preflight.get("status", "UNKNOWN_NOT_PROVEN_IMPOSSIBLE"))
                        diagnostics.shipping_truck_preflight_status = status
                        diagnostics.shipping_truck_preflight_counts[status] = (
                            diagnostics.shipping_truck_preflight_counts.get(status, 0) + 1
                        )
                        if status != "PASS_TO_TRUCK_SEARCH":
                            diagnostics.funnel[code]["coupled_interface_rejection_count"] += 1
                            diagnostics.failure_taxonomy = (
                                "SHIPPING_TRUCK_CAPACITY_PREFLIGHT_REJECTION"
                            )
                            save_witness(placed, code)
                            continue
                    placed[code] = candidate
                    if not _partial_intent_possible(handoff, placed, faces):
                        diagnostics.funnel[code]["composition_intent_rejection_count"] += 1
                        diagnostics.failure_taxonomy = (
                            f"{code.upper()}_PARTIAL_COMPOSITION_INTENT_REJECTION"
                        )
                        save_witness(
                            placed,
                            order[index + 1] if index + 1 < len(order) else "COMPLETE",
                        )
                        placed.pop(code, None)
                        continue
                    if (
                        access_intent is not None
                        and code != "packaging_material_storage"
                        and "sorting_packaging_room" in placed
                        and "packaging_material_storage" not in placed
                    ):
                        packaging_capacity_remains = _packaging_interface_capacity_remains(
                            handoff,
                            ordered_shapes,
                            access_intent,
                            domains,
                            bank_sign,
                            placed,
                            boundary,
                            obstacles,
                        )
                        if packaging_capacity_remains:
                            diagnostics.packaging_preflight_pass_partial_count += 1
                        else:
                            diagnostics.packaging_preflight_fail_partial_count += 1
                            diagnostics.funnel[code]["access_interface_rejection_count"] += 1
                            diagnostics.failure_taxonomy = (
                                "PACKAGING_STRAIGHT_INTERFACE_CAPACITY_CLOSED_BY_PARTIAL_PLACEMENT"
                            )
                            save_witness(placed, "packaging_material_storage")
                            placed.pop(code, None)
                            continue
                    remaining_main_chain_role_count = sum(
                        role not in placed for role in material_chain_roles
                    )
                    fixed_main_chain_role_count = sum(
                        role in placed for role in material_chain_roles
                    )
                    fixed_successor_with_chain_hole = any(
                        role in placed
                        and any(previous not in placed for previous in material_chain_roles[:index])
                        for index, role in enumerate(material_chain_roles)
                    )
                    branch_capacity_trigger = (
                        code in FORWARD_CHECK_TRIGGER_ROLES
                        and code != "shipping_channel"
                        and fixed_main_chain_role_count >= 3
                        and remaining_main_chain_role_count <= 3
                    )
                    main_chain_hole_trigger = (
                        code in material_chain_roles
                        and fixed_successor_with_chain_hole
                        and remaining_main_chain_role_count <= 2
                    )
                    shipping_capacity_trigger = (
                        code == "shipping_channel"
                        and fixed_main_chain_role_count >= 3
                        and remaining_main_chain_role_count <= 3
                    )
                    if (
                        access_intent is not None
                        and remaining_main_chain_role_count > 0
                        and (
                            branch_capacity_trigger
                            or shipping_capacity_trigger
                            or main_chain_hole_trigger
                        )
                    ):
                        probe = _optimistic_main_chain_completion_probe(
                            handoff,
                            ordered_shapes,
                            domains,
                            bank_sign,
                            placed,
                            boundary,
                            obstacles,
                            access_intent,
                            diagnostics,
                            code,
                            chain_hole=main_chain_hole_trigger
                            and remaining_main_chain_role_count <= 1,
                        )
                        if code == "packaging_material_storage" and access_intent is not None:
                            diagnostics.packaging_local_pass_chain_forward_fail_count += int(
                                probe.status
                                == "PROVED_NO_MAIN_CHAIN_COMPLETION_IN_CURRENT_SEARCH_DOMAIN"
                            )
                            diagnostics.packaging_local_pass_chain_forward_pass_count += int(
                                probe.status == "PASS_TO_SEARCH"
                            )
                        elif code == "secondary_fruit_buffer":
                            diagnostics.secondary_local_pass_chain_forward_fail_count += int(
                                probe.status
                                == "PROVED_NO_MAIN_CHAIN_COMPLETION_IN_CURRENT_SEARCH_DOMAIN"
                            )
                        elif code == "frozen_fruit_room":
                            diagnostics.frozen_local_pass_chain_forward_fail_count += int(
                                probe.status
                                == "PROVED_NO_MAIN_CHAIN_COMPLETION_IN_CURRENT_SEARCH_DOMAIN"
                            )
                        elif code in ("changing_room", "office"):
                            diagnostics.personnel_local_pass_chain_forward_fail_count += int(
                                probe.status
                                == "PROVED_NO_MAIN_CHAIN_COMPLETION_IN_CURRENT_SEARCH_DOMAIN"
                            )
                        if (
                            probe.status
                            == "PROVED_NO_MAIN_CHAIN_COMPLETION_IN_CURRENT_SEARCH_DOMAIN"
                        ):
                            diagnostics.chain_starvation_prune_count_by_trigger_role[code] = (
                                diagnostics.chain_starvation_prune_count_by_trigger_role.get(
                                    code, 0
                                )
                                + 1
                            )
                            diagnostics.funnel[code]["main_chain_forward_check_prune_count"] += 1
                            diagnostics.failure_taxonomy = (
                                "PROVED_NO_MAIN_CHAIN_COMPLETION_IN_CURRENT_SEARCH_DOMAIN"
                            )
                            save_witness(
                                placed,
                                order[index + 1]
                                if index + 1 < len(order)
                                else "MAIN_CHAIN_FORWARD_CHECK",
                            )
                            placed.pop(code, None)
                            diagnostics.funnel[code]["backtrack_count"] += 1
                            continue
                    diagnostics.max_placed = max(diagnostics.max_placed, len(placed))
                    if diagnostics.deepest_successfully_placed == "NOT_PLACED" or role_rank[
                        code
                    ] > role_rank.get(diagnostics.deepest_successfully_placed, -1):
                        diagnostics.deepest_successfully_placed = code
                    diagnostics.funnel[code]["accepted_partial_placement_count"] += 1
                    diagnostics.failure_taxonomy = "PARTIAL_PLACEMENT_ACCEPTED"
                    save_witness(placed, order[index + 1] if index + 1 < len(order) else "COMPLETE")
                    if code == "shipping_channel" and not access_aware:
                        seed = _shipping_office_seed(
                            candidate,
                            placed,
                            ordered_shapes["office"],
                            handoff,
                            domains,
                            bank_sign,
                            boundary,
                            obstacles,
                            diagnostics,
                        )
                        if seed is None:
                            diagnostics.funnel[code]["coupled_interface_rejection_count"] += 1
                            diagnostics.failure_taxonomy = "SHIPPING_OFFICE_INTERFACE_REJECTION"
                            save_witness(placed, "office")
                            placed.pop(code, None)
                            if diagnostics.budget_hit:
                                return None
                            continue
                    solution = recurse(index + 1, placed)
                    if solution is not None:
                        return solution
                    placed.pop(code, None)
                    diagnostics.funnel[code]["backtrack_count"] += 1
                    if diagnostics.budget_hit:
                        return None
        return None

    if diagnostics.shipping_office_status == "PROVABLY_NO_SHARED_EDGE_CAPACITY_IN_SITE_BOUNDS":
        diagnostics.failure_taxonomy = "SHIPPING_OFFICE_INTERFACE_PROVED_IMPOSSIBLE_IN_SITE_BOUNDS"
        return _SearchOutcome(
            solution=None,
            diagnostics=diagnostics,
            deepest_attempted="NOT_ATTEMPTED",
            deepest_successfully_placed="NOT_PLACED",
        )

    if total_zone_area > site_area:
        diagnostics.failure_taxonomy = "AUTHORITATIVE_ZONE_AREA_EXCEEDS_BUILDABLE_SITE_AREA"
        save_witness({}, "PREFLIGHT")
        return _SearchOutcome(
            solution=None,
            diagnostics=diagnostics,
            deepest_attempted="NOT_ATTEMPTED",
            deepest_successfully_placed="NOT_PLACED",
        )
    solution = recurse(0, {})
    if diagnostics.best_witness is None:
        diagnostics.failure_taxonomy = "NO_PARTIAL_PLACEMENT"
        save_witness({}, order[0])
    return _SearchOutcome(
        solution=solution,
        diagnostics=diagnostics,
        deepest_attempted=diagnostics.deepest_attempted,
        deepest_successfully_placed=diagnostics.deepest_successfully_placed,
    )


def _candidate(
    handoff: StructuralCompositionPlacementHandoffV1,
    placements: Mapping[str, PlacedRectangleV1],
    domains: tuple[ConstructionDomainV1, ...],
    hashes: tuple[str, str, str],
    node_provenance: tuple[tuple[str, str], ...],
) -> CompositionPlacementCandidateV1:
    ordered_zones = tuple(placements[code] for code in ZONE_CODES)
    must_count = sum(
        rectangles_share_positive_edge(placements[first], placements[second])
        for first, second in process_graph().must_adjacencies
    )
    return CompositionPlacementCandidateV1(
        identity=IDENTITY,
        schema_version=SCHEMA_VERSION,
        composition_identity=handoff.composition_identity,
        composition_signature=handoff.composition_signature,
        family=handoff.family,
        process_axis=handoff.process_axis,
        process_direction=handoff.process_direction,
        zones=ordered_zones,
        zone_count=len(ordered_zones),
        placement_scope=PLACEMENT_HARD_SCOPE,
        hard_constraints_passed=True,
        site_valid=True,
        dimension_valid=True,
        non_overlap_valid=True,
        must_adjacency_valid=must_count == len(process_graph().must_adjacencies),
        must_adjacency_satisfied_count=must_count,
        composition_intent_preserved=True,
        construction_domains=domains,
        source_zone_plan_hash=hashes[0],
        source_p1_handoff_hash=hashes[1],
        source_site_geometry_hash=hashes[2],
        search_provenance=node_provenance,
    )


def enumerate_composition_placements(
    handoffs: Sequence[StructuralCompositionPlacementHandoffV1],
    dimension_authorities: Mapping[str, Mapping[str, Any]],
    site_geometry: Mapping[str, Any],
    *,
    source_zone_plan_hash: str,
    source_p1_handoff_hash: str,
    source_site_geometry_hash: str,
    node_budget: int = DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET,
    access_intent: AccessCriticalConstructionIntentV1 | None = None,
    complete_candidate_admission: Callable[
        [
            StructuralCompositionPlacementHandoffV1,
            Mapping[str, PlacedRectangleV1],
            int,
            str,
            int,
        ],
        bool,
    ]
    | None = None,
    shipping_candidate_preflight: Callable[
        [StructuralCompositionPlacementHandoffV1, Mapping[str, PlacedRectangleV1]],
        Mapping[str, Any],
    ]
    | None = None,
) -> CompositionPlacementEnumerationV1:
    """Generate bounded, family-first exact candidates from server-bound intents."""
    if (
        type(node_budget) is not int
        or node_budget < len(FAMILY_ORDER)
        or node_budget > MAX_COMPOSITION_PLACEMENT_NODE_BUDGET
    ):
        raise ValueError("INVALID_COMPOSITION_PLACEMENT_NODE_BUDGET")
    if set(dimension_authorities) != set(ZONE_CODES):
        raise ValueError("DIMENSION_AUTHORITY_ROLE_COVERAGE_INVALID")
    if not handoffs or any(
        not isinstance(item, StructuralCompositionPlacementHandoffV1) for item in handoffs
    ):
        raise ValueError("SERVER_BOUND_COMPOSITION_HANDOFFS_REQUIRED")
    if access_intent is not None and not isinstance(
        access_intent, AccessCriticalConstructionIntentV1
    ):
        raise ValueError("SERVER_BOUND_ACCESS_CRITICAL_INTENT_REQUIRED")
    if (complete_candidate_admission is not None or shipping_candidate_preflight is not None) and (
        access_intent is None
    ):
        raise ValueError("ACCESS_ADMISSION_REQUIRES_ACCESS_INTENT")
    boundary_raw = site_geometry.get("site", {}).get("effective_buildable_boundary")
    if not isinstance(boundary_raw, Mapping):
        raise ValueError("VALIDATED_BUILDABLE_BOUNDARY_REQUIRED")
    boundary = normalize_polygon(boundary_raw, allow_numeric_string=True)
    obstacles_raw = site_geometry.get("obstacles", {}).get("no_build_zones", [])
    if not isinstance(obstacles_raw, list):
        raise ValueError("VALIDATED_OBSTACLES_REQUIRED")
    obstacles = tuple(normalize_polygon(item, allow_numeric_string=True) for item in obstacles_raw)
    authority_shapes = _authority_shapes(dimension_authorities, boundary, obstacles, access_intent)
    shapes = {
        role: _canonical_construction_shapes(variants)
        for role, variants in authority_shapes.items()
    }
    by_family: dict[CompositionFamilyV2, list[StructuralCompositionPlacementHandoffV1]] = (
        defaultdict(list)
    )
    for item in handoffs:
        by_family[item.family].append(item)
    if set(by_family) != set(FAMILY_ORDER):
        raise ValueError("COMPOSITION_FAMILY_COVERAGE_INVALID")

    attempt_budget_by_stage: tuple[int, ...]
    if access_intent is None:
        per_attempt_budget = max(1, node_budget // (len(FAMILY_ORDER) * 2 * 2))
        alternate_mirrored_slice = per_attempt_budget
        initial_family_budget = per_attempt_budget * 2
        continuation_budget = max(0, node_budget - initial_family_budget * len(FAMILY_ORDER))
        attempt_budget_by_stage = (
            per_attempt_budget,
            per_attempt_budget,
            per_attempt_budget,
        )
    else:
        # Stage A gives every family both banks on its first composition.
        # Stage B covers alternate-composition positive banks for all families
        # (including the known S3-feasible Linear r1/+1 lane), then all three
        # opposite banks. Stage C spends the remaining fixed allocation on
        # the Linear positive-bank partial-progress lane. No family is skipped
        # and the task allocations sum to the existing 60,000-node cap.
        first_composition_slice = max(1, node_budget // 120)
        mirrored_composition_slice = max(1, node_budget // 120)
        alternate_composition_slice = max(1, node_budget // 15)
        known_lane_slice = max(1, node_budget // 3)
        linear_first_lane_continuation_slice = max(1, node_budget * 11 // 24)
        alternate_mirrored_slice = max(1, node_budget // 120)
        per_attempt_budget = first_composition_slice
        initial_family_budget = first_composition_slice + mirrored_composition_slice
        continuation_budget = max(0, node_budget - initial_family_budget * len(FAMILY_ORDER))
        attempt_budget_by_stage = (
            first_composition_slice,
            mirrored_composition_slice,
            alternate_composition_slice,
            alternate_mirrored_slice,
        )
    remaining = node_budget
    attempts: dict[str, int] = {family.value: 0 for family in FAMILY_ORDER}
    used: dict[str, int] = {family.value: 0 for family in FAMILY_ORDER}
    deepest_attempted_by_family: dict[str, str] = {
        family.value: "NOT_ATTEMPTED" for family in FAMILY_ORDER
    }
    deepest_attempted_rank: dict[str, int] = {family.value: -1 for family in FAMILY_ORDER}
    deepest_successfully_placed: dict[str, str] = {
        family.value: "NOT_PLACED" for family in FAMILY_ORDER
    }
    deepest_success_rank: dict[str, int] = {family.value: -1 for family in FAMILY_ORDER}
    max_placed_by_family: dict[str, int] = {family.value: 0 for family in FAMILY_ORDER}
    domain_anchor_by_family: dict[str, int] = {family.value: 0 for family in FAMILY_ORDER}
    generic_anchor_by_family: dict[str, int] = {family.value: 0 for family in FAMILY_ORDER}
    generic_nodes_by_family: dict[str, int] = {family.value: 0 for family in FAMILY_ORDER}
    failures: dict[str, str] = {}
    hashes = (source_zone_plan_hash, source_p1_handoff_hash, source_site_geometry_hash)
    candidates: list[CompositionPlacementCandidateV1] = []
    families_with_candidate: set[CompositionFamilyV2] = set()
    search_attempts: list[CompositionPlacementSearchAttemptV1] = []
    # True family-first rounds: every family receives its positive-bank probe
    # before any family receives the mirrored probe, then composition variants
    # continue in the same deterministic family order.
    tasks: list[
        tuple[
            CompositionFamilyV2,
            StructuralCompositionPlacementHandoffV1,
            int,
            str,
            int,
        ]
    ] = []
    if access_intent is None:
        tasks.extend(
            (
                family,
                by_family[family][0],
                1,
                "S3_COMPATIBILITY_ORDER",
                attempt_budget_by_stage[0],
            )
            for family in FAMILY_ORDER
        )
        tasks.extend(
            (
                family,
                by_family[family][0],
                -1,
                "S3_COMPATIBILITY_ORDER",
                attempt_budget_by_stage[1],
            )
            for family in FAMILY_ORDER
        )
        tasks.extend(
            (family, by_family[family][1], 1, "S3_COMPATIBILITY_ORDER", per_attempt_budget)
            for family in FAMILY_ORDER
            if len(by_family[family]) > 1
        )
        tasks.extend(
            (family, by_family[family][1], -1, "S3_COMPATIBILITY_ORDER", per_attempt_budget)
            for family in FAMILY_ORDER
            if len(by_family[family]) > 1
        )
    else:
        # Stage A is family-first on both first-composition banks. Stage B
        # explicitly covers all alternate-composition positive and opposite
        # banks. Stage C uses the remaining bounded slice on the Linear lane
        # with the deepest prior partial witness.
        tasks.extend(
            (
                family,
                by_family[family][0],
                1,
                "ACCESS_AWARE_ORDER",
                attempt_budget_by_stage[0],
            )
            for family in FAMILY_ORDER
        )
        tasks.extend(
            (
                family,
                by_family[family][0],
                -1,
                "ACCESS_AWARE_ORDER",
                attempt_budget_by_stage[1],
            )
            for family in FAMILY_ORDER
        )
        tasks.extend(
            (
                family,
                by_family[family][1],
                1,
                "S3_COMPATIBILITY_ORDER",
                (
                    known_lane_slice
                    if family == CompositionFamilyV2.LINEAR_BANDED
                    and by_family[family][1].composition_identity.endswith(
                        "LINEAR_BANDED:Y:POSITIVE:r1"
                    )
                    else attempt_budget_by_stage[2]
                ),
            )
            for family in FAMILY_ORDER
            if len(by_family[family]) > 1
        )
        tasks.extend(
            (
                family,
                by_family[family][1],
                -1,
                "S3_COMPATIBILITY_ORDER",
                alternate_mirrored_slice,
            )
            for family in FAMILY_ORDER
            if len(by_family[family]) > 1
        )
        tasks.append(
            (
                CompositionFamilyV2.LINEAR_BANDED,
                by_family[CompositionFamilyV2.LINEAR_BANDED][0],
                1,
                "ACCESS_AWARE_ORDER",
                linear_first_lane_continuation_slice,
            )
        )
    for family, handoff, bank_sign, search_order_lane, task_budget in tasks:
        if remaining <= 0 or (access_intent is None and family in families_with_candidate):
            continue
        family_key = family.value
        attempts[family_key] += 1
        domains = _domain_arrangement(handoff, bank_sign, boundary, dimension_authorities)
        allocation = min(task_budget, remaining)
        outcome = _search_one(
            handoff,
            shapes,
            authority_shapes,
            dimension_authorities,
            boundary,
            obstacles,
            domains,
            bank_sign,
            search_order_lane,
            allocation,
            access_intent,
            complete_candidate_admission,
            shipping_candidate_preflight,
        )
        solution = outcome.solution
        diagnostics = outcome.diagnostics
        visited = diagnostics.nodes
        if diagnostics.primary_search_nodes + diagnostics.forward_check_nodes != visited:
            raise RuntimeError("COMPOSITION_PLACEMENT_NODE_ACCOUNTING_MISMATCH")
        hit = diagnostics.budget_hit
        deepest_attempted = outcome.deepest_attempted
        used[family_key] += visited
        domain_anchor_by_family[family_key] += sum(diagnostics.domain_anchor_count.values())
        generic_anchor_by_family[family_key] += sum(diagnostics.generic_anchor_count.values())
        generic_nodes_by_family[family_key] += diagnostics.generic_nodes
        max_placed_by_family[family_key] = max(
            max_placed_by_family[family_key], diagnostics.max_placed
        )
        search_order = _zone_order(
            handoff,
            access_aware=access_intent is not None,
            search_order_lane=search_order_lane,
        )
        attempt_role_rank = {role: index for index, role in enumerate(search_order)}
        if attempt_role_rank[deepest_attempted] >= deepest_attempted_rank[family_key]:
            deepest_attempted_by_family[family_key] = deepest_attempted
            deepest_attempted_rank[family_key] = attempt_role_rank[deepest_attempted]
        deepest_placed = outcome.deepest_successfully_placed
        if (
            deepest_placed != "NOT_PLACED"
            and attempt_role_rank[deepest_placed] >= deepest_success_rank[family_key]
        ):
            deepest_successfully_placed[family_key] = deepest_placed
            deepest_success_rank[family_key] = attempt_role_rank[deepest_placed]
        attempt_failure = None
        if solution is None and not diagnostics.complete_placements:
            attempt_failure = (
                "COMPOSITION_VARIANT_NODE_ALLOCATION_EXHAUSTED"
                if hit
                else "NO_COMPLETE_COMPOSITION_CONSTRAINED_LAYOUT"
            )
        elif solution is None:
            attempt_failure = "COMPLETE_CANDIDATE_RETAINED_SEARCH_CONTINUED"
        search_attempts.append(
            CompositionPlacementSearchAttemptV1(
                family=family,
                composition_identity=handoff.composition_identity,
                composition_signature=handoff.composition_signature,
                process_axis=handoff.process_axis,
                process_direction=handoff.process_direction,
                peripheral_bank_sign=bank_sign,
                search_order_lane=search_order_lane,
                access_critical_construction_intent_identity=(
                    access_intent.identity if access_intent is not None else None
                ),
                construction_domains=domains,
                nodes_allocated=allocation,
                nodes_visited=visited,
                primary_search_nodes_used=diagnostics.primary_search_nodes,
                forward_check_nodes_used=diagnostics.forward_check_nodes,
                forward_check_attempt_node_limit=diagnostics.forward_check_node_limit,
                forward_check_regular_nodes_used=diagnostics.forward_check_regular_nodes,
                forward_check_chain_hole_nodes_used=diagnostics.forward_check_chain_hole_nodes,
                forward_check_regular_node_limit=diagnostics.forward_check_regular_node_limit,
                forward_check_chain_hole_node_limit=(
                    diagnostics.forward_check_chain_hole_node_limit
                ),
                forward_check_invocation_count=diagnostics.forward_check_invocation_count,
                forward_check_pass_count=diagnostics.forward_check_pass_count,
                forward_check_proved_no_completion_count=(
                    diagnostics.forward_check_proved_no_completion_count
                ),
                forward_check_unknown_budget_count=diagnostics.forward_check_unknown_budget_count,
                forward_check_unknown_other_count=diagnostics.forward_check_unknown_other_count,
                forward_check_cache_hit_count=diagnostics.forward_check_cache_hit_count,
                forward_check_unique_partial_signature_count=len(
                    diagnostics.forward_check_signatures
                ),
                forward_check_sequence_hash=canonical_hash(
                    [list(item) for item in diagnostics.forward_check_sequence]
                ),
                chain_starvation_prune_count_by_trigger_role=tuple(
                    sorted(diagnostics.chain_starvation_prune_count_by_trigger_role.items())
                ),
                packaging_local_pass_chain_forward_fail_count=(
                    diagnostics.packaging_local_pass_chain_forward_fail_count
                ),
                packaging_local_pass_chain_forward_pass_count=(
                    diagnostics.packaging_local_pass_chain_forward_pass_count
                ),
                secondary_local_pass_chain_forward_fail_count=(
                    diagnostics.secondary_local_pass_chain_forward_fail_count
                ),
                frozen_local_pass_chain_forward_fail_count=(
                    diagnostics.frozen_local_pass_chain_forward_fail_count
                ),
                personnel_local_pass_chain_forward_fail_count=(
                    diagnostics.personnel_local_pass_chain_forward_fail_count
                ),
                forward_check_witnesses=tuple(diagnostics.forward_check_witnesses),
                forward_check_negative_proofs=tuple(diagnostics.forward_check_negative_proofs),
                deepest_role_attempted=outcome.deepest_attempted,
                deepest_role_successfully_placed=deepest_placed,
                max_simultaneously_placed_role_count=diagnostics.max_placed,
                role_search_funnel=tuple(
                    RoleSearchFunnelV1(
                        zone_role=role,
                        **metrics,
                    )
                    for role, metrics in diagnostics.funnel.items()
                ),
                domain_derived_anchor_count_by_role=tuple(
                    (role, diagnostics.domain_anchor_count[role]) for role in search_order
                ),
                generic_fallback_anchor_count_by_role=tuple(
                    (role, diagnostics.generic_anchor_count[role]) for role in search_order
                ),
                generic_fallback_node_count_by_role=tuple(
                    (role, diagnostics.generic_nodes_by_role[role]) for role in search_order
                ),
                authority_shape_variant_count_by_role=tuple(
                    (role, diagnostics.authority_shape_count[role]) for role in search_order
                ),
                construction_shape_variant_count_by_role=tuple(
                    (role, diagnostics.construction_shape_count[role]) for role in search_order
                ),
                shipping_office_interface_preflight_status=diagnostics.shipping_office_status,
                shipping_truck_preflight_status=diagnostics.shipping_truck_preflight_status,
                shipping_truck_preflight_counts=tuple(
                    sorted(diagnostics.shipping_truck_preflight_counts.items())
                ),
                packaging_preflight_pass_partial_count=(
                    diagnostics.packaging_preflight_pass_partial_count
                ),
                packaging_preflight_fail_partial_count=(
                    diagnostics.packaging_preflight_fail_partial_count
                ),
                band_capacity_preflight_status=diagnostics.band_capacity_status,
                peripheral_capacity_preflight_status=diagnostics.peripheral_capacity_status,
                best_partial_placement_witness=diagnostics.best_witness
                or PartialPlacementWitnessV1(
                    composition_identity=handoff.composition_identity,
                    placed_roles=(),
                    zone_bounds_mm=(),
                    next_role=search_order[0],
                    failure_taxonomy="NO_PARTIAL_PLACEMENT",
                    hard_subset_rejection_count=0,
                    bank_sign=bank_sign,
                    nodes_used=visited,
                ),
                node_budget_exhausted=hit,
                complete_layout_found=bool(diagnostics.complete_placements),
                failure_reason=attempt_failure,
            )
        )
        remaining -= visited
        if diagnostics.complete_placements:
            for complete_zones, nodes_at_discovery in diagnostics.complete_placements:
                if access_intent is None:
                    candidate_provenance = [
                        (
                            "domain_arrangement",
                            "MIRROR_POSITIVE" if bank_sign > 0 else "MIRROR_NEGATIVE",
                        ),
                        ("nodes_visited", str(used[family_key])),
                        ("event_policy", "SITE_ROOM_EDGE_AND_CLOSED_OBSTACLE_PLUS_MINUS_GRID_MM"),
                        ("per_attempt_node_allocation", str(per_attempt_budget)),
                        (
                            "domain_anchor_path",
                            "COMPOSITION_DOMAIN_FIRST_BOUNDED_GENERIC_FALLBACK",
                        ),
                        ("shipping_office_preflight", diagnostics.shipping_office_status),
                    ]
                else:
                    candidate_provenance = [
                        (
                            "domain_arrangement",
                            "MIRROR_POSITIVE" if bank_sign > 0 else "MIRROR_NEGATIVE",
                        ),
                        ("nodes_visited", str(nodes_at_discovery)),
                        ("event_policy", "SITE_ROOM_EDGE_AND_CLOSED_OBSTACLE_PLUS_MINUS_GRID_MM"),
                        ("per_attempt_node_allocation", str(allocation)),
                        (
                            "domain_anchor_path",
                            "COMPOSITION_DOMAIN_FIRST_BOUNDED_GENERIC_FALLBACK",
                        ),
                        ("shipping_office_preflight", diagnostics.shipping_office_status),
                        ("search_order_lane", search_order_lane),
                        ("peripheral_bank_sign", str(bank_sign)),
                    ]
                if access_intent is not None:
                    candidate_provenance.append(
                        ("access_critical_construction_intent", access_intent.identity)
                    )
                candidates.append(
                    _candidate(
                        handoff,
                        complete_zones,
                        domains,
                        hashes,
                        tuple(candidate_provenance),
                    )
                )
        if solution is not None:
            failures.pop(family_key, None)
            families_with_candidate.add(family)
        elif diagnostics.complete_placements:
            failures.setdefault(family_key, "COMPLETE_CANDIDATE_RETAINED_SEARCH_CONTINUED")
        elif hit:
            failures[family_key] = "COMPOSITION_VARIANT_NODE_ALLOCATION_EXHAUSTED"
        else:
            failures.setdefault(family_key, "NO_COMPLETE_COMPOSITION_CONSTRAINED_LAYOUT")
    best_partial_by_family: dict[str, PartialPlacementWitnessV1] = {}
    for attempt in search_attempts:
        witness = attempt.best_partial_placement_witness
        family_key = attempt.family.value
        current = best_partial_by_family.get(family_key)
        witness_key = (
            -len(witness.placed_roles),
            witness.hard_subset_rejection_count,
            witness.zone_bounds_mm,
            witness.composition_identity,
            witness.bank_sign,
        )
        if current is None or witness_key < (
            -len(current.placed_roles),
            current.hard_subset_rejection_count,
            current.zone_bounds_mm,
            current.composition_identity,
            current.bank_sign,
        ):
            best_partial_by_family[family_key] = witness

    nodes_used = sum(used.values())
    return CompositionPlacementEnumerationV1(
        identity=IDENTITY,
        schema_version=SCHEMA_VERSION,
        node_budget=node_budget,
        nodes_used=nodes_used,
        node_budget_exhausted=nodes_used >= node_budget,
        initial_family_budget=initial_family_budget,
        continuation_budget=continuation_budget,
        continuation_selection_reason=(
            (
                "ACCESS_AWARE_CR2: Stage A gives each family 500 nodes on each first-composition "
                "bank. Stage B covers every alternate-composition positive bank, assigning "
                "20,000 nodes to the previously proven LINEAR_BANDED:Y:POSITIVE:r1 lane and "
                "4,000 to each other family, then 500 to every opposite alternate bank. Stage C "
                "allocates 27,500 nodes to the Linear first-composition positive-bank lane, "
                "whose prior partial witness reached 11/12. Allocations total exactly 60,000; "
                "historical geometry and candidate hashes are not reused."
            )
            if access_intent is not None and node_budget == 60_000
            else (
                "ROUND_1: positive-bank probe for each family; ROUND_2: mirrored first-composition "
                "probe for each family; only then deterministic second-composition continuations "
                "in family order, each bounded by the same per-attempt slice"
            )
        ),
        family_coverage_order=tuple(family.value for family in FAMILY_ORDER),
        family_first_round_complete=all(attempts[family.value] >= 1 for family in FAMILY_ORDER),
        attempt_count_by_family=tuple(
            (family.value, attempts[family.value]) for family in FAMILY_ORDER
        ),
        nodes_used_by_family=tuple((family.value, used[family.value]) for family in FAMILY_ORDER),
        deepest_role_attempted_by_family=tuple(
            (family.value, deepest_attempted_by_family[family.value]) for family in FAMILY_ORDER
        ),
        deepest_role_successfully_placed_by_family=tuple(
            (family.value, deepest_successfully_placed[family.value]) for family in FAMILY_ORDER
        ),
        max_simultaneously_placed_role_count_by_family=tuple(
            (family.value, max_placed_by_family[family.value]) for family in FAMILY_ORDER
        ),
        best_partial_placement_witness_by_family=tuple(
            (family.value, best_partial_by_family[family.value])
            for family in FAMILY_ORDER
            if family.value in best_partial_by_family
        ),
        domain_derived_anchor_count_by_family=tuple(
            (family.value, domain_anchor_by_family[family.value]) for family in FAMILY_ORDER
        ),
        generic_fallback_anchor_count_by_family=tuple(
            (family.value, generic_anchor_by_family[family.value]) for family in FAMILY_ORDER
        ),
        generic_fallback_node_count_by_family=tuple(
            (family.value, generic_nodes_by_family[family.value]) for family in FAMILY_ORDER
        ),
        failure_reason_by_family=tuple((key, failures[key]) for key in sorted(failures)),
        search_attempts=tuple(search_attempts),
        candidates=tuple(candidates),
    )
