"""P0C Golden abstraction integrity and offline-metric tests."""

from __future__ import annotations

import json
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
    assert reference["building_outline"]["class"] == "RECTANGLE"
    assert reference["building_outline"]["site_context_class"] == "IRREGULAR_SITE_CONSTRAINED"
    assert reference_metrics(reference)["functional_grouping"] == "PASS_QUALITATIVE"


def test_outline_classifier_distinguishes_rectangle_l_shape_and_reflex_from_notch() -> None:
    rectangle = orthogonal_outline_facts([[0, 0], [1, 0], [1, 1], [0, 1]])
    simple_l = orthogonal_outline_facts(
        [[0, 0], [1, 0], [1, 0.4], [0.4, 0.4], [0.4, 1], [0, 1]]
    )
    u_outline = orthogonal_outline_facts(
        [[0, 0], [1, 0], [1, 1], [0.7, 1], [0.7, 0.3], [0.3, 0.3], [0.3, 1], [0, 1]]
    )
    assert classify_outline_v1(rectangle) == "RECTANGLE"
    assert classify_outline_v1(simple_l) == "SIMPLE_L"
    assert classify_outline_v1(u_outline) == "COMPLEX_L"
    assert u_outline["reflex_corner_count"] == 2
    assert u_outline["notch_count"] == 1
    assert u_outline["notch_count"] != u_outline["reflex_corner_count"]
    assert classify_outline_v1(simple_l, site_constrained_exception=True) == "IRREGULAR_SITE_CONSTRAINED"
    assert classify_outline_v1(simple_l, narrow_neck_confirmed=True) == "NARROW_NECK"
    assert classify_outline_v1(simple_l, owner_confirmed_unmotivated_appendage=True) == "ISOLATED_APPENDAGE"
    assert classify_outline_v1(rectangle, component_count=2) == "MULTI_COMPONENT"


def test_golden_overlay_review_pack_is_present_and_not_runtime_input() -> None:
    manifest_path = REFERENCE_DIR / "overlay-review-pack.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["abstraction_visual_overlay_created"] is True
    assert manifest["owner_visual_review"] == "PENDING"
    assert manifest["runtime_project_input"] is False
    assert len(manifest["overlays"]) == 5
    for overlay in manifest["overlays"]:
        png_path = REFERENCE_DIR / overlay["png"]
        assert png_path.is_file() and png_path.stat().st_size > 0


def test_xinzhao_negative_uses_existing_structured_evidence_without_inventing_missing_facts() -> None:
    matrix_path = Path(__file__).resolve().parents[2] / ".." / "docs/tasks/evidence/v2_2_2_p0c/calibration-matrix.json"
    matrix: dict[str, Any] = json.loads(matrix_path.resolve().read_text(encoding="utf-8"))
    row = next(item for item in matrix["fixtures"] if item["fixture_id"] == "XINZHAO_20T_SITE_LAYOUT_INPUT_V3_OWNER_ACCEPTANCE")
    assert row["owner_label"] == "FAIL"
    assert row["grid_alignment_rate"] == "0.4"
    assert row["bounding_rectangle_occupancy"] == "0.5792454589543597230802131883"
    assert row["reflex_corner_count"] == 16
    assert row["depth_alignment_rate"] == "UNAVAILABLE"
    assert str(row["backtrack_count"]).startswith("UNAVAILABLE")
    assert matrix["numeric_threshold_calibration_ready"] is False
