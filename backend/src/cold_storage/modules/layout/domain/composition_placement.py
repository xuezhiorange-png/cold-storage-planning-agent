"""Bounded rectangle placement constrained by whole-building composition intent.

This module produces exact rectangle candidates only.  Construction domains are
search organizers, not site/access/Truck engineering authorities.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from decimal import ROUND_CEILING, Decimal
from hashlib import sha256
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
SUCCESSOR_CAPACITY_ENGINEERING_AUTHORITY = False
SUCCESSOR_CAPACITY_VALIDATION_AUTHORITY = False
SUCCESSOR_DOMAIN_SOURCE = "PRIMARY_FINITE_ORIGIN_UNION"
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
    forward_check_skipped_due_to_valid_witness_count: int
    forward_check_exact_cache_hit_count: int
    witness_created_count: int
    witness_reuse_attempt_count: int
    witness_reuse_accepted_count: int
    witness_reuse_rejected_count: int
    witness_inheritance_count: int
    witness_invalidated_by_new_geometry_count: int
    witness_invalidated_by_site_count: int
    witness_invalidated_by_obstacle_count: int
    witness_invalidated_by_overlap_count: int
    witness_invalidated_by_must_edge_count: int
    witness_invalidated_by_other_hard_check_count: int
    witness_sequence_hash: str
    witness_events: tuple[Mapping[str, Any], ...]
    chain_starvation_prune_count_by_trigger_role: tuple[tuple[str, int], ...]
    packaging_local_pass_chain_forward_fail_count: int
    packaging_local_pass_chain_forward_pass_count: int
    secondary_local_pass_chain_forward_fail_count: int
    frozen_local_pass_chain_forward_fail_count: int
    personnel_local_pass_chain_forward_fail_count: int
    forward_check_witnesses: tuple[Mapping[str, Any], ...]
    forward_check_negative_proofs: tuple[Mapping[str, Any], ...]
    composition_propagation_evaluation_count: int
    composition_propagation_provable_rejection_count: int
    composition_propagation_rank_only_count: int
    linear_raw_core_bound_evaluation_count: int
    linear_raw_core_provable_rejection_count: int
    linear_core_finished_bound_evaluation_count: int
    linear_core_finished_provable_rejection_count: int
    central_bound_evaluation_count: int
    central_provable_rejection_count: int
    spine_monotonic_bound_evaluation_count: int
    spine_monotonic_provable_rejection_count: int
    composition_propagation_sequence_hash: str
    forward_probe_funnel_by_role: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]
    forward_probe_candidate_samples: tuple[Mapping[str, Any], ...]
    forward_probe_budget_stop_samples: tuple[Mapping[str, Any], ...]
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
    successor_capacity_diagnostics: Mapping[str, Any] | None = None

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
            "forward_check_skipped_due_to_valid_witness_count": (
                self.forward_check_skipped_due_to_valid_witness_count
            ),
            "forward_check_exact_cache_hit_count": self.forward_check_exact_cache_hit_count,
            "witness_created_count": self.witness_created_count,
            "witness_reuse_attempt_count": self.witness_reuse_attempt_count,
            "witness_reuse_accepted_count": self.witness_reuse_accepted_count,
            "witness_reuse_rejected_count": self.witness_reuse_rejected_count,
            "witness_inheritance_count": self.witness_inheritance_count,
            "witness_invalidated_by_new_geometry_count": (
                self.witness_invalidated_by_new_geometry_count
            ),
            "witness_invalidated_by_site_count": self.witness_invalidated_by_site_count,
            "witness_invalidated_by_obstacle_count": self.witness_invalidated_by_obstacle_count,
            "witness_invalidated_by_overlap_count": self.witness_invalidated_by_overlap_count,
            "witness_invalidated_by_must_edge_count": self.witness_invalidated_by_must_edge_count,
            "witness_invalidated_by_other_hard_check_count": (
                self.witness_invalidated_by_other_hard_check_count
            ),
            "witness_sequence_hash": self.witness_sequence_hash,
            "witness_events": [dict(item) for item in self.witness_events],
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
            "composition_propagation": {
                "engineering_authority": False,
                "validation_authority": False,
                "search_optimization_only": True,
                "source": "EXISTING_COMPOSITION_INTENT_PREDICATE",
                "evaluation_count": self.composition_propagation_evaluation_count,
                "provable_rejection_count": (self.composition_propagation_provable_rejection_count),
                "rank_only_count": self.composition_propagation_rank_only_count,
                "linear_raw_core_bound_evaluation_count": (
                    self.linear_raw_core_bound_evaluation_count
                ),
                "linear_raw_core_provable_rejection_count": (
                    self.linear_raw_core_provable_rejection_count
                ),
                "linear_core_finished_bound_evaluation_count": (
                    self.linear_core_finished_bound_evaluation_count
                ),
                "linear_core_finished_provable_rejection_count": (
                    self.linear_core_finished_provable_rejection_count
                ),
                "central_bound_evaluation_count": self.central_bound_evaluation_count,
                "central_provable_rejection_count": self.central_provable_rejection_count,
                "spine_monotonic_bound_evaluation_count": (
                    self.spine_monotonic_bound_evaluation_count
                ),
                "spine_monotonic_provable_rejection_count": (
                    self.spine_monotonic_provable_rejection_count
                ),
                "decision_sequence_hash": self.composition_propagation_sequence_hash,
                "forward_probe_funnel_by_role": {
                    role: dict(metrics) for role, metrics in self.forward_probe_funnel_by_role
                },
                "accepted_candidate_samples": [
                    dict(item) for item in self.forward_probe_candidate_samples
                ],
                "budget_stop_candidate_samples": [
                    dict(item) for item in self.forward_probe_budget_stop_samples
                ],
                "propagation_range_is_conservative": True,
                "false_negative_allowed": False,
                "heuristic_can_hard_reject": False,
            },
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
            "mandatory_chain_successor_capacity": (
                dict(self.successor_capacity_diagnostics)
                if self.successor_capacity_diagnostics is not None
                else {}
            ),
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
    witness_created_count: int = 0
    witness_reuse_attempt_count: int = 0
    witness_reuse_accepted_count: int = 0
    witness_reuse_rejected_count: int = 0
    witness_inheritance_count: int = 0
    witness_invalidated_by_new_geometry_count: int = 0
    witness_invalidated_by_site_count: int = 0
    witness_invalidated_by_obstacle_count: int = 0
    witness_invalidated_by_overlap_count: int = 0
    witness_invalidated_by_must_edge_count: int = 0
    witness_invalidated_by_other_hard_check_count: int = 0
    forward_check_skipped_due_to_valid_witness_count: int = 0
    witness_events: list[Mapping[str, Any]] = field(default_factory=list)
    composition_propagation_evaluation_count: int = 0
    composition_propagation_provable_rejection_count: int = 0
    composition_propagation_rank_only_count: int = 0
    linear_raw_core_bound_evaluation_count: int = 0
    linear_raw_core_provable_rejection_count: int = 0
    linear_core_finished_bound_evaluation_count: int = 0
    linear_core_finished_provable_rejection_count: int = 0
    central_bound_evaluation_count: int = 0
    central_provable_rejection_count: int = 0
    spine_monotonic_bound_evaluation_count: int = 0
    spine_monotonic_provable_rejection_count: int = 0
    composition_propagation_sequence: list[tuple[str, tuple[int, int, int, int], str, str, int]] = (
        field(default_factory=list)
    )
    forward_probe_funnel: dict[str, dict[str, int]] = field(default_factory=dict)
    forward_probe_candidate_samples: list[Mapping[str, Any]] = field(default_factory=list)
    forward_probe_budget_stop_samples: list[Mapping[str, Any]] = field(default_factory=list)
    main_chain_successor_capacity_check_count: int = 0
    successor_capacity_pass_count: int = 0
    successor_capacity_proved_none_count: int = 0
    successor_capacity_unknown_budget_count: int = 0
    successor_capacity_unknown_other_count: int = 0
    successor_capacity_witness_created_count: int = 0
    successor_capacity_witness_reuse_attempt_count: int = 0
    successor_capacity_witness_reused_count: int = 0
    successor_capacity_witness_invalidated_count: int = 0
    successor_capacity_same_parent_replay_mismatch: bool = False
    successor_capacity_edge_diagnostics: dict[str, dict[str, Any]] = field(default_factory=dict)
    successor_capacity_witnesses: list[Mapping[str, Any]] = field(default_factory=list)
    successor_capacity_decision_sequence: list[tuple[str, str, str, str, int]] = field(
        default_factory=list
    )
    successor_free_space_profiles: list[Mapping[str, Any]] = field(default_factory=list)

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
    witness_shape_specs: tuple[tuple[str, _Shape], ...] = ()
    cache_hit: bool = False
    cached_probe_nodes: int = 0


@dataclass(frozen=True)
class _FeasibleSuccessorDomainV1:
    """Exact-MUST-filtered view of an existing finite construction domain.

    The object is an invocation-local search structure. Its candidates are
    generated by the same domain/access/physical-event union as the forward
    probe, and filtering is only the existing positive-edge MUST predicate.
    """

    successor_role: str
    parent_partial_geometry_hash: str
    source_finite_domain_identity: str
    fixed_must_neighbors: tuple[str, ...]
    raw_finite_origin_count: int
    must_edge_compatible_origin_count: int
    origins: tuple[tuple[int, int], ...]
    shape: _Shape
    engineering_authority: bool = False
    validation_authority: bool = False


@dataclass(frozen=True)
class _FeasibleSuccessorWitnessV1:
    """A non-authoritative, revalidatable first-support search hint."""

    parent_partial_geometry_hash: str
    composition_identity: str
    composition_signature: str
    bank_sign: int
    predecessor_roles: tuple[str, ...]
    successor_role: str
    bounds_mm: tuple[int, int, int, int]
    shape: _Shape
    authoritative_shape_identity: str
    source_finite_domain_identity: str
    engineering_authority: bool = False
    validation_authority: bool = False


@dataclass(frozen=True)
class _MainChainCompletionWitnessV1:
    """Invocation-local constructive hint from a positive optimistic probe.

    The witness is neither placement nor validation authority. Every geometry
    is replayed through the ordinary primary candidate checks before use.
    """

    source_partial_geometry_hash: str
    composition_identity: str
    composition_signature: str
    bank_sign: int
    main_chain_source: str
    fixed_main_chain_roles: tuple[str, ...]
    unplaced_main_chain_roles: tuple[str, ...]
    ordered_witness_roles: tuple[str, ...]
    witness_geometry: tuple[tuple[str, tuple[int, int, int, int], _Shape, str], ...]
    source_forward_check_status: str
    engineering_authority: bool = False
    validation_authority: bool = False

    def geometry_for(self, role: str) -> tuple[tuple[int, int, int, int], _Shape, str] | None:
        for witness_role, bounds, shape, shape_identity in self.witness_geometry:
            if witness_role == role:
                return bounds, shape, shape_identity
        return None

    def without_role(self, role: str) -> _MainChainCompletionWitnessV1 | None:
        remaining = tuple(item for item in self.witness_geometry if item[0] != role)
        if len(remaining) == len(self.witness_geometry):
            return self
        if not remaining:
            return None
        remaining_roles = tuple(item[0] for item in remaining)
        return replace(
            self,
            ordered_witness_roles=remaining_roles,
            witness_geometry=remaining,
        )


@dataclass(frozen=True)
class _CompositionIntentProjectionDecisionV1:
    """Conservative necessary-condition result derived from existing intent.

    The site-boundary projection interval is a superset of every legal room
    center in the finite construction search. A negative result is therefore
    used only when no completion can satisfy the existing group/chain
    inequalities; all surviving geometry still reaches the original exact
    partial-intent predicate.
    """

    status: str
    slack: int
    reason: str
    evaluated_rules: tuple[str, ...] = ()
    rejected_rules: tuple[str, ...] = ()


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
        successor_attempts = [
            dict(attempt.successor_capacity_diagnostics)
            for attempt in self.search_attempts
            if attempt.successor_capacity_diagnostics is not None
        ]
        successor_edges: dict[str, dict[str, Any]] = {}
        for diagnostics in successor_attempts:
            for edge_key, row in diagnostics.get("edge_capacity", {}).items():
                aggregate = successor_edges.get(edge_key)
                if aggregate is None:
                    successor_edges[edge_key] = dict(row)
                    continue
                for key, value in row.items():
                    if key not in ("predecessor", "successor") and isinstance(value, int):
                        aggregate[key] = int(aggregate.get(key, 0)) + value
        successor_witnesses = [
            witness
            for diagnostics in successor_attempts
            for witness in diagnostics.get("witnesses", [])
        ]
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
            "main_chain_completion_witness_implemented": True,
            "witness_engineering_authority": False,
            "witness_validation_authority": False,
            "witness_scope": "CURRENT_SEARCH_INVOCATION_ONLY",
            "witness_footprint_is_hard_reserved": False,
            "witness_compatibility_can_reorder": True,
            "witness_compatibility_can_hard_reject": False,
            "witness_source_must_be_forward_check_pass": True,
            "witness_bypasses_hard_checks": False,
            "forward_check_attempt_slice_divisor": FORWARD_CHECK_ATTEMPT_SLICE_DIVISOR,
            "forward_check_trigger_roles": sorted(FORWARD_CHECK_TRIGGER_ROLES),
            "unplaced_non_main_roles_ignored": True,
            "unknown_forward_check_can_prune": UNKNOWN_FORWARD_CHECK_CAN_PRUNE,
            "forward_check_budget_exhaustion_can_prune": (
                FORWARD_CHECK_BUDGET_EXHAUSTION_CAN_PRUNE
            ),
            "whole_building_completion_first_class_search_objective": True,
            "mandatory_chain_successor_capacity": {
                "engineering_authority": SUCCESSOR_CAPACITY_ENGINEERING_AUTHORITY,
                "validation_authority": SUCCESSOR_CAPACITY_VALIDATION_AUTHORITY,
                "search_optimization_only": True,
                "main_chain_source": MAIN_CHAIN_SOURCE,
                "must_chain_source": "EXISTING_PROCESS_GRAPH_MUST_ADJACENCIES",
                "must_edge_early_filter_source": "EXISTING_MUST_ADJACENCY",
                "successor_domain_source": SUCCESSOR_DOMAIN_SOURCE,
                "successor_domain_is_primary_search_equivalent_or_superset": True,
                "existing_final_must_predicate_preserved": True,
                "multi_placed_must_neighbor_edge_filter_implemented": True,
                "unknown_can_prune": False,
                "total_check_count": sum(
                    int(item.get("check_count", 0)) for item in successor_attempts
                ),
                "pass_count": sum(int(item.get("pass_count", 0)) for item in successor_attempts),
                "proved_none_count": sum(
                    int(item.get("proved_none_count", 0)) for item in successor_attempts
                ),
                "unknown_budget_count": sum(
                    int(item.get("unknown_budget_count", 0)) for item in successor_attempts
                ),
                "unknown_other_count": sum(
                    int(item.get("unknown_other_count", 0)) for item in successor_attempts
                ),
                "witness_created_count": sum(
                    int(item.get("witness_created_count", 0)) for item in successor_attempts
                ),
                "witness_reuse_attempt_count": sum(
                    int(item.get("witness_reuse_attempt_count", 0)) for item in successor_attempts
                ),
                "witness_reused_count": sum(
                    int(item.get("witness_reused_count", 0)) for item in successor_attempts
                ),
                "witness_invalidated_count": sum(
                    int(item.get("witness_invalidated_count", 0)) for item in successor_attempts
                ),
                "same_parent_replay_mismatch": any(
                    bool(item.get("same_parent_replay_mismatch")) for item in successor_attempts
                ),
                "edge_capacity": successor_edges,
                "witnesses": successor_witnesses,
                "attempt_sequence_hashes": {
                    f"{attempt.family.value}:{attempt.composition_identity}:"
                    f"{attempt.peripheral_bank_sign}:{attempt.search_order_lane}": (
                        dict(attempt.successor_capacity_diagnostics).get(
                            "decision_sequence_hash", ""
                        )
                    )
                    for attempt in self.search_attempts
                    if attempt.successor_capacity_diagnostics is not None
                },
            },
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
            "forward_check_exact_cache_hit_count": sum(
                item.forward_check_exact_cache_hit_count for item in self.search_attempts
            ),
            "forward_check_skipped_due_to_valid_witness_count": sum(
                item.forward_check_skipped_due_to_valid_witness_count
                for item in self.search_attempts
            ),
            "witness_created_count": sum(
                item.witness_created_count for item in self.search_attempts
            ),
            "witness_reuse_attempt_count": sum(
                item.witness_reuse_attempt_count for item in self.search_attempts
            ),
            "witness_reuse_accepted_count": sum(
                item.witness_reuse_accepted_count for item in self.search_attempts
            ),
            "witness_reuse_rejected_count": sum(
                item.witness_reuse_rejected_count for item in self.search_attempts
            ),
            "witness_inheritance_count": sum(
                item.witness_inheritance_count for item in self.search_attempts
            ),
            "witness_invalidated_by_new_geometry_count": sum(
                item.witness_invalidated_by_new_geometry_count for item in self.search_attempts
            ),
            "witness_invalidated_by_site_count": sum(
                item.witness_invalidated_by_site_count for item in self.search_attempts
            ),
            "witness_invalidated_by_obstacle_count": sum(
                item.witness_invalidated_by_obstacle_count for item in self.search_attempts
            ),
            "witness_invalidated_by_overlap_count": sum(
                item.witness_invalidated_by_overlap_count for item in self.search_attempts
            ),
            "witness_invalidated_by_must_edge_count": sum(
                item.witness_invalidated_by_must_edge_count for item in self.search_attempts
            ),
            "witness_invalidated_by_other_hard_check_count": sum(
                item.witness_invalidated_by_other_hard_check_count for item in self.search_attempts
            ),
            "witness_sequence_hashes": {
                f"{attempt.family.value}:{attempt.composition_identity}:"
                f"{attempt.peripheral_bank_sign}:{attempt.search_order_lane}": (
                    attempt.witness_sequence_hash
                )
                for attempt in self.search_attempts
            },
            "witness_events": [
                dict(row) for attempt in self.search_attempts for row in attempt.witness_events
            ],
            "same_parent_witness_primary_replay_mismatch": any(
                bool(row.get("same_parent_replay_mismatch"))
                for attempt in self.search_attempts
                for row in attempt.witness_events
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


def _feasible_successor_domain(
    role: str,
    shape: _Shape,
    origins: Sequence[tuple[int, int]],
    placed: Mapping[str, PlacedRectangleV1],
    handoff: StructuralCompositionPlacementHandoffV1,
    bank_sign: int,
) -> _FeasibleSuccessorDomainV1:
    """Apply only exact existing MUST-edge compatibility to finite origins.

    ``origins`` must be the union assembled by the caller from its ordinary
    finite composition, Access, MUST-face, and physical-event generators.
    Filtering every placed MUST neighbor is equivalent to the later hard
    predicate; the unfiltered union is never silently narrowed by a heuristic.
    """
    neighbors = tuple(sorted(name for name in _must_neighbors(role) if name in placed))
    unique_origins = tuple(sorted(set(origins)))
    compatible = tuple(
        point
        for point in unique_origins
        if all(
            rectangles_share_positive_edge(
                _rectangle(role, point[0], point[1], shape), placed[neighbor]
            )
            for neighbor in neighbors
        )
    )
    parent_hash = _main_chain_partial_geometry_hash(handoff, bank_sign, placed)
    domain_identity = canonical_hash(
        {
            "source": SUCCESSOR_DOMAIN_SOURCE,
            "successor_role": role,
            "shape": asdict(shape),
            "finite_origins": [list(point) for point in unique_origins],
            "fixed_must_neighbors": {
                neighbor: list(_bounds(placed[neighbor])) for neighbor in neighbors
            },
            "composition_identity": handoff.composition_identity,
            "composition_signature": handoff.composition_signature,
        }
    )
    return _FeasibleSuccessorDomainV1(
        successor_role=role,
        parent_partial_geometry_hash=parent_hash,
        source_finite_domain_identity=domain_identity,
        fixed_must_neighbors=neighbors,
        raw_finite_origin_count=len(unique_origins),
        must_edge_compatible_origin_count=len(compatible),
        origins=compatible,
        shape=shape,
    )


def _successor_edge_keys(
    successor_role: str,
    placed: Mapping[str, PlacedRectangleV1],
) -> tuple[str, ...]:
    material_edges = tuple(
        (flow.from_ref, flow.to_ref) for flow in process_graph().flows if flow.kind == "MATERIAL"
    )
    must_edges = {frozenset(pair) for pair in process_graph().must_adjacencies}
    return tuple(
        f"{predecessor}->{successor}"
        for predecessor, successor in material_edges
        if (
            (successor == successor_role and predecessor in placed)
            or (predecessor == successor_role and successor in placed)
        )
        and frozenset((predecessor, successor)) in must_edges
    )


def _rectangular_polygon_bounds(polygon: PolygonMM) -> tuple[int, int, int, int] | None:
    """Recognize exact axis-aligned rectangles, never approximate polygons."""
    left, right = min(p[0] for p in polygon), max(p[0] for p in polygon)
    bottom, top = min(p[1] for p in polygon), max(p[1] for p in polygon)
    if len(polygon) == 4 and set(polygon) == {
        (left, bottom),
        (left, top),
        (right, bottom),
        (right, top),
    }:
        return left, bottom, right, top
    return None


def _exact_successor_free_space_domain(
    role: str,
    shape: _Shape,
    origins: Sequence[tuple[int, int]],
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    handoff: StructuralCompositionPlacementHandoffV1,
    bank_sign: int,
) -> tuple[tuple[tuple[int, int], ...], Mapping[str, Any]]:
    """Subtract exact physical exclusions from a finite origin domain.

    No new origins, shape search, recursive expansion, or validator is added.
    All blockers are recorded (not just the first failing predicate). The
    result is only a search domain: survivors still undergo normal hard checks.
    Counterfactuals release ONE non-MUST room footprint in this fixed domain;
    they never mutate placement or authorize a room's removal.
    """
    groups = {item.zone_role: item.composition_group for item in handoff.zone_role_assignment}
    must_neighbors = set(_must_neighbors(role))
    rows: list[dict[str, Any]] = []
    survivors: list[tuple[int, int]] = []
    exclusive: Counter[str] = Counter()
    obstacle_counts: Counter[str] = Counter()
    room_counts: Counter[str] = Counter()
    group_counts: Counter[str] = Counter()
    release: dict[str, list[list[int]]] = {}
    boundary_box = _rectangular_polygon_bounds(boundary)
    obstacle_facts = tuple(
        (canonical_hash({"polygon_mm": polygon}), polygon, _rectangular_polygon_bounds(polygon))
        for polygon in obstacles
    )
    occupied = {name: _bounds(existing) for name, existing in placed.items()}
    polygon_fallback_count = 0
    for x, y in origins:
        right, top = x + shape.world_width_mm, y + shape.world_depth_mm
        candidate = None
        if boundary_box is not None:
            site_blocked = not (
                boundary_box[0] <= x
                and boundary_box[1] <= y
                and right <= boundary_box[2]
                and top <= boundary_box[3]
            )
        else:
            candidate = _rectangle(role, x, y, shape)
            site_blocked = not rectangle_inside_polygon(candidate, boundary)
            polygon_fallback_count += 1
        obstacle_ids = []
        for identity, polygon, box in obstacle_facts:
            if box is not None:
                # Closed obstacles prohibit touching; room overlaps below
                # require positive area. These are exact origin exclusions,
                # not bounding-box approximations of a nonrectangular polygon.
                blocked = x <= box[2] and box[0] <= right and y <= box[3] and box[1] <= top
            else:
                if candidate is None:
                    candidate = _rectangle(role, x, y, shape)
                blocked = rectangle_intersects_closed_obstacle(candidate, polygon)
                polygon_fallback_count += 1
            if blocked:
                obstacle_ids.append(identity)
        room_roles = sorted(
            name
            for name, box in occupied.items()
            if x < box[2] and box[0] < right and y < box[3] and box[1] < top
        )
        first = (
            "SITE"
            if site_blocked
            else "OBSTACLE"
            if obstacle_ids
            else "OVERLAP"
            if room_roles
            else "FREE_SPACE"
        )
        exclusive[first] += 1
        obstacle_counts.update(obstacle_ids)
        room_counts.update(room_roles)
        group_counts.update(sorted({groups[name] for name in room_roles}))
        bounds = [x, y, right, top]
        if first == "FREE_SPACE":
            survivors.append((x, y))
        # A simultaneous site/obstacle/MUST blocker cannot be released by
        # removing a single non-MUST room. Retain exactly the same origins.
        if not site_blocked and not obstacle_ids and len(room_roles) == 1:
            blocker = room_roles[0]
            if blocker not in must_neighbors:
                release.setdefault(blocker, []).append(bounds)
        rows.append(
            {
                "bounds_mm": bounds,
                "site_boundary_blocked": site_blocked,
                "obstacle_identities": obstacle_ids,
                "overlapping_room_roles": room_roles,
                "overlapping_groups": sorted({groups[name] for name in room_roles}),
                "exclusive_classification": first,
            }
        )
    profile = {
        "engineering_authority": False,
        "validation_authority": False,
        "search_optimization_only": True,
        "source": "EXISTING_EXACT_SITE_OBSTACLE_OVERLAP_PREDICATES",
        "rectangular_origin_interval_subtraction": True,
        "nonrectangular_polygon_predicate_fallback_count": polygon_fallback_count,
        "role": role,
        "shape": asdict(shape),
        "partial_geometry_hash": _main_chain_partial_geometry_hash(handoff, bank_sign, placed),
        "fixed_zone_bounds_mm": {name: list(_bounds(placed[name])) for name in sorted(placed)},
        "finite_domain_count": len(rows),
        "free_space_count": len(survivors),
        "classified_count": sum(exclusive.values()),
        "unclassified_count": 0,
        "exclusive_counts": dict(sorted(exclusive.items())),
        "obstacle_identity_counts": dict(sorted(obstacle_counts.items())),
        "overlapping_room_counts": dict(sorted(room_counts.items())),
        "overlapping_group_counts": dict(sorted(group_counts.items())),
        "candidates": rows,
        "single_non_must_blocker_release": [
            {
                "released_role": name,
                "released_group": groups[name],
                "restored_physical_domain_count": len(release.get(name, [])),
                "restored_bounds_mm": release.get(name, []),
                "diagnostic_only": True,
                "geometry_mutated": False,
                "proves_complete_layout": False,
            }
            for name in sorted(set(placed) - must_neighbors)
        ],
        "successor_domain_conflict_set": {
            "site_boundary": exclusive["SITE"] > 0,
            "obstacle_identities": sorted(obstacle_counts),
            "room_roles": sorted(room_counts),
            "groups": sorted(group_counts),
            "covers_all_physical_exclusions": True,
            "minimal_conflict_set_claimed": False,
            "global_infeasibility_proven": False,
            "hard_recovery_authority": False,
        },
    }
    return tuple(survivors), profile


def _axis_coordinate(rectangle: PlacedRectangleV1, axis: str) -> int:
    return _center(rectangle, axis)


def _primitive_diagnostic_hash(value: object) -> str:
    """Canonical digest for diagnostic trees of strings/ints/bools only.

    These records contain no Decimal/float or authority objects. Avoid the
    recursive engineering-number normalization for every diagnostic scalar;
    JSON's tuple-to-array encoding is identical to canonical_hash here.
    This function is never used for authority or candidate identities.
    """
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + sha256(encoded.encode("utf-8")).hexdigest()


def _signed_group_center_range(
    roles: Sequence[str],
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    axis: str,
    sign: int,
    shape_variants: Mapping[str, tuple[_Shape, ...]] | None = None,
) -> tuple[int, int]:
    """Bound the exact floor-average group center used by composition intent."""
    site_coordinates = [point[0 if axis == "X" else 1] for point in boundary]
    site_low, site_high = min(site_coordinates), max(site_coordinates)
    centers: list[tuple[int, int]] = []
    for role in roles:
        if role in placed:
            center = _axis_coordinate(placed[role], axis)
            centers.append((center, center))
            continue
        low, high = site_low, site_high
        variants = (shape_variants or {}).get(role, ())
        if variants:
            role_max_span = max(
                item.world_width_mm if axis == "X" else item.world_depth_mm for item in variants
            )
            for neighbor in _must_neighbors(role):
                neighbor_rectangle = placed.get(neighbor)
                if neighbor_rectangle is None:
                    continue
                neighbor_bounds = _bounds(neighbor_rectangle)
                neighbor_span = (
                    neighbor_bounds[2] - neighbor_bounds[0]
                    if axis == "X"
                    else neighbor_bounds[3] - neighbor_bounds[1]
                )
                # A positive shared edge bounds center separation by the sum
                # of half-spans. The extra grid unit covers integer-center
                # flooring and keeps this a conservative superset.
                max_delta = (role_max_span + neighbor_span + 1) // 2 + GRID_MM
                neighbor_center = _axis_coordinate(neighbor_rectangle, axis)
                low = max(low, neighbor_center - max_delta)
                high = min(high, neighbor_center + max_delta)
        # An empty interval is not converted into a propagation proof here;
        # the exact MUST construction predicate remains responsible for it.
        centers.append((low, high) if low <= high else (site_low, site_high))
    physical_low = sum(low for low, _ in centers) // len(roles)
    physical_high = sum(high for _, high in centers) // len(roles)
    return (physical_low, physical_high) if sign > 0 else (-physical_high, -physical_low)


def _composition_intent_projection_decision(
    handoff: StructuralCompositionPlacementHandoffV1,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    shape_variants: Mapping[str, tuple[_Shape, ...]] | None = None,
    faces: Mapping[str, tuple[str, int]] | None = None,
) -> _CompositionIntentProjectionDecisionV1:
    """Project only necessary inequalities from the existing intent rules.

    This is a safe prefilter/order signal, not a replacement for
    ``_partial_intent_possible``. Unknown future roles retain the full site
    bbox projection range; only a provably empty completion interval rejects.
    """
    axis = handoff.process_axis.value
    sign = 1 if handoff.process_direction == ProcessDirectionV1.POSITIVE else -1
    evaluated: list[str] = []
    rejected: list[str] = []
    slack_values: list[int] = []

    sorting = placed.get("sorting_packaging_room")
    if sorting is not None and faces:
        for role, rectangle in placed.items():
            if role in faces:
                rule = f"EXISTING_SIDE_INTENT:{role}"
                evaluated.append(rule)
                if not _side_ok(role, rectangle, sorting, faces):
                    rejected.append(rule)

    if handoff.family == CompositionFamilyV2.LINEAR_BANDED and "sorting_packaging_room" in placed:
        raw = _signed_group_center_range(
            ("raw_fruit_buffer", "primary_precooling_room"),
            placed,
            boundary,
            axis,
            sign,
            shape_variants,
        )
        core = _signed_group_center_range(
            ("sorting_packaging_room", "secondary_precooling_room", "coating_room"),
            placed,
            boundary,
            axis,
            sign,
            shape_variants,
        )
        evaluated.append("LINEAR_RAW_CORE")
        raw_core_slack = core[1] - raw[0]
        slack_values.append(raw_core_slack)
        if raw[0] >= core[1]:
            rejected.append("LINEAR_RAW_CORE")

        finished = _signed_group_center_range(
            ("finished_goods_room", "shipping_channel"),
            placed,
            boundary,
            axis,
            sign,
            shape_variants,
        )
        evaluated.append("LINEAR_CORE_FINISHED")
        core_finished_slack = finished[1] - core[0]
        slack_values.append(core_finished_slack)
        if core[0] >= finished[1]:
            rejected.append("LINEAR_CORE_FINISHED")

    elif (
        handoff.family == CompositionFamilyV2.CENTRAL_PROCESS_CORE
        and "sorting_packaging_room" in placed
    ):
        sorting_projection = sign * _axis_coordinate(placed["sorting_packaging_room"], axis)
        raw = _signed_group_center_range(
            ("raw_fruit_buffer", "primary_precooling_room"),
            placed,
            boundary,
            axis,
            sign,
            shape_variants,
        )
        evaluated.append("CENTRAL_RAW_SORTING")
        raw_slack = sorting_projection - raw[0]
        slack_values.append(raw_slack)
        if raw[0] >= sorting_projection:
            rejected.append("CENTRAL_RAW_SORTING")

        finished = _signed_group_center_range(
            ("finished_goods_room", "shipping_channel"),
            placed,
            boundary,
            axis,
            sign,
            shape_variants,
        )
        evaluated.append("CENTRAL_FINISHED_SORTING")
        finished_slack = finished[1] - sorting_projection
        slack_values.append(finished_slack)
        if finished[1] <= sorting_projection:
            rejected.append("CENTRAL_FINISHED_SORTING")

    elif handoff.family == CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS:
        chain = _main_chain_roles_from_process_graph()
        fixed = tuple(role for role in chain if role in placed)
        if len(fixed) >= 2:
            evaluated.append("SPINE_MONOTONIC")
            projections = tuple(sign * _axis_coordinate(placed[role], axis) for role in fixed)
            gaps = tuple(
                second - first for first, second in zip(projections, projections[1:], strict=False)
            )
            slack_values.extend(gaps)
            if any(gap < 0 for gap in gaps):
                rejected.append("SPINE_MONOTONIC")

    return _CompositionIntentProjectionDecisionV1(
        status="PROVABLY_INCOMPATIBLE" if rejected else "POSSIBLY_COMPATIBLE",
        slack=min(slack_values, default=0),
        reason=",".join(rejected) if rejected else "NO_PROVEN_INTENT_CONFLICT",
        evaluated_rules=tuple(evaluated),
        rejected_rules=tuple(rejected),
    )


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


def _main_chain_partial_geometry_hash(
    handoff: StructuralCompositionPlacementHandoffV1,
    bank_sign: int,
    placed: Mapping[str, PlacedRectangleV1],
) -> str:
    return canonical_hash(
        {
            "composition_identity": handoff.composition_identity,
            "composition_signature": handoff.composition_signature,
            "bank_sign": bank_sign,
            "fixed_geometry": {role: list(_bounds(placed[role])) for role in sorted(placed)},
            "main_chain": list(_main_chain_roles_from_process_graph()),
        }
    )


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
    dimension_authorities: Mapping[str, Mapping[str, Any]] | None = None,
) -> _MainChainForwardCheckResultV1:
    """Probe an optimistic finite completion of only the existing MATERIAL chain.

    This is construction-search pruning only.  A negative result is returned
    only after every event-derived candidate in the probe's union domain has
    been exhausted.  A shared-slice limit or incomplete input is UNKNOWN.
    """
    chain = _main_chain_roles_from_process_graph()
    material_flows = tuple(flow for flow in process_graph().flows if flow.kind == "MATERIAL")
    predecessors = {
        role: tuple(flow.from_ref for flow in material_flows if flow.to_ref == role)
        for role in chain
    }
    successors = {
        role: tuple(flow.to_ref for flow in material_flows if flow.from_ref == role)
        for role in chain
    }
    process_axis = handoff.process_axis.value
    process_sign = 1 if handoff.process_direction == ProcessDirectionV1.POSITIVE else -1
    fixed_chain = tuple(role for role in chain if role in placed)
    unplaced_chain = tuple(role for role in chain if role not in placed)
    signature = _main_chain_partial_geometry_hash(handoff, bank_sign, placed)
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
            witness_shapes: dict[str, _Shape] = {}
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
            composition_faces = _domain_faces(handoff, bank_sign)

            def probe_funnel(role: str) -> dict[str, int]:
                return diagnostics.forward_probe_funnel.setdefault(
                    role,
                    {
                        "raw_anchor_count": 0,
                        "must_edge_compatible_count": 0,
                        "must_edge_rejected_count": 0,
                        "cr5_propagation_compatible_count": 0,
                        "propagation_rejected_count": 0,
                        "after_propagation_count": 0,
                        "candidate_expansion_count": 0,
                        "site_rejected_count": 0,
                        "obstacle_rejected_count": 0,
                        "overlap_rejected_count": 0,
                        "must_rejected_count": 0,
                        "coupled_interface_rejected_count": 0,
                        "partial_intent_rejected_after_propagation_count": 0,
                        "accepted_probe_partial_count": 0,
                        "full_hard_valid_count": 0,
                        "not_expanded_budget_stop_count": 0,
                        "free_space_classified_count": 0,
                        "free_space_rejected_count": 0,
                        "free_space_surviving_count": 0,
                    },
                )

            def increment_edges(edge_keys: Sequence[str], metric: str, amount: int = 1) -> None:
                for edge_key in edge_keys:
                    edge_metrics(edge_key)[metric] += amount

            def record_edge_outcome(edge_keys: Sequence[str], status: str, *, once: bool) -> None:
                if not edge_keys:
                    return
                outcome_metric = {
                    "PASS_SUCCESSOR_CAPACITY": "pass_count",
                    "PROVED_NO_SUCCESSOR_CAPACITY_IN_CURRENT_FINITE_DOMAIN": ("proved_none_count"),
                    "UNKNOWN_BUDGET_EXHAUSTED": "unknown_count",
                    "UNKNOWN_INCOMPLETE_DOMAIN": "unknown_count",
                }[status]
                if once:
                    increment_edges(edge_keys, outcome_metric)
                diagnostics.successor_capacity_decision_sequence.append(
                    (edge_keys[0], status, "EXISTING_MUST_ADJACENCY", "", 0)
                )

            def record_propagation(
                role: str,
                decision: _CompositionIntentProjectionDecisionV1,
                candidate: PlacedRectangleV1,
            ) -> None:
                diagnostics.composition_propagation_evaluation_count += 1
                metrics = probe_funnel(role)
                for rule in decision.evaluated_rules:
                    if rule == "LINEAR_RAW_CORE":
                        diagnostics.linear_raw_core_bound_evaluation_count += 1
                    elif rule == "LINEAR_CORE_FINISHED":
                        diagnostics.linear_core_finished_bound_evaluation_count += 1
                    elif rule.startswith("CENTRAL_"):
                        diagnostics.central_bound_evaluation_count += 1
                    elif rule == "SPINE_MONOTONIC":
                        diagnostics.spine_monotonic_bound_evaluation_count += 1
                if decision.status == "PROVABLY_INCOMPATIBLE":
                    diagnostics.composition_propagation_provable_rejection_count += 1
                    metrics["propagation_rejected_count"] += 1
                    for rule in decision.rejected_rules:
                        if rule == "LINEAR_RAW_CORE":
                            diagnostics.linear_raw_core_provable_rejection_count += 1
                        elif rule == "LINEAR_CORE_FINISHED":
                            diagnostics.linear_core_finished_provable_rejection_count += 1
                        elif rule.startswith("CENTRAL_"):
                            diagnostics.central_provable_rejection_count += 1
                        elif rule == "SPINE_MONOTONIC":
                            diagnostics.spine_monotonic_provable_rejection_count += 1
                else:
                    diagnostics.composition_propagation_rank_only_count += int(
                        bool(decision.evaluated_rules)
                    )
                    metrics["after_propagation_count"] += 1
                diagnostics.composition_propagation_sequence.append(
                    (role, _bounds(candidate), decision.status, decision.reason, decision.slack)
                )

            projection_decisions_by_role_shape: dict[
                tuple[str, tuple[int, int, int]],
                dict[tuple[int, int], _CompositionIntentProjectionDecisionV1],
            ] = {}
            successor_domain_identity_by_role_shape: dict[
                tuple[str, tuple[int, int, int]], str
            ] = {}
            propagation_rejection_count_by_role: Counter[str] = Counter()

            def edge_metrics(edge_key: str) -> dict[str, Any]:
                predecessor, successor = edge_key.split("->", 1)
                return diagnostics.successor_capacity_edge_diagnostics.setdefault(
                    edge_key,
                    {
                        "predecessor": predecessor,
                        "successor": successor,
                        "capacity_checks": 0,
                        "finite_candidates": 0,
                        "must_edge_compatible": 0,
                        "cr5_propagation_compatible": 0,
                        "site_valid": 0,
                        "obstacle_valid": 0,
                        "non_overlap_valid": 0,
                        "hard_valid": 0,
                        "pass_count": 0,
                        "proved_none_count": 0,
                        "unknown_count": 0,
                        "must_edge_rejected": 0,
                        "candidate_expansion_count": 0,
                        "not_expanded_budget_stop_count": 0,
                    },
                )

            def candidate_origins(
                role: str,
                shape: _Shape,
                capacity_edge_keys: tuple[str, ...] = (),
            ) -> tuple[tuple[int, int], ...]:
                origins: set[tuple[int, int]] = set()
                must_face_origins: set[tuple[int, int]] = set()
                shape_key = (shape.world_width_mm, shape.world_depth_mm, shape.rotation_deg)
                projection_decisions: dict[
                    tuple[int, int], _CompositionIntentProjectionDecisionV1
                ] = {}
                projection_axes = {process_axis}
                if role in composition_faces:
                    projection_axes.add(composition_faces[role][0])
                decision_cache: dict[tuple[int, ...], _CompositionIntentProjectionDecisionV1] = {}
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
                    must_face_origins.update(
                        _anchors_at_must_faces(
                            role, shape, probe_placed, neighbors, boundary, obstacles
                        )
                    )
                    origins.update(must_face_origins)

                # Propagate existing composition-intent necessary conditions
                # before sorting or expanding geometry. Only a proven conflict
                # is removed; all survivors still pass through the unchanged
                # physical checks and _partial_intent_possible below.
                metrics = probe_funnel(role)
                metrics["raw_anchor_count"] += len(origins)
                for edge_key in capacity_edge_keys:
                    edge_metrics(edge_key)["finite_candidates"] += len(origins)
                successor_domain = _feasible_successor_domain(
                    role,
                    shape,
                    tuple(origins),
                    probe_placed,
                    handoff,
                    bank_sign,
                )
                successor_domain_identity_by_role_shape[(role, shape_key)] = (
                    successor_domain.source_finite_domain_identity
                )
                must_rejected_count = (
                    successor_domain.raw_finite_origin_count
                    - successor_domain.must_edge_compatible_origin_count
                )
                metrics["must_edge_compatible_count"] += (
                    successor_domain.must_edge_compatible_origin_count
                )
                metrics["must_edge_rejected_count"] += must_rejected_count
                metrics["must_rejected_count"] += must_rejected_count
                for edge_key in capacity_edge_keys:
                    edge = edge_metrics(edge_key)
                    edge["must_edge_compatible"] += (
                        successor_domain.must_edge_compatible_origin_count
                    )
                    edge["must_edge_rejected"] += must_rejected_count
                compatible_origins: list[tuple[int, int]] = []
                for point in successor_domain.origins:
                    candidate = _rectangle(role, point[0], point[1], shape)
                    projection_key = tuple(
                        _center(candidate, axis) for axis in sorted(projection_axes)
                    )
                    decision = decision_cache.get(projection_key)
                    if decision is None:
                        trial = dict(probe_placed)
                        trial[role] = candidate
                        decision = _composition_intent_projection_decision(
                            handoff, trial, boundary, shapes, composition_faces
                        )
                        decision_cache[projection_key] = decision
                    projection_decisions[point] = decision
                    record_propagation(role, decision, candidate)
                    if decision.status == "PROVABLY_INCOMPATIBLE":
                        propagation_rejection_count_by_role[role] += 1
                        continue
                    compatible_origins.append(point)
                    metrics["cr5_propagation_compatible_count"] += 1
                    for edge_key in capacity_edge_keys:
                        edge_metrics(edge_key)["cr5_propagation_compatible"] += 1
                if capacity_edge_keys:
                    free_origins, free_profile = _exact_successor_free_space_domain(
                        role,
                        shape,
                        tuple(compatible_origins),
                        probe_placed,
                        boundary,
                        obstacles,
                        handoff,
                        bank_sign,
                    )
                    # Preserve every classification through a canonical row
                    # digest and complete blocker counters, without retaining
                    # repeated per-origin trees across the entire search.
                    # The historical seven/debt diagnostic runner retains
                    # unabridged rows separately; it is not a runtime seed.
                    recorded_profile = dict(free_profile)
                    recorded_profile["candidate_classification_rows_hash"] = (
                        _primitive_diagnostic_hash(recorded_profile.pop("candidates"))
                    )
                    diagnostics.successor_free_space_profiles.append(recorded_profile)
                    classified = free_profile["exclusive_counts"]
                    metrics["free_space_classified_count"] += len(compatible_origins)
                    metrics["free_space_surviving_count"] += len(free_origins)
                    metrics["free_space_rejected_count"] += len(compatible_origins) - len(
                        free_origins
                    )
                    for reason in ("SITE", "OBSTACLE", "OVERLAP"):
                        metrics[f"{reason.lower()}_rejected_count"] += classified.get(reason, 0)
                    for edge_key in capacity_edge_keys:
                        edge = edge_metrics(edge_key)
                        edge["site_valid"] += len(compatible_origins) - classified.get("SITE", 0)
                        edge["obstacle_valid"] += (
                            len(compatible_origins)
                            - classified.get("SITE", 0)
                            - classified.get("OBSTACLE", 0)
                        )
                        edge["non_overlap_valid"] += len(free_origins)
                    origins = set(free_origins)
                else:
                    origins = set(compatible_origins)

                axis, interval = _domain_interval(role, handoff, domains)
                boundary_bbox = (
                    min(point[0] for point in boundary),
                    min(point[1] for point in boundary),
                    max(point[0] for point in boundary),
                    max(point[1] for point in boundary),
                )
                obstacle_bboxes = tuple(
                    (
                        min(point[0] for point in obstacle),
                        min(point[1] for point in obstacle),
                        max(point[0] for point in obstacle),
                        max(point[1] for point in obstacle),
                    )
                    for obstacle in obstacles
                )
                occupied_bounds = tuple(_bounds(item) for item in probe_placed.values())

                def completion_order(
                    point: tuple[int, int],
                ) -> tuple[int, ...]:
                    candidate = _rectangle(role, point[0], point[1], shape)
                    trial = dict(probe_placed)
                    trial[role] = candidate
                    # Ordering only: keep every finite event anchor in the
                    # probe domain, but try primary-search-compatible intent
                    # states first so a positive witness can be replayed
                    # without consuming the shared slice on known-invalid
                    # group/band placements.
                    process_projection = process_sign * _center(candidate, process_axis)
                    projection_decision = projection_decisions.get(point)
                    assert projection_decision is not None
                    predecessor_positions = [
                        process_sign * _center(probe_placed[name], process_axis)
                        for name in predecessors[role]
                        if name in probe_placed
                    ]
                    successor_positions = [
                        process_sign * _center(probe_placed[name], process_axis)
                        for name in successors[role]
                        if name in probe_placed
                    ]
                    flow_violation = max(
                        [
                            *(position - process_projection for position in predecessor_positions),
                            *(process_projection - position for position in successor_positions),
                            0,
                        ]
                    )
                    projection = _center(candidate, axis)
                    interval_penalty = 0
                    if interval is not None:
                        low, high = interval
                        interval_penalty = (
                            0
                            if low <= projection <= high
                            else min(abs(projection - low), abs(projection - high))
                        )
                    candidate_bounds = _bounds(candidate)
                    boundary_bbox_penalty = int(
                        candidate_bounds[0] < boundary_bbox[0]
                        or candidate_bounds[1] < boundary_bbox[1]
                        or candidate_bounds[2] > boundary_bbox[2]
                        or candidate_bounds[3] > boundary_bbox[3]
                    )
                    # Ranking only: axis-aligned rectangle overlap is a cheap
                    # predictor of the unchanged physical predicates, while
                    # obstacle bounding-box overlap is deliberately
                    # conservative. Neither signal removes a candidate or
                    # substitutes for the normal site/obstacle/overlap checks.
                    placed_bbox_overlap_count = sum(
                        int(
                            candidate_bounds[0] < bounds[2]
                            and bounds[0] < candidate_bounds[2]
                            and candidate_bounds[1] < bounds[3]
                            and bounds[1] < candidate_bounds[3]
                        )
                        for bounds in occupied_bounds
                    )
                    obstacle_bbox_overlap_count = sum(
                        int(
                            candidate_bounds[0] < obstacle_bbox[2]
                            and obstacle_bbox[0] < candidate_bounds[2]
                            and candidate_bounds[1] < obstacle_bbox[3]
                            and obstacle_bbox[1] < candidate_bounds[3]
                        )
                        for obstacle_bbox in obstacle_bboxes
                    )
                    return (
                        int(point not in must_face_origins),
                        boundary_bbox_penalty,
                        placed_bbox_overlap_count,
                        obstacle_bbox_overlap_count,
                        int(projection_decision.status == "PROVABLY_INCOMPATIBLE"),
                        -projection_decision.slack,
                        flow_violation,
                        interval_penalty,
                        point[0],
                        point[1],
                    )

                projection_decisions_by_role_shape[(role, shape_key)] = projection_decisions
                return tuple(sorted(origins, key=completion_order))

            def visit_next() -> bool | None:
                nonlocal incomplete_proof, probe_budget_exhausted
                role = next((item for item in chain if item not in probe_placed), None)
                if role is None:
                    return True
                capacity_edge_keys = _successor_edge_keys(role, probe_placed)
                if capacity_edge_keys:
                    diagnostics.main_chain_successor_capacity_check_count += len(capacity_edge_keys)
                    increment_edges(capacity_edge_keys, "capacity_checks")
                if not shapes[role]:
                    incomplete_proof = True
                    record_edge_outcome(capacity_edge_keys, "UNKNOWN_INCOMPLETE_DOMAIN", once=True)
                    diagnostics.successor_capacity_unknown_other_count += len(capacity_edge_keys)
                    return None
                role_had_anchor = False
                role_capacity_outcome_recorded = False
                role_failure_counts: Counter[str] = Counter()
                if propagation_rejection_count_by_role[role]:
                    role_failure_counts["COMPOSITION_INTENT_PROPAGATION"] = (
                        propagation_rejection_count_by_role[role]
                    )
                if probe_funnel(role)["must_edge_rejected_count"]:
                    role_failure_counts["MUST_EDGE"] = probe_funnel(role)[
                        "must_edge_rejected_count"
                    ]
                physical_failures_before = {
                    reason: probe_funnel(role)[f"{reason.lower()}_rejected_count"]
                    for reason in ("SITE", "OBSTACLE", "OVERLAP")
                }
                shape_points = tuple(
                    (shape, candidate_origins(role, shape, capacity_edge_keys))
                    for shape in shapes[role]
                )
                for reason, before in physical_failures_before.items():
                    role_failure_counts[reason] += (
                        probe_funnel(role)[f"{reason.lower()}_rejected_count"] - before
                    )
                for shape_index, (shape, points) in enumerate(shape_points):
                    for point_index, (x, y) in enumerate(points):
                        metrics = probe_funnel(role)
                        candidate = _rectangle(role, x, y, shape)
                        shape_key = (
                            shape.world_width_mm,
                            shape.world_depth_mm,
                            shape.rotation_deg,
                        )
                        decision = projection_decisions_by_role_shape[(role, shape_key)][(x, y)]
                        if (
                            diagnostics.nodes >= diagnostics.node_limit
                            or diagnostics.forward_check_nodes - forward_nodes_before
                            >= forward_probe_slice_limit
                        ):
                            unexpanded_count = (
                                len(points)
                                - point_index
                                + sum(
                                    len(remaining_points)
                                    for _, remaining_points in shape_points[shape_index + 1 :]
                                )
                            )
                            metrics["not_expanded_budget_stop_count"] += unexpanded_count
                            increment_edges(
                                capacity_edge_keys,
                                "not_expanded_budget_stop_count",
                                unexpanded_count,
                            )
                            diagnostics.forward_probe_budget_stop_samples.append(
                                {
                                    "role": role,
                                    "bounds_mm": list(_bounds(candidate)),
                                    "projection_status": decision.status,
                                    "projection_reason": decision.reason,
                                    "placed_main_chain_bounds_mm": {
                                        item: list(_bounds(probe_placed[item]))
                                        for item in chain
                                        if item in probe_placed
                                    },
                                }
                            )
                            probe_budget_exhausted = True
                            if capacity_edge_keys and not role_capacity_outcome_recorded:
                                record_edge_outcome(
                                    capacity_edge_keys,
                                    "UNKNOWN_BUDGET_EXHAUSTED",
                                    once=True,
                                )
                                diagnostics.successor_capacity_unknown_budget_count += len(
                                    capacity_edge_keys
                                )
                                role_capacity_outcome_recorded = True
                            return None
                        diagnostics.nodes += 1
                        diagnostics.forward_check_nodes += 1
                        metrics["candidate_expansion_count"] += 1
                        increment_edges(capacity_edge_keys, "candidate_expansion_count")
                        if chain_hole:
                            diagnostics.forward_check_chain_hole_nodes += 1
                        else:
                            diagnostics.forward_check_regular_nodes += 1
                        rejected = _candidate_rejection(
                            candidate, probe_placed, boundary, obstacles
                        )
                        if rejected is not None:
                            role_failure_counts[rejected] += 1
                            metrics[f"{rejected.lower()}_rejected_count"] += 1
                            if rejected == "OBSTACLE":
                                increment_edges(capacity_edge_keys, "site_valid")
                            elif rejected == "OVERLAP":
                                increment_edges(capacity_edge_keys, "site_valid")
                                increment_edges(capacity_edge_keys, "obstacle_valid")
                            continue
                        # Capacity edges already classified these exact
                        # physical facts during finite-domain subtraction.
                        neighbors = tuple(
                            name for name in _must_neighbors(role) if name in probe_placed
                        )
                        if any(
                            not rectangles_share_positive_edge(candidate, probe_placed[neighbor])
                            for neighbor in neighbors
                        ):
                            role_failure_counts["MUST_EDGE"] += 1
                            metrics["must_rejected_count"] += 1
                            continue
                        probe_placed[role] = candidate
                        if not _partial_intent_possible(handoff, probe_placed, composition_faces):
                            role_failure_counts["COMPOSITION_INTENT"] += 1
                            metrics["partial_intent_rejected_after_propagation_count"] += 1
                            probe_placed.pop(role, None)
                            continue
                        if access_intent is not None and role == "shipping_channel":
                            office_preflight = _shipping_office_candidate_preflight_status(
                                candidate, shapes["office"], boundary
                            )
                            if (
                                office_preflight
                                == "PROVABLY_NO_SHARED_EDGE_CAPACITY_IN_SITE_BOUNDS"
                            ):
                                role_failure_counts["SHIPPING_OFFICE_INTERFACE"] += 1
                                metrics["coupled_interface_rejected_count"] += 1
                                probe_placed.pop(role, None)
                                continue
                        metrics["full_hard_valid_count"] += 1
                        increment_edges(capacity_edge_keys, "hard_valid")
                        increment_edges(capacity_edge_keys, "pass_count")
                        diagnostics.successor_capacity_pass_count += len(capacity_edge_keys)
                        if capacity_edge_keys:
                            role_capacity_outcome_recorded = True
                            witness_parent_geometry = dict(probe_placed)
                            witness_parent_geometry.pop(role, None)
                            parent_geometry_hash = _main_chain_partial_geometry_hash(
                                handoff, bank_sign, witness_parent_geometry
                            )
                            predecessor_roles = tuple(
                                edge_key.split("->", 1)[0] for edge_key in capacity_edge_keys
                            )
                            capacity_witness = _FeasibleSuccessorWitnessV1(
                                parent_partial_geometry_hash=parent_geometry_hash,
                                composition_identity=handoff.composition_identity,
                                composition_signature=handoff.composition_signature,
                                bank_sign=bank_sign,
                                predecessor_roles=predecessor_roles,
                                successor_role=role,
                                bounds_mm=_bounds(candidate),
                                shape=shape,
                                authoritative_shape_identity=(
                                    _shape_authority_identity(
                                        role, dimension_authorities[role], shape
                                    )
                                    if dimension_authorities is not None
                                    and role in dimension_authorities
                                    else canonical_hash({"role": role, "shape": asdict(shape)})
                                ),
                                source_finite_domain_identity=(
                                    successor_domain_identity_by_role_shape[(role, shape_key)]
                                ),
                            )
                            diagnostics.successor_capacity_witness_created_count += 1
                            if len(diagnostics.successor_capacity_witnesses) < 512:
                                diagnostics.successor_capacity_witnesses.append(
                                    {
                                        "parent_partial_geometry_hash": (
                                            capacity_witness.parent_partial_geometry_hash
                                        ),
                                        "composition_identity": (
                                            capacity_witness.composition_identity
                                        ),
                                        "composition_signature": (
                                            capacity_witness.composition_signature
                                        ),
                                        "bank_sign": capacity_witness.bank_sign,
                                        "predecessor_roles": list(
                                            capacity_witness.predecessor_roles
                                        ),
                                        "successor_role": capacity_witness.successor_role,
                                        "bounds_mm": list(capacity_witness.bounds_mm),
                                        "shape": asdict(capacity_witness.shape),
                                        "authoritative_shape_identity": (
                                            capacity_witness.authoritative_shape_identity
                                        ),
                                        "source_finite_domain_identity": (
                                            capacity_witness.source_finite_domain_identity
                                        ),
                                        "engineering_authority": False,
                                        "validation_authority": False,
                                        "forward_probe_candidate_revalidated": True,
                                    }
                                )
                            diagnostics.successor_capacity_decision_sequence.append(
                                (
                                    capacity_edge_keys[0],
                                    "PASS_SUCCESSOR_CAPACITY",
                                    "EXACT_MUST_AND_EXISTING_HARD_PREDICATES",
                                    capacity_witness.source_finite_domain_identity,
                                    diagnostics.forward_check_nodes - forward_nodes_before,
                                )
                            )
                        role_had_anchor = True
                        metrics["accepted_probe_partial_count"] += 1
                        if len(diagnostics.forward_probe_candidate_samples) < 256:
                            diagnostics.forward_probe_candidate_samples.append(
                                {
                                    "role": role,
                                    "bounds_mm": list(_bounds(candidate)),
                                    "projection_slack_mm": decision.slack,
                                    "projection_rules": list(decision.evaluated_rules),
                                    "partial_intent_passed": True,
                                }
                            )
                        witness_order.append(role)
                        witness_bounds[role] = _bounds(candidate)
                        witness_shapes[role] = shape
                        child = visit_next()
                        if child is True:
                            return True
                        probe_placed.pop(role, None)
                        witness_order.pop()
                        witness_bounds.pop(role, None)
                        witness_shapes.pop(role, None)
                        if child is None and (probe_budget_exhausted or incomplete_proof):
                            return None
                failure_counts_by_role[role].update(role_failure_counts)
                if capacity_edge_keys and not role_capacity_outcome_recorded:
                    if probe_budget_exhausted:
                        outcome = "UNKNOWN_BUDGET_EXHAUSTED"
                        diagnostics.successor_capacity_unknown_budget_count += len(
                            capacity_edge_keys
                        )
                    elif incomplete_proof:
                        outcome = "UNKNOWN_INCOMPLETE_DOMAIN"
                        diagnostics.successor_capacity_unknown_other_count += len(
                            capacity_edge_keys
                        )
                    else:
                        outcome = "PROVED_NO_SUCCESSOR_CAPACITY_IN_CURRENT_FINITE_DOMAIN"
                        diagnostics.successor_capacity_proved_none_count += len(capacity_edge_keys)
                    record_edge_outcome(capacity_edge_keys, outcome, once=True)
                elif capacity_edge_keys and not role_had_anchor:
                    # A positive local successor was seen, but every suffix
                    # failed. Preserve PASS for this edge: only the deeper
                    # material-chain edge lacked capacity.
                    pass
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
                    witness_shape_specs=tuple(
                        (role, witness_shapes[role]) for role in witness_order
                    ),
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
                    "witness_shape_specs": {
                        role: asdict(shape) for role, shape in result.witness_shape_specs
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


def _shape_authority_identity(role: str, authority: Mapping[str, Any], shape: _Shape) -> str:
    return canonical_hash(
        {
            "zone_role": role,
            "dimension_authority": dict(authority),
            "authorized_shape": asdict(shape),
        }
    )


def _completion_witness_from_probe(
    probe: _MainChainForwardCheckResultV1,
    handoff: StructuralCompositionPlacementHandoffV1,
    bank_sign: int,
    dimension_authorities: Mapping[str, Mapping[str, Any]],
) -> _MainChainCompletionWitnessV1 | None:
    if probe.status != "PASS_TO_SEARCH" or not probe.witness_role_order:
        return None
    bounds_by_role = dict(probe.witness_zone_bounds_mm)
    shape_by_role = dict(probe.witness_shape_specs)
    if set(bounds_by_role) != set(probe.witness_role_order) or set(shape_by_role) != set(
        probe.witness_role_order
    ):
        return None
    geometry = tuple(
        (
            role,
            bounds_by_role[role],
            shape_by_role[role],
            _shape_authority_identity(role, dimension_authorities[role], shape_by_role[role]),
        )
        for role in probe.witness_role_order
    )
    return _MainChainCompletionWitnessV1(
        source_partial_geometry_hash=probe.partial_geometry_hash,
        composition_identity=handoff.composition_identity,
        composition_signature=handoff.composition_signature,
        bank_sign=bank_sign,
        main_chain_source=MAIN_CHAIN_SOURCE,
        fixed_main_chain_roles=probe.fixed_main_chain_roles,
        unplaced_main_chain_roles=probe.unplaced_main_chain_roles,
        ordered_witness_roles=probe.witness_role_order,
        witness_geometry=geometry,
        source_forward_check_status=probe.status,
    )


def _completion_witness_incompatibility(
    witness: _MainChainCompletionWitnessV1,
    handoff: StructuralCompositionPlacementHandoffV1,
    bank_sign: int,
    shapes: Mapping[str, tuple[_Shape, ...]],
    authority_shapes: Mapping[str, tuple[_Shape, ...]],
    dimension_authorities: Mapping[str, Mapping[str, Any]],
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    faces: Mapping[str, tuple[str, int]],
) -> str | None:
    """Revalidate an advisory suffix against the current deterministic state."""
    if (
        witness.source_forward_check_status != "PASS_TO_SEARCH"
        or witness.engineering_authority
        or witness.validation_authority
        or witness.main_chain_source != MAIN_CHAIN_SOURCE
        or witness.composition_identity != handoff.composition_identity
        or witness.composition_signature != handoff.composition_signature
        or witness.bank_sign != bank_sign
    ):
        return "OTHER_HARD_CHECK"
    trial = dict(placed)
    for role, bounds, shape, shape_identity in witness.witness_geometry:
        if role in trial or shape not in authority_shapes.get(role, ()):
            return "OTHER_HARD_CHECK"
        if shape not in shapes.get(role, ()):
            return "OTHER_HARD_CHECK"
        if shape_identity != _shape_authority_identity(role, dimension_authorities[role], shape):
            return "OTHER_HARD_CHECK"
        rectangle = _rectangle(role, bounds[0], bounds[1], shape)
        if _bounds(rectangle) != bounds:
            return "OTHER_HARD_CHECK"
        rejected = _candidate_rejection(rectangle, trial, boundary, obstacles)
        if rejected is not None:
            return rejected
        neighbors = tuple(name for name in _must_neighbors(role) if name in trial)
        if any(not rectangles_share_positive_edge(rectangle, trial[name]) for name in neighbors):
            return "MUST_EDGE"
        trial[role] = rectangle
        if not _partial_intent_possible(handoff, trial, faces):
            return "OTHER_HARD_CHECK"
    return None


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

    def record_witness_rejection(
        source: str,
        role: str,
        reason: str,
        candidate: PlacedRectangleV1,
        witness: _MainChainCompletionWitnessV1 | None,
        current_placed: Mapping[str, PlacedRectangleV1],
    ) -> None:
        if source == "SUCCESSOR_WITNESS":
            diagnostics.successor_capacity_witness_invalidated_count += 1
            parent_geometry = dict(current_placed)
            parent_geometry.pop(role, None)
            parent_hash = _main_chain_partial_geometry_hash(handoff, bank_sign, parent_geometry)
            same_parent_mismatch = any(
                item.get("parent_partial_geometry_hash") == parent_hash
                and item.get("successor_role") == role
                and item.get("bounds_mm") == list(_bounds(candidate))
                for item in diagnostics.successor_capacity_witnesses
            )
            diagnostics.successor_capacity_same_parent_replay_mismatch |= same_parent_mismatch
            record_witness_event(
                "SUCCESSOR_CAPACITY_WITNESS_INVALIDATED",
                role=role,
                reason=reason,
                source_partial_geometry_hash=parent_hash,
                candidate_bounds_mm=list(_bounds(candidate)),
                same_parent_replay_mismatch=same_parent_mismatch,
            )
            return
        if source != "WITNESS" or witness is None:
            return
        diagnostics.witness_reuse_rejected_count += 1
        if any(
            item.get("successor_role") == role and item.get("bounds_mm") == list(_bounds(candidate))
            for item in diagnostics.successor_capacity_witnesses
        ):
            diagnostics.successor_capacity_witness_invalidated_count += 1
        parent_geometry = dict(current_placed)
        parent_geometry.pop(role, None)
        mismatch = _main_chain_partial_geometry_hash(handoff, bank_sign, parent_geometry) == (
            witness.source_partial_geometry_hash
        )
        record_witness_event(
            "REUSE_REJECTED",
            role=role,
            reason=reason,
            same_parent_replay_mismatch=mismatch,
            candidate_bounds_mm=list(_bounds(candidate)),
        )

    def record_witness_event(event: str, **details: Any) -> None:
        diagnostics.witness_events.append({"event": event, **details})

    def invalidate_witness(
        witness: _MainChainCompletionWitnessV1,
        role: str,
        reason: str,
        current_placed: Mapping[str, PlacedRectangleV1],
    ) -> None:
        diagnostics.witness_invalidated_by_new_geometry_count += 1
        counter_by_reason = {
            "SITE": "witness_invalidated_by_site_count",
            "OBSTACLE": "witness_invalidated_by_obstacle_count",
            "OVERLAP": "witness_invalidated_by_overlap_count",
            "MUST_EDGE": "witness_invalidated_by_must_edge_count",
        }
        counter_name = counter_by_reason.get(reason)
        if counter_name is not None:
            setattr(diagnostics, counter_name, getattr(diagnostics, counter_name) + 1)
        elif reason != "NEW_GEOMETRY":
            diagnostics.witness_invalidated_by_other_hard_check_count += 1
        record_witness_event(
            "INVALIDATED",
            role=role,
            reason=reason,
            source_partial_geometry_hash=witness.source_partial_geometry_hash,
            current_partial_geometry_hash=_main_chain_partial_geometry_hash(
                handoff, bank_sign, current_placed
            ),
        )

    def recurse(
        index: int,
        placed: dict[str, PlacedRectangleV1],
        active_witness: _MainChainCompletionWitnessV1 | None = None,
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

        role_shapes = ordered_shapes[code]
        witness_geometry = active_witness.geometry_for(code) if active_witness else None
        parent_signature = _main_chain_partial_geometry_hash(handoff, bank_sign, placed)
        successor_witness_entry = next(
            (
                item
                for item in diagnostics.successor_capacity_witnesses
                if item.get("parent_partial_geometry_hash") == parent_signature
                and item.get("successor_role") == code
                and item.get("composition_identity") == handoff.composition_identity
                and item.get("composition_signature") == handoff.composition_signature
                and item.get("bank_sign") == bank_sign
                and item.get("engineering_authority") is False
                and item.get("validation_authority") is False
            ),
            None,
        )
        if witness_geometry is None and successor_witness_entry is not None:
            raw_bounds = successor_witness_entry.get("bounds_mm")
            raw_shape = successor_witness_entry.get("shape")
            if (
                isinstance(raw_bounds, list)
                and len(raw_bounds) == 4
                and isinstance(raw_shape, Mapping)
            ):
                candidate_shape = _Shape(
                    int(raw_shape["width_mm"]),
                    int(raw_shape["depth_mm"]),
                    int(raw_shape["rotation_deg"]),
                )
                expected_shape_identity = _shape_authority_identity(
                    code, dimension_authorities[code], candidate_shape
                )
                if (
                    candidate_shape in role_shapes
                    and successor_witness_entry.get("authoritative_shape_identity")
                    == expected_shape_identity
                ):
                    bounds = (
                        int(raw_bounds[0]),
                        int(raw_bounds[1]),
                        int(raw_bounds[2]),
                        int(raw_bounds[3]),
                    )
                    witness_geometry = (bounds, candidate_shape, "SUCCESSOR_CAPACITY")
        witness_shape = witness_geometry[1] if witness_geometry else None
        witness_bounds = witness_geometry[0] if witness_geometry else None
        witness_origin = (witness_bounds[0], witness_bounds[1]) if witness_bounds else None
        if witness_shape in role_shapes:
            role_shapes = (witness_shape,) + tuple(
                shape for shape in role_shapes if shape != witness_shape
            )

        def ordered_points(
            points: Sequence[tuple[int, int]], shape: _Shape
        ) -> tuple[tuple[int, int], ...]:
            def key(
                point: tuple[int, int],
            ) -> tuple[int, int, int, int, int, int, int, int, int, int]:
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
                witness_compatibility_penalty = 0
                if active_witness is not None and code not in {
                    item[0] for item in active_witness.witness_geometry
                }:
                    hypothetical = dict(placed)
                    hypothetical[code] = _rectangle(code, point[0], point[1], shape)
                    witness_compatibility_penalty = int(
                        _completion_witness_incompatibility(
                            active_witness,
                            handoff,
                            bank_sign,
                            shapes,
                            authority_shapes,
                            dimension_authorities,
                            hypothetical,
                            boundary,
                            obstacles,
                            faces,
                        )
                        is not None
                    )
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
                    witness_compatibility_penalty,
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
        witness_source = (
            "WITNESS"
            if active_witness is not None and active_witness.geometry_for(code) is not None
            else "SUCCESSOR_WITNESS"
            if successor_witness_entry is not None and witness_geometry is not None
            else None
        )
        sources = (
            (witness_source, "DOMAIN", "GENERIC")
            if witness_source is not None
            else ("DOMAIN", "GENERIC")
        )
        for source in sources:
            if source == "GENERIC" and diagnostics.generic_nodes >= max(1, node_limit // 10):
                break
            if source in {"WITNESS", "SUCCESSOR_WITNESS"}:
                assert witness_shape is not None
                source_shapes: tuple[_Shape, ...] = (witness_shape,)
            else:
                source_shapes = role_shapes
            for shape in source_shapes:
                diagnostics.funnel[code]["shape_variant_attempt_count"] += 1
                origins: Sequence[tuple[int, int]]
                if source in {"WITNESS", "SUCCESSOR_WITNESS"}:
                    assert witness_origin is not None
                    origins = (witness_origin,)
                elif source == "DOMAIN":
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
                    if witness_origin is not None and shape == witness_shape:
                        origins = tuple(point for point in origins if point != witness_origin)
                        domain_origins_by_shape[shape].discard(witness_origin)
                else:
                    if diagnostics.generic_nodes >= max(1, node_limit // 10):
                        break
                    origins = _generic_fallback_anchors(code, shape, placed, boundary, obstacles)
                    origins = tuple(
                        point
                        for point in origins
                        if point not in domain_origins_by_shape.get(shape, set())
                    )
                    if witness_origin is not None and shape == witness_shape:
                        origins = tuple(point for point in origins if point != witness_origin)
                    diagnostics.generic_anchor_count[code] += len(origins)
                    diagnostics.funnel[code]["generic_fallback_anchor_count"] += len(origins)
                if source not in {"WITNESS", "SUCCESSOR_WITNESS"} and neighbors and origins:
                    finite_domain = _feasible_successor_domain(
                        code, shape, origins, placed, handoff, bank_sign
                    )
                    diagnostics.funnel[code]["must_edge_rejection_count"] += (
                        finite_domain.raw_finite_origin_count
                        - finite_domain.must_edge_compatible_origin_count
                    )
                    origins = finite_domain.origins
                points = (
                    origins
                    if source in {"WITNESS", "SUCCESSOR_WITNESS"}
                    else ordered_points(origins, shape)
                )
                for x, y in points:
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
                    witness_candidate = source in {"WITNESS", "SUCCESSOR_WITNESS"}
                    if witness_candidate:
                        if source == "WITNESS":
                            diagnostics.witness_reuse_attempt_count += 1
                        else:
                            diagnostics.successor_capacity_witness_reuse_attempt_count += 1
                        record_witness_event(
                            (
                                "REUSE_ATTEMPTED"
                                if source == "WITNESS"
                                else "SUCCESSOR_CAPACITY_WITNESS_REUSE_ATTEMPTED"
                            ),
                            role=code,
                            bounds_mm=list(witness_bounds or ()),
                            source_partial_geometry_hash=(
                                active_witness.source_partial_geometry_hash
                                if active_witness is not None
                                else parent_signature
                            ),
                        )
                    if source == "GENERIC":
                        diagnostics.generic_nodes += 1
                        diagnostics.generic_nodes_by_role[code] += 1
                    candidate = _rectangle(code, x, y, shape)
                    rejected = _candidate_rejection(candidate, placed, boundary, obstacles)
                    if rejected is not None:
                        count_candidate_failure(code, rejected)
                        record_witness_rejection(
                            source, code, rejected, candidate, active_witness, placed
                        )
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
                        record_witness_rejection(
                            source,
                            code,
                            "PACKAGING_STRAIGHT_INTERFACE",
                            candidate,
                            active_witness,
                            placed,
                        )
                        save_witness(placed, code)
                        continue
                    if neighbors and any(
                        not rectangles_share_positive_edge(candidate, placed[neighbor])
                        for neighbor in neighbors
                    ):
                        diagnostics.funnel[code]["must_edge_rejection_count"] += 1
                        diagnostics.failure_taxonomy = f"{code.upper()}_MUST_EDGE_REJECTION"
                        record_witness_rejection(
                            source, code, "MUST_EDGE", candidate, active_witness, placed
                        )
                        save_witness(placed, code)
                        continue
                    sorting = placed.get("sorting_packaging_room")
                    if sorting is not None and not _side_ok(code, candidate, sorting, faces):
                        diagnostics.funnel[code]["domain_side_rejection_count"] += 1
                        diagnostics.failure_taxonomy = f"{code.upper()}_DOMAIN_SIDE_REJECTION"
                        record_witness_rejection(
                            source, code, "COMPOSITION_SIDE", candidate, active_witness, placed
                        )
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
                            record_witness_rejection(
                                source,
                                code,
                                "SHIPPING_OFFICE_INTERFACE",
                                candidate,
                                active_witness,
                                placed,
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
                            record_witness_rejection(
                                source, code, "TRUCK_PREFLIGHT", candidate, active_witness, placed
                            )
                            save_witness(placed, code)
                            continue
                    placed[code] = candidate
                    if not _partial_intent_possible(handoff, placed, faces):
                        diagnostics.funnel[code]["composition_intent_rejection_count"] += 1
                        diagnostics.failure_taxonomy = (
                            f"{code.upper()}_PARTIAL_COMPOSITION_INTENT_REJECTION"
                        )
                        record_witness_rejection(
                            source, code, "COMPOSITION_INTENT", candidate, active_witness, placed
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
                            record_witness_rejection(
                                source,
                                code,
                                "PACKAGING_CAPACITY",
                                candidate,
                                active_witness,
                                placed,
                            )
                            save_witness(placed, "packaging_material_storage")
                            placed.pop(code, None)
                            continue
                    child_witness = active_witness
                    witness_invalidated = False
                    if active_witness is not None:
                        inherited_entry = active_witness.geometry_for(code)
                        if inherited_entry is not None:
                            expected_bounds, expected_shape, _ = inherited_entry
                            selected_shape = _Shape(
                                _mm(candidate.width_m),
                                _mm(candidate.depth_m),
                                candidate.rotation_deg,
                            )
                            if (
                                _bounds(candidate) == expected_bounds
                                and selected_shape == expected_shape
                            ):
                                child_witness = active_witness.without_role(code)
                                reason = (
                                    _completion_witness_incompatibility(
                                        child_witness,
                                        handoff,
                                        bank_sign,
                                        shapes,
                                        authority_shapes,
                                        dimension_authorities,
                                        placed,
                                        boundary,
                                        obstacles,
                                        faces,
                                    )
                                    if child_witness is not None
                                    else None
                                )
                            else:
                                child_witness = None
                                reason = "NEW_GEOMETRY"
                        else:
                            reason = _completion_witness_incompatibility(
                                active_witness,
                                handoff,
                                bank_sign,
                                shapes,
                                authority_shapes,
                                dimension_authorities,
                                placed,
                                boundary,
                                obstacles,
                                faces,
                            )
                        if reason is not None:
                            invalidate_witness(active_witness, code, reason, placed)
                            child_witness = None
                            witness_invalidated = True
                        elif child_witness is not None:
                            diagnostics.witness_inheritance_count += 1
                            record_witness_event(
                                "INHERITED",
                                role=code,
                                remaining_roles=list(child_witness.ordered_witness_roles),
                                source_partial_geometry_hash=(
                                    child_witness.source_partial_geometry_hash
                                ),
                                current_partial_geometry_hash=(
                                    _main_chain_partial_geometry_hash(handoff, bank_sign, placed)
                                ),
                            )
                    if source == "SUCCESSOR_WITNESS" and not witness_invalidated:
                        diagnostics.successor_capacity_witness_reused_count += 1
                        record_witness_event(
                            "SUCCESSOR_CAPACITY_WITNESS_REUSED",
                            role=code,
                            parent_partial_geometry_hash=parent_signature,
                            bounds_mm=list(_bounds(candidate)),
                            source_finite_domain_identity=successor_witness_entry.get(
                                "source_finite_domain_identity"
                            )
                            if successor_witness_entry is not None
                            else None,
                        )
                    if source == "WITNESS" and witness_candidate and not witness_invalidated:
                        diagnostics.witness_reuse_accepted_count += 1
                        parent_placed = dict(placed)
                        parent_placed.pop(code, None)
                        parent_signature = _main_chain_partial_geometry_hash(
                            handoff, bank_sign, parent_placed
                        )
                        matching_capacity_witnesses = [
                            item
                            for item in diagnostics.successor_capacity_witnesses
                            if item.get("parent_partial_geometry_hash") == parent_signature
                            and item.get("successor_role") == code
                            and item.get("bounds_mm") == list(_bounds(candidate))
                        ]
                        if matching_capacity_witnesses:
                            diagnostics.successor_capacity_witness_reused_count += 1
                            record_witness_event(
                                "SUCCESSOR_CAPACITY_WITNESS_REUSED",
                                role=code,
                                parent_partial_geometry_hash=parent_signature,
                                bounds_mm=list(_bounds(candidate)),
                                source_finite_domain_identity=matching_capacity_witnesses[0].get(
                                    "source_finite_domain_identity"
                                ),
                            )
                        record_witness_event(
                            "REUSE_ACCEPTED",
                            role=code,
                            candidate_bounds_mm=list(_bounds(candidate)),
                            remaining_roles=(
                                list(child_witness.ordered_witness_roles)
                                if child_witness is not None
                                else []
                            ),
                        )
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
                    forward_check_triggered = (
                        access_intent is not None
                        and remaining_main_chain_role_count > 0
                        and (
                            branch_capacity_trigger
                            or shipping_capacity_trigger
                            or main_chain_hole_trigger
                        )
                    )
                    if forward_check_triggered and child_witness is not None:
                        diagnostics.forward_check_skipped_due_to_valid_witness_count += 1
                        record_witness_event(
                            "REDUNDANT_FORWARD_CHECK_SKIPPED",
                            trigger_role=code,
                            witness_roles=list(child_witness.ordered_witness_roles),
                        )
                    elif forward_check_triggered:
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
                            dimension_authorities=dimension_authorities,
                        )
                        child_witness = _completion_witness_from_probe(
                            probe, handoff, bank_sign, dimension_authorities
                        )
                        if child_witness is not None:
                            diagnostics.witness_created_count += 1
                            record_witness_event(
                                "CREATED",
                                trigger_role=code,
                                source_partial_geometry_hash=(
                                    child_witness.source_partial_geometry_hash
                                ),
                                witness_roles=list(child_witness.ordered_witness_roles),
                                witness_geometry={
                                    role: {
                                        "bounds_mm": list(bounds),
                                        "shape": asdict(shape),
                                        "shape_authority_identity": shape_identity,
                                    }
                                    for role, bounds, shape, shape_identity in (
                                        child_witness.witness_geometry
                                    )
                                },
                                engineering_authority=False,
                                validation_authority=False,
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
                    solution = recurse(index + 1, placed, child_witness)
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
                forward_check_skipped_due_to_valid_witness_count=(
                    diagnostics.forward_check_skipped_due_to_valid_witness_count
                ),
                forward_check_exact_cache_hit_count=diagnostics.forward_check_cache_hit_count,
                witness_created_count=diagnostics.witness_created_count,
                witness_reuse_attempt_count=diagnostics.witness_reuse_attempt_count,
                witness_reuse_accepted_count=diagnostics.witness_reuse_accepted_count,
                witness_reuse_rejected_count=diagnostics.witness_reuse_rejected_count,
                witness_inheritance_count=diagnostics.witness_inheritance_count,
                witness_invalidated_by_new_geometry_count=(
                    diagnostics.witness_invalidated_by_new_geometry_count
                ),
                witness_invalidated_by_site_count=diagnostics.witness_invalidated_by_site_count,
                witness_invalidated_by_obstacle_count=(
                    diagnostics.witness_invalidated_by_obstacle_count
                ),
                witness_invalidated_by_overlap_count=(
                    diagnostics.witness_invalidated_by_overlap_count
                ),
                witness_invalidated_by_must_edge_count=(
                    diagnostics.witness_invalidated_by_must_edge_count
                ),
                witness_invalidated_by_other_hard_check_count=(
                    diagnostics.witness_invalidated_by_other_hard_check_count
                ),
                witness_sequence_hash=canonical_hash(
                    [dict(item) for item in diagnostics.witness_events]
                ),
                witness_events=tuple(diagnostics.witness_events),
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
                composition_propagation_evaluation_count=(
                    diagnostics.composition_propagation_evaluation_count
                ),
                composition_propagation_provable_rejection_count=(
                    diagnostics.composition_propagation_provable_rejection_count
                ),
                composition_propagation_rank_only_count=(
                    diagnostics.composition_propagation_rank_only_count
                ),
                linear_raw_core_bound_evaluation_count=(
                    diagnostics.linear_raw_core_bound_evaluation_count
                ),
                linear_raw_core_provable_rejection_count=(
                    diagnostics.linear_raw_core_provable_rejection_count
                ),
                linear_core_finished_bound_evaluation_count=(
                    diagnostics.linear_core_finished_bound_evaluation_count
                ),
                linear_core_finished_provable_rejection_count=(
                    diagnostics.linear_core_finished_provable_rejection_count
                ),
                central_bound_evaluation_count=diagnostics.central_bound_evaluation_count,
                central_provable_rejection_count=diagnostics.central_provable_rejection_count,
                spine_monotonic_bound_evaluation_count=(
                    diagnostics.spine_monotonic_bound_evaluation_count
                ),
                spine_monotonic_provable_rejection_count=(
                    diagnostics.spine_monotonic_provable_rejection_count
                ),
                composition_propagation_sequence_hash=_primitive_diagnostic_hash(
                    diagnostics.composition_propagation_sequence
                ),
                forward_probe_funnel_by_role=tuple(
                    (
                        role,
                        tuple(sorted(metrics.items())),
                    )
                    for role, metrics in sorted(diagnostics.forward_probe_funnel.items())
                ),
                forward_probe_candidate_samples=tuple(diagnostics.forward_probe_candidate_samples),
                forward_probe_budget_stop_samples=tuple(
                    diagnostics.forward_probe_budget_stop_samples
                ),
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
                successor_capacity_diagnostics={
                    "engineering_authority": SUCCESSOR_CAPACITY_ENGINEERING_AUTHORITY,
                    "validation_authority": SUCCESSOR_CAPACITY_VALIDATION_AUTHORITY,
                    "search_optimization_only": True,
                    "main_chain_source": MAIN_CHAIN_SOURCE,
                    "must_chain_source": "EXISTING_PROCESS_GRAPH_MUST_ADJACENCIES",
                    "must_edge_early_filter_source": "EXISTING_MUST_ADJACENCY",
                    "successor_domain_source": SUCCESSOR_DOMAIN_SOURCE,
                    "successor_domain_is_primary_search_equivalent_or_superset": True,
                    "existing_final_must_predicate_preserved": True,
                    "multi_placed_must_neighbor_edge_filter_implemented": True,
                    "same_parent_successor_capacity_result_reuse_allowed": True,
                    "changed_parent_requires_revalidation": True,
                    "unknown_can_prune": False,
                    "check_count": diagnostics.main_chain_successor_capacity_check_count,
                    "pass_count": diagnostics.successor_capacity_pass_count,
                    "proved_none_count": diagnostics.successor_capacity_proved_none_count,
                    "unknown_budget_count": diagnostics.successor_capacity_unknown_budget_count,
                    "unknown_other_count": diagnostics.successor_capacity_unknown_other_count,
                    "witness_created_count": diagnostics.successor_capacity_witness_created_count,
                    "witness_reuse_attempt_count": (
                        diagnostics.successor_capacity_witness_reuse_attempt_count
                    ),
                    "witness_reused_count": diagnostics.successor_capacity_witness_reused_count,
                    "witness_invalidated_count": (
                        diagnostics.successor_capacity_witness_invalidated_count
                    ),
                    "same_parent_replay_mismatch": (
                        diagnostics.successor_capacity_same_parent_replay_mismatch
                    ),
                    "edge_capacity": {
                        key: dict(value)
                        for key, value in sorted(
                            diagnostics.successor_capacity_edge_diagnostics.items()
                        )
                    },
                    "witnesses": [dict(item) for item in diagnostics.successor_capacity_witnesses],
                    "exact_successor_free_space": {
                        "engineering_authority": False,
                        "validation_authority": False,
                        "domain_classification_is_recursive_expansion": False,
                        "recursive_survivor_evaluation_charged_to_shared_budget": True,
                        "classification_count": sum(
                            int(item["classified_count"])
                            for item in diagnostics.successor_free_space_profiles
                        ),
                        "unclassified_count": 0,
                        "profiles": [
                            dict(item) for item in diagnostics.successor_free_space_profiles
                        ],
                        "sequence_hash": _primitive_diagnostic_hash(
                            diagnostics.successor_free_space_profiles
                        ),
                    },
                    "decision_sequence_hash": canonical_hash(
                        [list(item) for item in diagnostics.successor_capacity_decision_sequence]
                    ),
                    "decision_sequence": [
                        list(item) for item in diagnostics.successor_capacity_decision_sequence
                    ],
                },
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
                    candidate_provenance.extend(
                        (
                            (
                                "witness_guidance_used",
                                str(diagnostics.witness_reuse_accepted_count > 0).lower(),
                            ),
                            (
                                "witness_guided_roles",
                                ",".join(
                                    str(event.get("role"))
                                    for event in diagnostics.witness_events
                                    if event.get("event") == "REUSE_ACCEPTED"
                                ),
                            ),
                        )
                    )
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
