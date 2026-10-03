from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest

from cold_storage.modules.layout.domain import placement
from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1, normalize_polygon
from cold_storage.modules.layout.domain.structural_composition import (
    FUNCTIONAL_GROUPS,
    STRAIGHT_LINEAR_BAND,
)
from cold_storage.modules.layout.domain.structured_building import (
    BASE_LAYOUT_FAMILIES,
    CENTRAL_PROCESS_WITH_SIDE_BANKS,
    FINISHED_SIDE_BAND,
    LINEAR_3_BAND,
    LONGITUDINAL_PROCESS_SPINE,
    PROCESS_CORE_BAND,
    RAW_SIDE_BAND,
    RECTANGLE,
    FunctionalBandV1,
    StructuredBuildingSkeletonV1,
    _minimum_single_zone_envelope_extent,
    _must_chain_band_dimension_options,
    construct_structured_building_plan_v1,
)
from tests.evaluation.r2_band_packing_recovery import _record_search_phase


def _boundary() -> tuple[tuple[int, int], ...]:
    return normalize_polygon(
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 100, "y": 0},
                {"x": 100, "y": 80},
                {"x": 0, "y": 80},
            ],
        }
    )


def _authorities() -> dict[str, dict[str, object]]:
    return {
        code: {
            "zone_code": code,
            "dimension_mode": "FIXED_RECTANGLE",
            "required_area_m2": 100,
            "geometry": {"width_m": 10, "depth_m": 10, "required_area_m2": 100},
        }
        for members in FUNCTIONAL_GROUPS.values()
        for code in members
    }


def test_recovery_evidence_classifies_search_phase_from_candidate_provenance() -> None:
    assert (
        _record_search_phase(
            {"candidate": {"search_provenance": {"search_phase": "GENERAL_FALLBACK"}}}
        )
        == "GENERAL_FALLBACK"
    )
    assert (
        _record_search_phase({"candidate": {"search_provenance": {"search_phase": "STRUCTURED"}}})
        == "STRUCTURED"
    )
    assert _record_search_phase({"candidate": {"_search_phase": "GENERAL_FALLBACK"}}) is None


@pytest.mark.parametrize("family", BASE_LAYOUT_FAMILIES)
def test_empty_band_geometry_returns_no_candidate_without_index_error(
    monkeypatch: pytest.MonkeyPatch, family: str
) -> None:
    constructors = {
        LINEAR_3_BAND: placement._synthesize_linear_3_band_main_process,
        CENTRAL_PROCESS_WITH_SIDE_BANKS: (
            placement._synthesize_central_process_with_side_banks_main_process
        ),
        LONGITUDINAL_PROCESS_SPINE: (placement._synthesize_longitudinal_process_spine_main_process),
    }
    geometry_builders = {
        LINEAR_3_BAND: "_linear_3_band_geometry",
        CENTRAL_PROCESS_WITH_SIDE_BANKS: "_central_side_bank_geometry",
        LONGITUDINAL_PROCESS_SPINE: "_longitudinal_spine_geometry",
    }
    monkeypatch.setattr(placement, geometry_builders[family], lambda *_args: ())
    failure_reasons = ["BAND_PACKING_UNAVAILABLE:FINISHED_SIDE_BAND"]

    result = constructors[family](
        cast(placement._PlacementSearchContext, object()),
        cast(StructuredBuildingSkeletonV1, object()),
        None,
        variant_index=0,
        failure_reasons=failure_reasons,
    )

    assert result is None
    assert failure_reasons == ["BAND_PACKING_UNAVAILABLE:FINISHED_SIDE_BAND"]


def test_negative_linear_direction_reverses_raw_and_finished_bands() -> None:
    positive = construct_structured_building_plan_v1(
        boundary=_boundary(),
        obstacles=(),
        authorities=_authorities(),
        process_axis="Y",
        process_direction="POSITIVE",
        layout_family=LINEAR_3_BAND,
        envelope_family=RECTANGLE,
    )
    negative = construct_structured_building_plan_v1(
        boundary=_boundary(),
        obstacles=(),
        authorities=_authorities(),
        process_axis="Y",
        process_direction="NEGATIVE",
        layout_family=LINEAR_3_BAND,
        envelope_family=RECTANGLE,
    )

    positive_raw = positive.band_for_zone("raw_fruit_buffer").bounds_mm
    positive_finished = positive.band_for_zone("shipping_channel").bounds_mm
    negative_raw = negative.band_for_zone("raw_fruit_buffer").bounds_mm
    negative_finished = negative.band_for_zone("shipping_channel").bounds_mm

    assert positive_raw[1] < positive_finished[1]
    assert positive_finished[3] == positive.envelope.bounds_mm[3]
    assert negative_finished[1] < negative_raw[1]
    assert negative_finished[1] == negative.envelope.bounds_mm[1]
    assert negative.to_dict()["process_direction"] == "NEGATIVE"


