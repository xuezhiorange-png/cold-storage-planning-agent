"""Durable architecture locks for the V2.2.1 P1A page composition fix."""

from __future__ import annotations

import subprocess
from decimal import Decimal
from pathlib import Path

from cold_storage.modules.layout.domain.svg_projection import (
    SVG_MAIN_DRAWING_MAX_OCCUPANCY,
    SVG_MAIN_DRAWING_MIN_OCCUPANCY,
    SVG_MAIN_DRAWING_TARGET_OCCUPANCY,
    SVG_MOBILE_DRAWING_MIN_OCCUPANCY,
    SVG_PAGE_PROFILES,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_MAIN_SHA = "00f684b994c22fbab85227a6ae7b88ff8f697f54"
DOMAIN = "backend/src/cold_storage/modules/layout/domain/svg_projection.py"
APPLICATION = "backend/src/cold_storage/modules/layout/application/svg_projection.py"
UNIT = "backend/tests/unit/test_v221_p1a_canvas_viewbox_page_composition.py"
SELF = "backend/tests/architecture/test_v221_p1a_canvas_viewbox_page_composition.py"
DOC = "docs/tasks/V2_2_1-P1A-canvas-viewbox-page-composition.md"
PLAN = "docs/tasks/V2_2-version-plan.md"
ADR = "docs/architecture/ADR-045-layout-drawing-style-projection.md"
ALLOWED_PATHS = {DOMAIN, APPLICATION, UNIT, SELF, DOC, PLAN, ADR}
GENERATED_ARTIFACT_PREFIX = "backend/artifacts/local/"
PROTECTED_PREFIXES = (
    "frontend/",
    "backend/alembic/",
    ".github/workflows/",
    "deployment/",
)
PROTECTED_PATHS = {
    "backend/src/cold_storage/modules/layout/domain/access_routing.py",
    "backend/src/cold_storage/modules/layout/application/access_routing.py",
    "backend/src/cold_storage/modules/layout/domain/placement.py",
    "backend/src/cold_storage/modules/layout/application/placement.py",
    "backend/src/cold_storage/modules/layout/domain/site_geometry.py",
    "backend/src/cold_storage/modules/layout/application/site_geometry.py",
    "backend/src/cold_storage/modules/aily/api/mcp_sse.py",
}


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _paths_from_base() -> set[str]:
    paths = set(_git("diff", "--name-only", BASE_MAIN_SHA, "HEAD").splitlines())
    paths.update(_git("ls-files", "--others", "--exclude-standard").splitlines())
    return {path for path in paths if path and not path.startswith(GENERATED_ARTIFACT_PREFIX)}


def _source(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_p1a_scope_is_limited_to_projection_and_evidence() -> None:
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_MAIN_SHA, "HEAD"],
        cwd=REPO_ROOT,
        check=True,
    )
    changed = _paths_from_base()
    assert changed <= ALLOWED_PATHS
    assert not any(path.startswith(PROTECTED_PREFIXES) for path in changed)
    assert not changed.intersection(PROTECTED_PATHS)


def test_p1a_profiles_and_occupancy_contract_are_versioned() -> None:
    assert SVG_PAGE_PROFILES == (
        "PRESENTATION",
        "MOBILE_PREVIEW",
        "ENGINEERING_SHEET",
        "ENGINEERING_REVIEW",
    )
    assert Decimal("0.78") == SVG_MAIN_DRAWING_TARGET_OCCUPANCY
    assert Decimal("0.70") == SVG_MAIN_DRAWING_MIN_OCCUPANCY
    assert Decimal("0.88") == SVG_MAIN_DRAWING_MAX_OCCUPANCY
    assert Decimal("0.80") == SVG_MOBILE_DRAWING_MIN_OCCUPANCY

    source = _source(DOMAIN)
    for required in (
        "def _page_composition(",
        '"engineering_geometry_bounds"',
        '"engineering_drawing_bounds"',
        '"page_layout_bounds"',
        '"main_drawing_occupancy"',
        '"source_geometry_occupancy"',
        '"title_block_overlap"',
        '"area_table_overlap"',
        '"legend_overlap"',
        '"area-schedule"',
        '"MOBILE_PREVIEW"',
        "SVG_MOBILE_PRIMARY_PLAN_OCCUPANCY_MIN",
        "SVG_MOBILE_PRIMARY_PLAN_WIDTH_RATIO_MIN",
        "SVG_MOBILE_PRIMARY_PLAN_HEIGHT_RATIO_MIN",
        '"primary_plan_bounds"',
        '"context_inset"',
        '"primary_plan_visually_readable"',
        "review_overlays_visible",
        "ENGINEERING_REVIEW",
        "if review_overlays_visible",
        "include_source_hash=review_overlays_visible",
    ):
        assert required in source


def test_p1a_projection_boundary_passes_profile_without_engineering_reentry() -> None:
    source = _source(APPLICATION)
    assert 'page_profile: str = "PRESENTATION"' in source
    assert "build_projection_payload(" in source
    assert "page_profile=page_profile" in source
    assert "route_site_placement" not in source
    assert "calculate_" not in source
    assert "mcp" not in source.lower()
    assert "fastapi" not in source.lower()


def test_p1a_evidence_freezes_authority_boundary() -> None:
    document = _source(DOC)
    plan = _source(PLAN)
    adr = _source(ADR)
    for text in (document, plan, adr):
        assert "ENGINEERING_BOUNDS_SEPARATED" in text or "engineering_geometry_bounds" in text
    for required in (
        "TASK_ID=V2_2_1_P1A_CANVAS_VIEWBOX_PAGE_COMPOSITION_R1",
        f"BASE_MAIN_SHA={BASE_MAIN_SHA}",
        "PRESENTATION_OCCUPANCY>=0.70",
        "MOBILE_PREVIEW_OCCUPANCY>=0.80",
        "P2_CHANGED=NO",
        "P2D_CHANGED=NO",
        "MCP_CHANGED=NO",
        "P1B_AUTHORIZED=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    ):
        assert required in document
