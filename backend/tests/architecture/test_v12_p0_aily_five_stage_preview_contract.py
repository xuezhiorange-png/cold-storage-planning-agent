"""Architecture tests for V1.2 Aily / 豆包 five-stage conversation preview."""

from __future__ import annotations

from pathlib import Path

from cold_storage.modules.calculations.domain.zone_planning import VERSION as ZONE_VERSION
from cold_storage.modules.orchestration.domain.dag import CALCULATOR_BINDINGS
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V1_2-P0-aily-five-stage-preview-contract.md"
PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V1_2-version-plan.md"
ADR_PATH = REPO_ROOT / "docs" / "architecture" / "ADR-034-aily-five-stage-conversation-preview.md"
AILY_API_DIR = REPO_ROOT / "backend" / "src" / "cold_storage" / "modules" / "aily"
AILY_API = AILY_API_DIR / "api" / "routes.py"
MCP_SSE = AILY_API_DIR / "api" / "mcp_sse.py"
SKILL_PATH = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.2" / "doubao-skill.v1.md"


def test_v12_contract_files_exist() -> None:
    assert CONTRACT_PATH.is_file()
    assert PLAN_PATH.is_file()
    assert ADR_PATH.is_file()
    assert SKILL_PATH.is_file()
    assert AILY_API.is_file()
    assert MCP_SSE.is_file()


def test_v12_keeps_frozen_operator_keys_and_calculator_identities() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    plan = PLAN_PATH.read_text(encoding="utf-8")
    for leaf in OPERATOR_V09_FIVE_KEY_FIELDS:
        assert leaf in contract
        assert leaf in plan
    assert ZONE_VERSION == "1.0.0"
    for identity in (
        "cold_room_zone_plan@1.0.0",
        "cooling_load@1.0.0",
        "equipment@1.0.0",
        "installed_power@1.0.0",
        "investment_estimate@1.0.0",
    ):
        assert identity in contract or identity in plan
    for flag in (
        "KEEP_ZONE_PLAN_VERSION=YES",
        "KEEP_COOLING_LOAD_VERSION=YES",
        "KEEP_EQUIPMENT_VERSION=YES",
        "KEEP_INSTALLED_POWER_VERSION=YES",
        "KEEP_INVESTMENT_VERSION=YES",
    ):
        assert flag in contract
    assert CALCULATOR_BINDINGS["zone"] == "cold_room_zone_plan"
    assert CALCULATOR_BINDINGS["cooling_load"] == "cooling_load"
    assert CALCULATOR_BINDINGS["equipment"] == "equipment"
    assert CALCULATOR_BINDINGS["power"] == "installed_power"
    assert CALCULATOR_BINDINGS["investment"] == "investment_estimate"


def test_v12_aily_layers_do_not_import_calculations_or_review_tools() -> None:
    for path in AILY_API_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "cold_storage.modules.calculations" not in text, path.name
    routes_text = AILY_API.read_text(encoding="utf-8")
    assert "mark_reviewed" not in routes_text
    assert "approve" not in routes_text
    assert "/api/v1/agent" not in routes_text
    assert (
        "/api/v1/aily/v1/concept-preview" in routes_text or '"/v1/concept-preview"' in routes_text
    )
    payload_path = AILY_API_DIR / "application" / "operator_payload.py"
    payload_text = payload_path.read_text(encoding="utf-8")
    assert "does not parse chat" in payload_text


def test_v12_contract_keeps_non_goals_and_cooling_honesty() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    for flag in (
        "FORMULA_RECUT_AUTHORIZED=NO",
        "COOLING_LOAD_FORMULA_RECUT=NO",
        "ENVELOPE_FROM_ZONE_AREA=NO",
        "AILY_OUTBOUND_LIVE_SESSION=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
        "AGENT_TO_ENGINEERING_VALUE=NO",
    ):
        assert flag in contract
    assert "envelope_from_zone_area" in contract
    assert "演示围护" in contract or "demo envelope" in adr.lower()
    assert "preview_cooling_load" in contract
    assert "preview_zone_plan" in contract
    assert "Streamable HTTP" in contract or "mcp/sse" in contract


def test_v12_mcp_lists_five_tools_zone_first() -> None:
    from cold_storage.modules.aily.application.mcp_zone_plan import PREVIEW_ZONE_PLAN_TOOL_NAME

    mcp_text = MCP_SSE.read_text(encoding="utf-8")
    assert PREVIEW_ZONE_PLAN_TOOL_NAME in mcp_text
    assert "PREVIEW_COOLING_LOAD_TOOL_NAME" in mcp_text
    assert "PREVIEW_EQUIPMENT_TOOL_NAME" in mcp_text
    assert "PREVIEW_INSTALLED_POWER_TOOL_NAME" in mcp_text
    assert "PREVIEW_INVESTMENT_TOOL_NAME" in mcp_text
    assert "演示围护" in mcp_text
    assert "validate_input=False" in mcp_text
