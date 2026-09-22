"""Architecture locks for the independent V2.2.1 P1D drawing lint layer."""

from __future__ import annotations

import subprocess
from pathlib import Path

from cold_storage.modules.layout.domain.drawing_lint import (
    DRAWING_LINT_GATE_VALUES,
    DRAWING_LINT_IDENTITY,
    DRAWING_LINT_PROFILES,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_MAIN_SHA = "27400de6934fd6bf8a307ac1e4ce3786a959e331"
DOMAIN = "backend/src/cold_storage/modules/layout/domain/drawing_lint.py"
APPLICATION = "backend/src/cold_storage/modules/layout/application/drawing_lint.py"
PROJECTION = "backend/src/cold_storage/modules/layout/domain/svg_projection.py"
UNIT = "backend/tests/unit/test_v221_p1d_drawing_lint.py"
SELF = "backend/tests/architecture/test_v221_p1d_drawing_lint.py"
DOC = "docs/tasks/V2_2_1-P1D-drawing-lint-foundation.md"
ALLOWED_PATHS = {DOMAIN, APPLICATION, PROJECTION, UNIT, SELF, DOC}
PROTECTED_PREFIXES = (
    "backend/src/cold_storage/modules/calculations/",
    "backend/src/cold_storage/modules/layout/application/access_routing.py",
    "backend/src/cold_storage/modules/layout/application/placement.py",
    "backend/src/cold_storage/modules/layout/domain/access_routing.py",
    "backend/src/cold_storage/modules/layout/domain/placement.py",
    "backend/src/cold_storage/modules/layout/domain/site_geometry.py",
    "frontend/",
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


def test_p1d_scope_is_independent_and_immutable_history_based() -> None:
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_MAIN_SHA, "HEAD"],
        cwd=REPO_ROOT,
        check=True,
    )
    changed = _historical_changed_paths()
    assert changed <= ALLOWED_PATHS
    assert not any(path.startswith(PROTECTED_PREFIXES) for path in changed)
    current_changed = set(_git("diff", "--name-only", BASE_MAIN_SHA, "HEAD").splitlines())
    assert current_changed <= ALLOWED_PATHS
    assert not any(path.startswith(PROTECTED_PREFIXES) for path in current_changed)


def test_drawing_lint_identity_profiles_and_gate_are_versioned() -> None:
    source = _source(DOMAIN)
    document = _source(DOC)
    assert DRAWING_LINT_IDENTITY == "drawing-lint@1.0.0"
    assert DRAWING_LINT_GATE_VALUES == ("PASS", "FAIL")
    assert DRAWING_LINT_PROFILES == (
        "PRESENTATION",
        "MOBILE_PREVIEW",
        "ENGINEERING_SHEET",
        "ENGINEERING_REVIEW",
    )
    for required in (
        "DrawingLintIssueV1",
        "DrawingLintReportV1",
        "lint_drawing_projection",
        "drawing_lint_gate",
        "ERROR",
        "WARNING",
        "INFO",
        "ROOM_LABEL_WALL_CROSSING_COUNT",
        "ROOM_LABEL_LABEL_OVERLAP_COUNT",
        "ROOM_LABEL_DIMENSION_COLLISION_COUNT",
        "ROOM_LABEL_PORTAL_COLLISION_COUNT",
        "CALLOUT_LABEL_COLLISION_COUNT",
        "CALLOUT_LEADER_SELF_INTERSECTION_COUNT",
        "CALLOUT_LEADER_LABEL_INTERSECTION_COUNT",
        "CALLOUT_OUT_OF_PAGE_COUNT",
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
        "canonical_lint_hash",
        "DrawingLintMetricEvidenceV1",
        "DRAWING_LINT_EVIDENCE_STATUSES",
        "MEASURED",
        "DERIVED",
        "NOT_APPLICABLE",
        "UNAVAILABLE",
        "DRAWING_LINT_REQUIRED_FACT_UNAVAILABLE",
        "MISSING_FACT_IS_ZERO",
        "MISSING_FACT_IS_FALSE",
        "MISSING_REQUIRED_FACT_FAILS_CLOSED",
        "EVIDENCE_STATUS_HASHED",
        "EVIDENCE_SOURCE_HASHED",
        "unavailable_required_fact_count",
        "metric_evidence",
        "required_fact_count",
        "measured_fact_count",
        "derived_fact_count",
        "not_applicable_fact_count",
    ):
        assert required in source
    for required in (
        "TASK_ID=V2_2_1_P1D_DRAWING_LINT_FOUNDATION_R1",
        "DRAWING_LINT_IDENTITY=drawing-lint@1.0.0",
        "DRAWING_LINT_GATE=PASS|FAIL",
        "DRAWING_LINT_IS_ENGINEERING_AUTHORITY=false",
        "SVG_BYTES_CHANGED=false",
        "SVG_HASH_CHANGED=false",
        "P1E_AUTHORIZED=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
        "MISSING_FACT_IS_ZERO=false",
        "MISSING_REQUIRED_FACT_FAILS_CLOSED=true",
        "SVG_VISUAL_OUTPUT_CHANGED=false",
    ):
        assert required in document


def test_required_fact_policy_and_sidecar_are_fail_closed() -> None:
    domain = _source(DOMAIN)
    projection = _source(PROJECTION)
    assert "_BASE_REQUIRED_FACTS" in domain
    assert "_CALLOUT_REQUIRED_FACTS" in domain
    assert 'status="UNAVAILABLE"' in domain
    assert "DRAWING_LINT_REQUIRED_FACT_UNAVAILABLE" in domain
    assert "_drawing_lint_sidecar" in projection
    assert '"drawing_lint_facts": drawing_lint_facts' in projection
    metadata_source = projection.split("metadata =", 1)[1].split("defs =", 1)[0]
    assert "drawing_lint_facts" not in metadata_source


def test_callout_leader_intersections_use_other_label_boxes_only() -> None:
    domain = _source(DOMAIN)
    assert "for other_id, other_box in label_by_id.items()" in domain
    assert "if other_id == own_label_id:" in domain
    assert '"Callout label overlaps another label."' in domain
    assert '"Callout leader intersects another label."' in domain


def test_lint_layer_does_not_depend_on_rendering_or_engineering_runtime() -> None:
    domain = _source(DOMAIN)
    application = _source(APPLICATION)
    for forbidden in (
        "route_site_placement",
        "place_zones",
        "calculate_",
        "MCP",
        "frontend",
        "fastapi",
        "sqlalchemy",
    ):
        assert forbidden not in domain.lower()
        assert forbidden not in application.lower()
    assert "ValidatedLayoutSvgProjectionV1" in application
    assert ".to_dict()" in application
    assert "build_projection_payload" not in application
