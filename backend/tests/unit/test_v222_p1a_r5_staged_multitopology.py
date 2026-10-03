"""R5 topology coverage, exact offsets, and bounded-budget scheduling."""

from __future__ import annotations

from decimal import Decimal

from cold_storage.modules.aily.application.site_layout_preview import P4_PLACEMENT_NODE_BUDGET
from cold_storage.modules.layout.application.validated_candidate_selection import (
    _family_lane_budgets,
)
from cold_storage.modules.layout.domain import placement as placement_domain
from cold_storage.modules.layout.domain.main_process_skeleton import (
    MainProcessSkeletonCandidateV1,
)
from cold_storage.modules.layout.domain.placement import PlacedRectangleV1
from cold_storage.modules.layout.domain.structural_composition import (
    CENTRAL_PROCESS_HUB,
    OFFSET_LINEAR_BAND,
    STRAIGHT_LINEAR_BAND,
    StructuralCompositionFamilyV1,
    structural_topology_lanes,
)


def _site_geometry(width: int = 80, depth: int = 50) -> dict[str, object]:
    return {
        "site": {
            "effective_buildable_boundary": {
                "type": "polygon",
                "points": [
                    {"x": 0, "y": 0},
                    {"x": width, "y": 0},
                    {"x": width, "y": depth},
                    {"x": 0, "y": depth},
                ],
            }
        }
    }


def _authorities() -> dict[str, dict[str, object]]:
    dimensions = {
        "raw_fruit_buffer": (15.2, 8.7),
        "primary_precooling_room": (14.7, 10.05),
        "sorting_packaging_room": (45.76, 13.6),
        "coating_room": (5.883, 13.6),
        "secondary_precooling_room": (9.8, 10.05),
        "finished_goods_room": (32.4, 18.6),
        "shipping_channel": (6.5, 7.693),
    }
    return {
        code: {"geometry": {"width_m": width, "depth_m": depth}}
        for code, (width, depth) in dimensions.items()
    }


def _band_layout(
    raw: tuple[int, int], core: tuple[int, int], finished: tuple[int, int]
) -> dict[str, PlacedRectangleV1]:
    group_members = {
        "raw_fruit_buffer": raw,
        "primary_precooling_room": raw,
        "sorting_packaging_room": core,
        "coating_room": core,
        "secondary_precooling_room": finished,
        "finished_goods_room": finished,
        "shipping_channel": finished,
    }
    return {
        code: PlacedRectangleV1(
            code,
            Decimal(index * 20),
            Decimal(bounds[0]),
            Decimal(10),
            Decimal(bounds[1] - bounds[0]),
        )
        for index, (code, bounds) in enumerate(group_members.items())
    }


def test_topology_lanes_cover_straight_offset_and_hub_deterministically() -> None:
    first = structural_topology_lanes(_site_geometry(), _authorities())
    second = structural_topology_lanes(_site_geometry(), _authorities())

    assert [lane.to_dict() for lane in first] == [lane.to_dict() for lane in second]
    assert [lane.topology for lane in first] == [
        STRAIGHT_LINEAR_BAND,
        OFFSET_LINEAR_BAND,
        CENTRAL_PROCESS_HUB,
    ]
    assert [(lane.family.dominant_axis, lane.family.dominant_direction) for lane in first] == [
        ("Y", "POSITIVE"),
        ("Y", "POSITIVE"),
        ("X", "UNRESOLVED"),
    ]


def test_straight_and_offset_topologies_have_distinct_exact_band_predicates() -> None:
    aligned = _band_layout((0, 10), (0, 10), (0, 10))
    staggered = _band_layout((0, 10), (5, 15), (10, 20))

    assert placement_domain._topology_geometry_valid(aligned, STRAIGHT_LINEAR_BAND, "X") is True
    assert placement_domain._topology_geometry_valid(aligned, OFFSET_LINEAR_BAND, "X") is False
    assert placement_domain._topology_geometry_valid(staggered, STRAIGHT_LINEAR_BAND, "X") is False
    assert placement_domain._topology_geometry_valid(staggered, OFFSET_LINEAR_BAND, "X") is True


def test_staged_scheduler_reserves_each_topology_before_diversity_expansion() -> None:
    assert _family_lane_budgets(120, 3, preferred_lane_index=2) == (40, 40, 40)
    assert _family_lane_budgets(121, 3, preferred_lane_index=2) == (40, 40, 41)
    assert sum(_family_lane_budgets(120, 3, preferred_lane_index=2)) == 120


def test_constructive_caps_split_face_pairs_and_sorting_roots_without_budget_growth() -> None:
    assert placement_domain.CONSTRUCTIVE_FACE_PAIR_NODE_BUDGET == 20
    assert placement_domain.CONSTRUCTIVE_SORTING_ROOT_NODE_BUDGET == 16
    assert placement_domain.STRUCTURED_SKELETON_CONSTRUCTION_SHARE_NUMERATOR == 1
    assert placement_domain.STRUCTURED_SKELETON_CONSTRUCTION_SHARE_DENOMINATOR == 2
    assert P4_PLACEMENT_NODE_BUDGET == 120
    assert placement_domain.MIN_CONSTRUCTIVE_SKELETON_NODE_ALLOWANCE == 15


def test_topology_name_is_not_part_of_main_process_geometry_identity() -> None:
    family = StructuralCompositionFamilyV1("LINEAR_PROCESS_BAND", "Y", "POSITIVE", "UNIT_TEST")
    rectangles = _band_layout((0, 10), (0, 10), (0, 10))
    predicates = ("SITE_CONTAINMENT", "NO_BUILD_CLEAR", "MUST_ADJACENCY")
    straight = MainProcessSkeletonCandidateV1.create(
        family=family,
        rectangles=rectangles,
        generation_pattern="STRAIGHT",
        hard_geometry_predicates_passed=predicates,
        topology=STRAIGHT_LINEAR_BAND,
    )
    offset = MainProcessSkeletonCandidateV1.create(
        family=family,
        rectangles=rectangles,
        generation_pattern="OFFSET",
        hard_geometry_predicates_passed=predicates,
        topology=OFFSET_LINEAR_BAND,
    )

    assert straight.topology != offset.topology
    assert straight.main_process_skeleton_hash == offset.main_process_skeleton_hash
