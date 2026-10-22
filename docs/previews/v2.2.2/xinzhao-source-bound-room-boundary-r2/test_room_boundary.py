"""Deterministic source/topology tests; no engineering solver entrypoint."""

from __future__ import annotations

import copy
import hashlib
import json
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from typing import Any

import fitz
import pytest

from offline_boundary_review import analyze, r1_reader, svg
from offline_room_boundary import (
    boundary_result,
    encode,
    point,
    source_digest,
    source_segment,
    topology,
    transform,
)


def edges(vertices: list[list[Any]]) -> list[Any]:
    points = [point(v) for v in vertices]
    return list(zip(points, points[1:] + points[:1], strict=True))


def fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    segments = [
        ((0, 0), (10, 0)),
        ((10, 0), (10, 4)),
        ((10, 6), (10, 10)),
        ((10, 10), (0, 10)),
        ((0, 10), (0, 0)),
    ]
    vectors = [{"items": [["l", list(a), list(b)]]} for a, b in segments]
    vectors += [
        {"items": [["l", [10, 4], [8, 4]]]},
        {"items": [["c", [8, 4], [8, 5], [9, 6], [10, 6]]]},
    ]
    source = {
        "source_sha256": "synthetic",
        "pdf_page_count": 1,
        "pages": [{"rotation_matrix": [1, 0, 0, 1, 0, 0], "vectors": vectors}],
    }
    refs = [
        {
            "path_id": n,
            "item_id": 0,
            "kind": "WALL_SEGMENT",
            "review_basis": "SYNTHETIC",
        }
        for n in range(5)
    ]
    selection = {
        "room_id": "synthetic",
        "source_room_id": "test",
        "room_name": "Synthetic",
        "source_page": 1,
        "source_sha256": "synthetic",
        "source_roi": [0, 0, 10, 10],
        "face_refs": refs,
        "missing_dimension_evidence": ["FINISH_BUILDUP"],
        "doors": [
            {
                "door_id": "test-door",
                "drawing_mark": "M0920",
                "review_basis": "SYNTHETIC",
                "a": {"ref": refs[1], "end": 1},
                "b": {"ref": refs[2], "end": 0},
                "leaf_ref": {"path_id": 5, "item_id": 0},
                "swing_ref": {"path_id": 6, "item_id": 0},
            }
        ],
    }
    return source, selection


def test_closed_rectangle_exact_area() -> None:
    r = topology(edges([[0, 0], [4, 0], [4, 3], [0, 3]]))
    assert r["closed"] and r["exact_area_pdf_points_squared"] == "12"


def test_nonrectangular_not_bounding_box_area() -> None:
    r = topology(edges([[0, 0], [4, 0], [4, 1], [1, 1], [1, 4], [0, 4]]))
    assert r["closed"] and r["exact_area_pdf_points_squared"] == "7"


def test_visual_closeness_never_snapped() -> None:
    e = edges([[0, 0], [4, 0], [4, 3], [0, 3]])
    e[-1] = (e[-1][0], point([0, "1/1000000"]))
    r = topology(e)
    assert not r["closed"] and len(r["unbound_endpoints"]) == 2
    assert r["exact_area_pdf_points_squared"] is None


@pytest.mark.parametrize(
    "case", ["duplicate", "crossing", "branch", "zero", "diagonal"]
)
def test_invalid_topology(case: str) -> None:
    e = edges([[0, 0], [4, 0], [4, 4], [0, 4]])
    if case == "duplicate":
        e.append(e[0])
    if case == "crossing":
        e.append((point([-1, 2]), point([5, 2])))
    if case == "branch":
        e.append((point([4, 0]), point([5, 0])))
    if case == "zero":
        e.append((point([0, 0]), point([0, 0])))
    if case == "diagonal":
        e.append((point([0, 0]), point([1, 1])))
    assert not topology(e)["closed"]


def test_duplicate_vertex_touch_rejected() -> None:
    r = topology(
        edges([[0, 0], [2, 0], [2, 2], [0, 2], [0, 0], [-2, 0], [-2, -2], [0, -2]])
    )
    assert not r["closed"]


def test_column_or_well_ring_not_silently_ignored() -> None:
    outer = edges([[0, 0], [10, 0], [10, 10], [0, 10]])
    well = edges([[2, 2], [3, 2], [3, 3], [2, 3]])
    r = topology(outer + well)
    assert not r["closed"] and "MULTIPLE_DISCONNECTED_RINGS" in r["issues"]
    assert r["exact_area_pdf_points_squared"] is None


