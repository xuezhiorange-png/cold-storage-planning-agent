"""Validate source-bound human review annotations, not engineering approval."""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path
from typing import Any

from offline_drawing_extract import encode, inventory


def number(value: Any) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("INVALID_NUMBER")
    return Fraction(str(value))


def region(box: Any, page: dict[str, Any]) -> None:
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError("SOURCE_REGION_REQUIRED")
    x0, y0, x1, y1 = (number(v) for v in box)
    _, _, width, height = page["display_box"]
    if not (0 <= x0 < x1 <= number(width) and 0 <= y0 < y1 <= number(height)):
        raise ValueError("SOURCE_REGION_OUT_OF_PAGE")


def line_points(page: dict[str, Any], anchor: dict[str, Any]) -> list[list[float]]:
    if any(
        type(anchor.get(k)) is not int or anchor[k] < 0 for k in ("path_id", "item_id")
    ):
        raise ValueError("ANCHOR_SOURCE_REFERENCE_INVALID")
    try:
        item = page["vectors"][anchor["path_id"]]["items"][anchor["item_id"]]
        if item[0] != "l":
            raise ValueError("ANCHOR_MUST_REFERENCE_SOURCE_LINE")
        a, b, c, d, e, f = page["rotation_matrix"]
        return [[a * x + c * y + e, b * x + d * y + f] for x, y in item[1:3]]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("ANCHOR_SOURCE_REFERENCE_INVALID") from exc


