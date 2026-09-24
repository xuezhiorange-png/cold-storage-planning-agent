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
from cold_storage.modules.layout.domain.placement import placement_candidate_is_better
from cold_storage.modules.layout.domain.structural_composition import (
    StructuralCompositionFamilyV1,
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
    row.update(
        {
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


def _selection_provenance(
    enumeration: Any,
    *,
    p2d_validated_count: int,
    p2d_full_pass_count: int,
    selected: bool,
) -> dict[str, Any]:
    search_provenance = enumeration.provenance
    return {
        "identity": IDENTITY,
        "selection_basis": P2C_CANDIDATE_SELECTION_BASIS,
        "p2c_candidate_enumeration": search_provenance,
        "p2c_candidate_count": enumeration.candidate_count,
        "p2d_validated_candidate_count": p2d_validated_count,
        "p2d_full_pass_candidate_count": p2d_full_pass_count,
        "selected_candidate": selected,
        "objective_optimal_within_search_family": (selected and enumeration.search_tree_exhausted),
        "route_objective_optimization_active": False,
        "p4_candidate_selection": False,
        "no_mathematical_infeasibility_proof": True,
    }


def _record_is_better(
    candidate: tuple[dict[str, Any], dict[str, Any], StructuralQualityFactsV1],
    best: tuple[dict[str, Any], dict[str, Any], StructuralQualityFactsV1] | None,
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
    "COMPOSITION_FAMILY_MATCH",
    "RAW_SIDE_GROUPING",
    "PROCESSING_CORE_GROUPING",
    "FINISHED_SIDE_GROUPING",
    "SUPPORT_GROUPING",
    "PERSONNEL_GROUPING",
    "PROCESS_CORE_LEGIBILITY",
    "AUTHORITATIVE_SUPPORT_ROUTE_COUNT",
    "SUPPORT_BRANCH_DIRECT_EDGE_COUNT",
    "PERSONNEL_PERIPHERAL_BOUNDARY_CONTACTS",
    "MAJOR_AXIS_ALIGNMENT_INCIDENCES",
    "DEPTH_ALIGNMENT_ELIGIBLE_PAIRS",
    "BUILDING_OUTLINE_CLASS",
)


def _internal_selection_evaluation(
    selected: tuple[dict[str, Any], dict[str, Any], StructuralQualityFactsV1],
    alternatives: list[tuple[dict[str, Any], dict[str, Any], StructuralQualityFactsV1]],
    *,
    family: StructuralCompositionFamilyV1,
    structured_candidate_count: int,
    fallback_candidate_count: int,
    p2b2_tiebreak_used: bool,
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
    selected_payload = selected_facts.to_dict()
    selected_structured = selected_payload.get("structurally_generated") is True
    return {
        "identity": "p1a-structural-candidate-selection-evaluation@1.0.0",
        "selection_basis": P2C_CANDIDATE_SELECTION_BASIS,
        "selected_composition_family": family.to_dict(),
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
        "p2b2_tiebreak_used": p2b2_tiebreak_used,
        "hard_feasibility_passed": True,
        "comparison_mode": "LEXICOGRAPHIC_ATOMIC_FACTS",
        "route_objective_optimization_active": False,
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
    enumeration = enumerate_placement_candidates(
        canonical_zone_plan,
        p1_handoff,
        site_geometry,
        objective_profile,
        node_budget=placement_node_budget,
        complete_candidate_limit=complete_candidate_limit,
    )
    site_body = site_geometry.to_dict()
    site = site_body.get("site")
    if not isinstance(site, Mapping) or not isinstance(site.get("preferred_loading_side"), str):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="preferred_loading_side")
    preferred_loading_side = str(site["preferred_loading_side"])

    trace: list[dict[str, Any]] = []
    p2d_validated_count = 0
    p2d_full_pass_count = 0
    full_pass_records: list[tuple[dict[str, Any], dict[str, Any], StructuralQualityFactsV1]] = []
    family = getattr(enumeration, "structural_composition_family", None)
    if not isinstance(family, StructuralCompositionFamilyV1):
        raise _error("STRUCTURAL_COMPOSITION_FAMILY_UNAVAILABLE")
    structural_flag_getter = getattr(enumeration, "structurally_generated", None)

    for candidate_index, candidate in enumerate(enumeration.iter_candidates(), start=1):
        candidate_body = candidate.to_dict()
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
        trace.append(_p2d_trace_row(candidate_index, candidate_body, p2d_body=routed_body))
        if not full_pass:
            continue
        p2d_full_pass_count += 1
        candidate_hash = candidate_body.get("canonical_candidate_hash")
        structurally_generated = bool(
            structural_flag_getter(candidate_hash)
            if callable(structural_flag_getter) and isinstance(candidate_hash, str)
            else False
        )
        try:
            structural_facts = build_structural_quality_facts(
                candidate_body,
                routed_body,
                site_body,
                family,
                structurally_generated=structurally_generated,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _error(
                "STRUCTURAL_QUALITY_FACTS_UNAVAILABLE",
                candidate_index=candidate_index,
                reason=type(exc).__name__,
            ) from None
        full_pass_records.append((candidate_body, routed_body, structural_facts))

    best_record: tuple[dict[str, Any], dict[str, Any], StructuralQualityFactsV1] | None = None
    for record in full_pass_records:
        if _record_is_better(record, best_record, preferred_loading_side):
            best_record = record

    structured_candidate_count = sum(
        int(record[2].to_dict().get("structurally_generated") is True)
        for record in full_pass_records
    )
    fallback_candidate_count = len(full_pass_records) - structured_candidate_count

    provenance = _selection_provenance(
        enumeration,
        p2d_validated_count=p2d_validated_count,
        p2d_full_pass_count=p2d_full_pass_count,
        selected=best_record is not None,
    )
    if best_record is None:
        warnings = [
            (
                "P2C candidate search budget exhausted before a P2D-full-pass placement was found; "
                "this is not a mathematical infeasibility proof."
                if enumeration.node_budget_exhausted
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
            "p2c_candidate_count": enumeration.candidate_count,
            "p2d_validated_candidate_count": p2d_validated_count,
            "p2d_full_pass_candidate_count": p2d_full_pass_count,
            "candidate_validation_trace": trace,
            "selection_provenance": provenance,
            "search_provenance": enumeration.provenance,
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
                "selected_composition_family": family.to_dict(),
                "structural_candidate_count": 0,
                "fallback_candidate_count": 0,
                "hard_feasibility_passed": False,
                "comparison_mode": "LEXICOGRAPHIC_ATOMIC_FACTS",
            },
        )

    assert best_record is not None
    best_candidate_body, best_routed_body, _ = best_record
    alternatives: list[tuple[dict[str, Any], dict[str, Any], StructuralQualityFactsV1]] = []
    runner_up: tuple[dict[str, Any], dict[str, Any], StructuralQualityFactsV1] | None = None
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
        family=family,
        structured_candidate_count=structured_candidate_count,
        fallback_candidate_count=fallback_candidate_count,
        p2b2_tiebreak_used=p2b2_tiebreak_used,
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
        "p2c_candidate_count": enumeration.candidate_count,
        "p2d_validated_candidate_count": p2d_validated_count,
        "p2d_full_pass_candidate_count": p2d_full_pass_count,
        "candidate_validation_trace": trace,
        "selection_provenance": provenance,
        "search_provenance": enumeration.provenance,
        "warnings": [
            (
                "Selected the highest-ranked P2C candidate among P2D-full-pass candidates "
                "within the exhausted deterministic candidate family."
                if enumeration.search_tree_exhausted
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
