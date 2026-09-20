"""Durable locks for the V2.2.1 P0 drawing-style contract freeze."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_MAIN_SHA = "34cd6b56c1d79dde9730898c6bd46e295e423334"
CONTRACT = "docs/tasks/V2_2_1-P0-layout-drawing-style-contract.md"
PLAN = "docs/tasks/V2_2-version-plan.md"
ADR = "docs/architecture/ADR-045-layout-drawing-style-projection.md"
SELF = "backend/tests/architecture/test_v221_p0_layout_drawing_style_contract.py"
ALLOWED_PATHS = {CONTRACT, PLAN, ADR, SELF}

PROTECTED_RUNTIME_PREFIXES = (
    "backend/src/",
    "frontend/",
    "backend/alembic/",
    ".github/workflows/",
    "deployment/",
)
PROTECTED_P3_PATHS = {
    "backend/src/cold_storage/modules/layout/domain/svg_projection.py",
    "backend/src/cold_storage/modules/layout/application/svg_projection.py",
    "backend/tests/unit/test_v22_p3_svg_projection.py",
}


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _source(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _historical_target() -> str | None:
    history = _git(
        "log",
        "--reverse",
        "--diff-filter=A",
        "--format=%H",
        "HEAD",
        "--",
        SELF,
    )
    return history.splitlines()[0] if history else None


def _historical_changed_paths() -> set[str]:
    target = _historical_target()
    if target:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", target, "HEAD"],
            cwd=REPO_ROOT,
            check=True,
        )
        return set(_git("diff", "--name-only", BASE_MAIN_SHA, target).splitlines())

    paths = set(_git("diff", "--name-only", BASE_MAIN_SHA, "HEAD").splitlines())
    paths.update(_git("ls-files", "--others", "--exclude-standard").splitlines())
    return {path for path in paths if path}


def test_scope_is_contract_docs_and_architecture_only() -> None:
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_MAIN_SHA, "HEAD"],
        cwd=REPO_ROOT,
        check=True,
    )
    changed = _historical_changed_paths()
    assert changed <= ALLOWED_PATHS
    assert not any(path.startswith(PROTECTED_RUNTIME_PREFIXES) for path in changed)
    assert not changed.intersection(PROTECTED_P3_PATHS)


def test_contract_identity_and_governance_boundary_are_frozen() -> None:
    source = _source(CONTRACT)
    for required in (
        "TASK_ID=V2_2_1_P0_LAYOUT_DRAWING_STYLE_CONTRACT_FREEZE_R1",
        "BASE_RELEASE=v2.2.0",
        f"BASE_MAIN_SHA={BASE_MAIN_SHA}",
        "TARGET_VERSION=v2.2.1",
        "STYLE_ID=LAYOUT_DRAWING_STYLE_V1",
        "STYLE_NAME=CAD_FACTORY_LAYOUT",
        "CANONICAL_ENGINEERING_AUTHORITY=STRUCTURED_LAYOUT_JSON",
        "SVG_ROLE=PRESENTATION_PROJECTION",
        "IMPLEMENTATION_STARTED=NO",
        "P1_AUTHORIZED=NO",
        "P2_CHANGED=NO",
        "P2D_CHANGED=NO",
        "P3_RUNTIME_CHANGED=NO",
        "P4_CHANGED=NO",
        "MCP_CHANGED=NO",
        "DATABASE_CHANGED=NO",
        "READY_AUTHORIZED=NO",
        "MERGE_AUTHORIZED=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    ):
        assert required in source


def test_golden_references_modes_profiles_and_layers_are_explicit() -> None:
    source = _source(CONTRACT)
    for required in (
        "GD-001",
        "GD-002",
        "GD-003",
        "GD-004",
        "GD-005",
        "GOLDEN_REFERENCE_COUNT=5",
        "PRIMARY_GOLDEN_REFERENCE=GD-005_PANLONG",
        "PRESENTATION_MODE_FROZEN=TRUE",
        "ENGINEERING_REVIEW_MODE_FROZEN=TRUE",
        "DEFAULT_DRAWING_MODE=PRESENTATION",
        "MOBILE_PREVIEW_PROFILE_FROZEN=TRUE",
        "ENGINEERING_SHEET_PROFILE_FROZEN=TRUE",
        "01 site-background",
        "09 zones",
        "12 truck-and-loading",
        "18 title-block",
        "DEBUG_LAYER=FALSE",
    ):
        assert required in source


def test_presentation_honesty_and_information_hierarchy_are_locked() -> None:
    source = _source(CONTRACT)
    for required in (
        "COLOR_MODE=MONOCHROME_PRIMARY",
        "MAX_ACCENT_COLORS=1",
        "W5=EXTERIOR_WALL",
        "W0=AUXILIARY_BACKGROUND",
        "UNAUTHORIZED_EQUIPMENT_INFERENCE=FALSE",
        "UNAUTHORIZED_RACK_INFERENCE=FALSE",
        "UNAUTHORIZED_GRID_INFERENCE=FALSE",
        "UNAUTHORIZED_COLUMN_INFERENCE=FALSE",
        "UNAUTHORIZED_TRUCK_GEOMETRY_INFERENCE=FALSE",
        "3 lines -> 2 lines -> 1 line -> numeric id + external schedule",
        "ROOM_LABEL_WALL_CROSSING_COUNT=0",
        "ROOM_LABEL_PRIMARY_COLLISION_COUNT=0",
        "LEVEL_1_TOTAL_DIMENSIONS",
        "LEVEL_4_ENGINEERING_REVIEW_DIMENSIONS",
        "GRID_RENDERING_CAPABILITY=TRUE",
        "AUTO_INVENT_GRID=FALSE",
        "SCALE=SCHEMATIC",
    ):
        assert required in source


def test_page_composition_and_acceptance_contract_are_locked() -> None:
    source = _source(CONTRACT)
    for required in (
        "ENGINEERING_GEOMETRY_BOUNDS_SEPARATE_FROM_PAGE_LAYOUT_BOUNDS=TRUE",
        "MAIN_DRAWING_TARGET_OCCUPANCY=0.78",
        "MAIN_DRAWING_MIN_OCCUPANCY=0.70",
        "MAIN_DRAWING_MAX_OCCUPANCY=0.88",
        "LEGEND_PARTICIPATES_IN_ENGINEERING_BOUNDS=FALSE",
        "TITLE_BLOCK_PARTICIPATES_IN_ENGINEERING_BOUNDS=FALSE",
        "AREA_SCHEDULE_PARTICIPATES_IN_ENGINEERING_BOUNDS=FALSE",
        "TITLE_BLOCK_OVERLAP=FALSE",
        "AREA_TABLE_OVERLAP=FALSE",
        "LEGEND_OVERLAP=FALSE",
        "MAIN_DRAWING_SCREEN_OCCUPANCY_MIN=0.80",
        "SVG_XML_VALID=TRUE",
        "SAME_INPUT_SAME_DRAWING_BYTES=TRUE",
        "SAME_INPUT_SAME_DRAWING_HASH=TRUE",
    ):
        assert required in source


def test_adr_and_version_plan_reference_the_current_freeze() -> None:
    adr = _source(ADR)
    plan = _source(PLAN)
    assert "LAYOUT_DRAWING_STYLE_V1" in adr
    assert "structured validated layout JSON remains the canonical" in adr
    assert "engineering authority" in adr
    for required in (
        "TASK_ID=V2_2_1_P0_LAYOUT_DRAWING_STYLE_CONTRACT_FREEZE_R1",
        "TARGET_VERSION=v2.2.1",
        "STYLE_CONTRACT_CREATED=YES",
        "PRESENTATION_MODE_FROZEN=YES",
        "ENGINEERING_REVIEW_MODE_FROZEN=YES",
        "MOBILE_PREVIEW_PROFILE_FROZEN=YES",
        "ENGINEERING_SHEET_PROFILE_FROZEN=YES",
        "IMPLEMENTATION_STARTED=NO",
        "P1_AUTHORIZED=NO",
    ):
        assert required in plan
