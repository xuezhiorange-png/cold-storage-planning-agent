"""Scope and authority locks for P0C Golden layout evidence."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
P0C_BASE = "9bc00b6157bb549f1fd3c7112cfc30f29452b8e0"
EVIDENCE_REL = Path("docs/tasks/evidence/v2_2_2_p0c")
EVIDENCE = ROOT / EVIDENCE_REL
ALLOWED_PATHS = {
    "backend/tests/architecture/test_v222_p0c_golden_layout_abstraction.py",
    "backend/tests/evaluation/test_v222_p0c_golden_layout_abstraction.py",
    "backend/tests/evaluation/v222_p0c_golden_layout_metrics.py",
    "backend/tests/evaluation/render_v222_p0c_overlay_review_pack.py",
    "docs/architecture/ADR-047-process-flow-layout-regularity-authority.md",
    "docs/tasks/V2_2-version-plan.md",
    "docs/tasks/V2_2_2-P0-process-flow-layout-regularity-contract.md",
    "docs/tasks/V2_2_2-P0C-golden-layout-abstraction-and-calibration.md",
    str(EVIDENCE_REL / "GD-001_ZHUYUAN.normalized-layout.json"),
    str(EVIDENCE_REL / "GD-002_XIAOXIANG.normalized-layout.json"),
    str(EVIDENCE_REL / "GD-003_MOUDING.normalized-layout.json"),
    str(EVIDENCE_REL / "GD-004_SHUANGLONGYING.normalized-layout.json"),
    str(EVIDENCE_REL / "GD-005_PANLONG.normalized-layout.json"),
    str(EVIDENCE_REL / "calibration-matrix.json"),
    str(EVIDENCE_REL / "overlay-review-pack.json"),
    str(EVIDENCE_REL / "gd-001-zhuyuan-normalized-overlay.png"),
    str(EVIDENCE_REL / "gd-002-xiaoxiang-normalized-overlay.png"),
    str(EVIDENCE_REL / "gd-003-mouding-normalized-overlay.png"),
    str(EVIDENCE_REL / "gd-004-shuanglongying-normalized-overlay.png"),
    str(EVIDENCE_REL / "gd-005-panlong-normalized-overlay.png"),
}
REFERENCE_FILES = sorted(EVIDENCE.glob("GD-*.normalized-layout.json"))


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _changed_paths() -> set[str]:
    # Scope is about files included in the PR, not test-run artifacts created
    # in the checkout (for example backend/artifacts/local reports).
    return set(_git("diff", "--name-only", P0C_BASE, "HEAD").splitlines())


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_p0c_is_limited_to_offline_evidence_docs_and_tests() -> None:
    subprocess.run(["git", "merge-base", "--is-ancestor", P0C_BASE, "HEAD"], cwd=ROOT, check=True)
    assert _changed_paths() == ALLOWED_PATHS
    for forbidden in ("backend/src/", "frontend/", "database/", "backend/alembic/"):
        assert not any(path.startswith(forbidden) for path in _changed_paths())


def test_release_and_layout_runtime_are_unchanged() -> None:
    subprocess.run(["git", "diff", "--quiet", P0C_BASE, "--", "backend/src"], cwd=ROOT, check=True)
    subprocess.run(
        ["git", "diff", "--quiet", "64f335bbfbbaf061b9ba08c18f2068db411f8922", "--", "backend/src"],
        cwd=ROOT,
        check=True,
    )
    p0c_doc_path = ROOT / "docs/tasks/V2_2_2-P0C-golden-layout-abstraction-and-calibration.md"
    p0c_doc = p0c_doc_path.read_text(encoding="utf-8")
    assert "RUNTIME_IMPLEMENTATION_AUTHORIZED=false" in p0c_doc
    assert "P1_IMPLEMENTATION_ENTRY_READY=false" in p0c_doc


def test_five_references_and_one_negative_are_non_authoritative() -> None:
    refs = [_json(path) for path in REFERENCE_FILES]
    assert len(refs) == 5
    assert {ref["owner_label"] for ref in refs} == {"PASS"}
    for ref in refs:
        assert ref["reference_derived"] is True
        assert ref["engineering_authority"] is False
        assert ref["runtime_project_input"] is False
        assert ref["normalization_version"] == "1.0.0"
        assert ref["normalization"]["real_dimensions_recorded"] is False
        assert ref["room_level_geometry_available"] is False
        assert ref["route_backtrack_turn_metrics"] == "UNAVAILABLE_NO_AUTHORITATIVE_ROUTE_TRACE"

    matrix = _json(EVIDENCE / "calibration-matrix.json")
    rows = matrix["fixtures"]
    positives = [row for row in rows if row["owner_label"] == "PASS"]
    negatives = [row for row in rows if row["owner_label"] == "FAIL"]
    assert len(positives) == 5
    assert len(negatives) == 1
    assert negatives[0]["fixture_id"] == "XINZHAO_20T_SITE_LAYOUT_INPUT_V3_OWNER_ACCEPTANCE"
    assert negatives[0]["project_layout_validated"] is True
    assert negatives[0]["grid_alignment_rate"] == "0.4"
    assert negatives[0]["depth_alignment_rate"] == "UNAVAILABLE"


def test_outline_classifier_and_metric_unavailability_are_explicit() -> None:
    report_path = ROOT / "docs/tasks/V2_2_2-P0C-golden-layout-abstraction-and-calibration.md"
    report = report_path.read_text(encoding="utf-8")
    for class_name in (
        "RECTANGLE",
        "SIMPLE_L",
        "COMPLEX_L",
        "IRREGULAR_SITE_CONSTRAINED",
        "STAIR_STEP",
        "NARROW_NECK",
        "ISOLATED_APPENDAGE",
        "MULTI_COMPONENT",
        "AMBIGUOUS_REQUIRES_OWNER_REVIEW",
    ):
        assert class_name in report
    assert "`EXTERIOR_NOTCH_COUNT` is different" in report
    matrix = _json(EVIDENCE / "calibration-matrix.json")
    assert matrix["threshold_assessment"]["grid_alignment"]["status"] == "NOT_READY"
    assert matrix["threshold_assessment"]["depth_alignment"]["status"] == "NOT_READY"
    assert matrix["threshold_assessment"]["bounding_rectangle_occupancy"]["status"] == "NOT_READY"


def test_structural_and_numeric_entry_are_separate_and_no_release_authority() -> None:
    matrix = _json(EVIDENCE / "calibration-matrix.json")
    entry = matrix["entry_readiness"]
    assert entry["p1a_structural_implementation_entry_ready"] is True
    assert entry["p1b_numeric_threshold_implementation_entry_ready"] is False
    assert entry["p1_implementation_entry_ready"] is False
    assert entry["implementation_authorized"] is False
    assert len(entry["blocking_numeric_items"]) >= 3
    assert "GOLDEN_ENGINEERING_AUTHORITY=false" in (
        ROOT / "docs/architecture/ADR-047-process-flow-layout-regularity-authority.md"
    ).read_text(encoding="utf-8") or "engineering authority" in (
        ROOT / "docs/tasks/V2_2_2-P0C-golden-layout-abstraction-and-calibration.md"
    ).read_text(encoding="utf-8")


def test_overlay_pack_contains_five_viewable_pngs_without_original_pdf_assets() -> None:
    manifest = _json(EVIDENCE / "overlay-review-pack.json")
    assert manifest["abstraction_visual_overlay_created"] is True
    assert manifest["owner_visual_review"] == "PENDING"
    assert manifest["original_pdf_bytes_committed"] is False
    assert len(manifest["overlays"]) == 5
    assert "combined_pdf" not in manifest
    for item in manifest["overlays"]:
        path = EVIDENCE / item["png"]
        assert path.is_file() and path.stat().st_size > 0
