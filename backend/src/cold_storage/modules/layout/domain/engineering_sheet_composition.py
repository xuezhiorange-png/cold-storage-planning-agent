"""Deterministic page-composition candidates for the Engineering Sheet.

This module places already-resolved drawing panels in page space.  It has no
engineering authority: every supplied geometry bound is preserved and only
the presentation rectangles are calculated here.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Any, Final

ENGINEERING_SHEET_CANDIDATE_ORDER: Final[tuple[str, ...]] = ("RIGHT_RAIL", "BOTTOM_RAIL")
ENGINEERING_SHEET_CANDIDATE_IDENTITY: Final = "engineering-sheet-composition@1.0.0"
ENGINEERING_SHEET_MAIN_DRAWING_MIN_OCCUPANCY: Final = Decimal("0.70")
ENGINEERING_SHEET_MAIN_DRAWING_TARGET_OCCUPANCY: Final = Decimal("0.78")
ENGINEERING_SHEET_MAIN_DRAWING_MAX_OCCUPANCY: Final = Decimal("0.88")
ENGINEERING_SHEET_PRIMARY_PLAN_MIN_OCCUPANCY: Final = Decimal("0.65")
ENGINEERING_SHEET_PRIMARY_PLAN_MIN_WIDTH_RATIO: Final = Decimal("0.70")
ENGINEERING_SHEET_PRIMARY_PLAN_MIN_HEIGHT_RATIO: Final = Decimal("0.55")

_SCALE: Final = Decimal("10")
_DRAWING_MARGIN_M: Final = Decimal("4")
_PAGE_GAP_M: Final = Decimal("0.1")
_PANEL_GAP_M: Final = Decimal("0.1")
_PANEL_MARGIN_M: Final = Decimal("1")
_CONTEXT_WIDTH_M: Final = Decimal("12")
_LEGEND_WIDTH_M: Final = Decimal("12")
_LEGEND_HEIGHT_M: Final = Decimal("21")
_SCHEDULE_WIDTH_M: Final = Decimal("21.9")
_SCHEDULE_HEIGHT_M: Final = Decimal("36")
_TITLE_WIDTH_M: Final = Decimal("21.9")
_TITLE_HEIGHT_M: Final = Decimal("18")


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 60
        return numerator / denominator


def _ceil_grid(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.001"), rounding=ROUND_CEILING)


def _rect(x: Decimal, y: Decimal, width: Decimal, height: Decimal) -> dict[str, object]:
    return {"visible": True, "x": x, "y": y, "width": width, "height": height}


def _rectangles_overlap(left: dict[str, object], right: dict[str, object]) -> bool:
    left_x = Decimal(str(left["x"]))
    left_y = Decimal(str(left["y"]))
    left_width = Decimal(str(left["width"]))
    left_height = Decimal(str(left["height"]))
    right_x = Decimal(str(right["x"]))
    right_y = Decimal(str(right["y"]))
    right_width = Decimal(str(right["width"]))
    right_height = Decimal(str(right["height"]))
    return not (
        left_x + left_width <= right_x
        or right_x + right_width <= left_x
        or left_y + left_height <= right_y
        or right_y + right_height <= left_y
    )


def _candidate_rectangles(
    *,
    candidate: str,
    drawing_width_m: Decimal,
    drawing_height_m: Decimal,
    source_width_m: Decimal,
    source_height_m: Decimal,
) -> tuple[Decimal, Decimal, dict[str, dict[str, object]], dict[str, object]]:
    context_inner_width_m = _CONTEXT_WIDTH_M - (2 * _PANEL_MARGIN_M)
    context_height_m = _ceil_grid(
        _ratio(context_inner_width_m * source_height_m, source_width_m) + (2 * _PANEL_MARGIN_M)
    )
    context_stack_height_m = context_height_m + _PANEL_GAP_M + _LEGEND_HEIGHT_M
    title_stack_height_m = _SCHEDULE_HEIGHT_M + _PANEL_GAP_M + _TITLE_HEIGHT_M

    if candidate == "RIGHT_RAIL":
        context_x_m = drawing_width_m + _PAGE_GAP_M
        legend_x_m = context_x_m
        title_x_m = context_x_m + _CONTEXT_WIDTH_M + _PANEL_GAP_M
        context_y_m = (drawing_height_m - context_stack_height_m) / 2
        legend_y_m = context_y_m + context_height_m + _PANEL_GAP_M
        title_y_m = (drawing_height_m - title_stack_height_m) / 2
        schedule_y_m = title_y_m
        furniture = {
            "site_context_inset": _rect(
                context_x_m * _SCALE,
                context_y_m * _SCALE,
                _CONTEXT_WIDTH_M * _SCALE,
                context_height_m * _SCALE,
            ),
            "legend": _rect(
                legend_x_m * _SCALE,
                legend_y_m * _SCALE,
                _LEGEND_WIDTH_M * _SCALE,
                _LEGEND_HEIGHT_M * _SCALE,
            ),
            "area_schedule": _rect(
                title_x_m * _SCALE,
                schedule_y_m * _SCALE,
                _SCHEDULE_WIDTH_M * _SCALE,
                _SCHEDULE_HEIGHT_M * _SCALE,
            ),
            "title_block": _rect(
                title_x_m * _SCALE,
                (title_y_m + _SCHEDULE_HEIGHT_M + _PANEL_GAP_M) * _SCALE,
                _TITLE_WIDTH_M * _SCALE,
                _TITLE_HEIGHT_M * _SCALE,
            ),
        }
        rail_width_m = _PAGE_GAP_M + _CONTEXT_WIDTH_M + _PANEL_GAP_M + _SCHEDULE_WIDTH_M
        page_width_m = drawing_width_m + rail_width_m
        page_height_m = max(
            drawing_height_m,
            max(context_stack_height_m, title_stack_height_m) + (2 * _PANEL_MARGIN_M),
        )
        context_bounds: dict[str, object] = {
            "x": context_x_m * _SCALE,
            "y": context_y_m * _SCALE,
            "width": _CONTEXT_WIDTH_M * _SCALE,
            "height": context_height_m * _SCALE,
            "inner_padding": _PANEL_MARGIN_M * _SCALE,
            "scale": _ratio(
                context_inner_width_m * _SCALE,
                source_width_m,
            ),
        }
    elif candidate == "BOTTOM_RAIL":
        page_width_m = max(
            drawing_width_m,
            _CONTEXT_WIDTH_M
            + _PANEL_GAP_M
            + _LEGEND_WIDTH_M
            + _PANEL_GAP_M
            + _SCHEDULE_WIDTH_M
            + _PANEL_GAP_M
            + _TITLE_WIDTH_M,
        )
        rail_height_m = max(
            context_height_m,
            _LEGEND_HEIGHT_M,
            _SCHEDULE_HEIGHT_M,
            _TITLE_HEIGHT_M,
        )
        page_height_m = drawing_height_m + _PAGE_GAP_M + rail_height_m
        context_x_m = _PANEL_MARGIN_M
        legend_x_m = context_x_m + _CONTEXT_WIDTH_M + _PANEL_GAP_M
        schedule_x_m = legend_x_m + _LEGEND_WIDTH_M + _PANEL_GAP_M
        title_x_m = schedule_x_m + _SCHEDULE_WIDTH_M + _PANEL_GAP_M
        rail_y_m = drawing_height_m + _PAGE_GAP_M
        furniture = {
            "site_context_inset": _rect(
                context_x_m * _SCALE,
                rail_y_m * _SCALE,
                _CONTEXT_WIDTH_M * _SCALE,
                context_height_m * _SCALE,
            ),
            "legend": _rect(
                legend_x_m * _SCALE,
                rail_y_m * _SCALE,
                _LEGEND_WIDTH_M * _SCALE,
                _LEGEND_HEIGHT_M * _SCALE,
            ),
            "area_schedule": _rect(
                schedule_x_m * _SCALE,
                rail_y_m * _SCALE,
                _SCHEDULE_WIDTH_M * _SCALE,
                _SCHEDULE_HEIGHT_M * _SCALE,
            ),
            "title_block": _rect(
                title_x_m * _SCALE,
                rail_y_m * _SCALE,
                _TITLE_WIDTH_M * _SCALE,
                _TITLE_HEIGHT_M * _SCALE,
            ),
        }
        page_width_m = max(page_width_m, title_x_m + _TITLE_WIDTH_M + _PANEL_MARGIN_M)
        context_bounds = {
            "x": context_x_m * _SCALE,
            "y": rail_y_m * _SCALE,
            "width": _CONTEXT_WIDTH_M * _SCALE,
            "height": context_height_m * _SCALE,
            "inner_padding": _PANEL_MARGIN_M * _SCALE,
            "scale": _ratio(context_inner_width_m * _SCALE, source_width_m),
        }
    else:
        raise ValueError(f"unsupported engineering sheet candidate: {candidate}")

    return page_width_m, page_height_m, furniture, context_bounds


def build_engineering_sheet_composition(
    *,
    candidate: str,
    geometry_bounds: dict[str, Decimal],
    primary_bounds: dict[str, Decimal],
) -> dict[str, Any]:
    """Resolve one finite composition candidate from existing bounds only."""
    if candidate not in ENGINEERING_SHEET_CANDIDATE_ORDER:
        raise ValueError(f"unsupported engineering sheet candidate: {candidate}")

    source_width_m = geometry_bounds["max_x_m"] - geometry_bounds["min_x_m"]
    source_height_m = geometry_bounds["max_y_m"] - geometry_bounds["min_y_m"]
    drawing_min_x = primary_bounds["min_x_m"] - _DRAWING_MARGIN_M
    drawing_min_y = primary_bounds["min_y_m"] - _DRAWING_MARGIN_M
    drawing_max_x = primary_bounds["max_x_m"] + _DRAWING_MARGIN_M
    drawing_max_y = primary_bounds["max_y_m"] + _DRAWING_MARGIN_M
    drawing_width_m = drawing_max_x - drawing_min_x
    drawing_height_m = drawing_max_y - drawing_min_y

    page_width_m, page_height_m, furniture, context_bounds = _candidate_rectangles(
        candidate=candidate,
        drawing_width_m=drawing_width_m,
        drawing_height_m=drawing_height_m,
        source_width_m=source_width_m,
        source_height_m=source_height_m,
    )
    page_min_x = drawing_min_x
    page_max_x = drawing_min_x + page_width_m
    page_max_y = drawing_max_y
    page_min_y = page_max_y - page_height_m

    drawing_width_px = drawing_width_m * _SCALE
    drawing_height_px = drawing_height_m * _SCALE
    page_width_px = page_width_m * _SCALE
    page_height_px = page_height_m * _SCALE
    primary_width_m = primary_bounds["max_x_m"] - primary_bounds["min_x_m"]
    primary_height_m = primary_bounds["max_y_m"] - primary_bounds["min_y_m"]
    main_occupancy = _ratio(
        drawing_width_px * drawing_height_px,
        page_width_px * page_height_px,
    )
    primary_occupancy = _ratio(
        primary_width_m * primary_height_m,
        drawing_width_m * drawing_height_m,
    )
    source_context_width_m = _ratio(
        Decimal(str(context_bounds["width"])) - (Decimal(str(context_bounds["inner_padding"])) * 2),
        Decimal(str(context_bounds["scale"])),
    )
    source_context_height_m = _ratio(
        Decimal(str(context_bounds["height"]))
        - (Decimal(str(context_bounds["inner_padding"])) * 2),
        Decimal(str(context_bounds["scale"])),
    )
    source_occupancy = _ratio(
        source_width_m * source_height_m,
        source_context_width_m * source_context_height_m,
    )
    furniture_values = tuple(furniture.values())
    overlaps = sum(
        _rectangles_overlap(left, right)
        for index, left in enumerate(furniture_values)
        for right in furniture_values[index + 1 :]
    )
    page_bounds = {
        "min_x_m": page_min_x,
        "min_y_m": page_min_y,
        "max_x_m": page_max_x,
        "max_y_m": page_max_y,
        "scale": _SCALE,
    }
    return {
        "profile": "ENGINEERING_SHEET",
        "candidate": candidate,
        "candidate_identity": ENGINEERING_SHEET_CANDIDATE_IDENTITY,
        "engineering_geometry_bounds": dict(geometry_bounds),
        "primary_plan_bounds": dict(primary_bounds),
        "engineering_drawing_bounds": {
            "min_x_m": drawing_min_x,
            "min_y_m": drawing_min_y,
            "max_x_m": drawing_max_x,
            "max_y_m": drawing_max_y,
            "scale": _SCALE,
        },
        "source_drawing_bounds": {
            "min_x_m": geometry_bounds["min_x_m"] - _DRAWING_MARGIN_M,
            "min_y_m": geometry_bounds["min_y_m"] - _DRAWING_MARGIN_M,
            "max_x_m": geometry_bounds["max_x_m"] + _DRAWING_MARGIN_M,
            "max_y_m": geometry_bounds["max_y_m"] + _DRAWING_MARGIN_M,
            "scale": _SCALE,
        },
        "context_inset": context_bounds,
        "page_layout_bounds": page_bounds,
        "engineering_drawing_rect": {
            "x": Decimal("0"),
            "y": Decimal("0"),
            "width": drawing_width_px,
            "height": drawing_height_px,
        },
        "page_size": {"width": page_width_px, "height": page_height_px},
        "furniture": furniture,
        "main_drawing_occupancy": main_occupancy,
        "source_geometry_occupancy": source_occupancy,
        "primary_plan_screen_occupancy": primary_occupancy,
        "primary_plan_width_ratio": _ratio(primary_width_m, drawing_width_m),
        "primary_plan_height_ratio": _ratio(primary_height_m, drawing_height_m),
        "primary_plan_occupancy_min": ENGINEERING_SHEET_PRIMARY_PLAN_MIN_OCCUPANCY,
        "primary_plan_width_ratio_min": ENGINEERING_SHEET_PRIMARY_PLAN_MIN_WIDTH_RATIO,
        "primary_plan_height_ratio_min": ENGINEERING_SHEET_PRIMARY_PLAN_MIN_HEIGHT_RATIO,
        "main_drawing_target_occupancy": ENGINEERING_SHEET_MAIN_DRAWING_TARGET_OCCUPANCY,
        "main_drawing_min_occupancy": ENGINEERING_SHEET_MAIN_DRAWING_MIN_OCCUPANCY,
        "main_drawing_max_occupancy": ENGINEERING_SHEET_MAIN_DRAWING_MAX_OCCUPANCY,
        "occupancy_target": ENGINEERING_SHEET_MAIN_DRAWING_TARGET_OCCUPANCY,
        "occupancy_min": ENGINEERING_SHEET_MAIN_DRAWING_MIN_OCCUPANCY,
        "occupancy_max": ENGINEERING_SHEET_MAIN_DRAWING_MAX_OCCUPANCY,
        "mobile_occupancy_min": Decimal("0.80"),
        "title_block_overlap": False,
        "area_table_overlap": False,
        "legend_overlap": False,
        "page_furniture_overlap": overlaps > 0,
        "page_furniture_overlap_count": overlaps,
        "review_overlays_visible": True,
    }


__all__ = [
    "ENGINEERING_SHEET_CANDIDATE_IDENTITY",
    "ENGINEERING_SHEET_CANDIDATE_ORDER",
    "ENGINEERING_SHEET_MAIN_DRAWING_MAX_OCCUPANCY",
    "ENGINEERING_SHEET_MAIN_DRAWING_MIN_OCCUPANCY",
    "ENGINEERING_SHEET_MAIN_DRAWING_TARGET_OCCUPANCY",
    "ENGINEERING_SHEET_PRIMARY_PLAN_MIN_HEIGHT_RATIO",
    "ENGINEERING_SHEET_PRIMARY_PLAN_MIN_OCCUPANCY",
    "ENGINEERING_SHEET_PRIMARY_PLAN_MIN_WIDTH_RATIO",
    "build_engineering_sheet_composition",
]
