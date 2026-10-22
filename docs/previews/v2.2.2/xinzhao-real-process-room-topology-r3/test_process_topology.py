"""Synthetic adapter tests; drawing bytes are checked separately in private evidence."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from offline_process_review import SCRIPT, review_html, safe_json
from offline_process_topology import analyze_source, dependencies, encode


def fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    lines = [
        ([0, 0], [10, 0]),
        ([10, 0], [10, 4]),
        ([10, 6], [10, 10]),
        ([10, 10], [0, 10]),
        ([0, 10], [0, 0]),
        ([12, 0], [22, 0]),
        ([22, 0], [22, 10]),
        ([22, 10], [12, 10]),
        ([12, 10], [12, 6]),
        ([12, 4], [12, 0]),
        ([10, 4], [12, 4]),
        ([10, 6], [12, 6]),
        ([11, 4], [11, 6]),
    ]
    source = {
        "source_sha256": "synthetic",
        "pdf_page_count": 1,
        "pages": [
            {
                "rotation_matrix": [1, 0, 0, 1, 0, 0],
                "vectors": [{"items": [["l", a, b]]} for a, b in lines],
            }
        ],
    }

    def ref(n: int) -> dict[str, Any]:
        return {
            "path_id": n,
            "item_id": 0,
            "kind": "WALL_SEGMENT",
            "review_basis": "SYNTHETIC_TEST",
        }

    def room(name: str, start: int) -> dict[str, Any]:
        return {
            "physical_room_id": name,
            "object_type": "PHYSICAL_ROOM",
            "source_room_name": "分选包装间" + name,
            "source_roi": [0, 0, 22, 10],
            "source_label_evidence": {"status": "SYNTHETIC_TEST"},
            "face_refs": [ref(n) for n in range(start, start + 5)],
            "selection_scope": "FULL_REVIEWED_PERIMETER",
            "design_temperature": {"value": [8, 11]},
            "drawing_clear_height": {"value": 3900},
            "logical_zone_candidates": ["sorting_packaging_room"],
        }

    portal = {
        "portal_id": "P1",
        "door_mark": "M0920",
        "door_type": "SYNTHETIC",
        "review_basis": "SYNTHETIC",
        "door_mark_source_region": [9, 3, 13, 7],
        "jamb_cap_refs": [ref(10), ref(11)],
        "witness_refs": [ref(12)],
        "sides": [
            {
                "room_id": "A",
                "a": {"ref": ref(1), "end": 1},
                "b": {"ref": ref(2), "end": 0},
            },
            {
                "room_id": "B",
                "a": {"ref": ref(9), "end": 0},
                "b": {"ref": ref(8), "end": 1},
            },
        ],
    }
    review = {
        "source_sha256": "synthetic",
        "rooms": [room("A", 0), room("B", 5)],
        "portals": [portal],
    }
    calibration = {
        "metric_transform": {
            "X": {"mm_per_pdf_point": "100"},
            "Y": {"mm_per_pdf_point": "200"},
        }
    }
    return source, review, calibration


def test_two_independent_faces_caps_and_reference_closure() -> None:
    source, review, calibration = fixture()
    result = analyze_source(source, review, calibration)
    assert all(r["boundary_reference_closed"] for r in result["rooms"])
    assert all(not r["continuous_wall_closed"] for r in result["rooms"])
    assert (
        result["portals"][0]["connection_status"] == "TWO_SIDE_SOURCE_BOUND_REFERENCE"
    )
    assert result["rooms"][0]["reference_area_m2"] == "2"
    assert result["graph"]["validated_material_routes"] == []


def test_one_side_is_not_two_side_or_graph_edge() -> None:
    source, review, calibration = fixture()
    review["portals"][0]["sides"] = review["portals"][0]["sides"][:1]
    result = analyze_source(source, review, calibration)
    assert result["portals"][0]["connection_status"] == "ONE_SIDE_VERIFIED"
    assert result["graph"]["edges"] == []
    assert result["rooms"][1]["reference_area_m2"] is None


@pytest.mark.parametrize(
    "problem",
    [
        "hash",
        "wrong-room",
        "same-room",
        "interval",
        "cap",
        "width",
        "approved",
        "witness",
        "not-open",
    ],
)
def test_invalid_or_forged_binding_rejected(problem: str) -> None:
    source, review, calibration = fixture()
    portal = review["portals"][0]
    if problem == "hash":
        review["source_sha256"] = "changed"
    if problem == "wrong-room":
        portal["sides"][1]["a"]["ref"]["path_id"] = 1
    if problem == "same-room":
        portal["sides"][1]["room_id"] = "A"
    if problem == "interval":
        source["pages"][0]["vectors"][9]["items"][0][1] = [12, 5]
    if problem == "cap":
        portal["jamb_cap_refs"][0]["path_id"] = 0
    if problem == "width":
        portal["verified_clear_width_mm"] = 900
    if problem == "approved":
        portal["engineering_approved"] = True
    if problem == "witness":
        portal["witness_refs"] = []
    if problem == "not-open":
        portal["sides"][0]["a"]["end"] = 0
    with pytest.raises(ValueError):
        analyze_source(source, review, calibration)


@pytest.mark.parametrize(
    "kind", ["SHARED_WALL", "DRAWING_ADJACENCY", "DECLARED_PROCESS_CONNECTION"]
)
def test_relation_does_not_become_door_or_route(kind: str) -> None:
    source, review, calibration = fixture()
    review["portals"] = []
    review["non_portal_relations"] = [
        {
            "type": kind,
            "from": "A",
            "to": "B",
            "source_refs": [
                review["rooms"][0]["face_refs"][1],
                review["rooms"][1]["face_refs"][4],
            ],
            "review_basis": "SYNTHETIC",
        }
    ]
    result = analyze_source(source, review, calibration)
    assert result["portals"] == []
    assert result["graph"]["edges"][0]["type"] == kind
    assert result["graph"]["edges"][0]["route_validated"] is False


def test_missing_door_never_bridged_and_roi_not_area() -> None:
    source, review, calibration = fixture()
    review["portals"] = []
    review["rooms"][0]["source_roi"] = [-500, -500, 500, 500]
    result = analyze_source(source, review, calibration)
    assert all(
        not r["boundary_reference_closed"] and r["reference_area_m2"] is None
        for r in result["rooms"]
    )


def test_internal_ring_retained_area_blocked() -> None:
    source, review, calibration = fixture()
    source["pages"][0]["vectors"].append({"items": [["re", [2, 2, 3, 3], 1]]})
    review["rooms"][0]["internal_ring_refs"] = [
        [{"path_id": 13, "item_id": 0, "edge": k} for k in range(4)]
    ]
    result = analyze_source(source, review, calibration)
    room = result["rooms"][0]
    assert (
        room["outer_ring_topology"]["closed"]
        and room["internal_ring_topology"][0]["closed"]
    )
    assert not room["boundary_reference_closed"] and room["reference_area_m2"] is None


def test_no_net_area_or_clear_width_even_geometrically_closed() -> None:
    source, review, calibration = fixture()
    result = analyze_source(source, review, calibration)
    assert all(
        r["finished_clear_area_m2"] is None and r["approved_net_area_m2"] is None
        for r in result["rooms"]
    )
    assert result["portals"][0]["verified_clear_width_mm"] is None
    assert result["portals"][0]["derived_opening_length_mm"] == "400"


def test_multiple_rooms_one_logic_and_different_temperatures_no_defaults() -> None:
    source, review, calibration = fixture()
    review["rooms"][1]["design_temperature"] = {"value": [0, 3]}
    review["rooms"][1]["drawing_clear_height"] = {
        "value": None,
        "status": "UNAVAILABLE",
    }
    result = analyze_source(source, review, calibration)
    assert result["mapping"]["mappings"][0]["physical_room_ids"] == ["A", "B"]
    assert (
        result["rooms"][0]["design_temperature"]
        != result["rooms"][1]["design_temperature"]
    )
    assert result["rooms"][1]["drawing_clear_height"]["value"] is None


def test_unmapped_so2_preserved_and_co2_rejected() -> None:
    source, review, calibration = fixture()
    gas = copy.deepcopy(review["rooms"][1])
    gas["physical_room_id"] = "SO2_FUMIGATION_TRANSFER"
    gas["source_room_name"] = "二氧化硫熏蒸/中转"
    gas["face_refs"] = []
    gas["logical_zone_candidates"] = []
    review["rooms"].append(gas)
    result = analyze_source(source, review, calibration)
    assert "SO2_FUMIGATION_TRANSFER" in result["mapping"]["unmapped_physical_rooms"]
    gas["source_room_name"] = "CO2"
    with pytest.raises(ValueError, match="SO2_SOURCE"):
        analyze_source(source, review, calibration)


def test_no_declared_validation_or_owner_approval() -> None:
    source, review, calibration = fixture()
    review["validated_material_routes"] = ["PASS"]
    with pytest.raises(ValueError):
        analyze_source(source, review, calibration)


def test_nonrectangular_area_uses_r2_polygon_not_bbox() -> None:
    source, review, calibration = fixture()
    vertices = [[0, 0], [4, 0], [4, 1], [1, 1], [1, 4], [0, 4]]
    source["pages"][0]["vectors"] = [
        {"items": [["l", a, b]]}
        for a, b in zip(vertices, vertices[1:] + vertices[:1], strict=True)
    ]
    room = review["rooms"][0]
    room["face_refs"] = [
        {
            "path_id": n,
            "item_id": 0,
            "kind": "WALL_SEGMENT",
            "review_basis": "SYNTHETIC",
        }
        for n in range(6)
    ]
    review["rooms"] = [room]
    review["portals"] = []
    result = analyze_source(source, review, calibration)
    assert result["rooms"][0]["reference_area_m2"] == "7/50"


def test_missing_metric_anchor_does_not_produce_mm_area() -> None:
    source, review, _ = fixture()
    result = analyze_source(source, review, {"metric_transform": None})
    assert result["rooms"][0]["boundary_reference_closed"]
    assert result["rooms"][0]["reference_area_m2"] is None
    assert result["portals"][0]["derived_opening_length_mm"] is None


def test_partial_selection_cannot_be_promoted_even_with_closed_outer_ring() -> None:
    source, review, calibration = fixture()
    review["rooms"][0]["selection_scope"] = "PARTIAL_REVIEWED_SOURCE_SEGMENTS"
    result = analyze_source(source, review, calibration)
    assert result["rooms"][0]["outer_ring_topology"]["closed"]
    assert not result["rooms"][0]["boundary_reference_closed"]
    assert result["rooms"][0]["reference_area_m2"] is None


@pytest.mark.parametrize("kind", ["RACK_LINE", "TEXT_GLYPH_PATH", "DIMENSION_LINE"])
def test_equipment_or_text_or_dimension_cannot_be_selected_wall(kind: str) -> None:
    source, review, calibration = fixture()
    review["rooms"][0]["face_refs"][0]["kind"] = kind
    with pytest.raises(ValueError, match="UNREVIEWED_WALL"):
        analyze_source(source, review, calibration)


def test_caller_cannot_approve_room() -> None:
    source, review, calibration = fixture()
    review["rooms"][0]["engineering_approved"] = True
    with pytest.raises(ValueError, match="CALLER_ROOM_APPROVAL"):
        analyze_source(source, review, calibration)


def test_duplicate_rooms_not_merged_or_counted_twice() -> None:
    source, review, calibration = fixture()
    review["rooms"][1]["physical_room_id"] = "A"
    with pytest.raises(ValueError, match="DUPLICATE_PHYSICAL"):
        analyze_source(source, review, calibration)


def test_stage_and_solve_counters_never_upgraded() -> None:
    source, review, calibration = fixture()
    result = analyze_source(source, review, calibration)
    assert (
        result["p2d_full_pass_count"]
        == result["real_factory_solves"]
        == result["real_truck_searches"]
        == result["native_solver_calls"]
        == 0
    )
    assert result["engineering_approved"] is result["new_owner_grant"] is False
    assert all(p["process_direction"] == "UNVERIFIED" for p in result["portals"])


def test_rotation_and_r1_r2_immutable_dependencies() -> None:
    core, reader = dependencies()
    assert core.transform([10, 20], [0, -1, 1, 0, 0, 100]) == core.point([20, 90])
    _, validator = reader.r1_reader()
    assert (
        validator.calibrate({"display_box": [0, 0, 100, 100]}, [])["metric_transform"]
        is None
    )


def test_historical_eight_layouts_and_authority_hashes() -> None:
    root = Path(__file__).resolve().parents[1] / "stage-b/layout-quality-baseline-01"
    for name, record in json.loads((root / "source_manifest.json").read_bytes())[
        "files"
    ].items():
        assert (
            hashlib.sha256((root / name).read_bytes()).hexdigest() == record["sha256"]
        )
    assert len(list((root / "inputs").glob("*candidate*.json"))) == 8


def test_deterministic_result_and_no_untrusted_html_scripts() -> None:
    source, review, calibration = fixture()
    result = analyze_source(source, review, calibration)
    assert encode(result) == encode(
        analyze_source(source, copy.deepcopy(review), calibration)
    )
    result["rooms"][0]["source_room_name"] = (
        '</script><script src="https://bad.example/x">'
    )
    a = review_html(result, {"synthetic": b'<svg xmlns="http://www.w3.org/2000/svg"/>'})
    assert a == review_html(
        result, {"synthetic": b'<svg xmlns="http://www.w3.org/2000/svg"/>'}
    )
    assert b"<script src=" not in a and b"default-src" in a
    assert b"Content-Security-Policy" in a and b"data-object" in a
    assert "<" not in safe_json(result)
    assert "innerHTML" not in SCRIPT and "textContent" in SCRIPT
