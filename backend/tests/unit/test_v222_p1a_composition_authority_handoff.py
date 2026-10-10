"""P1-S2 binds composition to current authorities and emits intent-only handoffs."""

from __future__ import annotations

import inspect
import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.application.p1_project_handoff import build_p1_project_handoff
from cold_storage.modules.layout.application.site_geometry import (
    ValidatedSiteGeometryV1,
    validate_site_geometry,
)
from cold_storage.modules.layout.application.structural_composition import (
    DOMINANT_SITE_AXIS_POLICY_ID,
    StructuralCompositionEnumerationResultV1,
    _derive_site_orientation_facts,
    _dominant_site_axis,
    build_structural_compositions,
    derive_boundary_side,
)
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.layout.domain.structural_composition import (
    CardinalSideV1,
    ProcessAxisV1,
    SiteOrientationFactsV1,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"
S1_EVIDENCE = (
    ROOT / "docs/tasks/evidence/v2_2_2_p1a_reset_s1/xinzhao_whole_building_compositions.json"
)
S2_EVIDENCE = (
    ROOT / "docs/tasks/evidence/v2_2_2_p1a_reset_s2/xinzhao_composition_authority_binding.json"
)


def _zone_plan() -> dict[str, Any]:
    result = ColdRoomZonePlanner().plan(
        ColdRoomZonePlanInput(
            daily_inbound_mass_kg=20000,
            working_time_h_per_day=16,
            finished_storage_days=7,
            packaging_storage_days=3,
            precooling_required_ratio=1,
            frozen_storage_days=10,
            main_packaging_storage_days=4,
            auxiliary_packaging_storage_days=12,
        )
    )
    assert result.success
    return asdict(result)


def _context(
    truck_input_override: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], ZoneDimensioningResultV1, ValidatedSiteGeometryV1]:
    source = json.loads(FIXTURE.read_text())
    plan = _zone_plan()
    truck_input = deepcopy(truck_input_override or source["truck_access"])
    p1_handoff = build_p1_project_handoff(plan, truck_input)
    geometry = validate_site_geometry(
        {"site_constraints": source["site_constraints"], "truck_access": truck_input},
        plan,
        p1_handoff=p1_handoff,
    )
    return plan, p1_handoff, geometry


def _result() -> StructuralCompositionEnumerationResultV1:
    plan, p1_handoff, geometry = _context()
    return build_structural_compositions(plan, p1_handoff, geometry)


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {str(key).lower() for key in value} | set().union(
            *(_all_keys(item) for item in value.values())
        )
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value)) if value else set()
    return set()


def test_authoritative_xinzhao_chain_generates_six_compositions_and_handoffs() -> None:
    result = _result()
    assert isinstance(result, StructuralCompositionEnumerationResultV1)
    assert result.composition_count == 6
    assert result.family_count == 3
    assert result.family_first_round_complete is True
    assert result.family_coverage_order == (
        "LINEAR_BANDED",
        "CENTRAL_PROCESS_CORE",
        "PROCESS_SPINE_WITH_PERIPHERAL_BANKS",
    )
    assert result.dominant_site_axis_policy_id == DOMINANT_SITE_AXIS_POLICY_ID
    assert result.source_zone_plan_hash.startswith("sha256:")
    assert result.source_p1_handoff_hash.startswith("sha256:")
    assert result.source_site_geometry_hash.startswith("sha256:")
    assert result.project_layout_validated_claimed is False
    assert result.exact_placement_performed is False
    assert result.access_routing_performed is False
    assert result.truck_validation_performed is False
    assert result.p2d_performed is False


def test_application_api_does_not_accept_caller_created_site_facts() -> None:
    parameters = inspect.signature(build_structural_compositions).parameters
    assert tuple(parameters) == ("canonical_zone_plan", "p1_handoff", "site_geometry")
    facts = SiteOrientationFactsV1(
        source_geometry_identity="caller-fabricated",
        source_geometry_hash="sha256:untrusted",
        validation_status="VALIDATED_GEOMETRY_FOUNDATION",
        dominant_site_axis=ProcessAxisV1.X,
        main_entrance_side=CardinalSideV1.EAST,
        truck_entrance_side=CardinalSideV1.WEST,
        preferred_loading_side=CardinalSideV1.UNSPECIFIED,
    )
    plan, p1_handoff, _geometry = _context()
    with pytest.raises(LayoutAuthorityError, match="INVALID_SITE_GEOMETRY_RESULT"):
        build_structural_compositions(plan, p1_handoff, facts)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_structural_compositions(facts)  # type: ignore[call-arg]


