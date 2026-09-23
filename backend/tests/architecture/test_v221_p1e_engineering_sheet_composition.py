"""Architecture and scope guards for P1E Engineering Sheet composition."""

from __future__ import annotations

import subprocess
from decimal import Decimal
from pathlib import Path

from cold_storage.modules.layout.domain.engineering_sheet_composition import (
    ENGINEERING_SHEET_CANDIDATE_IDENTITY,
    ENGINEERING_SHEET_CANDIDATE_ORDER,
    ENGINEERING_SHEET_MAIN_DRAWING_MAX_OCCUPANCY,
    ENGINEERING_SHEET_MAIN_DRAWING_MIN_OCCUPANCY,
    ENGINEERING_SHEET_MAIN_DRAWING_TARGET_OCCUPANCY,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_MAIN_SHA = "2154c869ed202beeeb1903d1875508122a4ed829"
DOMAIN = "backend/src/cold_storage/modules/layout/domain/engineering_sheet_composition.py"
PROJECTION = "backend/src/cold_storage/modules/layout/domain/svg_projection.py"
APPLICATION = "backend/src/cold_storage/modules/layout/application/svg_projection.py"
UNIT = "backend/tests/unit/test_v221_p1e_engineering_sheet_composition.py"
SELF = "backend/tests/architecture/test_v221_p1e_engineering_sheet_composition.py"
P1A_UNIT = "backend/tests/unit/test_v221_p1a_canvas_viewbox_page_composition.py"
P1A_ARCH = "backend/tests/architecture/test_v221_p1a_canvas_viewbox_page_composition.py"
P1D_UNIT = "backend/tests/unit/test_v221_p1d_drawing_lint.py"
P1D_ARCH = "backend/tests/architecture/test_v221_p1d_drawing_lint.py"
P3_ARCH = "backend/tests/architecture/test_v22_p3_svg_projection.py"
DOC = "docs/tasks/V2_2_1-P1E-engineering-sheet-composition.md"
PLAN = "docs/tasks/V2_2-version-plan.md"
ADR = "docs/architecture/ADR-046-engineering-sheet-composition.md"
BEFORE_PNG = "docs/tasks/evidence/v2_2_1_p1e/before-engineering-sheet.png"
AFTER_PNG = "docs/tasks/evidence/v2_2_1_p1e/after-engineering-sheet.png"
GENERATED_ARTIFACT_PREFIX = "backend/artifacts/local/"
ALLOWED_PATHS = {
    DOMAIN,
    PROJECTION,
    APPLICATION,
    UNIT,
    SELF,
    P1A_UNIT,
    P1A_ARCH,
    P1D_UNIT,
    P1D_ARCH,
    P3_ARCH,
    DOC,
    PLAN,
    ADR,
    BEFORE_PNG,
    AFTER_PNG,
}
PROTECTED_PATHS = {
    "backend/src/cold_storage/modules/calculations/",
    "backend/src/cold_storage/modules/layout/domain/access_routing.py",
    "backend/src/cold_storage/modules/layout/application/access_routing.py",
    "backend/src/cold_storage/modules/layout/domain/placement.py",
    "backend/src/cold_storage/modules/layout/application/placement.py",
    "backend/src/cold_storage/modules/layout/domain/site_geometry.py",
    "backend/src/cold_storage/modules/layout/application/site_geometry.py",
    "backend/src/cold_storage/modules/aily/api/mcp_sse.py",
    "backend/alembic/",
    "frontend/",
    ".github/workflows/",
}


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _source(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _source_changes(tracked: set[str], untracked: set[str]) -> set[str]:
    # Backend integration/architecture tests may leave generated report files
    # in this runtime output directory. They are not source changes in the PR.
    return tracked | {path for path in untracked if not path.startswith(GENERATED_ARTIFACT_PREFIX)}


def test_generated_report_artifacts_are_not_source_changes() -> None:
    assert (
        _source_changes(
            set(),
            {
                "backend/artifacts/local/run/report.pdf",
                "backend/artifacts/local/run/report.pdf.meta",
            },
        )
        == set()
    )
    assert _source_changes(set(), {"backend/src/cold_storage/modules/layout/new_module.py"}) == {
        "backend/src/cold_storage/modules/layout/new_module.py"
    }


def test_p1e_changes_are_projection_only_and_within_allowlist() -> None:
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_MAIN_SHA, "HEAD"],
        cwd=REPO_ROOT,
        check=True,
    )
    tracked = set(_git("diff", "--name-only", BASE_MAIN_SHA, "HEAD").splitlines())
    untracked = set(_git("ls-files", "--others", "--exclude-standard").splitlines())
    changed = _source_changes(tracked, untracked)
    assert changed <= ALLOWED_PATHS
    assert not any(
        path == protected or path.startswith(protected)
        for path in changed
        for protected in PROTECTED_PATHS
    )


def test_composition_is_a_finite_presentation_only_policy() -> None:
    source = _source(DOMAIN)
    application = _source(APPLICATION)
    projection = _source(PROJECTION)
    document = _source(DOC)
    assert (REPO_ROOT / BEFORE_PNG).is_file()
    assert (REPO_ROOT / AFTER_PNG).is_file()

    assert ENGINEERING_SHEET_CANDIDATE_IDENTITY == "engineering-sheet-composition@1.0.0"
    assert ENGINEERING_SHEET_CANDIDATE_ORDER == ("RIGHT_RAIL", "BOTTOM_RAIL")
    assert Decimal("0.70") == ENGINEERING_SHEET_MAIN_DRAWING_MIN_OCCUPANCY
    assert Decimal("0.78") == ENGINEERING_SHEET_MAIN_DRAWING_TARGET_OCCUPANCY
    assert Decimal("0.88") == ENGINEERING_SHEET_MAIN_DRAWING_MAX_OCCUPANCY
    assert "build_engineering_sheet_composition" in projection
    assert "lint_validated_layout_drawing(payload" in application
    assert "for candidate in ENGINEERING_SHEET_CANDIDATE_ORDER" in application
    assert "ENGINEERING_SHEET_COMPOSITION_NO_VALID_CANDIDATE" in application
    for forbidden in (
        "modules.calculations",
        "placement",
        "access_routing",
        "site_geometry",
        "fastapi",
        "sqlalchemy",
        "mcp",
    ):
        assert forbidden not in source.lower()
    for required in (
        "P1E_ENGINEERING_SHEET_COMPOSITION_R1",
        "ENGINEERING_SHEET_PRIMARY_PLAN_FOCUS=true",
        "ENGINEERING_SHEET_CONTEXT_INSET_VISIBLE=true",
        "FULL_SITE_CONTEXT_PRESERVED=true",
        "ENGINEERING_SHEET_FULL_ROOM_DIMENSIONS=true",
        "P1D_DRAWING_LINT_GATE=HARD_GATE",
        "PRESENTATION_SVG_BYTES_CHANGED=false",
        "MOBILE_PREVIEW_SVG_BYTES_CHANGED=false",
        "ENGINEERING_REVIEW_SVG_BYTES_CHANGED=false",
        "SOURCE_ENGINEERING_GEOMETRY_CHANGED=false",
        "P2_CHANGED=false",
    ):
        assert required in document
