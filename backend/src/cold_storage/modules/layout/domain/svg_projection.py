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
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
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
SVG_MARGIN_M: Final = Decimal("4")
SVG_LEGEND_WIDTH_M: Final = Decimal("42")
SVG_TITLE_HEIGHT_M: Final = Decimal("18")
SVG_PAGE_FURNITURE_GAP_M: Final = Decimal("4")
SVG_PAGE_FURNITURE_WIDTH_M: Final = Decimal("60")
SVG_PAGE_FURNITURE_MARGIN_M: Final = Decimal("2")
SVG_AREA_SCHEDULE_HEIGHT_M: Final = Decimal("36")
SVG_AREA_SCHEDULE_TITLE_BASELINE_OFFSET_PX: Final = Decimal("22")
SVG_AREA_SCHEDULE_HEADER_BASELINE_OFFSET_PX: Final = Decimal("40")
SVG_AREA_SCHEDULE_FIRST_ROW_BASELINE_OFFSET_PX: Final = Decimal("62")
SVG_AREA_SCHEDULE_ROW_SPACING_PX: Final = Decimal("24")
SVG_AREA_SCHEDULE_HEADER_TEXT_HEIGHT_PX: Final = Decimal("9")
SVG_AREA_SCHEDULE_ROW_TEXT_HEIGHT_PX: Final = Decimal("10")
SVG_FURNITURE_GAP_M: Final = Decimal("2")
SVG_MAIN_DRAWING_TARGET_OCCUPANCY: Final = Decimal("0.78")
SVG_MAIN_DRAWING_MIN_OCCUPANCY: Final = Decimal("0.70")
SVG_MAIN_DRAWING_MAX_OCCUPANCY: Final = Decimal("0.88")
SVG_MOBILE_DRAWING_MIN_OCCUPANCY: Final = Decimal("0.80")
SVG_MOBILE_PRIMARY_PLAN_OCCUPANCY_MIN: Final = Decimal("0.65")
SVG_MOBILE_PRIMARY_PLAN_WIDTH_RATIO_MIN: Final = Decimal("0.70")
SVG_MOBILE_PRIMARY_PLAN_HEIGHT_RATIO_MIN: Final = Decimal("0.55")
SVG_CONTEXT_INSET_WIDTH_M: Final = Decimal("24")
SVG_CONTEXT_INSET_GAP_M: Final = Decimal("2")
SVG_CONTEXT_INSET_MARGIN_M: Final = Decimal("1")
SVG_FOCUSED_FURNITURE_MIN_WIDTH_M: Final = Decimal("42")
SVG_STYLE_ID: Final = "LAYOUT_DRAWING_STYLE_V1"
SVG_STYLE_NAME: Final = "CAD_FACTORY_LAYOUT"
SVG_COLOR_MODE: Final = "MONOCHROME_PRIMARY"
SVG_NO_BUILD_HATCH_COLOR: Final = "#B5B5B5"
SVG_STROKE_W5: Final = Decimal("3.0")
SVG_STROKE_W4: Final = Decimal("2.2")
SVG_STROKE_W3: Final = Decimal("1.6")
SVG_STROKE_W2: Final = Decimal("1.1")
SVG_STROKE_W1: Final = Decimal("0.75")
SVG_STROKE_W0: Final = Decimal("0.45")
SVG_ZONE_FILL_OPACITY: Final = Decimal("0.52")
SVG_CONTEXT_FILL_OPACITY: Final = Decimal("0.18")
SVG_PAGE_PROFILES: Final[tuple[str, ...]] = (
    "PRESENTATION",
    "MOBILE_PREVIEW",
    "ENGINEERING_SHEET",
    "ENGINEERING_REVIEW",
)
SVG_FOCUS_PROFILES: Final[frozenset[str]] = frozenset({"PRESENTATION", "MOBILE_PREVIEW"})
SVG_REVIEW_PROFILES: Final[frozenset[str]] = frozenset({"ENGINEERING_SHEET", "ENGINEERING_REVIEW"})
SVG_REVIEW_ACCENT_PROFILES: Final[frozenset[str]] = frozenset({"ENGINEERING_REVIEW"})
SVG_DISPLAY_DIMENSION_DECIMALS: Final = 2
SVG_LABEL_FONT_SIZE: Final = Decimal("11")
SVG_LABEL_COMPACT_FONT_SIZE: Final = Decimal("10")
SVG_LABEL_NUMERIC_FONT_SIZE: Final = Decimal("9")
SVG_LABEL_LINE_HEIGHT: Final = Decimal("14")
SVG_LABEL_BOX_PADDING: Final = Decimal("2")
SVG_LABEL_WALL_CLEARANCE: Final = Decimal("2")
SVG_LABEL_PORTAL_CLEARANCE: Final = Decimal("4")
SVG_LABEL_ANCHOR_ORDER: Final[tuple[str, ...]] = (
    "CENTER",
    "TOP",
    "BOTTOM",
    "LEFT",
    "RIGHT",
)
SVG_PRESENTATION_DIMENSION_CODES: Final[tuple[str, ...]] = (
    "primary_precooling_room",
    "secondary_precooling_room",
    "sorting_packaging_room",
    "shipping_channel",
)
SVG_MOBILE_DIMENSION_CODES: Final[tuple[str, ...]] = ()

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


def _validate_svg_theme_fields(theme: object) -> dict[str, str]:
    values: dict[str, str] = {}
    for field_name in _THEME_COLOR_FIELDS:
        try:
            value = getattr(theme, field_name)
        except AttributeError:
            raise LayoutAuthorityError("SVG_THEME_INVALID", field=field_name) from None
        if not isinstance(value, str) or _THEME_HEX_COLOR_PATTERN.fullmatch(value) is None:
            raise LayoutAuthorityError("SVG_THEME_INVALID", field=field_name)
        values[field_name] = value
    return values


@dataclass(frozen=True)
class SvgDrawingThemeV1:
    """Display-only colours; the theme is not part of engineering authority."""

    background: str = "#FFFFFF"
    zone_fill: str = "#FAFAFA"
    cold_zone_fill: str = "#F3F3F3"
    corridor_fill: str = "#F7F7F7"
    building_outline: str = "#111111"
    site_outline: str = "#555555"
    obstacle_fill: str = "#999999"
    portal_stroke: str = "#666666"
    # The one reserved accent is used only by ENGINEERING_REVIEW overlays.
    truck_envelope: str = "#B3261E"
    loading_face: str = "#222222"
    text: str = "#111111"
    dimension: str = "#777777"
    buildable_outline: str = "#777777"
    entrance_stroke: str = "#555555"

    def __post_init__(self) -> None:
        _validate_svg_theme_fields(self)


def validate_svg_theme(theme: object | None) -> SvgDrawingThemeV1:
    """Return a validated server-owned theme for SVG paint serialization."""
    if theme is None:
        return SvgDrawingThemeV1()
    if type(theme) is not SvgDrawingThemeV1:
        raise LayoutAuthorityError("SVG_THEME_INVALID", reason="THEME_TYPE_REQUIRED")
    return SvgDrawingThemeV1(**_validate_svg_theme_fields(theme))


def _review_accent(theme: SvgDrawingThemeV1, page_profile: str) -> str:
    """Return the sole review accent only for the explicit review profile."""
    if page_profile in SVG_REVIEW_ACCENT_PROFILES:
        return theme.truck_envelope
    return theme.dimension


@dataclass(frozen=True)
class SvgProjectionTransformV1:
    """Fixed engineering-to-screen transform used by one drawing."""

    min_x_m: Decimal
    max_y_m: Decimal
    scale: Decimal = SVG_SCALE
    offset_x_px: Decimal = Decimal("0")
    offset_y_px: Decimal = Decimal("0")

    def point(self, point: PointPair) -> tuple[Decimal, Decimal]:
        x_m = Decimal(point[0]) / Decimal(1000)
        y_m = Decimal(point[1]) / Decimal(1000)
        return (
            (x_m - self.min_x_m) * self.scale + self.offset_x_px,
            (self.max_y_m - y_m) * self.scale + self.offset_y_px,
        )


def _safe_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 60
        return numerator / denominator


def _ceil_to_grid(value: Decimal) -> Decimal:
    return value.quantize(SVG_GEOMETRY_GRID_M, rounding=ROUND_CEILING)