def test_source_rotation_270_exact() -> None:
    assert transform([10, 20], [0, -1, 1, 0, 0, 100]) == point([20, 90])


def test_rect_edge_has_exact_source_identity() -> None:
    page = {
        "rotation_matrix": [0, -1, 1, 0, 0, 100],
        "vectors": [{"items": [["re", [0, 10, 2, 20], 1]]}],
    }
    assert source_segment(page, {"path_id": 0, "item_id": 0, "edge": 0}) == (
        point([10, 100]),
        point([10, 98]),
    )


@pytest.mark.parametrize(
    "ref",
    [
        {"path_id": -1, "item_id": 0},
        {"path_id": 100, "item_id": 0},
        {"path_id": 0, "item_id": -1},
        {"path_id": True, "item_id": 0},
    ],
)
def test_invalid_reference_rejected(ref: dict[str, Any]) -> None:
    source, _ = fixture()
    with pytest.raises(ValueError):
        source_segment(source["pages"][0], ref)


def test_curve_never_flattened_to_room_rectangle() -> None:
    source, _ = fixture()
    with pytest.raises(ValueError, match="NONLINEAR"):
        source_segment(source["pages"][0], {"path_id": 6, "item_id": 0})


def test_explicit_door_closes_reference_not_wall() -> None:
    source, selection = fixture()
    r = boundary_result(source, selection, {"X": 100, "Y": 200})
    assert r["boundary_closed"] and not r["continuous_closed_wall_boundary"]
    assert r["geometric_area_m2"] == "2"
    assert r["door_openings"][0]["derived_source_gap_mm"] == "400"
    assert r["door_openings"][0]["clear_door_width_mm"] is None
    assert r["finished_clear_area_m2"] is None
    assert r["wall_envelope_area_m2"] is None and r["usable_floor_area_m2"] is None


def test_unknown_gap_no_automatic_bridge_or_area() -> None:
    source, selection = fixture()
    selection["doors"] = []
    r = boundary_result(source, selection, {"X": 100, "Y": 100})
    assert not r["boundary_closed"] and r["geometric_area_m2"] is None
    assert len(r["reference_topology"]["unbound_endpoints"]) == 2


@pytest.mark.parametrize("scales", [{}, {"X": 100}, {"Y": 200}])
def test_missing_two_axis_calibration_cannot_produce_mm(scales: dict[str, Any]) -> None:
    source, selection = fixture()
    r = boundary_result(source, selection, scales)
    assert r["geometric_area_m2"] is None
    assert r["engineering_origin_status"] == "UNVERIFIED_ROOM_LOCAL_RELATIVE_ONLY"


@pytest.mark.parametrize(
    "mutation", ["hash", "approval", "semantics", "clear-width", "endpoint", "swing"]
)
def test_false_evidence_rejected(mutation: str) -> None:
    source, s = fixture()
    if mutation == "hash":
        s["source_sha256"] = "bad"
    if mutation == "approval":
        s["engineering_approved"] = True
    if mutation == "semantics":
        s["face_refs"][0]["kind"] = "DIMENSION_LINE"
    if mutation == "clear-width":
        s["doors"][0]["clear_door_width_mm"] = 900
    if mutation == "endpoint":
        s["doors"][0]["a"]["end"] = 0
    if mutation == "swing":
        s["doors"][0]["swing_ref"] = {"path_id": 0, "item_id": 0}
    with pytest.raises(ValueError):
        boundary_result(source, s, {"X": 1, "Y": 1})


@pytest.mark.parametrize(
    "kind",
    [
        "DIMENSION_LINE",
        "RACK_OR_STORAGE_PATTERN",
        "TEXT_GLYPH_PATH",
        "EQUIPMENT_SYMBOL",
    ],
)
def test_nonarchitectural_vectors_cannot_be_selected_as_wall(kind: str) -> None:
    source, s = fixture()
    s["face_refs"][0]["kind"] = kind
    with pytest.raises(ValueError, match="NON_BOUNDARY_SEMANTICS"):
        boundary_result(source, s, {})


