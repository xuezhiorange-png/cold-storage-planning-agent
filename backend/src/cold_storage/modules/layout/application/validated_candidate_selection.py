"""Select a P2C placement only after P2D validation.

P2C owns deterministic placement candidate generation and its frozen
lexicographic objective. P2D owns final route, truck, access and layout
validation. This application boundary composes those responsibilities: every
complete P2C candidate is passed through P2D, and the highest-ranked P2C
candidate among the P2D-full-pass candidates is selected. The structured
Tool 7 path may also supply the same truck authority to P2C for a necessary
condition check before tail search; that check never replaces final P2D.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any, cast

from cold_storage.modules.layout.application.access_routing import (
    route_site_placement,
)
from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.application.placement import (
    enumerate_placement_candidates,
)
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.domain.access_routing import validate_truck_maneuver_chain
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.layout.domain.objective_profile import ObjectiveProfileV1
from cold_storage.modules.layout.domain.placement import (
    LEGACY_COMPAT_PHASE,
    MIN_CONSTRUCTIVE_SKELETON_NODE_ALLOWANCE,
    PLACEMENT_SEARCH_QUANTUM_NODES,
    STRUCTURED_PHASE,
    compare_placement_candidate_business_objectives,
    placement_candidate_canonical_tiebreak_key,
)
from cold_storage.modules.layout.domain.structural_composition import (
    CENTRAL_PROCESS_HUB,
    MAIN_PROCESS_ZONE_CODES,
    OFFSET_LINEAR_BAND,
    STRAIGHT_LINEAR_BAND,
    StructuralCompositionFamilyV1,
    StructuralTopologyLaneV1,
    composition_family_candidates,
    select_structural_composition_family,
    structural_topology_lanes,
)
from cold_storage.modules.layout.domain.structural_quality import (
    StructuralQualityFactsV1,
    build_structural_quality_facts,
    structural_candidate_is_better,
)
from cold_storage.modules.layout.domain.structured_building import BASE_LAYOUT_FAMILIES
from cold_storage.modules.layout.domain.truck_maneuver import (
    BoundTruckManeuverProjectInputV1,
)

IDENTITY = "p2-validated-candidate-selection-application@1.0.0"
RESULT_IDENTITY = "p2_validated_candidate_selection@1.0.0"
SCHEMA_VERSION = "1.0.0"
P2C_CANDIDATE_SELECTION_BASIS = "P1A_STRUCTURAL_QUALITY_THEN_P2B2_AMONG_P2D_FULL_PASS_CANDIDATES"


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


@dataclass(frozen=True, init=False)
class ValidatedPlacementSelectionResultV1:
    """Immutable evidence for the P2C-to-P2D candidate-selection decision."""

    payload_json: str
    _internal_evaluation_json: str = dataclass_field(repr=False, compare=False)
    _content_hash: str = dataclass_field(init=False, repr=False, compare=False)

    def __init__(
        self,
        payload: Mapping[str, Any],
        internal_evaluation: Mapping[str, Any] | None = None,
    ) -> None:
        content = dict(payload)
        content.pop("canonical_result_hash", None)
        object.__setattr__(self, "payload_json", canonical_json(content))
        object.__setattr__(
            self,
            "_internal_evaluation_json",
            canonical_json(dict(internal_evaluation or {})),
        )
        object.__setattr__(self, "_content_hash", canonical_hash(content))

    def to_dict(self) -> dict[str, Any]:
        value = cast(dict[str, Any], json.loads(self.payload_json))
        value["canonical_result_hash"] = self._content_hash
        return value

    def canonical_json(self) -> str:
        return self.payload_json

    @property
    def canonical_result_hash(self) -> str:
        return self._content_hash

    @property
    def selected_layout(self) -> dict[str, Any] | None:
        selected = self.to_dict().get("selected_layout")
        return dict(selected) if isinstance(selected, Mapping) else None

    @property
    def internal_evaluation(self) -> dict[str, Any]:
        """P1A selector evidence, deliberately excluded from public serialization."""
        value = cast(dict[str, Any], json.loads(self._internal_evaluation_json))
        return value


def _p2d_trace_row(
    candidate_index: int,
    candidate_body: Mapping[str, Any],
    *,
    p2d_body: Mapping[str, Any],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "candidate_index": candidate_index,
        "p2c_candidate_hash": candidate_body.get("canonical_candidate_hash"),
        "p2c_canonical_result_hash": candidate_body.get("canonical_result_hash"),
        "p2c_objective_vector": candidate_body.get("placement_objective_vector"),
    }
    interaction = p2d_body.get("personnel_truck_evaluation")
    interaction_status = interaction.get("status") if isinstance(interaction, Mapping) else None
    search = candidate_body.get("search_provenance")
    skeleton = search.get("structural_skeleton") if isinstance(search, Mapping) else None
    family = skeleton.get("family") if isinstance(skeleton, Mapping) else None
    row.update(
        {
            "composition_family": dict(family) if isinstance(family, Mapping) else None,
            "search_phase": search.get("search_phase") if isinstance(search, Mapping) else None,
            "p2d_status": p2d_body.get("result_identity"),
            "p2d_full_pass": p2d_body.get("project_layout_validated") is True
            and p2d_body.get("p2_complete") is True,
            "project_layout_validated": p2d_body.get("project_layout_validated"),
            "p2_complete": p2d_body.get("p2_complete"),
            "access_pass_count": p2d_body.get("access_pass_count"),
            "access_requirement_count": p2d_body.get("access_requirement_count"),
            "truck_route_validated": p2d_body.get("truck_route_validated"),
            "personnel_truck_status": interaction_status,
            "warnings": list(p2d_body.get("warnings", [])),
            "truck_route_codes": list(p2d_body.get("truck_route_codes", [])),
            "p2d_result_hash": p2d_body.get("canonical_result_hash"),
        }
    )
    return row


def _lane_budget_split(lane_budget: int) -> tuple[int, int]:
    """Give structured construction first use of the lane's bounded budget.

    General fallback is allocated only from a remainder when structured search
    has actually exhausted its family before using the lane budget. A truncated
    structured family is not evidence that its candidates do not exist.
    """
    return lane_budget, 0


def _family_lane_budgets(
    total_budget: int, lane_count: int, *, preferred_lane_index: int | None = None
) -> tuple[int, ...]:
    if lane_count <= 0 or total_budget <= 0:
        raise _error("INVALID_PLACEMENT_SEARCH_BUDGET")
    if preferred_lane_index is not None and not 0 <= preferred_lane_index < lane_count:
        raise _error("STRUCTURAL_PREFERRED_LANE_INDEX_INVALID")
    coverage_per_lane = min(
        MIN_CONSTRUCTIVE_SKELETON_NODE_ALLOWANCE,
        total_budget // lane_count,
    )
    budgets = [coverage_per_lane] * lane_count
    remaining = total_budget - sum(budgets)
    quotient, remainder = divmod(remaining, lane_count)
    for index in range(lane_count):
        budgets[index] += quotient
    preferred_order = (preferred_lane_index,) if preferred_lane_index is not None else ()
    preference_order = preferred_order + tuple(
        index for index in range(lane_count) if index != preferred_lane_index
    )
    for index in preference_order[:remainder]:
        budgets[index] += 1
    return tuple(budgets)


def _preferred_topology_index(
    lanes: tuple[StructuralTopologyLaneV1, ...],
    preferred_family: StructuralCompositionFamilyV1 | None,
) -> int | None:
    if preferred_family is None:
        return None
    preferred_topology = (
        CENTRAL_PROCESS_HUB
        if preferred_family.family == CENTRAL_PROCESS_HUB
        else STRAIGHT_LINEAR_BAND
    )
    return next(
        (index for index, lane in enumerate(lanes) if lane.topology == preferred_topology),
        None,
    )


def _selector_topology_lanes(
    site_geometry: Mapping[str, object],
    handoff: object | None = None,
) -> tuple[StructuralTopologyLaneV1, ...]:
    """Bind deterministic topology identities to site family candidates."""
    site = site_geometry.get("site")
    has_boundary = isinstance(site, Mapping) and isinstance(
        site.get("effective_buildable_boundary"), Mapping
    )
    authorities = _zone_authorities_from_handoff(handoff)
    if handoff is None or not has_boundary or authorities is None:
        families = composition_family_candidates(site_geometry)
        return tuple(
            StructuralTopologyLaneV1(
                CENTRAL_PROCESS_HUB
                if family.family == CENTRAL_PROCESS_HUB
                else STRAIGHT_LINEAR_BAND
                if family.dominant_direction == "POSITIVE"
                else OFFSET_LINEAR_BAND,
                family,
            )
            for family in families
        )
    return structural_topology_lanes(site_geometry, authorities)


def _zone_authorities_from_handoff(
    handoff: object | None,
) -> dict[str, Mapping[str, object]] | None:
    if isinstance(handoff, ZoneDimensioningResultV1):
        body: object = handoff.to_dict()
    elif isinstance(handoff, Mapping):
        body = handoff
    else:
        return None
    historical = body.get("p1e_historical_handoff") if isinstance(body, Mapping) else None
    dimension = historical.get("dimension_handoff") if isinstance(historical, Mapping) else None
    raw_authorities = dimension.get("authorities") if isinstance(dimension, Mapping) else None
    if not isinstance(raw_authorities, list):
        return None
    authorities = {
        str(row["zone_code"]): row
        for row in raw_authorities
        if isinstance(row, Mapping) and isinstance(row.get("zone_code"), str)
    }
    if len(authorities) != len(raw_authorities):
        return None
    return authorities


def _preferred_family_from_handoff(
    site_body: Mapping[str, Any], handoff: object
) -> StructuralCompositionFamilyV1 | None:
    authorities = _zone_authorities_from_handoff(handoff)
    if authorities is None:
        return None
    try:
        return select_structural_composition_family(site_body, authorities)
    except (KeyError, TypeError, ValueError):
        # Preference only orders lanes. The normal P1 validation remains
        # responsible for rejecting invalid inputs, and no lane is removed.
        return None


def _placement_geometry_signature(candidate: Mapping[str, Any]) -> str:
    zones = candidate.get("zones")
    if not isinstance(zones, list):
        return canonical_json(
            {
                "candidate_hash": candidate.get("canonical_candidate_hash"),
                "marker": candidate.get("marker"),
            }
        )
    geometry = [
        {
            field: row.get(field)
            for field in ("zone_code", "x", "y", "width_m", "depth_m", "rotation_deg")
        }
        for row in zones
        if isinstance(row, Mapping)
    ]
    geometry.sort(key=lambda row: str(row["zone_code"]))
    return canonical_json(geometry)


def _main_process_geometry_signature(candidate: Mapping[str, Any]) -> str:
    rows = candidate.get("zones")
    if not isinstance(rows, list):
        raise LayoutAuthorityError("MAIN_PROCESS_SKELETON_FACTS_UNAVAILABLE")
    by_code = {
        str(row["zone_code"]): row
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("zone_code"), str)
    }
    if not set(MAIN_PROCESS_ZONE_CODES) <= set(by_code):
        raise LayoutAuthorityError("MAIN_PROCESS_SKELETON_FACTS_UNAVAILABLE")
    return canonical_json(
        [
            {
                field: by_code[code].get(field)
                for field in ("zone_code", "x", "y", "width_m", "depth_m", "rotation_deg")
            }
            for code in MAIN_PROCESS_ZONE_CODES
        ]
    )


def _selection_provenance(
    lane_reports: list[dict[str, Any]],
    *,
    placement_node_budget: int,
    p2c_candidate_count: int,
    p2d_validated_count: int,
    p2d_full_pass_count: int,
    selected: bool,
) -> dict[str, Any]:
    tree_exhausted = all(row["search_tree_exhausted"] for row in lane_reports)
    node_budget_exhausted = any(row["node_budget_exhausted"] for row in lane_reports)
    public_lane_reports = [
        {
            **{
                key: value
                for key, value in lane.items()
                if key
                not in {
                    "topology",
                    "scheduler_policy",
                    "topology_coverage_node_budget",
                    "preference_extra_node_budget",
                }
            },
            "phases": [
                {
                    key: value
                    for key, value in phase.items()
                    if key != "main_process_skeleton_generation"
                }
                for phase in lane["phases"]
            ],
        }
        for lane in lane_reports
    ]
    return {
        "identity": IDENTITY,
        "selection_basis": P2C_CANDIDATE_SELECTION_BASIS,
        "p2c_candidate_enumeration": {
            "candidate_family": "MULTI_FAMILY_STRUCTURAL_SKELETON_V1",
            "node_budget": placement_node_budget,
            "visited_nodes": sum(row["visited_nodes"] for row in lane_reports),
            "complete_candidates": p2c_candidate_count,
            "node_budget_exhausted": node_budget_exhausted,
            "search_tree_exhausted": tree_exhausted,
            "family_lanes": public_lane_reports,
            "node_budget_is_only_search_cutoff": True,
            "global_optimum_claimed": False,
        },
        "p2c_candidate_count": p2c_candidate_count,
        "p2d_validated_candidate_count": p2d_validated_count,
        "p2d_full_pass_candidate_count": p2d_full_pass_count,
        "selected_candidate": selected,
        "objective_optimal_within_search_family": selected and tree_exhausted,
        "route_objective_optimization_active": False,
        "p4_candidate_selection": False,
        "no_mathematical_infeasibility_proof": True,
    }


def _record_is_better(
    candidate: tuple[
        dict[str, Any], dict[str, Any], StructuralQualityFactsV1, StructuralCompositionFamilyV1
    ],
    best: tuple[
        dict[str, Any], dict[str, Any], StructuralQualityFactsV1, StructuralCompositionFamilyV1
    ]
    | None,
    preferred_loading_side: str,
) -> bool:
    if best is None:
        return True
    candidate_facts = candidate[2]
    best_facts = best[2]
    if candidate_facts.comparison_key != best_facts.comparison_key:
        return structural_candidate_is_better(candidate_facts, best_facts)
    business_comparison = compare_placement_candidate_business_objectives(
        candidate[0], best[0], preferred_loading_side
    )
    if business_comparison != 0:
        return business_comparison > 0
    return placement_candidate_canonical_tiebreak_key(candidate[0]) < (
        placement_candidate_canonical_tiebreak_key(best[0])
    )


_STRUCTURAL_COMPONENTS = (
    "STRUCTURED_GENERATION",
    "MAIN_GROUP_ORDER_MONOTONIC",
    "PROCESS_CORE_CONTIGUOUS",
    "COMPOSITION_FAMILY_MATCH",
    "RAW_SIDE_GROUPING",
    "PROCESSING_CORE_GROUPING",
    "FINISHED_SIDE_GROUPING",
    "SUPPORT_GROUPING",
    "PERSONNEL_GROUPING",
    "PROCESS_CORE_LEGIBILITY",
    "FINISHED_SHIPPING_INTERFACE_ALIGNMENT",
    "AUTHORITATIVE_SUPPORT_ROUTE_COUNT",
    "SUPPORT_ATTACHMENT_SIDE_COUNT",
    "SUPPORT_COMPONENT_COUNT",
    "SUPPORT_BRANCH_DIRECT_EDGE_COUNT",
    "SUPPORT_OCCUPIED_CORE_FACES",
    "CORE_EXPOSED_MAIN_FACES",
    "PERSONNEL_PERIPHERAL_BOUNDARY_CONTACTS",
    "STORAGE_BANK_ALIGNMENT",
    "MAJOR_AXIS_ALIGNMENT_INCIDENCES",
    "DEPTH_ALIGNMENT_ELIGIBLE_PAIRS",
    "BUILDING_OUTLINE_CLASS",
)


def _first_decisive_component(
    candidate: tuple[
        dict[str, Any], dict[str, Any], StructuralQualityFactsV1, StructuralCompositionFamilyV1
    ],
    other: tuple[
        dict[str, Any], dict[str, Any], StructuralQualityFactsV1, StructuralCompositionFamilyV1
    ],
    preferred_loading_side: str,
) -> tuple[str, object, object]:
    candidate_key = candidate[2].comparison_key
    other_key = other[2].comparison_key
    for index, component in enumerate(_STRUCTURAL_COMPONENTS):
        if (
            index < len(candidate_key)
            and index < len(other_key)
            and candidate_key[index] != other_key[index]
        ):
            return component, candidate_key[index], other_key[index]

    candidate_vector = candidate[0].get("placement_objective_vector", {})
    other_vector = other[0].get("placement_objective_vector", {})
    if isinstance(candidate_vector, Mapping) and isinstance(other_vector, Mapping):
        candidate_should = candidate_vector.get("should_adjacency", {})
        other_should = other_vector.get("should_adjacency", {})
        if isinstance(candidate_should, Mapping) and isinstance(other_should, Mapping):
            candidate_count = candidate_should.get("satisfied_count")
            other_count = other_should.get("satisfied_count")
            if candidate_count != other_count:
                return "P2B2_SHOULD_ADJACENCY", candidate_count, other_count
        candidate_loading = candidate_vector.get("loading_side", {})
        other_loading = other_vector.get("loading_side", {})
        if isinstance(candidate_loading, Mapping) and isinstance(other_loading, Mapping):
            if preferred_loading_side in {"NORTH", "EAST", "SOUTH", "WEST"}:
                candidate_match = candidate_loading.get("match")
                other_match = other_loading.get("match")
                if candidate_match != other_match:
                    return "P2B2_LOADING_SIDE_PREFERENCE", candidate_match, other_match
            elif preferred_loading_side == "NEAREST_TRUCK_ENTRANCE":
                candidate_distance = candidate_loading.get("distance_squared_mm2")
                other_distance = other_loading.get("distance_squared_mm2")
                if candidate_distance != other_distance:
                    return (
                        "P2B2_NEAREST_TRUCK_ENTRANCE",
                        candidate_distance,
                        other_distance,
                    )
    return "CANONICAL_JSON_FINAL_TIE_BREAK", "CANONICAL_ORDER_WINNER", "CANONICAL_ORDER_RUNNER_UP"


def _internal_selection_evaluation(
    selected: tuple[
        dict[str, Any], dict[str, Any], StructuralQualityFactsV1, StructuralCompositionFamilyV1
    ],
    alternatives: list[
        tuple[
            dict[str, Any], dict[str, Any], StructuralQualityFactsV1, StructuralCompositionFamilyV1
        ]
    ],
    *,
    structured_candidate_count: int,
    fallback_candidate_count: int,
    p2b2_tiebreak_used: bool,
    canonical_json_tiebreak_used: bool,
    preferred_loading_side: str,
    lane_reports: list[dict[str, Any]],
    r6_topology_diagnostics: Mapping[str, Any],
    full_pass_records: list[
        tuple[
            dict[str, Any],
            dict[str, Any],
            StructuralQualityFactsV1,
            StructuralCompositionFamilyV1,
        ]
    ],
) -> dict[str, Any]:
    selected_facts = selected[2]
    runner_up = alternatives[0] if alternatives else None
    first_component = "ONLY_FULL_PASS_CANDIDATE_IN_EXPLORED_FAMILY"
    winner_value: object = None
    runner_up_value: object = None
    if runner_up is not None:
        first_component, winner_value, runner_up_value = _first_decisive_component(
            selected, runner_up, preferred_loading_side
        )
    selected_skeleton_signature = _main_process_geometry_signature(selected[0])
    best_by_skeleton: dict[
        str,
        tuple[
            dict[str, Any],
            dict[str, Any],
            StructuralQualityFactsV1,
            StructuralCompositionFamilyV1,
        ],
    ] = {}
    for record in full_pass_records:
        signature = _main_process_geometry_signature(record[0])
        current = best_by_skeleton.get(signature)
        if _record_is_better(record, current, preferred_loading_side):
            best_by_skeleton[signature] = record
    distinct_runner_up: (
        tuple[
            dict[str, Any],
            dict[str, Any],
            StructuralQualityFactsV1,
            StructuralCompositionFamilyV1,
        ]
        | None
    ) = None
    for signature, record in best_by_skeleton.items():
        if signature == selected_skeleton_signature:
            continue
        if _record_is_better(record, distinct_runner_up, preferred_loading_side):
            distinct_runner_up = record

    distinct_first_component = "ONLY_ONE_P2D_FULL_PASS_MAIN_SKELETON"
    distinct_winner_value: object = None
    distinct_runner_value: object = None
    if distinct_runner_up is not None:
        (
            distinct_first_component,
            distinct_winner_value,
            distinct_runner_value,
        ) = _first_decisive_component(selected, distinct_runner_up, preferred_loading_side)
    distinct_business_comparison = (
        compare_placement_candidate_business_objectives(
            selected[0], distinct_runner_up[0], preferred_loading_side
        )
        if distinct_runner_up is not None
        else 0
    )
    distinct_structural_tie = bool(
        distinct_runner_up is not None
        and selected[2].comparison_key == distinct_runner_up[2].comparison_key
    )
    distinct_canonical_tiebreak_used = False
    if (
        distinct_runner_up is not None
        and distinct_structural_tie
        and distinct_business_comparison == 0
    ):
        distinct_canonical_tiebreak_used = placement_candidate_canonical_tiebreak_key(
            selected[0]
        ) != placement_candidate_canonical_tiebreak_key(distinct_runner_up[0])
    ordinary_runner_same_skeleton = bool(
        runner_up is not None
        and _main_process_geometry_signature(selected[0])
        == _main_process_geometry_signature(runner_up[0])
    )

    skeleton_survival = [
        lifecycle
        for lane in lane_reports
        for phase in lane.get("phases", [])
        if isinstance(phase, Mapping)
        for generation in [phase.get("main_process_skeleton_generation", {})]
        if isinstance(generation, Mapping)
        for lifecycle in generation.get("skeleton_tail_lifecycle", [])
        if isinstance(lifecycle, Mapping)
    ]
    topology_count_explored = len(
        {str(lane.get("topology")) for lane in lane_reports if lane.get("topology")}
    )
    topology_count_constructed = len(
        {
            str(lifecycle.get("discovery_topology", lifecycle.get("topology")))
            for lifecycle in skeleton_survival
            if lifecycle.get("skeleton_hash")
        }
    )
    distinct_evaluated_skeletons = len(
        {
            str(lifecycle.get("skeleton_hash"))
            for lifecycle in skeleton_survival
            if lifecycle.get("p2d_reached") is True
        }
    )
    distinct_full_pass_skeletons = len(best_by_skeleton)
    selected_payload = selected_facts.to_dict()
    selected_structured = selected_payload.get("structurally_generated") is True
    return {
        "identity": "p1a-structural-candidate-selection-evaluation@1.0.0",
        "selection_basis": P2C_CANDIDATE_SELECTION_BASIS,
        "selected_composition_family": selected[3].to_dict(),
        "selected_topology": selected[0].get("_r5_topology"),
        "selected_candidate_hash": selected[0].get("canonical_candidate_hash"),
        "selected_main_process_skeleton_hash": selected[0].get("_r5_skeleton_hash"),
        "selected_p2d_result_hash": selected[1].get("canonical_result_hash"),
        "selected_structural_facts": selected_payload,
        "structural_candidate_count": structured_candidate_count,
        "fallback_candidate_count": fallback_candidate_count,
        "structural_fallback_used": not selected_structured,
        "runner_up_present": runner_up is not None,
        "runner_up_candidate_hash": runner_up[0].get("canonical_candidate_hash")
        if runner_up is not None
        else None,
        "runner_up_main_process_skeleton_hash": runner_up[0].get("_r5_skeleton_hash")
        if runner_up is not None
        else None,
        "runner_up_structural_facts": runner_up[2].to_dict() if runner_up is not None else None,
        "first_decisive_component": first_component,
        "winner_value": winner_value,
        "runner_up_value": runner_up_value,
        "search_policy": "STAGED_COVERAGE_THEN_PREFERENCE",
        "topology_count_explored": topology_count_explored,
        "topology_count_with_constructed_skeleton": topology_count_constructed,
        "discovery_lane_count_with_constructed_skeleton": topology_count_constructed,
        "constructed_main_process_skeleton_count": len(
            {
                str(lifecycle.get("skeleton_hash"))
                for lifecycle in skeleton_survival
                if lifecycle.get("skeleton_hash")
            }
        ),
        "p2d_evaluated_distinct_main_process_skeleton_count": distinct_evaluated_skeletons,
        "p2d_full_pass_distinct_main_process_skeleton_count": distinct_full_pass_skeletons,
        "skeleton_survival": skeleton_survival,
        "distinct_runner_up_present": distinct_runner_up is not None,
        "distinct_runner_up_skeleton_hash": distinct_runner_up[0].get("_r5_skeleton_hash")
        if distinct_runner_up is not None
        else None,
        "distinct_runner_up_topology": distinct_runner_up[0].get("_r5_topology")
        if distinct_runner_up is not None
        else None,
        "distinct_runner_up_p2d_full_pass": distinct_runner_up is not None,
        "distinct_skeleton_first_decisive_component": distinct_first_component,
        "distinct_skeleton_winner_value": distinct_winner_value,
        "distinct_skeleton_runner_up_value": distinct_runner_value,
        "distinct_skeleton_p2b2_business_objective_used": (
            distinct_structural_tie and distinct_business_comparison != 0
        ),
        "distinct_skeleton_canonical_json_tiebreak_used": distinct_canonical_tiebreak_used,
        "p2b2_tiebreak_used": p2b2_tiebreak_used,
        "canonical_json_tiebreak_used": canonical_json_tiebreak_used,
        "canonical_json_tiebreak_scope": (
            "SAME_MAIN_PROCESS_SKELETON_TAIL_VARIANTS"
            if canonical_json_tiebreak_used and ordinary_runner_same_skeleton
            else "DISTINCT_MAIN_PROCESS_SKELETONS"
            if canonical_json_tiebreak_used
            else "NOT_USED"
        ),
        "hard_feasibility_passed": True,
        "comparison_mode": "LEXICOGRAPHIC_ATOMIC_FACTS",
        "route_objective_optimization_active": False,
        "family_lanes": lane_reports,
        "distinct_full_pass_family_count": len(
            {canonical_json(record[3].to_dict()) for record in full_pass_records}
        ),
        "distinct_full_pass_main_process_skeleton_count": len(
            {_main_process_geometry_signature(record[0]) for record in full_pass_records}
        ),
        "r6_topology_diagnostics": dict(r6_topology_diagnostics),
    }


def select_validated_placement(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: ZoneDimensioningResultV1 | Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    truck_maneuver_binding: BoundTruckManeuverProjectInputV1 | Mapping[str, Any] | None = None,
    objective_profile: ObjectiveProfileV1 | Mapping[str, object] | None = None,
    *,
    placement_node_budget: int = 50_000,
    complete_candidate_limit: int | None = None,
    route_node_budget: int = 20_000,
    truck_node_budget: int = 20_000,
) -> ValidatedPlacementSelectionResultV1:
    """Validate all complete P2C candidates and select the best P2C-ranked pass.

    No route metric participates in selection.  A P2D result is eligible only
    when both of its final validation flags are true.  If the deterministic
    P2C search is bounded before a full pass is found, the result remains an
    explicit search-exhaustion result rather than an infeasibility proof.
    """
    site_body = site_geometry.to_dict()
    site = site_body.get("site")
    if not isinstance(site, Mapping) or not isinstance(site.get("preferred_loading_side"), str):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="preferred_loading_side")
    preferred_loading_side = str(site["preferred_loading_side"])

    trace: list[dict[str, Any]] = []
    p2d_validated_count = 0
    p2d_full_pass_count = 0
    full_pass_records: list[
        tuple[
            dict[str, Any], dict[str, Any], StructuralQualityFactsV1, StructuralCompositionFamilyV1
        ]
    ] = []
    lane_reports: list[dict[str, Any]] = []
    skeleton_lifecycle_by_hash: dict[str, dict[str, Any]] = {}
    global_skeleton_geometry_registry: dict[str, dict[str, Any]] = {}
    cross_topology_duplicate_trace: list[dict[str, Any]] = []
    r6_topology_diagnostics: dict[str, Any] = {
        "identity": "p1a-r7-geometry-evaluation-evidence@1.0.0",
        "ownership_matrix": [],
        "ownership_duplicates": [],
        "geometry_evaluation_admissions": [],
        "tail_slot_preflight_trace": [],
        "main_skeleton_truck_preflight_trace": [],
        "construction_attempts": [],
        "constructive_divergence_trace": [],
        "offset_transition_trace": [],
        "topology_classification_failures": [],
        "cross_topology_duplicate_geometry_trace": cross_topology_duplicate_trace,
        "global_unique_skeleton_geometry_count": 0,
        "geometry_evaluation_registry": [],
        "r11_scheduler_trace": [],
        "r11_work_queue": [],
        "r11_budget_accounting": {},
    }
    topology_lanes = _selector_topology_lanes(site_body, p1_handoff)
    preferred_family = _preferred_family_from_handoff(site_body, p1_handoff)
    preferred_lane_index = _preferred_topology_index(topology_lanes, preferred_family)
    topology_coverage_budget = min(
        MIN_CONSTRUCTIVE_SKELETON_NODE_ALLOWANCE,
        placement_node_budget // len(topology_lanes),
    )
    # Discover non-canonical owners before the precedence owner so geometries
    # seen first in Offset/Hub lanes can be consumed at most once by their
    # canonical Straight lane. Lane order is identity servicing, not a quality
    # bonus; candidate comparison remains hard-gate then atomic structural facts.
    canonical_service_order = (
        OFFSET_LINEAR_BAND,
        CENTRAL_PROCESS_HUB,
        STRAIGHT_LINEAR_BAND,
    )
    lane_order = tuple(
        index
        for topology in canonical_service_order
        for index, lane in enumerate(topology_lanes)
        if lane.topology == topology
    )
    direct_synthesis_lane_index = (
        preferred_lane_index if preferred_lane_index is not None else lane_order[0]
    )
    global_node_budget_remaining = placement_node_budget
    global_node_visits = 0
    p2c_candidate_count = 0
    candidate_index = 0
    lane_state: dict[int, dict[str, Any]] = {}
    phase_states: list[dict[str, Any]] = []

    def make_enumeration(lane_index: int, phase: str) -> Any:
        lane = topology_lanes[lane_index]
        phase_budget = (
            min(placement_node_budget, len(BASE_LAYOUT_FAMILIES))
            if phase == STRUCTURED_PHASE
            else placement_node_budget
        )
        return enumerate_placement_candidates(
            canonical_zone_plan,
            p1_handoff,
            site_geometry,
            objective_profile,
            node_budget=phase_budget,
            truck_maneuver_binding=truck_maneuver_binding,
            truck_node_budget=truck_node_budget,
            truck_maneuver_validator=validate_truck_maneuver_chain,
            complete_candidate_limit=complete_candidate_limit,
            structural_family=lane.family,
            structural_topology=lane.topology,
            search_phase=phase,
            direct_synthesis_enabled=True,
            global_main_process_geometry_registry=global_skeleton_geometry_registry,
            global_cross_topology_duplicate_trace=cross_topology_duplicate_trace,
        )

    for lane_index in lane_order:
        lane = topology_lanes[lane_index]
        lane_report: dict[str, Any] = {
            "composition_family": lane.family.to_dict(),
            "topology": lane.topology,
            "scheduler_policy": "STAGED_COVERAGE_THEN_PREFERENCE",
            "topology_coverage_node_budget": topology_coverage_budget,
            "diversity_expansion_node_budget": 0,
            "preference_extra_node_budget": 0,
            "preferred_lane": preferred_family is not None and lane_index == preferred_lane_index,
            "lane_node_budget": placement_node_budget,
            "global_budget_before_lane": None,
            "structured_node_budget": min(placement_node_budget, len(BASE_LAYOUT_FAMILIES)),
            "fallback_node_budget": 0,
            "phases": [],
            "p2d_full_pass_candidate_count": 0,
            "p2d_rejected_candidate_count": 0,
            "p2d_rejection_warnings": [],
            "visited_nodes": 0,
            "complete_candidates": 0,
            "node_budget_exhausted": False,
            "search_tree_exhausted": False,
        }
        lane_reports.append(lane_report)
        lane_state[lane_index] = {
            "seen_geometry": set(),
            "full_pass_count": 0,
            "report": lane_report,
        }
        if lane_index == direct_synthesis_lane_index:
            phase_states.append(
                {
                    "lane_index": lane_index,
                    "phase": STRUCTURED_PHASE,
                    "phase_budget": min(placement_node_budget, len(BASE_LAYOUT_FAMILIES)),
                    "enumeration": make_enumeration(lane_index, STRUCTURED_PHASE),
                    "candidate_count": 0,
                    "rejected_count": 0,
                    "full_pass_count": 0,
                    "status": "ACTIVE",
                    "finalized": False,
                }
            )
        else:
            lane_report["structured_phase_status"] = (
                "ALL_LAYOUT_FAMILIES_COVERED_BY_DIRECT_SYNTHESIS_LANE"
            )

    def process_candidate(state: dict[str, Any], candidate: Any) -> None:
        nonlocal p2c_candidate_count, candidate_index, p2d_validated_count
        nonlocal p2d_full_pass_count
        lane_index = int(state["lane_index"])
        lane = topology_lanes[lane_index]
        phase = str(state["phase"])
        enumeration = state["enumeration"]
        lane_report = lane_state[lane_index]["report"]
        candidate_body = candidate.to_dict()
        candidate_hash = candidate_body.get("canonical_candidate_hash")
        skeleton_hash_getter = getattr(enumeration, "candidate_main_process_skeleton_hash", None)
        topology_getter = getattr(enumeration, "candidate_topology", None)
        family_getter = getattr(enumeration, "candidate_structural_family", None)
        discovery_topology_getter = getattr(enumeration, "candidate_discovery_topology", None)
        skeleton_hash = (
            skeleton_hash_getter(candidate_hash)
            if isinstance(candidate_hash, str) and callable(skeleton_hash_getter)
            else None
        )
        candidate_body["_r5_topology"] = (
            topology_getter(candidate_hash)
            if isinstance(candidate_hash, str) and callable(topology_getter)
            else lane.topology
        )
        candidate_body["_r5_skeleton_hash"] = skeleton_hash
        candidate_body["_r7_discovery_topology"] = (
            discovery_topology_getter(candidate_hash)
            if isinstance(candidate_hash, str) and callable(discovery_topology_getter)
            else lane.topology
        )
        geometry_signature = _placement_geometry_signature(candidate_body)
        seen_geometry = lane_state[lane_index]["seen_geometry"]
        if geometry_signature in seen_geometry:
            return
        seen_geometry.add(geometry_signature)
        state["candidate_count"] += 1
        p2c_candidate_count += 1
        candidate_index += 1
        routed = route_site_placement(
            canonical_zone_plan,
            p1_handoff,
            site_geometry,
            candidate,
            truck_maneuver_binding,
            route_node_budget=route_node_budget,
            truck_node_budget=truck_node_budget,
        )
        p2d_validated_count += 1
        routed_body = routed.to_dict()
        full_pass = (
            routed_body.get("project_layout_validated") is True
            and routed_body.get("p2_complete") is True
        )
        if isinstance(skeleton_hash, str):
            lifecycle = skeleton_lifecycle_by_hash.setdefault(
                skeleton_hash,
                {
                    "skeleton_hash": skeleton_hash,
                    "discovery_topology": candidate_body.get("_r7_discovery_topology"),
                    "canonical_topology_owner": candidate_body.get("_r5_topology"),
                    "tail_search_started_by_topology": candidate_body.get("_r7_discovery_topology"),
                    "p2d_reached": True,
                    "p2d_candidate_count": 0,
                    "p2d_full_pass_count": 0,
                    "first_failure_stage": None,
                    "first_failure_reason": None,
                },
            )
            lifecycle["p2d_candidate_count"] += 1
            registry_row = global_skeleton_geometry_registry.get(skeleton_hash)
            if registry_row is not None:
                registry_row["p2d_reached"] = True
                registry_row["p2d_candidate_count"] = (
                    int(registry_row.get("p2d_candidate_count", 0)) + 1
                )
            if full_pass:
                lifecycle["p2d_full_pass_count"] += 1
                if registry_row is not None:
                    registry_row["p2d_full_pass_count"] = (
                        int(registry_row.get("p2d_full_pass_count", 0)) + 1
                    )
            elif lifecycle["first_failure_stage"] is None:
                lifecycle["first_failure_stage"] = "P2D"
                warnings = routed_body.get("warnings")
                lifecycle["first_failure_reason"] = (
                    warnings[0]
                    if isinstance(warnings, list) and warnings
                    else "P2D_HARD_VALIDATION_FAILED"
                )
                if registry_row is not None:
                    registry_row.setdefault("first_failure_stage", "P2D")
                    registry_row.setdefault(
                        "first_failure_reason", lifecycle["first_failure_reason"]
                    )
        trace.append(_p2d_trace_row(candidate_index, candidate_body, p2d_body=routed_body))
        if not full_pass:
            state["rejected_count"] += 1
            for warning in routed_body.get("warnings", []):
                if (
                    isinstance(warning, str)
                    and warning not in lane_report["p2d_rejection_warnings"]
                ):
                    lane_report["p2d_rejection_warnings"].append(warning)
            return
        state["full_pass_count"] += 1
        lane_state[lane_index]["full_pass_count"] += 1
        lane_report["p2d_full_pass_candidate_count"] += 1
        p2d_full_pass_count += 1
        structural_flag_getter = getattr(enumeration, "structurally_generated", None)
        structurally_generated = bool(
            phase == STRUCTURED_PHASE
            and callable(structural_flag_getter)
            and isinstance(candidate_hash, str)
            and structural_flag_getter(candidate_hash)
        )
        candidate_family = (
            family_getter(candidate_hash)
            if isinstance(candidate_hash, str) and callable(family_getter)
            else None
        ) or lane.family
        try:
            structural_facts = build_structural_quality_facts(
                candidate_body,
                routed_body,
                site_body,
                candidate_family,
                structurally_generated=structurally_generated,
                search_phase=phase,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _error(
                "STRUCTURAL_QUALITY_FACTS_UNAVAILABLE",
                candidate_index=candidate_index,
                reason=type(exc).__name__,
            ) from None
        full_pass_records.append((candidate_body, routed_body, structural_facts, candidate_family))

    def finalize_phase(state: dict[str, Any]) -> None:
        if state["finalized"]:
            return
        lane_index = int(state["lane_index"])
        lane = topology_lanes[lane_index]
        lane_report = lane_state[lane_index]["report"]
        enumeration = state["enumeration"]
        phase = str(state["phase"])
        generation_report = dict(enumeration.skeleton_generation_report)
        preflight_rows = getattr(enumeration, "main_skeleton_truck_preflight_rows", ())
        r6_topology_diagnostics["main_skeleton_truck_preflight_trace"].extend(
            dict(row) for row in preflight_rows if isinstance(row, Mapping)
        )
        for skeleton_row in generation_report.get("candidates", []):
            if not isinstance(skeleton_row, dict):
                continue
            r6_topology_diagnostics["ownership_matrix"].append(
                {
                    "skeleton_hash": skeleton_row.get("main_process_skeleton_hash"),
                    "discovery_topology": skeleton_row.get("discovery_topology", lane.topology),
                    "constructed_topology": skeleton_row.get("topology"),
                    "canonical_owner": skeleton_row.get("canonical_topology_owner"),
                    "discovery_family": skeleton_row.get("discovery_family"),
                    "canonical_family": skeleton_row.get("canonical_family"),
                    "construction_policy": skeleton_row.get("construction_policy"),
                    "topology_divergence_stage": skeleton_row.get("topology_divergence_stage"),
                    "offset_transition_stage": skeleton_row.get("offset_transition_stage"),
                    "offset_direction": skeleton_row.get("offset_direction"),
                    "offset_cross_axis_shift_mm": skeleton_row.get("offset_cross_axis_shift_mm"),
                }
            )
            for field in (
                "canonical_topology_owner",
                "discovery_topology",
                "discovery_family",
                "canonical_family",
                "construction_policy",
                "topology_divergence_stage",
                "offset_transition_stage",
                "offset_direction",
                "offset_cross_axis_shift_mm",
            ):
                skeleton_row.pop(field, None)
        attempts = generation_report.get("construction_attempts", [])
        if isinstance(attempts, list):
            r6_topology_diagnostics["construction_attempts"].extend(
                dict(row, topology=row.get("topology", lane.topology))
                for row in attempts
                if isinstance(row, Mapping)
            )
        for source_key, target_key in (
            ("_r6_topology_ownership_duplicates", "ownership_duplicates"),
            ("_r7_geometry_evaluation_admissions", "geometry_evaluation_admissions"),
            ("tail_slot_preflight_rows", "tail_slot_preflight_trace"),
            ("_r6_offset_transition_trace", "offset_transition_trace"),
            ("_r6_constructive_divergence_attempts", "constructive_divergence_trace"),
            ("_r6_topology_classification_failures", "topology_classification_failures"),
        ):
            rows = generation_report.pop(source_key, [])
            if isinstance(rows, list):
                r6_topology_diagnostics[target_key].extend(rows)
        generation_report.pop("_r6_cross_topology_duplicate_count", None)
        enriched_lifecycle = []
        raw_rows = generation_report.get("skeleton_tail_lifecycle", [])
        raw_facts = generation_report.get("tail_search_zone_facts", {})
        for row in raw_rows if isinstance(raw_rows, list) else []:
            if not isinstance(row, Mapping):
                continue
            item = dict(row)
            skeleton_hash = str(item.get("skeleton_hash"))
            zone_facts = raw_facts.get(skeleton_hash, {}) if isinstance(raw_facts, Mapping) else {}
            item["zero_option_tail_zone_codes"] = sorted(
                str(code)
                for code, facts in zone_facts.items()
                if isinstance(facts, Mapping)
                and int(facts.get("branch_visits", 0)) > 0
                and int(facts.get("candidate_options", 0)) == 0
            )
            p2d = skeleton_lifecycle_by_hash.get(skeleton_hash, {})
            item["p2d_reached"] = p2d.get("p2d_reached", False)
            item["p2d_candidate_count"] = p2d.get("p2d_candidate_count", 0)
            item["p2d_full_pass_count"] = p2d.get("p2d_full_pass_count", 0)
            if item["p2d_reached"] and not item["p2d_full_pass_count"]:
                item["first_failure_stage"] = "P2D"
                item["first_failure_reason"] = p2d.get(
                    "first_failure_reason", "P2D_HARD_VALIDATION_FAILED"
                )
            enriched_lifecycle.append(item)
        generation_report["skeleton_tail_lifecycle"] = enriched_lifecycle
        phase_row = {
            "search_phase": phase,
            "node_budget": state["phase_budget"],
            "visited_nodes": enumeration.visited_node_count,
            "complete_candidates": enumeration.candidate_count,
            "distinct_main_process_skeleton_count": (
                enumeration.distinct_main_process_skeleton_count
            ),
            "distinct_structural_core_root_count": enumeration.distinct_structural_core_root_count,
            "validated_unique_candidates": state["candidate_count"],
            "p2d_rejected_candidate_count": state["rejected_count"],
            "p2d_full_pass_candidate_count": state["full_pass_count"],
            "node_budget_exhausted": enumeration.node_budget_exhausted,
            "search_tree_exhausted": enumeration.search_tree_exhausted,
            "main_process_skeleton_generation": generation_report,
        }
        lane_report["phases"].append(phase_row)
        lane_report["visited_nodes"] += enumeration.visited_node_count
        lane_report["complete_candidates"] += enumeration.candidate_count
        lane_report["p2d_rejected_candidate_count"] += state["rejected_count"]
        lane_report["node_budget_exhausted"] = (
            lane_report["node_budget_exhausted"] or enumeration.node_budget_exhausted
        )
        state["finalized"] = True

    active_states = list(phase_states)
    scheduler_round = 0
    while active_states and global_node_budget_remaining > 0:
        scheduler_round += 1
        round_states = list(active_states)
        active_states = []
        for turn_index, state in enumerate(round_states):
            if global_node_budget_remaining <= 0:
                active_states.append(state)
                continue
            enumeration = state["enumeration"]
            status_before = str(state["status"])
            turns_remaining = len(round_states) - turn_index
            fair_share = (global_node_budget_remaining + turns_remaining - 1) // turns_remaining
            quantum_limit = min(PLACEMENT_SEARCH_QUANTUM_NODES, fair_share)
            advance = enumeration.advance_quantum(quantum_limit)
            visited = advance.nodes_visited
            if visited > global_node_budget_remaining:
                raise _error(
                    "STRUCTURAL_GLOBAL_NODE_BUDGET_EXCEEDED",
                    topology=enumeration.structural_topology,
                )
            global_node_visits += visited
            global_node_budget_remaining -= visited
            state["status"] = advance.status
            lane_index = int(state["lane_index"])
            work_item = dict(advance.work_item or {})
            work_item_id = canonical_hash(
                {
                    "topology": topology_lanes[lane_index].topology,
                    "phase": state["phase"],
                    "work_item": work_item,
                }
            )
            work_row = {
                "round": scheduler_round,
                "work_item_id": work_item_id,
                "topology": topology_lanes[lane_index].topology,
                "root": work_item.get("sorting_root_mm"),
                "face_pair": [work_item.get("raw_side"), work_item.get("finished_side")],
                "offset_direction": work_item.get("offset_direction"),
                "nodes_before": global_node_visits - visited,
                "nodes_after": global_node_visits,
                "status_before": status_before,
                "status_after": advance.status,
                "continuation_created": not advance.completed,
                "quantum_node_limit": quantum_limit,
                "nodes_visited": visited,
                "work_item": work_item,
            }
            r6_topology_diagnostics["r11_scheduler_trace"].append(work_row)
            r6_topology_diagnostics["r11_work_queue"].append(work_row)
            for candidate in advance.candidates:
                process_candidate(state, candidate)
            if advance.completed:
                finalize_phase(state)
                if state["phase"] == STRUCTURED_PHASE and global_node_budget_remaining > 0:
                    fallback_order = lane_order
                    for fallback_lane in fallback_order:
                        if lane_state[fallback_lane]["full_pass_count"] > 0:
                            continue
                        fallback_report = lane_state[fallback_lane]["report"]
                        fallback_report["fallback_admission_reason"] = (
                            "STRUCTURED_PHASE_COMPLETED_WITH_REMAINING_GLOBAL_BUDGET"
                        )
                        fallback_report["fallback_node_budget"] = global_node_budget_remaining
                        fallback_report["fallback_budget_is_shared_pool"] = True
                        fallback_state = {
                            "lane_index": fallback_lane,
                            "phase": LEGACY_COMPAT_PHASE,
                            "phase_budget": placement_node_budget,
                            "enumeration": make_enumeration(fallback_lane, LEGACY_COMPAT_PHASE),
                            "candidate_count": 0,
                            "rejected_count": 0,
                            "full_pass_count": 0,
                            "status": "ACTIVE",
                            "finalized": False,
                        }
                        phase_states.append(fallback_state)
                        active_states.append(fallback_state)
            else:
                active_states.append(state)

    for state in phase_states:
        finalize_phase(state)

    global_node_budget_remaining = placement_node_budget - global_node_visits
    global_budget_exhausted = global_node_budget_remaining == 0
    if global_budget_exhausted:
        # The per-enumeration budget is a guardrail, while the shared scheduler
        # owns the actual production cutoff. Preserve the distinction in the
        # phase diagnostics without claiming that any lane's search tree ended.
        for state in active_states:
            lane_report = lane_state[int(state["lane_index"])]["report"]
            lane_report["node_budget_exhausted"] = True
    for lane_index in lane_order:
        lane_report = lane_state[lane_index]["report"]
        phase_rows = lane_report["phases"]
        lane_report["p2d_full_pass_candidate_count"] = lane_state[lane_index]["full_pass_count"]
        lane_report["search_tree_exhausted"] = bool(phase_rows) and all(
            bool(row["search_tree_exhausted"]) for row in phase_rows
        )
    construction_nodes = sum(
        int(phase["main_process_skeleton_generation"].get("construction_node_count", 0))
        for lane_report in lane_reports
        for phase in lane_report["phases"]
        if phase["search_phase"] == STRUCTURED_PHASE
    )
    tail_nodes = sum(
        int(phase["main_process_skeleton_generation"].get("tail_node_count", 0))
        for lane_report in lane_reports
        for phase in lane_report["phases"]
    )
    general_fallback_nodes = sum(
        int(phase["visited_nodes"])
        for lane_report in lane_reports
        for phase in lane_report["phases"]
        if phase["search_phase"] != STRUCTURED_PHASE
    )
    classified_node_total = construction_nodes + tail_nodes + general_fallback_nodes
    if classified_node_total != global_node_visits:
        raise _error(
            "PLACEMENT_NODE_ACCOUNTING_INCONSISTENT",
            global_node_visits=global_node_visits,
            classified_node_total=classified_node_total,
        )
    r6_topology_diagnostics["r11_budget_accounting"] = {
        "global_budget": placement_node_budget,
        "global_nodes_visited": global_node_visits,
        "global_nodes_remaining": global_node_budget_remaining,
        "construction_nodes": construction_nodes,
        "tail_nodes": tail_nodes,
        "general_fallback_nodes": general_fallback_nodes,
        "classified_node_total": classified_node_total,
        "global_node_visits_match_classified_total": True,
        "replayed_prefix_node_count": 0,
        "stranded_budget_allowed": False,
        "global_budget_exhausted": global_budget_exhausted,
        "nodes_by_work_item": {
            str(work_item_id): sum(
                int(row["nodes_visited"])
                for row in r6_topology_diagnostics["r11_scheduler_trace"]
                if row["work_item_id"] == work_item_id
            )
            for work_item_id in sorted(
                {str(row["work_item_id"]) for row in r6_topology_diagnostics["r11_scheduler_trace"]}
            )
        },
        "nodes_by_topology": {
            topology: sum(
                int(row["nodes_visited"])
                for row in r6_topology_diagnostics["r11_scheduler_trace"]
                if row["topology"] == topology
            )
            for topology in sorted(
                {str(row["topology"]) for row in r6_topology_diagnostics["r11_scheduler_trace"]}
            )
        },
        "nodes_by_round": {
            str(round_number): sum(
                int(row["nodes_visited"])
                for row in r6_topology_diagnostics["r11_scheduler_trace"]
                if row["round"] == round_number
            )
            for round_number in sorted(
                {int(row["round"]) for row in r6_topology_diagnostics["r11_scheduler_trace"]}
            )
        },
        "preflight_compute_nodes": 0,
        "work_round_count": scheduler_round,
        "active_work_item_count": sum(
            not state["enumeration"].completed for state in active_states
        ),
        "exhausted_work_item_count": sum(
            state["enumeration"].completed and state["enumeration"].search_tree_exhausted
            for state in phase_states
        ),
        "truncated_active_work_item_count": sum(
            not state["enumeration"].completed
            and state["status"] in {"ACTIVE", "QUANTUM_EXHAUSTED"}
            for state in active_states
        ),
        "unused_global_nodes_with_active_truncated_work": (
            global_node_budget_remaining
            if active_states and global_node_budget_remaining > 0
            else 0
        ),
        "early_stop_reason": (
            "GLOBAL_PLACEMENT_NODE_BUDGET_EXHAUSTED"
            if global_budget_exhausted
            else "ALL_ACTIVE_WORK_EXHAUSTED_OR_NORMAL_COMPLETION_LIMIT"
            if not active_states
            else "SCHEDULER_STOPPED_WITH_ACTIVE_WORK"
        ),
    }

    r6_topology_diagnostics["ownership_matrix"] = sorted(
        r6_topology_diagnostics["ownership_matrix"],
        key=lambda row: (
            str(row.get("skeleton_hash")),
            str(row.get("constructed_topology")),
        ),
    )
    r6_topology_diagnostics["ownership_duplicates"] = sorted(
        r6_topology_diagnostics.get("ownership_duplicates", []),
        key=lambda row: (
            str(row.get("skeleton_hash")),
            str(row.get("duplicate_discovery_topology")),
            str(row.get("canonical_topology_owner")),
        ),
    )
    r6_topology_diagnostics["construction_attempts"] = sorted(
        r6_topology_diagnostics["construction_attempts"],
        key=lambda row: (
            str(row.get("topology")),
            int(row.get("construction_attempt_index", 0)),
            tuple(row.get("sorting_root_mm", [])),
            str(row.get("raw_side")),
            str(row.get("finished_side")),
            str(row.get("offset_direction")),
        ),
    )
    r6_topology_diagnostics["constructive_divergence_trace"] = sorted(
        r6_topology_diagnostics["constructive_divergence_trace"],
        key=lambda row: (str(row.get("topology")), str(row.get("construction_policy"))),
    )
    r6_topology_diagnostics["offset_transition_trace"] = sorted(
        r6_topology_diagnostics["offset_transition_trace"],
        key=lambda row: (
            str(row.get("direction")),
            str(row.get("transition_stage")),
            tuple(row.get("raw_core_common_interval_mm", [])),
        ),
    )
    r6_topology_diagnostics["cross_topology_duplicate_geometry_trace"] = sorted(
        cross_topology_duplicate_trace,
        key=lambda row: (
            str(row.get("skeleton_hash")),
            str(row.get("first_discovery_topology")),
            str(row.get("duplicate_discovery_topology")),
        ),
    )
    r6_topology_diagnostics["cross_topology_duplicate_geometry_count"] = len(
        r6_topology_diagnostics["cross_topology_duplicate_geometry_trace"]
    )
    hub_duplicate_attempts = [
        row
        for row in r6_topology_diagnostics["ownership_duplicates"]
        if row.get("duplicate_discovery_topology") == CENTRAL_PROCESS_HUB
    ]
    hub_attempts = [
        row
        for row in r6_topology_diagnostics["construction_attempts"]
        if row.get("topology") == CENTRAL_PROCESS_HUB
    ]
    r6_topology_diagnostics["hub_search_continued_after_geometry_duplicate"] = any(
        any(
            int(attempt.get("construction_attempt_index", -1))
            > int(duplicate.get("construction_attempt_index", -1))
            for attempt in hub_attempts
        )
        for duplicate in hub_duplicate_attempts
    )
    r6_topology_diagnostics["global_unique_skeleton_geometry_count"] = len(
        global_skeleton_geometry_registry
    )
    r6_topology_diagnostics["geometry_evaluation_registry"] = [
        dict(row) for _, row in sorted(global_skeleton_geometry_registry.items())
    ]
    r6_topology_diagnostics["geometry_evaluation_admissions"] = sorted(
        r6_topology_diagnostics["geometry_evaluation_admissions"],
        key=lambda row: (
            str(row.get("skeleton_hash")),
            str(row.get("discovery_topology")),
        ),
    )
    r6_topology_diagnostics["tail_slot_preflight_trace"] = sorted(
        r6_topology_diagnostics["tail_slot_preflight_trace"],
        key=lambda row: (
            str(row.get("skeleton_hash")),
            str(row.get("discovery_topology")),
            str(row.get("event")),
        ),
    )
    r6_topology_diagnostics["main_skeleton_truck_preflight_trace"] = sorted(
        r6_topology_diagnostics["main_skeleton_truck_preflight_trace"],
        key=lambda row: (
            str(row.get("main_skeleton_hash")),
            str(row.get("discovery_topology")),
            str(row.get("event")),
        ),
    )

    best_record: (
        tuple[
            dict[str, Any], dict[str, Any], StructuralQualityFactsV1, StructuralCompositionFamilyV1
        ]
        | None
    ) = None
    for record in full_pass_records:
        if _record_is_better(record, best_record, preferred_loading_side):
            best_record = record

    structured_candidate_count = sum(
        int(record[2].to_dict().get("structurally_generated") is True)
        for record in full_pass_records
    )
    fallback_candidate_count = len(full_pass_records) - structured_candidate_count

    provenance = _selection_provenance(
        lane_reports,
        placement_node_budget=placement_node_budget,
        p2c_candidate_count=p2c_candidate_count,
        p2d_validated_count=p2d_validated_count,
        p2d_full_pass_count=p2d_full_pass_count,
        selected=best_record is not None,
    )
    search_provenance = provenance["p2c_candidate_enumeration"]
    if best_record is None:
        budget_exhausted = search_provenance["node_budget_exhausted"] is True
        warnings = [
            (
                "P2C candidate search budget exhausted before a P2D-full-pass placement was found; "
                "this is not a mathematical infeasibility proof."
                if budget_exhausted
                else "No P2D-full-pass candidate was found in the exhausted deterministic P2C "
                "candidate family; this is not a mathematical infeasibility proof."
            )
        ]
        payload: dict[str, Any] = {
            "identity": IDENTITY,
            "schema_version": SCHEMA_VERSION,
            "result_identity": RESULT_IDENTITY,
            "status": "VALIDATED_LAYOUT_SEARCH_EXHAUSTED",
            "validated_layout_selected": False,
            "selected_layout": None,
            "selected_p2c_candidate_hash": None,
            "selected_p2d_result_hash": None,
            "p2c_candidate_count": p2c_candidate_count,
            "p2d_validated_candidate_count": p2d_validated_count,
            "p2d_full_pass_candidate_count": p2d_full_pass_count,
            "candidate_validation_trace": trace,
            "selection_provenance": provenance,
            "search_provenance": search_provenance,
            "warnings": warnings,
            "route_objective_optimization_active": False,
            "project_layout_validated": False,
            "p2_complete": False,
            "layout_infeasible_proof_implemented": False,
            "requires_review": True,
        }
        return ValidatedPlacementSelectionResultV1(
            payload,
            {
                "identity": "p1a-structural-candidate-selection-evaluation@1.0.0",
                "selected": False,
                "selected_composition_family": None,
                "family_lanes": lane_reports,
                "structural_candidate_count": 0,
                "fallback_candidate_count": 0,
                "hard_feasibility_passed": False,
                "comparison_mode": "LEXICOGRAPHIC_ATOMIC_FACTS",
                "distinct_full_pass_family_count": 0,
                "r6_topology_diagnostics": r6_topology_diagnostics,
            },
        )

    assert best_record is not None
    best_candidate_body, best_routed_body, _, _ = best_record
    alternatives: list[
        tuple[
            dict[str, Any], dict[str, Any], StructuralQualityFactsV1, StructuralCompositionFamilyV1
        ]
    ] = []
    runner_up: (
        tuple[
            dict[str, Any], dict[str, Any], StructuralQualityFactsV1, StructuralCompositionFamilyV1
        ]
        | None
    ) = None
    for record in full_pass_records:
        if record is best_record:
            continue
        if _record_is_better(record, runner_up, preferred_loading_side):
            runner_up = record
    if runner_up is not None:
        alternatives.append(runner_up)
    structural_tie = bool(
        runner_up is not None and best_record[2].comparison_key == runner_up[2].comparison_key
    )
    business_comparison = (
        compare_placement_candidate_business_objectives(
            best_candidate_body, runner_up[0], preferred_loading_side
        )
        if runner_up is not None
        else 0
    )
    p2b2_tiebreak_used = structural_tie and business_comparison != 0
    canonical_json_tiebreak_used = False
    if runner_up is not None and structural_tie and business_comparison == 0:
        canonical_json_tiebreak_used = placement_candidate_canonical_tiebreak_key(
            best_candidate_body
        ) != placement_candidate_canonical_tiebreak_key(runner_up[0])
    internal_evaluation = _internal_selection_evaluation(
        best_record,
        alternatives,
        structured_candidate_count=structured_candidate_count,
        fallback_candidate_count=fallback_candidate_count,
        p2b2_tiebreak_used=p2b2_tiebreak_used,
        canonical_json_tiebreak_used=canonical_json_tiebreak_used,
        preferred_loading_side=preferred_loading_side,
        lane_reports=lane_reports,
        full_pass_records=full_pass_records,
        r6_topology_diagnostics=r6_topology_diagnostics,
    )
    payload = {
        "identity": IDENTITY,
        "schema_version": SCHEMA_VERSION,
        "result_identity": RESULT_IDENTITY,
        "status": "VALIDATED_LAYOUT_SELECTED",
        "validated_layout_selected": True,
        "selected_layout": best_routed_body,
        "selected_p2c_candidate_hash": best_candidate_body.get("canonical_candidate_hash"),
        "selected_p2d_result_hash": best_routed_body.get("canonical_result_hash"),
        "p2c_candidate_count": p2c_candidate_count,
        "p2d_validated_candidate_count": p2d_validated_count,
        "p2d_full_pass_candidate_count": p2d_full_pass_count,
        "candidate_validation_trace": trace,
        "selection_provenance": provenance,
        "search_provenance": search_provenance,
        "warnings": [
            (
                "Selected the highest-ranked P2C candidate among P2D-full-pass candidates "
                "within the exhausted deterministic candidate family."
                if search_provenance["search_tree_exhausted"]
                else "Selected the highest-ranked P2C candidate among deterministically "
                "explored P2D-full-pass candidates; the search-family optimum is not proven."
            )
        ],
        "route_objective_optimization_active": False,
        "project_layout_validated": True,
        "p2_complete": True,
        "requires_review": True,
    }
    return ValidatedPlacementSelectionResultV1(payload, internal_evaluation)


# This descriptive alias keeps the application boundary easy to discover in
# callers that phrase the operation as validation followed by selection.
validate_candidates_and_select_layout = select_validated_placement