def test_layout_family_variants_remain_explicitly_distinct() -> None:
    assert len(set(BASE_LAYOUT_FAMILIES)) == 3
    assert {LINEAR_3_BAND, CENTRAL_PROCESS_WITH_SIDE_BANKS, LONGITUDINAL_PROCESS_SPINE} == set(
        BASE_LAYOUT_FAMILIES
    )
    assert RAW_SIDE_BAND != FINISHED_SIDE_BAND


def test_simple_l_necessary_extent_uses_room_shape_not_rectangular_family_projection() -> None:
    authorities = {
        "wide_room": {
            "dimension_mode": "FIXED_RECTANGLE",
            "geometry": {"width_m": 45.76, "depth_m": 13.6},
        },
        "square_room": {
            "dimension_mode": "FIXED_RECTANGLE",
            "geometry": {"width_m": 8.4, "depth_m": 8.4},
        },
    }

    assert _minimum_single_zone_envelope_extent(authorities) == 13_600


def test_direct_synthesis_covers_axis_direction_before_envelope_variants() -> None:
    rounds = placement._DIRECT_STRUCTURAL_VARIANT_ROUNDS

    assert len(rounds) == 12
    assert {row[0] for row in rounds} == {0, 1}
    assert {row[2] for row in rounds} == {
        "DEFAULT_SUPPORT_SIDE",
        "PERPENDICULAR_SUPPORT_SIDE_A",
        "PERPENDICULAR_SUPPORT_SIDE_B",
    }
    assert {row[3] for row in rounds} == {"POSITIVE", "NEGATIVE"}
    assert {row[4] for row in rounds} == {0, 1}
    assert {row[5] for row in rounds} == {0, -1}
    assert len(rounds) * len(BASE_LAYOUT_FAMILIES) == placement.DIRECT_SYNTHESIS_ATTEMPT_COUNT

    scheduled_families = tuple(family for _round in rounds for family in BASE_LAYOUT_FAMILIES)
    assert scheduled_families == BASE_LAYOUT_FAMILIES * len(rounds)


def test_main_skeleton_validator_checks_only_frozen_seven_zone_must_chain() -> None:
    zone_codes = placement.MAIN_PROCESS_ZONE_CODES
    placed = {
        code: PlacedRectangleV1(
            code,
            Decimal(index * 10),
            Decimal("0"),
            Decimal("10"),
            Decimal("10"),
        )
        for index, code in enumerate(zone_codes)
    }

    placement._validate_main_process_skeleton_graph(process_graph(), placed)

    displaced_coating = dict(placed)
    displaced_coating["coating_room"] = PlacedRectangleV1(
        "coating_room", Decimal("50"), Decimal("0"), Decimal("10"), Decimal("10")
    )
    with pytest.raises(LayoutAuthorityError, match="HARD_CONSTRAINT_UNSATISFIABLE"):
        placement._validate_main_process_skeleton_graph(process_graph(), displaced_coating)


def test_coating_transition_is_admitted_by_finished_band_without_sorting_edge() -> None:
    plan = construct_structured_building_plan_v1(
        boundary=_boundary(),
        obstacles=(),
        authorities=_authorities(),
        process_axis="Y",
        layout_family=LINEAR_3_BAND,
        envelope_family=RECTANGLE,
    )
    finished = next(row for row in plan.bands if row.band_code == FINISHED_SIDE_BAND)
    x0, y0, _x1, _y1 = finished.bounds_mm
    transition = PlacedRectangleV1(
        "coating_room",
        Decimal(x0) / 1000,
        Decimal(y0) / 1000,
        Decimal("10"),
        Decimal("10"),
    )

    assert plan.admits_to_band("coating_room", transition, FINISHED_SIDE_BAND)
    assert plan.admits("coating_room", transition)


