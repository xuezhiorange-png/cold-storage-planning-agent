"""S4 CR1 access-critical construction remains subordinate to final authorities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cold_storage.modules.layout.application.access_aware_composition_placement import (
    MAX_ACCESS_VALIDATION_CHECKPOINTS_PER_FAMILY,
    _interface_preflight,
    search_access_aware_composition_placements,
)
from cold_storage.modules.layout.application.access_critical_construction import (
    build_access_critical_construction_intent,
)
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.domain.composition_placement import (
    _packaging_straight_interface_possible,
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
    assert placements["initial_family_budget"] == 12_500
    assert placements["continuation_budget"] == 22_500
    assert placements["candidates"] == [] or all(
        candidate["legacy_fallback_used"] is False for candidate in placements["candidates"]
    )
    assert result.access_validation_attempts == len(body["candidate_assessments"])
    assert all(
        item["non_truck_access_requirement_count"] == 11 for item in body["candidate_assessments"]
    )
    assert all(
        item["checkpoint_limit_per_family"] == MAX_ACCESS_VALIDATION_CHECKPOINTS_PER_FAMILY
        for item in body["candidate_assessments"]
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
