"""Architecture tests for V1.1 P5 Aily MCP Streamable HTTP inbound transport."""

from __future__ import annotations

import json
from pathlib import Path

from cold_storage.modules.calculations.domain.zone_planning import VERSION
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V1_1-P5-aily-mcp-sse-contract.md"
ADR_PATH = REPO_ROOT / "docs" / "architecture" / "ADR-033-aily-mcp-sse-zone-plan.md"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "v11-doubao-aily-connector.md"
AILY_API = REPO_ROOT / "backend" / "src" / "cold_storage" / "modules" / "aily" / "api"
MCP_SSE = AILY_API / "mcp_sse.py"
MCP_APP = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "aily"
    / "application"
    / "mcp_zone_plan.py"
)
ROUTES = AILY_API / "routes.py"


def test_v11_p5_contract_files_exist() -> None:
    assert CONTRACT_PATH.is_file()
    assert ADR_PATH.is_file()
    assert MCP_SSE.is_file()
    assert MCP_APP.is_file()


def test_v11_p5_keeps_zone_identity_and_five_keys() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    app_text = MCP_APP.read_text(encoding="utf-8")
    api_text = MCP_SSE.read_text(encoding="utf-8")
    assert VERSION == "1.0.0"
    assert "cold_room_zone_plan@1.0.0" in contract
    assert "DO_NOT_BUMP_ZONE_PLAN_VERSION=YES" in contract
    assert "preview_zone_plan" in contract
    assert "preview_zone_plan" in app_text
    for leaf in OPERATOR_V09_FIVE_KEY_FIELDS:
        assert leaf in contract
        assert leaf in api_text
    assert "validate_input=False" in api_text


def test_v11_p5_mcp_layers_do_not_import_calculations_or_agent_routes() -> None:
    for path in (MCP_SSE, MCP_APP, ROUTES):
        text = path.read_text(encoding="utf-8")
        assert "cold_storage.modules.calculations" not in text
        assert "mark_reviewed" not in text
        assert "/api/v1/agent" not in text
        assert "要建一个" not in text


def test_v11_p5_application_and_domain_stay_mcp_sdk_free() -> None:
    domain_dir = REPO_ROOT / "backend" / "src" / "cold_storage" / "modules" / "aily" / "domain"
    for path in domain_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "from mcp" not in text
        assert "import mcp" not in text
    text = MCP_APP.read_text(encoding="utf-8")
    assert "from mcp" not in text
    assert "import mcp" not in text
    assert "fastapi" not in text
    assert "sqlalchemy" not in text
    assert "does not import the MCP SDK" in text


def test_v11_p5_runbook_tells_operator_streamable_http_not_get_sse() -> None:
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    api_text = MCP_SSE.read_text(encoding="utf-8")
    assert "/api/v1/aily/v1/mcp/sse" in runbook
    assert "/api/v1/aily/v1/mcp/sse" in contract
    assert "添加自定义 MCP 工具" in runbook
    assert "POST /api/v1/aily/v1/zone-plan" in runbook
    assert "工作伙伴 / Aily → 连接器 / 自定义连接器 → 从 OpenAPI 导入" not in runbook
    assert "Streamable HTTP" in runbook
    assert "Streamable HTTP" in contract
    assert "传输选 **SSE**" not in runbook
    assert "json_response=true" in api_text or "json_response=true" in contract
    assert "is_json_response_enabled=True" in api_text
    assert "tools/list" in runbook
    assert "preview_zone_plan" in runbook
    assert "trycloudflare" in runbook
    assert "5173" in runbook
    assert "8000" in runbook
    assert "GET SSE" in runbook or "GET 事件流" in runbook
    assert "POST JSON-RPC" in runbook or "POST JSON-RPC" in contract
    assert "GET {origin}/api/v1/aily/v1/mcp/sse" not in contract


def test_v11_p5_contract_keeps_non_goals() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    for flag in (
        "AILY_OUTBOUND_LIVE_SESSION=NO",
        "COOLING_LOAD_FORMULA_RECUT=NO",
        "EQUIPMENT_FORMULA_RECUT=NO",
        "INSTALLED_POWER_FORMULA_RECUT=NO",
        "INVESTMENT_FORMULA_RECUT=NO",
        "CAD_BIM_CONSTRUCTION_DRAWINGS=NO",
        "PRODUCTION_RBAC_CLAIM=NO",
        "AGENT_TO_ENGINEERING_VALUE=NO",
        "EXTEND_API_V1_AGENT_FOR_AILY=NO",
    ):
        assert flag in contract
    assert "豆包工作伙伴" in contract
    assert "吨 always means per day" in contract


def test_v11_p5_skill_declares_streamable_http_transport() -> None:
    skill_json = json.loads(
        (REPO_ROOT / "docs" / "contracts" / "aily" / "v1.1" / "doubao-skill.v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert skill_json["mcp"]["transport"] == "streamable_http"
    assert skill_json["mcp"]["path"] == "/api/v1/aily/v1/mcp/sse"
    assert skill_json["mcp"]["tool"] == "preview_zone_plan"
