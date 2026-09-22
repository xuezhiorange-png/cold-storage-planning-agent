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
DRAWING_LINT_EVIDENCE_STATUSES: Final[tuple[str, ...]] = (
    "MEASURED",
    "DERIVED",
    "NOT_APPLICABLE",
    "UNAVAILABLE",
)
MISSING_FACT_IS_ZERO: Final[bool] = False
MISSING_FACT_IS_FALSE: Final[bool] = False
MISSING_REQUIRED_FACT_FAILS_CLOSED: Final[bool] = True
EVIDENCE_STATUS_HASHED: Final[bool] = True
EVIDENCE_SOURCE_HASHED: Final[bool] = True
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
_BASE_REQUIRED_FACTS: Final[tuple[str, ...]] = (
    "ROOM_LABEL_CALLOUT_COUNT",
    "ROOM_LABEL_WALL_CROSSING_COUNT",
    "ROOM_LABEL_LABEL_OVERLAP_COUNT",
    "ROOM_LABEL_DIMENSION_COLLISION_COUNT",
    "ROOM_LABEL_PORTAL_COLLISION_COUNT",
    "AREA_SCHEDULE_HEADER_FIRST_ROW_OVERLAP",
    "AREA_SCHEDULE_ROW_OVERLAP_COUNT",
    "AREA_SCHEDULE_CONTENT_CLIP_COUNT",
    "AREA_SCHEDULE_OUT_OF_PAGE_COUNT",
    "TITLE_BLOCK_OVERLAP",
    "LEGEND_OVERLAP",
    "AREA_TABLE_OVERLAP",
    "PAGE_FURNITURE_OVERLAP_COUNT",
    "PAGE_FURNITURE_OUT_OF_PAGE_COUNT",
    "INTERNAL_ZONE_CODE_VISIBLE",
    "SOURCE_HASH_VISIBLE",
    "PORTAL_DEBUG_TEXT_VISIBLE",
    "SCHEMA_IDENTITY_VISIBLE",
    "PRIMARY_PLAN_OUT_OF_PAGE_COUNT",
    "VISIBLE_DIMENSION_OUT_OF_PAGE_COUNT",
    "ROOM_LABEL_OUT_OF_PAGE_COUNT",
)
_CALLOUT_REQUIRED_FACTS: Final[tuple[str, ...]] = (
    "CALLOUT_LABEL_COLLISION_COUNT",
    "CALLOUT_LEADER_SELF_INTERSECTION_COUNT",
    "CALLOUT_LEADER_LABEL_INTERSECTION_COUNT",
    "CALLOUT_OUT_OF_PAGE_COUNT",
)
_PROJECTION_FIELD_ALIASES: Final[dict[str, str]] = {
    "TITLE_BLOCK_OVERLAP": "title_block_overlap",
    "LEGEND_OVERLAP": "legend_overlap",
    "AREA_TABLE_OVERLAP": "area_table_overlap",
    "INTERNAL_ZONE_CODE_VISIBLE": "internal_zone_code_visible",
    "SOURCE_HASH_VISIBLE": "source_hash_visible",
    "PORTAL_DEBUG_TEXT_VISIBLE": "portal_debug_text_visible",
    "SCHEMA_IDENTITY_VISIBLE": "schema_identity_visible",
}


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


def _drawing_lint_facts(projection: Mapping[str, Any]) -> Mapping[str, Any] | None:
    facts = projection.get("drawing_lint_facts")
    if facts is None:
        return None
    return _mapping(facts, field_name="drawing_lint_facts")


def _metric_value_with_source(
    projection: Mapping[str, Any], name: str
) -> tuple[bool, object | None, str]:
    if name in projection:
        return True, cast(object, projection[name]), f"projection.{name}"
    alias = _PROJECTION_FIELD_ALIASES.get(name)
    if alias is not None and alias in projection:
        return True, cast(object, projection[alias]), f"projection.{alias}"
    facts = _drawing_lint_facts(projection)
    if facts is not None:
        fact_metrics = facts.get("metrics")
        if isinstance(fact_metrics, Mapping) and name in fact_metrics:
            return True, cast(object, fact_metrics[name]), f"drawing_lint_facts.metrics.{name}"
    for group_name in _METRIC_GROUPS:
        group = projection.get(group_name)
        if isinstance(group, Mapping) and name in group:
            return True, cast(object, group[name]), f"{group_name}.{name}"
    return False, None, "insufficient_drawing_facts"


