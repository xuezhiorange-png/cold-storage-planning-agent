"""Application boundary for deterministic drawing diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.drawing_lint import (
    DrawingLintReportV1,
    lint_drawing_projection,
)
from cold_storage.modules.layout.domain.svg_projection import ValidatedLayoutSvgProjectionV1


def lint_validated_layout_drawing(
    projection: ValidatedLayoutSvgProjectionV1 | Mapping[str, Any],
    *,
    page_profile: str | None = None,
) -> DrawingLintReportV1:
    """Lint resolved projection facts without invoking the renderer again."""
    if isinstance(projection, ValidatedLayoutSvgProjectionV1):
        body = projection.to_dict()
    elif isinstance(projection, Mapping):
        body = dict(projection)
    else:
        raise LayoutAuthorityError("DRAWING_LINT_INPUT_INVALID", field="projection")
    return lint_drawing_projection(body, profile=page_profile)


build_drawing_lint_report = lint_validated_layout_drawing


__all__ = ["build_drawing_lint_report", "lint_validated_layout_drawing"]