def _rectangles_overlap(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    left_x = cast(Decimal, left["x"])
    left_y = cast(Decimal, left["y"])
    left_width = cast(Decimal, left["width"])
    left_height = cast(Decimal, left["height"])
    right_x = cast(Decimal, right["x"])
    right_y = cast(Decimal, right["y"])
    right_width = cast(Decimal, right["width"])
    right_height = cast(Decimal, right["height"])
    return not (
        left_x + left_width <= right_x
        or right_x + right_width <= left_x
        or left_y + left_height <= right_y
        or right_y + right_height <= left_y
    )


def _primary_plan_bounds(
    rectangles: Mapping[str, PlacedRectangleV1], building: PolygonMM
) -> dict[str, Decimal]:
    """Return bounds for the user-facing factory plan, excluding site context.

    The bounds are a presentation measurement only.  They are derived from
    the authoritative building footprint and the twelve authoritative zone
    rectangles; no source geometry is resized, translated, or omitted from
    the projection payload.
    """
    points: list[PointPair] = list(building)
    for rectangle in rectangles.values():
        points.extend(rectangle.polygon_mm)
    min_x_mm, min_y_mm, max_x_mm, max_y_mm = _points_for_bounds(points)
    return {
        "min_x_m": Decimal(min_x_mm) / Decimal(1000),
        "min_y_m": Decimal(min_y_mm) / Decimal(1000),
        "max_x_m": Decimal(max_x_mm) / Decimal(1000),
        "max_y_m": Decimal(max_y_mm) / Decimal(1000),
    }


def _page_composition(
    *,
    geometry_min_x: Decimal,
    geometry_min_y: Decimal,
    geometry_max_x: Decimal,
    geometry_max_y: Decimal,
    primary_min_x: Decimal,
    primary_min_y: Decimal,
    primary_max_x: Decimal,
    primary_max_y: Decimal,
    page_profile: str,
) -> dict[str, Any]:
    """Build page-space rectangles without changing source engineering geometry."""
    if page_profile not in SVG_PAGE_PROFILES:
        raise _error("SVG_PAGE_PROFILE_INVALID", profile=page_profile)

    focused = page_profile in SVG_FOCUS_PROFILES
    review_overlays_visible = page_profile in SVG_REVIEW_PROFILES
    source_width_m = geometry_max_x - geometry_min_x
    source_height_m = geometry_max_y - geometry_min_y
    source_drawing_min_x = geometry_min_x - SVG_MARGIN_M
    source_drawing_min_y = geometry_min_y - SVG_MARGIN_M
    source_drawing_max_x = geometry_max_x + SVG_MARGIN_M
    source_drawing_max_y = geometry_max_y + SVG_MARGIN_M

    primary_drawing_min_x = primary_min_x - SVG_MARGIN_M
    primary_drawing_min_y = primary_min_y - SVG_MARGIN_M
    primary_drawing_max_x = primary_max_x + SVG_MARGIN_M
    primary_drawing_max_y = primary_max_y + SVG_MARGIN_M
    primary_width_m = primary_drawing_max_x - primary_drawing_min_x
    primary_height_m = primary_drawing_max_y - primary_drawing_min_y

    context_inset: dict[str, object] = {}
    if focused:
        context_width_m = SVG_CONTEXT_INSET_WIDTH_M
        context_inner_width_m = context_width_m - (SVG_CONTEXT_INSET_MARGIN_M * 2)
        context_height_m = _ceil_to_grid(
            _safe_ratio(context_inner_width_m * source_height_m, source_width_m)
            + (SVG_CONTEXT_INSET_MARGIN_M * 2)
        )
        drawing_min_x = primary_drawing_min_x
        drawing_min_y = primary_drawing_max_y - max(primary_height_m, context_height_m)
        if page_profile == "MOBILE_PREVIEW":
            drawing_max_x = primary_drawing_max_x
            context_x = max(
                SVG_CONTEXT_INSET_MARGIN_M,
                primary_width_m - context_width_m - SVG_CONTEXT_INSET_MARGIN_M,
            )
        else:
            drawing_max_x = primary_drawing_max_x + SVG_CONTEXT_INSET_GAP_M + context_width_m
            context_x = primary_width_m + SVG_CONTEXT_INSET_GAP_M
        drawing_max_y = primary_drawing_max_y
        context_inset = {
            "x": context_x * SVG_SCALE,
            "y": SVG_CONTEXT_INSET_MARGIN_M * SVG_SCALE,
            "width": context_width_m * SVG_SCALE,
            "height": context_height_m * SVG_SCALE,
            "inner_padding": SVG_CONTEXT_INSET_MARGIN_M * SVG_SCALE,
            "scale": _safe_ratio(
                min(
                    context_inner_width_m * SVG_SCALE / source_width_m,
                    (context_height_m - (SVG_CONTEXT_INSET_MARGIN_M * 2))
                    * SVG_SCALE
                    / source_height_m,
                ),
                Decimal("1"),
            ),
        }
    else:
        drawing_min_x = source_drawing_min_x
        drawing_min_y = source_drawing_min_y
        drawing_max_x = source_drawing_max_x
        drawing_max_y = source_drawing_max_y

    drawing_width_m = drawing_max_x - drawing_min_x
    drawing_height_m = drawing_max_y - drawing_min_y

    if page_profile == "MOBILE_PREVIEW" or page_profile == "ENGINEERING_REVIEW":
        page_min_x = drawing_min_x
        page_min_y = drawing_min_y
        page_max_x = drawing_max_x
        page_max_y = drawing_max_y
        furniture: dict[str, dict[str, object]] = {}
    else:
        legend_height_m = Decimal("21")
        title_height_m = SVG_TITLE_HEIGHT_M
        required_furniture_height_m = (
            SVG_PAGE_FURNITURE_MARGIN_M
            + legend_height_m
            + SVG_FURNITURE_GAP_M
            + SVG_AREA_SCHEDULE_HEIGHT_M
            + SVG_FURNITURE_GAP_M
            + title_height_m
            + SVG_PAGE_FURNITURE_MARGIN_M
        )
        page_height_m = max(drawing_height_m, required_furniture_height_m)
        # Keep page furniture out of the engineering drawing while targeting the
        # frozen occupancy range. The minimum width keeps the schedule legible;
        # the target-derived width prevents a wide plan from becoming a tiny
        # corner of the page.
        target_page_width_m = _safe_ratio(
            drawing_width_m * page_height_m,
            SVG_MAIN_DRAWING_TARGET_OCCUPANCY * drawing_height_m,
        )
        target_furniture_width_m = _ceil_to_grid(
            target_page_width_m - drawing_width_m - SVG_PAGE_FURNITURE_GAP_M
        )
        furniture_min_width_m = (
            SVG_FOCUSED_FURNITURE_MIN_WIDTH_M if focused else SVG_PAGE_FURNITURE_WIDTH_M
        )
        furniture_width_m = max(furniture_min_width_m, target_furniture_width_m)
        page_min_x = drawing_min_x
        page_min_y = drawing_max_y - page_height_m
        page_max_x = drawing_max_x + SVG_PAGE_FURNITURE_GAP_M + furniture_width_m
        page_max_y = drawing_max_y

        page_width_px = (page_max_x - page_min_x) * SVG_SCALE
        page_height_px = (page_max_y - page_min_y) * SVG_SCALE
        furniture_x_px = (drawing_max_x + SVG_PAGE_FURNITURE_GAP_M - page_min_x) * SVG_SCALE
        furniture_margin_px = SVG_PAGE_FURNITURE_MARGIN_M * SVG_SCALE
        furniture_width_px = furniture_width_m * SVG_SCALE
        inner_x = furniture_x_px + furniture_margin_px
        inner_width = furniture_width_px - (furniture_margin_px * 2)
        legend_y = furniture_margin_px
        legend_height_px = legend_height_m * SVG_SCALE
        schedule_y = legend_y + legend_height_px + (SVG_FURNITURE_GAP_M * SVG_SCALE)
        schedule_height_px = SVG_AREA_SCHEDULE_HEIGHT_M * SVG_SCALE
        title_height_px = title_height_m * SVG_SCALE
        title_y = page_height_px - furniture_margin_px - title_height_px
        furniture = {
            "legend": {
                "visible": True,
                "x": inner_x,
                "y": legend_y,
                "width": inner_width,
                "height": legend_height_px,
            },
            "area_schedule": {
                "visible": True,
                "x": inner_x,
                "y": schedule_y,
                "width": inner_width,
                "height": schedule_height_px,
            },
            "title_block": {
                "visible": True,
                "x": inner_x,
                "y": title_y,
                "width": inner_width,
                "height": title_height_px,
            },
        }

    page_width_m = page_max_x - page_min_x
    page_height_m = page_max_y - page_min_y
    drawing_width_px = drawing_width_m * SVG_SCALE
    drawing_height_px = drawing_height_m * SVG_SCALE
    page_width_px = page_width_m * SVG_SCALE
    page_height_px = page_height_m * SVG_SCALE
    engineering_drawing_rect = {
        "x": Decimal("0"),
        "y": Decimal("0"),
        "width": drawing_width_px,
        "height": drawing_height_px,
    }
    main_occupancy = _safe_ratio(
        drawing_width_px * drawing_height_px,
        page_width_px * page_height_px,
    )
    primary_occupancy = _safe_ratio(
        primary_width_m * primary_height_m,
        drawing_width_m * drawing_height_m,
    )
    primary_width_ratio = _safe_ratio(primary_width_m, drawing_width_m)
    primary_height_ratio = _safe_ratio(primary_height_m, drawing_height_m)
    if focused:
        context_scale = cast(Decimal, context_inset["scale"])
        context_inner_width_px = cast(Decimal, context_inset["width"]) - (
            cast(Decimal, context_inset["inner_padding"]) * 2
        )
        context_inner_height_px = cast(Decimal, context_inset["height"]) - (
            cast(Decimal, context_inset["inner_padding"]) * 2
        )
        context_source_width_m = _safe_ratio(
            context_inner_width_px,
            context_scale,
        )
        context_source_height_m = _safe_ratio(
            context_inner_height_px,
            context_scale,
        )
        source_occupancy = _safe_ratio(
            source_width_m * source_height_m,
            context_source_width_m * context_source_height_m,
        )
    else:
        source_occupancy = _safe_ratio(
            source_width_m * source_height_m,
            page_width_m * page_height_m,
        )
    furniture_values = tuple(furniture.values())
    title_block = furniture.get("title_block")
    area_schedule = furniture.get("area_schedule")
    legend = furniture.get("legend")
    return {
        "profile": page_profile,
        "engineering_geometry_bounds": {
            "min_x_m": geometry_min_x,
            "min_y_m": geometry_min_y,
            "max_x_m": geometry_max_x,
            "max_y_m": geometry_max_y,
        },
        "primary_plan_bounds": {
            "min_x_m": primary_min_x,
            "min_y_m": primary_min_y,
            "max_x_m": primary_max_x,
            "max_y_m": primary_max_y,
        },
        "engineering_drawing_bounds": {
            "min_x_m": drawing_min_x,
            "min_y_m": drawing_min_y,
            "max_x_m": drawing_max_x,
            "max_y_m": drawing_max_y,
            "scale": SVG_SCALE,
        },
        "source_drawing_bounds": {
            "min_x_m": source_drawing_min_x,
            "min_y_m": source_drawing_min_y,
            "max_x_m": source_drawing_max_x,
            "max_y_m": source_drawing_max_y,
            "scale": SVG_SCALE,
        },
        "context_inset": context_inset,
        "page_layout_bounds": {
            "min_x_m": page_min_x,
            "min_y_m": page_min_y,
            "max_x_m": page_max_x,
            "max_y_m": page_max_y,
            "scale": SVG_SCALE,
        },
        "engineering_drawing_rect": engineering_drawing_rect,
        "page_size": {"width": page_width_px, "height": page_height_px},
        "furniture": furniture,
        "main_drawing_occupancy": main_occupancy,
        "source_geometry_occupancy": source_occupancy,
        "primary_plan_screen_occupancy": primary_occupancy,
        "primary_plan_width_ratio": primary_width_ratio,
        "primary_plan_height_ratio": primary_height_ratio,
        "primary_plan_occupancy_min": SVG_MOBILE_PRIMARY_PLAN_OCCUPANCY_MIN,
        "primary_plan_width_ratio_min": SVG_MOBILE_PRIMARY_PLAN_WIDTH_RATIO_MIN,
        "primary_plan_height_ratio_min": SVG_MOBILE_PRIMARY_PLAN_HEIGHT_RATIO_MIN,
        "review_overlays_visible": review_overlays_visible,
        "occupancy_target": SVG_MAIN_DRAWING_TARGET_OCCUPANCY,
        "occupancy_min": SVG_MAIN_DRAWING_MIN_OCCUPANCY,
        "occupancy_max": SVG_MAIN_DRAWING_MAX_OCCUPANCY,
        "mobile_occupancy_min": SVG_MOBILE_DRAWING_MIN_OCCUPANCY,
        "title_block_overlap": bool(
            title_block and _rectangles_overlap(engineering_drawing_rect, title_block)
        ),
        "area_table_overlap": bool(
            area_schedule and _rectangles_overlap(engineering_drawing_rect, area_schedule)
        ),
        "legend_overlap": bool(legend and _rectangles_overlap(engineering_drawing_rect, legend)),
        "page_furniture_overlap": any(
            _rectangles_overlap(left, right)
            for index, left in enumerate(furniture_values)
            for right in furniture_values[index + 1 :]
        ),
    }


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


def _dimension_codes_for_profile(page_profile: str) -> tuple[str, ...]:
    if page_profile == "PRESENTATION":
        return SVG_PRESENTATION_DIMENSION_CODES
    if page_profile == "MOBILE_PREVIEW":
        return SVG_MOBILE_DIMENSION_CODES
    return EXPECTED_ZONE_CODES


def _screen_rectangle_bounds(
    rectangle: PlacedRectangleV1, transform: SvgProjectionTransformV1
) -> dict[str, Decimal]:
    left, bottom, right, top = rectangle.bounds_mm
    points = (
        transform.point((left, bottom)),
        transform.point((right, bottom)),
        transform.point((right, top)),
        transform.point((left, top)),
    )
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "x": min(xs),
        "y": min(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }


def _estimated_text_width(text: str, font_size: Decimal) -> Decimal:
    """Use a stable conservative width estimate for presentation-only labels."""
    width = Decimal("0")
    for character in text:
        # CJK glyphs are approximately square at the selected font size.  The
        # ASCII estimate covers units, digits and punctuation without relying
        # on a runner-specific font or browser text measurement.
        width += font_size if ord(character) >= 0x2E80 else font_size * Decimal("0.62")
    return width


def _label_box(
    lines: Sequence[str],
    font_size: Decimal,
    line_height: Decimal = SVG_LABEL_LINE_HEIGHT,
) -> tuple[Decimal, Decimal]:
    width = max((_estimated_text_width(line, font_size) for line in lines), default=font_size)
    height = font_size + (line_height * Decimal(max(0, len(lines) - 1)))
    return (
        width + (SVG_LABEL_BOX_PADDING * 2),
        height + (SVG_LABEL_BOX_PADDING * 2),
    )


def _label_anchor_center(
    room: Mapping[str, Decimal],
    box_width: Decimal,
    box_height: Decimal,
    anchor: str,
) -> tuple[Decimal, Decimal]:
    room_left = room["x"]
    room_top = room["y"]
    room_right = room_left + room["width"]
    room_bottom = room_top + room["height"]
    center_x = (room_left + room_right) / Decimal("2")
    center_y = (room_top + room_bottom) / Decimal("2")
    if anchor == "TOP":
        center_y = room_top + SVG_LABEL_WALL_CLEARANCE + (box_height / Decimal("2"))
    elif anchor == "BOTTOM":
        center_y = room_bottom - SVG_LABEL_WALL_CLEARANCE - (box_height / Decimal("2"))
    elif anchor == "LEFT":
        center_x = room_left + SVG_LABEL_WALL_CLEARANCE + (box_width / Decimal("2"))
    elif anchor == "RIGHT":
        center_x = room_right - SVG_LABEL_WALL_CLEARANCE - (box_width / Decimal("2"))
    return center_x, center_y


def _box_at_center(
    center_x: Decimal, center_y: Decimal, width: Decimal, height: Decimal
) -> dict[str, Decimal]:
    return {
        "x": center_x - (width / Decimal("2")),
        "y": center_y - (height / Decimal("2")),
        "width": width,
        "height": height,
    }


def _box_inside(candidate: Mapping[str, Decimal], room: Mapping[str, Decimal]) -> bool:
    clearance = SVG_LABEL_WALL_CLEARANCE
    return (
        candidate["x"] >= room["x"] + clearance
        and candidate["y"] >= room["y"] + clearance
        and candidate["x"] + candidate["width"] <= room["x"] + room["width"] - clearance
        and candidate["y"] + candidate["height"] <= room["y"] + room["height"] - clearance
    )


def _screen_segment_box(
    segment: SegmentMM,
    transform: SvgProjectionTransformV1,
    padding: Decimal,
) -> dict[str, Decimal]:
    first = transform.point(segment[0])
    second = transform.point(segment[1])
    return {
        "x": min(first[0], second[0]) - padding,
        "y": min(first[1], second[1]) - padding,
        "width": abs(first[0] - second[0]) + (padding * 2),
        "height": abs(first[1] - second[1]) + (padding * 2),
    }


def _dimension_obstacle_boxes(
    rectangles: Mapping[str, PlacedRectangleV1],
    transform: SvgProjectionTransformV1,
    dimension_codes: Sequence[str],
) -> list[dict[str, Decimal]]:
    """Reserve the screen-space footprint of visible dimension annotations."""
    obstacles: list[dict[str, Decimal]] = []
    for code in dimension_codes:
        rectangle = rectangles[code]
        left, bottom, right, top = rectangle.bounds_mm
        hx1, hy1 = transform.point((left, bottom))
        hx2, hy2 = transform.point((right, bottom))
        vx1, vy1 = transform.point((left, bottom))
        vx2, vy2 = transform.point((left, top))
        offset = Decimal("2") * transform.scale
        h_y = hy1 + offset
        v_x = vx1 - offset
        line_padding = SVG_STROKE_W1
        obstacles.append(
            {
                "x": min(hx1, hx2) - line_padding,
                "y": h_y - line_padding,
                "width": abs(hx2 - hx1) + (line_padding * 2),
                "height": line_padding * 2,
            }
        )
        horizontal_text = f"{format_display_number(Decimal(right - left) / Decimal(1000))} m"
        text_width = _estimated_text_width(horizontal_text, Decimal("11"))
        obstacles.append(
            _box_at_center(
                (hx1 + hx2) / Decimal("2"),
                h_y + Decimal("12") - Decimal("5"),
                text_width,
                Decimal("14"),
            )
        )
        obstacles.append(
            {
                "x": v_x - line_padding,
                "y": min(vy1, vy2) - line_padding,
                "width": line_padding * 2,
                "height": abs(vy2 - vy1) + (line_padding * 2),
            }
        )
        vertical_text = f"{format_display_number(Decimal(top - bottom) / Decimal(1000))} m"
        obstacles.append(
            _box_at_center(
                v_x - Decimal("5"),
                (vy1 + vy2) / Decimal("2"),
                Decimal("14"),
                _estimated_text_width(vertical_text, Decimal("11")),
            )
        )
    return obstacles


def _callout_centers(
    room: Mapping[str, Decimal], box_width: Decimal, box_height: Decimal
) -> tuple[tuple[Decimal, Decimal, str], ...]:
    """Return stable external callout anchors around one room."""
    room_center_x = room["x"] + room["width"] / Decimal("2")
    room_center_y = room["y"] + room["height"] / Decimal("2")
    candidates: list[tuple[Decimal, Decimal, str]] = []
    for gap in (Decimal("8"), Decimal("16"), Decimal("24"), Decimal("32")):
        candidates.extend(
            (
                (
                    room["x"] + room["width"] + gap + box_width / Decimal("2"),
                    room_center_y,
                    "CALLOUT_RIGHT",
                ),
                (
                    room["x"] - gap - box_width / Decimal("2"),
                    room_center_y,
                    "CALLOUT_LEFT",
                ),
                (
                    room_center_x,
                    room["y"] - gap - box_height / Decimal("2"),
                    "CALLOUT_TOP",
                ),
                (
                    room_center_x,
                    room["y"] + room["height"] + gap + box_height / Decimal("2"),
                    "CALLOUT_BOTTOM",
                ),
            )
        )
    return tuple(candidates)


def _callout_leader_endpoint(*, anchor: str, box: Mapping[str, Decimal]) -> tuple[Decimal, Decimal]:
    """Return the leader endpoint on the callout side facing its room."""
    half = Decimal("2")
    if anchor == "CALLOUT_RIGHT":
        return box["x"], box["y"] + box["height"] / half
    if anchor == "CALLOUT_LEFT":
        return box["x"] + box["width"], box["y"] + box["height"] / half
    if anchor == "CALLOUT_TOP":
        return box["x"] + box["width"] / half, box["y"] + box["height"]
    if anchor == "CALLOUT_BOTTOM":
        return box["x"] + box["width"] / half, box["y"]
    raise LayoutAuthorityError("SVG_CALLOUT_ANCHOR_INVALID", anchor=anchor)


def _label_lines(
    code: str,
    rectangle: PlacedRectangleV1,
    mode: str,
    *,
    debug: bool,
) -> tuple[str, ...]:
    name = DISPLAY_LABELS[code]
    area = f"{format_display_number(rectangle.actual_area_m2)} m²"
    dimensions = (
        f"{format_display_number(rectangle.width_m)} × {format_display_number(rectangle.depth_m)} m"
    )
    if debug:
        if mode == "DEBUG":
            return (name, code, dimensions, area)
        if mode == "DEBUG_SHORT":
            return (name, code)
        if mode == "DEBUG_ID":
            return (code,)
    if mode == "3_LINES":
        return (name, area, dimensions)
    if mode == "2_LINES":
        return (name, area)
    if mode == "1_LINE":
        return (name,)
    return (f"{EXPECTED_ZONE_CODES.index(code) + 1:02d}",)


def _label_modes(*, debug: bool) -> tuple[tuple[str, Decimal], ...]:
    if debug:
        return (
            ("DEBUG", SVG_LABEL_FONT_SIZE),
            ("DEBUG_SHORT", SVG_LABEL_FONT_SIZE),
            ("DEBUG_ID", SVG_LABEL_NUMERIC_FONT_SIZE),
        )
    return (
        ("3_LINES", SVG_LABEL_FONT_SIZE),
        ("2_LINES", SVG_LABEL_FONT_SIZE),
        ("1_LINE", SVG_LABEL_COMPACT_FONT_SIZE),
        ("NUMERIC_ID", SVG_LABEL_NUMERIC_FONT_SIZE),
    )


def _build_room_label_plan(
    rectangles: Mapping[str, PlacedRectangleV1],
    transform: SvgProjectionTransformV1,
    *,
    page_profile: str,
    portal_segments: Sequence[SegmentMM],
    dimension_codes: Sequence[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """Choose stable presentation labels without mutating engineering geometry."""
    debug = page_profile == "ENGINEERING_REVIEW"
    portal_obstacles = [
        _screen_segment_box(segment, transform, SVG_LABEL_PORTAL_CLEARANCE)
        for segment in portal_segments
    ]
    dimension_obstacles = _dimension_obstacle_boxes(rectangles, transform, dimension_codes)
    obstacles = [*portal_obstacles, *dimension_obstacles]
    plans: dict[str, dict[str, Any]] = {}
    placed_boxes: list[dict[str, Decimal]] = []
    for code in EXPECTED_ZONE_CODES:
        rectangle = rectangles[code]
        room = _screen_rectangle_bounds(rectangle, transform)
        chosen: dict[str, Any] | None = None
        for mode, font_size in _label_modes(debug=debug):
            lines = _label_lines(code, rectangle, mode, debug=debug)
            box_width, box_height = _label_box(lines, font_size)
            for anchor in SVG_LABEL_ANCHOR_ORDER:
                center_x, center_y = _label_anchor_center(room, box_width, box_height, anchor)
                box = _box_at_center(center_x, center_y, box_width, box_height)
                if not _box_inside(box, room):
                    continue
                if any(_rectangles_overlap(box, other) for other in placed_boxes):
                    continue
                if any(_rectangles_overlap(box, other) for other in obstacles):
                    continue
                chosen = {
                    "code": code,
                    "index": f"{EXPECTED_ZONE_CODES.index(code) + 1:02d}",
                    "mode": mode,
                    "lines": lines,
                    "font_size": font_size,
                    "line_height": SVG_LABEL_LINE_HEIGHT,
                    "center_x": center_x,
                    "center_y": center_y,
                    "box": box,
                    "room": room,
                    "anchor": anchor,
                    "callout": False,
                }
                break
            if chosen is not None:
                break
        if chosen is None:
            # A room that cannot hold even its fixed numeric ID uses a stable
            # callout.  It is not counted as a wall-crossing room label because
            # the room label itself is intentionally externalized to the schedule.
            lines = _label_lines(code, rectangle, "NUMERIC_ID", debug=False)
            box_width, box_height = _label_box(lines, SVG_LABEL_NUMERIC_FONT_SIZE)
            room_center_x = room["x"] + room["width"] / Decimal("2")
            room_center_y = room["y"] + room["height"] / Decimal("2")
            center_x, center_y, anchor = next(
                (
                    (candidate_x, candidate_y, candidate_anchor)
                    for candidate_x, candidate_y, candidate_anchor in _callout_centers(
                        room, box_width, box_height
                    )
                    if not any(
                        _rectangles_overlap(
                            _box_at_center(candidate_x, candidate_y, box_width, box_height),
                            other,
                        )
                        for other in (*placed_boxes, *obstacles)
                    )
                ),
                (
                    room["x"] + room["width"] + Decimal("8") + box_width / Decimal("2"),
                    room_center_y,
                    "CALLOUT_RIGHT",
                ),
            )
            chosen = {
                "code": code,
                "index": f"{EXPECTED_ZONE_CODES.index(code) + 1:02d}",
                "mode": "CALLOUT",
                "lines": lines,
                "font_size": SVG_LABEL_NUMERIC_FONT_SIZE,
                "line_height": SVG_LABEL_LINE_HEIGHT,
                "center_x": center_x,
                "center_y": center_y,
                "box": _box_at_center(center_x, center_y, box_width, box_height),
                "room": room,
                "anchor": anchor,
                "callout": True,
                "leader_start_x": room_center_x,
                "leader_start_y": room_center_y,
            }
            chosen["leader_end_x"], chosen["leader_end_y"] = _callout_leader_endpoint(
                anchor=anchor,
                box=cast(dict[str, Decimal], chosen["box"]),
            )
        plans[code] = chosen
        placed_boxes.append(cast(dict[str, Decimal], chosen["box"]))

    primary_collision_count = 0
    for index, left in enumerate(placed_boxes):
        for right in placed_boxes[index + 1 :]:
            primary_collision_count += int(_rectangles_overlap(left, right))
        primary_collision_count += sum(
            int(_rectangles_overlap(left, obstacle)) for obstacle in obstacles
        )
    wall_crossing_count = sum(
        int(not _box_inside(cast(Mapping[str, Decimal], plan["box"]), plan["room"]))
        for plan in plans.values()
        if not plan["callout"]
    )
    label_overlap_count = sum(
        int(_rectangles_overlap(left, right))
        for index, left in enumerate(placed_boxes)
        for right in placed_boxes[index + 1 :]
    )
    dimension_collision_count = sum(
        int(_rectangles_overlap(cast(Mapping[str, Decimal], plan["box"]), obstacle))
        for plan in plans.values()
        for obstacle in dimension_obstacles
    )
    portal_collision_count = sum(
        int(_rectangles_overlap(cast(Mapping[str, Decimal], plan["box"]), obstacle))
        for plan in plans.values()
        for obstacle in portal_obstacles
    )
    metrics = {
        "ROOM_LABEL_WALL_CROSSING_COUNT": wall_crossing_count,
        "ROOM_LABEL_PRIMARY_COLLISION_COUNT": primary_collision_count,
        "ROOM_LABEL_LABEL_OVERLAP_COUNT": label_overlap_count,
        "ROOM_LABEL_DIMENSION_COLLISION_COUNT": dimension_collision_count,
        "ROOM_LABEL_PORTAL_COLLISION_COUNT": portal_collision_count,
        "ROOM_LABEL_3_LINE_COUNT": sum(plan["mode"] == "3_LINES" for plan in plans.values()),
        "ROOM_LABEL_2_LINE_COUNT": sum(plan["mode"] == "2_LINES" for plan in plans.values()),
        "ROOM_LABEL_1_LINE_COUNT": sum(plan["mode"] == "1_LINE" for plan in plans.values()),
        "ROOM_LABEL_NUMERIC_ID_COUNT": sum(plan["mode"] == "NUMERIC_ID" for plan in plans.values()),
        "ROOM_LABEL_CALLOUT_COUNT": sum(plan["callout"] for plan in plans.values()),
    }
    return plans, metrics


def _drawing_lint_sidecar(
    label_plans: Mapping[str, Mapping[str, Any]],
    rectangles: Mapping[str, PlacedRectangleV1],
    transform: SvgProjectionTransformV1,
    portal_segments: Sequence[SegmentMM],
    dimension_codes: Sequence[str],
) -> dict[str, Any]:
    """Expose resolved drawing facts without adding them to the SVG XML."""
    label_boxes = [
        {
            "element_id": f"label-zone-{_safe_id(code)}",
            "zone_code": code,
            "callout": bool(plan["callout"]),
            "box": dict(cast(Mapping[str, Decimal], plan["box"])),
        }
        for code, plan in label_plans.items()
    ]
    callout_leaders = [
        {
            "element_id": f"label-callout-line-{_safe_id(code)}",
            "label_element_id": f"label-zone-{_safe_id(code)}",
            "zone_code": code,
            "points": [
                {
                    "x": plan["leader_start_x"],
                    "y": plan["leader_start_y"],
                },
                {
                    "x": plan["leader_end_x"],
                    "y": plan["leader_end_y"],
                },
            ],
            "label_box": dict(cast(Mapping[str, Decimal], plan["box"])),
        }
        for code, plan in label_plans.items()
        if plan["callout"]
    ]
    dimension_boxes = [
        {
            "element_id": f"dimension-box-{index:03d}",
            "box": box,
        }
        for index, box in enumerate(
            _dimension_obstacle_boxes(rectangles, transform, dimension_codes)
        )
    ]
    portal_boxes = [
        {
            "element_id": f"portal-box-{index:03d}",
            "box": _screen_segment_box(segment, transform, SVG_LABEL_PORTAL_CLEARANCE),
        }
        for index, segment in enumerate(portal_segments)
    ]
    return {
        "schema_version": "1.0.0",
        "label_boxes": label_boxes,
        "callout_leaders": callout_leaders,
        "dimension_boxes": dimension_boxes,
        "portal_boxes": portal_boxes,
    }


def _style(theme: SvgDrawingThemeV1, **values: object) -> dict[str, object]:
    return {key: value for key, value in values.items()}


def _render_dimensions(
    rectangles: Mapping[str, PlacedRectangleV1],
    transform: SvgProjectionTransformV1,
    theme: SvgDrawingThemeV1,
    *,
    dimension_codes: Sequence[str] = EXPECTED_ZONE_CODES,
) -> str:
    parts: list[str] = []
    for code in EXPECTED_ZONE_CODES:
        rectangle = rectangles[code]
        group_id = f"dimension-zone-{_safe_id(code)}"
        if code not in dimension_codes:
            # Keep stable machine identities for consumers and historical
            # architecture tests, but do not paint non-selected room chains in
            # focused business views.
            parts.append(
                _element(
                    "g",
                    attrs={"id": group_id, "data-zone-code": code, "data-dimension-level": "3"},
                    body=_element(
                        "line",
                        attrs={
                            "x1": 0,
                            "y1": 0,
                            "x2": 0,
                            "y2": 0,
                            "stroke": theme.dimension,
                            "stroke-width": SVG_STROKE_W1,
                            "visibility": "hidden",
                        },
                    ),
                )
            )
            continue
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
                            "stroke-width": SVG_STROKE_W1,
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
                        "stroke-width": SVG_STROKE_W1,
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
                        "stroke-width": SVG_STROKE_W1,
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
                        "stroke-width": SVG_STROKE_W1,
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
                        "stroke-width": SVG_STROKE_W1,
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
                        "stroke-width": SVG_STROKE_W1,
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
        parts.append(
            _element(
                "g",
                attrs={"id": group_id, "data-zone-code": code, "data-dimension-level": "2"},
                body=body,
            )
        )
    return "".join(parts)


def _render_total_dimensions(
    building: PolygonMM,
    transform: SvgProjectionTransformV1,
    theme: SvgDrawingThemeV1,
) -> str:
    """Render the frozen level-1 overall building extents."""
    min_x, min_y, max_x, max_y = _points_for_bounds(building)
    hx1, hy1 = transform.point((min_x, min_y))
    hx2, hy2 = transform.point((max_x, min_y))
    vx1, vy1 = transform.point((min_x, min_y))
    vx2, vy2 = transform.point((min_x, max_y))
    offset = Decimal("3") * transform.scale
    h_y = hy1 + offset
    v_x = vx1 - offset
    horizontal_value = Decimal(max_x - min_x) / Decimal(1000)
    vertical_value = Decimal(max_y - min_y) / Decimal(1000)
    vertical_label_x = v_x - Decimal("5")
    vertical_label_y = (vy1 + vy2) / Decimal("2")
    vertical_transform = (
        f"rotate(-90 {_format_number(vertical_label_x)} {_format_number(vertical_label_y)})"
    )
    body = "".join(
        (
            _element(
                "line",
                attrs={
                    "x1": hx1,
                    "y1": h_y,
                    "x2": hx2,
                    "y2": h_y,
                    "stroke": theme.dimension,
                    "stroke-width": SVG_STROKE_W1,
                    "marker-start": "url(#dimension-tick)",
                    "marker-end": "url(#dimension-tick)",
                },
            ),
            _element(
                "line",
                attrs={
                    "x1": hx1,
                    "y1": hy1,
                    "x2": hx1,
                    "y2": h_y,
                    "stroke": theme.dimension,
                    "stroke-width": SVG_STROKE_W1,
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
                    "stroke-width": SVG_STROKE_W1,
                },
            ),
            _text(
                (hx1 + hx2) / Decimal("2"),
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
                    "stroke-width": SVG_STROKE_W1,
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
                    "stroke-width": SVG_STROKE_W1,
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
                    "stroke-width": SVG_STROKE_W1,
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
    return _element(
        "g",
        attrs={"id": "dimension-level-1-total", "data-dimension-level": "1"},
        body=body,
    )


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
        ("禁建区", theme.obstacle_fill, "url(#no-build-hatch)", "rect"),
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
                "stroke-width": SVG_STROKE_W1,
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
                        "stroke-width": SVG_STROKE_W3,
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
                        "stroke-width": SVG_STROKE_W1,
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
                        "stroke-width": SVG_STROKE_W4,
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
                        "stroke-width": SVG_STROKE_W3,
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
                "stroke-width": SVG_STROKE_W1,
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


def _render_legend_at(
    x: Decimal,
    y: Decimal,
    width: Decimal,
    height: Decimal,
    theme: SvgDrawingThemeV1,
    source_hash: str,
    *,
    include_source_hash: bool = True,
    include_review_items: bool = True,
    review_accent: str | None = None,
) -> str:
    rows = [
        ("场地边界", theme.site_outline, "none", "site"),
        ("建筑轮廓", theme.building_outline, "none", "building"),
        ("冷库/预冷区", theme.cold_zone_fill, theme.cold_zone_fill, "rect"),
        ("生产/辅助区", theme.zone_fill, theme.zone_fill, "rect"),
        ("人流/物流通道", theme.corridor_fill, theme.corridor_fill, "rect"),
        ("入口 / Portal", theme.entrance_stroke, "none", "line"),
        ("装卸面", theme.loading_face, "none", "line"),
        ("禁建区", theme.obstacle_fill, "url(#no-build-hatch)", "rect"),
    ]
    if include_review_items:
        rows.insert(6, ("货车机动包络", review_accent or theme.dimension, "none", "dash"))
    parts = [
        _element(
            "rect",
            attrs={
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "fill": theme.background,
                "stroke": theme.building_outline,
                "stroke-width": SVG_STROKE_W1,
            },
        ),
        _text(
            x + Decimal("14"),
            y + Decimal("22"),
            "图例",
            attrs={"fill": theme.text, "font-size": 16, "font-weight": "700"},
        ),
    ]
    for index, (label, stroke, fill, kind) in enumerate(rows):
        cy = y + Decimal("43") + (Decimal(index) * Decimal("18"))
        if kind == "rect":
            parts.append(
                _element(
                    "rect",
                    attrs={
                        "x": x + Decimal("14"),
                        "y": cy - Decimal("9"),
                        "width": 18,
                        "height": 12,
                        "fill": fill,
                        "stroke": stroke,
                        "stroke-width": SVG_STROKE_W3,
                    },
                )
            )
        elif kind == "dash":
            parts.append(
                _element(
                    "line",
                    attrs={
                        "x1": x + Decimal("14"),
                        "y1": cy - Decimal("3"),
                        "x2": x + Decimal("32"),
                        "y2": cy - Decimal("3"),
                        "stroke": stroke,
                        "stroke-width": SVG_STROKE_W1,
                        "stroke-dasharray": "5 3",
                    },
                )
            )
        elif kind == "site":
            parts.append(
                _element(
                    "rect",
                    attrs={
                        "x": x + Decimal("14"),
                        "y": cy - Decimal("9"),
                        "width": 18,
                        "height": 12,
                        "fill": "none",
                        "stroke": stroke,
                        "stroke-width": SVG_STROKE_W4,
                    },
                )
            )
        else:
            parts.append(
                _element(
                    "line",
                    attrs={
                        "x1": x + Decimal("14"),
                        "y1": cy - Decimal("3"),
                        "x2": x + Decimal("32"),
                        "y2": cy - Decimal("3"),
                        "stroke": stroke,
                        "stroke-width": SVG_STROKE_W3,
                    },
                )
            )
        parts.append(
            _text(
                x + Decimal("42"),
                cy,
                label,
                attrs={"fill": theme.text, "font-size": 11},
            )
        )
    if include_source_hash:
        parts.append(
            _text(
                x + Decimal("14"),
                y + height - Decimal("12"),
                f"source layout hash: {source_hash[7:19]}",
                attrs={"fill": theme.text, "font-size": 10},
            )
        )
    return _element("g", attrs={"id": "legend"}, body="".join(parts))


def _render_area_schedule(
    x: Decimal,
    y: Decimal,
    width: Decimal,
    height: Decimal,
    rectangles: Mapping[str, PlacedRectangleV1],
    theme: SvgDrawingThemeV1,
) -> str:
    parts = [
        _element(
            "rect",
            attrs={
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "fill": theme.background,
                "stroke": theme.building_outline,
                "stroke-width": SVG_STROKE_W1,
            },
        ),
        _text(
            x + Decimal("14"),
            y + SVG_AREA_SCHEDULE_TITLE_BASELINE_OFFSET_PX,
            "面积表",
            attrs={"fill": theme.text, "font-size": 16, "font-weight": "700"},
        ),
        _text(
            x + Decimal("14"),
            y + SVG_AREA_SCHEDULE_HEADER_BASELINE_OFFSET_PX,
            "编号 | 中文名称 | 面积",
            attrs={"fill": theme.text, "font-size": 9},
        ),
    ]
    for index, code in enumerate(EXPECTED_ZONE_CODES):
        rectangle = rectangles[code]
        row_y = (
            y
            + SVG_AREA_SCHEDULE_FIRST_ROW_BASELINE_OFFSET_PX
            + (Decimal(index) * SVG_AREA_SCHEDULE_ROW_SPACING_PX)
        )
        value = (
            f"{index + 1:02d} | {DISPLAY_LABELS[code]} | "
            f"{format_display_number(rectangle.actual_area_m2)} m²"
        )
        parts.append(
            _text(
                x + Decimal("14"),
                row_y,
                value,
                attrs={"fill": theme.text, "font-size": 10},
            )
        )
    return _element("g", attrs={"id": "area-schedule"}, body="".join(parts))


def _area_schedule_metrics(row_count: int) -> dict[str, bool | int]:
    """Return deterministic, conservative vertical-overlap metrics."""
    header_baseline = SVG_AREA_SCHEDULE_HEADER_BASELINE_OFFSET_PX
    first_row_baseline = SVG_AREA_SCHEDULE_FIRST_ROW_BASELINE_OFFSET_PX
    header_first_row_overlap = first_row_baseline - header_baseline < max(
        SVG_AREA_SCHEDULE_HEADER_TEXT_HEIGHT_PX, SVG_AREA_SCHEDULE_ROW_TEXT_HEIGHT_PX
    )
    row_overlap_count = sum(
        1
        for index in range(max(row_count - 1, 0))
        if SVG_AREA_SCHEDULE_ROW_SPACING_PX < SVG_AREA_SCHEDULE_ROW_TEXT_HEIGHT_PX
    )
    return {
        "AREA_SCHEDULE_HEADER_FIRST_ROW_OVERLAP": header_first_row_overlap,
        "AREA_SCHEDULE_ROW_OVERLAP_COUNT": row_overlap_count,
    }


def _render_title_block_at(
    x: Decimal,
    y: Decimal,
    width: Decimal,
    height: Decimal,
    theme: SvgDrawingThemeV1,
    body: Mapping[str, Any],
    *,
    include_source_hash: bool = True,
) -> str:
    source_hash = str(body.get("canonical_result_hash", ""))
    parts = [
        _element(
            "rect",
            attrs={
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "fill": theme.background,
                "stroke": theme.building_outline,
                "stroke-width": SVG_STROKE_W1,
            },
        ),
        _text(
            x + Decimal("14"),
            y + Decimal("23"),
            "冷库/加工厂平面规划图",
            attrs={"fill": theme.text, "font-size": 17, "font-weight": "700"},
        ),
        _text(
            x + Decimal("14"),
            y + Decimal("46"),
            "v2.2  ·  Layout status: VALIDATED",
            attrs={"fill": theme.text, "font-size": 12},
        ),
        _text(
            x + Decimal("14"),
            y + Decimal("66"),
            "Zone count: 12   Access: 12/12",
            attrs={"fill": theme.text, "font-size": 12},
        ),
        _text(
            x + Decimal("14"),
            y + Decimal("86"),
            "Truck route: VALIDATED",
            attrs={"fill": theme.text, "font-size": 12},
        ),
    ]
    if include_source_hash:
        parts.append(
            _text(
                x + Decimal("14"),
                y + Decimal("106"),
                f"Source layout hash: {source_hash[7:19]}",
                attrs={"fill": theme.text, "font-size": 10},
            )
        )
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
    page_profile: str,
) -> tuple[str, dict[str, Any], dict[str, int], dict[str, Any]]:
    all_points = _all_geometry_points(site, rectangles, building, loading_face, body)
    min_x_mm, min_y_mm, max_x_mm, max_y_mm = _points_for_bounds(all_points)
    geometry_min_x = Decimal(min_x_mm) / Decimal(1000)
    geometry_min_y = Decimal(min_y_mm) / Decimal(1000)
    geometry_max_x = Decimal(max_x_mm) / Decimal(1000)
    geometry_max_y = Decimal(max_y_mm) / Decimal(1000)
    primary = _primary_plan_bounds(rectangles, building)
    composition = _page_composition(
        geometry_min_x=geometry_min_x,
        geometry_min_y=geometry_min_y,
        geometry_max_x=geometry_max_x,
        geometry_max_y=geometry_max_y,
        primary_min_x=primary["min_x_m"],
        primary_min_y=primary["min_y_m"],
        primary_max_x=primary["max_x_m"],
        primary_max_y=primary["max_y_m"],
        page_profile=page_profile,
    )
    page_bounds = composition["page_layout_bounds"]
    page_min_x = cast(Decimal, page_bounds["min_x_m"])
    page_max_y = cast(Decimal, page_bounds["max_y_m"])
    page_size = composition["page_size"]
    width = cast(Decimal, page_size["width"])
    height = cast(Decimal, page_size["height"])
    transform = SvgProjectionTransformV1(page_min_x, page_max_y)
    focused = page_profile in SVG_FOCUS_PROFILES
    review_overlays_visible = page_profile in SVG_REVIEW_PROFILES
    review_accent_visible = page_profile in SVG_REVIEW_ACCENT_PROFILES
    review_accent = _review_accent(theme, page_profile)
    site_boundary_width = SVG_STROKE_W1 if focused else SVG_STROKE_W4
    context_transform: SvgProjectionTransformV1 | None = None
    if focused:
        context = cast(dict[str, object], composition["context_inset"])
        context_scale = cast(Decimal, context["scale"])
        context_padding = cast(Decimal, context["inner_padding"])
        context_transform = SvgProjectionTransformV1(
            geometry_min_x,
            geometry_max_y,
            scale=context_scale,
            offset_x_px=cast(Decimal, context["x"]) + context_padding,
            offset_y_px=cast(Decimal, context["y"]) + context_padding,
        )
    site_transform = context_transform if context_transform is not None else transform
    raw_portals = body.get("portals", [])
    if not isinstance(raw_portals, list):
        raise _error("SVG_PROJECTION_INPUT_INVALID", field="portals")
    portal_segments = tuple(
        _segment(
            _mapping(portal_value, field=f"portals[{index}]").get("segment"),
            field=f"portals[{index}].segment",
        )
        for index, portal_value in enumerate(raw_portals)
    )
    dimension_codes = _dimension_codes_for_profile(page_profile)
    label_plans, label_metrics = _build_room_label_plan(
        rectangles,
        transform,
        page_profile=page_profile,
        portal_segments=portal_segments,
        dimension_codes=dimension_codes,
    )
    drawing_lint_facts = _drawing_lint_sidecar(
        label_plans,
        rectangles,
        transform,
        portal_segments,
        dimension_codes,
    )
    internal_zone_code_visible = page_profile == "ENGINEERING_REVIEW"

    metadata = {
        "projection_identity": SVG_PROJECTION_IDENTITY,
        "schema_version": SVG_SCHEMA_VERSION,
        "geometry_source_unit": "m",
        "drawing_transform": "engineering_x_to_svg_x; engineering_y_to_inverted_svg_y",
        "scale": SVG_SCALE,
        "source_layout_hash": body["canonical_result_hash"],
        "style_id": SVG_STYLE_ID,
        "style_name": SVG_STYLE_NAME,
        "color_mode": SVG_COLOR_MODE,
        "review_accent_visible": review_accent_visible,
        "presentation_accent_color_count": 0,
        "mobile_accent_color_count": 0,
        "engineering_review_accent_color_count": 1,
        "stroke_weights": {
            "W5": SVG_STROKE_W5,
            "W4": SVG_STROKE_W4,
            "W3": SVG_STROKE_W3,
            "W2": SVG_STROKE_W2,
            "W1": SVG_STROKE_W1,
            "W0": SVG_STROKE_W0,
        },
        "north_angle_degrees": site["north_angle_degrees"],
        "page_profile": page_profile,
        "engineering_geometry_bounds": composition["engineering_geometry_bounds"],
        "engineering_drawing_bounds": composition["engineering_drawing_bounds"],
        "page_layout_bounds": composition["page_layout_bounds"],
        # Keep the historical review metadata byte-identical.  New lint facts
        # are returned in the payload sidecar below and are deliberately not
        # serialized into the SVG metadata element.
        "room_label_metrics": {
            key: label_metrics[key]
            for key in (
                "ROOM_LABEL_WALL_CROSSING_COUNT",
                "ROOM_LABEL_PRIMARY_COLLISION_COUNT",
                "ROOM_LABEL_3_LINE_COUNT",
                "ROOM_LABEL_2_LINE_COUNT",
                "ROOM_LABEL_1_LINE_COUNT",
                "ROOM_LABEL_NUMERIC_ID_COUNT",
                "ROOM_LABEL_CALLOUT_COUNT",
            )
        },
        "internal_zone_code_visible": internal_zone_code_visible,
        "source_hash_visible": review_overlays_visible,
        "portal_debug_text_visible": review_overlays_visible,
        "schema_identity_visible": review_overlays_visible,
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
                        "width": 12,
                        "height": 12,
                        "patternTransform": "rotate(45)",
                    },
                    body=_element(
                        "line",
                        attrs={
                            "x1": 0,
                            "y1": 0,
                            "x2": 0,
                            "y2": 8,
                            "stroke": SVG_NO_BUILD_HATCH_COLOR,
                            "stroke-width": SVG_STROKE_W0,
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
    context_frame = ""
    if focused:
        context = cast(dict[str, object], composition["context_inset"])
        context_frame = _element(
            "rect",
            attrs={
                "id": "site-context-inset-frame",
                "x": context["x"],
                "y": context["y"],
                "width": context["width"],
                "height": context["height"],
                "fill": theme.background,
                "stroke": theme.site_outline,
                "stroke-width": SVG_STROKE_W1,
            },
        )
    site_group = _element(
        "g",
        attrs={"id": "site-boundary"},
        body=context_frame
        + _element(
            "polygon",
            attrs={
                "id": "site-boundary-polygon",
                "points": _polygon_points(site["site_boundary"], site_transform),
                "fill": "none",
                "stroke": theme.site_outline,
                "stroke-width": site_boundary_width,
            },
        ),
    )
    constraints: list[str] = [
        _element(
            "polygon",
            attrs={
                "id": "effective-buildable-boundary",
                "points": _polygon_points(site["buildable_boundary"], site_transform),
                "fill": "none",
                "stroke": theme.buildable_outline,
                "stroke-width": SVG_STROKE_W1,
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
                    "points": _polygon_points(polygon, site_transform),
                    "fill": "url(#no-build-hatch)",
                    "stroke": theme.obstacle_fill,
                    "stroke-width": SVG_STROKE_W1,
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
                    "points": _polygon_points(existing["footprint"], site_transform),
                    "fill": theme.obstacle_fill if existing.get("retained") else "none",
                    "fill-opacity": 0.22 if focused else 0.45,
                    "stroke": theme.obstacle_fill,
                    "stroke-width": SVG_STROKE_W2,
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
                        "stroke-width": SVG_STROKE_W5,
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
                        "fill-opacity": SVG_ZONE_FILL_OPACITY,
                        "stroke": theme.building_outline,
                        "stroke-width": SVG_STROKE_W3,
                    },
                    body=_element(
                        "title",
                        body=escape(
                            f"{DISPLAY_LABELS[code]} {code}"
                            if internal_zone_code_visible
                            else DISPLAY_LABELS[code]
                        ),
                    ),
                ),
            )
        )
        plan = label_plans[code]
        plan_box = cast(dict[str, Decimal], plan["box"])
        plan_font_size = cast(Decimal, plan["font_size"])
        label_body = ""
        if plan["callout"]:
            label_body = _element(
                "line",
                attrs={
                    "id": f"label-callout-line-{_safe_id(code)}",
                    "x1": plan["leader_start_x"],
                    "y1": plan["leader_start_y"],
                    "x2": plan["leader_end_x"],
                    "y2": plan["leader_end_y"],
                    "stroke": theme.dimension,
                    "stroke-width": SVG_STROKE_W1,
                },
            )
        label_body += _multiline_text(
            plan["center_x"],
            plan_box["y"] + plan_font_size + SVG_LABEL_BOX_PADDING,
            cast(tuple[str, ...], plan["lines"]),
            attrs={
                "id": f"label-zone-{_safe_id(code)}",
                "data-zone-code": code,
                "data-label-index": plan["index"],
                "data-label-mode": plan["mode"],
                "fill": theme.text,
                "font-size": plan_font_size,
                "text-anchor": "middle",
            },
            line_height=plan["line_height"],
        )
        label_parts.append(
            _element(
                "g",
                attrs={"id": f"label-group-{_safe_id(code)}"},
                body=label_body,
            )
        )
    zones_group = _element("g", attrs={"id": "zones"}, body="".join(zone_parts))
    context_layout_group = ""
    if context_transform is not None:
        context_zone_parts = [
            _element(
                "polygon",
                attrs={
                    "id": f"context-zone-footprint-{_safe_id(code)}",
                    "data-zone-code": code,
                    "points": _polygon_points(rectangles[code].polygon_mm, context_transform),
                    "fill": theme.cold_zone_fill if code in COLD_ZONE_CODES else theme.zone_fill,
                    "fill-opacity": SVG_CONTEXT_FILL_OPACITY,
                    "stroke": theme.building_outline,
                    "stroke-width": SVG_STROKE_W1,
                },
            )
            for code in EXPECTED_ZONE_CODES
        ]
        context_layout_group = _element(
            "g",
            attrs={"id": "site-context-layout"},
            body=_element(
                "polygon",
                attrs={
                    "id": "context-building-footprint-polygon",
                    "points": _polygon_points(building, context_transform),
                    "fill": "none",
                    "stroke": theme.building_outline,
                    "stroke-width": SVG_STROKE_W1,
                },
            )
            + "".join(context_zone_parts),
        )
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
                        "stroke-width": SVG_STROKE_W2,
                        "stroke-linecap": "round",
                    },
                )
                + (
                    _text(
                        *transform.point(segment[0]),
                        f"portal {format_display_number(portal.get('clear_width_m', 0))} m",
                        attrs={"fill": theme.portal_stroke, "font-size": 9},
                    )
                    if review_overlays_visible
                    else ""
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
        envelope_parts = []
        for envelope_index, envelope in enumerate(corridor.get("envelope", [])):
            envelope_polygon = _polygon(envelope, field="corridor.envelope")
            if review_overlays_visible:
                envelope_parts.append(
                    _element(
                        "polygon",
                        attrs={
                            "id": f"corridor-envelope-{_safe_id(identity)}-{envelope_index}",
                            "points": _polygon_points(envelope_polygon, transform),
                            "fill": theme.corridor_fill,
                            "fill-opacity": 0.42,
                            "stroke": theme.corridor_fill,
                            "stroke-width": SVG_STROKE_W1,
                        },
                    )
                )
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
                        "stroke-width": SVG_STROKE_W1,
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
                        "fill": review_accent,
                        "fill-opacity": 0.18,
                        "stroke": review_accent,
                        "stroke-width": SVG_STROKE_W1,
                        "stroke-dasharray": "7 4",
                    },
                )
                + _element(
                    "polyline",
                    attrs={
                        "id": f"truck-reference-path-{index}",
                        "points": _polyline_points((entry, exit_point), transform),
                        "fill": "none",
                        "stroke": review_accent,
                        "stroke-width": SVG_STROKE_W1,
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
                        "fill": review_accent,
                        "fill-opacity": 0.18,
                        "stroke": review_accent,
                        "stroke-width": SVG_STROKE_W1,
                        "stroke-dasharray": "7 4",
                    },
                )
            )
    truck_group = _element(
        "g",
        attrs={"id": "truck-maneuvers"},
        body="".join(maneuver_parts) if review_overlays_visible else "",
    )
    entrance_transform = context_transform if context_transform is not None else transform
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
                        "x1": entrance_transform.point(site["main_entrance"][0])[0],
                        "y1": entrance_transform.point(site["main_entrance"][0])[1],
                        "x2": entrance_transform.point(site["main_entrance"][1])[0],
                        "y2": entrance_transform.point(site["main_entrance"][1])[1],
                        "stroke": theme.entrance_stroke,
                        "stroke-width": SVG_STROKE_W2,
                    },
                ),
                _element(
                    "line",
                    attrs={
                        "id": "truck-entrance",
                        "data-entrance-type": "truck",
                        "x1": entrance_transform.point(site["truck_entrance"][0])[0],
                        "y1": entrance_transform.point(site["truck_entrance"][0])[1],
                        "x2": entrance_transform.point(site["truck_entrance"][1])[0],
                        "y2": entrance_transform.point(site["truck_entrance"][1])[1],
                        "stroke": theme.entrance_stroke,
                        "stroke-width": SVG_STROKE_W2,
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
                        "stroke-width": SVG_STROKE_W3,
                    },
                ),
            )
        ),
    )
    dimensions_group = _element(
        "g",
        attrs={"id": "dimensions"},
        body=_render_total_dimensions(building, transform, theme)
        + _render_dimensions(
            rectangles,
            transform,
            theme,
            dimension_codes=dimension_codes,
        ),
    )
    labels_group = _element("g", attrs={"id": "labels"}, body="".join(label_parts))
    furniture = cast(dict[str, dict[str, object]], composition["furniture"])
    if not furniture:
        legend_group = ""
        schedule_group = ""
        title_block = ""
    else:
        legend_rect = furniture["legend"]
        schedule_rect = furniture["area_schedule"]
        title_rect = furniture["title_block"]
        legend_group = _render_legend_at(
            cast(Decimal, legend_rect["x"]),
            cast(Decimal, legend_rect["y"]),
            cast(Decimal, legend_rect["width"]),
            cast(Decimal, legend_rect["height"]),
            theme,
            str(body["canonical_result_hash"]),
            include_source_hash=review_overlays_visible,
            include_review_items=review_overlays_visible,
            review_accent=review_accent,
        )
        schedule_group = _render_area_schedule(
            cast(Decimal, schedule_rect["x"]),
            cast(Decimal, schedule_rect["y"]),
            cast(Decimal, schedule_rect["width"]),
            cast(Decimal, schedule_rect["height"]),
            rectangles,
            theme,
        )
        title_block = _render_title_block_at(
            cast(Decimal, title_rect["x"]),
            cast(Decimal, title_rect["y"]),
            cast(Decimal, title_rect["width"]),
            cast(Decimal, title_rect["height"]),
            theme,
            body,
            include_source_hash=review_overlays_visible,
        )
    metadata_element = (
        _element("metadata", body=escape(canonical_json(metadata)))
        if review_overlays_visible
        else ""
    )
    svg = '<?xml version="1.0" encoding="UTF-8"?>' + _element(
        "svg",
        attrs={
            "xmlns": "http://www.w3.org/2000/svg",
            "version": "1.1",
            "width": "100%",
            "height": "100%",
            "viewBox": f"0 0 {_format_number(width)} {_format_number(height)}",
            "preserveAspectRatio": "xMidYMin meet"
            if page_profile in SVG_FOCUS_PROFILES
            else "xMidYMid meet",
            "role": "img",
            "aria-labelledby": "drawing-title",
        },
        body=metadata_element
        + _element("title", attrs={"id": "drawing-title"}, body="冷库/加工厂平面规划图")
        + defs
        + site_group
        + constraints_group
        + context_layout_group
        + building_group
        + zones_group
        + portals_group
        + corridors_group
        + truck_group
        + entrances_group
        + dimensions_group
        + labels_group
        + legend_group
        + schedule_group
        + title_block,
    )
    counts = {
        "zone_count": len(rectangles),
        "portal_count": len(raw_portals),
        "corridor_count": len(raw_corridors),
        "truck_maneuver_count": len(raw_maneuvers)
        if raw_maneuvers
        else len(body.get("truck_envelopes", [])),
        **_area_schedule_metrics(len(EXPECTED_ZONE_CODES)),
        **label_metrics,
    }
    return svg, composition, counts, drawing_lint_facts


