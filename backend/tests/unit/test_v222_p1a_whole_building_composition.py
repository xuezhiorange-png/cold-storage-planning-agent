"""P1-S1 whole-building composition core: topology only, before placement."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.layout.application.site_geometry import validate_site_geometry
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.structural_composition import (
    AXIS_FAMILY_IS_INTENT_ONLY,
    PERIPHERAL_DOMAIN_IS_ENGINEERING_AUTHORITY,
    TRUCK_INTERFACE_IS_COMPOSITION_INTENT_ONLY,
    CardinalSideV1,
    CompositionFamilyV2,
    FunctionalGroupIdV1,
    PeripheralDomainIdV1,
    ProcessAxisV1,
    ProcessDirectionV1,
    SiteOrientationFactsV1,
    StructuralCompositionPlanV2,
    enumerate_structural_compositions,
    family_coverage_evidence,
)

ROOT = Path(__file__).resolve().parents[3]
XINZHAO_FIXTURE = (
    ROOT / "backend" / "tests" / "fixtures" / "v22" / "xinzhao_20t_site_layout_input_v3.json"
)
EXPECTED_GROUPS = {
    FunctionalGroupIdV1.RAW_SIDE_GROUP: {"raw_fruit_buffer", "primary_precooling_room"},
    FunctionalGroupIdV1.PROCESSING_CORE_GROUP: {
        "sorting_packaging_room",
        "secondary_precooling_room",
        "coating_room",
    },
    FunctionalGroupIdV1.FINISHED_SIDE_GROUP: {"finished_goods_room", "shipping_channel"},
    FunctionalGroupIdV1.SUPPORT_GROUP: {
        "packaging_material_storage",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
    },
    FunctionalGroupIdV1.PERSONNEL_GROUP: {"changing_room", "office"},
}


def _boundary_side(segment: dict[str, Any], boundary: dict[str, Any]) -> CardinalSideV1:
    points = boundary["points"]
    xs = [float(point["x"]) for point in points]
    ys = [float(point["y"]) for point in points]
    start, end = segment["start"], segment["end"]
    if float(start["x"]) == float(end["x"]) == min(xs):
        return CardinalSideV1.WEST
    if float(start["x"]) == float(end["x"]) == max(xs):
        return CardinalSideV1.EAST
    if float(start["y"]) == float(end["y"]) == min(ys):
        return CardinalSideV1.SOUTH
    if float(start["y"]) == float(end["y"]) == max(ys):
        return CardinalSideV1.NORTH
    raise AssertionError("validated entrance did not resolve to a cardinal boundary side")


def _xinzhao_orientation_facts() -> SiteOrientationFactsV1:
    source = json.loads(XINZHAO_FIXTURE.read_text())
    validated = validate_site_geometry(
        {"site_constraints": source["site_constraints"], "truck_access": source["truck_access"]},
        _canonical_zone_plan(),
    )
    payload = validated.to_dict()
    assert payload["validation_status"] == "VALIDATED_GEOMETRY_FOUNDATION"
    boundary = payload["site"]["effective_buildable_boundary"]
    points = boundary["points"]
    x_span = max(float(point["x"]) for point in points) - min(float(point["x"]) for point in points)
    y_span = max(float(point["y"]) for point in points) - min(float(point["y"]) for point in points)
    site_constraints = source["site_constraints"]
    loading_side = payload["site"]["preferred_loading_side"]
    return SiteOrientationFactsV1(
        source_geometry_identity=payload["identity"],
        source_geometry_hash=validated.canonical_result_hash,
        validation_status=payload["validation_status"],
        dominant_site_axis=ProcessAxisV1.X if x_span >= y_span else ProcessAxisV1.Y,
        main_entrance_side=_boundary_side(site_constraints["main_entrance"], boundary),
        truck_entrance_side=_boundary_side(site_constraints["truck_entrance"], boundary),
        preferred_loading_side=CardinalSideV1(loading_side),
    )


def _canonical_zone_plan() -> dict[str, Any]:
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


def _plans() -> tuple[StructuralCompositionPlanV2, ...]:
    return enumerate_structural_compositions(_xinzhao_orientation_facts())


def _collect_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        object_keys = {str(key).lower() for key in value}
        for nested in value.values():
            object_keys.update(_collect_keys(nested))
        return object_keys
    if isinstance(value, list):
        list_keys: set[str] = set()
        for nested in value:
            list_keys.update(_collect_keys(nested))
        return list_keys
    return set()


def test_xinzhao_fixture_generates_family_first_compositions_without_placement() -> None:
    plans = _plans()
    evidence = family_coverage_evidence(plans)
    assert len(plans) >= 3
    assert tuple(plan.family for plan in plans[:3]) == (
        CompositionFamilyV2.LINEAR_BANDED,
        CompositionFamilyV2.CENTRAL_PROCESS_CORE,
        CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS,
    )
    assert evidence["family_first_round_complete"] is True
    assert evidence["family_coverage_order"] == [plan.family.value for plan in plans[:3]]
    assert {plan.site_orientation_intent.source_geometry_identity for plan in plans} == {
        "site-geometry-foundation@1.0.0"
    }
    assert all(
        plan.construction_provenance.source_validation_status == "VALIDATED_GEOMETRY_FOUNDATION"
        for plan in plans
    )


def test_machine_readable_evidence_is_a_deterministic_projection_of_runtime_plans() -> None:
    plans = _plans()[:3]
    evidence_path = (
        ROOT
        / "docs"
        / "tasks"
        / "evidence"
        / "v2_2_2_p1a_reset_s1"
        / "xinzhao_whole_building_compositions.json"
    )
    evidence = json.loads(evidence_path.read_text())
    assert evidence["generation_scope"] == "STRUCTURAL_COMPOSITION_ONLY_NO_EXACT_PLACEMENT"
    assert evidence["summary"]["structural_composition_count"] == 3
    assert evidence["summary"]["family_count"] == 3
    assert evidence["summary"]["complete_12_role_composition_count"] == 3
    assert evidence["summary"]["family_first_round_complete"] is True
    assert evidence["candidates"] == [
        {"candidate_id": chr(65 + index), **plan.to_dict()} for index, plan in enumerate(plans)
    ]


def test_each_composition_assigns_all_twelve_roles_and_five_groups_once() -> None:
    for plan in _plans():
        assert len(plan.zone_role_assignment) == 12
        assert {item.zone_role for item in plan.zone_role_assignment} == set(ZONE_CODES)
        assert len({item.zone_role for item in plan.zone_role_assignment}) == 12
        groups = {group.group_id: set(group.zone_roles) for group in plan.functional_groups}
        assert groups == EXPECTED_GROUPS
        assert len(groups) == 5
        assert all(
            "PLACE_LATER_IF_SPACE_REMAINS" not in item.topology_role
            for item in plan.zone_role_assignment
        )


def test_every_composition_has_all_five_non_authoritative_peripheral_domains() -> None:
    for plan in _plans():
        assert len(plan.peripheral_domains) == 5
        assert {domain.domain_id for domain in plan.peripheral_domains} == set(PeripheralDomainIdV1)
        assert all(domain.engineering_authority is False for domain in plan.peripheral_domains)
        assert plan.peripheral_domain_is_engineering_authority is False
        assert PERIPHERAL_DOMAIN_IS_ENGINEERING_AUTHORITY is False
        assert plan.peripheral_domains[0].domain_id == PeripheralDomainIdV1.PERSONNEL_INGRESS_DOMAIN


def test_three_families_have_pairwise_distinct_topology_not_only_labels() -> None:
    first_round = _plans()[:3]
    assert len({plan.family for plan in first_round}) == 3
    signatures = [plan.signature.topology_key for plan in first_round]
    assert len(set(signatures)) == 3
    by_family = {plan.family: plan for plan in first_round}
    assert (
        by_family[CompositionFamilyV2.LINEAR_BANDED].signature.topology_key
        != by_family[CompositionFamilyV2.CENTRAL_PROCESS_CORE].signature.topology_key
    )
    assert (
        by_family[CompositionFamilyV2.LINEAR_BANDED].signature.topology_key
        != by_family[CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS].signature.topology_key
    )
    assert (
        by_family[CompositionFamilyV2.CENTRAL_PROCESS_CORE].signature.topology_key
        != by_family[CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS].signature.topology_key
    )


def test_linear_family_exposes_three_ordered_main_bands() -> None:
    plan = next(plan for plan in _plans() if plan.family == CompositionFamilyV2.LINEAR_BANDED)
    main_bands = [band for band in plan.principal_bands if band.sequence_index is not None]
    assert [band.sequence_index for band in main_bands] == [0, 1, 2]
    assert [band.relative_position for band in main_bands] == [
        "PROCESS_UPSTREAM",
        "PROCESS_MIDDLE",
        "PROCESS_DOWNSTREAM",
    ]
    assert [band.group_ids[0] for band in main_bands] == [
        FunctionalGroupIdV1.RAW_SIDE_GROUP,
        FunctionalGroupIdV1.PROCESSING_CORE_GROUP,
        FunctionalGroupIdV1.FINISHED_SIDE_GROUP,
    ]


def test_central_family_places_sorting_as_organizer_with_opposing_group_faces() -> None:
    plan = next(
        plan for plan in _plans() if plan.family == CompositionFamilyV2.CENTRAL_PROCESS_CORE
    )
    by_id = {band.band_id: band for band in plan.principal_bands}
    assert by_id["CENTRAL_SORTING_CORE"].zone_roles == ("sorting_packaging_room",)
    assert by_id["RAW_CORE_FACE"].relative_position == "CORE_FACE_A"
    assert by_id["FINISHED_OPPOSING_FACE"].relative_position == "OPPOSITE_CORE_FACE"
    assert by_id["SUPPORT_OTHER_FACES"].relative_position == "OTHER_PERIPHERAL_FACES"


def test_spine_family_has_dominant_process_spine_and_distinct_side_banks() -> None:
    plan = next(
        plan
        for plan in _plans()
        if plan.family == CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS
    )
    by_id = {band.band_id: band for band in plan.principal_bands}
    assert by_id["DOMINANT_PROCESS_SPINE"].zone_roles == (
        "raw_fruit_buffer",
        "primary_precooling_room",
        "sorting_packaging_room",
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )
    assert by_id["PRODUCT_SUPPORT_SIDE_BANK"].relative_position == "SPINE_SIDE_BANK_A"
    assert (
        by_id["PERSONNEL_INGRESS_BANK"].relative_position
        == "SPINE_SIDE_BANK_B_OUTSIDE_PRODUCT_CHAIN"
    )


def test_frozen_secondary_and_packaging_are_assigned_at_creation() -> None:
    for plan in _plans():
        assignment = {item.zone_role: item for item in plan.zone_role_assignment}
        assert assignment["frozen_fruit_room"].group_id == FunctionalGroupIdV1.SUPPORT_GROUP
        assert assignment["secondary_fruit_buffer"].group_id == FunctionalGroupIdV1.SUPPORT_GROUP
        assert (
            assignment["packaging_material_storage"].group_id == FunctionalGroupIdV1.SUPPORT_GROUP
        )
        domain_ids = {domain.domain_id for domain in plan.peripheral_domains}
        assert PeripheralDomainIdV1.FROZEN_BRANCH_DOMAIN in domain_ids
        assert PeripheralDomainIdV1.SECONDARY_BRANCH_DOMAIN in domain_ids
        assert PeripheralDomainIdV1.PACKAGING_SUPPORT_DOMAIN in domain_ids
        assert plan.frozen_branch_relationship.source == "frozen_fruit_room"
        assert plan.secondary_branch_relationship.source == "secondary_fruit_buffer"
        assert plan.packaging_branch_relationship.source == "packaging_material_storage"


def test_personnel_roles_are_separate_from_all_product_and_support_groups() -> None:
    for plan in _plans():
        assignment = {item.zone_role: item.group_id for item in plan.zone_role_assignment}
        assert assignment["changing_room"] == FunctionalGroupIdV1.PERSONNEL_GROUP
        assert assignment["office"] == FunctionalGroupIdV1.PERSONNEL_GROUP
        assert assignment["changing_room"] != assignment["sorting_packaging_room"]
        assert assignment["office"] not in {
            FunctionalGroupIdV1.RAW_SIDE_GROUP,
            FunctionalGroupIdV1.PROCESSING_CORE_GROUP,
            FunctionalGroupIdV1.FINISHED_SIDE_GROUP,
            FunctionalGroupIdV1.SUPPORT_GROUP,
        }
        assert plan.personnel_ingress_relationship.target == "PERSONNEL_INGRESS_DOMAIN"
        assert (
            "OUTSIDE" in plan.personnel_ingress_relationship.topology_intent
            or "SEPARATE" in plan.personnel_ingress_relationship.topology_intent
        )


def test_shipping_and_truck_relationship_is_intent_only() -> None:
    for plan in _plans():
        assert plan.shipping_truck_interface_relationship.source == "shipping_channel"
        assert (
            plan.shipping_truck_interface_relationship.target == "SHIPPING_TRUCK_INTERFACE_DOMAIN"
        )
        assert "INTENT_ONLY" in plan.shipping_truck_interface_relationship.topology_intent
        assert plan.shipping_truck_interface_relationship.engineering_authority is False
        assert TRUCK_INTERFACE_IS_COMPOSITION_INTENT_ONLY is True
        body = plan.to_dict()
        assert body["construction_provenance"]["golden_reference_used"] is False


def test_plans_contain_no_final_geometry_route_or_validation_claim() -> None:
    forbidden_fields = {
        "x",
        "y",
        "width",
        "depth",
        "width_m",
        "depth_m",
        "portal_coordinates",
        "corridor_geometry",
        "truck_path",
        "maneuver_path",
        "building_footprint",
        "p2d_pass",
        "project_layout_validated",
    }
    for plan in _plans():
        body = plan.to_dict()
        all_keys = _collect_keys(body)
        assert forbidden_fields.isdisjoint(all_keys)
        assert "coordinates" not in json.dumps(body).lower()
        assert (
            "golden" not in json.dumps(body).lower()
            or body["construction_provenance"]["golden_reference_used"] is False
        )
        assert plan.dominant_axis_family.basis == "COMPOSITION_INTENT_ONLY"
        assert plan.dominant_axis_family.engineering_axis_authority is False
        assert AXIS_FAMILY_IS_INTENT_ONLY is True


def test_axis_and_direction_variants_are_deterministic_and_coordinate_free() -> None:
    first = _plans()
    second = _plans()
    assert first == second
    assert {plan.process_axis for plan in first} == {ProcessAxisV1.X, ProcessAxisV1.Y}
    assert {plan.process_direction for plan in first} <= {
        ProcessDirectionV1.POSITIVE,
        ProcessDirectionV1.NEGATIVE,
    }
    assert all(
        plan.site_orientation_intent.selected_process_axis == plan.process_axis for plan in first
    )
    assert all(
        plan.site_orientation_intent.selected_process_direction == plan.process_direction
        for plan in first
    )
    assert all(plan.construction_provenance.golden_reference_used is False for plan in first)
    assert first[0].process_axis == ProcessAxisV1.X
    assert first[0].process_direction == ProcessDirectionV1.NEGATIVE
    assert first[3].process_axis == ProcessAxisV1.Y
    assert first[3].process_direction == ProcessDirectionV1.POSITIVE


def test_process_graph_remains_the_only_must_adjacency_authority() -> None:
    before = process_graph()
    plans = _plans()
    after = process_graph()
    assert before == after
    assert before.must_adjacencies == after.must_adjacencies
    assert all(
        "MUST" not in relation.relation_kind.value
        for plan in plans
        for relation in plan.composition_adjacency_intent
    )


def test_family_coverage_precedes_secondary_variants() -> None:
    plans = _plans()
    evidence = family_coverage_evidence(plans)
    expected = [
        CompositionFamilyV2.LINEAR_BANDED,
        CompositionFamilyV2.CENTRAL_PROCESS_CORE,
        CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS,
    ]
    assert [plan.family for plan in plans[:3]] == expected
    assert [plan.family for plan in plans[3:6]] == expected
    assert evidence["family_coverage_order"] == [family.value for family in expected]
    assert evidence["family_first_round_complete"] is True
    assert evidence["family_enumeration_count_by_family"] == {
        family.value: 2 for family in expected
    }
