"""Small PDF fixtures only. No solver, grant, or production validator invocation."""

from __future__ import annotations

import copy
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import fitz
import pytest

from offline_drawing_extract import encode, inventory
from offline_drawing_render import render
from offline_drawing_validate import calibrate, validate


@pytest.fixture
def sample(tmp_path: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    pdf = tmp_path / "synthetic.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=300)
        page.draw_line((20, 20), (220, 20))
        page.draw_line((20, 20), (20, 220))
        page.insert_text((40, 50), "Synthetic test - not project source")
        doc.save(pdf)
    source = inventory(pdf)
    review: dict[str, Any] = {
        "source_sha256": source["source_sha256"],
        "engineering_authority_approved": False,
        "objects": [],
        "anchors": [
            {
                "page": 1,
                "path_id": n,
                "item_id": 0,
                "direction": direction,
                "length_mm": 10000,
                "dimension_chain_mm": [5000, 5000],
                "label_status": "DRAWING_LABEL_VERIFIED",
                "label_region": [10, 10, 30, 30],
            }
            for n, direction in enumerate(("X", "Y"))
        ],
    }
    return pdf, source, review


def obj(identifier: str, kind: str = "PHYSICAL_ROOM") -> dict[str, Any]:
    return {
        "object_id": identifier,
        "object_type": kind,
        "source_page": 1,
        "source_region": [40, 60, 80, 100],
        "source_label": None,
        "review_method": "SYNTHETIC_TEST",
        "width_mm": None,
        "depth_mm": None,
        "area_m2": None,
        "boundary_geometry": None,
    }


def test_byte_hash_and_cad_text_gate(sample: Any) -> None:
    pdf, source, _ = sample
    assert source["source_sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert source["pages"][0]["text_status"] == "MANUAL_REVIEW_REQUIRED"


@pytest.mark.parametrize("count", [1, 2, 3])
def test_page_count(tmp_path: Path, count: int) -> None:
    pdf = tmp_path / "pages.pdf"
    with fitz.open() as doc:
        for _ in range(count):
            doc.new_page()
        doc.save(pdf)
    assert inventory(pdf)["pdf_page_count"] == count


def test_crop_is_warning_not_missing_room_claim(tmp_path: Path) -> None:
    pdf = tmp_path / "crop.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=300)
        page.set_cropbox(fitz.Rect(20, 20, 380, 280))
        doc.save(pdf)
    assert inventory(pdf)["pages"][0]["crop_status"] == "CROP_DIFFERS_REVIEW_REQUIRED"


@pytest.mark.parametrize("count", [0, 1])
def test_unconfirmed_metric_coordinates_remain_null(sample: Any, count: int) -> None:
    _, source, review = sample
    review["anchors"] = review["anchors"][:count]
    result = validate(source, review)
    assert result["calibrations"][0]["metric_transform"] is None
    assert result["room_dimensions_mm"] is None


def test_independent_anchor_calibration(sample: Any) -> None:
    _, source, review = sample
    result = validate(source, review)
    assert (
        result["calibrations"][0]["metric_transform"]["X"]["mm_per_pdf_point"] == "50"
    )
    assert result["engineering_authority_approved"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("dimension_chain_mm", [5000, 4999]),
        ("path_id", 999),
        ("label_status", "APPROVED"),
        ("direction", "Z"),
    ],
)
def test_bad_anchor_rejected(sample: Any, field: str, value: Any) -> None:
    _, source, review = sample
    review["anchors"][0][field] = value
    with pytest.raises(ValueError):
        validate(source, review)


def test_wrong_source_rejected(sample: Any) -> None:
    _, source, review = sample
    review["source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SOURCE_HASH"):
        validate(source, review)


@pytest.mark.parametrize("field,value", [("path_id", -1), ("item_id", -1), ("page", 2)])
def test_invalid_anchor_index_cannot_alias_or_disappear(
    sample: Any, field: str, value: int
) -> None:
    _, source, review = sample
    review["anchors"][0][field] = value
    with pytest.raises(ValueError):
        validate(source, review)


def test_multiple_rooms_logical_mapping_and_auxiliary_separation(sample: Any) -> None:
    _, source, review = sample
    ids = ["precool-1", "precool-2", "office", "male", "female", "gas-separate"]
    review["objects"] = [obj(i) for i in ids]
    review["logical_mapping"] = [
        {
            "logical_zone": "primary",
            "physical_objects": ids[:2],
            "status": "MAPPING_REVIEW_REQUIRED",
        }
    ]
    assert validate(source, review)["physical_room_regions"] == 6
    assert all(o["source_label"] is None for o in review["objects"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("width_mm", 1000),
        ("depth_mm", 1000),
        ("area_m2", 60),
        ("boundary_geometry", [[0, 0], [1, 1]]),
        ("source_page", 2),
        ("source_region", [-1, 0, 20, 20]),
        ("review_method", None),
    ],
)
def test_roi_cannot_become_net_room_authority(
    sample: Any, field: str, value: Any
) -> None:
    _, source, review = sample
    item = obj("room")
    item[field] = value
    review["objects"] = [item]
    with pytest.raises(ValueError):
        validate(source, review)


def test_door_mark_cannot_supply_clear_width(sample: Any) -> None:
    _, source, review = sample
    door = obj("door", "PORTAL")
    door.update(drawing_mark="DK2530", clear_opening_status="UNAVAILABLE")
    review["objects"] = [door]
    validate(source, review)
    door["door_width_mm"] = 2500
    with pytest.raises(ValueError, match="DOOR_MARK"):
        validate(source, review)


def test_equipment_depiction_not_selection(sample: Any) -> None:
    _, source, review = sample
    equipment = obj("line", "EQUIPMENT")
    equipment["selection_status"] = "UNAVAILABLE"
    review["objects"] = [equipment]
    validate(source, review)
    equipment["selection_status"] = "PROJECT_SELECTED_EQUIPMENT"
    with pytest.raises(ValueError):
        validate(source, review)


@pytest.mark.parametrize(
    "kind", ["DRAWING_ADJACENCY", "DRAWING_PORTAL_CONNECTION", "DECLARED_PROCESS_FLOW"]
)
def test_connection_is_not_route_pass(sample: Any, kind: str) -> None:
    _, source, review = sample
    review["objects"] = [obj("a"), obj("b")]
    review["relationships"] = [{"from": "a", "to": "b", "type": kind}]
    assert validate(source, review)["process_flow_pass"] is None
    review["relationships"][0]["type"] = "VALIDATED_MATERIAL_ROUTE"
    with pytest.raises(ValueError):
        validate(source, review)


def test_area_labels_distinct_exact_arithmetic(sample: Any) -> None:
    _, source, review = sample
    review["area_labels"] = {
        k: {"value": v, "source_region": [10, 10, 20, 20], "source_page": 1}
        for k, v in [("wall_enclosed", "1.01"), ("canopy", "2.02"), ("total", "3.03")]
    }
    assert validate(source, review)["area_label_addition_matches"] is True


def test_no_authority_upgrade(sample: Any) -> None:
    _, source, review = sample
    review["engineering_authority_approved"] = True
    with pytest.raises(ValueError):
        validate(source, review)


@pytest.mark.parametrize("layer", ["axes", "rooms", "mapping"])
def test_svg_source_alignment_determinism_and_escaping(sample: Any, layer: str) -> None:
    pdf, _, review = sample
    item = obj("safe")
    item["source_label"] = '<script>alert("bad")</script>'
    review["objects"] = [item]
    a = render(pdf, review, layer)
    assert a == render(pdf, copy.deepcopy(review), layer)
    root = ET.fromstring(a)
    assert not root.findall(".//{http://www.w3.org/2000/svg}script")
    assert b"data:image/png;base64," in a


def test_inventory_and_json_deterministic_no_execution(sample: Any) -> None:
    pdf, source, review = sample
    assert encode(source) == encode(inventory(pdf))
    result = validate(source, review)
    assert result["real_factory_solves"] == 0
    assert result["new_owner_grant"] is False


def test_historical_sealed_source_hashes() -> None:
    root = (
        Path(__file__).resolve().parents[1] / "stage-b" / "layout-quality-baseline-01"
    )
    manifest = json.loads((root / "source_manifest.json").read_bytes())
    for name, record in manifest["files"].items():
        assert (
            hashlib.sha256((root / name).read_bytes()).hexdigest() == record["sha256"]
        )
    assert len(list((root / "inputs").glob("*candidate*.json"))) == 8


def test_calibration_does_not_use_declared_scale(sample: Any) -> None:
    _, source, _ = sample
    assert calibrate(source["pages"][0], [])["metric_transform"] is None