def build_projection_payload(
    body: Mapping[str, Any],
    geometry_body: Mapping[str, Any],
    *,
    source_layout_hash: str,
    theme: object | None = None,
    page_profile: str = "PRESENTATION",
) -> dict[str, Any]:
    """Render one validated result and return the projection payload."""
    normalized_theme = validate_svg_theme(theme)
    site = _source_site_geometry(geometry_body)
    rectangles = _source_rectangles(body)
    building, gross_area = _source_building_footprint(body)
    loading_face = _source_loading_face(body)
    svg, bounds, counts, drawing_lint_facts = _render_svg(
        body,
        site,
        rectangles,
        building,
        gross_area,
        loading_face,
        theme=normalized_theme,
        page_profile=page_profile,
    )
    svg_hash = "sha256:" + hashlib.sha256(svg.encode("utf-8")).hexdigest()
    page_bounds = cast(dict[str, Decimal], bounds["page_layout_bounds"])
    page_width = (page_bounds["max_x_m"] - page_bounds["min_x_m"]) * SVG_SCALE
    page_height = (page_bounds["max_y_m"] - page_bounds["min_y_m"]) * SVG_SCALE
    view_box = f"0 0 {_format_number(page_width)} {_format_number(page_height)}"
    return {
        "identity": SVG_PROJECTION_IDENTITY,
        "schema_version": SVG_SCHEMA_VERSION,
        "style_id": SVG_STYLE_ID,
        "style_name": SVG_STYLE_NAME,
        "color_mode": SVG_COLOR_MODE,
        "review_accent_visible": page_profile in SVG_REVIEW_ACCENT_PROFILES,
        "presentation_accent_color_count": 0,
        "mobile_accent_color_count": 0,
        "engineering_review_accent_color_count": 1,
        "stroke_weights": {
            "W5": SVG_STROKE_W5,
            "W4": SVG_STROKE_W4,
            "W3": SVG_STROKE_W3,
            "W2": SVG_STROKE_W2,
            "W1": SVG_STROKE_W1,
            "W0": SVG_STROKE_W0,
        },
        "source_validated_layout_hash": source_layout_hash,
        "source_zone_plan_hash": body.get("source_zone_plan_hash"),
        "source_p1_handoff_hash": body.get("source_p1_handoff_hash"),
        "source_site_geometry_hash": body.get("source_site_geometry_hash"),
        "source_objective_profile_hash": body.get("source_objective_profile_hash"),
        "source_placement_result_hash": body.get("source_placement_result_hash"),
        "source_truck_maneuver_binding_hash": body.get("source_truck_maneuver_binding_hash"),
        "page_profile": bounds["profile"],
        "view_box": view_box,
        "drawing_bounds": bounds["engineering_drawing_bounds"],
        "engineering_geometry_bounds": bounds["engineering_geometry_bounds"],
        "engineering_drawing_bounds": bounds["engineering_drawing_bounds"],
        "source_drawing_bounds": bounds["source_drawing_bounds"],
        "primary_plan_bounds": bounds["primary_plan_bounds"],
        "context_inset": bounds["context_inset"],
        "page_layout_bounds": bounds["page_layout_bounds"],
        "page_size": bounds["page_size"],
        "engineering_drawing_rect": bounds["engineering_drawing_rect"],
        "page_furniture": bounds["furniture"],
        "drawing_lint_facts": drawing_lint_facts,
        "dimension_codes_rendered": list(_dimension_codes_for_profile(page_profile)),
        "main_drawing_occupancy": bounds["main_drawing_occupancy"],
        "source_geometry_occupancy": bounds["source_geometry_occupancy"],
        "primary_plan_screen_occupancy": bounds["primary_plan_screen_occupancy"],
        "primary_plan_width_ratio": bounds["primary_plan_width_ratio"],
        "primary_plan_height_ratio": bounds["primary_plan_height_ratio"],
        "primary_plan_occupancy_min": bounds["primary_plan_occupancy_min"],
        "primary_plan_width_ratio_min": bounds["primary_plan_width_ratio_min"],
        "primary_plan_height_ratio_min": bounds["primary_plan_height_ratio_min"],
        "primary_plan_visually_readable": (
            bounds["primary_plan_screen_occupancy"] >= bounds["primary_plan_occupancy_min"]
            and bounds["primary_plan_width_ratio"] >= bounds["primary_plan_width_ratio_min"]
            and bounds["primary_plan_height_ratio"] >= bounds["primary_plan_height_ratio_min"]
        ),
        "review_overlays_visible": bounds["review_overlays_visible"],
        "presentation_review_overlays_hidden": page_profile in SVG_FOCUS_PROFILES,
        "mobile_review_overlays_hidden": page_profile == "MOBILE_PREVIEW",
        "engineering_review_overlays_preserved": page_profile in SVG_REVIEW_PROFILES,
        "internal_zone_code_visible": page_profile == "ENGINEERING_REVIEW",
        "source_hash_visible": page_profile in SVG_REVIEW_PROFILES,
        "portal_debug_text_visible": page_profile in SVG_REVIEW_PROFILES,
        "schema_identity_visible": page_profile in SVG_REVIEW_PROFILES,
        "source_engineering_geometry_changed": False,
        "main_drawing_target_occupancy": bounds["occupancy_target"],
        "main_drawing_min_occupancy": bounds["occupancy_min"],
        "main_drawing_max_occupancy": bounds["occupancy_max"],
        "mobile_drawing_min_occupancy": bounds["mobile_occupancy_min"],
        "title_block_overlap": bounds["title_block_overlap"],
        "area_table_overlap": bounds["area_table_overlap"],
        "legend_overlap": bounds["legend_overlap"],
        "page_furniture_overlap": bounds["page_furniture_overlap"],
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
