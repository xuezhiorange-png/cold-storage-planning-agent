"""Architecture locks for the V2.1 P1 upstream authority adapter."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cold_storage.modules.projects.application.factory_power_upstream_authority import (
    EXPECTED_FACTORY_ZONE_CODES,
    REFRIGERATED_ZONE_CODES,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_MAIN_SHA = "1d0a8e23f550b3c9ced413932fde0995acb227c0"
BASE_RELEASE_SHA = "a7049ca93d238013c0cf62069fe1e0a89ff834d7"
# Immutable final commit of the merged P1 branch.  Later P2 changes must not
# be treated as P1 scope or as mutations of P1's frozen surfaces.
P1_REFERENCE_HEAD_SHA = "cfa6d990d5f21327289e73d1ac92654cdc8488a5"
ADAPTER_PATH = (
    "backend/src/cold_storage/modules/projects/application/factory_power_upstream_authority.py"
)
V20_CALCULATOR_PATH = (
    "backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py"
)
V20_PRESENTATION_PATH = (
    "backend/src/cold_storage/modules/calculations/application/factory_power_presentation.py"
)
MCP_PATHS = (
    "backend/src/cold_storage/modules/aily/api/mcp_sse.py",
    "backend/src/cold_storage/modules/aily/application/mcp_stage_preview.py",
    "backend/src/cold_storage/modules/aily/application/mcp_zone_plan.py",
)
V18_FROZEN_PATHS = (
    "docs/contracts/aily/v1.8",
    "docs/runbooks/v18-doubao-aily-connector.md",
)
HISTORICAL_P1_GOLDEN_PATH = (
    REPO_ROOT / "backend/tests/golden/v20_factory_power_canonical_result_v1.json"
)
ALLOWED_CHANGED_PATHS = {
    ADAPTER_PATH,
    "backend/tests/architecture/test_v20_p0_factory_power_estimation_and_presentation_contract.py",
    "backend/tests/architecture/test_v20_p1_factory_power_estimation_canonical_result.py",
    "backend/tests/architecture/test_v20_p2_factory_power_read_only_presentation.py",
    "backend/tests/architecture/test_v20_release_closure_readiness.py",
    "backend/tests/architecture/test_v21_p1_factory_power_upstream_authority.py",
    "backend/tests/unit/test_v21_p1_factory_power_upstream_authority.py",
    "backend/tests/architecture/test_v21_p0_factory_power_upstream_authority_doubao_mcp_contract.py",
    "docs/tasks/V2_1-P1-factory-power-upstream-authority-adapter-implementation.md",
    "docs/tasks/V2_1-version-plan.md",
    "docs/architecture/ADR-043-factory-power-upstream-authority-doubao-mcp.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/TECH_DEBT.md",
    # Later V2.1 P2 lane: these paths are outside the historical P1 diff but
    # must not make the durable P1 scope lock fail on a follow-on branch.
    "backend/src/cold_storage/modules/aily/application/factory_power_preview.py",
    "backend/src/cold_storage/modules/aily/application/mcp_factory_power.py",
    "backend/tests/architecture/test_v21_p2_factory_power_mcp_doubao_integration.py",
    "backend/tests/architecture/test_v21_release_closure_readiness.py",
    "backend/tests/integration/test_v21_p2_aily_factory_power_mcp_http.py",
    "backend/tests/unit/test_v21_p2_aily_factory_power_mcp.py",
    "backend/tests/unit/test_v21_p2_aily_factory_power_preview.py",
    "docs/contracts/aily/v2.1/doubao-skill.v1.json",
    "docs/contracts/aily/v2.1/doubao-skill.v1.md",
    "docs/runbooks/v21-doubao-aily-connector.md",
    "docs/tasks/V2_1-P2-factory-power-mcp-doubao-skill-integration.md",
    "docs/tasks/V2_1-release-closure-readiness.md",
}


def _text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _historical_p1_calculator() -> dict[str, str]:
    payload = json.loads(HISTORICAL_P1_GOLDEN_PATH.read_text(encoding="utf-8"))
    calculator = payload["calculator"]
    assert isinstance(calculator, dict)
    assert all(isinstance(value, str) for value in calculator.values())
    return calculator


def _changed_paths() -> set[str]:
    tracked = subprocess.run(
        ["git", "diff", "--name-only", BASE_MAIN_SHA, P1_REFERENCE_HEAD_SHA],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return {
        path.strip()
        for path in tracked
        if path.strip()
        if path and not path.startswith("backend/artifacts/local/")
    }


def _diff_is_empty(*paths: str) -> bool:
    return (
        subprocess.run(
            [
                "git",
                "diff",
                "--quiet",
                BASE_MAIN_SHA,
                P1_REFERENCE_HEAD_SHA,
                "--",
                *paths,
            ],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        == 0
    )


def test_v21_p1_scope_is_limited_to_adapter_tests_and_governance() -> None:
    changed = _changed_paths()
    assert changed <= ALLOWED_CHANGED_PATHS
    assert not any(path.startswith("frontend/src/") for path in changed)
    assert not any(path.startswith("backend/alembic/") for path in changed)
    assert not any(path.startswith(".github/workflows/") for path in changed)
    assert not any(path.startswith("deployment/") for path in changed)
    assert not any(path.startswith("docs/contracts/aily/v1.8/") for path in changed)


def test_v21_p1_uses_durable_base_lineage_not_origin_main_equality() -> None:
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", BASE_MAIN_SHA, "HEAD"],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        == 0
    )
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", P1_REFERENCE_HEAD_SHA, "HEAD"],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        == 0
    )
    assert (
        subprocess.run(
            ["git", "rev-parse", "v2.0.0^{}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        == BASE_RELEASE_SHA
    )
    plan = _text("docs/tasks/V2_1-version-plan.md")
    p1_doc = _text("docs/tasks/V2_1-P1-factory-power-upstream-authority-adapter-implementation.md")
    assert f"BASE_MAIN_SHA={BASE_MAIN_SHA}" in p1_doc
    assert "BASE_MAIN_SHA_IS_ANCESTOR_OF_HEAD=YES" in p1_doc
    assert "origin/main ==" not in p1_doc
    assert "P1_STATUS=IMPLEMENTATION_ACTIVE" in plan


def test_v21_p1_adapter_is_the_only_new_runtime_authority_boundary() -> None:
    adapter = _text(ADAPTER_PATH)
    assert "REFRIGERATED_ZONE_REGISTRY" in adapter
    assert "calculate_factory_power_estimation_from_mapping" in adapter
    assert "FactoryPowerEstimationResult" in adapter
    assert "ZONE_PLAN_CALCULATOR_IDENTITY" in adapter
    assert "EXPECTED_FACTORY_ZONE_CODES" in adapter
    assert "REFRIGERATED_AREA_M2_FORBIDDEN_AS_AUTHORITY" in adapter
    assert "DUPLICATE_ZONE_CODE" in adapter
    assert "ZONE_AUTHORITY_SET_MISMATCH" in adapter
    assert "MISSING_ZONE_REQUIRED_AREA" in adapter
    assert "INVALID_ZONE_REQUIRED_AREA" in adapter
    assert "REFRIGERATED_ZONE_TEMPERATURE_MISMATCH" in adapter
    assert "FACTORY_AREA_TOTAL_MISMATCH" in adapter
    assert "raw_position_count" not in adapter
    assert "subtotal_load_kw_r" not in adapter
    assert tuple(EXPECTED_FACTORY_ZONE_CODES) == (
        "office",
        "changing_room",
        "primary_precooling_room",
        "secondary_precooling_room",
        "raw_fruit_buffer",
        "sorting_packaging_room",
        "coating_room",
        "finished_goods_room",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "packaging_material_storage",
        "shipping_channel",
    )
    assert len(EXPECTED_FACTORY_ZONE_CODES) == 12
    assert len(REFRIGERATED_ZONE_CODES) == 9


def test_v21_p1_preserves_v20_calculator_presentation_and_mcp_surfaces() -> None:
    assert _diff_is_empty(V20_CALCULATOR_PATH)
    assert _diff_is_empty(V20_PRESENTATION_PATH)
    assert all(_diff_is_empty(path) for path in MCP_PATHS)
    assert all(_diff_is_empty(path) for path in V18_FROZEN_PATHS)
    assert _diff_is_empty("backend/src/cold_storage/modules/orchestration/domain/contracts.py")
    assert _historical_p1_calculator() == {
        "id": "factory_power_estimation",
        "version": "2.0.0-p1",
        "identity": "factory_power_estimation@2.0.0-p1",
    }


def test_v21_p1_governance_records_p0_merged_and_p2_not_started() -> None:
    p1_doc = _text("docs/tasks/V2_1-P1-factory-power-upstream-authority-adapter-implementation.md")
    plan = _text("docs/tasks/V2_1-version-plan.md")
    adr = _text("docs/architecture/ADR-043-factory-power-upstream-authority-doubao-mcp.md")
    for text in (p1_doc, plan, adr):
        assert "V20_P0_STATUS=MERGED" in text or "P0_STATUS=MERGED" in text
        assert "P1_STATUS=IMPLEMENTATION_ACTIVE" in text
        assert "P2_STATUS=UNAUTHORIZED" in text
        assert "DOUBAO_MCP_IMPLEMENTATION=NO" in text
        assert "NO_STEP_IMPLIES_THE_NEXT=TRUE" in text
    assert "P1_EXECUTED=YES" in p1_doc
    assert "V20_CALCULATOR_INVOKED=YES" in p1_doc
    assert "MCP_IMPLEMENTED=NO" in p1_doc
    assert "FRONTEND_CHANGED=NO" in p1_doc
    assert "DATABASE_MIGRATION=NO" in p1_doc


def test_v21_p1_docs_keep_the_five_key_and_area_authority_contract() -> None:
    p1_doc = _text("docs/tasks/V2_1-P1-factory-power-upstream-authority-adapter-implementation.md")
    required = (
        "CANONICAL_ZONE_PLAN_IDENTITY_REQUIRED=YES",
        "FACTORY_AREA_FROM_12_ZONE_ROWS=YES",
        "FACTORY_AREA_TOTAL_CROSS_CHECK=YES",
        "COLD_STORAGE_AREA_FROM_REFRIGERATED_REGISTRY=YES",
        "REFRIGERATED_ZONE_COUNT=9",
        "FROZEN_FRUIT_ROOM_INCLUDED=YES",
        "SHIPPING_CHANNEL_INCLUDED=YES",
        "REFRIGERATED_TEMPERATURE_INTEGRITY=YES",
        "REFRIGERATED_AREA_M2_USED_AS_AUTHORITY=NO",
        "ADAPTER_ONLY_BINDS_AUTHORITY=YES",
        "RAW_POSITION_COUNT_FALLBACK=NO",
        "SUBTOTAL_LOAD_FALLBACK=NO",
    )
    for marker in required:
        assert marker in p1_doc
