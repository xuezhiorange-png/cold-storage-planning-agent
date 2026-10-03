"""Exact geometric ownership tests for P1A R6 topology lanes."""

from __future__ import annotations

from decimal import Decimal

from cold_storage.modules.layout.domain.main_process_skeleton import (
    MainProcessSkeletonCandidateV1,
    canonicalize_main_process_skeleton_for_evaluation,
)
from cold_storage.modules.layout.domain.main_process_topology import (
    classify_main_process_topology_v1,
    decide_main_process_topology_ownership_v1,
)
from cold_storage.modules.layout.domain.placement import _topology_geometry_valid
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
from cold_storage.modules.layout.domain.structural_composition import (
    CENTRAL_PROCESS_HUB,
    LINEAR_PROCESS_BAND,
    OFFSET_LINEAR_BAND,
    STRAIGHT_LINEAR_BAND,
    StructuralCompositionFamilyV1,
)


def _rect(
    code: str,
    x: int | str | Decimal,
    y: int | str | Decimal,
    width: int | str | Decimal,
    depth: int | str | Decimal,
    rotation: int = 0,
) -> PlacedRectangleV1:
    return PlacedRectangleV1(
        code,
        Decimal(str(x)),
        Decimal(str(y)),
        Decimal(str(width)),
        Decimal(str(depth)),
        rotation,
    )


def _straight_geometry() -> dict[str, PlacedRectangleV1]:
    return {
        "raw_fruit_buffer": _rect("raw_fruit_buffer", 0, 0, 5, 6),
        "primary_precooling_room": _rect("primary_precooling_room", 5, 0, 5, 6),
        "sorting_packaging_room": _rect("sorting_packaging_room", 10, 0, 10, 6),
        "coating_room": _rect("coating_room", 20, 0, 3, 6),
        "secondary_precooling_room": _rect("secondary_precooling_room", 23, 0, 5, 6),
        "finished_goods_room": _rect("finished_goods_room", 28, 0, 10, 6),
        "shipping_channel": _rect("shipping_channel", 38, 0, 2, 6),
    }


def _offset_geometry() -> dict[str, PlacedRectangleV1]:
    return {
        "raw_fruit_buffer": _rect("raw_fruit_buffer", 0, 0, 5, 10),
        "primary_precooling_room": _rect("primary_precooling_room", 5, 0, 5, 10),
        "sorting_packaging_room": _rect("sorting_packaging_room", 10, 5, 10, 10),
        "coating_room": _rect("coating_room", 20, 5, 3, 10),
        "secondary_precooling_room": _rect("secondary_precooling_room", 23, 10, 5, 10),
        "finished_goods_room": _rect("finished_goods_room", 28, 10, 10, 10),
        "shipping_channel": _rect("shipping_channel", 38, 10, 2, 10),
    }


def _hub_geometry() -> dict[str, PlacedRectangleV1]:
    return {
        "raw_fruit_buffer": _rect("raw_fruit_buffer", 0, 5, 10, 5),
        "primary_precooling_room": _rect("primary_precooling_room", 0, 10, 10, 5),
        "sorting_packaging_room": _rect("sorting_packaging_room", 10, 10, 10, 10),
        "secondary_precooling_room": _rect("secondary_precooling_room", 10, 20, 5, 10),
        "coating_room": _rect("coating_room", 15, 20, 5, 10),
        "finished_goods_room": _rect("finished_goods_room", 5, 30, 15, 10),
        "shipping_channel": _rect("shipping_channel", 0, 30, 5, 10),
    }


def _r5_shared_geometry() -> dict[str, PlacedRectangleV1]:
    return {
        "raw_fruit_buffer": _rect("raw_fruit_buffer", "0", "0", "15.2", "8.7"),
        "primary_precooling_room": _rect("primary_precooling_room", "15.2", "0", "14.7", "10.05"),
        "sorting_packaging_room": _rect("sorting_packaging_room", "15.2", "10.05", "45.76", "13.6"),
        "secondary_precooling_room": _rect(
            "secondary_precooling_room", "15.2", "23.65", "9.8", "10.05"
        ),
        "coating_room": _rect("coating_room", "9.317", "20.1", "5.883", "13.6"),
        "finished_goods_room": _rect("finished_goods_room", "9.317", "33.7", "32.4", "18.6"),
        "shipping_channel": _rect("shipping_channel", "1.624", "33.7", "6.5", "7.693", 90),
    }


def test_synthetic_straight_topology_has_canonical_straight_owner() -> None:
    result = classify_main_process_topology_v1(_straight_geometry())

    assert result.canonical_owner == STRAIGHT_LINEAR_BAND
    assert STRAIGHT_LINEAR_BAND in result.matched_topologies


def test_synthetic_offset_topology_has_canonical_offset_owner() -> None:
    result = classify_main_process_topology_v1(_offset_geometry())

    assert result.canonical_owner == OFFSET_LINEAR_BAND
    assert result.offset_transition_present is True
    assert result.pairwise_band_continuity is True
    assert result.three_group_common_band is False


def test_synthetic_hub_topology_has_canonical_hub_owner() -> None:
    result = classify_main_process_topology_v1(_hub_geometry())

    assert result.canonical_owner == CENTRAL_PROCESS_HUB
    assert result.hub_raw_face is not None
    assert result.hub_finished_face is not None
    assert result.hub_raw_face != result.hub_finished_face


