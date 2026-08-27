"""Architecture tests for V0.9 P6 operator sample and runbook contract."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
P6_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_9-P6-operator-sample-runbook-contract.md"
P0_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_9-P0-version-contract.md"
V09_LOADER = REPO_ROOT / "backend/src/cold_storage/bootstrap/v09_sample_loader.py"
V09_MANIFEST = REPO_ROOT / "samples/v09-process-input/manifest.json"
ZONE_PLANNING = REPO_ROOT / "backend/src/cold_storage/modules/calculations/domain/zone_planning.py"
COOLING_LOAD = REPO_ROOT / "backend/src/cold_storage/modules/calculations/domain/cooling_load.py"

P0_P6_MANIFEST_ALIAS = (
    "samples/v09-process-input/**",
    "samples/v09-process-input/manifest.json",
)

P6_ALLOWLIST = (
    "docs/tasks/V0_9-P6-operator-sample-runbook-contract.md",
    "samples/v09-process-input/manifest.json",
    "backend/src/cold_storage/bootstrap/v09_sample_loader.py",
    "docs/runbooks/v09-process-input-runbook.md",
    "Makefile",
    "backend/tests/integration/v09_p6_operator_fixtures.py",
    "backend/tests/integration/test_v09_p6_operator_sample_sqlite.py",
    "backend/tests/integration/test_v09_p6_operator_sample_postgresql.py",
    "backend/tests/architecture/test_v09_p6_operator_sample_contract.py",
    "backend/tests/integration/test_audit_outbox_postgresql.py",
)

_INTERESTING_PREFIXES = (
    "docs/",
    "backend/src/",
    "backend/tests/",
    "frontend/src/",
)


def _current_branch_name() -> str:
    head_ref = os.environ.get("GITHUB_HEAD_REF")
    if head_ref:
        return head_ref
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _on_p6_branch() -> bool:
    return "v09-p6-operator" in _current_branch_name()


def _extract_allowlist_paths(contract: str, marker: str) -> set[str]:
    start = contract.index(marker)
    fence_start = contract.rfind("```", 0, start)
    fence_end = contract.index("```", start)
    block = contract[fence_start + 3 : fence_end].strip()
    if block.startswith("text"):
        block = block.split("\n", 1)[1].strip()
    paths: set[str] = set()
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped == marker:
            continue
        paths.add(stripped)
    return paths


def _changed_interesting_paths() -> set[str]:
    diff = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    names = {line.strip() for line in diff.stdout.splitlines() if line.strip()}
    names |= {line.strip() for line in untracked.stdout.splitlines() if line.strip()}
    return {name for name in names if name.startswith(_INTERESTING_PREFIXES)}


def test_p6_contract_exists_and_flags() -> None:
    assert P6_CONTRACT.is_file()
    text = P6_CONTRACT.read_text(encoding="utf-8")
    assert "BASE_MAIN_SHA=567732f7079ad04a9e53a585f5f40d208bf6f999" in text
    assert "V09_P6_IMPLEMENTATION_AUTHORIZED=YES" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "AILY_LIVE_IMPLEMENTATION=NO" in text
    assert "v09-process-input" in text


def test_p0_p6_paths_are_subset_of_p6_allowlist_after_manifest_alias() -> None:
    p0 = P0_CONTRACT.read_text(encoding="utf-8")
    p0_paths = _extract_allowlist_paths(p0, "V09_P6_FILE_ALLOWLIST")
    glob_path, manifest_path = P0_P6_MANIFEST_ALIAS
    aliased_p0_paths = (p0_paths - {glob_path}) | {manifest_path}
    assert aliased_p0_paths <= set(P6_ALLOWLIST)


def test_p6_allowlist_matches_contract_and_files_exist() -> None:
    p6 = P6_CONTRACT.read_text(encoding="utf-8")
    p6_paths = _extract_allowlist_paths(p6, "V09_P6_FILE_ALLOWLIST")
    assert set(P6_ALLOWLIST) == p6_paths
    for path in P6_ALLOWLIST:
        assert (REPO_ROOT / path).is_file(), path


def test_p6_manifest_five_key_only_no_bundle() -> None:
    import json

    manifest = json.loads(V09_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["sample_id"] == "v09-process-input"
    assert "engineering_input_bundle" not in manifest
    operator_input = manifest["operator_process_input"]
    assert operator_input["schema_version"] == "1.1.0"
    zone_inputs = operator_input["zone_planning_inputs"]
    assert set(zone_inputs) == {
        "daily_inbound_mass_kg",
        "finished_storage_days",
        "frozen_storage_days",
        "main_packaging_storage_days",
        "auxiliary_packaging_storage_days",
    }
    for forbidden in (
        "working_time_h_per_day",
        "packaging_storage_days",
        "precooling_required_ratio",
    ):
        assert forbidden not in zone_inputs


def test_p6_loader_does_not_edit_zone_planning_or_cooling_load() -> None:
    loader = V09_LOADER.read_text(encoding="utf-8")
    assert "zone_planning.py" not in loader
    assert "cooling_load.py" not in loader


@pytest.mark.skipif(
    not _on_p6_branch(),
    reason=("P6 allowlist diff only enforced on branches whose name contains v09-p6-operator"),
)
def test_p6_diff_stays_on_allowlist() -> None:
    changed = _changed_interesting_paths()
    allowlist = set(P6_ALLOWLIST)
    extra = sorted(changed - allowlist)
    assert extra == [], f"P6 diff off allowlist: {extra}"


@pytest.mark.skipif(
    not _on_p6_branch(),
    reason=("P6 formula-file freeze only enforced on branches whose name contains v09-p6-operator"),
)
def test_p6_diff_does_not_edit_zone_planning_or_cooling_load() -> None:
    changed = _changed_interesting_paths()
    forbidden_formula_files = {
        str(ZONE_PLANNING.relative_to(REPO_ROOT)),
        str(COOLING_LOAD.relative_to(REPO_ROOT)),
    }
    assert forbidden_formula_files.isdisjoint(changed)