def test_legacy_fallback_search_domain_is_not_mislabeled_as_a_building_envelope() -> None:
    plan = placement._legacy_compatibility_search_plan(
        boundary=_boundary(),
        obstacles=(),
        authorities=_authorities(),
        process_axis="Y",
        process_direction="POSITIVE",
        topology=STRAIGHT_LINEAR_BAND,
        main_entrance=((0, 30_000), (0, 40_000)),
    )

    assert plan.envelope.family == "LEGACY_COMPATIBILITY_SEARCH_DOMAIN"
    assert plan.envelope.extension_reason == "SITE_SEARCH_REGION_ONLY_NOT_A_BUILDING_ENVELOPE"
    assert plan.band_for_zone("packaging_material_storage").bounds_mm == plan.envelope.bounds_mm
    assert plan.band_for_zone("office").bounds_mm == plan.envelope.bounds_mm
    assert plan.band_for_zone("raw_fruit_buffer").bounds_mm != plan.envelope.bounds_mm
    assert plan.layout_family == LINEAR_3_BAND


def test_band_room_may_span_adjacent_region_tiles_but_not_a_gap() -> None:
    tiled = FunctionalBandV1(
        band_code=RAW_SIDE_BAND,
        group_code="RAW_SIDE_GROUP",
        zone_codes=("raw_fruit_buffer",),
        bounds_mm=(0, 0, 30_000, 10_000),
        process_axis="X",
        ordering_role="UPSTREAM",
        regions_mm=((0, 0, 12_000, 10_000), (12_000, 0, 30_000, 10_000)),
    )
    across_join = PlacedRectangleV1(
        "raw_fruit_buffer", Decimal("5"), Decimal("1"), Decimal("20"), Decimal("8")
    )
    assert tiled.contains(across_join)

    with_gap = FunctionalBandV1(
        **{
            **tiled.__dict__,
            "regions_mm": ((0, 0, 12_000, 10_000), (13_000, 0, 30_000, 10_000)),
        }
    )
    assert not with_gap.contains(across_join)


def test_direct_band_packer_uses_each_exact_envelope_region() -> None:
    authorities = _authorities()
    boundary = _boundary()
    plan = construct_structured_building_plan_v1(
        boundary=boundary,
        obstacles=(),
        authorities=authorities,
        process_axis="X",
        layout_family=LINEAR_3_BAND,
        envelope_family=RECTANGLE,
    )
    target_band = plan.band_for_zone("sorting_packaging_room")
    regions = ((50_000, 0, 60_000, 10_000), (70_000, 20_000, 80_000, 30_000))
    replacement = replace(
        target_band,
        bounds_mm=(50_000, 0, 80_000, 30_000),
        regions_mm=regions,
    )
    plan = replace(
        plan,
        bands=tuple(
            replacement if row.band_code == PROCESS_CORE_BAND else row for row in plan.bands
        ),
    )
    fixed = {
        "blocking_zone": PlacedRectangleV1(
            "blocking_zone", Decimal("50"), Decimal("0"), Decimal("10"), Decimal("10")
        )
    }
    context = SimpleNamespace(
        authorities=authorities,
        boundary=boundary,
        boundary_bounds=(0, 0, 100_000, 80_000),
        obstacles=(),
    )

    rows = placement.synthesize_band_geometry(
        context,
        plan,
        PROCESS_CORE_BAND,
        ("sorting_packaging_room",),
        packing_axis="X",
        reverse_order=False,
        cross_alignment="LOW",
        fixed_placements=fixed,
    )

    assert rows
    assert rows[0]["sorting_packaging_room"].bounds_mm == (70_000, 20_000, 80_000, 30_000)


def test_must_chain_roots_include_band_regions_even_with_fixed_neighbors() -> None:
    authorities = _authorities()
    plan = construct_structured_building_plan_v1(
        boundary=_boundary(),
        obstacles=(),
        authorities=authorities,
        process_axis="Y",
        layout_family=LINEAR_3_BAND,
        envelope_family=RECTANGLE,
    )
    finished = plan.band_for_zone("secondary_precooling_room")
    regions = ((40_000, 0, 50_000, 10_000), (70_000, 20_000, 80_000, 30_000))
    replacement = replace(finished, bounds_mm=(40_000, 0, 80_000, 30_000), regions_mm=regions)
    plan = replace(
        plan,
        bands=tuple(
            replacement if row.band_code == FINISHED_SIDE_BAND else row for row in plan.bands
        ),
    )
    context = SimpleNamespace(graph=process_graph())
    fixed = {
        "sorting_packaging_room": PlacedRectangleV1(
            "sorting_packaging_room", Decimal("30"), Decimal("0"), Decimal("10"), Decimal("10")
        )
    }

    origins = placement._band_edge_chain_origins(
        context,
        plan,
        FINISHED_SIDE_BAND,
        "secondary_precooling_room",
        10_000,
        10_000,
        fixed,
    )

    assert (70_000, 20_000) in origins