def test_p1_handoff_and_validated_site_geometry_are_required_authorities() -> None:
    plan, p1_handoff, geometry = _context()
    with pytest.raises(LayoutAuthorityError, match="INVALID_SITE_GEOMETRY_RESULT"):
        ValidatedSiteGeometryV1(geometry.canonical_json())

    tampered = p1_handoff.to_dict()
    tampered["truck_input_binding"]["to_ref"] = "office"
    with pytest.raises(LayoutAuthorityError, match="P1_HANDOFF_INTEGRITY_MISMATCH"):
        build_structural_compositions(plan, tampered, geometry)

    incomplete = p1_handoff.to_dict()
    incomplete["authority_status"]["p1_complete"] = False
    with pytest.raises(LayoutAuthorityError, match="P1_HANDOFF_NOT_COMPLETE"):
        build_structural_compositions(plan, incomplete, geometry)
    blocked = p1_handoff.to_dict()
    blocked["p1_closure_blockers"] = ["BLOCKED"]
    with pytest.raises(LayoutAuthorityError, match="P1_HANDOFF_NOT_COMPLETE"):
        build_structural_compositions(plan, blocked, geometry)


@pytest.mark.parametrize("field", ["identity", "schema_version"])
def test_p1_handoff_identity_and_schema_are_checked(field: str) -> None:
    plan, p1_handoff, geometry = _context()
    candidate = p1_handoff.to_dict()
    candidate[field] = "unrecognized"
    with pytest.raises(LayoutAuthorityError, match="P1_HANDOFF_IDENTITY_INVALID"):
        build_structural_compositions(plan, candidate, geometry)


@pytest.mark.parametrize(
    "status_field",
    [
        "dimension_authority_complete",
        "personnel_access_authority_complete",
        "material_access_authority_complete",
        "truck_access_contract_complete",
        "truck_project_input_contract_complete",
        "p1_complete",
    ],
)
def test_every_required_p1_authority_status_is_fail_closed(status_field: str) -> None:
    plan, p1_handoff, geometry = _context()
    candidate = p1_handoff.to_dict()
    candidate["authority_status"][status_field] = False
    with pytest.raises(LayoutAuthorityError, match="P1_HANDOFF_NOT_COMPLETE"):
        build_structural_compositions(plan, candidate, geometry)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("success", False),
        ("calculator_name", "unrecognized"),
        ("calculator_version", "2.0.0"),
    ],
)
def test_zone_plan_identity_version_and_success_are_checked(field: str, value: object) -> None:
    plan, p1_handoff, geometry = _context()
    candidate = deepcopy(plan)
    candidate[field] = value
    with pytest.raises(LayoutAuthorityError, match="ZONE_PLAN_IDENTITY_INVALID"):
        build_structural_compositions(candidate, p1_handoff, geometry)


def test_validated_site_geometry_must_bind_the_current_p1_hash() -> None:
    source = json.loads(FIXTURE.read_text())
    alternate_truck = deepcopy(source["truck_access"])
    alternate_truck["project_id"] = "another-authorized-project"
    for key, value in tuple(alternate_truck.items()):
        if isinstance(value, dict) and "project_id" in value:
            alternate_truck[key] = {**value, "project_id": "another-authorized-project"}
    plan, original_p1, _geometry = _context()
    alternate_p1 = build_p1_project_handoff(plan, alternate_truck)
    alternate_geometry = validate_site_geometry(
        {"site_constraints": source["site_constraints"], "truck_access": alternate_truck},
        plan,
        p1_handoff=alternate_p1,
    )
    with pytest.raises(LayoutAuthorityError, match="P1_HANDOFF_INTEGRITY_MISMATCH"):
        build_structural_compositions(plan, original_p1, alternate_geometry)


def test_zone_plan_hash_must_match_the_dimension_handoff_source() -> None:
    plan, p1_handoff, geometry = _context()
    tampered_plan = deepcopy(plan)
    tampered_plan["result"]["planning_parameters"]["working_time_h_per_day"] = 17
    with pytest.raises(LayoutAuthorityError, match="P1_HANDOFF_INTEGRITY_MISMATCH"):
        build_structural_compositions(tampered_plan, p1_handoff, geometry)


def test_invalid_preferred_loading_side_fails_closed() -> None:
    _plan, _p1_handoff, geometry = _context()
    payload = geometry.to_dict()
    payload["site"]["preferred_loading_side"] = "DIAGONAL"
    object.__setattr__(geometry, "payload_json", canonical_json(payload))
    with pytest.raises(LayoutAuthorityError, match="SITE_ORIENTATION_FACTS_INVALID"):
        _derive_site_orientation_facts(geometry)