def calibrate(page: dict[str, Any], anchors: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for anchor in anchors:
        if anchor.get("label_status") != "DRAWING_LABEL_VERIFIED":
            raise ValueError("ANCHOR_LABEL_NOT_REVIEWED")
        region(anchor["label_region"], page)
        direction = anchor["direction"]
        if direction not in ("X", "Y") or direction in result:
            raise ValueError("EXACTLY_ONE_INDEPENDENT_ANCHOR_PER_DIRECTION")
        points = line_points(page, anchor)
        k = 0 if direction == "X" else 1
        if abs(points[0][1 - k] - points[1][1 - k]) > 0.001:
            raise ValueError("ANCHOR_NOT_AXIS_ALIGNED")
        distance = abs(number(points[1][k]) - number(points[0][k]))
        length = number(anchor["length_mm"])
        chain = anchor["dimension_chain_mm"]
        if not chain or any(number(v) <= 0 for v in chain):
            raise ValueError("POSITIVE_DIMENSION_CHAIN_REQUIRED")
        if sum((number(v) for v in chain), Fraction()) != length or length <= 0:
            raise ValueError("DIMENSION_CHAIN_MISMATCH")
        if distance <= 0:
            raise ValueError("ZERO_ANCHOR")
        scale = length / distance
        result[direction] = {
            "mm_per_pdf_point": str(scale),
            "source_points": points,
            "source_path_id": anchor["path_id"],
            "length_mm": str(length),
        }
    if set(result) != {"X", "Y"}:
        return {"status": "UNVERIFIED", "metric_transform": None}
    return {
        "status": "DIMENSION_ANCHOR_VERIFIED",
        "metric_transform": result,
        "engineering_authority": "UNVERIFIED",
        "derived_geometry_status": "GEOMETRY_DERIVED_REVIEW_REQUIRED",
        "note": "PDF export quantization is not measured construction accuracy; no net room sizes.",
    }


def validate(source: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    if review.get("source_sha256") != source["source_sha256"]:
        raise ValueError("SOURCE_HASH_MISMATCH")
    if review.get("engineering_authority_approved") is not False:
        raise ValueError("NO_ENGINEERING_APPROVAL_IN_THIS_CONTRACT")
    objects = review["objects"]
    ids = [o["object_id"] for o in objects]
    if len(set(ids)) != len(ids):
        raise ValueError("DUPLICATE_OBJECT_ID")
    for obj in objects:
        page_number = obj["source_page"]
        if (
            type(page_number) is not int
            or not 1 <= page_number <= source["pdf_page_count"]
        ):
            raise ValueError("SOURCE_PAGE_OUT_OF_RANGE")
        region(obj["source_region"], source["pages"][page_number - 1])
        if not obj.get("review_method"):
            raise ValueError("REVIEW_METHOD_REQUIRED")
        if obj.get("width_mm") is not None or obj.get("depth_mm") is not None:
            raise ValueError("NET_ROOM_DIMENSIONS_NOT_SUPPORTED_BY_REVIEW_ROI")
        if obj.get("area_m2") is not None:
            raise ValueError("ROOM_AREA_NOT_INFERRED_FROM_REVIEW_ROI")
        if obj.get("boundary_geometry") is not None:
            raise ValueError("ROI_IS_NOT_A_TRACED_WALL_BOUNDARY")
        if obj["object_type"] == "PORTAL":
            if (
                obj.get("door_width_mm") is not None
                or obj.get("door_height_mm") is not None
            ):
                raise ValueError("DOOR_MARK_IS_NOT_A_CLEAR_DIMENSION")
            if obj.get("clear_opening_status") != "UNAVAILABLE":
                raise ValueError("CLEAR_OPENING_UNVERIFIED")
        if (
            obj["object_type"] == "EQUIPMENT"
            and obj.get("selection_status") != "UNAVAILABLE"
        ):
            raise ValueError("DEPICTION_IS_NOT_EQUIPMENT_SELECTION")
    for mapping in review.get("logical_mapping", []):
        if not set(mapping["physical_objects"]).issubset(ids):
            raise ValueError("UNKNOWN_MAPPING_OBJECT")
        if mapping["status"] != "MAPPING_REVIEW_REQUIRED":
            raise ValueError("MAPPING_IS_NOT_P1_AUTHORITY")
    for relationship in review.get("relationships", []):
        if not {relationship["from"], relationship["to"]}.issubset(ids):
            raise ValueError("UNKNOWN_RELATIONSHIP_OBJECT")
        if relationship["type"] not in {
            "DRAWING_ADJACENCY",
            "DRAWING_PORTAL_CONNECTION",
            "DECLARED_PROCESS_FLOW",
        }:
            raise ValueError("NO_VALIDATED_MATERIAL_ROUTE_FROM_DRAWING")
    calibrations = []
    for anchor in review.get("anchors", []):
        if (
            type(anchor.get("page")) is not int
            or not 1 <= anchor["page"] <= source["pdf_page_count"]
        ):
            raise ValueError("ANCHOR_PAGE_OUT_OF_RANGE")
    for index, page in enumerate(source["pages"]):
        anchors = [a for a in review.get("anchors", []) if a["page"] == index + 1]
        calibrations.append(calibrate(page, anchors))
    areas = review.get("area_labels", {})
    area_sum = None
    if all(k in areas for k in ("wall_enclosed", "canopy", "total")):
        for item in areas.values():
            region(item["source_region"], source["pages"][item["source_page"] - 1])
        area_sum = number(areas["wall_enclosed"]["value"]) + number(
            areas["canopy"]["value"]
        ) == number(areas["total"]["value"])
    return {
        "contract": "XinzhaoDrawingGeometryV1",
        "status": "PARTIAL_SOURCE_BOUND_REVIEW_NOT_ENGINEERING_MODEL",
        "source_sha256": source["source_sha256"],
        "object_count": len(objects),
        "physical_room_regions": sum(
            o["object_type"] == "PHYSICAL_ROOM" for o in objects
        ),
        "verified_net_room_boundaries": 0,
        "calibrations": calibrations,
        "area_label_addition_matches": area_sum,
        "process_flow_pass": None,
        "engineering_authority_approved": False,
        "room_dimensions_mm": None,
        "real_factory_solves": 0,
        "new_owner_grant": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("review", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = validate(inventory(args.pdf), json.loads(args.review.read_bytes()))
    with args.output.open("xb") as stream:
        stream.write(encode(result))


if __name__ == "__main__":
    main()
