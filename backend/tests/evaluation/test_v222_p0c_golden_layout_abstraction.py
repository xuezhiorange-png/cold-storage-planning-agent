"""P0C Golden abstraction integrity and offline-metric tests."""

from __future__ import annotations

import json
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import Any

from tests.evaluation.v222_p0c_golden_layout_metrics import (
    REFERENCE_DIR,
    REFERENCE_IDS,
    all_positive_metrics,
    classify_outline_v1,
    load_reference,
    orthogonal_outline_facts,
    reference_metrics,
)

_ALLOWED_ROLES = {
    "PRIMARY_PRECOOL",
    "SECONDARY_PRECOOL",
    "SORTING_PACKAGING",
    "FINISHED_STORAGE",
    "PACKAGING_SUPPORT",
    "SECONDARY_PRODUCT_SUPPORT",
    "FROZEN_SUPPORT",
    "PERSONNEL_SUPPORT",
    "OTHER_SUPPORT",
    "UNAVAILABLE",
}


def test_five_positive_abstractions_are_normalized_non_authoritative_and_stable() -> None:
    assert len(REFERENCE_IDS) == 5
    for reference_id in REFERENCE_IDS:
        first = load_reference(reference_id)
        second = load_reference(reference_id)
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
        assert first["owner_label"] == "PASS"
        assert first["reference_derived"] is True
        assert first["engineering_authority"] is False
        assert first["runtime_project_input"] is False
        assert first["normalization_version"] == "1.0.0"
        assert first["normalization"]["real_dimensions_recorded"] is False
        assert first["normalization"]["source_bbox_is_approximate_visual_trace"] is True
        for role in (zone["semantic_role"] for zone in first["major_zone_rectangles"]):
            assert role in _ALLOWED_ROLES
        page_bbox = first["normalization"]["primary_envelope_page_bbox_norm"]
        assert len(page_bbox) == 4
        assert all(0 <= value <= 1 for value in page_bbox)


def test_metric_evidence_does_not_promote_coarse_envelopes_to_room_facts() -> None:
    rows = all_positive_metrics()
    assert [row["fixture_id"] for row in rows] == list(REFERENCE_IDS)
    for row in rows:
        assert 0 <= float(row["grid_alignment_rate"]) <= 1
        assert row["grid_alignment_evidence"] == "REFERENCE_DERIVED_PROVISIONAL_GROUP_ENVELOPES"
        assert row["depth_alignment_rate"] == "UNAVAILABLE_ROOM_LEVEL_GEOMETRY_NOT_PRESENT"
        assert row["bounding_rectangle_occupancy"] == "UNAVAILABLE_COARSE_ENVELOPE_ONLY"
        assert row["reflex_corner_count"] == "UNAVAILABLE_COARSE_ENVELOPE_ONLY"
        assert row["notch_count"] == "UNAVAILABLE_COARSE_ENVELOPE_ONLY"
        assert row["appendage_count"] == "UNAVAILABLE_COMPONENT_PURPOSE_AND_NECK_FACTS"
        assert row["main_flow_backtrack_count"] == "UNAVAILABLE_NO_AUTHORITATIVE_ROUTE_TRACE"
        assert row["main_flow_turn_count"] == "UNAVAILABLE_NO_AUTHORITATIVE_ROUTE_TRACE"


def test_mouding_keeps_site_constraint_separate_from_building_shape() -> None:
    reference = load_reference("GD-003_MOUDING")
    assert reference["building_outline"]["class"] == "ORTHOGONAL_STEPPED_COMPOSITION"
    assert reference["building_outline"]["classification_status"] == (
        "APPROXIMATE_OVERLAY_ONLY_NOT_EXACT_CLASSIFIER_INPUT"
    )
    assert reference["building_outline"]["site_context_class"] == "IRREGULAR_SITE_CONSTRAINED"
    assert reference["site_boundary_context"]["class"] == "IRREGULAR_SITE_CONTEXT"
    assert len(reference["site_boundary_context"]["polygons"][0]) > 4
    assert len(reference["building_outline"]["polygons"][0]) > 4
    assert (
        reference["principal_building_mass"]["source_geometry_ref"] == "building_outline.polygons"
    )
    assert reference_metrics(reference)["functional_grouping"] == "PASS_QUALITATIVE"


def _inside_or_on_orthogonal_polygon(
    point: tuple[Decimal, Decimal], polygon: list[list[object]]
) -> bool:
    px, py = point
    vertices = [(Decimal(str(x)), Decimal(str(y))) for x, y in polygon]
    inside = False
    for index, (x1, y1) in enumerate(vertices):
        x2, y2 = vertices[(index + 1) % len(vertices)]
        if x1 == x2 and min(y1, y2) <= py <= max(y1, y2) and px == x1:
            return True
        if y1 == y2 and min(x1, x2) <= px <= max(x1, x2) and py == y1:
            return True
        if x1 == x2 and min(y1, y2) <= py < max(y1, y2) and x1 > px:
            inside = not inside
    return inside


