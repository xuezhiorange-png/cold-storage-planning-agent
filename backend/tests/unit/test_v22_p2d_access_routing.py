"""P2D route, truck-chain and final-layout validation tests."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any

import pytest

from cold_storage.modules.layout.application.access_routing import route_site_placement
from cold_storage.modules.layout.application.p1_project_handoff import build_p1_project_handoff
from cold_storage.modules.layout.application.site_geometry import validate_site_geometry
from cold_storage.modules.layout.domain.access_routing import route_access_requirement
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.objective_profile import approved_objective_profile
from cold_storage.modules.layout.domain.placement import SitePlacementResultV1
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    normalize_polygon,
)
from cold_storage.modules.layout.domain.truck_maneuver import (
    DOCK_FACE_REFERENCE,
    DOCK_REVERSE,
    FORWARD_AXIS,
    ORIGIN_REFERENCE,
    REFERENCE_FRAME,
    STRAIGHT_APPROACH,
    TURN_90,
    validate_truck_maneuver_project_binding,
)
from tests.unit.test_v22_p1a_dimensioning_adjacency import snapshot
from tests.unit.test_v22_p1f_project_truck_input import truck_input
from tests.unit.test_v22_p2b1_truck_maneuver_templates import (
    p1f_input,
    project_payload,
    template_payload,
)


def _point(x: object, y: object) -> dict[str, object]:
    return {"x": x, "y": y}


def _reference_frame(
    exit_pose: dict[str, object], entry_pose: dict[str, object] | None = None
) -> dict[str, object]:
    entry = entry_pose or {**_point(0, 0), "rotation_deg": 0}
    return {
        "reference_frame": REFERENCE_FRAME,
        "forward_axis": FORWARD_AXIS,
        "origin_reference": ORIGIN_REFERENCE,
        "vehicle_reference_point": _point(0, 0),
        "entry_pose": entry,
        "exit_pose": exit_pose,
    }


def _truck_maneuver_payload() -> dict[str, object]:
    straight = template_payload(
        STRAIGHT_APPROACH,
        template_id="straight",
        vehicle_width_m=Decimal("2.731"),
        vehicle_length_m=Decimal("11.113"),
        envelope_geometry={
            "type": "polygon",
            "points": [_point(0, -2), _point(40, -2), _point(40, 2), _point(0, 2)],
        },
        reference_frame=_reference_frame({**_point(40, 0), "rotation_deg": 0}),
    )
    turn = template_payload(
        TURN_90,
        template_id="turn",
        vehicle_width_m=Decimal("2.731"),
        vehicle_length_m=Decimal("11.113"),
        envelope_geometry={
            "type": "polygon",
            "points": [_point(0, 0), _point(4, 0), _point(4, 20), _point(0, 20)],
        },
        reference_frame=_reference_frame({**_point(0, 20), "rotation_deg": 0}),
        turn_direction="LEFT",
    )
    dock = template_payload(
        DOCK_REVERSE,
        template_id="dock",
        vehicle_width_m=Decimal("2.731"),
        vehicle_length_m=Decimal("11.113"),
        envelope_geometry={
            "type": "polygon",
            "points": [_point(0, 0), _point(88.6, 0), _point(88.6, 20), _point(0, 20)],
        },
        reference_frame=_reference_frame(
            {**_point(88.6, 12), "rotation_deg": 0},
        ),
        dock_face_reference=DOCK_FACE_REFERENCE,
        approach_pose={**_point(0, 0), "rotation_deg": 0},
        final_dock_pose={**_point(88.6, 12), "rotation_deg": 180},
    )
    return project_payload(
        templates=[straight, turn, dock],
        classes=[STRAIGHT_APPROACH, TURN_90, DOCK_REVERSE],
    )


def _site_input() -> dict[str, Any]:
    return {
        "site_boundary": {
            "type": "polygon",
            "points": [_point(0, 0), _point(220, 0), _point(220, 160), _point(0, 160)],
        },
        "main_entrance": {"start": _point(Decimal("34.7"), 0), "end": _point(Decimal("44.7"), 0)},
        "truck_entrance": {"start": _point(220, 78), "end": _point(220, 82)},
        "preferred_loading_side": "UNSPECIFIED",
        "no_build_zones": [],
    }


def _zone(
    code: str,
    x: object,
    y: object,
    width: object,
    depth: object,
    rotation: int = 0,
) -> dict[str, object]:
    return {
        "zone_code": code,
        "x": x,
        "y": y,
        "width_m": width,
        "depth_m": depth,
        "rotation_deg": rotation,
    }


def _placement(zone_plan: dict[str, Any], handoff: Any, geometry: Any) -> SitePlacementResultV1:
    rows = [
        _zone("raw_fruit_buffer", "19.5", 20, "15.2", "8.7"),
        _zone("primary_precooling_room", 20, "28.7", "14.7", "10.05"),
        _zone("sorting_packaging_room", "34.7", 29, "45.76", "13.6"),
        _zone("secondary_precooling_room", "34.7", "42.6", "9.8", "10.05"),
        _zone("coating_room", "44.5", "42.6", 8, 10),
        _zone("finished_goods_room", "52.5", "42.6", "32.4", "18.6"),
        _zone("shipping_channel", "84.9", "42.6", "6.5", "7.693"),
        _zone("changing_room", "34.7", 19, 4, 10),
        _zone("office", "84.9", "50.293", 6, 10),
        _zone("packaging_material_storage", 0, "26.9", "17.3", "14.5"),
        _zone("secondary_fruit_buffer", 50, "22.1", "8.4", "6.9"),
        _zone("frozen_fruit_room", "58.4", "20.8", "10.8", "8.2"),
    ]
    return SitePlacementResultV1.from_payload(
        {
            "schema_version": "1.0.0",
            "placement_result_identity": "site_constrained_factory_layout@1.0.0",
            "source_zone_plan_hash": canonical_hash(zone_plan),
            "source_p1_handoff_hash": handoff.canonical_result_hash,
            "source_site_geometry_hash": geometry.canonical_result_hash,
            "source_objective_profile_hash": approved_objective_profile().canonical_result_hash,
            "zone_count": 12,
            "placement_access_requirement_count": 12,
            "zones": rows,
            "shipping_loading_face_side": "RIGHT_LONG_EDGE",
            "shipping_loading_face_segment": {
                "start": _point("91.4", "42.6"),
                "end": _point("91.4", "49.1"),
            },
            "placement_hard_constraints_passed": True,
            "must_adjacency_evaluation": {"hard_constraints_passed": True},
            "should_adjacency_evaluation": {"satisfied_count": 0, "required_count": 5},
            "placement_access_observations": [],
            "placement_objective_vector": {},
            "search_provenance": {"fixture": True},
        }
    )


@pytest.fixture(scope="module")
def representative_context() -> tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any]:
    zone_plan = snapshot()
    p1f = truck_input()
    handoff = build_p1_project_handoff(zone_plan, p1f)
    geometry = validate_site_geometry(
        {"site_constraints": _site_input(), "truck_access": p1f},
        zone_plan,
        p1_handoff=handoff,
    )
    placement = _placement(zone_plan, handoff, geometry)
    binding = validate_truck_maneuver_project_binding(p1f_input(), _truck_maneuver_payload())
    return zone_plan, handoff, geometry, placement, binding


def test_representative_full_pass_validates_all_access_and_truck_requirements(
    representative_context: tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any],
) -> None:
    zone_plan, handoff, geometry, placement, binding = representative_context
    result = route_site_placement(
        zone_plan,
        handoff,
        geometry,
        placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=5000,
    ).to_dict()
    assert result["access_requirement_count"] == 12
    assert result["access_result_count"] == 12
    assert result["access_pass_count"] == 12
    assert result["truck_route_validated"] is True
    assert result["project_layout_validated"] is True
    assert result["p2_complete"] is True
    assert result["building_footprint"] is not None
    assert result["route_metrics"]["available"] is True
    assert result["route_metrics"]["objective_optimization_active"] is False
    assert all(row["status"] == "PASS" for row in result["access_results"])


def test_missing_truck_binding_keeps_twelve_results_but_fails_closed(
    representative_context: tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any],
) -> None:
    zone_plan, handoff, geometry, placement, _ = representative_context
    result = route_site_placement(
        zone_plan,
        handoff,
        geometry,
        placement,
        None,
        route_node_budget=5000,
    ).to_dict()
    assert result["access_result_count"] == 12
    assert result["truck_route_validated"] is False
    assert result["project_layout_validated"] is False
    assert result["p2_complete"] is False
    truck = next(row for row in result["access_results"] if row["flow_kind"] == "TRUCK")
    assert truck["codes"] == ["BLOCKED_PROJECT_MANEUVER_INPUT_REQUIRED"]


def test_replay_is_deterministic_and_access_observations_are_one_to_one(
    representative_context: tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any],
) -> None:
    zone_plan, handoff, geometry, placement, binding = representative_context
    first = route_site_placement(
        zone_plan,
        handoff,
        geometry,
        placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=5000,
    )
    second = route_site_placement(
        zone_plan,
        handoff,
        geometry,
        placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=5000,
    )
    first_body = first.to_dict()
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_result_hash == second.canonical_result_hash
    assert len(first_body["placement_access_observations"]) == 12
    expected_ids = {
        row["identity"]
        for row in handoff.to_dict()["p1e_historical_handoff"]["access_requirements"]
    }
    assert {
        row["observation_id"] for row in first_body["placement_access_observations"]
    } == expected_ids
    assert (
        first_body["access_requirements"]
        == handoff.to_dict()["p1e_historical_handoff"]["access_requirements"]
    )


def test_placement_source_hash_and_p1_authority_are_bound(
    representative_context: tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any],
) -> None:
    zone_plan, handoff, geometry, placement, binding = representative_context
    tampered = placement.to_dict()
    tampered["source_zone_plan_hash"] = "sha256:" + "0" * 64
    with pytest.raises(LayoutAuthorityError) as error:
        route_site_placement(zone_plan, handoff, geometry, tampered, binding)
    assert error.value.code == "PLACEMENT_INTEGRITY_MISMATCH"

    handoff_body = handoff.to_dict()
    handoff_body["p1e_historical_handoff"]["access_requirements"][0]["direct_allowed"] = False
    with pytest.raises(LayoutAuthorityError) as error:
        route_site_placement(zone_plan, handoff_body, geometry, placement, binding)
    assert error.value.code == "P1_HANDOFF_INTEGRITY_MISMATCH"


def test_maneuver_binding_is_project_bound_and_not_defaulted(
    representative_context: tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any],
) -> None:
    zone_plan, handoff, geometry, placement, _ = representative_context
    invalid = deepcopy(_truck_maneuver_payload())
    invalid["project_id"] = "another-project"
    with pytest.raises(LayoutAuthorityError):
        route_site_placement(
            zone_plan,
            handoff,
            geometry,
            placement,
            invalid,
        )


def test_selected_loading_face_cannot_be_switched_during_routing(
    representative_context: tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any],
) -> None:
    zone_plan, handoff, geometry, placement, binding = representative_context
    tampered = placement.to_dict()
    tampered["shipping_loading_face_side"] = "LEFT_LONG_EDGE"
    tampered.pop("canonical_result_hash")
    tampered["canonical_result_hash"] = canonical_hash(tampered)
    with pytest.raises(LayoutAuthorityError) as error:
        route_site_placement(zone_plan, handoff, geometry, tampered, binding)
    assert error.value.code == "PLACEMENT_INTEGRITY_MISMATCH"


def test_truck_search_budget_exhaustion_does_not_claim_validation(
    representative_context: tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any],
) -> None:
    zone_plan, handoff, geometry, placement, binding = representative_context
    result = route_site_placement(
        zone_plan,
        handoff,
        geometry,
        placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=0,
    ).to_dict()
    assert result["truck_route_validated"] is False
    assert result["project_layout_validated"] is False
    assert result["p2_complete"] is False
    assert result["truck_route_status"] == "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
    assert result["truck_search_provenance"]["node_budget_exhausted"] is True


def test_packaging_access_rejects_a_non_straight_route() -> None:
    requirement = {
        "identity": "access:packaging_material_storage->sorting_packaging_room@1.0.0",
        "from_ref": "packaging_material_storage",
        "to_ref": "sorting_packaging_room",
        "flow_kind": "PACKAGING",
        "access_class": "MATERIAL_LOGISTICS",
        "profile_identity": "packaging-sorting-straight-access@1.0.0",
        "portal_required": True,
        "corridor_allowed": True,
        "direct_allowed": True,
        "route_shape_constraint": "STRAIGHT_ONLY",
        "edge_orientation_requirement": "packaging-sorting-edge-connection@1.0.0",
        "cold_room_refs": [],
        "cold_room_portal_profile_identity": None,
        "source_authority": "Charles:V2_2_P1E_ACCESS_PROFILE_AUTHORITY_R1",
    }
    zones = {
        "packaging_material_storage": PlacedRectangleV1(
            "packaging_material_storage", 5, 5, 17.3, 14.5
        ),
        "sorting_packaging_room": PlacedRectangleV1("sorting_packaging_room", 55, 50, 45.76, 13.6),
    }
    boundary = normalize_polygon(
        {
            "type": "polygon",
            "points": [_point(0, 0), _point(130, 0), _point(130, 100), _point(0, 100)],
        }
    )
    result, corridors = route_access_requirement(
        requirement,
        relationships={
            "packaging-sorting-edge-connection@1.0.0": {
                "identity": "packaging-sorting-edge-connection@1.0.0",
                "from_edge_class": "LONG_EDGE",
                "to_edge_class": "SHORT_EDGE_EXIT_SIDE",
            }
        },
        zones=zones,
        boundary=boundary,
        obstacles=(),
        entrances={},
    )
    assert result["status"] in {"BLOCKED", "FAIL"}
    assert "PACKAGING_SORTING_STRAIGHT_ROUTE_REQUIRED" in result["codes"]
    assert corridors == ()


def test_portal_width_is_fail_closed() -> None:
    requirement = {
        "identity": "access:raw_fruit_buffer->primary_precooling_room@1.0.0",
        "from_ref": "raw_fruit_buffer",
        "to_ref": "primary_precooling_room",
        "flow_kind": "MATERIAL",
        "access_class": "MATERIAL_LOGISTICS",
        "profile_identity": "manual-pallet-jack-clear-envelope@1.0.0",
        "portal_required": True,
        "corridor_allowed": True,
        "direct_allowed": True,
        "route_shape_constraint": "NOT_FROZEN",
        "edge_orientation_requirement": None,
        "cold_room_refs": [],
        "cold_room_portal_profile_identity": None,
        "source_authority": "Charles:V2_2_P1E_ACCESS_PROFILE_AUTHORITY_R1",
    }
    zones = {
        "raw_fruit_buffer": PlacedRectangleV1("raw_fruit_buffer", 5, 5, 1, 1),
        "primary_precooling_room": PlacedRectangleV1("primary_precooling_room", 6, 5, 1, 1),
    }
    boundary = normalize_polygon(
        {
            "type": "polygon",
            "points": [_point(0, 0), _point(20, 0), _point(20, 20), _point(0, 20)],
        }
    )
    result, _ = route_access_requirement(
        requirement,
        relationships={},
        zones=zones,
        boundary=boundary,
        obstacles=(),
        entrances={},
    )
    assert result["status"] == "FAIL"
    assert "PORTAL_CLEAR_WIDTH_INSUFFICIENT" in result["codes"]