def test_roi_does_not_generate_boundary_or_area() -> None:
    source, s = fixture()
    a = boundary_result(source, s, {"X": 1, "Y": 1})
    s["source_roi"] = [-1000, -1000, 2000, 2000]
    b = boundary_result(source, s, {"X": 1, "Y": 1})
    assert a["boundary_vertex_sequence"] == b["boundary_vertex_sequence"]
    assert a["geometric_area_m2"] == b["geometric_area_m2"]


def test_source_bound_column_intrusion_is_not_ignored() -> None:
    source, s = fixture()
    source["pages"][0]["vectors"].append({"items": [["re", [8, 0, 10, 2], 1]]})
    col = {
        "path_id": 7,
        "item_id": 0,
        "edge": 3,
        "kind": "COLUMN_GEOMETRY",
        "review_basis": "SYNTHETIC",
    }
    bottom = {**col, "edge": 2}
    s["face_refs"][0]["source_bound_trims"] = [
        {"end": 1, "source_ref": col, "source_end": 1}
    ]
    s["face_refs"][1]["source_bound_trims"] = [
        {"end": 0, "source_ref": bottom, "source_end": 0}
    ]
    s["face_refs"] += [col, bottom]
    r = boundary_result(source, s, {"X": 100, "Y": 100})
    assert r["boundary_closed"] and r["geometric_area_m2"] == "24/25"
    assert r["finished_clear_area_m2"] is None


def test_nearby_trim_cannot_force_collinearity() -> None:
    source, s = fixture()
    source["pages"][0]["vectors"].append({"items": [["l", [8, "1/10000"], [8, 2]]]})
    ref = {
        **s["face_refs"][0],
        "source_bound_trims": [
            {"end": 1, "source_ref": {"path_id": 7, "item_id": 0}, "source_end": 0}
        ],
    }
    with pytest.raises(ValueError, match="NOT_EXACTLY_ON_ORIGINAL_SOURCE"):
        source_segment(source["pages"][0], ref)


def test_three_rooms_and_so2_not_merged() -> None:
    source, s = fixture()
    results = []
    for name in ("office", "male-changing", "female-changing"):
        room = copy.deepcopy(s)
        room["room_id"] = name
        results.append(boundary_result(source, room, {}))
    assert len({r["room_id"] for r in results}) == 3
    assert all(r["engineering_approved"] is False for r in results)
    assert all(
        r["new_owner_grant"] is False and r["native_solver_calls"] == 0 for r in results
    )


def test_r1_immutable_manifest_and_source_reader() -> None:
    extractor, validator = r1_reader()
    assert extractor.digest(b"synthetic") == source_digest(b"synthetic")
    assert (
        validator.calibrate({"display_box": [0, 0, 100, 100]}, [])["metric_transform"]
        is None
    )


def test_historical_eight_and_canonical_p1_hashes_unchanged() -> None:
    root = Path(__file__).resolve().parents[1] / "stage-b/layout-quality-baseline-01"
    manifest = json.loads((root / "source_manifest.json").read_bytes())
    for name, record in manifest["files"].items():
        assert (
            hashlib.sha256((root / name).read_bytes()).hexdigest() == record["sha256"]
        )
    assert len(list((root / "inputs").glob("*candidate*.json"))) == 8


def test_source_mismatch_fail_closed(tmp_path: Path) -> None:
    pdf = tmp_path / "source.pdf"
    with fitz.open() as doc:
        doc.new_page()
        doc.save(pdf)
    with pytest.raises(ValueError, match="SOURCE_HASH"):
        analyze(pdf, {"source_sha256": "wrong"})


def test_fractional_svg_and_json_determinism(tmp_path: Path) -> None:
    pdf = tmp_path / "source.pdf"
    with fitz.open() as doc:
        doc.new_page(width=200, height=200)
        doc.save(pdf)
    source, s = fixture()
    # A noninteger binary coordinate must survive rendering without decimal-string parsing loss.
    for vector in source["pages"][0]["vectors"]:
        for item in vector["items"]:
            for p in item[1:]:
                p[0] = Fraction(p[0]) + Fraction(1, 8)
    s["source_roi"] = [30, 30, 100, 100]
    result = boundary_result(source, s, {"X": 1, "Y": 1})
    a = svg(pdf, source, result)
    assert a == svg(pdf, source, result)
    assert encode(result) == encode(copy.deepcopy(result))
    ET.fromstring(a)
    assert b"data:image/png;base64," in a
    assert b"<script" not in a and b"http://" not in a.split(b">", 1)[1]
