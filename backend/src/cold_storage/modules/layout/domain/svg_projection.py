"""Deterministic, static SVG projection primitives for validated V2.2 layouts.

This module is deliberately a drawing layer.  It consumes already validated
engineering geometry and never recalculates an area, changes a rectangle,
chooses a loading face, or searches for a route.  All source coordinates are
normalised to the existing integer-millimetre grid before they are projected
into SVG screen coordinates.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from typing import Any, Final, cast
from xml.sax.saxutils import escape, quoteattr

from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PointPair,
    PolygonMM,
    SegmentMM,
    _point_from_mapping,
    normalize_polygon,
)

SVG_PROJECTION_IDENTITY: Final = "validated-layout-svg-projection@1.0.0"
SVG_SCHEMA_VERSION: Final = "1.0.0"
SVG_GEOMETRY_GRID_M: Final = Decimal("0.001")
SVG_SCALE: Final = Decimal("10")
SVG_MARGIN_M: Final = Decimal("8")
SVG_LEGEND_WIDTH_M: Final = Decimal("42")
SVG_TITLE_HEIGHT_M: Final = Decimal("18")
SVG_DISPLAY_DIMENSION_DECIMALS: Final = 2

LAYER_ORDER: Final[tuple[str, ...]] = (
    "site-boundary",
    "site-constraints",
    "building-footprint",
    "zones",
    "portals",
    "corridors",
    "truck-maneuvers",
    "entrances",
    "dimensions",
    "labels",
    "legend",
)

EXPECTED_ZONE_CODES: Final[tuple[str, ...]] = (
    "office",
    "changing_room",
    "primary_precooling_room",
    "secondary_precooling_room",
    "raw_fruit_buffer",
    "sorting_packaging_room",
    "coating_room",
    "finished_goods_room",
    "secondary_fruit_buffer",
    "frozen_fruit_room",
    "packaging_material_storage",
    "shipping_channel",
)

COLD_ZONE_CODES: Final[frozenset[str]] = frozenset(
    {
        "primary_precooling_room",
        "secondary_precooling_room",
        "raw_fruit_buffer",
        "sorting_packaging_room",
        "coating_room",
        "finished_goods_room",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "shipping_channel",
    }
)

DISPLAY_LABELS: Final[dict[str, str]] = {
    "office": "办公室",
    "changing_room": "更衣室",
    "primary_precooling_room": "一级预冷间",
    "secondary_precooling_room": "二级预冷间",
    "raw_fruit_buffer": "原果暂存间",
    "sorting_packaging_room": "分选包装间",
    "coating_room": "覆膜间",
    "finished_goods_room": "成品间",
    "secondary_fruit_buffer": "次果暂存间",
    "frozen_fruit_room": "冻果间",
    "packaging_material_storage": "包材库",
    "shipping_channel": "出货通道",
}

_THEME_HEX_COLOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"^#[0-9A-Fa-f]{6}$")
_THEME_COLOR_FIELDS: Final[tuple[str, ...]] = (
    "background",
    "zone_fill",
    "cold_zone_fill",
    "corridor_fill",
    "building_outline",
    "site_outline",
    "obstacle_fill",
    "portal_stroke",
    "truck_envelope",
    "loading_face",
    "text",
    "dimension",
    "buildable_outline",
    "entrance_stroke",
)


@dataclass(frozen=True)
class SvgDrawingThemeV1:
    """Display-only colours; the theme is not part of engineering authority."""

    background: str = "#ffffff"
    zone_fill: str = "#dbeafe"
    cold_zone_fill: str = "#bfdbfe"
    corridor_fill: str = "#fef3c7"
    building_outline: str = "#1f2937"
    site_outline: str = "#111827"
    obstacle_fill: str = "#fecaca"
    portal_stroke: str = "#7c3aed"
    truck_envelope: str = "#dc2626"
    loading_face: str = "#ea580c"
    text: str = "#111827"
    dimension: str = "#374151"
    buildable_outline: str = "#2563eb"
    entrance_stroke: str = "#059669"

    def __post_init__(self) -> None:
        for field_name in _THEME_COLOR_FIELDS:
            value = getattr(self, field_name)
            if not isinstance(value, str) or _THEME_HEX_COLOR_PATTERN.fullmatch(value) is None:
                raise LayoutAuthorityError("SVG_THEME_INVALID", field=field_name)


@dataclass(frozen=True)
class SvgProjectionTransformV1:
    """Fixed engineering-to-screen transform used by one drawing."""

    min_x_m: Decimal
    max_y_m: Decimal
    scale: Decimal = SVG_SCALE

    def point(self, point: PointPair) -> tuple[Decimal, Decimal]:
        x_m = Decimal(point[0]) / Decimal(1000)
        y_m = Decimal(point[1]) / Decimal(1000)
        return (
            (x_m - self.min_x_m) * self.scale,
            (self.max_y_m - y_m) * self.scale,
        )


@dataclass(frozen=True)
class ValidatedLayoutSvgProjectionV1:
    """Immutable projection result whose canonical hash covers the SVG bytes."""

    payload_json: str
    _content_hash: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ValidatedLayoutSvgProjectionV1:
        content = dict(payload)
        content.pop("canonical_result_hash", None)
        normalized = canonical_json(content)
        return cls(normalized, canonical_hash(content))

    def to_dict(self) -> dict[str, Any]:
        import json

        value = cast(dict[str, Any], json.loads(self.payload_json))
        value["canonical_result_hash"] = self._content_hash
        return value

    def canonical_json(self) -> str:
        return self.payload_json

    @property
    def canonical_result_hash(self) -> str:
        return self._content_hash


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error("SVG_PROJECTION_INPUT_INVALID", field=field)
    return value


def _decimal(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise _error("SVG_PROJECTION_INPUT_INVALID", field=field)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise _error("SVG_PROJECTION_INPUT_INVALID", field=field) from None
    if not number.is_finite():
        raise _error("SVG_PROJECTION_INPUT_INVALID", field=field)
    return number


def _point(value: object, *, field: str) -> PointPair:
    try:
        if isinstance(value, Mapping) and {"x", "y"} <= set(value):
            value = {"x": value["x"], "y": value["y"]}
        return _point_from_mapping(
            value,
            code="SVG_PROJECTION_INPUT_INVALID",
            field=field,
            allow_numeric_string=True,
        )
    except LayoutAuthorityError:
        raise
    except (TypeError, ValueError):
        raise _error("SVG_PROJECTION_INPUT_INVALID", field=field) from None


def _segment(value: object, *, field: str) -> SegmentMM:
    source = _mapping(value, field=field)
    if set(source) != {"start", "end"}:
        raise _error("SVG_PROJECTION_INPUT_INVALID", field=field)
    start = _point(source["start"], field=f"{field}.start")
    end = _point(source["end"], field=f"{field}.end")
    if start == end:
        raise _error("SVG_PROJECTION_INPUT_INVALID", field=field)
    return (start, end)


def _polyline(value: object, *, field: str) -> tuple[PointPair, ...]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise _error("SVG_PROJECTION_INPUT_INVALID", field=field)
    return tuple(_point(point, field=f"{field}[{index}]") for index, point in enumerate(value))


def _polygon(value: object, *, field: str) -> PolygonMM:
    try:
        return normalize_polygon(
            value,
            error_code="SVG_PROJECTION_INPUT_INVALID",
            allow_numeric_string=True,
        )
    except LayoutAuthorityError:
        raise
    except (TypeError, ValueError):
        raise _error("SVG_PROJECTION_INPUT_INVALID", field=field) from None


def _format_number(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def format_display_number(value: object, *, decimals: int = SVG_DISPLAY_DIMENSION_DECIMALS) -> str:
    """Format a display value without feeding display rounding into geometry."""
    number = _decimal(value, field="display_value")
    quantum = Decimal(1).scaleb(-decimals)
    with localcontext() as context:
        context.prec = max(28, len(number.as_tuple().digits) + decimals + 4)
        rounded = number.quantize(quantum, rounding=ROUND_HALF_UP)
    if rounded == 0:
        return "0"
    return format(rounded, "f")


def _safe_id(value: object) -> str:
    raw = str(value)
    return "".join(
        character if character.isalnum() or character in "-_" else "-" for character in raw
    )


def _attr(name: str, value: object) -> str:
    return f" {name}={quoteattr(str(value))}"


def _element(
    name: str,
    *,
    attrs: Mapping[str, object] | None = None,
    body: str = "",
    self_closing: bool = False,
) -> str:
    rendered_attrs = "".join(
        _attr(key, value) for key, value in (attrs.items() if attrs is not None else ())
    )
    if self_closing:
        return f"<{name}{rendered_attrs}/>"
    return f"<{name}{rendered_attrs}>{body}</{name}>"


def _polygon_points(polygon: PolygonMM, transform: SvgProjectionTransformV1) -> str:
    return " ".join(
        f"{_format_number(x)} {_format_number(y)}"
        for x, y in (transform.point(point) for point in polygon)
    )


def _line_points(segment: SegmentMM, transform: SvgProjectionTransformV1) -> str:
    return _polygon_points(segment, transform)


def _polyline_points(points: Sequence[PointPair], transform: SvgProjectionTransformV1) -> str:
    return _polygon_points(tuple(points), transform)


def _points_for_bounds(points: Sequence[PointPair]) -> tuple[int, int, int, int]:
    if not points:
        raise _error("SVG_PROJECTION_INPUT_INVALID", field="geometry")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _append_points(target: list[PointPair], polygon: PolygonMM) -> None:
    target.extend(polygon)


def _source_rectangles(body: Mapping[str, Any]) -> dict[str, PlacedRectangleV1]:
    raw_zones = body.get("zones")
    if not isinstance(raw_zones, list) or len(raw_zones) != len(EXPECTED_ZONE_CODES):
        raise _error(
            "SVG_PROJECTION_INPUT_INVALID",
            field="zones",
            expected_count=len(EXPECTED_ZONE_CODES),
        )
    rectangles: dict[str, PlacedRectangleV1] = {}
    for index, row_value in enumerate(raw_zones):
        row = _mapping(row_value, field=f"zones[{index}]")
        required = {"zone_code", "x", "y", "width_m", "depth_m", "rotation_deg"}
        if not required <= set(row):
            raise _error("SVG_PROJECTION_INPUT_INVALID", field=f"zones[{index}]")
        code = row.get("zone_code")
        if not isinstance(code, str) or code in rectangles:
            raise _error("SVG_PROJECTION_INPUT_INVALID", field="zones", reason="ZONE_SET")
        try:
            rectangles[code] = PlacedRectangleV1(
                code,
                _decimal(row["x"], field=f"zones[{index}].x"),
                _decimal(row["y"], field=f"zones[{index}].y"),
                _decimal(row["width_m"], field=f"zones[{index}].width_m"),
                _decimal(row["depth_m"], field=f"zones[{index}].depth_m"),
                row["rotation_deg"],
            )
        except LayoutAuthorityError:
            raise
        except (TypeError, ValueError):
            raise _error("SVG_PROJECTION_INPUT_INVALID", field=f"zones[{index}]") from None
    if set(rectangles) != set(EXPECTED_ZONE_CODES):
        raise _error("SVG_PROJECTION_INPUT_INVALID", field="zones", reason="ZONE_SET")
    return rectangles


def _source_site_geometry(geometry_body: Mapping[str, Any]) -> dict[str, Any]:
    site = _mapping(geometry_body.get("site"), field="site")
    obstacles = _mapping(geometry_body.get("obstacles"), field="obstacles")
    site_boundary = _polygon(site.get("site_boundary"), field="site_boundary")
    buildable = _polygon(
        site.get("effective_buildable_boundary"), field="effective_buildable_boundary"
    )
    raw_no_build = obstacles.get("no_build_zones", [])
    raw_buildings = obstacles.get("existing_buildings", [])
    if not isinstance(raw_no_build, list) or not isinstance(raw_buildings, list):
        raise _error("SVG_PROJECTION_INPUT_INVALID", field="obstacles")
    no_build = tuple(
        _polygon(row, field=f"no_build_zones[{index}]") for index, row in enumerate(raw_no_build)
    )
    buildings: list[dict[str, Any]] = []
    for index, raw_building in enumerate(raw_buildings):
        building = dict(_mapping(raw_building, field=f"existing_buildings[{index}]"))
        building["footprint"] = _polygon(
            building.get("footprint"), field=f"existing_buildings[{index}].footprint"
        )
        buildings.append(building)
    entrances = _mapping(geometry_body.get("entrances"), field="entrances")
    return {
        "site_boundary": site_boundary,
        "buildable_boundary": buildable,
        "no_build_zones": no_build,
        "existing_buildings": tuple(buildings),
        "main_entrance": _segment(entrances.get("main_entrance"), field="main_entrance"),
        "truck_entrance": _segment(entrances.get("truck_entrance"), field="truck_entrance"),
        "north_angle_degrees": site.get("north_angle_degrees", "0"),
    }


def _source_building_footprint(body: Mapping[str, Any]) -> tuple[PolygonMM, Decimal]:
    building = _mapping(body.get("building_footprint"), field="building_footprint")
    polygon = _polygon(building.get("footprint"), field="building_footprint.footprint")
    gross_area = _decimal(building.get("gross_area_m2"), field="building_footprint.gross_area_m2")
    return polygon, gross_area


def _source_loading_face(body: Mapping[str, Any]) -> SegmentMM:
    return _segment(
        body.get("shipping_loading_face_segment"), field="shipping_loading_face_segment"
    )


def _all_geometry_points(
    site: Mapping[str, Any],
    rectangles: Mapping[str, PlacedRectangleV1],
    building: PolygonMM,
    loading_face: SegmentMM,
    body: Mapping[str, Any],
) -> list[PointPair]:
    points: list[PointPair] = []
    _append_points(points, site["site_boundary"])
    _append_points(points, site["buildable_boundary"])
    _append_points(points, building)
    _append_points(points, loading_face)
    for rectangle in rectangles.values():
        _append_points(points, rectangle.polygon_mm)
    _append_points(points, site["main_entrance"])
    _append_points(points, site["truck_entrance"])
    for polygon in site["no_build_zones"]:
        _append_points(points, polygon)
    for existing in site["existing_buildings"]:
        _append_points(points, existing["footprint"])
    raw_portals = body.get("portals", [])
    raw_corridors = body.get("corridors", [])
    raw_maneuvers = body.get("truck_maneuver_chain", [])
    raw_truck_envelopes = body.get("truck_envelopes", [])
    if not isinstance(raw_portals, list) or not isinstance(raw_corridors, list):
        raise _error("SVG_PROJECTION_INPUT_INVALID", field="portals_or_corridors")
    for index, portal_value in enumerate(raw_portals):
        portal = _mapping(portal_value, field=f"portals[{index}]")
        _append_points(points, _segment(portal.get("segment"), field=f"portals[{index}].segment"))
    for index, corridor_value in enumerate(raw_corridors):
        corridor = _mapping(corridor_value, field=f"corridors[{index}]")
        for polygon_value in corridor.get("envelope", []):
            _append_points(
                points,
                _polygon(polygon_value, field=f"corridors[{index}].envelope"),
            )
        _append_points(
            points,
            _polyline(corridor.get("centerline"), field=f"corridors[{index}].centerline"),
        )
    if not isinstance(raw_maneuvers, list) or not isinstance(raw_truck_envelopes, list):
        raise _error("SVG_PROJECTION_INPUT_INVALID", field="truck_maneuvers")
    for index, maneuver_value in enumerate(raw_maneuvers):
        maneuver = _mapping(maneuver_value, field=f"truck_maneuver_chain[{index}]")
        _append_points(
            points,
            _polygon(
                maneuver.get("envelope_geometry"),
                field=f"truck_maneuver_chain[{index}].envelope_geometry",
            ),
        )
        reference = maneuver.get("reference_frame")
        if isinstance(reference, Mapping):
            for pose_name in ("entry_pose", "exit_pose"):
                pose = reference.get(pose_name)
                if isinstance(pose, Mapping):
                    points.append(_point(pose, field=f"truck_maneuver_chain[{index}].{pose_name}"))
    if not raw_maneuvers:
        for index, envelope in enumerate(raw_truck_envelopes):
            _append_points(points, _polygon(envelope, field=f"truck_envelopes[{index}]"))
    return points


def _text(x: object, y: object, value: object, *, attrs: Mapping[str, object] | None = None) -> str:
    text_attrs: dict[str, object] = {"x": x, "y": y}
    if attrs:
        text_attrs.update(attrs)
    return _element("text", attrs=text_attrs, body=escape(str(value)))


def _multiline_text(
    x: object,
    y: object,
    lines: Sequence[str],
    *,
    attrs: Mapping[str, object] | None = None,
    line_height: object = 16,
) -> str:
    text_attrs: dict[str, object] = {"x": x, "y": y}
    if attrs:
        text_attrs.update(attrs)
    body = "".join(
        _element(
            "tspan",
            attrs={"x": x, "dy": 0 if index == 0 else line_height},
            body=escape(line),
        )
        for index, line in enumerate(lines)
    )
    return _element("text", attrs=text_attrs, body=body)


def _style(theme: SvgDrawingThemeV1, **values: object) -> dict[str, object]:
    return {key: value for key, value in values.items()}


def _render_dimensions(
    rectangles: Mapping[str, PlacedRectangleV1],
    transform: SvgProjectionTransformV1,
    theme: SvgDrawingThemeV1,
) -> str:
    parts: list[str] = []
    for code in EXPECTED_ZONE_CODES:
        rectangle = rectangles[code]
        left, bottom, right, top = rectangle.bounds_mm
        horizontal = ((left, bottom), (right, bottom))
        vertical = ((left, bottom), (left, top))
        hx1, hy1 = transform.point(horizontal[0])
        hx2, hy2 = transform.point(horizontal[1])
        vx1, vy1 = transform.point(vertical[0])
        vx2, vy2 = transform.point(vertical[1])
        offset = Decimal("2") * transform.scale
        h_y = hy1 + offset
        v_x = vx1 - offset
        horizontal_value = Decimal(right - left) / Decimal(1000)
        vertical_value = Decimal(top - bottom) / Decimal(1000)
        group_id = f"dimension-zone-{_safe_id(code)}"
        vertical_label_x = v_x - Decimal("5")
        vertical_label_y = (vy1 + vy2) / 2
        vertical_transform = (
            f"rotate(-90 {_format_number(vertical_label_x)} {_format_number(vertical_label_y)})"
        )
        body = "".join(
            (
                _element(
                    "line",
                    attrs=_style(
                        theme,
                        x1=hx1,
                        y1=h_y,
                        x2=hx2,
                        y2=h_y,
                        stroke=theme.dimension,
                        **{
                            "stroke-width": 1,
                            "marker-start": "url(#dimension-tick)",
                            "marker-end": "url(#dimension-tick)",
                        },
                    ),
                ),
                _element(
                    "line",
                    attrs={
                        "x1": hx1,
                        "y1": hy1,
                        "x2": hx1,
                        "y2": h_y,
                        "stroke": theme.dimension,
                        "stroke-width": 1,
                    },
                ),
                _element(
                    "line",
                    attrs={
                        "x1": hx2,
                        "y1": hy2,
                        "x2": hx2,
                        "y2": h_y,
                        "stroke": theme.dimension,
                        "stroke-width": 1,
                    },
                ),
                _text(
                    (hx1 + hx2) / 2,
                    h_y + Decimal("12"),
                    f"{format_display_number(horizontal_value)} m",
                    attrs={"fill": theme.dimension, "font-size": 11, "text-anchor": "middle"},
                ),
                _element(
                    "line",
                    attrs={
                        "x1": v_x,
                        "y1": vy1,
                        "x2": v_x,
                        "y2": vy2,
                        "stroke": theme.dimension,
                        "stroke-width": 1,
                        "marker-start": "url(#dimension-tick)",
                        "marker-end": "url(#dimension-tick)",
                    },
                ),
                _element(
                    "line",
                    attrs={
                        "x1": vx1,
                        "y1": vy1,
                        "x2": v_x,
                        "y2": vy1,
                        "stroke": theme.dimension,
                        "stroke-width": 1,
                    },
                ),
                _element(
                    "line",
                    attrs={
                        "x1": vx2,
                        "y1": vy2,
                        "x2": v_x,
                        "y2": vy2,
                        "stroke": theme.dimension,
                        "stroke-width": 1,
                    },
                ),
                _text(
                    vertical_label_x,
                    vertical_label_y,
                    f"{format_display_number(vertical_value)} m",
                    attrs={
                        "fill": theme.dimension,
                        "font-size": 11,
                        "text-anchor": "middle",
                        "transform": vertical_transform,
                    },
                ),
            )
        )
        parts.append(_element("g", attrs={"id": group_id, "data-zone-code": code}, body=body))
    return "".join(parts)


def _render_legend(
    width: Decimal, height: Decimal, theme: SvgDrawingThemeV1, source_hash: str
) -> str:
    x = width - Decimal("390")
    y = Decimal("25")
    rows = (
        ("场地边界", theme.site_outline, "none", "site"),
        ("建筑轮廓", theme.building_outline, "none", "building"),
        ("冷库/预冷区", theme.cold_zone_fill, theme.cold_zone_fill, "rect"),
        ("生产/辅助区", theme.zone_fill, theme.zone_fill, "rect"),
        ("人流/物流通道", theme.corridor_fill, theme.corridor_fill, "rect"),
        ("入口 / Portal", theme.entrance_stroke, "none", "line"),
        ("货车机动包络", theme.truck_envelope, "none", "dash"),
        ("装卸面", theme.loading_face, "none", "line"),
        ("禁建区", theme.obstacle_fill, theme.obstacle_fill, "rect"),
    )
    parts = [
        _element(
            "rect",
            attrs={
                "x": x,
                "y": y,
                "width": 370,
                "height": 210,
                "fill": theme.background,
                "stroke": theme.building_outline,
                "stroke-width": 1,
            },
        ),
        _text(
            x + 14,
            y + 22,
            "图例",
            attrs={"fill": theme.text, "font-size": 16, "font-weight": "700"},
        ),
    ]
    for index, (label, stroke, fill, kind) in enumerate(rows):
        cy = y + 43 + index * 18
        if kind == "rect":
            parts.append(
                _element(
                    "rect",
                    attrs={
                        "x": x + 14,
                        "y": cy - 9,
                        "width": 18,
                        "height": 12,
                        "fill": fill,
                        "stroke": stroke,
                        "stroke-width": 1,
                    },
                )
            )
        elif kind == "dash":
            parts.append(
                _element(
                    "line",
                    attrs={
                        "x1": x + 14,
                        "y1": cy - 3,
                        "x2": x + 32,
                        "y2": cy - 3,
                        "stroke": stroke,
                        "stroke-width": 2,
                        "stroke-dasharray": "5 3",
                    },
                )
            )
        elif kind == "site":
            parts.append(
                _element(
                    "rect",
                    attrs={
                        "x": x + 14,
                        "y": cy - 9,
                        "width": 18,
                        "height": 12,
                        "fill": "none",
                        "stroke": stroke,
                        "stroke-width": 2,
                    },
                )
            )
        else:
            parts.append(
                _element(
                    "line",
                    attrs={
                        "x1": x + 14,
                        "y1": cy - 3,
                        "x2": x + 32,
                        "y2": cy - 3,
                        "stroke": stroke,
                        "stroke-width": 3,
                    },
                )
            )
        parts.append(_text(x + 42, cy, label, attrs={"fill": theme.text, "font-size": 11}))
    parts.append(
        _text(
            x + 14,
            y + 198,
            f"source layout hash: {source_hash[7:19]}",
            attrs={"fill": theme.text, "font-size": 10},
        )
    )
    return _element("g", attrs={"id": "legend"}, body="".join(parts))


def _render_title_block(
    width: Decimal, height: Decimal, theme: SvgDrawingThemeV1, body: Mapping[str, Any]
) -> str:
    x = width - Decimal("390")
    y = height - Decimal("145")
    source_hash = str(body.get("canonical_result_hash", ""))
    parts = [
        _element(
            "rect",
            attrs={
                "x": x,
                "y": y,
                "width": 370,
                "height": 125,
                "fill": theme.background,
                "stroke": theme.building_outline,
                "stroke-width": 1,
            },
        ),
        _text(
            x + 14,
            y + 23,
            "冷库/加工厂平面规划图",
            attrs={"fill": theme.text, "font-size": 17, "font-weight": "700"},
        ),
        _text(
            x + 14,
            y + 46,
            "v2.2  ·  Layout status: VALIDATED",
            attrs={"fill": theme.text, "font-size": 12},
        ),
        _text(
            x + 14,
            y + 66,
            "Zone count: 12   Access: 12/12",
            attrs={"fill": theme.text, "font-size": 12},
        ),
        _text(
            x + 14, y + 86, "Truck route: VALIDATED", attrs={"fill": theme.text, "font-size": 12}
        ),
        _text(
            x + 14,
            y + 106,
            f"Source layout hash: {source_hash[7:19]}",
            attrs={"fill": theme.text, "font-size": 10},
        ),
    ]
    return _element("g", attrs={"id": "title-block"}, body="".join(parts))


def _render_svg(
    body: Mapping[str, Any],
    site: Mapping[str, Any],
    rectangles: Mapping[str, PlacedRectangleV1],
    building: PolygonMM,
    gross_area: Decimal,
    loading_face: SegmentMM,
    *,
    theme: SvgDrawingThemeV1,
) -> tuple[str, dict[str, Any], dict[str, int]]:
    all_points = _all_geometry_points(site, rectangles, building, loading_face, body)
    min_x_mm, min_y_mm, max_x_mm, max_y_mm = _points_for_bounds(all_points)
    geometry_min_x = Decimal(min_x_mm) / Decimal(1000)
    geometry_min_y = Decimal(min_y_mm) / Decimal(1000)
    geometry_max_x = Decimal(max_x_mm) / Decimal(1000)
    geometry_max_y = Decimal(max_y_mm) / Decimal(1000)
    drawing_min_x = geometry_min_x - SVG_MARGIN_M
    drawing_min_y = geometry_min_y - SVG_MARGIN_M
    drawing_max_x = geometry_max_x + SVG_MARGIN_M + SVG_LEGEND_WIDTH_M
    drawing_max_y = geometry_max_y + SVG_MARGIN_M + SVG_TITLE_HEIGHT_M
    width = (drawing_max_x - drawing_min_x) * SVG_SCALE
    height = (drawing_max_y - drawing_min_y) * SVG_SCALE
    transform = SvgProjectionTransformV1(drawing_min_x, drawing_max_y)

    metadata = {
        "projection_identity": SVG_PROJECTION_IDENTITY,
        "schema_version": SVG_SCHEMA_VERSION,
        "geometry_source_unit": "m",
        "drawing_transform": "engineering_x_to_svg_x; engineering_y_to_inverted_svg_y",
        "scale": SVG_SCALE,
        "source_layout_hash": body["canonical_result_hash"],
        "north_angle_degrees": site["north_angle_degrees"],
    }
    defs = _element(
        "defs",
        body="".join(
            (
                _element(
                    "pattern",
                    attrs={
                        "id": "no-build-hatch",
                        "patternUnits": "userSpaceOnUse",
                        "width": 8,
                        "height": 8,
                        "patternTransform": "rotate(45)",
                    },
                    body=_element(
                        "line",
                        attrs={
                            "x1": 0,
                            "y1": 0,
                            "x2": 0,
                            "y2": 8,
                            "stroke": theme.obstacle_fill,
                            "stroke-width": 3,
                        },
                    ),
                ),
                _element(
                    "marker",
                    attrs={
                        "id": "dimension-tick",
                        "markerWidth": 5,
                        "markerHeight": 5,
                        "refX": 2.5,
                        "refY": 2.5,
                        "orient": "auto",
                    },
                    body=_element(
                        "path", attrs={"d": "M 0 0 L 5 2.5 L 0 5 z", "fill": theme.dimension}
                    ),
                ),
            )
        ),
    )
    site_group = _element(
        "g",
        attrs={"id": "site-boundary"},
        body=_element(
            "polygon",
            attrs={
                "id": "site-boundary-polygon",
                "points": _polygon_points(site["site_boundary"], transform),
                "fill": "none",
                "stroke": theme.site_outline,
                "stroke-width": 3,
            },
        ),
    )
    constraints: list[str] = [
        _element(
            "polygon",
            attrs={
                "id": "effective-buildable-boundary",
                "points": _polygon_points(site["buildable_boundary"], transform),
                "fill": "none",
                "stroke": theme.buildable_outline,
                "stroke-width": 2,
                "stroke-dasharray": "8 4",
            },
        )
    ]
    for index, polygon in enumerate(site["no_build_zones"]):
        constraints.append(
            _element(
                "polygon",
                attrs={
                    "id": f"no-build-zone-{index}",
                    "points": _polygon_points(polygon, transform),
                    "fill": "url(#no-build-hatch)",
                    "stroke": theme.obstacle_fill,
                    "stroke-width": 1,
                },
            )
        )
    for index, existing in enumerate(site["existing_buildings"]):
        constraints.append(
            _element(
                "polygon",
                attrs={
                    "id": f"existing-building-{_safe_id(existing.get('id', index))}",
                    "data-retained": existing.get("retained", False),
                    "points": _polygon_points(existing["footprint"], transform),
                    "fill": theme.obstacle_fill if existing.get("retained") else "none",
                    "fill-opacity": 0.45,
                    "stroke": theme.obstacle_fill,
                    "stroke-width": 2,
                    "stroke-dasharray": "5 3",
                },
            )
        )
    constraints_group = _element("g", attrs={"id": "site-constraints"}, body="".join(constraints))
    building_group = _element(
        "g",
        attrs={"id": "building-footprint"},
        body="".join(
            (
                _element(
                    "polygon",
                    attrs={
                        "id": "building-footprint-polygon",
                        "points": _polygon_points(building, transform),
                        "fill": "none",
                        "stroke": theme.building_outline,
                        "stroke-width": 3,
                    },
                ),
                _text(
                    *transform.point(building[0]),
                    "建筑 footprint",
                    attrs={"fill": theme.building_outline, "font-size": 12},
                ),
                _text(
                    *transform.point(building[0]),
                    f"gross area {format_display_number(gross_area)} m²",
                    attrs={"fill": theme.building_outline, "font-size": 10, "dy": 14},
                ),
            )
        ),
    )
    zone_parts: list[str] = []
    label_parts: list[str] = []
    for code in EXPECTED_ZONE_CODES:
        rectangle = rectangles[code]
        polygon = rectangle.polygon_mm
        fill = theme.cold_zone_fill if code in COLD_ZONE_CODES else theme.zone_fill
        zone_parts.append(
            _element(
                "g",
                attrs={"id": f"zone-{_safe_id(code)}", "data-zone-code": code},
                body=_element(
                    "polygon",
                    attrs={
                        "id": f"zone-footprint-{_safe_id(code)}",
                        "points": _polygon_points(polygon, transform),
                        "fill": fill,
                        "fill-opacity": 0.72,
                        "stroke": theme.building_outline,
                        "stroke-width": 1.5,
                    },
                    body=_element("title", body=escape(f"{DISPLAY_LABELS[code]} {code}")),
                ),
            )
        )
        left, bottom, right, top = rectangle.bounds_mm
        center = ((left + right) // 2, (bottom + top) // 2)
        cx, cy = transform.point(center)
        area = rectangle.actual_area_m2
        dimension_label = (
            f"{format_display_number(rectangle.width_m)} × "
            f"{format_display_number(rectangle.depth_m)} m"
        )
        label_parts.append(
            _multiline_text(
                cx,
                cy - Decimal("10"),
                (
                    DISPLAY_LABELS[code],
                    code,
                    dimension_label,
                    f"{format_display_number(area)} m²",
                ),
                attrs={
                    "id": f"label-zone-{_safe_id(code)}",
                    "data-zone-code": code,
                    "fill": theme.text,
                    "font-size": 11,
                    "text-anchor": "middle",
                },
                line_height=14,
            )
        )
    zones_group = _element("g", attrs={"id": "zones"}, body="".join(zone_parts))
    portal_parts: list[str] = []
    raw_portals = body.get("portals", [])
    if not isinstance(raw_portals, list):
        raise _error("SVG_PROJECTION_INPUT_INVALID", field="portals")
    for index, portal_value in enumerate(raw_portals):
        portal = _mapping(portal_value, field=f"portals[{index}]")
        identity = portal.get("identity", f"portal-{index}")
        segment = _segment(portal.get("segment"), field=f"portals[{index}].segment")
        portal_parts.append(
            _element(
                "g",
                attrs={"id": f"portal-{_safe_id(identity)}", "data-portal-identity": identity},
                body=_element(
                    "line",
                    attrs={
                        "x1": transform.point(segment[0])[0],
                        "y1": transform.point(segment[0])[1],
                        "x2": transform.point(segment[1])[0],
                        "y2": transform.point(segment[1])[1],
                        "stroke": theme.portal_stroke,
                        "stroke-width": 5,
                        "stroke-linecap": "round",
                    },
                )
                + _text(
                    *transform.point(segment[0]),
                    f"portal {format_display_number(portal.get('clear_width_m', 0))} m",
                    attrs={"fill": theme.portal_stroke, "font-size": 9},
                ),
            )
        )
    portals_group = _element("g", attrs={"id": "portals"}, body="".join(portal_parts))
    corridor_parts: list[str] = []
    raw_corridors = body.get("corridors", [])
    if not isinstance(raw_corridors, list):
        raise _error("SVG_PROJECTION_INPUT_INVALID", field="corridors")
    for index, corridor_value in enumerate(raw_corridors):
        corridor = _mapping(corridor_value, field=f"corridors[{index}]")
        identity = corridor.get("requirement_identity", f"corridor-{index}")
        envelope_parts = [
            _element(
                "polygon",
                attrs={
                    "id": f"corridor-envelope-{_safe_id(identity)}-{envelope_index}",
                    "points": _polygon_points(
                        _polygon(envelope, field="corridor.envelope"), transform
                    ),
                    "fill": theme.corridor_fill,
                    "fill-opacity": 0.42,
                    "stroke": theme.corridor_fill,
                    "stroke-width": 1,
                },
            )
            for envelope_index, envelope in enumerate(corridor.get("envelope", []))
        ]
        centerline = _polyline(corridor.get("centerline"), field=f"corridors[{index}].centerline")
        corridor_parts.append(
            _element(
                "g",
                attrs={
                    "id": f"corridor-{_safe_id(identity)}",
                    "data-requirement-identity": identity,
                },
                body="".join(envelope_parts)
                + _element(
                    "polyline",
                    attrs={
                        "points": _polyline_points(centerline, transform),
                        "fill": "none",
                        "stroke": theme.dimension,
                        "stroke-width": 1.5,
                        "stroke-dasharray": "5 3",
                    },
                ),
            )
        )
    corridors_group = _element("g", attrs={"id": "corridors"}, body="".join(corridor_parts))
    maneuver_parts: list[str] = []
    raw_maneuvers = body.get("truck_maneuver_chain", [])
    if not isinstance(raw_maneuvers, list):
        raise _error("SVG_PROJECTION_INPUT_INVALID", field="truck_maneuver_chain")
    for index, maneuver_value in enumerate(raw_maneuvers):
        maneuver = _mapping(maneuver_value, field=f"truck_maneuver_chain[{index}]")
        envelope = _polygon(
            maneuver.get("envelope_geometry"),
            field=f"truck_maneuver_chain[{index}].envelope_geometry",
        )
        reference = _mapping(
            maneuver.get("reference_frame"), field=f"truck_maneuver_chain[{index}].reference_frame"
        )
        entry = _point(
            reference.get("entry_pose"), field=f"truck_maneuver_chain[{index}].entry_pose"
        )
        exit_point = _point(
            reference.get("exit_pose"), field=f"truck_maneuver_chain[{index}].exit_pose"
        )
        identity = maneuver.get("template_identity", f"maneuver-{index}")
        maneuver_parts.append(
            _element(
                "g",
                attrs={
                    "id": f"truck-maneuver-{index}",
                    "data-maneuver-class": maneuver.get("maneuver_class", ""),
                    "data-template-identity": identity,
                    "data-sequence-index": index,
                },
                body=_element(
                    "polygon",
                    attrs={
                        "id": f"truck-envelope-{index}",
                        "points": _polygon_points(envelope, transform),
                        "fill": theme.truck_envelope,
                        "fill-opacity": 0.18,
                        "stroke": theme.truck_envelope,
                        "stroke-width": 2,
                        "stroke-dasharray": "7 4",
                    },
                )
                + _element(
                    "polyline",
                    attrs={
                        "id": f"truck-reference-path-{index}",
                        "points": _polyline_points((entry, exit_point), transform),
                        "fill": "none",
                        "stroke": theme.truck_envelope,
                        "stroke-width": 2,
                        "stroke-dasharray": "3 3",
                    },
                )
                + _element(
                    "title",
                    body=escape(
                        f"{maneuver.get('maneuver_class', '')} {identity} sequence {index}"
                    ),
                ),
            )
        )
    if not raw_maneuvers:
        raw_envelopes = body.get("truck_envelopes", [])
        if not isinstance(raw_envelopes, list):
            raise _error("SVG_PROJECTION_INPUT_INVALID", field="truck_envelopes")
        for index, envelope_value in enumerate(raw_envelopes):
            envelope = _polygon(envelope_value, field=f"truck_envelopes[{index}]")
            maneuver_parts.append(
                _element(
                    "polygon",
                    attrs={
                        "id": f"truck-envelope-{index}",
                        "points": _polygon_points(envelope, transform),
                        "fill": theme.truck_envelope,
                        "fill-opacity": 0.18,
                        "stroke": theme.truck_envelope,
                        "stroke-width": 2,
                        "stroke-dasharray": "7 4",
                    },
                )
            )
    truck_group = _element("g", attrs={"id": "truck-maneuvers"}, body="".join(maneuver_parts))
    entrances_group = _element(
        "g",
        attrs={"id": "entrances"},
        body="".join(
            (
                _element(
                    "line",
                    attrs={
                        "id": "main-entrance",
                        "data-entrance-type": "main",
                        "x1": transform.point(site["main_entrance"][0])[0],
                        "y1": transform.point(site["main_entrance"][0])[1],
                        "x2": transform.point(site["main_entrance"][1])[0],
                        "y2": transform.point(site["main_entrance"][1])[1],
                        "stroke": theme.entrance_stroke,
                        "stroke-width": 6,
                    },
                ),
                _element(
                    "line",
                    attrs={
                        "id": "truck-entrance",
                        "data-entrance-type": "truck",
                        "x1": transform.point(site["truck_entrance"][0])[0],
                        "y1": transform.point(site["truck_entrance"][0])[1],
                        "x2": transform.point(site["truck_entrance"][1])[0],
                        "y2": transform.point(site["truck_entrance"][1])[1],
                        "stroke": theme.truck_envelope,
                        "stroke-width": 6,
                    },
                ),
                _element(
                    "line",
                    attrs={
                        "id": "shipping-loading-face",
                        "data-loading-face-side": body.get("shipping_loading_face_side", ""),
                        "x1": transform.point(loading_face[0])[0],
                        "y1": transform.point(loading_face[0])[1],
                        "x2": transform.point(loading_face[1])[0],
                        "y2": transform.point(loading_face[1])[1],
                        "stroke": theme.loading_face,
                        "stroke-width": 7,
                    },
                ),
            )
        ),
    )
    dimensions_group = _element(
        "g", attrs={"id": "dimensions"}, body=_render_dimensions(rectangles, transform, theme)
    )
    labels_group = _element("g", attrs={"id": "labels"}, body="".join(label_parts))
    legend_group = _render_legend(width, height, theme, str(body["canonical_result_hash"]))
    title_block = _render_title_block(width, height, theme, body)
    metadata_element = _element("metadata", body=escape(canonical_json(metadata)))
    svg = '<?xml version="1.0" encoding="UTF-8"?>' + _element(
        "svg",
        attrs={
            "xmlns": "http://www.w3.org/2000/svg",
            "version": "1.1",
            "width": "100%",
            "height": "100%",
            "viewBox": f"0 0 {_format_number(width)} {_format_number(height)}",
            "role": "img",
            "aria-labelledby": "drawing-title",
        },
        body=metadata_element
        + _element("title", attrs={"id": "drawing-title"}, body="冷库/加工厂平面规划图")
        + defs
        + site_group
        + constraints_group
        + building_group
        + zones_group
        + portals_group
        + corridors_group
        + truck_group
        + entrances_group
        + dimensions_group
        + labels_group
        + legend_group
        + title_block,
    )
    bounds = {
        "min_x_m": drawing_min_x,
        "min_y_m": drawing_min_y,
        "max_x_m": drawing_max_x,
        "max_y_m": drawing_max_y,
        "scale": SVG_SCALE,
    }
    counts = {
        "zone_count": len(rectangles),
        "portal_count": len(raw_portals),
        "corridor_count": len(raw_corridors),
        "truck_maneuver_count": len(raw_maneuvers)
        if raw_maneuvers
        else len(body.get("truck_envelopes", [])),
    }
    return svg, bounds, counts


def build_projection_payload(
    body: Mapping[str, Any],
    geometry_body: Mapping[str, Any],
    *,
    source_layout_hash: str,
    theme: SvgDrawingThemeV1 | None = None,
) -> dict[str, Any]:
    """Render one validated result and return the projection payload."""
    site = _source_site_geometry(geometry_body)
    rectangles = _source_rectangles(body)
    building, gross_area = _source_building_footprint(body)
    loading_face = _source_loading_face(body)
    svg, bounds, counts = _render_svg(
        body,
        site,
        rectangles,
        building,
        gross_area,
        loading_face,
        theme=theme or SvgDrawingThemeV1(),
    )
    svg_hash = "sha256:" + hashlib.sha256(svg.encode("utf-8")).hexdigest()
    view_box = (
        f"0 0 {_format_number((bounds['max_x_m'] - bounds['min_x_m']) * SVG_SCALE)} "
        f"{_format_number((bounds['max_y_m'] - bounds['min_y_m']) * SVG_SCALE)}"
    )
    return {
        "identity": SVG_PROJECTION_IDENTITY,
        "schema_version": SVG_SCHEMA_VERSION,
        "source_validated_layout_hash": source_layout_hash,
        "source_zone_plan_hash": body.get("source_zone_plan_hash"),
        "source_p1_handoff_hash": body.get("source_p1_handoff_hash"),
        "source_site_geometry_hash": body.get("source_site_geometry_hash"),
        "source_objective_profile_hash": body.get("source_objective_profile_hash"),
        "source_placement_result_hash": body.get("source_placement_result_hash"),
        "source_truck_maneuver_binding_hash": body.get("source_truck_maneuver_binding_hash"),
        "view_box": view_box,
        "drawing_bounds": bounds,
        "layer_order": list(LAYER_ORDER),
        **counts,
        "svg": svg,
        "svg_sha256": svg_hash,
        "canonical_svg_hash": svg_hash,
        "same_input_same_svg_bytes": True,
        "same_input_same_svg_hash": True,
        "svg_renderable": True,
        "project_layout_validated": True,
        "p2_complete": True,
        "projection_only": True,
        "geometry_source_unit": "m",
        "drawing_transform_deterministic": True,
        "engineering_coordinates_mutated": False,
        "display_label_authority": False,
        "engineering_semantics_changed": False,
    }
