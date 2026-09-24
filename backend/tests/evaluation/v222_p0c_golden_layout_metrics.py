"""Offline measurements for normalized V2.2.2 P0C reference abstractions."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

REFERENCE_DIR = (
    Path(__file__).resolve().parents[2]
    / ".."
    / "docs/tasks/evidence/v2_2_2_p0c"
).resolve()
REFERENCE_IDS = (
    "GD-001_ZHUYUAN",
    "GD-002_XIAOXIANG",
    "GD-003_MOUDING",
    "GD-004_SHUANGLONGYING",
    "GD-005_PANLONG",
)
_FILES = {
    "GD-001_ZHUYUAN": "GD-001_ZHUYUAN.normalized-layout.json",
    "GD-002_XIAOXIANG": "GD-002_XIAOXIANG.normalized-layout.json",
    "GD-003_MOUDING": "GD-003_MOUDING.normalized-layout.json",
    "GD-004_SHUANGLONGYING": "GD-004_SHUANGLONGYING.normalized-layout.json",
    "GD-005_PANLONG": "GD-005_PANLONG.normalized-layout.json",
}


def load_reference(reference_id: str) -> dict[str, Any]:
    """Read one committed visual abstraction; never reads the source PDF."""
    if reference_id not in _FILES:
        raise ValueError(f"unknown P0C reference: {reference_id}")
    value = json.loads((REFERENCE_DIR / _FILES[reference_id]).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("normalized reference must be an object")
    return value


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def major_group_axis_alignment(reference: dict[str, Any]) -> Decimal:
    """Measure traced group-envelope edges on the separately traced axis families."""
    groups = reference.get("major_zone_rectangles")
    axes = reference.get("axis_families")
    if not isinstance(groups, list) or not groups or not isinstance(axes, dict):
        raise ValueError("major group rectangles and axis families are required")
    x_axes = {_decimal(value) for value in axes.get("x", [])}
    y_axes = {_decimal(value) for value in axes.get("y", [])}
    aligned = 0
    incidences = 0
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("rect"), list):
            raise ValueError("invalid major group rectangle")
        x, y, width, height = (_decimal(value) for value in group["rect"])
        if min(x, y, width, height) < 0 or x + width > 1 or y + height > 1:
            raise ValueError("normalized group rectangle is outside [0, 1]")
        aligned += int(x in x_axes) + int(x + width in x_axes)
        aligned += int(y in y_axes) + int(y + height in y_axes)
        incidences += 4
    return Decimal(aligned) / Decimal(incidences)


def reference_metrics(reference: dict[str, Any]) -> dict[str, Any]:
    """Return observed abstraction facts and explicit unavailable metrics."""
    if reference.get("identity") != "golden-layout-abstraction@1.0.0":
        raise ValueError("unsupported abstraction identity")
    outline = reference.get("building_outline")
    if not isinstance(outline, dict):
        raise ValueError("building outline is required")
    return {
        "grid_alignment_rate": str(major_group_axis_alignment(reference)),
        "grid_alignment_evidence": "REFERENCE_DERIVED_PROVISIONAL_GROUP_ENVELOPES",
        "depth_alignment_rate": "UNAVAILABLE_ROOM_LEVEL_GEOMETRY_NOT_PRESENT",
        "main_building_component_count": outline.get("main_building_component_count", "UNAVAILABLE"),
        "bounding_rectangle_occupancy": "UNAVAILABLE_COARSE_ENVELOPE_ONLY",
        "reflex_corner_count": "UNAVAILABLE_COARSE_ENVELOPE_ONLY",
        "notch_count": "UNAVAILABLE_COARSE_ENVELOPE_ONLY",
        "appendage_count": "UNAVAILABLE_COMPONENT_PURPOSE_AND_NECK_FACTS",
        "outline_class": outline.get("class", "UNAVAILABLE"),
        "outline_class_status": outline.get("classification_status", "UNAVAILABLE"),
        "functional_grouping": "PASS_QUALITATIVE",
        "process_core_legibility": reference["process_core"]["legibility"],
        "support_group_subordination": reference["support_groups"]["subordination"],
        "main_flow_backtrack_count": "UNAVAILABLE_NO_AUTHORITATIVE_ROUTE_TRACE",
        "main_flow_turn_count": "UNAVAILABLE_NO_AUTHORITATIVE_ROUTE_TRACE",
        "process_route_length_m": "UNAVAILABLE_NO_AUTHORITATIVE_ROUTE_TRACE",
        "process_route_efficiency_ratio": "UNAVAILABLE_NO_AUTHORITATIVE_ROUTE_TRACE",
        "side_branch_crossing": "UNAVAILABLE_NO_AUTHORITATIVE_ROUTE_TRACE",
        "personnel_logistics_separation": "UNAVAILABLE_NO_AUTHORITATIVE_ACCESS_ROUTES",
    }


def orthogonal_outline_facts(points: list[list[object]]) -> dict[str, Any]:
    """Measure a closed rectilinear ring in normalized coordinates exactly."""
    vertices = [(_decimal(point[0]), _decimal(point[1])) for point in points]
    if len(vertices) > 1 and vertices[0] == vertices[-1]:
        vertices.pop()
    if len(vertices) < 4 or len(set(vertices)) != len(vertices):
        raise ValueError("outline must have at least four unique orthogonal vertices")
    for index, current in enumerate(vertices):
        following = vertices[(index + 1) % len(vertices)]
        if current[0] != following[0] and current[1] != following[1]:
            raise ValueError("outline edges must be orthogonal")
        if current == following:
            raise ValueError("outline cannot contain zero-length edges")
    twice_area = sum(
        vertices[index][0] * vertices[(index + 1) % len(vertices)][1]
        - vertices[(index + 1) % len(vertices)][0] * vertices[index][1]
        for index in range(len(vertices))
    )
    if twice_area == 0:
        raise ValueError("outline area must be positive")
    orientation = Decimal(1) if twice_area > 0 else Decimal(-1)
    reflex = 0
    for index, current in enumerate(vertices):
        previous = vertices[index - 1]
        following = vertices[(index + 1) % len(vertices)]
        cross = (current[0] - previous[0]) * (following[1] - current[1]) - (
            current[1] - previous[1]
        ) * (following[0] - current[0])
        reflex += int(cross * orientation < 0)

    xs = sorted({point[0] for point in vertices})
    ys = sorted({point[1] for point in vertices})
    exterior_cells: set[tuple[int, int]] = set()
    for x_index in range(len(xs) - 1):
        for y_index in range(len(ys) - 1):
            sample = ((xs[x_index] + xs[x_index + 1]) / 2, (ys[y_index] + ys[y_index + 1]) / 2)
            if not _point_in_polygon(sample, vertices):
                exterior_cells.add((x_index, y_index))
    notch_components = 0
    while exterior_cells:
        notch_components += 1
        pending = [exterior_cells.pop()]
        while pending:
            x_index, y_index = pending.pop()
            for neighbor in (
                (x_index - 1, y_index),
                (x_index + 1, y_index),
                (x_index, y_index - 1),
                (x_index, y_index + 1),
            ):
                if neighbor in exterior_cells:
                    exterior_cells.remove(neighbor)
                    pending.append(neighbor)

    area = abs(twice_area) / 2
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    if width <= 0 or height <= 0:
        raise ValueError("outline bounds must have positive width and height")
    return {
        "bounding_rectangle_occupancy": area / (width * height),
        "reflex_corner_count": reflex,
        "notch_count": notch_components,
        "vertex_count": len(vertices),
    }


def _point_in_polygon(
    point: tuple[Decimal, Decimal], vertices: list[tuple[Decimal, Decimal]]
) -> bool:
    """Ray-crossing predicate used only at exact cell midpoints."""
    x, y = point
    inside = False
    for index, first in enumerate(vertices):
        second = vertices[(index + 1) % len(vertices)]
        if first[0] == second[0] and (first[1] > y) != (second[1] > y):
            crossing_x = first[0]
            if crossing_x > x:
                inside = not inside
    return inside


def classify_outline_v1(
    facts: dict[str, Any],
    *,
    component_count: int = 1,
    site_constrained_exception: bool = False,
    narrow_neck_confirmed: bool = False,
    owner_confirmed_unmotivated_appendage: bool = False,
) -> str:
    """Apply the evidence-gated P0C outline class precedence."""
    if component_count > 1:
        return "MULTI_COMPONENT"
    if owner_confirmed_unmotivated_appendage:
        return "ISOLATED_APPENDAGE"
    if narrow_neck_confirmed:
        return "NARROW_NECK"
    reflex = int(facts["reflex_corner_count"])
    notches = int(facts["notch_count"])
    if reflex == 0 and int(facts["vertex_count"]) == 4:
        return "RECTANGLE"
    if site_constrained_exception:
        return "IRREGULAR_SITE_CONSTRAINED"
    if reflex == 1 and notches == 1:
        return "SIMPLE_L"
    if notches == 1 and reflex >= 2:
        return "COMPLEX_L"
    if notches >= 2:
        return "STAIR_STEP"
    return "AMBIGUOUS_REQUIRES_OWNER_REVIEW"


def all_positive_metrics() -> list[dict[str, Any]]:
    """Stable-order, non-authoritative metric rows for the five accepted drawings."""
    rows: list[dict[str, Any]] = []
    for reference_id in REFERENCE_IDS:
        reference = load_reference(reference_id)
        rows.append(
            {
                "fixture_id": reference_id,
                "owner_label": reference["owner_label"],
                "source_sha256": reference["source_sha256"],
                **reference_metrics(reference),
            }
        )
    return rows