def _rect_within_orthogonal_polygon(rect: list[object], polygon: list[list[object]]) -> bool:
    x, y, width, height = (Decimal(str(value)) for value in rect)
    x2, y2 = x + width, y + height
    vertices = [(Decimal(str(px)), Decimal(str(py))) for px, py in polygon]
    corners = ((x, y), (x2, y), (x2, y2), (x, y2))
    if not all(_inside_or_on_orthogonal_polygon(corner, polygon) for corner in corners):
        return False
    x_breaks = sorted({x, x2, *(px for px, _ in vertices if x < px < x2)})
    y_breaks = sorted({y, y2, *(py for _, py in vertices if y < py < y2)})
    return all(
        _inside_or_on_orthogonal_polygon(((left + right) / 2, (top + bottom) / 2), polygon)
        for left, right in pairwise(x_breaks)
        for top, bottom in pairwise(y_breaks)
    )


def _local_rect_to_source_page(
    rect: list[object], page_bbox: list[object]
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    left, top, right, bottom = (Decimal(str(value)) for value in page_bbox)
    x, y, width, height = (Decimal(str(value)) for value in rect)
    return (
        left + x * (right - left),
        top + y * (bottom - top),
        left + (x + width) * (right - left),
        top + (y + height) * (bottom - top),
    )


def _bbox_overlap_ratio(
    first: tuple[Decimal, Decimal, Decimal, Decimal],
    second: tuple[Decimal, Decimal, Decimal, Decimal],
) -> Decimal:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(Decimal(0), right - left) * max(Decimal(0), bottom - top)
    area = (first[2] - first[0]) * (first[3] - first[1])
    return intersection / area


def test_mouding_major_groups_align_to_one_principal_building_source_bbox() -> None:
    reference = load_reference("GD-003_MOUDING")
    page_bbox = reference["normalization"]["primary_envelope_page_bbox_norm"]
    assert reference["principal_building_mass"]["source_page_bbox_norm"] == page_bbox
    outline = reference["building_outline"]["polygons"][0]
    groups = reference["major_zone_rectangles"]
    assert {group["functional_group"] for group in groups} >= {
        "RAW_SIDE_GROUP",
        "PROCESSING_CORE_GROUP",
        "FINISHED_SIDE_GROUP",
        "COLD_STORAGE_GROUP",
        "SUPPORT_GROUP",
    }
    assert all(_rect_within_orthogonal_polygon(group["rect"], outline) for group in groups)


def test_mouding_finished_and_storage_groups_stay_inside_mass_and_away_from_table() -> None:
    reference = load_reference("GD-003_MOUDING")
    page_bbox = reference["normalization"]["primary_envelope_page_bbox_norm"]
    outline = reference["building_outline"]["polygons"][0]
    furniture = next(
        region
        for region in reference["known_drawing_furniture_regions"]
        if region["id"] == "RIGHT_PAGE_AREA_TABLE"
    )
    table_values = [Decimal(str(value)) for value in furniture["page_bbox_norm"]]
    assert len(table_values) == 4
    table_bbox = (table_values[0], table_values[1], table_values[2], table_values[3])
    groups = reference["major_zone_rectangles"]
    by_id = {group["id"]: group for group in groups}
    for group in groups:
        mapped_bbox = _local_rect_to_source_page(group["rect"], page_bbox)
        assert _bbox_overlap_ratio(mapped_bbox, table_bbox) < Decimal("0.5")
    for group_id in ("finished_side_bank", "secondary_storage_band"):
        group = by_id[group_id]
        assert _rect_within_orthogonal_polygon(group["rect"], outline)
    assert furniture["engineering_authority"] is False
    assert reference["reference_derived"] is True
    assert reference["engineering_authority"] is False
    assert reference["approximate_group_envelope"] is True


def test_owner_corrections_make_zhuyuan_process_hall_and_annex_explicit() -> None:
    reference = load_reference("GD-001_ZHUYUAN")
    assert reference["overlay_correction"]["task_id"] == ("V2_2_2_P0C_OWNER_OVERLAY_CORRECTION_R1")
    assert reference["reference_derived"] is True
    assert reference["engineering_authority"] is False
    assert reference["approximate_group_envelope"] is True
    process = next(
        group
        for group in reference["major_zone_rectangles"]
        if group["id"] == "dominant_processing_hall"
    )
    assert process["functional_group"] == "PROCESSING_CORE_GROUP"
    assert process["rect"][2] >= process["rect"][3] * 2
    assert {group["functional_group"] for group in reference["major_zone_rectangles"]} >= {
        "RAW_SIDE_GROUP",
        "COLD_STORAGE_GROUP",
        "PROCESSING_CORE_GROUP",
        "FINISHED_SIDE_GROUP",
        "SUPPORT_GROUP",
    }
    annex = reference["excluded_areas"][0]
    assert annex["kind"] == "ANNEX"
    assert annex["exclusion_reason"]
    assert (
        min(point[0] for point in annex["polygon_page_norm"])
        > (reference["normalization"]["primary_envelope_page_bbox_norm"][2])
    )


def test_owner_correction_keeps_xiaoxiang_as_one_central_process_hub() -> None:
    reference = load_reference("GD-002_XIAOXIANG")
    process_groups = [
        group
        for group in reference["major_zone_rectangles"]
        if group["functional_group"] == "PROCESSING_CORE_GROUP"
    ]
    assert len(process_groups) == 1
    assert process_groups[0]["id"] == "central_process_hub"
    assert process_groups[0]["display_label"] == "CENTRAL PROCESS HUB"
    assert process_groups[0]["rect"][2] > process_groups[0]["rect"][3]
    cold_groups = [
        group
        for group in reference["major_zone_rectangles"]
        if group["functional_group"] == "COLD_STORAGE_GROUP"
    ]
    assert {group["id"] for group in cold_groups} == {
        "north_cold_storage_bank",
        "west_storage_branch",
        "east_storage_branch",
    }
    assert reference["process_core"]["form"] == "SINGLE_CONNECTED_CENTRAL_PROCESS_HUB"


def test_outline_classifier_distinguishes_rectangle_l_shape_and_reflex_from_notch() -> None:
    rectangle = orthogonal_outline_facts([[0, 0], [1, 0], [1, 1], [0, 1]])
    simple_l = orthogonal_outline_facts([[0, 0], [1, 0], [1, 0.4], [0.4, 0.4], [0.4, 1], [0, 1]])
    u_outline = orthogonal_outline_facts(
        [[0, 0], [1, 0], [1, 1], [0.7, 1], [0.7, 0.3], [0.3, 0.3], [0.3, 1], [0, 1]]
    )
    assert classify_outline_v1(rectangle) == "RECTANGLE"
    assert classify_outline_v1(simple_l) == "SIMPLE_L"
    assert classify_outline_v1(u_outline) == "COMPLEX_L"
    assert u_outline["reflex_corner_count"] == 2
    assert u_outline["notch_count"] == 1
    assert u_outline["notch_count"] != u_outline["reflex_corner_count"]
    assert (
        classify_outline_v1(simple_l, site_constrained_exception=True)
        == "IRREGULAR_SITE_CONSTRAINED"
    )
    assert classify_outline_v1(simple_l, narrow_neck_confirmed=True) == "NARROW_NECK"
    assert (
        classify_outline_v1(simple_l, owner_confirmed_unmotivated_appendage=True)
        == "ISOLATED_APPENDAGE"
    )
    assert classify_outline_v1(rectangle, component_count=2) == "MULTI_COMPONENT"


def test_golden_overlay_review_pack_is_present_and_not_runtime_input() -> None:
    manifest_path = REFERENCE_DIR / "overlay-review-pack.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["abstraction_visual_overlay_created"] is True
    assert manifest["owner_visual_review"] == "PASS"
    assert manifest["runtime_project_input"] is False
    assert len(manifest["overlays"]) == 5
    for overlay in manifest["overlays"]:
        png_path = REFERENCE_DIR / overlay["png"]
        assert png_path.is_file() and png_path.stat().st_size > 0


def test_xinzhao_negative_uses_existing_structured_evidence_without_inventing_missing_facts() -> (
    None
):
    matrix_path = (
        Path(__file__).resolve().parents[2]
        / ".."
        / "docs/tasks/evidence/v2_2_2_p0c/calibration-matrix.json"
    )
    matrix: dict[str, Any] = json.loads(matrix_path.resolve().read_text(encoding="utf-8"))
    row = next(
        item
        for item in matrix["fixtures"]
        if item["fixture_id"] == "XINZHAO_20T_SITE_LAYOUT_INPUT_V3_OWNER_ACCEPTANCE"
    )
    assert row["owner_label"] == "FAIL"
    assert row["grid_alignment_rate"] == "0.4"
    assert row["bounding_rectangle_occupancy"] == "0.5792454589543597230802131883"
    assert row["reflex_corner_count"] == 16
    assert row["depth_alignment_rate"] == "UNAVAILABLE"
    assert str(row["backtrack_count"]).startswith("UNAVAILABLE")
    assert matrix["numeric_threshold_calibration_ready"] is False