def _metric_value(projection: Mapping[str, Any], name: str) -> object | None:
    present, value, _ = _metric_value_with_source(projection, name)
    return value if present else None


def _read_bool_metric(projection: Mapping[str, Any], name: str) -> bool | None:
    present, value, _ = _metric_value_with_source(projection, name)
    return _boolean(value, field_name=name) if present else None


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


def _bounds_out_of_page(projection: Mapping[str, Any]) -> int | None:
    primary = _mapping(projection.get("primary_plan_bounds"), field_name="primary_plan_bounds")
    page = _mapping(projection.get("page_layout_bounds"), field_name="page_layout_bounds")
    if primary is None or page is None:
        return None
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


def _furniture_out_of_page(projection: Mapping[str, Any]) -> int | None:
    page_size = _page_size(projection)
    furniture = _mapping(projection.get("page_furniture"), field_name="page_furniture")
    if furniture is None or page_size is None:
        return None
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
class DrawingLintMetricEvidenceV1:
    """Evidence state for one lint metric.

    ``UNAVAILABLE`` is intentionally distinct from a measured/derived zero.
    A missing fact must never be silently converted into a clean result.
    """

    status: str
    value: Any
    source: str

    def __post_init__(self) -> None:
        if self.status not in DRAWING_LINT_EVIDENCE_STATUSES or not self.source:
            raise _error("DRAWING_LINT_INPUT_INVALID", field="metric_evidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "value": self.value,
            "source": self.source,
        }


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
    metric_evidence: Mapping[str, DrawingLintMetricEvidenceV1]
    required_fact_count: int
    measured_fact_count: int
    derived_fact_count: int
    not_applicable_fact_count: int
    unavailable_required_fact_count: int
    issues: tuple[DrawingLintIssueV1, ...]
    _content_hash: str

    @classmethod
    def from_parts(
        cls,
        *,
        profile: str,
        metrics: Mapping[str, Any],
        metric_evidence: Mapping[str, DrawingLintMetricEvidenceV1],
        required_fact_names: Sequence[str],
        issues: Sequence[DrawingLintIssueV1],
    ) -> DrawingLintReportV1:
        ordered = tuple(sorted(issues, key=lambda issue: issue.sort_key))
        metric_copy = dict(metrics)
        evidence_copy = {name: metric_evidence[name] for name in sorted(metric_evidence)}
        required_names = tuple(sorted(set(required_fact_names)))
        error_count = sum(issue.severity == "ERROR" for issue in ordered)
        warning_count = sum(issue.severity == "WARNING" for issue in ordered)
        info_count = sum(issue.severity == "INFO" for issue in ordered)
        gate = "FAIL" if error_count else "PASS"
        measured_count = sum(evidence.status == "MEASURED" for evidence in evidence_copy.values())
        derived_count = sum(evidence.status == "DERIVED" for evidence in evidence_copy.values())
        not_applicable_count = sum(
            evidence.status == "NOT_APPLICABLE" for evidence in evidence_copy.values()
        )
        unavailable_required_count = sum(
            evidence_copy[name].status == "UNAVAILABLE"
            for name in required_names
            if name in evidence_copy
        )
        content = {
            "identity": DRAWING_LINT_IDENTITY,
            "schema_version": DRAWING_LINT_SCHEMA_VERSION,
            "profile": profile,
            "drawing_lint_gate": gate,
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "metrics": metric_copy,
            "metric_evidence": {
                name: evidence.to_dict() for name, evidence in evidence_copy.items()
            },
            "required_fact_count": len(required_names),
            "measured_fact_count": measured_count,
            "derived_fact_count": derived_count,
            "not_applicable_fact_count": not_applicable_count,
            "unavailable_required_fact_count": unavailable_required_count,
            "evidence_status_hashed": EVIDENCE_STATUS_HASHED,
            "evidence_source_hashed": EVIDENCE_SOURCE_HASHED,
            "same_input_same_evidence_status": True,
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
            metric_evidence=MappingProxyType(evidence_copy),
            required_fact_count=len(required_names),
            measured_fact_count=measured_count,
            derived_fact_count=derived_count,
            not_applicable_fact_count=not_applicable_count,
            unavailable_required_fact_count=unavailable_required_count,
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
            "metric_evidence": {
                name: evidence.to_dict() for name, evidence in sorted(self.metric_evidence.items())
            },
            "required_fact_count": self.required_fact_count,
            "measured_fact_count": self.measured_fact_count,
            "derived_fact_count": self.derived_fact_count,
            "not_applicable_fact_count": self.not_applicable_fact_count,
            "unavailable_required_fact_count": self.unavailable_required_fact_count,
            "evidence_status_hashed": EVIDENCE_STATUS_HASHED,
            "evidence_source_hashed": EVIDENCE_SOURCE_HASHED,
            "same_input_same_evidence_status": True,
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


def _fact_rectangles(
    projection: Mapping[str, Any], name: str
) -> tuple[tuple[str, tuple[Decimal, Decimal, Decimal, Decimal]], ...] | None:
    facts = _drawing_lint_facts(projection)
    if facts is None or name not in facts:
        return None
    raw = facts[name]
    if not isinstance(raw, (list, tuple)):
        raise _error("DRAWING_LINT_INPUT_INVALID", field=f"drawing_lint_facts.{name}")
    result: list[tuple[str, tuple[Decimal, Decimal, Decimal, Decimal]]] = []
    for index, item in enumerate(raw):
        source = _mapping(item, field_name=f"drawing_lint_facts.{name}[{index}]")
        if source is None:
            raise _error("DRAWING_LINT_INPUT_INVALID", field=f"drawing_lint_facts.{name}")
        identity = source.get("element_id", f"{name}-{index}")
        if not isinstance(identity, str):
            raise _error("DRAWING_LINT_INPUT_INVALID", field=f"drawing_lint_facts.{name}")
        box_value = source.get("box", source)
        box = _rectangle(box_value, field_name=f"drawing_lint_facts.{name}[{index}]")
        if box is None:
            raise _error("DRAWING_LINT_INPUT_INVALID", field=f"drawing_lint_facts.{name}")
        result.append((identity, box))
    return tuple(result)


def _rectangles_overlap(
    left: tuple[Decimal, Decimal, Decimal, Decimal],
    right: tuple[Decimal, Decimal, Decimal, Decimal],
) -> bool:
    left_x, left_y, left_width, left_height = left
    right_x, right_y, right_width, right_height = right
    return max(left_x, right_x) < min(left_x + left_width, right_x + right_width) and max(
        left_y, right_y
    ) < min(left_y + left_height, right_y + right_height)


def _point(value: object, *, field_name: str) -> tuple[Decimal, Decimal]:
    source = _mapping(value, field_name=field_name)
    if source is None:
        raise _error("DRAWING_LINT_INPUT_INVALID", field=field_name)
    if "x" not in source or "y" not in source:
        raise _error("DRAWING_LINT_INPUT_INVALID", field=field_name)
    return (
        _decimal(source["x"], field_name=f"{field_name}.x"),
        _decimal(source["y"], field_name=f"{field_name}.y"),
    )


def _callout_leaders(
    projection: Mapping[str, Any],
) -> tuple[dict[str, Any], ...] | None:
    facts = _drawing_lint_facts(projection)
    if facts is None or "callout_leaders" not in facts:
        return None
    raw = facts["callout_leaders"]
    if not isinstance(raw, (list, tuple)):
        raise _error("DRAWING_LINT_INPUT_INVALID", field="drawing_lint_facts.callout_leaders")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        source = _mapping(item, field_name=f"drawing_lint_facts.callout_leaders[{index}]")
        if source is None:
            raise _error("DRAWING_LINT_INPUT_INVALID", field="drawing_lint_facts.callout_leaders")
        identity = source.get("element_id", f"callout-{index}")
        if not isinstance(identity, str):
            raise _error("DRAWING_LINT_INPUT_INVALID", field="drawing_lint_facts.callout_leaders")
        raw_points = source.get("points")
        if not isinstance(raw_points, (list, tuple)) or len(raw_points) < 2:
            raise _error("DRAWING_LINT_INPUT_INVALID", field="drawing_lint_facts.callout_leaders")
        points = tuple(
            _point(point, field_name=f"drawing_lint_facts.callout_leaders[{index}].points")
            for point in raw_points
        )
        label_box = _rectangle(
            source.get("label_box"),
            field_name=f"drawing_lint_facts.callout_leaders[{index}].label_box",
        )
        if label_box is None:
            raise _error("DRAWING_LINT_INPUT_INVALID", field="drawing_lint_facts.callout_leaders")
        result.append(
            {
                "element_id": identity,
                "label_element_id": source.get("label_element_id"),
                "points": points,
                "label_box": label_box,
            }
        )
    return tuple(result)


def _segment_intersects_rectangle_interior(
    start: tuple[Decimal, Decimal],
    end: tuple[Decimal, Decimal],
    rectangle: tuple[Decimal, Decimal, Decimal, Decimal],
) -> bool:
    """Check positive-length interior intersection for the resolved orthogonal leader."""
    x1, y1 = start
    x2, y2 = end
    x, y, width, height = rectangle
    right = x + width
    bottom = y + height
    if x1 == x2 and x < x1 < right:
        return max(min(y1, y2), y) < min(max(y1, y2), bottom)
    if y1 == y2 and y < y1 < bottom:
        return max(min(x1, x2), x) < min(max(x1, x2), right)
    return False


def _segments_intersect(
    first_start: tuple[Decimal, Decimal],
    first_end: tuple[Decimal, Decimal],
    second_start: tuple[Decimal, Decimal],
    second_end: tuple[Decimal, Decimal],
) -> bool:
    def orientation(
        a: tuple[Decimal, Decimal],
        b: tuple[Decimal, Decimal],
        c: tuple[Decimal, Decimal],
    ) -> Decimal:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def on_segment(
        a: tuple[Decimal, Decimal],
        b: tuple[Decimal, Decimal],
        c: tuple[Decimal, Decimal],
    ) -> bool:
        return min(a[0], c[0]) <= b[0] <= max(a[0], c[0]) and min(a[1], c[1]) <= b[1] <= max(
            a[1], c[1]
        )

    first = orientation(first_start, first_end, second_start)
    second = orientation(first_start, first_end, second_end)
    third = orientation(second_start, second_end, first_start)
    fourth = orientation(second_start, second_end, first_end)
    if first == 0 and on_segment(first_start, second_start, first_end):
        return True
    if second == 0 and on_segment(first_start, second_end, first_end):
        return True
    if third == 0 and on_segment(second_start, first_start, second_end):
        return True
    if fourth == 0 and on_segment(second_start, first_end, second_end):
        return True
    return (first > 0) != (second > 0) and (third > 0) != (fourth > 0)


def _page_point_out_of_page(
    point: tuple[Decimal, Decimal], page_size: tuple[Decimal, Decimal]
) -> bool:
    x, y = point
    width, height = page_size
    return x < 0 or y < 0 or x > width or y > height


def _derived_label_out_of_page_count(projection: Mapping[str, Any]) -> int | None:
    boxes = _fact_rectangles(projection, "label_boxes")
    page_size = _page_size(projection)
    if boxes is None or page_size is None:
        return None
    return sum(_out_of_page(box, page_size) for _, box in boxes)


def _derived_dimension_out_of_page_count(projection: Mapping[str, Any]) -> int | None:
    boxes = _fact_rectangles(projection, "dimension_boxes")
    page_size = _page_size(projection)
    if boxes is None or page_size is None:
        return None
    return sum(_out_of_page(box, page_size) for _, box in boxes)


def _derived_furniture_overlap_count(projection: Mapping[str, Any]) -> int | None:
    furniture = _mapping(projection.get("page_furniture"), field_name="page_furniture")
    if furniture is None:
        return None
    boxes: list[tuple[str, tuple[Decimal, Decimal, Decimal, Decimal]]] = []
    for name, item in furniture.items():
        if not isinstance(name, str) or not isinstance(item, Mapping):
            raise _error("DRAWING_LINT_INPUT_INVALID", field="page_furniture")
        if item.get("visible", True) is False:
            continue
        box = _rectangle(item, field_name=f"page_furniture.{name}")
        if box is not None:
            boxes.append((name, box))
    return sum(
        _rectangles_overlap(left, right)
        for index, (_, left) in enumerate(boxes)
        for _, right in boxes[index + 1 :]
    )


def _derived_callout_metrics(
    projection: Mapping[str, Any],
    *,
    callout_count: int,
) -> dict[str, DrawingLintMetricEvidenceV1]:
    explicit: dict[str, DrawingLintMetricEvidenceV1] = {}
    for name in _CALLOUT_REQUIRED_FACTS:
        present, value, source = _metric_value_with_source(projection, name)
        if present:
            explicit[name] = DrawingLintMetricEvidenceV1(
                status="MEASURED",
                value=_count(value, field_name=name),
                source=source,
            )
    if callout_count == 0:
        return {
            name: explicit.get(
                name,
                DrawingLintMetricEvidenceV1(
                    status="NOT_APPLICABLE",
                    value=0,
                    source="profile.no_callouts",
                ),
            )
            for name in _CALLOUT_REQUIRED_FACTS
        }
    leaders = _callout_leaders(projection)
    labels = _fact_rectangles(projection, "label_boxes")
    page_size = _page_size(projection)
    if leaders is None or labels is None or page_size is None or len(leaders) != callout_count:
        return {
            name: DrawingLintMetricEvidenceV1(
                status="UNAVAILABLE",
                value=None,
                source="callout_count+callout_leaders+label_boxes+page_size",
            )
            for name in _CALLOUT_REQUIRED_FACTS
        }
    label_by_id = dict(labels)
    label_collision_count = 0
    leader_label_intersection_count = 0
    self_intersection_count = 0
    out_of_page_count = 0
    for entry in leaders:
        box = entry["label_box"]
        own_label_id = entry.get("label_element_id")
        if any(
            other_id != own_label_id and _rectangles_overlap(box, other_box)
            for other_id, other_box in label_by_id.items()
        ):
            label_collision_count += 1
        points = entry["points"]
        for first_index in range(len(points) - 1):
            for second_index in range(first_index + 2, len(points) - 1):
                if _segments_intersect(
                    points[first_index],
                    points[first_index + 1],
                    points[second_index],
                    points[second_index + 1],
                ):
                    self_intersection_count += 1
        for other_id, other_box in label_by_id.items():
            if other_id == own_label_id:
                continue
            if any(
                _segment_intersects_rectangle_interior(points[index], points[index + 1], other_box)
                for index in range(len(points) - 1)
            ):
                # Count each leader/other-label pair once, even if multiple
                # orthogonal segments cross the same label box.
                leader_label_intersection_count += 1
        if _out_of_page(box, page_size) or any(
            _page_point_out_of_page(point, page_size) for point in points
        ):
            out_of_page_count += 1
    values = {
        "CALLOUT_LABEL_COLLISION_COUNT": label_collision_count,
        "CALLOUT_LEADER_SELF_INTERSECTION_COUNT": self_intersection_count,
        "CALLOUT_LEADER_LABEL_INTERSECTION_COUNT": leader_label_intersection_count,
        "CALLOUT_OUT_OF_PAGE_COUNT": out_of_page_count,
    }
    derived_evidence = {
        name: DrawingLintMetricEvidenceV1(
            status="DERIVED",
            value=value,
            source="drawing_lint_facts.callout_leaders+label_boxes+page_size",
        )
        for name, value in values.items()
    }
    derived_evidence.update(explicit)
    return derived_evidence


def _required_fact_evidence(
    projection: Mapping[str, Any], name: str
) -> DrawingLintMetricEvidenceV1:
    present, value, source = _metric_value_with_source(projection, name)
    if not present:
        return DrawingLintMetricEvidenceV1(status="UNAVAILABLE", value=None, source=source)
    if name.endswith("_COUNT"):
        normalized: object = _count(value, field_name=name)
    else:
        normalized = _boolean(value, field_name=name)
    return DrawingLintMetricEvidenceV1(status="MEASURED", value=normalized, source=source)


def _area_schedule_visible(projection: Mapping[str, Any]) -> bool:
    furniture = _mapping(projection.get("page_furniture"), field_name="page_furniture")
    if not furniture:
        return False
    schedule = furniture.get("area_schedule")
    return isinstance(schedule, Mapping) and schedule.get("visible", True) is not False


def _derived_or_measured_count(
    projection: Mapping[str, Any],
    name: str,
    derived: tuple[int | None, str] | None = None,
) -> DrawingLintMetricEvidenceV1:
    present, value, source = _metric_value_with_source(projection, name)
    if present:
        return DrawingLintMetricEvidenceV1(
            status="MEASURED", value=_count(value, field_name=name), source=source
        )
    if derived is not None and derived[0] is not None:
        return DrawingLintMetricEvidenceV1(status="DERIVED", value=derived[0], source=derived[1])
    return DrawingLintMetricEvidenceV1(
        status="UNAVAILABLE", value=None, source="insufficient_drawing_facts"
    )


def _derived_or_measured_bool(
    projection: Mapping[str, Any],
    name: str,
    derived: tuple[bool | None, str] | None = None,
) -> DrawingLintMetricEvidenceV1:
    present, value, source = _metric_value_with_source(projection, name)
    if present:
        return DrawingLintMetricEvidenceV1(
            status="MEASURED", value=_boolean(value, field_name=name), source=source
        )
    if derived is not None and derived[0] is not None:
        return DrawingLintMetricEvidenceV1(status="DERIVED", value=derived[0], source=derived[1])
    return DrawingLintMetricEvidenceV1(
        status="UNAVAILABLE", value=None, source="insufficient_drawing_facts"
    )


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

    evidence: dict[str, DrawingLintMetricEvidenceV1] = {}
    evidence["ROOM_LABEL_CALLOUT_COUNT"] = _required_fact_evidence(
        projection, "ROOM_LABEL_CALLOUT_COUNT"
    )
    callout_count = evidence["ROOM_LABEL_CALLOUT_COUNT"].value
    if evidence["ROOM_LABEL_CALLOUT_COUNT"].status == "UNAVAILABLE":
        callout_count = 0
    elif not isinstance(callout_count, int):
        raise _error("DRAWING_LINT_INPUT_INVALID", field="ROOM_LABEL_CALLOUT_COUNT")

    evidence["ROOM_LABEL_WALL_CROSSING_COUNT"] = _required_fact_evidence(
        projection, "ROOM_LABEL_WALL_CROSSING_COUNT"
    )
    overlap_present, overlap_value, overlap_source = _metric_value_with_source(
        projection, "ROOM_LABEL_LABEL_OVERLAP_COUNT"
    )
    if overlap_present:
        evidence["ROOM_LABEL_LABEL_OVERLAP_COUNT"] = DrawingLintMetricEvidenceV1(
            status="MEASURED",
            value=_count(overlap_value, field_name="ROOM_LABEL_LABEL_OVERLAP_COUNT"),
            source=overlap_source,
        )
    else:
        primary_present, primary_value, primary_source = _metric_value_with_source(
            projection, "ROOM_LABEL_PRIMARY_COLLISION_COUNT"
        )
        evidence["ROOM_LABEL_LABEL_OVERLAP_COUNT"] = (
            DrawingLintMetricEvidenceV1(
                status="DERIVED",
                value=_count(primary_value, field_name="ROOM_LABEL_PRIMARY_COLLISION_COUNT"),
                source=primary_source,
            )
            if primary_present
            else DrawingLintMetricEvidenceV1(
                status="UNAVAILABLE", value=None, source="insufficient_drawing_facts"
            )
        )
    for name in (
        "ROOM_LABEL_DIMENSION_COLLISION_COUNT",
        "ROOM_LABEL_PORTAL_COLLISION_COUNT",
        "AREA_SCHEDULE_ROW_OVERLAP_COUNT",
        "PAGE_FURNITURE_OUT_OF_PAGE_COUNT",
        "ROOM_LABEL_OUT_OF_PAGE_COUNT",
        "VISIBLE_DIMENSION_OUT_OF_PAGE_COUNT",
    ):
        derived: tuple[int | None, str] | None = None
        if name == "PAGE_FURNITURE_OUT_OF_PAGE_COUNT":
            derived = (_furniture_out_of_page(projection), "page_furniture+page_size")
        elif name == "ROOM_LABEL_OUT_OF_PAGE_COUNT":
            derived_value = _derived_label_out_of_page_count(projection)
            derived = (derived_value, "drawing_lint_facts.label_boxes+page_size")
        elif name == "VISIBLE_DIMENSION_OUT_OF_PAGE_COUNT":
            derived_value = _derived_dimension_out_of_page_count(projection)
            derived = (derived_value, "drawing_lint_facts.dimension_boxes+page_size")
        evidence[name] = _derived_or_measured_count(projection, name, derived)

    evidence["AREA_SCHEDULE_CONTENT_CLIP_COUNT"] = _derived_or_measured_count(
        projection,
        "AREA_SCHEDULE_CONTENT_CLIP_COUNT",
        (
            _area_schedule_content_clip_count(projection),
            "page_furniture.area_schedule+schedule_row_envelope",
        ),
    )
    evidence["AREA_SCHEDULE_OUT_OF_PAGE_COUNT"] = _derived_or_measured_count(
        projection,
        "AREA_SCHEDULE_OUT_OF_PAGE_COUNT",
        (
            _furniture_out_of_page_for_name(projection, "area_schedule"),
            "page_furniture.area_schedule+page_size",
        ),
    )
    if not _area_schedule_visible(projection):
        for name in (
            "AREA_SCHEDULE_HEADER_FIRST_ROW_OVERLAP",
            "AREA_SCHEDULE_ROW_OVERLAP_COUNT",
            "AREA_SCHEDULE_CONTENT_CLIP_COUNT",
            "AREA_SCHEDULE_OUT_OF_PAGE_COUNT",
        ):
            evidence[name] = DrawingLintMetricEvidenceV1(
                status="NOT_APPLICABLE",
                value=0,
                source="profile.area_schedule_not_visible",
            )
    furniture_overlap_present, furniture_overlap_value, furniture_overlap_source = (
        _metric_value_with_source(projection, "PAGE_FURNITURE_OVERLAP_COUNT")
    )
    if furniture_overlap_present:
        evidence["PAGE_FURNITURE_OVERLAP_COUNT"] = DrawingLintMetricEvidenceV1(
            status="MEASURED",
            value=_count(furniture_overlap_value, field_name="PAGE_FURNITURE_OVERLAP_COUNT"),
            source=furniture_overlap_source,
        )
    else:
        legacy_overlap = _read_bool_metric(projection, "page_furniture_overlap")
        derived_overlap = (
            (int(legacy_overlap), "projection.page_furniture_overlap")
            if legacy_overlap is not None
            else (_derived_furniture_overlap_count(projection), "page_furniture.rectangles")
        )
        evidence["PAGE_FURNITURE_OVERLAP_COUNT"] = _derived_or_measured_count(
            projection, "PAGE_FURNITURE_OVERLAP_COUNT", derived_overlap
        )

    for name in (
        "AREA_SCHEDULE_HEADER_FIRST_ROW_OVERLAP",
        "TITLE_BLOCK_OVERLAP",
        "LEGEND_OVERLAP",
        "AREA_TABLE_OVERLAP",
        "INTERNAL_ZONE_CODE_VISIBLE",
        "SOURCE_HASH_VISIBLE",
        "PORTAL_DEBUG_TEXT_VISIBLE",
        "SCHEMA_IDENTITY_VISIBLE",
    ):
        evidence[name] = _required_fact_evidence(projection, name)

    evidence["PRIMARY_PLAN_OUT_OF_PAGE_COUNT"] = _derived_or_measured_count(
        projection,
        "PRIMARY_PLAN_OUT_OF_PAGE_COUNT",
        (_bounds_out_of_page(projection), "primary_plan_bounds+page_layout_bounds"),
    )

    evidence.update(_derived_callout_metrics(projection, callout_count=callout_count))
    metrics: dict[str, Any] = {name: item.value for name, item in evidence.items()}

    required_names = list(_BASE_REQUIRED_FACTS)
    if callout_count > 0:
        required_names.extend(_CALLOUT_REQUIRED_FACTS)
    issues: list[DrawingLintIssueV1] = []
    for name in required_names:
        item = evidence[name]
        if item.status == "UNAVAILABLE":
            issues.append(
                DrawingLintIssueV1(
                    severity="ERROR",
                    code="DRAWING_LINT_REQUIRED_FACT_UNAVAILABLE",
                    profile=resolved_profile,
                    element_ids=(name,),
                    message="Required drawing lint fact is unavailable.",
                    metrics={"fact": name, "source": item.source},
                )
            )

    count_messages = {
        "ROOM_LABEL_WALL_CROSSING_COUNT": "Room label crosses its room wall.",
        "ROOM_LABEL_LABEL_OVERLAP_COUNT": "Room labels overlap.",
        "ROOM_LABEL_DIMENSION_COLLISION_COUNT": "Room label collides with a dimension.",
        "ROOM_LABEL_PORTAL_COLLISION_COUNT": "Room label collides with a portal.",
        "CALLOUT_LABEL_COLLISION_COUNT": "Callout label overlaps another label.",
        "CALLOUT_LEADER_SELF_INTERSECTION_COUNT": "Callout leader self-intersects.",
        "CALLOUT_LEADER_LABEL_INTERSECTION_COUNT": "Callout leader intersects another label.",
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
    count_names = tuple(count_messages)
    for code in count_names:
        item = evidence[code]
        if item.status == "UNAVAILABLE" or not isinstance(item.value, int):
            continue
        issue = _issues_for_count(
            profile=resolved_profile,
            code=code,
            count=item.value,
            message=count_messages[code],
            element_ids=_stable_element_ids(projection, code),
        )
        if issue is not None:
            issues.append(issue)

    for code, message in (
        ("AREA_SCHEDULE_HEADER_FIRST_ROW_OVERLAP", "Area schedule header overlaps its first row."),
        ("TITLE_BLOCK_OVERLAP", "Title block overlaps another page element."),
        ("LEGEND_OVERLAP", "Legend overlaps another page element."),
        ("AREA_TABLE_OVERLAP", "Area schedule overlaps another page element."),
    ):
        item = evidence[code]
        if item.status != "UNAVAILABLE" and item.value is True:
            issue = _issues_for_bool(
                profile=resolved_profile,
                code=code,
                value=True,
                message=message,
                element_ids=_stable_element_ids(projection, code),
            )
            if issue is not None:
                issues.append(issue)

    leakage_severity = _leakage_severity(resolved_profile)
    if leakage_severity is not None:
        for code, message in (
            (
                "INTERNAL_ZONE_CODE_VISIBLE",
                "Internal zone code is visible in a business drawing profile.",
            ),
            ("SOURCE_HASH_VISIBLE", "Source hash is visible in a business drawing profile."),
            (
                "PORTAL_DEBUG_TEXT_VISIBLE",
                "Portal debug text is visible in a business drawing profile.",
            ),
            (
                "SCHEMA_IDENTITY_VISIBLE",
                "Schema identity is visible in a business drawing profile.",
            ),
        ):
            item = evidence[code]
            if item.status != "UNAVAILABLE" and item.value is True:
                issue = _issues_for_bool(
                    profile=resolved_profile,
                    code=code,
                    value=True,
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
        metric_evidence=evidence,
        required_fact_names=required_names,
        issues=issues,
    )


def _furniture_out_of_page_for_name(projection: Mapping[str, Any], name: str) -> int | None:
    page_size = _page_size(projection)
    furniture = _mapping(projection.get("page_furniture"), field_name="page_furniture")
    if page_size is None or furniture is None:
        return None
    item = furniture.get(name)
    if item is None:
        return None
    if isinstance(item, Mapping) and item.get("visible", True) is False:
        return 0
    return int(_out_of_page(_rectangle(item, field_name=f"page_furniture.{name}"), page_size))


def _area_schedule_content_clip_count(projection: Mapping[str, Any]) -> int | None:
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
        return None
    schedule = furniture.get("area_schedule")
    if not isinstance(schedule, Mapping):
        return None
    if schedule.get("visible", True) is False:
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
    "DRAWING_LINT_EVIDENCE_STATUSES",
    "MISSING_FACT_IS_ZERO",
    "MISSING_FACT_IS_FALSE",
    "MISSING_REQUIRED_FACT_FAILS_CLOSED",
    "EVIDENCE_STATUS_HASHED",
    "EVIDENCE_SOURCE_HASHED",
    "DRAWING_LINT_PROFILES",
    "DrawingLintMetricEvidenceV1",
    "DrawingLintIssueV1",
    "DrawingLintReportV1",
    "lint_drawing_projection",
]