@pytest.mark.parametrize("field", ["identity", "schema_version", "validation_status"])
def test_site_geometry_result_integrity_fields_are_checked(field: str) -> None:
    _plan, _p1_handoff, geometry = _context()
    payload = geometry.to_dict()
    payload[field] = "unrecognized"
    object.__setattr__(geometry, "payload_json", canonical_json(payload))
    with pytest.raises(LayoutAuthorityError, match="INVALID_SITE_GEOMETRY_RESULT"):
        _derive_site_orientation_facts(geometry)


def test_boundary_side_derivation_is_exact_and_fails_closed_for_non_boundary_segments() -> None:
    boundary = {
        "type": "polygon",
        "points": [
            {"x": 0, "y": 0},
            {"x": 75.46, "y": 0},
            {"x": 75.46, "y": 55},
            {"x": 0, "y": 55},
        ],
    }
    main = {"start": {"x": 75.46, "y": 24.525}, "end": {"x": 75.46, "y": 26.525}}
    truck = {"start": {"x": 0, "y": 33.7}, "end": {"x": 0, "y": 33.701}}
    assert derive_boundary_side(main, boundary) == CardinalSideV1.EAST
    assert derive_boundary_side(truck, boundary) == CardinalSideV1.WEST
    with pytest.raises(LayoutAuthorityError, match="SITE_BOUNDARY_SIDE_UNRESOLVED"):
        derive_boundary_side({"start": {"x": 10, "y": 10}, "end": {"x": 11, "y": 11}}, boundary)


def test_dominant_axis_policy_uses_buildable_bbox_long_axis_and_x_tie_break() -> None:
    def rectangle(width: int, height: int) -> dict[str, Any]:
        return {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": width, "y": 0},
                {"x": width, "y": height},
                {"x": 0, "y": height},
            ],
        }

    assert _dominant_site_axis(rectangle(20, 10)) == ProcessAxisV1.X
    assert _dominant_site_axis(rectangle(10, 20)) == ProcessAxisV1.Y
    assert _dominant_site_axis(rectangle(10, 10)) == ProcessAxisV1.X


def test_xinzhao_authoritative_orientation_matches_s1_evidence() -> None:
    result = _result()
    facts = result.site_orientation_facts
    assert facts.main_entrance_side == CardinalSideV1.EAST
    assert facts.truck_entrance_side == CardinalSideV1.WEST
    assert facts.dominant_site_axis == ProcessAxisV1.X
    assert facts.preferred_loading_side == CardinalSideV1.UNSPECIFIED
    evidence = json.loads(S1_EVIDENCE.read_text())
    old_signatures = [candidate["signature"] for candidate in evidence["candidates"]]
    new_signatures = [plan.to_dict()["signature"] for plan in result.compositions[:3]]
    assert new_signatures == old_signatures


