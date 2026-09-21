"""Durable architecture locks for the V2.2.1 P1C label overlay."""

from __future__ import annotations

import subprocess
from pathlib import Path

from cold_storage.modules.layout.domain.svg_projection import (
    SVG_LABEL_ANCHOR_ORDER,
    SVG_MOBILE_DIMENSION_CODES,
    SVG_PRESENTATION_DIMENSION_CODES,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_MAIN_SHA = "aae74ad71fdedc6b29daf8373f581bb6aa99d81a"
DOMAIN = "backend/src/cold_storage/modules/layout/domain/svg_projection.py"
UNIT = "backend/tests/unit/test_v221_p1c_room_label_collision_annotation.py"
SELF = "backend/tests/architecture/test_v221_p1c_room_label_collision_annotation.py"
DOC = "docs/tasks/V2_2_1-P1C-room-label-collision-annotation.md"
PLAN = "docs/tasks/V2_2-version-plan.md"
ADR = "docs/architecture/ADR-045-layout-drawing-style-projection.md"
ALLOWED_PATHS = {DOMAIN, UNIT, SELF, DOC, PLAN, ADR}
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


def _historical_changed_paths() -> set[str]:
    history = _git("log", "--reverse", "--diff-filter=A", "--format=%H", "HEAD", "--", SELF)
    targets = history.splitlines()
    if not targets:
        return set(_git("diff", "--name-only", BASE_MAIN_SHA, "HEAD").splitlines())
    target = targets[0]
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", target, "HEAD"],
        cwd=REPO_ROOT,
        check=True,
    )
    return set(_git("diff", "--name-only", BASE_MAIN_SHA, target).splitlines())


def test_p1c_scope_is_projection_only_and_uses_immutable_history() -> None:
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_MAIN_SHA, "HEAD"],
        cwd=REPO_ROOT,
        check=True,
    )
    changed = _historical_changed_paths()
    assert changed <= ALLOWED_PATHS
    assert not any(path.startswith(PROTECTED_PREFIXES) for path in changed)


def test_p1c_label_and_debug_visibility_contract_is_versioned() -> None:
    source = _source(DOMAIN)
    document = _source(DOC)
    for required in (
        "SVG_LABEL_FONT_SIZE",
        "SVG_LABEL_ANCHOR_ORDER",
        "_build_room_label_plan",
        "ROOM_LABEL_WALL_CROSSING_COUNT",
        "ROOM_LABEL_PRIMARY_COLLISION_COUNT",
        "ROOM_LABEL_NUMERIC_ID_COUNT",
        "internal_zone_code_visible",
        "portal_debug_text_visible",
        "schema_identity_visible",
        "_dimension_codes_for_profile",
        "data-label-mode",
    ):
        assert required in source
    for required in (
        "TASK_ID=V2_2_1_P1C_ROOM_LABEL_COLLISION_ANNOTATION_R1",
        "P1C_AUTHORIZED=YES",
        "LABEL_FALLBACK_ORDER=3_LINES>2_LINES>1_LINE>NUMERIC_ID",
        "ROOM_LABEL_WALL_CROSSING_COUNT=0",
        "ROOM_LABEL_PRIMARY_COLLISION_COUNT=0",
        "INTERNAL_ZONE_CODE_VISIBLE=false",
        "SOURCE_HASH_VISIBLE=false",
        "P2_CHANGED=NO",
        "P2D_CHANGED=NO",
        "P4_CHANGED=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    ):
        assert required in document


def test_presentation_dimension_policy_is_narrower_than_review() -> None:
    assert SVG_PRESENTATION_DIMENSION_CODES == (
        "primary_precooling_room",
        "secondary_precooling_room",
        "sorting_packaging_room",
        "shipping_channel",
    )
    assert SVG_MOBILE_DIMENSION_CODES == ()
    assert SVG_LABEL_ANCHOR_ORDER == ("CENTER", "TOP", "BOTTOM", "LEFT", "RIGHT")


def test_p1c_does_not_introduce_geometry_or_runtime_dependencies() -> None:
    source = _source(DOMAIN)
    assert "route_site_placement" not in source
    assert "calculate_" not in source
    assert "MCP" not in source
    assert "frontend" not in source.lower()
    assert "SVG_LABEL_WALL_CLEARANCE" in source
    assert "SVG_LABEL_PORTAL_CLEARANCE" in source
