"""Durable architecture locks for the V2.1.1 patch release closure."""

from __future__ import annotations

import subprocess
from pathlib import Path

from cold_storage.modules.aily.api.mcp_sse import _PREVIEW_TOOL_ORDER
from cold_storage.modules.calculations.domain.zone_planning import FORMULA_AUTHORITY
from cold_storage.modules.orchestration.domain.contracts import CalculationType

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_RELEASE_SHA = "2221077d4ebe0ee90e218b8869ccb3bb000b1d60"
PATCH_TARGET_SHA = "c3f4be969bfbc65531c38338e3712355e74b6776"

# This is an immutable candidate snapshot, created before this architecture
# test was added.  The scope guard uses it as the historical diff target and
# checks only that it remains an ancestor of later repository heads.
CLOSURE_SCOPE_BASE_SHA = PATCH_TARGET_SHA
CLOSURE_SCOPE_SNAPSHOT_SHA = "96854d0c9a19321355794da874329871592978c4"

CLOSURE_PATH = REPO_ROOT / "docs/tasks/V2_1_1-patch-release-closure-readiness.md"
REGRESSION_PATH = REPO_ROOT / "backend/tests/unit/test_post_v21_effective_working_hours_14h.py"

ALLOWED_CLOSURE_SCOPE_PATHS = {
    "backend/tests/architecture/test_v211_patch_release_closure_readiness.py",
    "docs/tasks/V2_1_1-patch-release-closure-readiness.md",
}
FROZEN_SCOPE_PREFIXES = (
    "backend/src",
    "frontend/src",
    "backend/alembic",
    ".github/workflows",
    "deployment",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_ancestor(ancestor: str, descendant: str = "HEAD") -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, f"{ancestor} must be an ancestor of {descendant}"


def _historical_changed_paths() -> set[str]:
    _assert_ancestor(CLOSURE_SCOPE_SNAPSHOT_SHA)
    output = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            CLOSURE_SCOPE_BASE_SHA,
            CLOSURE_SCOPE_SNAPSHOT_SHA,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {path.strip() for path in output.splitlines() if path.strip()}


def test_v211_patch_lineage_and_v210_tag_are_immutable() -> None:
    _assert_ancestor(BASE_RELEASE_SHA)
    _assert_ancestor(PATCH_TARGET_SHA)
    release_target = subprocess.run(
        ["git", "rev-parse", "v2.1.0^{}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert release_target == BASE_RELEASE_SHA

    closure = _text(CLOSURE_PATH)
    for marker in (
        "BASE_RELEASE=v2.1.0",
        f"BASE_RELEASE_SHA={BASE_RELEASE_SHA}",
        f"PATCH_TARGET_SHA={PATCH_TARGET_SHA}",
        "SOURCE_PR=264",
        "MAIN_CI_RUN_ID=34462264950",
        "MAIN_CI_RESULT=SUCCESS",
        "MAIN_CI_SHA_MATCH=YES",
        "V2_1_0_TAG_TARGET_IMMUTABLE=YES",
        "ORIGIN_MAIN_HEAD_EQUALITY_USED=NO",
    ):
        assert marker in closure


def test_v211_closure_scope_uses_immutable_candidate_snapshot() -> None:
    changed = _historical_changed_paths()
    assert changed <= ALLOWED_CLOSURE_SCOPE_PATHS
    assert not any(
        path == prefix or path.startswith(prefix + "/")
        for path in changed
        for prefix in FROZEN_SCOPE_PREFIXES
    )

    closure = _text(CLOSURE_PATH)
    assert f"CLOSURE_SCOPE_BASE_SHA={CLOSURE_SCOPE_BASE_SHA}" in closure
    assert f"CLOSURE_SCOPE_SNAPSHOT_SHA={CLOSURE_SCOPE_SNAPSHOT_SHA}" in closure
    assert "CLOSURE_SCOPE_TARGET_IS_IMMUTABLE=YES" in closure
    assert "CLOSURE_SCOPE_CHECKS_CURRENT_HEAD_FOR_LINEAGE_ONLY=YES" in closure
    assert "origin/main" not in closure


def test_v211_patch_regression_and_formula_authority_are_present() -> None:
    assert REGRESSION_PATH.exists()
    regression = _text(REGRESSION_PATH)
    for marker in (
        'FORMULA_AUTHORITY == "POST-V0.9-P4-charles-zone-area-recut"',
        'secondary["working_hours_per_day"] == 14',
        'secondary["position_daily_capacity_kg_day"] == 2800',
        'planning_parameters["secondary_precooling_q_d_kg_day"] == 2800',
        'sorting["person_daily_capacity_kg_day"] == 336',
        'planning_parameters["packing_person_daily_capacity_kg"] == 336',
        'sorting["required_area_m2"] == pytest.approx(565.76',
        'result.result["total_area_m2"] == pytest.approx(2138.01',
        "packing_working_hours_per_day=10",
    ):
        assert marker in regression
    assert FORMULA_AUTHORITY == "POST-V0.9-P4-charles-zone-area-recut"


def test_v211_mcp_and_calculation_type_boundaries_are_unchanged() -> None:
    assert len(_PREVIEW_TOOL_ORDER) == 6
    assert _PREVIEW_TOOL_ORDER[-1] == "preview_factory_power"
    assert len(CalculationType) == 5

    closure = _text(CLOSURE_PATH)
    for marker in (
        "FACTORY_POWER_CALCULATOR=factory_power_estimation@2.0.0-p1",
        "MCP_TOOL_COUNT=6",
        "MCP_CONTRACT_CHANGED=NO",
        "DOUBAO_SKILL_CHANGED=NO",
        "DATABASE_MIGRATION_CHANGED=NO",
        "DEPLOYMENT_CHANGED=NO",
        "V2_1_1_IMPLEMENTATION_COMPLETE=YES",
        "V2_1_1_RELEASE_CANDIDATE=YES",
        "V2_1_1_RELEASE_READY=YES",
        "TAG_CREATION_AUTHORIZED=NO",
        "GITHUB_RELEASE_CREATION_AUTHORIZED=NO",
        "DEPLOYMENT_AUTHORIZED=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    ):
        assert marker in closure
