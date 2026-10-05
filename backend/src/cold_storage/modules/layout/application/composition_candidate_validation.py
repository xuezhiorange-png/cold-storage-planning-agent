"""Replay and validate one composition-native placement through existing P2D."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from cold_storage.modules.layout.application.access_routing import route_site_placement
from cold_storage.modules.layout.application.composition_placement import (
    enumerate_composition_placements,
)
from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.application.layout_authority_binding import (
    bind_layout_authority,
)
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.application.structural_composition import (
    StructuralCompositionEnumerationResultV1,
    build_structural_compositions,
)
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.composition_placement import (
    DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET,
    CompositionPlacementCandidateV1,
)
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.layout.domain.objective_profile import approved_objective_profile
from cold_storage.modules.layout.domain.placement import (
    PLACEMENT_RESULT_IDENTITY,
    SitePlacementResultV1,
    _loading_face,
    _zone_record,
)
from cold_storage.modules.layout.domain.placement import (
    SCHEMA_VERSION as PLACEMENT_SCHEMA_VERSION,
)
from cold_storage.modules.layout.domain.site_geometry import (
    rectangles_share_positive_edge,
)
from cold_storage.modules.layout.domain.truck_maneuver import BoundTruckManeuverProjectInputV1

IDENTITY = "composition-candidate-hard-validation@1.0.0"
SCHEMA_VERSION = "1.0.0"
_CANDIDATE_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


@dataclass(frozen=True, init=False)
class CompositionCandidateValidationResultV1:
    """Auditable bridge result retaining the unchanged downstream P2D body."""

    payload_json: str
    _content_hash: str

    def __init__(self, payload: Mapping[str, Any]) -> None:
        content = dict(payload)
        content.pop("canonical_result_hash", None)
        normalized = canonical_json(content)
        object.__setattr__(self, "payload_json", normalized)
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


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _select_replayed_candidate(
    candidates: tuple[CompositionPlacementCandidateV1, ...], candidate_hash: str
) -> CompositionPlacementCandidateV1:
    if (
        not isinstance(candidate_hash, str)
        or _CANDIDATE_HASH_PATTERN.fullmatch(candidate_hash) is None
    ):
        raise _error("COMPOSITION_CANDIDATE_REFERENCE_INVALID")
    matches = [
        candidate for candidate in candidates if candidate.canonical_result_hash == candidate_hash
    ]
    if len(matches) != 1:
        raise _error(
            "COMPOSITION_CANDIDATE_REPLAY_MISMATCH",
            candidate_hash=candidate_hash,
            replay_match_count=len(matches),
        )
    return matches[0]


def _validate_composition_provenance(
    candidate: CompositionPlacementCandidateV1,
    *,
    composition_result: StructuralCompositionEnumerationResultV1,
    source_zone_plan_hash: str,
    source_p1_handoff_hash: str,
    source_site_geometry_hash: str,
) -> None:
    matches = [
        plan
        for plan in composition_result.compositions
        if plan.identity == candidate.composition_identity
        and plan.signature.key == candidate.composition_signature
        and plan.family == candidate.family
        and plan.process_axis == candidate.process_axis
        and plan.process_direction == candidate.process_direction
    ]
    if (
        len(matches) != 1
        or candidate.source_zone_plan_hash != source_zone_plan_hash
        or candidate.source_p1_handoff_hash != source_p1_handoff_hash
        or candidate.source_site_geometry_hash != source_site_geometry_hash
        or candidate.zone_count != len(ZONE_CODES)
        or not candidate.hard_constraints_passed
        or not candidate.composition_intent_preserved
    ):
        raise _error("COMPOSITION_CANDIDATE_PROVENANCE_MISMATCH")


def _geometry_by_role(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[Decimal | int, ...]]:
    result: dict[str, tuple[Decimal | int, ...]] = {}
    for row in rows:
        result[str(row["zone_code"])] = (
            Decimal(str(row["x"])),
            Decimal(str(row["y"])),
            Decimal(str(row["width_m"])),
            Decimal(str(row["depth_m"])),
            int(row["rotation_deg"]),
        )
    return result


def _adapt_candidate_to_existing_placement(
    candidate: CompositionPlacementCandidateV1,
    *,
    dimension_authorities: Mapping[str, Mapping[str, Any]],
    site_body: Mapping[str, Any],
    source_zone_plan_hash: str,
    source_p1_handoff_hash: str,
    source_site_geometry_hash: str,
) -> SitePlacementResultV1:
    """Adapt exact candidate representation only; no geometry search or repair."""
    by_role = {zone.zone_code: zone for zone in candidate.zones}
    if len(by_role) != len(candidate.zones) or set(by_role) != set(ZONE_CODES):
        raise _error("COMPOSITION_CANDIDATE_ROLE_SET_MISMATCH")

    graph = process_graph()
    satisfied = [
        [first, second]
        for first, second in graph.must_adjacencies
        if rectangles_share_positive_edge(by_role[first], by_role[second])
    ]
    if len(satisfied) != len(graph.must_adjacencies):
        raise _error("COMPOSITION_CANDIDATE_MUST_ADJACENCY_MISMATCH")

    zones = [_zone_record(dimension_authorities[role], by_role[role]) for role in sorted(by_role)]
    if _geometry_by_role(zones) != _geometry_by_role(
        [by_role[role].to_dict() for role in sorted(by_role)]
    ):
        raise _error("COMPOSITION_CANDIDATE_ADAPTER_GEOMETRY_CHANGED")

    side, segment, _loading_score, _comparison = _loading_face(
        by_role["shipping_channel"], site_body
    )
    loading_segment = {
        "start": {"x": Decimal(segment[0][0]) / 1000, "y": Decimal(segment[0][1]) / 1000},
        "end": {"x": Decimal(segment[1][0]) / 1000, "y": Decimal(segment[1][1]) / 1000},
    }
    payload = {
        "schema_version": PLACEMENT_SCHEMA_VERSION,
        "placement_result_identity": PLACEMENT_RESULT_IDENTITY,
        "source_zone_plan_hash": source_zone_plan_hash,
        "source_p1_handoff_hash": source_p1_handoff_hash,
        "source_site_geometry_hash": source_site_geometry_hash,
        # P2D requires this existing P2C envelope field. No objective is scored
        # or used to rank/select a composition-native candidate here.
        "source_objective_profile_hash": approved_objective_profile().canonical_result_hash,
        "zone_count": len(zones),
        "placement_access_requirement_count": 12,
        "zones": zones,
        "shipping_loading_face_side": side,
        "shipping_loading_face_segment": loading_segment,
        "must_adjacency_evaluation": {
            "hard_constraints_passed": True,
            "satisfied_count": len(satisfied),
            "required_count": len(graph.must_adjacencies),
            "satisfied_pairs": satisfied,
            "violations": [],
        },
        "placement_hard_constraints_passed": True,
        "composition_native_provenance": {
            "candidate_hash": candidate.canonical_result_hash,
            "composition_identity": candidate.composition_identity,
            "composition_signature": candidate.composition_signature,
            "family": candidate.family.value,
            "process_axis": candidate.process_axis.value,
            "process_direction": candidate.process_direction.value,
            "source_zone_plan_hash": source_zone_plan_hash,
            "source_p1_handoff_hash": source_p1_handoff_hash,
            "source_site_geometry_hash": source_site_geometry_hash,
        },
        "search_provenance": {
            "algorithm": "COMPOSITION_NATIVE_EXACT_PLACEMENT",
            "legacy_candidate_search_used": False,
            "geometry_repair_performed": False,
        },
    }
    return SitePlacementResultV1.from_payload(payload)


def _failure_stage(validation: Mapping[str, Any], access_fail_count: int) -> str:
    if access_fail_count:
        return "ACCESS"
    if validation.get("truck_route_validated") is not True:
        return "TRUCK"
    interaction = validation.get("personnel_truck_evaluation")
    if not isinstance(interaction, Mapping) or interaction.get("status") != "PASS":
        return "PERSONNEL_TRUCK_INTERACTION"
    if validation.get("building_footprint") is None:
        return "BUILDING_FOOTPRINT"
    if validation.get("p2_complete") is not True:
        return "P2D"
    return "NONE"


def _failure_codes(validation: Mapping[str, Any]) -> list[str]:
    codes: set[str] = {str(code) for code in validation.get("warnings", [])}
    access_results = validation.get("access_results", [])
    if isinstance(access_results, list):
        for result in access_results:
            if not isinstance(result, Mapping) or result.get("status") == "PASS":
                continue
            for key in ("code", "failure_code", "status"):
                value = result.get(key)
                if isinstance(value, str) and value:
                    codes.add(value)
            values = result.get("codes", [])
            if isinstance(values, list):
                codes.update(str(value) for value in values)
    truck_codes = validation.get("truck_route_codes", [])
    if isinstance(truck_codes, list):
        codes.update(str(value) for value in truck_codes)
    interaction = validation.get("personnel_truck_evaluation")
    if isinstance(interaction, Mapping):
        values = interaction.get("codes", [])
        if isinstance(values, list):
            codes.update(str(value) for value in values)
        values = interaction.get("warnings", [])
        if isinstance(values, list):
            codes.update(str(value) for value in values)
    return sorted(code for code in codes if code)


def validate_composition_candidate(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: ZoneDimensioningResultV1 | Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    truck_maneuver_binding: BoundTruckManeuverProjectInputV1 | Mapping[str, Any],
    candidate_hash: str,
    *,
    placement_node_budget: int = DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET,
    route_node_budget: int = 20_000,
    truck_node_budget: int = 20_000,
) -> CompositionCandidateValidationResultV1:
    """Replay one server-produced candidate and run the existing complete P2D chain.

    The public boundary accepts only a hash reference, never a caller-created
    candidate object or geometry payload. It performs exactly one P2D call and
    never changes room geometry after replay.
    """
    if (
        not isinstance(candidate_hash, str)
        or _CANDIDATE_HASH_PATTERN.fullmatch(candidate_hash) is None
    ):
        raise _error("COMPOSITION_CANDIDATE_REFERENCE_INVALID")
    binding = bind_layout_authority(canonical_zone_plan, p1_handoff, site_geometry)
    placement_replay = enumerate_composition_placements(
        canonical_zone_plan,
        p1_handoff,
        site_geometry,
        node_budget=placement_node_budget,
    )
    candidate = _select_replayed_candidate(placement_replay.placements.candidates, candidate_hash)
    composition_replay = build_structural_compositions(
        canonical_zone_plan, p1_handoff, site_geometry
    )
    _validate_composition_provenance(
        candidate,
        composition_result=composition_replay,
        source_zone_plan_hash=binding.canonical_zone_plan_hash,
        source_p1_handoff_hash=binding.p1_handoff_hash,
        source_site_geometry_hash=binding.site_geometry_hash,
    )
    site_body = site_geometry.to_dict()
    adapted = _adapt_candidate_to_existing_placement(
        candidate,
        dimension_authorities=binding.dimension_authorities,
        site_body=site_body,
        source_zone_plan_hash=binding.canonical_zone_plan_hash,
        source_p1_handoff_hash=binding.p1_handoff_hash,
        source_site_geometry_hash=binding.site_geometry_hash,
    )
    adapted_body = adapted.to_dict()
    routed = route_site_placement(
        canonical_zone_plan,
        p1_handoff,
        site_geometry,
        adapted,
        truck_maneuver_binding,
        route_node_budget=route_node_budget,
        truck_node_budget=truck_node_budget,
    )
    validation = routed.to_dict()
    access_results = validation.get("access_results", [])
    if not isinstance(access_results, list):
        raise _error("P2D_ACCESS_RESULT_INVALID")
    access_requirement_count = int(validation.get("access_requirement_count", 0))
    access_pass_count = sum(
        isinstance(row, Mapping) and row.get("status") == "PASS" for row in access_results
    )
    access_fail_count = access_requirement_count - access_pass_count
    candidate_geometry = _geometry_by_role([zone.to_dict() for zone in candidate.zones])
    validated_geometry = _geometry_by_role(cast(list[Mapping[str, Any]], validation["zones"]))
    if candidate_geometry != validated_geometry:
        raise _error("COMPOSITION_CANDIDATE_GEOMETRY_CHANGED_DURING_VALIDATION")

    payload = {
        "identity": IDENTITY,
        "schema_version": SCHEMA_VERSION,
        "implementation_result": "PASS",
        "candidate_validation_result": "PASS"
        if validation.get("p2_complete") is True
        else f"FAIL_{_failure_stage(validation, access_fail_count)}",
        "candidate_hash": candidate.canonical_result_hash,
        "candidate_geometry_hash": canonical_hash(
            [zone.to_dict() for zone in sorted(candidate.zones, key=lambda item: item.zone_code)]
        ),
        "composition_identity": candidate.composition_identity,
        "composition_signature": candidate.composition_signature,
        "family": candidate.family.value,
        "process_axis": candidate.process_axis.value,
        "process_direction": candidate.process_direction.value,
        "source_zone_plan_hash": binding.canonical_zone_plan_hash,
        "source_p1_handoff_hash": binding.p1_handoff_hash,
        "source_site_geometry_hash": binding.site_geometry_hash,
        "server_side_candidate_replay_enforced": True,
        "caller_forged_composition_candidate_accepted": False,
        "validated_composition_candidate_count": len(placement_replay.placements.candidates),
        "composition_placement_node_budget": placement_replay.placements.node_budget,
        "composition_placement_nodes_used": placement_replay.placements.nodes_used,
        "composition_placement_replay_hash": canonical_hash(placement_replay.placements.to_dict()),
        "composition_candidate": candidate.to_dict(),
        "composition_placement_search_summary": {
            "family_coverage_order": list(placement_replay.placements.family_coverage_order),
            "family_first_round_complete": (
                placement_replay.placements.family_first_round_complete
            ),
            "attempt_count_by_family": dict(placement_replay.placements.attempt_count_by_family),
            "nodes_used_by_family": dict(placement_replay.placements.nodes_used_by_family),
            "candidate_count_by_family": {
                family: sum(
                    item.family.value == family for item in placement_replay.placements.candidates
                )
                for family in placement_replay.placements.family_coverage_order
            },
        },
        "s3_placement_search_behavior_changed": False,
        "adapter_used": True,
        "adapter_geometry_changed": False,
        "adapter_dimension_changed": False,
        "adapter_role_set_changed": False,
        "adapter_provenance_preserved": True,
        "adapter_placement_result_hash": adapted.canonical_result_hash,
        "adapter_placement_result": adapted_body,
        "existing_access_authority_used": True,
        "access_routing_performed": True,
        "access_requirement_count": access_requirement_count,
        "access_pass_count": access_pass_count,
        "access_fail_count": access_fail_count,
        "access_failure_codes": sorted(
            {
                str(code)
                for row in access_results
                if isinstance(row, Mapping) and row.get("status") != "PASS"
                for code in (
                    row.get("code"),
                    row.get("failure_code"),
                    row.get("status"),
                    *(row.get("codes", []) if isinstance(row.get("codes"), list) else []),
                )
                if isinstance(code, str) and code
            }
        ),
        "portal_validation_performed": access_requirement_count == 12 and len(access_results) == 12,
        "existing_truck_authority_used": True,
        "truck_validation_performed": validation.get("truck_route_status") is not None,
        "truck_route_validated": validation.get("truck_route_validated") is True,
        "truck_route_status": validation.get("truck_route_status"),
        "truck_route_codes": validation.get("truck_route_codes", []),
        "loading_face_validated": True,
        "personnel_truck_status": (
            validation.get("personnel_truck_evaluation", {}).get("status")
            if isinstance(validation.get("personnel_truck_evaluation"), Mapping)
            else "UNAVAILABLE"
        ),
        "existing_p2d_authority_used": True,
        "p2d_performed": True,
        "building_footprint_derived_by_existing_authority": (
            validation.get("building_footprint") is not None
        ),
        "project_layout_validated": validation.get("project_layout_validated") is True,
        "p2_complete": validation.get("p2_complete") is True,
        "p2d_result_hash": routed.canonical_result_hash,
        "failure_stage": _failure_stage(validation, access_fail_count),
        "failure_codes": _failure_codes(validation),
        "no_geometry_repair_performed": True,
        "global_infeasibility_proven": False,
        "existing_validation_result": validation,
    }
    return CompositionCandidateValidationResultV1(payload)