def test_six_handoffs_preserve_each_complete_role_assignment_and_intent() -> None:
    result = _result()
    assert len(result.placement_handoffs) == 6
    for plan, handoff in zip(result.compositions, result.placement_handoffs, strict=True):
        plan_roles = {item.zone_role: item for item in plan.zone_role_assignment}
        handoff_roles = {item.zone_role: item for item in handoff.zone_role_assignment}
        assert len(handoff_roles) == 12
        assert len(handoff_roles) == len(handoff.zone_role_assignment)
        assert set(handoff_roles) == set(ZONE_CODES)
        for role, assignment in plan_roles.items():
            carried = handoff_roles[role]
            assert carried.composition_group == assignment.group_id.value
            assert carried.composition_band == assignment.band_id
            assert carried.topology_role == assignment.topology_role
            assert carried.dimension_authority_ref.zone_code == role
            assert (
                carried.dimension_authority_ref.source_p1_handoff_hash
                == result.source_p1_handoff_hash
            )
        assert handoff.family == plan.family
        assert handoff.process_axis == plan.process_axis
        assert handoff.process_direction == plan.process_direction
        assert handoff.principal_band_intents == tuple(
            type(handoff.principal_band_intents[0])(
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
        assert handoff.source_zone_plan_hash == result.source_zone_plan_hash
        assert handoff.source_p1_handoff_hash == result.source_p1_handoff_hash
        assert handoff.source_site_geometry_hash == result.source_site_geometry_hash


def test_machine_readable_s2_evidence_matches_the_bound_runtime_result() -> None:
    result = _result()
    evidence = json.loads(S2_EVIDENCE.read_text())
    assert evidence["generation_scope"] == (
        "COMPOSITION_ONLY_NO_EXACT_PLACEMENT_OR_ENGINEERING_VALIDATION"
    )
    assert evidence["authority_chain"] == {
        "zone_plan_hash": result.source_zone_plan_hash,
        "p1_handoff_hash": result.source_p1_handoff_hash,
        "site_geometry_hash": result.source_site_geometry_hash,
    }
    assert evidence["enumeration"]["composition_count"] == 6
    assert evidence["enumeration"]["family_count"] == 3
    assert evidence["enumeration"]["family_first_round_complete"] is True
    # S2 evidence is immutable historical serialization, before the additive
    # P0 mandatory-interface projection. Reconstruct that exact body rather
    # than overwrite the evidence or pretend the new contract has its hash.
    for historical, plan, handoff in zip(
        evidence["handoffs"], result.compositions, result.placement_handoffs, strict=True
    ):
        old_plan = plan.to_dict()
        old_plan.pop("mandatory_hard_interfaces")
        old_plan.pop("mandatory_interface_reservations")
        old_plan.pop("structural_interface_capacity_gate")
        old_handoff = asdict(handoff)
        old_handoff.pop("mandatory_hard_interfaces")
        old_handoff.pop("mandatory_interface_reservations")
        old_handoff.pop("structural_interface_capacity_gate")
        old_handoff["source_composition_hash"] = canonical_hash(old_plan)
        assert historical["canonical_hash"] == canonical_hash(old_handoff)
        assert historical["canonical_hash"] != handoff.canonical_result_hash
    assert all(item["role_count"] == 12 for item in evidence["handoffs"])
    assert all(
        item["peripheral_memberships"]["frozen_fruit_room"] == ["FROZEN_BRANCH_DOMAIN"]
        for item in evidence["handoffs"]
    )
    assert evidence["scope_flags"] == {
        "project_layout_validated_claimed": False,
        "exact_placement_performed": False,
        "access_routing_performed": False,
        "truck_validation_performed": False,
        "p2d_performed": False,
        "tool7_integrated": False,
    }


def test_peripheral_memberships_and_non_authority_survive_handoff() -> None:
    handoff = _result().placement_handoffs[0]
    roles = {item.zone_role: item for item in handoff.zone_role_assignment}
    expected = {
        "changing_room": "PERSONNEL_INGRESS_DOMAIN",
        "office": "PERSONNEL_INGRESS_DOMAIN",
        "packaging_material_storage": "PACKAGING_SUPPORT_DOMAIN",
        "secondary_fruit_buffer": "SECONDARY_BRANCH_DOMAIN",
        "frozen_fruit_room": "FROZEN_BRANCH_DOMAIN",
        "shipping_channel": "SHIPPING_TRUCK_INTERFACE_DOMAIN",
    }
    for role, domain in expected.items():
        assert roles[role].peripheral_domain_membership == (domain,)
    assert len(handoff.peripheral_domain_intents) == 5
    assert all(not item.engineering_authority for item in handoff.peripheral_domain_intents)
    assert handoff.composition_relationships_are_engineering_authority is False
    assert all(not item.engineering_authority for item in handoff.composition_relationships)
    assert handoff.placement_handoff_is_final_layout is False
    assert handoff.placement_handoff_is_p2c_candidate is False
    assert handoff.placement_handoff_is_engineering_validity_result is False


def test_handoff_contains_no_geometry_dimensions_or_final_validity_claims() -> None:
    forbidden = {
        "x",
        "y",
        "x_mm",
        "y_mm",
        "width_override",
        "depth_override",
        "rotation_selected",
        "portal_point",
        "corridor",
        "truck_pose",
        "footprint",
    }
    for handoff in _result().placement_handoffs:
        body = handoff.to_dict()
        assert not (forbidden & _all_keys(body))
        assert all(
            set(item.dimension_authority_ref.__dict__)
            == {"authority_identity", "zone_code", "source_p1_handoff_hash"}
            for item in handoff.zone_role_assignment
        )
        claimed_hash = body.pop("canonical_result_hash")
        assert claimed_hash == canonical_hash(body)


def test_composition_result_hash_is_deterministic_and_does_not_claim_placement() -> None:
    first = _result()
    second = _result()
    assert first.canonical_result_hash == second.canonical_result_hash
    assert first.to_dict() == second.to_dict()
    assert first.to_dict()["canonical_result_hash"] == first.canonical_result_hash
    assert all(not item.placement_handoff_is_final_layout for item in first.placement_handoffs)


def test_composition_does_not_modify_authoritative_process_graph() -> None:
    plan, p1_handoff, geometry = _context()
    before = canonical_json(asdict(process_graph()))
    build_structural_compositions(plan, p1_handoff, geometry)
    historical = p1_handoff.to_dict()["p1e_historical_handoff"]
    assert canonical_json(asdict(process_graph())) == before
    assert canonical_json(historical["dimension_handoff"]["adjacency_graph"]) == before