def test_finished_chain_dimension_census_includes_a_compact_turn_pattern() -> None:
    options = _must_chain_band_dimension_options(
        _authorities(),
        (
            "secondary_precooling_room",
            "coating_room",
            "finished_goods_room",
            "shipping_channel",
        ),
        "X",
    )

    assert (20_000, 20_000) in options


def test_band_chain_synthesizer_constructs_joint_turning_must_path() -> None:
    authorities = _authorities()
    boundary = _boundary()
    plan = construct_structured_building_plan_v1(
        boundary=boundary,
        obstacles=(),
        authorities=authorities,
        process_axis="X",
        layout_family=LINEAR_3_BAND,
        envelope_family=RECTANGLE,
    )
    context = SimpleNamespace(
        authorities=authorities,
        graph=process_graph(),
        boundary=boundary,
        boundary_bounds=(0, 0, 100_000, 80_000),
        obstacles=(),
        structural_topology=STRAIGHT_LINEAR_BAND,
    )
    zones = (
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )
    rows = placement.synthesize_must_chain_band_geometry(
        context,
        plan,
        FINISHED_SIDE_BAND,
        zones,
        transition_zone_codes=frozenset({"coating_room"}),
        result_limit=12,
    )

    assert rows
    turning_rows = []
    for row in rows:
        assert all(
            placement.rectangles_share_positive_edge(row[first], row[second])
            for first, second in zip(zones, zones[1:], strict=False)
        )
        bounds = tuple(rectangle.bounds_mm for rectangle in row.values())
        span_x = max(value[2] for value in bounds) - min(value[0] for value in bounds)
        span_y = max(value[3] for value in bounds) - min(value[1] for value in bounds)
        if max(span_x, span_y) <= 30_000 and min(span_x, span_y) >= 20_000:
            turning_rows.append(row)

    assert turning_rows


def test_production_band_chain_variants_are_finite_and_deterministic() -> None:
    authorities = _authorities()
    boundary = _boundary()
    plan = construct_structured_building_plan_v1(
        boundary=boundary,
        obstacles=(),
        authorities=authorities,
        process_axis="X",
        layout_family=LINEAR_3_BAND,
        envelope_family=RECTANGLE,
    )
    context = SimpleNamespace(
        authorities=authorities,
        graph=process_graph(),
        boundary=boundary,
        boundary_bounds=(0, 0, 100_000, 80_000),
        obstacles=(),
    )
    zones = (
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )

    def run_variant(index: int) -> tuple[tuple[str, tuple[int, ...]], ...]:
        rows = placement.synthesize_must_chain_band_geometry(
            context,
            plan,
            FINISHED_SIDE_BAND,
            zones,
            transition_zone_codes=frozenset({"coating_room"}),
            construction_variant_index=index,
            result_limit=1,
        )
        assert len(rows) <= 1
        if not rows:
            return ()
        return tuple(
            (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
            for code, rectangle in sorted(rows[0].items())
        )

    first = run_variant(0)
    assert run_variant(0) == first
    variants = {signature for index in range(12) if (signature := run_variant(index))}

    assert variants
    assert len(variants) > 1


def test_linear_family_synthesizes_full_must_chain_across_planned_bands() -> None:
    authorities = _authorities()
    boundary = _boundary()
    plan = construct_structured_building_plan_v1(
        boundary=boundary,
        obstacles=(),
        authorities=authorities,
        process_axis="X",
        process_direction="POSITIVE",
        layout_family=LINEAR_3_BAND,
        envelope_family=RECTANGLE,
    )
    context = SimpleNamespace(
        authorities=authorities,
        graph=process_graph(),
        boundary=boundary,
        boundary_bounds=(0, 0, 100_000, 80_000),
        obstacles=(),
        structural_topology=STRAIGHT_LINEAR_BAND,
    )

    rows = placement._linear_3_band_geometry(context, plan, 0, failure_reasons=[])

    assert rows
    assert set(rows[0]) == set(placement.PLACEMENT_ZONE_ORDER[:7])
    assert all(plan.admits(code, rectangle) for code, rectangle in rows[0].items())
    assert all(
        placement.rectangles_share_positive_edge(rows[0][first], rows[0][second])
        for first, second in zip(
            placement.PLACEMENT_ZONE_ORDER[:6], placement.PLACEMENT_ZONE_ORDER[1:7], strict=True
        )
    )
