"""Deterministic diagnostics for an already-resolved layout drawing.

Drawing lint is deliberately separate from SVG projection.  It consumes the
facts that the projection already resolved (page rectangles, visibility
flags, label metrics and geometry bounds) and reports presentation defects;
it never recalculates engineering geometry or repairs a drawing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Final, cast

from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
)

DRAWING_LINT_IDENTITY: Final = "drawing-lint@1.0.0"
DRAWING_LINT_SCHEMA_VERSION: Final = "1.0.0"
DRAWING_LINT_GATE_VALUES: Final[tuple[str, ...]] = ("PASS", "FAIL")
DRAWING_LINT_PROFILES: Final[tuple[str, ...]] = (
    "PRESENTATION",
    "MOBILE_PREVIEW",
    "ENGINEERING_SHEET",
    "ENGINEERING_REVIEW",
)
_SEVERITY_ORDER: Final[dict[str, int]] = {"ERROR": 0, "WARNING": 1, "INFO": 2}
_BUSINESS_PROFILES: Final[frozenset[str]] = frozenset(
    {"PRESENTATION", "MOBILE_PREVIEW", "ENGINEERING_SHEET"}
)
_METRIC_GROUPS: Final[tuple[str, ...]] = (
    "room_label_metrics",
    "callout_metrics",
    "area_schedule_metrics",
    "page_furniture_metrics",
)
_AREA_SCHEDULE_FIRST_ROW_BASELINE_PX: Final = Decimal("62")
_AREA_SCHEDULE_ROW_SPACING_PX: Final = Decimal("24")
_AREA_SCHEDULE_ROW_TEXT_HEIGHT_PX: Final = Decimal("10")
_AREA_SCHEDULE_ROW_COUNT: Final = 12


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _decimal(value: object, *, field_name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise _error("DRAWING_LINT_INPUT_INVALID", field=field_name)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise _error("DRAWING_LINT_INPUT_INVALID", field=field_name) from None
    if not number.is_finite():
        raise _error("DRAWING_LINT_INPUT_INVALID", field=field_name)
    return number


def _count(value: object, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise _error("DRAWING_LINT_INPUT_INVALID", field=field_name)
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and value.isdigit():
        result = int(value)
    else:
        raise _error("DRAWING_LINT_INPUT_INVALID", field=field_name)
    if result < 0:
        raise _error("DRAWING_LINT_INPUT_INVALID", field=field_name)
    return result


def _boolean(value: object, *, field_name: str) -> bool:
    if type(value) is not bool:
        raise _error("DRAWING_LINT_INPUT_INVALID", field=field_name)
    return value


def _mapping(value: object, *, field_name: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise _error("DRAWING_LINT_INPUT_INVALID", field=field_name)
    return value


def _metric_value(projection: Mapping[str, Any], name: str) -> object | None:
    if name in projection:
        return cast(object, projection[name])
    for group_name in _METRIC_GROUPS:
        group = projection.get(group_name)
        if isinstance(group, Mapping) and name in group:
            return cast(object, group[name])
    return None


def _count_metric(projection: Mapping[str, Any], name: str, *, fallback: int = 0) -> int:
    value = _metric_value(projection, name)
    if value is None:
        return fallback
    return _count(value, field_name=name)


def _bool_metric(projection: Mapping[str, Any], name: str, *, fallback: bool = False) -> bool:
    value = _metric_value(projection, name)
    if value is None:
        return fallback
    return _boolean(value, field_name=name)


def _stable_element_ids(projection: Mapping[str, Any], code: str) -> tuple[str, ...]:
    source = projection.get("drawing_lint_element_ids")
    if source is None:
        return ()
    if not isinstance(source, Mapping):
        raise _error("DRAWING_LINT_INPUT_INVALID", field="drawing_lint_element_ids")
    value = source.get(code, ())
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise _error("DRAWING_LINT_INPUT_INVALID", field=f"drawing_lint_element_ids.{code}")
    return tuple(sorted(set(value)))


def _rectangle(
    value: object, *, field_name: str
) -> tuple[Decimal, Decimal, Decimal, Decimal] | None:
    source = _mapping(value, field_name=field_name)
    if source is None:
        return None
    required = ("x", "y", "width", "height")
    if any(field not in source for field in required):
        raise _error("DRAWING_LINT_INPUT_INVALID", field=field_name)
    x = _decimal(source["x"], field_name=f"{field_name}.x")
    y = _decimal(source["y"], field_name=f"{field_name}.y")
    width = _decimal(source["width"], field_name=f"{field_name}.width")
    height = _decimal(source["height"], field_name=f"{field_name}.height")
    if width < 0 or height < 0:
        raise _error("DRAWING_LINT_INPUT_INVALID", field=field_name)
    return x, y, width, height


def _out_of_page(
    rectangle: tuple[Decimal, Decimal, Decimal, Decimal] | None,
    page_size: tuple[Decimal, Decimal] | None,
) -> bool:
    if rectangle is None or page_size is None:
        return False
    x, y, width, height = rectangle
    page_width, page_height = page_size
    return x < 0 or y < 0 or x + width > page_width or y + height > page_height


def _page_size(projection: Mapping[str, Any]) -> tuple[Decimal, Decimal] | None:
    source = _mapping(projection.get("page_size"), field_name="page_size")
    if source is None:
        return None
    if "width" not in source or "height" not in source:
        raise _error("DRAWING_LINT_INPUT_INVALID", field="page_size")
    width = _decimal(source["width"], field_name="page_size.width")
    height = _decimal(source["height"], field_name="page_size.height")
    if width < 0 or height < 0:
        raise _error("DRAWING_LINT_INPUT_INVALID", field="page_size")
    return width, height


def _bounds_out_of_page(projection: Mapping[str, Any]) -> int:
    primary = _mapping(projection.get("primary_plan_bounds"), field_name="primary_plan_bounds")
    page = _mapping(projection.get("page_layout_bounds"), field_name="page_layout_bounds")
    if primary is None or page is None:
        return 0
    required = ("min_x_m", "min_y_m", "max_x_m", "max_y_m")
    if any(field not in primary for field in required) or any(
        field not in page for field in required
    ):
        raise _error("DRAWING_LINT_INPUT_INVALID", field="primary_plan_bounds")
    return int(
        _decimal(primary["min_x_m"], field_name="primary_plan_bounds.min_x_m")
        < _decimal(page["min_x_m"], field_name="page_layout_bounds.min_x_m")
        or _decimal(primary["min_y_m"], field_name="primary_plan_bounds.min_y_m")
        < _decimal(page["min_y_m"], field_name="page_layout_bounds.min_y_m")
        or _decimal(primary["max_x_m"], field_name="primary_plan_bounds.max_x_m")
        > _decimal(page["max_x_m"], field_name="page_layout_bounds.max_x_m")
        or _decimal(primary["max_y_m"], field_name="primary_plan_bounds.max_y_m")
        > _decimal(page["max_y_m"], field_name="page_layout_bounds.max_y_m")
    )


def _furniture_out_of_page(projection: Mapping[str, Any]) -> int:
    page_size = _page_size(projection)
    furniture = _mapping(projection.get("page_furniture"), field_name="page_furniture")
    if furniture is None or page_size is None:
        return 0
    return sum(
        int(
            isinstance(item, Mapping)
            and item.get("visible", True) is not False
            and _out_of_page(
                _rectangle(item, field_name=f"page_furniture.{name}"),
                page_size,
            )
        )
        for name, item in furniture.items()
    )


def _issues_for_count(
    *,
    profile: str,
    code: str,
    count: int,
    message: str,
    severity: str = "ERROR",
    element_ids: tuple[str, ...] = (),
) -> DrawingLintIssueV1 | None:
    if count == 0:
        return None
    return DrawingLintIssueV1(
        severity=severity,
        code=code,
        profile=profile,
        element_ids=element_ids,
        message=message,
        metrics={"count": count},
    )


def _issues_for_bool(
    *,
    profile: str,
    code: str,
    value: bool,
    message: str,
    severity: str = "ERROR",
    element_ids: tuple[str, ...] = (),
) -> DrawingLintIssueV1 | None:
    if not value:
        return None
    return DrawingLintIssueV1(
        severity=severity,
        code=code,
        profile=profile,
        element_ids=element_ids,
        message=message,
        metrics={"value": True},
    )


@dataclass(frozen=True)
class DrawingLintIssueV1:
    """One stable, machine-readable drawing diagnostic."""

    severity: str
    code: str
    profile: str
    element_ids: tuple[str, ...] = ()
    message: str = ""
    metrics: Mapping[str, Any] = field(default_factory=dict)
    identity: str = DRAWING_LINT_IDENTITY

    def __post_init__(self) -> None:
        if self.identity != DRAWING_LINT_IDENTITY:
            raise _error("DRAWING_LINT_INPUT_INVALID", field="issue.identity")
        if self.severity not in _SEVERITY_ORDER or not self.code or not self.profile:
            raise _error("DRAWING_LINT_INPUT_INVALID", field="issue")
        if not isinstance(self.element_ids, tuple) or any(
            not isinstance(value, str) for value in self.element_ids
        ):
            raise _error("DRAWING_LINT_INPUT_INVALID", field="issue.element_ids")
        if not isinstance(self.metrics, Mapping):
            raise _error("DRAWING_LINT_INPUT_INVALID", field="issue.metrics")
        object.__setattr__(self, "element_ids", tuple(sorted(set(self.element_ids))))
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))

    @property
    def sort_key(self) -> tuple[object, ...]:
        return (
            self.profile,
            _SEVERITY_ORDER[self.severity],
            self.code,
            self.element_ids,
            self.message,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "severity": self.severity,
            "code": self.code,
            "profile": self.profile,
            "element_ids": list(self.element_ids),
            "message": self.message,
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True)
class DrawingLintReportV1:
    """Immutable report whose hash covers the sorted diagnostics and metrics."""

    identity: str
    schema_version: str
    profile: str
    drawing_lint_gate: str
    error_count: int
    warning_count: int
    info_count: int
    metrics: Mapping[str, Any]
    issues: tuple[DrawingLintIssueV1, ...]
    _content_hash: str

    @classmethod
    def from_parts(
        cls,
        *,
        profile: str,
        metrics: Mapping[str, Any],
        issues: Sequence[DrawingLintIssueV1],
    ) -> DrawingLintReportV1:
        ordered = tuple(sorted(issues, key=lambda issue: issue.sort_key))
        metric_copy = dict(metrics)
        error_count = sum(issue.severity == "ERROR" for issue in ordered)
        warning_count = sum(issue.severity == "WARNING" for issue in ordered)
        info_count = sum(issue.severity == "INFO" for issue in ordered)
        gate = "FAIL" if error_count else "PASS"
        content = {
            "identity": DRAWING_LINT_IDENTITY,
            "schema_version": DRAWING_LINT_SCHEMA_VERSION,
            "profile": profile,
            "drawing_lint_gate": gate,
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "metrics": metric_copy,
            "issues": [issue.to_dict() for issue in ordered],
            "same_input_same_lint_report": True,
            "same_input_same_lint_hash": True,
        }
        return cls(
            identity=DRAWING_LINT_IDENTITY,
            schema_version=DRAWING_LINT_SCHEMA_VERSION,
            profile=profile,
            drawing_lint_gate=gate,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            metrics=MappingProxyType(metric_copy),
            issues=ordered,
            _content_hash=canonical_hash(content),
        )

    @property
    def canonical_lint_hash(self) -> str:
        return self._content_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "schema_version": self.schema_version,
            "profile": self.profile,
            "drawing_lint_gate": self.drawing_lint_gate,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "metrics": dict(self.metrics),
            "issues": [issue.to_dict() for issue in self.issues],
            "same_input_same_lint_report": True,
            "same_input_same_lint_hash": True,
            "canonical_lint_hash": self._content_hash,
        }


def _leakage_severity(profile: str) -> str | None:
    if profile in {"PRESENTATION", "MOBILE_PREVIEW"}:
        return "ERROR"
    if profile == "ENGINEERING_SHEET":
        # The current renderer historically exposes review metadata on the
        # engineering sheet. P1D reports that as a warning without changing
        # the SVG or silently treating it as a clean business view.
        return "WARNING"
    return None


def lint_drawing_projection(
    projection: Mapping[str, Any], *, profile: str | None = None
) -> DrawingLintReportV1:
    """Lint one existing projection payload without rendering or repairing it."""

    if not isinstance(projection, Mapping):
        raise _error("DRAWING_LINT_INPUT_INVALID", field="projection")
    resolved_profile = profile or projection.get("page_profile")
    if resolved_profile not in DRAWING_LINT_PROFILES:
        raise _error("DRAWING_LINT_PROFILE_INVALID", profile=str(resolved_profile))
    resolved_profile = str(resolved_profile)

    room_label_wall = _count_metric(projection, "ROOM_LABEL_WALL_CROSSING_COUNT")
    room_label_overlap = _count_metric(
        projection,
        "ROOM_LABEL_LABEL_OVERLAP_COUNT",
        fallback=_count_metric(projection, "ROOM_LABEL_PRIMARY_COLLISION_COUNT"),
    )
    room_dimension_collision = _count_metric(projection, "ROOM_LABEL_DIMENSION_COLLISION_COUNT")
    room_portal_collision = _count_metric(projection, "ROOM_LABEL_PORTAL_COLLISION_COUNT")
    callout_label_collision = _count_metric(projection, "CALLOUT_LABEL_COLLISION_COUNT")
    callout_self_intersection = _count_metric(projection, "CALLOUT_LEADER_SELF_INTERSECTION_COUNT")
    callout_label_intersection = _count_metric(
        projection, "CALLOUT_LEADER_LABEL_INTERSECTION_COUNT"
    )
    callout_out_of_page = _count_metric(projection, "CALLOUT_OUT_OF_PAGE_COUNT")

    schedule_header_overlap = _bool_metric(projection, "AREA_SCHEDULE_HEADER_FIRST_ROW_OVERLAP")
    schedule_row_overlap = _count_metric(projection, "AREA_SCHEDULE_ROW_OVERLAP_COUNT")
    schedule_content_clip = _area_schedule_content_clip_count(projection)
    schedule_out_of_page = _count_metric(
        projection,
        "AREA_SCHEDULE_OUT_OF_PAGE_COUNT",
        fallback=_furniture_out_of_page_for_name(projection, "area_schedule"),
    )
    title_overlap = _bool_metric(projection, "TITLE_BLOCK_OVERLAP")
    legend_overlap = _bool_metric(projection, "LEGEND_OVERLAP")
    area_table_overlap = _bool_metric(projection, "AREA_TABLE_OVERLAP")
    furniture_overlap = _count_metric(
        projection,
        "PAGE_FURNITURE_OVERLAP_COUNT",
        fallback=int(_bool_metric(projection, "page_furniture_overlap")),
    )
    furniture_out_of_page = _count_metric(
        projection,
        "PAGE_FURNITURE_OUT_OF_PAGE_COUNT",
        fallback=_furniture_out_of_page(projection),
    )

    primary_out_of_page = _count_metric(
        projection,
        "PRIMARY_PLAN_OUT_OF_PAGE_COUNT",
        fallback=_bounds_out_of_page(projection),
    )
    visible_dimension_out_of_page = _count_metric(projection, "VISIBLE_DIMENSION_OUT_OF_PAGE_COUNT")
    room_label_out_of_page = _count_metric(projection, "ROOM_LABEL_OUT_OF_PAGE_COUNT")

    internal_code_visible = _bool_metric(projection, "internal_zone_code_visible")
    source_hash_visible = _bool_metric(projection, "source_hash_visible")
    portal_debug_visible = _bool_metric(projection, "portal_debug_text_visible")
    schema_identity_visible = _bool_metric(projection, "schema_identity_visible")

    metrics: dict[str, Any] = {
        "ROOM_LABEL_WALL_CROSSING_COUNT": room_label_wall,
        "ROOM_LABEL_LABEL_OVERLAP_COUNT": room_label_overlap,
        "ROOM_LABEL_DIMENSION_COLLISION_COUNT": room_dimension_collision,
        "ROOM_LABEL_PORTAL_COLLISION_COUNT": room_portal_collision,
        "CALLOUT_LABEL_COLLISION_COUNT": callout_label_collision,
        "CALLOUT_LEADER_SELF_INTERSECTION_COUNT": callout_self_intersection,
        "CALLOUT_LEADER_LABEL_INTERSECTION_COUNT": callout_label_intersection,
        "CALLOUT_OUT_OF_PAGE_COUNT": callout_out_of_page,
        "AREA_SCHEDULE_HEADER_FIRST_ROW_OVERLAP": schedule_header_overlap,
        "AREA_SCHEDULE_ROW_OVERLAP_COUNT": schedule_row_overlap,
        "AREA_SCHEDULE_CONTENT_CLIP_COUNT": schedule_content_clip,
        "AREA_SCHEDULE_OUT_OF_PAGE_COUNT": schedule_out_of_page,
        "TITLE_BLOCK_OVERLAP": title_overlap,
        "LEGEND_OVERLAP": legend_overlap,
        "AREA_TABLE_OVERLAP": area_table_overlap,
        "PAGE_FURNITURE_OVERLAP_COUNT": furniture_overlap,
        "PAGE_FURNITURE_OUT_OF_PAGE_COUNT": furniture_out_of_page,
        "INTERNAL_ZONE_CODE_VISIBLE": internal_code_visible,
        "SOURCE_HASH_VISIBLE": source_hash_visible,
        "PORTAL_DEBUG_TEXT_VISIBLE": portal_debug_visible,
        "SCHEMA_IDENTITY_VISIBLE": schema_identity_visible,
        "PRIMARY_PLAN_OUT_OF_PAGE_COUNT": primary_out_of_page,
        "VISIBLE_DIMENSION_OUT_OF_PAGE_COUNT": visible_dimension_out_of_page,
        "ROOM_LABEL_OUT_OF_PAGE_COUNT": room_label_out_of_page,
    }

    issues: list[DrawingLintIssueV1] = []
    count_messages = {
        "ROOM_LABEL_WALL_CROSSING_COUNT": "Room label crosses its room wall.",
        "ROOM_LABEL_LABEL_OVERLAP_COUNT": "Room labels overlap.",
        "ROOM_LABEL_DIMENSION_COLLISION_COUNT": "Room label collides with a dimension.",
        "ROOM_LABEL_PORTAL_COLLISION_COUNT": "Room label collides with a portal.",
        "CALLOUT_LABEL_COLLISION_COUNT": "Callout label collides with another drawing element.",
        "CALLOUT_LEADER_SELF_INTERSECTION_COUNT": "Callout leader self-intersects.",
        "CALLOUT_LEADER_LABEL_INTERSECTION_COUNT": "Callout leader intersects its label.",
        "CALLOUT_OUT_OF_PAGE_COUNT": "Callout is outside the page.",
        "AREA_SCHEDULE_ROW_OVERLAP_COUNT": "Area schedule rows overlap.",
        "AREA_SCHEDULE_CONTENT_CLIP_COUNT": "Area schedule content is clipped.",
        "AREA_SCHEDULE_OUT_OF_PAGE_COUNT": "Area schedule is outside the page.",
        "PAGE_FURNITURE_OVERLAP_COUNT": "Page furniture overlaps.",
        "PAGE_FURNITURE_OUT_OF_PAGE_COUNT": "Page furniture is outside the page.",
        "PRIMARY_PLAN_OUT_OF_PAGE_COUNT": "Primary plan is outside the page.",
        "VISIBLE_DIMENSION_OUT_OF_PAGE_COUNT": "A visible dimension is outside the page.",
        "ROOM_LABEL_OUT_OF_PAGE_COUNT": "A room label is outside the page.",
    }
    for code in (
        "ROOM_LABEL_WALL_CROSSING_COUNT",
        "ROOM_LABEL_LABEL_OVERLAP_COUNT",
        "ROOM_LABEL_DIMENSION_COLLISION_COUNT",
        "ROOM_LABEL_PORTAL_COLLISION_COUNT",
        "CALLOUT_LABEL_COLLISION_COUNT",
        "CALLOUT_LEADER_SELF_INTERSECTION_COUNT",
        "CALLOUT_LEADER_LABEL_INTERSECTION_COUNT",
        "CALLOUT_OUT_OF_PAGE_COUNT",
        "AREA_SCHEDULE_ROW_OVERLAP_COUNT",
        "AREA_SCHEDULE_CONTENT_CLIP_COUNT",
        "AREA_SCHEDULE_OUT_OF_PAGE_COUNT",
        "PAGE_FURNITURE_OVERLAP_COUNT",
        "PAGE_FURNITURE_OUT_OF_PAGE_COUNT",
        "PRIMARY_PLAN_OUT_OF_PAGE_COUNT",
        "VISIBLE_DIMENSION_OUT_OF_PAGE_COUNT",
        "ROOM_LABEL_OUT_OF_PAGE_COUNT",
    ):
        issue = _issues_for_count(
            profile=resolved_profile,
            code=code,
            count=metrics[code],
            message=count_messages[code],
            element_ids=_stable_element_ids(projection, code),
        )
        if issue is not None:
            issues.append(issue)

    for code, value, message in (
        (
            "AREA_SCHEDULE_HEADER_FIRST_ROW_OVERLAP",
            schedule_header_overlap,
            "Area schedule header overlaps its first row.",
        ),
        ("TITLE_BLOCK_OVERLAP", title_overlap, "Title block overlaps another page element."),
        ("LEGEND_OVERLAP", legend_overlap, "Legend overlaps another page element."),
        ("AREA_TABLE_OVERLAP", area_table_overlap, "Area schedule overlaps another page element."),
    ):
        issue = _issues_for_bool(
            profile=resolved_profile,
            code=code,
            value=value,
            message=message,
            element_ids=_stable_element_ids(projection, code),
        )
        if issue is not None:
            issues.append(issue)

    leakage_severity = _leakage_severity(resolved_profile)
    if leakage_severity is not None:
        for code, value, message in (
            (
                "INTERNAL_ZONE_CODE_VISIBLE",
                internal_code_visible,
                "Internal zone code is visible in a business drawing profile.",
            ),
            (
                "SOURCE_HASH_VISIBLE",
                source_hash_visible,
                "Source hash is visible in a business drawing profile.",
            ),
            (
                "PORTAL_DEBUG_TEXT_VISIBLE",
                portal_debug_visible,
                "Portal debug text is visible in a business drawing profile.",
            ),
            (
                "SCHEMA_IDENTITY_VISIBLE",
                schema_identity_visible,
                "Schema identity is visible in a business drawing profile.",
            ),
        ):
            issue = _issues_for_bool(
                profile=resolved_profile,
                code=code,
                value=value,
                message=message,
                severity=leakage_severity,
                element_ids=_stable_element_ids(projection, code),
            )
            if issue is not None:
                issues.append(issue)

    occupancy_warning = False
    if resolved_profile == "ENGINEERING_SHEET":
        occupancy = projection.get("primary_plan_screen_occupancy")
        threshold = projection.get("primary_plan_occupancy_min", "0.65")
        if occupancy is not None:
            occupancy_warning = _decimal(
                occupancy, field_name="primary_plan_screen_occupancy"
            ) < _decimal(threshold, field_name="primary_plan_occupancy_min")
    metrics["ENGINEERING_SHEET_PRIMARY_PLAN_OCCUPANCY_WARNING"] = occupancy_warning
    warning = _issues_for_bool(
        profile=resolved_profile,
        code="ENGINEERING_SHEET_PRIMARY_PLAN_OCCUPANCY_WARNING",
        value=occupancy_warning,
        message="Engineering sheet primary plan occupancy is below its advisory threshold.",
        severity="WARNING",
    )
    if warning is not None:
        issues.append(warning)

    return DrawingLintReportV1.from_parts(
        profile=resolved_profile,
        metrics=metrics,
        issues=issues,
    )


def _furniture_out_of_page_for_name(projection: Mapping[str, Any], name: str) -> int:
    page_size = _page_size(projection)
    furniture = _mapping(projection.get("page_furniture"), field_name="page_furniture")
    if page_size is None or furniture is None:
        return 0
    item = furniture.get(name)
    if item is None or (isinstance(item, Mapping) and item.get("visible", True) is False):
        return 0
    return int(_out_of_page(_rectangle(item, field_name=f"page_furniture.{name}"), page_size))


def _area_schedule_content_clip_count(projection: Mapping[str, Any]) -> int:
    """Check the resolved schedule box against its fixed rendered row envelope.

    The offsets mirror the existing renderer's resolved schedule composition;
    they are a drawing fact check, not a second layout calculation. A caller
    may provide an explicit content count when it has richer text-box facts.
    """
    explicit = _metric_value(projection, "AREA_SCHEDULE_CONTENT_CLIP_COUNT")
    if explicit is not None:
        return _count(explicit, field_name="AREA_SCHEDULE_CONTENT_CLIP_COUNT")
    furniture = _mapping(projection.get("page_furniture"), field_name="page_furniture")
    if furniture is None:
        return 0
    schedule = furniture.get("area_schedule")
    if not isinstance(schedule, Mapping) or schedule.get("visible", True) is False:
        return 0
    height = _decimal(schedule.get("height"), field_name="page_furniture.area_schedule.height")
    last_row_baseline = _AREA_SCHEDULE_FIRST_ROW_BASELINE_PX + (
        Decimal(_AREA_SCHEDULE_ROW_COUNT - 1) * _AREA_SCHEDULE_ROW_SPACING_PX
    )
    required_height = last_row_baseline + (_AREA_SCHEDULE_ROW_TEXT_HEIGHT_PX / Decimal("2"))
    return int(height < required_height)


__all__ = [
    "DRAWING_LINT_IDENTITY",
    "DRAWING_LINT_GATE_VALUES",
    "DRAWING_LINT_PROFILES",
    "DrawingLintIssueV1",
    "DrawingLintReportV1",
    "lint_drawing_projection",
]
