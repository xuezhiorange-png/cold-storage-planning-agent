"""S4 CR1 access-critical construction remains subordinate to final authorities."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cold_storage.modules.layout.application import (
    access_aware_composition_placement as access_aware_application,
)
from cold_storage.modules.layout.application.access_aware_composition_placement import (
    _interface_preflight,
    search_access_aware_composition_placements,
)
from cold_storage.modules.layout.application.access_critical_construction import (
    build_access_critical_construction_intent,
)
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.application.structural_composition import (
    build_structural_compositions,
)
from cold_storage.modules.layout.domain.composition_placement import (
    _packaging_interface_capacity_remains,
    _packaging_straight_interface_possible,
    _Shape,
)
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1, normalize_polygon
from cold_storage.modules.layout.domain.truck_maneuver import (
    validate_truck_maneuver_project_binding,
)
from tests.unit.test_v222_p1a_composition_authority_handoff import _context

ROOT = Path(__file__).resolve().parents[2]
XINZHAO_FIXTURE = ROOT / "tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"


@pytest.fixture(scope="module")
def authorities() -> tuple[dict[str, Any], Any, Any, Any]:
    zone_plan, p1_handoff, site_geometry = _context()
    source = json.loads(XINZHAO_FIXTURE.read_text())
    truck_binding = validate_truck_maneuver_project_binding(
        source["truck_access"], source["truck_maneuver"]
    )
    return zone_plan, p1_handoff, site_geometry, truck_binding


def test_access_critical_intent_binds_all_five_frozen_interfaces(authorities) -> None:
    zone_plan, p1_handoff, site_geometry, truck_binding = authorities
    intent = build_access_critical_construction_intent(
        zone_plan, p1_handoff, site_geometry, truck_binding
    )

    assert {item.interface_kind for item in intent.interfaces} == {
        "PERSONNEL_INGRESS_INTERFACE",
        "PACKAGING_SORTING_STRAIGHT_INTERFACE",
        "SECONDARY_SORTING_ACCESS_INTERFACE",
        "FROZEN_SORTING_ACCESS_INTERFACE",
        "SHIPPING_TRUCK_MANEUVER_INTERFACE",
    }
    packaging = intent.interface("PACKAGING_SORTING_STRAIGHT_INTERFACE")
    assert packaging.route_shape_constraint == "STRAIGHT_ONLY"
    assert packaging.from_edge_class == "LONG_EDGE"
    assert packaging.to_edge_class == "SHORT_EDGE_EXIT_SIDE"
    assert packaging.portal_clear_width_mm == 2400
    assert packaging.corridor_clear_width_mm == 5000
    assert intent.main_entrance_segment_mm == ((75460, 24525), (75460, 26525))
    assert intent.truck_entrance_segment_mm == ((0, 33700), (0, 33701))
    assert intent.truck_dock_point_events
    assert intent.engineering_authority is False
    assert intent.access_pass_claimed is False
    assert intent.truck_pass_claimed is False
    assert all(item.engineering_authority is False for item in intent.interfaces)
    assert all(
        item.validation_owner == "EXISTING_ACCESS_OR_TRUCK_AUTHORITY" for item in intent.interfaces
    )


def test_interface_preflight_only_admits_search_and_checks_portal_capacity(authorities) -> None:
    zone_plan, p1_handoff, site_geometry, truck_binding = authorities
    intent = build_access_critical_construction_intent(
        zone_plan, p1_handoff, site_geometry, truck_binding
    )
    binding = bind_layout_authority(zone_plan, p1_handoff, site_geometry)

    statuses = _interface_preflight(binding, intent)
    assert statuses == {
        "PERSONNEL_INGRESS_INTERFACE": "PASS_TO_SEARCH",
        "PACKAGING_SORTING_STRAIGHT_INTERFACE": "PASS_TO_SEARCH",
        "SECONDARY_SORTING_ACCESS_INTERFACE": "PASS_TO_SEARCH",
        "FROZEN_SORTING_ACCESS_INTERFACE": "PASS_TO_SEARCH",
        "SHIPPING_TRUCK_MANEUVER_INTERFACE": "PASS_TO_SEARCH",
    }
    assert all(status.endswith("TO_SEARCH") for status in statuses.values())


def test_packaging_straight_preflight_accepts_aligned_and_rejects_nonstraight_geometry(
    authorities,
) -> None:
    zone_plan, p1_handoff, site_geometry, truck_binding = authorities
    intent = build_access_critical_construction_intent(
        zone_plan, p1_handoff, site_geometry, truck_binding
    )
    boundary = normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 100, "y": 0},
                {"x": 100, "y": 100},
                {"x": 0, "y": 100},
            ],
        }
    )

    packaging = PlacedRectangleV1("packaging_material_storage", 0, 10, 17.3, 14.5, 90)
    sorting_direct = PlacedRectangleV1("sorting_packaging_room", 14.5, 10, 45.76, 13.6)
    assert _packaging_straight_interface_possible(
        packaging, sorting_direct, intent, boundary, (), {}
    )

    packaging_horizontal = PlacedRectangleV1("packaging_material_storage", 10, 0, 17.3, 14.5)
    sorting_horizontal = PlacedRectangleV1("sorting_packaging_room", 10, 14.5, 45.76, 13.6, 90)
    assert _packaging_straight_interface_possible(
        packaging_horizontal, sorting_horizontal, intent, boundary, (), {}
    )

    sorting_offset = PlacedRectangleV1("sorting_packaging_room", 20, 10, 45.76, 13.6)
    assert _packaging_straight_interface_possible(
        packaging, sorting_offset, intent, boundary, (), {}
    )
    blocking_obstacle = normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": 15, "y": 16},
                {"x": 16, "y": 16},
                {"x": 16, "y": 21},
                {"x": 15, "y": 21},
            ],
        }
    )
    assert not _packaging_straight_interface_possible(
        packaging, sorting_offset, intent, boundary, (blocking_obstacle,), {}
    )

    sorting_misaligned = PlacedRectangleV1("sorting_packaging_room", 14.5, 25, 45.76, 13.6)
    assert not _packaging_straight_interface_possible(
        packaging, sorting_misaligned, intent, boundary, (), {}
    )


def test_packaging_partial_capacity_preflight_preserves_a_straight_seed(authorities) -> None:
    zone_plan, p1_handoff, site_geometry, truck_binding = authorities
    intent = build_access_critical_construction_intent(
        zone_plan, p1_handoff, site_geometry, truck_binding
    )
    composition_result = build_structural_compositions(zone_plan, p1_handoff, site_geometry)
    handoff = next(
        item
        for item in composition_result.placement_handoffs
        if item.composition_identity.endswith("LINEAR_BANDED:Y:POSITIVE:r1")
    )
    boundary = normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 100, "y": 0},
                {"x": 100, "y": 100},
                {"x": 0, "y": 100},
            ],
        }
    )
    sorting = PlacedRectangleV1("sorting_packaging_room", 40, 40, 30, 15)
    shapes = {"packaging_material_storage": (_Shape(17_300, 14_500, 90),)}

    assert _packaging_interface_capacity_remains(
        handoff, shapes, intent, (), 1, {"sorting_packaging_room": sorting}, boundary, ()
    )
    east_blocker = PlacedRectangleV1("capacity_blocker", 70, 0, 30, 100)
    assert not _packaging_interface_capacity_remains(
        handoff,
        shapes,
        intent,
        (),
        1,
        {"sorting_packaging_room": sorting, "capacity_blocker": east_blocker},
        boundary,
        (),
    )


@pytest.fixture(scope="module")
def access_aware_replay(authorities):
    zone_plan, p1_handoff, site_geometry, truck_binding = authorities
    return search_access_aware_composition_placements(
        zone_plan, p1_handoff, site_geometry, truck_binding
    )


def test_access_aware_search_is_bounded_family_first_and_never_fakes_validation(
    access_aware_replay,
) -> None:
    result = access_aware_replay
    body = result.to_dict()
    placements = body["placements"]

    assert placements["node_budget"] == 60_000
    assert placements["nodes_used"] <= 60_000
    assert placements["family_first_round_complete"] is True
    assert placements["family_coverage_order"] == [
        "LINEAR_BANDED",
        "CENTRAL_PROCESS_CORE",
        "PROCESS_SPINE_WITH_PERIPHERAL_BANKS",
    ]
    assert set(placements["attempt_count_by_family"]) == set(placements["family_coverage_order"])
    assert all(placements["attempt_count_by_family"].values())
    assert placements["initial_family_budget"] == 1_000
    assert placements["continuation_budget"] == 57_000
    assert placements["search_order_lanes_enabled"] == {
        "ACCESS_AWARE_ORDER": True,
        "S3_COMPATIBILITY_ORDER": True,
    }
    assert placements["search_order_is_engineering_authority"] is False
    assert placements["attempt_count_by_search_order_lane"] == {
        "ACCESS_AWARE_ORDER": 7,
        "S3_COMPATIBILITY_ORDER": 6,
    }
    assert placements["attempt_count"] == 13
    assert {
        (attempt["family"], attempt["search_order_lane"])
        for attempt in placements["search_attempts"]
    } >= {
        (family, lane)
        for family in placements["family_coverage_order"]
        for lane in ("ACCESS_AWARE_ORDER", "S3_COMPATIBILITY_ORDER")
    }
    known_lane = [
        attempt
        for attempt in placements["search_attempts"]
        if attempt["composition_identity"]
        == "whole-building-structural-composition@2.0.0:LINEAR_BANDED:Y:POSITIVE:r1"
        and attempt["peripheral_bank_sign"] == 1
    ]
    assert len(known_lane) == 1
    assert known_lane[0]["search_order_lane"] == "S3_COMPATIBILITY_ORDER"
    assert known_lane[0]["nodes_allocated"] == 20_000
    opposite_known_lane = [
        attempt
        for attempt in placements["search_attempts"]
        if attempt["composition_identity"]
        == "whole-building-structural-composition@2.0.0:LINEAR_BANDED:Y:POSITIVE:r1"
        and attempt["peripheral_bank_sign"] == -1
    ]
    assert len(opposite_known_lane) == 1
    assert opposite_known_lane[0]["search_order_lane"] == "S3_COMPATIBILITY_ORDER"
    linear_progress_lane = [
        attempt
        for attempt in placements["search_attempts"]
        if attempt["composition_identity"]
        == "whole-building-structural-composition@2.0.0:LINEAR_BANDED:X:NEGATIVE:r0"
        and attempt["peripheral_bank_sign"] == 1
        and attempt["search_order_lane"] == "ACCESS_AWARE_ORDER"
    ]
    assert len(linear_progress_lane) == 2
    assert max(attempt["nodes_allocated"] for attempt in linear_progress_lane) == 27_500
    assert sum(attempt["nodes_allocated"] for attempt in placements["search_attempts"]) == 60_000
    assert all(
        attempt["access_critical_construction_intent_identity"]
        == result.construction_intent.identity
        for attempt in placements["search_attempts"]
    )
    assert placements["complete_candidates_constructed"] == len(placements["candidates"])
    assert result.complete_candidates_constructed == result.complete_candidates_access_assessed
    assert result.truck_preflight_complete_candidate_prune_count == 0
    assert placements["candidates"] == [] or all(
        candidate["legacy_fallback_used"] is False for candidate in placements["candidates"]
    )
    assert result.access_validation_attempts == len(body["candidate_assessments"])
    assert all(
        item["non_truck_access_requirement_count"] == 11 for item in body["candidate_assessments"]
    )
    assert all(
        len(item["access_results"]) == 11
        and item["access_assessed_before_truck_preflight"] is True
        and item["truck_preflight"]["truck_validated"] is False
        for item in body["candidate_assessments"]
    )
    assert all(
        dict(candidate["search_provenance"]).get("access_critical_construction_intent")
        == result.construction_intent.identity
        for candidate in placements["candidates"]
    )
    assert result.best_non_truck_access_pass_count == max(
        (item["non_truck_access_pass_count"] for item in body["candidate_assessments"]),
        default=0,
    )
    assert result.selected_non_truck_access_pass_count == (
        max(
            (
                item["non_truck_access_pass_count"]
                for item in body["candidate_assessments"]
                if item["candidate_admitted_for_access_progress"]
            ),
            default=0,
        )
    )
    assert result.truck_validation_attempts == (1 if result.final_validation is not None else 0)
    assert result.p2d_validation_attempts == result.truck_validation_attempts
    if result.final_validation is None:
        assert result.truck_validation_performed is False
        assert result.p2d_performed is False
        assert result.project_layout_validated_claimed is False


def test_access_aware_search_replays_deterministically(authorities, access_aware_replay) -> None:
    zone_plan, p1_handoff, site_geometry, truck_binding = authorities
    replay = search_access_aware_composition_placements(
        zone_plan, p1_handoff, site_geometry, truck_binding
    )
    assert replay.canonical_result_hash == access_aware_replay.canonical_result_hash


def test_truck_preflight_runs_after_complete_candidate_and_non_truck_assessment(
    authorities, monkeypatch
) -> None:
    zone_plan, p1_handoff, site_geometry, truck_binding = authorities
    binding = bind_layout_authority(zone_plan, p1_handoff, site_geometry)
    compositions = build_structural_compositions(zone_plan, p1_handoff, site_geometry)
    handoff = compositions.placement_handoffs[0]
    intent = build_access_critical_construction_intent(
        zone_plan, p1_handoff, site_geometry, truck_binding
    )
    zones = {
        role: PlacedRectangleV1(role, index * 2, 0, 1, 1)
        for index, role in enumerate(sorted(binding.dimension_authorities))
    }
    candidate = SimpleNamespace(
        composition_identity=handoff.composition_identity,
        canonical_result_hash="sha256:synthetic-complete-candidate",
        search_provenance=(("access_critical_construction_intent", intent.identity),),
        zones=tuple(zones.values()),
    )
    event_order: list[str] = []

    def route(requirement, **_kwargs):
        event_order.append(f"ACCESS:{requirement['identity']}")
        return {"status": "PASS", "codes": []}, ()

    def truck_preflight(*_args):
        event_order.append("TRUCK_PREFLIGHT")
        return {
            "status": "PROVABLY_NO_BASIC_MANEUVER_CAPACITY",
            "truck_validated": False,
            "reason": "SYNTHETIC_ORDERING_TEST_ONLY",
        }

    def domain_enumeration(*_args, **kwargs):
        admitted = kwargs["complete_candidate_admission"](
            handoff, zones, 1, "ACCESS_AWARE_ORDER", 12
        )
        assert admitted is True
        return SimpleNamespace(
            candidates=(candidate,),
            search_attempts=(),
            to_dict=lambda: {"candidates": [candidate.canonical_result_hash]},
        )

    monkeypatch.setattr(access_aware_application, "validate_access_requirement", route)
    monkeypatch.setattr(access_aware_application, "_truck_necessary_preflight", truck_preflight)
    monkeypatch.setattr(access_aware_application, "enumerate_domain_placements", domain_enumeration)

    result = search_access_aware_composition_placements(
        zone_plan, p1_handoff, site_geometry, truck_binding
    )

    assert result.complete_candidates_constructed == 1
    assert result.complete_candidates_access_assessed == 1
    assert result.candidates_admitted == 1
    assert result.candidates_selected == 1
    assessment = result.candidate_assessments[0]
    assert assessment["non_truck_access_pass_count"] == 11
    assert len(assessment["access_results"]) == 11
    assert assessment["truck_preflight"]["status"] == "PROVABLY_NO_BASIC_MANEUVER_CAPACITY"
    assert result.truck_preflight_complete_candidate_prune_count == 0
    assert event_order[-1] == "TRUCK_PREFLIGHT"
    assert len(event_order) == 12
    assert result.truck_validation_performed is False
    assert result.p2d_performed is False