def test_known_r5_shared_geometry_has_exactly_one_straight_owner() -> None:
    rectangles = _r5_shared_geometry()
    result = classify_main_process_topology_v1(rectangles)
    skeleton = MainProcessSkeletonCandidateV1.create(
        family=StructuralCompositionFamilyV1(
            LINEAR_PROCESS_BAND, "Y", "POSITIVE", "R5_GEOMETRY_REGRESSION"
        ),
        rectangles=rectangles,
        generation_pattern="R5_SHARED_GEOMETRY",
        hard_geometry_predicates_passed=("EXISTING_R5_SKELETON",),
    )

    assert result.canonical_owner == STRAIGHT_LINEAR_BAND
    assert result.matched_topologies.count(result.canonical_owner) == 1
    assert CENTRAL_PROCESS_HUB in result.matched_topologies
    assert skeleton.main_process_skeleton_hash == (
        "sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953"
    )
    assert "canonical_topology_owner" not in skeleton.to_dict()
    assert skeleton.to_evaluation_dict()["canonical_topology_owner"] == STRAIGHT_LINEAR_BAND


def test_r5_shared_geometry_is_not_claimed_by_hub_lane() -> None:
    rectangles = _r5_shared_geometry()

    assert _topology_geometry_valid(rectangles, STRAIGHT_LINEAR_BAND, "Y") is True
    assert _topology_geometry_valid(rectangles, CENTRAL_PROCESS_HUB, "X") is False


def test_offset_transition_identity_requires_exact_nonzero_cross_axis_shift() -> None:
    result = classify_main_process_topology_v1(_offset_geometry())

    assert result.canonical_owner == OFFSET_LINEAR_BAND
    assert result.cross_axis_shift_gt_zero is True
    assert result.three_group_common_band is False
    assert classify_main_process_topology_v1(_straight_geometry()).canonical_owner != (
        OFFSET_LINEAR_BAND
    )


def test_new_non_owner_geometry_is_admitted_to_tail_search() -> None:
    new_geometry = decide_main_process_topology_ownership_v1(
        lane_topology=CENTRAL_PROCESS_HUB,
        canonical_owner=STRAIGHT_LINEAR_BAND,
        first_discovery_topology=None,
        tail_search_discovery_topology=None,
        geometry_previously_seen=False,
        tail_search_started=False,
    )
    duplicate_geometry = decide_main_process_topology_ownership_v1(
        lane_topology=OFFSET_LINEAR_BAND,
        canonical_owner=STRAIGHT_LINEAR_BAND,
        first_discovery_topology=CENTRAL_PROCESS_HUB,
        tail_search_discovery_topology=CENTRAL_PROCESS_HUB,
        geometry_previously_seen=True,
        tail_search_started=True,
    )

    assert new_geometry.start_tail_search is True
    assert new_geometry.action == "START_TAIL_FOR_NEW_GEOMETRY"
    assert new_geometry.cross_topology_duplicate is False
    assert duplicate_geometry.start_tail_search is False
    assert duplicate_geometry.action == "SKIP_ALREADY_EVALUATED_GEOMETRY"
    assert duplicate_geometry.cross_topology_duplicate is True


def test_previously_seen_but_unevaluated_geometry_is_admitted() -> None:
    decision = decide_main_process_topology_ownership_v1(
        lane_topology=CENTRAL_PROCESS_HUB,
        canonical_owner=STRAIGHT_LINEAR_BAND,
        first_discovery_topology=STRAIGHT_LINEAR_BAND,
        tail_search_discovery_topology=None,
        geometry_previously_seen=True,
        tail_search_started=False,
    )

    assert decision.start_tail_search is True
    assert decision.action == "START_TAIL_FOR_PREVIOUSLY_SEEN_UNEVALUATED_GEOMETRY"
    assert decision.cross_topology_duplicate is True


def test_canonicalization_rebinds_family_and_preserves_exact_geometry() -> None:
    rectangles = _straight_geometry()
    discovery_family = StructuralCompositionFamilyV1(
        CENTRAL_PROCESS_HUB, "Y", "UNRESOLVED", "TEST_DISCOVERY_LANE"
    )
    discovery_seed = MainProcessSkeletonCandidateV1.create(
        family=discovery_family,
        rectangles=rectangles,
        topology=CENTRAL_PROCESS_HUB,
        generation_pattern="HUB_DISCOVERY_STRAIGHT_GEOMETRY",
        hard_geometry_predicates_passed=("EXACT_GEOMETRY",),
        discovery_topology=CENTRAL_PROCESS_HUB,
        discovery_family=discovery_family,
    )
    site_geometry = {
        "site": {
            "effective_buildable_boundary": {
                "points": [
                    {"x": "0", "y": "0"},
                    {"x": "50", "y": "0"},
                    {"x": "50", "y": "50"},
                    {"x": "0", "y": "50"},
                ]
            }
        }
    }

    canonical = canonicalize_main_process_skeleton_for_evaluation(
        discovery_seed,
        classify_main_process_topology_v1(rectangles),
        site_geometry=site_geometry,
    )

    assert canonical.topology == STRAIGHT_LINEAR_BAND
    assert canonical.canonical_topology_owner == STRAIGHT_LINEAR_BAND
    assert canonical.family.family == LINEAR_PROCESS_BAND
    assert canonical.family.dominant_axis == canonical.dominant_axis
    assert canonical.family.dominant_direction == canonical.dominant_direction
    assert canonical.discovery_topology == CENTRAL_PROCESS_HUB
    assert canonical.discovery_family == discovery_family
    assert canonical.main_process_skeleton_hash == discovery_seed.main_process_skeleton_hash
    assert canonical.zone_rectangles == discovery_seed.zone_rectangles
