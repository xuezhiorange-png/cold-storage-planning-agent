"""Select a P2C placement only after P2D validation.

P2C owns deterministic placement candidate generation and its frozen
lexicographic objective.  P2D owns route, truck, access and final-layout
validation.  This application boundary is the only place that composes those
two responsibilities: every complete P2C candidate is passed through P2D,
and the highest-ranked P2C candidate among the P2D-full-pass candidates is
selected.
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
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.layout.domain.objective_profile import ObjectiveProfileV1
from cold_storage.modules.layout.domain.placement import (
    GENERAL_FALLBACK_PHASE,
    MIN_CONSTRUCTIVE_SKELETON_NODE_ALLOWANCE,
    STRUCTURED_PHASE,
    placement_candidate_is_better,
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
    return placement_candidate_is_better(candidate[0], best[0], preferred_loading_side)


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
    lane_reports: list[dict[str, Any]],
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
    winner_value: int | None = None
    runner_up_value: int | None = None
    if runner_up is not None:
        first_component = "P2B2_FINAL_TIE_BREAK" if p2b2_tiebreak_used else "STRUCTURAL_QUALITY_TIE"
        for index, component in enumerate(_STRUCTURAL_COMPONENTS):
            if index < len(selected_facts.comparison_key) and index < len(
                runner_up[2].comparison_key
            ):
                winner = selected_facts.comparison_key[index]
                other = runner_up[2].comparison_key[index]
                if winner != other:
                    first_component = component
                    winner_value = winner
                    runner_up_value = other
                    break
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
        if _record_is_better(record, current, "UNSPECIFIED"):
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
        if _record_is_better(record, distinct_runner_up, "UNSPECIFIED"):
            distinct_runner_up = record

    distinct_first_component = "ONLY_ONE_P2D_FULL_PASS_MAIN_SKELETON"
    distinct_winner_value: int | None = None
    distinct_runner_value: int | None = None
    if distinct_runner_up is not None:
        distinct_first_component = "P2B2_FINAL_TIE_BREAK"
        for index, component in enumerate(_STRUCTURAL_COMPONENTS):
            winner_key = selected[2].comparison_key
            runner_key = distinct_runner_up[2].comparison_key
            if (
                index < len(winner_key)
                and index < len(runner_key)
                and winner_key[index] != runner_key[index]
            ):
                distinct_first_component = component
                distinct_winner_value = winner_key[index]
                distinct_runner_value = runner_key[index]
                break
        else:
            if selected[2].comparison_key == distinct_runner_up[2].comparison_key:
                distinct_first_component = "P2B2_FINAL_TIE_BREAK"
            else:
                distinct_first_component = "STRUCTURAL_COMPARISON"

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
            str(lifecycle.get("topology"))
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
        "selected_p2d_result_hash": selected[1].get("canonical_result_hash"),
        "selected_structural_facts": selected_payload,
        "structural_candidate_count": structured_candidate_count,
        "fallback_candidate_count": fallback_candidate_count,
        "structural_fallback_used": not selected_structured,
        "runner_up_present": runner_up is not None,
        "runner_up_candidate_hash": runner_up[0].get("canonical_candidate_hash")
        if runner_up is not None
        else None,
        "runner_up_structural_facts": runner_up[2].to_dict() if runner_up is not None else None,
        "first_decisive_component": first_component,
        "winner_value": winner_value,
        "runner_up_value": runner_up_value,
        "search_policy": "STAGED_COVERAGE_THEN_PREFERENCE",
        "topology_count_explored": topology_count_explored,
        "topology_count_with_constructed_skeleton": topology_count_constructed,
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
        "p2b2_tiebreak_used": p2b2_tiebreak_used,
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
    skeleton_lifecycle_by_hash: dict[tuple[str, str], dict[str, Any]] = {}
    topology_lanes = _selector_topology_lanes(site_body, p1_handoff)
    preferred_family = _preferred_family_from_handoff(site_body, p1_handoff)
    preferred_lane_index = _preferred_topology_index(topology_lanes, preferred_family)
    lane_budgets = _family_lane_budgets(
        placement_node_budget,
        len(topology_lanes),
        preferred_lane_index=preferred_lane_index,
    )
    topology_coverage_budget = min(
        MIN_CONSTRUCTIVE_SKELETON_NODE_ALLOWANCE,
        placement_node_budget // len(topology_lanes),
    )
    lane_order = tuple(
        index for index in range(len(topology_lanes)) if index != preferred_lane_index
    ) + ((preferred_lane_index,) if preferred_lane_index is not None else ())
    p2c_candidate_count = 0
    candidate_index = 0

    for lane_index in lane_order:
        lane = topology_lanes[lane_index]
        family = lane.family
        lane_budget = lane_budgets[lane_index]
        structured_budget, fallback_budget = _lane_budget_split(lane_budget)
        lane_seen_geometry: set[str] = set()
        lane_full_pass_count = 0
        lane_report: dict[str, Any] = {
            "composition_family": family.to_dict(),
            "topology": lane.topology,
            "scheduler_policy": "STAGED_COVERAGE_THEN_PREFERENCE",
            "topology_coverage_node_budget": topology_coverage_budget,
            "diversity_expansion_node_budget": max(
                0,
                lane_budget
                - topology_coverage_budget
                - int(
                    preferred_family is not None
                    and lane_index == preferred_lane_index
                    and (placement_node_budget - topology_coverage_budget * len(topology_lanes))
                    % len(topology_lanes)
                    > 0
                ),
            ),
            "preference_extra_node_budget": (
                int(
                    preferred_family is not None
                    and lane_index == preferred_lane_index
                    and (placement_node_budget - topology_coverage_budget * len(topology_lanes))
                    % len(topology_lanes)
                    > 0
                )
                if preferred_lane_index is not None
                else 0
            ),
            "preferred_lane": preferred_family is not None and lane_index == preferred_lane_index,
            "lane_node_budget": lane_budget,
            "structured_node_budget": structured_budget,
            "fallback_node_budget": fallback_budget,
            "phases": [],
            "p2d_full_pass_candidate_count": 0,
            "p2d_rejected_candidate_count": 0,
            "p2d_rejection_warnings": [],
        }

        phase_budgets = [(STRUCTURED_PHASE, structured_budget)]
        phase_index = 0
        while phase_index < len(phase_budgets):
            phase, phase_budget = phase_budgets[phase_index]
            phase_index += 1
            if phase == GENERAL_FALLBACK_PHASE and lane_full_pass_count:
                break
            enumeration = enumerate_placement_candidates(
                canonical_zone_plan,
                p1_handoff,
                site_geometry,
                objective_profile,
                node_budget=phase_budget,
                complete_candidate_limit=complete_candidate_limit,
                structural_family=family,
                structural_topology=lane.topology,
                search_phase=phase,
            )
            phase_full_pass_count = 0
            phase_rejected_count = 0
            phase_candidate_count = 0
            structural_flag_getter = getattr(enumeration, "structurally_generated", None)
            for candidate in enumeration.iter_candidates():
                candidate_body = candidate.to_dict()
                candidate_hash = candidate_body.get("canonical_candidate_hash")
                skeleton_hash_getter = getattr(
                    enumeration, "candidate_main_process_skeleton_hash", None
                )
                topology_getter = getattr(enumeration, "candidate_topology", None)
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
                geometry_signature = _placement_geometry_signature(candidate_body)
                if geometry_signature in lane_seen_geometry:
                    continue
                lane_seen_geometry.add(geometry_signature)
                phase_candidate_count += 1
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
                    lifecycle_key = (lane.topology, skeleton_hash)
                    lifecycle = skeleton_lifecycle_by_hash.setdefault(
                        lifecycle_key,
                        {
                            "topology": lane.topology,
                            "skeleton_hash": skeleton_hash,
                            "p2d_reached": True,
                            "p2d_candidate_count": 0,
                            "p2d_full_pass_count": 0,
                            "first_failure_stage": None,
                            "first_failure_reason": None,
                        },
                    )
                    lifecycle["p2d_candidate_count"] += 1
                    if full_pass:
                        lifecycle["p2d_full_pass_count"] += 1
                    elif lifecycle["first_failure_stage"] is None:
                        lifecycle["first_failure_stage"] = "P2D"
                        warnings = routed_body.get("warnings")
                        lifecycle["first_failure_reason"] = (
                            warnings[0]
                            if isinstance(warnings, list) and warnings
                            else "P2D_HARD_VALIDATION_FAILED"
                        )
                trace.append(_p2d_trace_row(candidate_index, candidate_body, p2d_body=routed_body))
                if not full_pass:
                    phase_rejected_count += 1
                    for warning in routed_body.get("warnings", []):
                        if (
                            isinstance(warning, str)
                            and warning not in lane_report["p2d_rejection_warnings"]
                        ):
                            lane_report["p2d_rejection_warnings"].append(warning)
                    continue
                phase_full_pass_count += 1
                lane_full_pass_count += 1
                p2d_full_pass_count += 1
                candidate_hash = candidate_body.get("canonical_candidate_hash")
                structurally_generated = bool(
                    phase == STRUCTURED_PHASE
                    and callable(structural_flag_getter)
                    and isinstance(candidate_hash, str)
                    and structural_flag_getter(candidate_hash)
                )
                try:
                    structural_facts = build_structural_quality_facts(
                        candidate_body,
                        routed_body,
                        site_body,
                        family,
                        structurally_generated=structurally_generated,
                        search_phase=phase,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise _error(
                        "STRUCTURAL_QUALITY_FACTS_UNAVAILABLE",
                        candidate_index=candidate_index,
                        reason=type(exc).__name__,
                    ) from None
                full_pass_records.append((candidate_body, routed_body, structural_facts, family))

            generation_report = getattr(enumeration, "skeleton_generation_report", {})
            if isinstance(generation_report, Mapping):
                generation_report = dict(generation_report)
                lifecycle_rows = generation_report.get("skeleton_tail_lifecycle", [])
                enriched_lifecycle: list[dict[str, Any]] = []
                for lifecycle_row in lifecycle_rows if isinstance(lifecycle_rows, list) else []:
                    if not isinstance(lifecycle_row, Mapping):
                        continue
                    lifecycle_copy = dict(lifecycle_row)
                    skeleton_hash_value = lifecycle_copy.get("skeleton_hash")
                    p2d_lifecycle = skeleton_lifecycle_by_hash.get(
                        (lane.topology, str(skeleton_hash_value)), {}
                    )
                    lifecycle_copy["p2d_reached"] = p2d_lifecycle.get("p2d_reached", False)
                    lifecycle_copy["p2d_candidate_count"] = p2d_lifecycle.get(
                        "p2d_candidate_count", 0
                    )
                    lifecycle_copy["p2d_full_pass_count"] = p2d_lifecycle.get(
                        "p2d_full_pass_count", 0
                    )
                    if lifecycle_copy["p2d_reached"] and not lifecycle_copy["p2d_full_pass_count"]:
                        lifecycle_copy["first_failure_stage"] = "P2D"
                        lifecycle_copy["first_failure_reason"] = p2d_lifecycle.get(
                            "first_failure_reason", "P2D_HARD_VALIDATION_FAILED"
                        )
                    elif not lifecycle_copy["p2d_reached"]:
                        lifecycle_copy["first_failure_stage"] = "TAIL_SEARCH"
                        lifecycle_copy["first_failure_reason"] = (
                            "TAIL_NODE_SHARE_EXHAUSTED_WITHOUT_COMPLETE_P2C_CANDIDATE"
                            if lifecycle_copy.get("tail_nodes", 0)
                            >= lifecycle_copy.get("tail_node_limit", 0)
                            else "TAIL_SEARCH_COMPLETED_WITHOUT_COMPLETE_P2C_CANDIDATE"
                        )
                    enriched_lifecycle.append(lifecycle_copy)
                generation_report["skeleton_tail_lifecycle"] = enriched_lifecycle
            lane_report["phases"].append(
                {
                    "search_phase": phase,
                    "node_budget": phase_budget,
                    "visited_nodes": enumeration.visited_node_count,
                    "complete_candidates": enumeration.candidate_count,
                    "distinct_main_process_skeleton_count": int(
                        getattr(enumeration, "distinct_main_process_skeleton_count", 0)
                    ),
                    "distinct_structural_core_root_count": int(
                        getattr(enumeration, "distinct_structural_core_root_count", 0)
                    ),
                    "validated_unique_candidates": phase_candidate_count,
                    "p2d_rejected_candidate_count": phase_rejected_count,
                    "p2d_full_pass_candidate_count": phase_full_pass_count,
                    "node_budget_exhausted": enumeration.node_budget_exhausted,
                    "search_tree_exhausted": enumeration.search_tree_exhausted,
                    "main_process_skeleton_generation": generation_report,
                }
            )
            if (
                phase == STRUCTURED_PHASE
                and lane_full_pass_count == 0
                and enumeration.search_tree_exhausted
            ):
                unused_lane_budget = max(0, lane_budget - enumeration.visited_node_count)
                if unused_lane_budget:
                    fallback_budget = unused_lane_budget
                    lane_report["fallback_node_budget"] = fallback_budget
                    phase_budgets.append((GENERAL_FALLBACK_PHASE, fallback_budget))
            if phase == GENERAL_FALLBACK_PHASE and lane_full_pass_count == 0:
                break

        lane_report["p2d_full_pass_candidate_count"] = lane_full_pass_count
        lane_report["p2d_rejected_candidate_count"] = sum(
            row["p2d_rejected_candidate_count"] for row in lane_report["phases"]
        )
        lane_report["visited_nodes"] = sum(row["visited_nodes"] for row in lane_report["phases"])
        lane_report["complete_candidates"] = sum(
            row["complete_candidates"] for row in lane_report["phases"]
        )
        lane_report["node_budget_exhausted"] = any(
            row["node_budget_exhausted"] for row in lane_report["phases"]
        )
        lane_report["search_tree_exhausted"] = all(
            row["search_tree_exhausted"] for row in lane_report["phases"]
        )
        lane_reports.append(lane_report)

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
    p2b2_tiebreak_used = bool(
        runner_up is not None
        and best_record[2].comparison_key == runner_up[2].comparison_key
        and placement_candidate_is_better(best_candidate_body, runner_up[0], preferred_loading_side)
    )
    internal_evaluation = _internal_selection_evaluation(
        best_record,
        alternatives,
        structured_candidate_count=structured_candidate_count,
        fallback_candidate_count=fallback_candidate_count,
        p2b2_tiebreak_used=p2b2_tiebreak_used,
        lane_reports=lane_reports,
        full_pass_records=full_pass_records,
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
