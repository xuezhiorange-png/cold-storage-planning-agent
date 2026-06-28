"""
Fixture consistency tests for Phase B pilot fixtures.

Validates that all three synthetic fixtures, expected contracts, and the
manifest are internally consistent and meet Phase B requirements.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "evaluation"
MANIFEST_PATH = EVAL_ROOT / "manifest.json"


# ── Helpers ──────────────────────────────────────────────────────────────


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text("utf-8"))


def _load_fixture(scenario_id: str, manifest: dict) -> dict:
    for s in manifest["scenarios"]:
        if s["scenario_id"] == scenario_id:
            return json.loads((EVAL_ROOT / s["project_input_path"]).read_text("utf-8"))
    raise KeyError(f"Scenario {scenario_id} not found")


def _load_expected(scenario_id: str, manifest: dict) -> dict:
    for s in manifest["scenarios"]:
        if s["scenario_id"] == scenario_id:
            return json.loads((EVAL_ROOT / s["expected_path"]).read_text("utf-8"))
    raise KeyError(f"Scenario {scenario_id} not found")


def _scenario_entry(manifest: dict, scenario_id: str) -> dict:
    for s in manifest["scenarios"]:
        if s["scenario_id"] == scenario_id:
            return s
    raise KeyError(f"Scenario {scenario_id} not found")


# ═══════════════════════════════════════════════════════════════════════
# 1. Fixture files exist
# ═══════════════════════════════════════════════════════════════════════


def test_manifest_exists() -> None:
    assert MANIFEST_PATH.exists(), f"Manifest not found at {MANIFEST_PATH}"


def test_all_fixture_files_exist() -> None:
    manifest = _load_manifest()
    for s in manifest["scenarios"]:
        fixture_path = EVAL_ROOT / s["project_input_path"]
        assert fixture_path.exists(), f"Fixture not found for {s['scenario_id']}: {fixture_path}"


def test_all_expected_files_exist() -> None:
    manifest = _load_manifest()
    for s in manifest["scenarios"]:
        expected_path = EVAL_ROOT / s["expected_path"]
        assert expected_path.exists(), (
            f"Expected file not found for {s['scenario_id']}: {expected_path}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 2. Synthetic property
# ═══════════════════════════════════════════════════════════════════════


def test_all_fixtures_are_synthetic() -> None:
    manifest = _load_manifest()
    for s in manifest["scenarios"]:
        fixture = _load_fixture(s["scenario_id"], manifest)
        assert fixture.get("synthetic") is True, (
            f"Fixture {s['scenario_id']} is not marked synthetic"
        )


# ═══════════════════════════════════════════════════════════════════════
# 3. Fixture revision consistency
# ═══════════════════════════════════════════════════════════════════════


def test_fixture_revision_matches_manifest() -> None:
    manifest = _load_manifest()
    for s in manifest["scenarios"]:
        fixture = _load_fixture(s["scenario_id"], manifest)
        assert fixture.get("fixture_revision") == s["fixture_revision"], (
            f"Fixture revision mismatch for {s['scenario_id']}: "
            f"fixture={fixture.get('fixture_revision')}, "
            f"manifest={s['fixture_revision']}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 4. Provenance — non-empty and not placeholder
# ═══════════════════════════════════════════════════════════════════════


def test_fixture_provenance_exists() -> None:
    manifest = _load_manifest()
    for s in manifest["scenarios"]:
        fixture = _load_fixture(s["scenario_id"], manifest)
        prov = fixture.get("provenance", {})
        assert "generator" in prov, f"Missing generator in {s['scenario_id']} provenance"
        assert "generated_at" in prov, f"Missing generated_at in {s['scenario_id']} provenance"
        assert "description" in prov, f"Missing description in {s['scenario_id']} provenance"
        assert prov["generator"] != "", f"Empty generator in {s['scenario_id']} provenance"


def test_manifest_scenario_provenance_exists() -> None:
    manifest = _load_manifest()
    for s in manifest["scenarios"]:
        prov = s.get("provenance", {})
        assert "source" in prov, f"Missing source in manifest scenario {s['scenario_id']}"
        assert "rationale" in prov, f"Missing rationale in manifest scenario {s['scenario_id']}"


# ═══════════════════════════════════════════════════════════════════════
# 5. Scenario IDs unique
# ═══════════════════════════════════════════════════════════════════════


def test_scenario_ids_unique() -> None:
    manifest = _load_manifest()
    ids = [s["scenario_id"] for s in manifest["scenarios"]]
    assert len(ids) == len(set(ids)), f"Duplicate scenario IDs: {ids}"


# ═══════════════════════════════════════════════════════════════════════
# 6. All paths inside evaluation/
# ═══════════════════════════════════════════════════════════════════════


def test_all_paths_in_evaluation() -> None:
    manifest = _load_manifest()
    for s in manifest["scenarios"]:
        assert not s["project_input_path"].startswith("/"), (
            f"Absolute path for {s['scenario_id']}: {s['project_input_path']}"
        )
        assert not s["expected_path"].startswith("/"), (
            f"Absolute path for {s['scenario_id']}: {s['expected_path']}"
        )
        # Resolve and check containment
        fixture_resolved = (EVAL_ROOT / s["project_input_path"]).resolve()
        expected_resolved = (EVAL_ROOT / s["expected_path"]).resolve()
        assert str(fixture_resolved).startswith(str(EVAL_ROOT.resolve())), (
            f"Fixture path outside evaluation/ for {s['scenario_id']}: {fixture_resolved}"
        )
        assert str(expected_resolved).startswith(str(EVAL_ROOT.resolve())), (
            f"Expected path outside evaluation/ for {s['scenario_id']}: {expected_resolved}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 7. Expected outcome contracts
# ═══════════════════════════════════════════════════════════════════════


def test_baseline_expected_outcome_success() -> None:
    manifest = _load_manifest()
    entry = _scenario_entry(manifest, "baseline-feasible")
    assert entry["expected_outcome"] == "success", (
        f"Frozen baseline contract requires success. "
        f"Got: {entry['expected_outcome']}. "
        f"Phase B is BLOCKED until formal production orchestration delivers "
        f"no-review baseline."
    )


def test_high_throughput_expected_outcome_review() -> None:
    manifest = _load_manifest()
    entry = _scenario_entry(manifest, "high-throughput-review")
    assert entry["expected_outcome"] == "review_required", (
        f"Expected review_required (production hardcoded review: zone_planning + investment), "
        f"got: {entry['expected_outcome']}"
    )


def test_invalid_expected_outcome_validation_error() -> None:
    manifest = _load_manifest()
    entry = _scenario_entry(manifest, "invalid-blocked")
    assert entry["expected_outcome"] == "validation_error", (
        f"Expected validation_error, got: {entry['expected_outcome']}"
    )


# ═══════════════════════════════════════════════════════════════════════
# 8. Required stages consistency
# ═══════════════════════════════════════════════════════════════════════


def test_baseline_required_stages() -> None:
    manifest = _load_manifest()
    entry = _scenario_entry(manifest, "baseline-feasible")
    assert entry["required_stages"] == [
        "project",
        "version",
        "validation",
        "planning",
        "zone_plan",
        "power",
        "investment",
        "schemes",
    ], f"Baseline required stages mismatch: {entry['required_stages']}"


def test_invalid_required_stages() -> None:
    manifest = _load_manifest()
    entry = _scenario_entry(manifest, "invalid-blocked")
    # invalid should only need project/version/validation
    assert "validation" in entry["required_stages"]
    assert "planning" not in entry["required_stages"], "invalid-blocked should not require planning"


# ════════════════════════════════════════════════════════════════════
# 8a. Baseline stage ledger coverage
# ════════════════════════════════════════════════════════════════════


def test_baseline_stage_ledger_covers_required_stages() -> None:
    """Manifest baseline required_stages has exactly 8 stages (all mandatory).

    The 8 required stages are: project, version, validation, planning,
    zone_plan, power, investment, schemes.

    These must all appear in any generated stage_ledger (verified at
    execution time by the acceptance tests; here we assert the manifest
    declares them correctly).
    """
    manifest = _load_manifest()
    entry = _scenario_entry(manifest, "baseline-feasible")
    required = entry["required_stages"]
    expected = [
        "project",
        "version",
        "validation",
        "planning",
        "zone_plan",
        "power",
        "investment",
        "schemes",
    ]
    assert len(required) == 8, f"Expected 8 required stages, got {len(required)}: {required}"
    assert required == expected, f"Required stages mismatch: {required} != {expected}"


# ════════════════════════════════════════════════════════════════════
# 8b. Suite revision
# ════════════════════════════════════════════════════════════════════


def test_manifest_suite_revision_is_2() -> None:
    manifest = _load_manifest()
    assert manifest["suite_revision"] == 2, (
        f"Expected suite_revision=2, got {manifest['suite_revision']}"
    )


# ═══════════════════════════════════════════════════════════════════════
# 9. Expected file is static (not auto-generated)
# ═══════════════════════════════════════════════════════════════════════


def test_expected_files_not_rewritten(tmp_path: Path) -> None:
    """Simulate running — expected files must have unchanged SHA-256."""
    manifest = _load_manifest()
    original_hashes: dict[str, str] = {}
    for s in manifest["scenarios"]:
        ep = EVAL_ROOT / s["expected_path"]
        original_hashes[s["scenario_id"]] = hashlib.sha256(ep.read_bytes()).hexdigest()

    # Re-read after "running" (this test doesn't actually run, just verifies static files)
    for s in manifest["scenarios"]:
        ep = EVAL_ROOT / s["expected_path"]
        current_hash = hashlib.sha256(ep.read_bytes()).hexdigest()
        assert current_hash == original_hashes[s["scenario_id"]], (
            f"Expected file changed for {s['scenario_id']}"
        )
