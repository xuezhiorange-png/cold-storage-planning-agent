"""Scope and rendering-contract locks for the P1F inset correction."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_MAIN_SHA = "debda749966e7c890e2f8758f468fa582fb3def8"
P1F_MERGE_SHA = "a71347a7ca56c32b2facaa3b57e489427b9a7ea8"
PROJECTION = "backend/src/cold_storage/modules/layout/domain/svg_projection.py"
UNIT = "backend/tests/unit/test_v221_p1f_context_inset_loading_face_correction.py"
SELF = "backend/tests/architecture/test_v221_p1f_context_inset_loading_face_correction.py"
P1D_ARCH = "backend/tests/architecture/test_v221_p1d_drawing_lint.py"
P1E_ARCH = "backend/tests/architecture/test_v221_p1e_engineering_sheet_composition.py"
P1D_UNIT = "backend/tests/unit/test_v221_p1d_drawing_lint.py"
P1E_UNIT = "backend/tests/unit/test_v221_p1e_engineering_sheet_composition.py"
DOC = "docs/tasks/V2_2_1-P1F-context-inset-loading-face-correction.md"
P1F_RERUN_EVIDENCE = {
    "docs/tasks/V2_2_1-P1F-cross-fixture-drawing-robustness.md",
    "docs/tasks/V2_2_1-P1E-engineering-sheet-composition.md",
    "docs/tasks/V2_2-version-plan.md",
    "backend/tests/evaluation/test_v221_p1f_cross_fixture_drawing_robustness.py",
    "docs/tasks/evidence/v2_2_1_p1f/acceptance-matrix.json",
    "docs/tasks/evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-presentation.png",
    "docs/tasks/evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-presentation.svg",
    "docs/tasks/evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-presentation-context-inset.png",
    "docs/tasks/evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-presentation-context-loading-face-detail.png",
    "docs/tasks/evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-mobile_preview.png",
    "docs/tasks/evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-mobile_preview.svg",
    "docs/tasks/evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-mobile_preview-context-inset.png",
    "docs/tasks/evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-mobile_preview-context-loading-face-detail.png",
    "docs/tasks/evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-engineering_sheet.png",
    "docs/tasks/evidence/v2_2_1_p1f/p2d_representative_20t_rectangular_site-engineering_sheet.svg",
    "docs/tasks/evidence/v2_2_1_p1f/p4_real_selector_site_with_no_build_zones-engineering_sheet.png",
    "docs/tasks/evidence/v2_2_1_p1f/p4_real_selector_site_with_no_build_zones-engineering_sheet.svg",
    "docs/tasks/evidence/v2_2_1_p1f/p3_existing_concave_site_validated_layout-engineering_review.png",
    "docs/tasks/evidence/v2_2_1_p1f/p3_existing_concave_site_validated_layout-engineering_review.svg",
}
EVIDENCE = {
    "docs/tasks/evidence/v2_2_1_p1f_context_loading_face/before_presentation.svg",
    "docs/tasks/evidence/v2_2_1_p1f_context_loading_face/before_presentation.png",
    "docs/tasks/evidence/v2_2_1_p1f_context_loading_face/after_presentation.svg",
    "docs/tasks/evidence/v2_2_1_p1f_context_loading_face/after_presentation.png",
    "docs/tasks/evidence/v2_2_1_p1f_context_loading_face/before_mobile_preview.svg",
    "docs/tasks/evidence/v2_2_1_p1f_context_loading_face/before_mobile_preview.png",
    "docs/tasks/evidence/v2_2_1_p1f_context_loading_face/after_mobile_preview.svg",
    "docs/tasks/evidence/v2_2_1_p1f_context_loading_face/after_mobile_preview.png",
    "docs/tasks/evidence/v2_2_1_p1f_context_loading_face/after_presentation_context_crop.png",
    "docs/tasks/evidence/v2_2_1_p1f_context_loading_face/after_mobile_context_crop.png",
    "docs/tasks/evidence/v2_2_1_p1f_context_loading_face/evidence.json",
}
ALLOWED_PATHS = {
    PROJECTION,
    UNIT,
    SELF,
    P1D_ARCH,
    P1E_ARCH,
    P1D_UNIT,
    P1E_UNIT,
    DOC,
    *EVIDENCE,
    *P1F_RERUN_EVIDENCE,
}
PROTECTED_PREFIXES = (
    "backend/src/cold_storage/modules/calculations/",
    "backend/src/cold_storage/modules/layout/application/access_routing.py",
    "backend/src/cold_storage/modules/layout/application/placement.py",
    "backend/src/cold_storage/modules/layout/domain/access_routing.py",
    "backend/src/cold_storage/modules/layout/domain/placement.py",
    "backend/src/cold_storage/modules/layout/domain/site_geometry.py",
    "backend/src/cold_storage/modules/aily/",
    "backend/alembic/",
    "frontend/",
    ".github/",
)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def test_context_loading_face_correction_has_exact_scope() -> None:
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_MAIN_SHA, P1F_MERGE_SHA],
        cwd=REPO_ROOT,
        check=True,
    )
    # This guard freezes the exact merged P1F change set. Later tasks are not
    # part of that historical PR scope and must not be folded into its audit.
    changed = set(_git("diff", "--name-only", BASE_MAIN_SHA, P1F_MERGE_SHA).splitlines())
    assert changed <= ALLOWED_PATHS
    changed_runtime = {path for path in changed if path.startswith("backend/src/")}
    assert changed_runtime == {PROJECTION}
    assert not any(path.startswith(PROTECTED_PREFIXES) for path in changed)


def test_context_loading_face_uses_the_existing_authoritative_segment() -> None:
    source = (REPO_ROOT / PROJECTION).read_text(encoding="utf-8")
    context_block = source.split("if context_transform is not None:", 1)[1].split(
        "portal_parts: list[str]", 1
    )[0]
    assert '"id": "context-shipping-loading-face"' in context_block
    assert "context_transform.point(loading_face[0])" in context_block
    assert "context_transform.point(loading_face[1])" in context_block
    assert 'page_profile == "ENGINEERING_SHEET"' not in context_block

    test_source = (REPO_ROOT / UNIT).read_text(encoding="utf-8")
    for contract in (
        '"PRESENTATION"',
        '"MOBILE_PREVIEW"',
        '"ENGINEERING_SHEET"',
        '"ENGINEERING_REVIEW"',
        "P2D_REPRESENTATIVE_20T_RECTANGULAR_SITE",
        "P3_EXISTING_CONCAVE_SITE_VALIDATED_LAYOUT",
        "P4_REAL_SELECTOR_SITE_WITH_NO_BUILD_ZONES",
    ):
        assert contract in test_source
