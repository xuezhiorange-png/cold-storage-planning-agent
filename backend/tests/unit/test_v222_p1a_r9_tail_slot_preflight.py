"""Exact event-set tests for the R9 necessary tail-slot predicate."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    normalize_polygon,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
)
from cold_storage.modules.layout.domain.tail_slot_feasibility import (
    EVENT_COMPLETENESS_UNAVAILABLE,
    EXACT_ORTHOGONAL_EVENT_ENUMERATION,
    evaluate_tail_zone_slot_feasibility_v1,
)

ROOT = Path(__file__).resolve().parents[3]
R8_EVIDENCE = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r8_tail_feasibility_search.json"
R5_SELECTED_LAYOUT = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r5_selected_layout.json"
XINZHAO_INPUT = ROOT / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"


def _rect_mm(
    code: str,
    x: int,
    y: int,
    width: int,
    depth: int,
    rotation: int = 0,
) -> PlacedRectangleV1:
    return PlacedRectangleV1(
        code,
        Decimal(x) / 1000,
        Decimal(y) / 1000,
        Decimal(width) / 1000,
        Decimal(depth) / 1000,
        rotation,
    )


def _polygon(points: list[tuple[int, int]]) -> PolygonMM:
    return tuple(points)


def _fixture_slot_inputs() -> tuple[PolygonMM, tuple[PolygonMM, ...], int, int]:
    input_body = json.loads(XINZHAO_INPUT.read_text(encoding="utf-8"))
    site_constraints = input_body["site_constraints"]
    boundary = normalize_polygon(site_constraints["site_boundary"])
    obstacles = tuple(normalize_polygon(row) for row in site_constraints["no_build_zones"])
    return boundary, obstacles, 17_300, 14_500


def _r8_rectangles() -> tuple[PlacedRectangleV1, ...]:
    body = json.loads(R8_EVIDENCE.read_text(encoding="utf-8"))
    rectangles = []
    for code, bounds in sorted(body["fixed_main_process_rectangles"].items()):
        left, bottom, right, top = bounds
        rectangles.append(_rect_mm(code, left, bottom, right - left, top - bottom))
    return tuple(rectangles)


def _r5_rectangles() -> tuple[PlacedRectangleV1, ...]:
    body = json.loads(R5_SELECTED_LAYOUT.read_text(encoding="utf-8"))
    return tuple(
        PlacedRectangleV1(
            str(row["zone_code"]),
            Decimal(str(row["x"])),
            Decimal(str(row["y"])),
            Decimal(str(row["width_m"])),
            Decimal(str(row["depth_m"])),
            int(row["rotation_deg"]),
        )
        for row in body["zones"]
        if row["zone_code"]
        in {
            "raw_fruit_buffer",
            "primary_precooling_room",
            "sorting_packaging_room",
            "secondary_precooling_room",
            "coating_room",
            "finished_goods_room",
            "shipping_channel",
        }
    )


def _brute_force_slot_exists(
    boundary: PolygonMM,
    obstacles: tuple[PolygonMM, ...],
    fixed: tuple[PlacedRectangleV1, ...],
    width_mm: int,
    depth_mm: int,
) -> bool:
    min_x = min(point[0] for point in boundary)
    min_y = min(point[1] for point in boundary)
    max_x = max(point[0] for point in boundary)
    max_y = max(point[1] for point in boundary)
    for rotation in (0, 90):
        bounds_width, bounds_depth = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        for x in range(min_x, max_x - bounds_width + 1):
            for y in range(min_y, max_y - bounds_depth + 1):
                candidate = _rect_mm(
                    "packaging_material_storage", x, y, width_mm, depth_mm, rotation
                )
                if not rectangle_inside_polygon(candidate, boundary):
                    continue
                if any(rectangle_intersects_closed_obstacle(candidate, item) for item in obstacles):
                    continue
                if any(rectangles_overlap(candidate, item) for item in fixed):
                    continue
                return True
    return False


def test_r9_finite_events_match_exhaustive_small_orthogonal_lattice_cases() -> None:
    cases: tuple[tuple[PolygonMM, tuple[PolygonMM, ...], tuple[PlacedRectangleV1, ...]], ...] = (
        (
            _polygon(((0, 0), (12, 0), (12, 10), (0, 10))),
            (_polygon(((4, 0), (8, 0), (8, 10), (4, 10))),),
            (_rect_mm("fixed", 0, 0, 2, 2),),
        ),
        (
            _polygon(((0, 0), (12, 0), (12, 4), (7, 4), (7, 10), (0, 10))),
            (_polygon(((2, 2), (5, 2), (5, 5), (2, 5))),),
            (_rect_mm("fixed", 8, 0, 2, 3),),
        ),
    )
    for boundary, obstacles, fixed in cases:
        result = evaluate_tail_zone_slot_feasibility_v1(
            zone_code="packaging_material_storage",
            dimension_variants=((3, 2, 0), (3, 2, 90)),
            dimension_authority_complete=True,
            boundary=boundary,
            obstacles=obstacles,
            fixed_main_process_rectangles=fixed,
        )
        assert result.proof_mode == EXACT_ORTHOGONAL_EVENT_ENUMERATION
        assert result.legal_slot_exists is _brute_force_slot_exists(
            boundary, obstacles, fixed, 3, 2
        )


def test_r9_declines_to_prune_nonorthogonal_or_incomplete_authority() -> None:
    diagonal_boundary = _polygon(((0, 0), (10, 0), (8, 10), (0, 10)))
    result = evaluate_tail_zone_slot_feasibility_v1(
        zone_code="packaging_material_storage",
        dimension_variants=((2, 3, 0), (2, 3, 90)),
        dimension_authority_complete=True,
        boundary=diagonal_boundary,
        obstacles=(),
        fixed_main_process_rectangles=(),
    )

    assert result.legal_slot_exists is None
    assert result.proof_mode == EVENT_COMPLETENESS_UNAVAILABLE

    flexible_dimensions = evaluate_tail_zone_slot_feasibility_v1(
        zone_code="packaging_material_storage",
        dimension_variants=((2, 3, 0), (2, 3, 90)),
        dimension_authority_complete=False,
        boundary=_polygon(((0, 0), (10, 0), (10, 10), (0, 10))),
        obstacles=(),
        fixed_main_process_rectangles=(),
    )
    assert flexible_dimensions.legal_slot_exists is None


def test_r8_956e_fixed_skeleton_has_no_exact_packaging_slot() -> None:
    boundary, obstacles, width_mm, depth_mm = _fixture_slot_inputs()
    result = evaluate_tail_zone_slot_feasibility_v1(
        zone_code="packaging_material_storage",
        dimension_variants=((width_mm, depth_mm, 0), (width_mm, depth_mm, 90)),
        dimension_authority_complete=True,
        boundary=boundary,
        obstacles=obstacles,
        fixed_main_process_rectangles=_r8_rectangles(),
    )

    assert result.legal_slot_exists is False
    assert result.proof_mode == EXACT_ORTHOGONAL_EVENT_ENUMERATION
    assert result.orientation_count == 2
    assert result.evaluated_placement_count > 0
    assert result.first_witness_rectangle is None


def test_r5_55589_hard_valid_skeleton_has_an_exact_packaging_slot() -> None:
    boundary, obstacles, width_mm, depth_mm = _fixture_slot_inputs()
    result = evaluate_tail_zone_slot_feasibility_v1(
        zone_code="packaging_material_storage",
        dimension_variants=((width_mm, depth_mm, 0), (width_mm, depth_mm, 90)),
        dimension_authority_complete=True,
        boundary=boundary,
        obstacles=obstacles,
        fixed_main_process_rectangles=_r5_rectangles(),
    )

    assert result.legal_slot_exists is True
    assert result.proof_mode == EXACT_ORTHOGONAL_EVENT_ENUMERATION
    assert result.first_witness_rectangle is not None


def test_tail_slot_result_is_internal_and_has_versioned_machine_fields() -> None:
    result = evaluate_tail_zone_slot_feasibility_v1(
        zone_code="packaging_material_storage",
        dimension_variants=((2, 3, 0), (2, 3, 90)),
        dimension_authority_complete=True,
        boundary=_polygon(((0, 0), (10, 0), (10, 10), (0, 10))),
        obstacles=(),
        fixed_main_process_rectangles=(),
    )

    body: dict[str, Any] = result.to_dict()
    assert body["identity"] == "tail-zone-slot-feasibility@1.0.0"
    assert body["zone_code"] == "packaging_material_storage"
    assert body["legal_slot_exists"] is True
    assert body["proof_mode"] == EXACT_ORTHOGONAL_EVENT_ENUMERATION
