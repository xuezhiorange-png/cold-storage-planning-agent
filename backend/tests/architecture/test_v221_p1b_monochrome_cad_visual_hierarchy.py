"""Durable architecture locks for the V2.2.1 P1B visual hierarchy."""

from __future__ import annotations

import subprocess
from pathlib import Path

from cold_storage.modules.layout.domain.svg_projection import (
    SVG_COLOR_MODE,
    SVG_NO_BUILD_HATCH_COLOR,
    SVG_STROKE_W0,
    SVG_STROKE_W1,
    SVG_STROKE_W2,
    SVG_STROKE_W3,
    SVG_STROKE_W4,
    SVG_STROKE_W5,
    SVG_STYLE_ID,
    SVG_STYLE_NAME,
    SvgDrawingThemeV1,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_MAIN_SHA = "dd26be03438ba7e3b147e5b700e3815d80d70458"
DOMAIN = "backend/src/cold_storage/modules/layout/domain/svg_projection.py"
UNIT = "backend/tests/unit/test_v221_p1b_monochrome_cad_visual_hierarchy.py"
SELF = "backend/tests/architecture/test_v221_p1b_monochrome_cad_visual_hierarchy.py"
P1A_SCOPE_GUARD = "backend/tests/architecture/test_v221_p1a_canvas_viewbox_page_composition.py"
DOC = "docs/tasks/V2_2_1-P1B-monochrome-cad-visual-hierarchy.md"
PLAN = "docs/tasks/V2_2-version-plan.md"
ADR = "docs/architecture/ADR-045-layout-drawing-style-projection.md"
ALLOWED_PATHS = {DOMAIN, UNIT, SELF, P1A_SCOPE_GUARD, DOC, PLAN, ADR}
PROTECTED_PREFIXES = (
    "backend/src/cold_storage/modules/calculations/",
    "backend/src/cold_storage/modules/layout/application/access_routing.py",
    "backend/src/cold_storage/modules/layout/application/placement.py",
    "backend/src/cold_storage/modules/layout/domain/access_routing.py",
    "backend/src/cold_storage/modules/layout/domain/placement.py",
    "frontend/src/",
    "backend/alembic/",
    ".github/workflows/",
)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _source(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _historical_target() -> str | None:
    history = _git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    return history.splitlines()[0] if history else None


def _historical_changed_paths() -> set[str]:
    target = _historical_target()
    if target is None:
        return set(_git("diff", "--name-only", BASE_MAIN_SHA, "HEAD").splitlines())
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=REPO_ROOT, check=True
    )
    return set(_git("diff", "--name-only", BASE_MAIN_SHA, target).splitlines())


def test_p1b_scope_is_projection_only_and_does_not_touch_runtime_authorities() -> None:
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_MAIN_SHA, "HEAD"], cwd=REPO_ROOT, check=True
    )
    changed = _historical_changed_paths()
    assert changed <= ALLOWED_PATHS
    assert not any(path.startswith(PROTECTED_PREFIXES) for path in changed)


def test_style_identity_palette_and_weights_are_frozen() -> None:
    assert SVG_STYLE_ID == "LAYOUT_DRAWING_STYLE_V1"
    assert SVG_STYLE_NAME == "CAD_FACTORY_LAYOUT"
    assert SVG_COLOR_MODE == "MONOCHROME_PRIMARY"
    assert SVG_NO_BUILD_HATCH_COLOR == "#B5B5B5"
    assert tuple(
        str(value)
        for value in (
            SVG_STROKE_W5,
            SVG_STROKE_W4,
            SVG_STROKE_W3,
            SVG_STROKE_W2,
            SVG_STROKE_W1,
            SVG_STROKE_W0,
        )
    ) == (
        "3.0",
        "2.2",
        "1.6",
        "1.1",
        "0.75",
        "0.45",
    )
    assert all(
        left > right
        for left, right in zip(
            (
                SVG_STROKE_W5,
                SVG_STROKE_W4,
                SVG_STROKE_W3,
                SVG_STROKE_W2,
                SVG_STROKE_W1,
            ),
            (SVG_STROKE_W4, SVG_STROKE_W3, SVG_STROKE_W2, SVG_STROKE_W1, SVG_STROKE_W0),
            strict=True,
        )
    )
    theme = SvgDrawingThemeV1()
    assert theme.zone_fill == "#FAFAFA"
    assert theme.cold_zone_fill == "#F3F3F3"
    assert theme.corridor_fill == "#F7F7F7"
    assert theme.loading_face == "#222222"
    assert theme.entrance_stroke == "#555555"


def test_style_source_keeps_profile_separation_and_no_geometry_authority() -> None:
    source = _source(DOMAIN)
    for required in (
        "SVG_STYLE_ID",
        "SVG_COLOR_MODE",
        "SVG_REVIEW_ACCENT_PROFILES",
        "SVG_STROKE_W5",
        "SVG_STROKE_W0",
        "SVG_NO_BUILD_HATCH_COLOR",
        "review_accent_visible",
        "review_overlays_visible",
        "SVG_ZONE_FILL_OPACITY",
        "engineering_coordinates_mutated",
        "source_engineering_geometry_changed",
    ):
        assert required in source
    assert "route_site_placement" not in source
    assert "calculate_" not in source
    assert "MCP" not in source
    assert "frontend" not in source.lower()


def test_p1a_focus_and_context_contract_remain_present() -> None:
    source = _source(DOMAIN)
    for required in (
        "primary_plan_bounds",
        "SVG_CONTEXT_INSET_WIDTH_M",
        "context_inset",
        "SVG_FOCUS_PROFILES",
        "primary_plan_screen_occupancy",
        "primary_plan_width_ratio",
        "primary_plan_height_ratio",
    ):
        assert required in source
