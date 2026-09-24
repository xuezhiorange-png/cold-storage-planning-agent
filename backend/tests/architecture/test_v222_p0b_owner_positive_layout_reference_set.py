"""Architecture and evidence locks for the P0B qualitative reference set."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[3]
P0B_BASE = "7dc2db96f01ae3d835c9a0540a3f226b4aa31aad"
MATRIX_PATH = "docs/tasks/evidence/v2_2_2_p0b/owner-layout-reference-matrix.json"
CONTRACT_PATH = "docs/tasks/V2_2_2-P0-process-flow-layout-regularity-contract.md"
P0B_DOC_PATH = "docs/tasks/V2_2_2-P0B-owner-positive-layout-reference-set.md"
ALLOWED_PATHS = {
    "backend/tests/architecture/test_v222_p0b_owner_positive_layout_reference_set.py",
    "docs/architecture/ADR-047-process-flow-layout-regularity-authority.md",
    "docs/tasks/V2_2-version-plan.md",
    CONTRACT_PATH,
    P0B_DOC_PATH,
    MATRIX_PATH,
}
POSITIVE_IDS = {
    "GD-001_ZHUYUAN",
    "GD-002_XIAOXIANG",
    "GD-003_MOUDING",
    "GD-004_SHUANGLONGYING",
    "GD-005_PANLONG",
}
XINZHAO_SHA256 = "d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _p0b_changed_paths() -> set[str]:
    history = _git(
        "log",
        "--reverse",
        "--diff-filter=A",
        "--format=%H",
        "HEAD",
        "--",
        "backend/tests/architecture/test_v222_p0b_owner_positive_layout_reference_set.py",
    )
    if history:
        p0b_commit = history.splitlines()[0]
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", P0B_BASE, p0b_commit],
            cwd=ROOT,
            check=True,
        )
        return set(_git("diff", "--name-only", f"{P0B_BASE}...{p0b_commit}").splitlines())

    changed = set(_git("diff", "--name-only", P0B_BASE).splitlines())
    changed.update(_git("diff", "--name-only").splitlines())
    changed.update(_git("ls-files", "--others", "--exclude-standard").splitlines())
    return changed


def _matrix() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((ROOT / MATRIX_PATH).read_text(encoding="utf-8")),
    )


def test_p0b_is_limited_to_docs_evidence_and_architecture_test_scope() -> None:
    changed = _p0b_changed_paths()
    assert changed == ALLOWED_PATHS
    assert not any(
        path.startswith(
            (
                "backend/src/",
                "frontend/",
                "database/",
                "backend/alembic/",
                "backend/src/cold_storage/modules/aily/",
            )
        )
        for path in changed
    )


def test_matrix_has_five_owner_positive_sources_and_one_canonical_negative() -> None:
    matrix = _matrix()
    rows = matrix["references"]
    assert isinstance(rows, list)
    positive_rows = [row for row in rows if row["owner_label"] == "PASS"]
    negative_rows = [row for row in rows if row["owner_label"] == "FAIL"]
    assert {row["reference_id"] for row in positive_rows} == POSITIVE_IDS
    assert len(positive_rows) == 5
    assert len(negative_rows) == 1
    assert negative_rows[0]["reference_id"] == "XINZHAO_20T_SITE_LAYOUT_INPUT_V3"
    assert negative_rows[0]["source_sha256"] == XINZHAO_SHA256

    for row in positive_rows:
        assert row["source_available"] is True
        assert len(row["source_sha256"]) == 64
        assert row["reference_role"]
        assert row["qualitative_findings"]
        assert 3 <= len(row["qualitative_findings"]) <= 6
        assert row["main_flow_backtrack_visible"] == "UNAVAILABLE"
        assert row["main_flow_multi_turn_visible"] == "UNAVAILABLE"


def test_positive_rules_and_comparison_remain_qualitative_and_non_authoritative() -> None:
    matrix = _matrix()
    assert matrix["golden_engineering_authority"] is False
    assert matrix["golden_runtime_training_data"] is False
    assert matrix["numeric_threshold_calibration_ready"] is False
    assert matrix["original_golden_source_available"] is True
    assert matrix["original_golden_assets_committed"] is False

    comparison = matrix["positive_vs_xinzhao_negative_comparison"]
    assert isinstance(comparison, list)
    assert len(comparison) == 13
    assert all(
        {"dimension", "positive_pattern", "xinzhao_negative_pattern", "algorithm_implication"}
        <= set(row)
        for row in comparison
    )

    rules = matrix["owner_positive_common_rules"]
    assert isinstance(rules, list)
    assert len(rules) == 5
    for rule in rules:
        assert set(rule["supporting_references"]) == POSITIVE_IDS
        assert rule["rule_type"] in {
            "HARD_CANDIDATE",
            "QUALITY_PRIORITY",
            "SOFT_PREFERENCE",
            "OWNER_REVIEW_ONLY",
        }

    entry = matrix["entry_readiness"]
    assert entry["p1_entry_canonical_fixture_ready"] is True
    assert entry["p1_entry_owner_positive_reference_ready"] is True
    assert entry["p1_entry_layout_rules_ready"] is True
    assert entry["p1_entry_calibration_matrix_ready"] is False
    assert entry["p1_implementation_entry_ready"] is False
    assert entry["depth_alignment_threshold"] == "NOT_READY"
    assert entry["bounding_rectangle_occupancy_floor"] == "NOT_READY"
    assert entry["max_exterior_notch_count"] == "NOT_READY"
    assert entry["max_isolated_appendage_count"] == "NOT_READY"


def test_p0_and_adr_update_preserves_historical_and_implementation_boundaries() -> None:
    contract = (ROOT / CONTRACT_PATH).read_text(encoding="utf-8")
    p0b_doc = (ROOT / P0B_DOC_PATH).read_text(encoding="utf-8")
    adr = (
        ROOT / "docs/architecture/ADR-047-process-flow-layout-regularity-authority.md"
    ).read_text(encoding="utf-8")

    assert "ORIGINAL_GOLDEN_SOURCE_AVAILABLE=false" in contract
    assert "P0B evidence task, Owner supplied the" in contract
    assert "GOLDEN_ENGINEERING_AUTHORITY=false" in p0b_doc
    assert "GOLDEN_RUNTIME_TRAINING_DATA=false" in p0b_doc
    assert "no structured positive layout geometry" in adr
    assert "P1 implementation" in adr
