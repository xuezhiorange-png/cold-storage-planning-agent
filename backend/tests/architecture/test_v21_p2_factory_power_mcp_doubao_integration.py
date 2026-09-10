"""Architecture locks for the V2.1 P2 factory-power MCP integration."""

from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path

from cold_storage.modules.aily.api.mcp_sse import _PREVIEW_TOOL_ORDER
from cold_storage.modules.aily.application.factory_power_preview import (
    MCP_INPUT_SCHEMA_REJECTED,
    PREVIEW_FACTORY_POWER_INPUT_FIELDS,
)
from cold_storage.modules.aily.application.mcp_factory_power import (
    PREVIEW_FACTORY_POWER_TOOL_NAME,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_MAIN_SHA = "95b6cbf839ba584f29f13735b07f8f8309b1cf37"
# The V2.1 P2 scope is the immutable range from the merged P1 commit to the
# PR #262 merge commit.  Later HEADs are checked only for lineage below.
HISTORICAL_TASK_BASE_SHA = BASE_MAIN_SHA
HISTORICAL_TASK_TARGET_SHA = "b314f08c74296e23e2a1729dd4f84dc8387c7a4e"
P2_DOC_PATH = REPO_ROOT / "docs/tasks/V2_1-P2-factory-power-mcp-doubao-skill-integration.md"
VERSION_PLAN_PATH = REPO_ROOT / "docs/tasks/V2_1-version-plan.md"
ADR_PATH = REPO_ROOT / "docs/architecture/ADR-043-factory-power-upstream-authority-doubao-mcp.md"
SKILL_MD_PATH = REPO_ROOT / "docs/contracts/aily/v2.1/doubao-skill.v1.md"
SKILL_JSON_PATH = REPO_ROOT / "docs/contracts/aily/v2.1/doubao-skill.v1.json"
RUNBOOK_PATH = REPO_ROOT / "docs/runbooks/v21-doubao-aily-connector.md"

P2_RUNTIME_PATHS = {
    "backend/src/cold_storage/modules/aily/api/mcp_sse.py",
    "backend/src/cold_storage/modules/aily/application/stage_preview.py",
    "backend/src/cold_storage/modules/aily/application/factory_power_preview.py",
    "backend/src/cold_storage/modules/aily/application/mcp_factory_power.py",
}
P2_TEST_PATHS = {
    "backend/tests/unit/test_v21_p2_aily_factory_power_preview.py",
    "backend/tests/unit/test_v21_p2_aily_factory_power_mcp.py",
    "backend/tests/integration/test_v21_p2_aily_factory_power_mcp_http.py",
    "backend/tests/architecture/test_v21_p2_factory_power_mcp_doubao_integration.py",
    "backend/tests/architecture/test_v20_p0_factory_power_estimation_and_presentation_contract.py",
    "backend/tests/architecture/test_v20_p1_factory_power_estimation_canonical_result.py",
    "backend/tests/architecture/test_v20_p2_factory_power_read_only_presentation.py",
    "backend/tests/architecture/test_v20_release_closure_readiness.py",
    "backend/tests/architecture/test_v21_p0_factory_power_upstream_authority_doubao_mcp_contract.py",
    "backend/tests/architecture/test_v21_p1_factory_power_upstream_authority.py",
    "backend/tests/architecture/test_v21_release_closure_readiness.py",
    "backend/tests/unit/test_v11_aily_mcp_protocol.py",
    "backend/tests/unit/test_v12_aily_mcp_protocol.py",
    "backend/tests/integration/test_v11_aily_mcp_sse_http.py",
    # These historical locks are explicitly updated to exempt the authorized
    # V2.1 P2 application surface from their legacy five-stage scan.
    "backend/tests/architecture/test_v12_p0_aily_five_stage_preview_contract.py",
    "backend/tests/architecture/test_v13_p0_aily_preview_lineage_contract.py",
    "backend/tests/architecture/test_v14_p0_workbench_debt_contract.py",
    "backend/tests/architecture/test_v15_p0_envelope_geometry_contract.py",
    "backend/tests/architecture/test_v16_p0_power_fan_catalog_contract.py",
    "backend/tests/architecture/test_v17_p0_zone_cooling_surface_contract.py",
    "backend/tests/architecture/test_v18_p0_zone_temperature_height_contract.py",
    "backend/tests/unit/test_v13_aily_preview_lineage.py",
    "backend/tests/unit/test_v15_aily_envelope_geometry.py",
    "backend/tests/unit/test_v16_power_fan_catalog.py",
    "backend/tests/unit/test_v17_zone_cooling_surface.py",
    "backend/tests/unit/test_v18_zone_temperature_height.py",
}
P2_DOC_PATHS = {
    "docs/tasks/V2_1-P2-factory-power-mcp-doubao-skill-integration.md",
    "docs/tasks/V2_1-version-plan.md",
    "docs/architecture/ADR-043-factory-power-upstream-authority-doubao-mcp.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/TECH_DEBT.md",
    "docs/tasks/V2_1-release-closure-readiness.md",
    "docs/contracts/aily/v2.1/doubao-skill.v1.md",
    "docs/contracts/aily/v2.1/doubao-skill.v1.json",
    "docs/runbooks/v21-doubao-aily-connector.md",
}
P2_ALLOWED_PATHS = P2_RUNTIME_PATHS | P2_TEST_PATHS | P2_DOC_PATHS
FROZEN_RUNTIME_PATHS = {
    "backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py",
    "backend/src/cold_storage/modules/projects/application/factory_power_upstream_authority.py",
    "backend/src/cold_storage/modules/calculations/application/factory_power_presentation.py",
    "backend/src/cold_storage/modules/projects/application/factory_power_presentation.py",
    "backend/src/cold_storage/modules/aily/application/factory_power_table.py",
    "frontend/src/features/calculations/model/mapFactoryPowerPresentation.ts",
    "frontend/src/features/calculations/components/FactoryPowerEstimationResults.vue",
}
FIVE_TOOLS = (
    "preview_zone_plan",
    "preview_cooling_load",
    "preview_equipment",
    "preview_installed_power",
    "preview_investment",
)
ALL_TOOLS = (*FIVE_TOOLS, "preview_factory_power")
FACTORY_POWER_PREVIEW_PATH = (
    "backend/src/cold_storage/modules/aily/application/factory_power_preview.py"
)
ALLOWED_CALCULATIONS_IMPORTS = {
    "cold_storage.modules.calculations.domain.factory_power_estimation": {
        "FactoryPowerEstimationError",
        "serialize_factory_power_result",
    }
}
P1_ADAPTER_IMPORT_MODULE = (
    "cold_storage.modules.projects.application.factory_power_upstream_authority"
)
P1_ADAPTER_IMPORT_NAMES = {
    "FactoryPowerUpstreamAuthorityError",
    "calculate_factory_power_from_zone_plan",
}


def _text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _assert_historical_target_is_ancestor_of_head() -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", HISTORICAL_TASK_TARGET_SHA, "HEAD"],
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, (
        f"historical target {HISTORICAL_TASK_TARGET_SHA} must be an ancestor of HEAD"
    )


def _historical_changed_paths() -> set[str]:
    _assert_historical_target_is_ancestor_of_head()
    tracked = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            HISTORICAL_TASK_BASE_SHA,
            HISTORICAL_TASK_TARGET_SHA,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return {
        path.strip()
        for path in tracked
        if path.strip() and not path.strip().startswith("backend/artifacts/local/")
    }


def _unchanged_from_historical_task(relative_path: str) -> bool:
    _assert_historical_target_is_ancestor_of_head()
    return (
        subprocess.run(
            [
                "git",
                "diff",
                "--quiet",
                HISTORICAL_TASK_BASE_SHA,
                HISTORICAL_TASK_TARGET_SHA,
                "--",
                relative_path,
            ],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        == 0
    )


def _assert_narrow_calculations_imports(source: str) -> None:
    tree = ast.parse(source)
    observed: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if not module.startswith("cold_storage.modules.calculations"):
                continue
            assert module in ALLOWED_CALCULATIONS_IMPORTS, (
                f"Unexpected calculations import module: {module}"
            )
            names = {alias.name for alias in node.names}
            assert names <= ALLOWED_CALCULATIONS_IMPORTS[module], (
                f"Unexpected names imported from {module}: {names}"
            )
            observed.setdefault(module, set()).update(names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("cold_storage.modules.calculations"):
                    raise AssertionError(
                        "Direct calculations imports are not allowed; use the exact "
                        "P2 allowlisted symbols"
                    )

    assert observed == ALLOWED_CALCULATIONS_IMPORTS


def _assert_p1_adapter_import(source: str) -> None:
    tree = ast.parse(source)
    adapter_imports: list[set[str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == P1_ADAPTER_IMPORT_MODULE:
            adapter_imports.append({alias.name for alias in node.names})
        elif isinstance(node, ast.Import):
            assert all(alias.name != P1_ADAPTER_IMPORT_MODULE for alias in node.names)

    assert adapter_imports == [P1_ADAPTER_IMPORT_NAMES]


def test_v21_p2_factory_power_preview_has_narrow_authority_imports() -> None:
    source = _text(FACTORY_POWER_PREVIEW_PATH)
    _assert_narrow_calculations_imports(source)
    _assert_p1_adapter_import(source)


def test_v21_p2_scope_is_limited_to_authorized_mcp_skill_and_docs_paths() -> None:
    changed = _historical_changed_paths()
    assert changed <= P2_ALLOWED_PATHS
    assert not any(path.startswith("backend/alembic/") for path in changed)
    assert not any(path.startswith("frontend/src/") for path in changed)
    assert not any(path.startswith(".github/workflows/") for path in changed)
    assert not any(path.startswith("deployment/") for path in changed)
    assert not any(path.startswith("docs/contracts/aily/v1.8/") for path in changed)
    assert "backend/src/cold_storage/modules/aily/api/mcp_sse.py" in changed


def test_v21_p2_has_durable_base_lineage_and_no_moving_origin_equality_lock() -> None:
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", BASE_MAIN_SHA, "HEAD"],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        == 0
    )
    doc = _text("docs/tasks/V2_1-P2-factory-power-mcp-doubao-skill-integration.md")
    assert f"BASE_MAIN_SHA={BASE_MAIN_SHA}" in doc
    assert "BASE_MAIN_CI_RUN_ID=34321050750" in doc
    assert "BASE_MAIN_CI_RESULT=SUCCESS" in doc
    assert "origin/main ==" not in doc


def test_v21_p2_governance_records_active_p2_without_rewriting_prior_gates() -> None:
    p2_doc = P2_DOC_PATH.read_text(encoding="utf-8")
    plan = VERSION_PLAN_PATH.read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")

    for text in (p2_doc, plan, adr):
        assert "P0_STATUS=MERGED" in text
        assert "P1_STATUS=MERGED" in text
        assert "P2_STATUS=IMPLEMENTATION_ACTIVE" in text
        assert "P2_EXECUTED=YES" in text
        assert "RELEASE_CLOSURE=UNAUTHORIZED" in text
        assert "READY=NO" in text
        assert "MERGE=NO" in text
        assert "NO_STEP_IMPLIES_THE_NEXT=TRUE" in text
    assert "V21_SKILL_STANDALONE_V18_SEMANTIC_SUPERSET=YES" in p2_doc
    assert "P2_CALCULATIONS_IMPORT_ALLOWLIST_DURABLE=YES" in p2_doc

    p0_history = _text("docs/tasks/V2_1-P0-factory-power-upstream-authority-doubao-mcp-contract.md")
    p1_history = _text(
        "docs/tasks/V2_1-P1-factory-power-upstream-authority-adapter-implementation.md"
    )
    assert "MCP_IMPLEMENTATION=NO" in p0_history
    assert "SKILL_IMPLEMENTATION=NO" in p0_history
    assert "P2_STATUS=UNAUTHORIZED" in p1_history
    assert "DOUBAO_MCP_IMPLEMENTATION=NO" in p1_history


def test_v21_p2_mcp_surface_appends_factory_power_after_the_existing_five() -> None:
    assert tuple(_PREVIEW_TOOL_ORDER) == ALL_TOOLS
    assert tuple(PREVIEW_FACTORY_POWER_INPUT_FIELDS) == (
        "daily_inbound_mass_kg",
        "finished_storage_days",
        "frozen_storage_days",
        "main_packaging_storage_days",
        "auxiliary_packaging_storage_days",
    )
    assert PREVIEW_FACTORY_POWER_TOOL_NAME == "preview_factory_power"
    api_text = _text("backend/src/cold_storage/modules/aily/api/mcp_sse.py")
    assert api_text.count("PREVIEW_FACTORY_POWER_TOOL_NAME") >= 2
    assert "validate_input=False" in api_text
    assert "additionalProperties" in api_text
    assert "OPERATOR_V09_FIVE_KEY_FIELDS" in api_text
    assert "CONCEPT_PREVIEW_STAGE_COUNT=5" in _text(
        "docs/tasks/V2_1-P2-factory-power-mcp-doubao-skill-integration.md"
    )


def test_v21_p2_runtime_chain_uses_existing_authorities_and_pure_projection() -> None:
    preview = _text("backend/src/cold_storage/modules/aily/application/factory_power_preview.py")
    wrapper = _text("backend/src/cold_storage/modules/aily/application/mcp_factory_power.py")
    stage = _text("backend/src/cold_storage/modules/aily/application/stage_preview.py")

    for needle in (
        "assemble_preview_context",
        "execute_zone_preview_authority",
        "calculate_factory_power_from_zone_plan",
        "serialize_factory_power_result",
        "project_factory_power_table",
        "_format_projected_table",
        "MCP_INPUT_SCHEMA_REJECTED",
        "unexpected_keys",
        "V20_FACTORY_POWER_CANONICAL_RESULT_UNAVAILABLE",
    ):
        assert needle in preview
    assert "preview_factory_power" in wrapper
    assert "preview_factory_power" in _text("backend/src/cold_storage/modules/aily/api/mcp_sse.py")

    tree = ast.parse(stage)
    helper = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "execute_zone_preview_authority"
    )
    assert len(helper.body) == 2
    assert isinstance(helper.body[0], ast.Expr)
    assert isinstance(helper.body[1], ast.Return)
    assert ast.unparse(helper.body[1].value) == "_execute_zone_stage(context)[1]"

    for forbidden in ("sum(", "round(", "Decimal(", "simultaneity"):
        assert forbidden.lower() not in preview.lower()
    assert re.search(r"\bCOP\b", preview, flags=re.IGNORECASE) is None
    assert "calculate_factory_power_estimation_from_mapping" not in preview
    assert "raw_position_count" not in preview
    assert "subtotal_load_kw_r" not in preview


def test_v21_p2_preserves_v20_p1_p2_and_p1_adapter_runtime_boundaries() -> None:
    for path in FROZEN_RUNTIME_PATHS:
        assert _unchanged_from_historical_task(path), f"P2 changed frozen path: {path}"
    assert len(CalculationType) == 5

    concept = _text("backend/src/cold_storage/modules/aily/application/concept_preview.py")
    assert "factory_power" not in concept
    assert "stages" in concept

    for path in (
        "backend/src/cold_storage/modules/aily/application/factory_power_preview.py",
        "backend/src/cold_storage/modules/aily/application/mcp_factory_power.py",
    ):
        source = _text(path)
        assert "fastapi" not in source.lower()
        assert "sqlalchemy" not in source.lower()
    mcp_source = _text("backend/src/cold_storage/modules/aily/api/mcp_sse.py")
    assert 'Route("/factory-power' not in mcp_source
    assert 'Route("/api/v1/factory-power' not in mcp_source


def test_v21_p2_skill_and_runbook_are_new_v21_surfaces() -> None:
    skill = json.loads(SKILL_JSON_PATH.read_text(encoding="utf-8"))
    v18_skill = json.loads(
        (REPO_ROOT / "docs/contracts/aily/v1.8/doubao-skill.v1.json").read_text(encoding="utf-8")
    )
    assert skill["schema_version"] == "2.1.0"
    assert skill["contract_family"] == "aily/v2.1"
    assert skill["governance"]["KEEP_AILY_V18_SKILL_FROZEN"] == "YES"
    assert skill["governance"]["AILY_OUTBOUND_LIVE_SESSION"] == "NO"
    assert skill["governance"]["AGENT_TO_ENGINEERING_VALUE"] == "NO"
    assert skill["governance"]["MCP_TOOL_COUNT"] == 6
    assert skill["governance"]["FACTORY_POWER_SOURCE"] == "factory_power_estimation@2.0.0-p1"
    assert skill["governance"]["SERVER_SIDE_CHAT_PARSING"] == "NO"
    assert skill["governance"]["V21_SKILL_STANDALONE_V18_SEMANTIC_SUPERSET"] == "YES"
    assert skill["governance"]["FACTORY_POWER_ACCEPTS_FLAT_TOP_LEVEL_FIVE_KEY_ONLY"] == "YES"
    assert skill["governance"]["FACTORY_POWER_ZONE_PLANNING_INPUTS_WRAPPER_ALLOWED"] == "NO"
    assert skill["governance"]["FACTORY_POWER_REQUIRES_PRECEDING_ZONE_TOOL_CALL"] == "NO"
    assert skill["factory_power"]["input_shape"] == "flat_top_level_five_keys_only"
    assert skill["factory_power"]["zone_planning_inputs_wrapper_allowed"] is False
    assert skill["factory_power"]["requires_preceding_preview_zone_plan"] is False
    for section in (
        "cooling_honesty",
        "equipment_honesty",
        "power_honesty",
        "investment_honesty",
    ):
        for key, value in v18_skill[section].items():
            assert skill[section][key] == value
    for key, value in v18_skill["governance"].items():
        assert skill["governance"][key] == value
    assert skill["calculator_identities"][:5] == v18_skill["calculator_identities"]
    assert skill["operator_keys"] == v18_skill["operator_keys"]
    assert (
        skill["response_handling"]["success_status"]
        == v18_skill["response_handling"]["success_status"]
    )
    assert (
        skill["response_handling"]["display_fields"]
        == v18_skill["response_handling"]["display_fields"]
    )
    assert skill["response_handling"]["on_error"] == v18_skill["response_handling"]["on_error"]
    assert (
        skill["self_check"]["tools_list_must_include"][:5]
        == v18_skill["self_check"]["tools_list_must_include"]
    )
    assert (
        skill["self_check"]["tools_call_smoke"][:2] == v18_skill["self_check"]["tools_call_smoke"]
    )
    assert set(v18_skill["forbidden_model_tools"]) <= set(skill["forbidden_model_tools"])
    assert set(v18_skill["forbidden_behaviors"]) <= set(skill["forbidden_behaviors"])
    assert skill["mcp"]["tools_in_order"] == list(ALL_TOOLS)
    assert skill["self_check"]["tools_list_must_include"] == list(ALL_TOOLS)
    assert skill["operator_schema"]["additional_properties"] is False
    assert set(skill["operator_schema"]["forbidden_fields"]) >= {
        "factory_area_m2",
        "cold_storage_area_m2",
        "refrigerated_area_m2",
        "total_area_m2",
        "zone_plan",
        "chat_text",
    }
    assert SKILL_MD_PATH.is_file()
    assert RUNBOOK_PATH.is_file()
    skill_text = SKILL_MD_PATH.read_text(encoding="utf-8")
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
    for marker in (
        "分区冷量按内核五项加总",
        "传热",
        "产品",
        "渗透",
        "内部",
        "化霜",
        "小计",
        "正方形平面 + 演示层高",
        "温区低端",
        "4.0 m",
        "10 / 8 kW(e)",
        "not kW(r)/COP",
        "extra_tables",
        "investment_from_demo_catalog=false",
        "power_from_demo_catalog: false",
        "AGENT_TO_ENGINEERING_VALUE=NO",
        "FACTORY_POWER_ACCEPTS_FLAT_TOP_LEVEL_FIVE_KEY_ONLY=YES",
        "FACTORY_POWER_ZONE_PLANNING_INPUTS_WRAPPER_ALLOWED=NO",
        "FACTORY_POWER_REQUIRES_PRECEDING_ZONE_TOOL_CALL=NO",
        "`preview_factory_power` 只接受五个顶层 KEY",
        "`zone_planning_inputs` 包裹对象",
        "不适用于 `preview_factory_power`",
    ):
        assert marker in skill_text
    for text in (skill_text, runbook):
        assert "preview_factory_power" in text
        assert "factory_power_estimation@2.0.0-p1" in text
        assert "kW" in text
        assert "概念设计" in text
        assert "需工程复核" in text or "requires_review" in text
        assert any(
            phrase in text
            for phrase in ("不要传面积", "不得传面积", "不要发送面积", "不得发送面积")
        )
    assert "/api/v1/aily/v1/mcp/sse" in runbook
    assert "Streamable HTTP" in runbook
    assert "tools/list" in runbook
    assert "tools/call" in runbook
    assert "v18-doubao-aily-connector.md" not in _historical_changed_paths()


def test_v21_p2_architecture_contract_exposes_strict_runtime_rejection() -> None:
    preview = _text("backend/src/cold_storage/modules/aily/application/factory_power_preview.py")
    p2_doc = P2_DOC_PATH.read_text(encoding="utf-8")
    assert MCP_INPUT_SCHEMA_REJECTED == "MCP_INPUT_SCHEMA_REJECTED"
    assert "set(PREVIEW_FACTORY_POWER_INPUT_FIELDS)" in preview
    wrapper = _text("backend/src/cold_storage/modules/aily/application/mcp_factory_power.py")
    assert "missing_keys" in wrapper
    assert "ask_operator" in wrapper
    for field in (
        "factory_area_m2",
        "cold_storage_area_m2",
        "refrigerated_area_m2",
        "total_area_m2",
        "zone_plan",
        "chat_text",
    ):
        assert field in p2_doc
    for forbidden in (
        'if "工厂功率"',
        'if "估算工厂电功率"',
        "server_side_chat_parsing",
    ):
        assert forbidden not in preview.lower()


def test_v21_p2_governance_no_release_or_downstream_gate_is_implied() -> None:
    p2_doc = P2_DOC_PATH.read_text(encoding="utf-8")
    for marker in (
        "P2_EXECUTED=YES",
        "READY=NO",
        "MERGE=NO",
        "TAG=NO",
        "RELEASE=NO",
        "DEPLOYMENT=NO",
        "RELEASE_CLOSURE=UNAUTHORIZED",
        "OUTBOUND_LIVE_AILY_SESSION=NO",
        "DATABASE_MIGRATION=NO",
        "FRONTEND_CHANGED=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    ):
        assert marker in p2_doc
