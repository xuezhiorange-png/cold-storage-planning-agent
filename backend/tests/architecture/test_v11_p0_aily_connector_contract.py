"""Architecture tests for V1.1 Aily / 豆包 zone-plan connector."""

from __future__ import annotations

from pathlib import Path

from cold_storage.modules.calculations.domain.zone_planning import VERSION
from cold_storage.modules.orchestration.domain.dag import (
    CALCULATOR_BINDINGS,
    ORCHESTRATION_STAGE_ORDER,
)
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V1_1-P0-aily-zone-plan-connector-contract.md"
PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V1_1-version-plan.md"
ADR_PATH = REPO_ROOT / "docs" / "architecture" / "ADR-031-aily-conversation-zone-plan.md"
AILY_API = REPO_ROOT / "backend" / "src" / "cold_storage" / "modules" / "aily" / "api" / "routes.py"
OPENAPI_PATH = (
    REPO_ROOT / "docs" / "contracts" / "aily" / "v1.1" / "aily-to-system-zone-plan.openapi.yaml"
)


def test_v11_contract_files_exist() -> None:
    assert CONTRACT_PATH.is_file()
    assert PLAN_PATH.is_file()
    assert ADR_PATH.is_file()
    assert OPENAPI_PATH.is_file()
    assert AILY_API.is_file()


def test_v11_keeps_frozen_operator_keys_and_zone_identity() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    plan = PLAN_PATH.read_text(encoding="utf-8")
    for leaf in OPERATOR_V09_FIVE_KEY_FIELDS:
        assert leaf in contract
        assert leaf in plan
    assert VERSION == "1.0.0"
    assert "cold_room_zone_plan@1.0.0" in contract
    assert "DO_NOT_BUMP_ZONE_PLAN_VERSION=YES" in contract
    assert ORCHESTRATION_STAGE_ORDER[0] == "zone"
    assert CALCULATOR_BINDINGS["zone"] == "cold_room_zone_plan"


def test_v11_aily_api_does_not_import_calculations_or_review_tools() -> None:
    api_text = AILY_API.read_text(encoding="utf-8")
    assert "cold_storage.modules.calculations" not in api_text
    assert "mark_reviewed" not in api_text
    assert "approve" not in api_text
    assert "/api/v1/agent" not in api_text
    assert "/api/v1/aily/v1/zone-plan" in api_text or 'prefix="/api/v1/aily"' in api_text
    assert "要建一个" not in api_text
    payload_path = (
        REPO_ROOT
        / "backend"
        / "src"
        / "cold_storage"
        / "modules"
        / "aily"
        / "application"
        / "operator_payload.py"
    )
    payload_text = payload_path.read_text(encoding="utf-8")
    assert "does not parse chat" in payload_text
    assert "cold_storage.modules.calculations" not in payload_text


def test_v11_contract_keeps_non_goals() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    for flag in (
        "COOLING_LOAD_FORMULA_RECUT=NO",
        "EQUIPMENT_FORMULA_RECUT=NO",
        "INSTALLED_POWER_FORMULA_RECUT=NO",
        "INVESTMENT_FORMULA_RECUT=NO",
        "CAD_BIM_CONSTRUCTION_DRAWINGS=NO",
        "PRODUCTION_RBAC_CLAIM=NO",
        "AGENT_TO_ENGINEERING_VALUE=NO",
        "AILY_OUTBOUND_LIVE_SESSION=NO",
    ):
        assert flag in contract
    assert "豆包工作伙伴" in contract
    assert "POST /api/v1/aily/v1/zone-plan" in contract
    assert "V11-E1" in contract
    assert "吨 always means per day" in contract
    assert "豆包 owns semantics" in contract
