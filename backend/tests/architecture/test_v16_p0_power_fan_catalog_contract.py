"""Architecture tests for V1.6 v05 power-fan demo catalog definition freeze."""

from __future__ import annotations

from pathlib import Path

from cold_storage.modules.calculations.domain.power import CALCULATOR_VERSION
from cold_storage.modules.calculations.domain.zone_planning import VERSION as ZONE_VERSION
from cold_storage.modules.orchestration.domain.dag import CALCULATOR_BINDINGS
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V1_6-P0-power-fan-catalog-contract.md"
PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V1_6-version-plan.md"
ADR_PATH = REPO_ROOT / "docs" / "architecture" / "ADR-038-v05-power-fan-demo-catalog.md"
V15_PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V1_5-version-plan.md"
V15_SKILL_PATH = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.5" / "doubao-skill.v1.md"
V13_SKILL_PATH = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.3" / "doubao-skill.v1.md"
V16_SKILL_PATH = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.6" / "doubao-skill.v1.md"
V16_SKILL_JSON = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.6" / "doubao-skill.v1.json"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "v16-doubao-aily-connector.md"
V05_MANIFEST = REPO_ROOT / "samples" / "v05-local-workbench" / "manifest.json"
POWER_KERNEL = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "calculations"
    / "domain"
    / "power.py"
)
LOADER = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "projects"
    / "application"
    / "demo_power_fan_catalog.py"
)
ASSEMBLER = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "projects"
    / "application"
    / "operator_process_input.py"
)
PREVIEW_BUNDLE = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "aily"
    / "application"
    / "preview_bundle.py"
)
MCP_SSE = REPO_ROOT / "backend" / "src" / "cold_storage" / "modules" / "aily" / "api" / "mcp_sse.py"
APP_PATH = REPO_ROOT / "backend" / "src" / "cold_storage" / "bootstrap" / "app.py"
AILY_API_DIR = REPO_ROOT / "backend" / "src" / "cold_storage" / "modules" / "aily"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"


def test_v16_plan_files_exist() -> None:
    assert CONTRACT_PATH.is_file()
    assert PLAN_PATH.is_file()
    assert ADR_PATH.is_file()
    assert V13_SKILL_PATH.is_file()
    assert V15_SKILL_PATH.is_file()
    assert V16_SKILL_PATH.is_file()
    assert V16_SKILL_JSON.is_file()
    assert RUNBOOK_PATH.is_file()
    assert V05_MANIFEST.is_file()
    assert LOADER.is_file()


def test_v16_keeps_frozen_operator_keys_and_calculator_identities() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    plan = PLAN_PATH.read_text(encoding="utf-8")
    for leaf in OPERATOR_V09_FIVE_KEY_FIELDS:
        assert leaf in contract
        assert leaf in plan
    assert ZONE_VERSION == "1.0.0"
    assert CALCULATOR_VERSION == "1.0.0"
    for identity in (
        "cold_room_zone_plan@1.0.0",
        "cooling_load@1.0.0",
        "equipment@1.0.0",
        "installed_power@1.0.0",
        "investment_estimate@1.0.0",
    ):
        assert identity in contract
        assert identity in plan
    for flag in (
        "KEEP_ZONE_PLAN_VERSION=YES",
        "KEEP_COOLING_LOAD_VERSION=YES",
        "KEEP_EQUIPMENT_VERSION=YES",
        "KEEP_INSTALLED_POWER_VERSION=YES",
        "KEEP_INVESTMENT_VERSION=YES",
        "KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0",
        "KEEP_AILY_V15_SKILL_FROZEN=YES",
        "KEEP_AILY_V16_SKILL=YES",
    ):
        assert flag in contract
        assert flag in plan
    assert CALCULATOR_BINDINGS["zone"] == "cold_room_zone_plan"
    assert CALCULATOR_BINDINGS["cooling_load"] == "cooling_load"
    assert CALCULATOR_BINDINGS["equipment"] == "equipment"
    assert CALCULATOR_BINDINGS["power"] == "installed_power"
    assert CALCULATOR_BINDINGS["investment"] == "investment_estimate"


def test_v16_definition_freeze_authorizes_fan_catalog_only() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    plan = PLAN_PATH.read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    for flag in (
        "V16_IMPLEMENTATION_AUTHORIZED=YES",
        "V16_P0_IMPLEMENTATION_AUTHORIZED=YES",
        "TD008_POWER_FAN_DEMO_AUTHORITY=YES",
        "TD008_EQUIPMENT_CATALOG_UNIFIED=NO",
        "FAN_KW_FROM_EQUIPMENT=NO",
        "FORMULA_RECUT_AUTHORIZED=NO",
        "AILY_OUTBOUND_LIVE_SESSION=NO",
        "DELETE_PATH_A_SAVE_INPUTS=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
        "AGENT_TO_ENGINEERING_VALUE=NO",
        "V05_COMPRESSOR_120_NOT_AUTHORITY=YES",
    ):
        assert flag in contract
        assert flag in plan
    assert "Accepted" in adr
    assert "KEEP_INSTALLED_POWER_VERSION=YES" in adr
    kernel = POWER_KERNEL.read_text(encoding="utf-8")
    assert 'CALCULATOR_VERSION = "1.0.0"' in kernel
    assert 'evaporator_fan_power_kw_e: Decimal = _D("0")' in kernel
    assert 'condenser_fan_power_kw_e: Decimal = _D("0")' in kernel
    v15_plan = V15_PLAN_PATH.read_text(encoding="utf-8")
    assert "V15_IMPLEMENTATION_AUTHORIZED=YES" in v15_plan
    assert "v1.5.0" in v15_plan


def test_v16_loader_and_assembler_use_v05_not_kernel_defaults() -> None:
    loader = LOADER.read_text(encoding="utf-8")
    assembler = ASSEMBLER.read_text(encoding="utf-8")
    assert 'DEMO_POWER_FAN_SAMPLE_ID = "v05-local-workbench"' in loader
    assert "installed_power_inputs" in loader
    assert "InstalledPowerCalcInput()" not in assembler
    assert "InstalledPowerCalcInput.evaporator_fan_power_kw_e" not in assembler
    assert "load_demo_power_fan_catalog" in assembler
    assert "DEMO_POWER_FAN_SOURCE" in assembler
    app_text = APP_PATH.read_text(encoding="utf-8")
    assert "/api/v1/demo/power-fan-catalog" in app_text


def test_v16_aily_has_no_second_fan_literal_set() -> None:
    preview = PREVIEW_BUNDLE.read_text(encoding="utf-8")
    assert "_PREVIEW_POWER_FAN_DEMO" not in preview
    assert '"evaporator_fan_power_kw_e": "10.0"' not in preview
    assert '"condenser_fan_power_kw_e": "8.0"' not in preview
    mcp_text = MCP_SSE.read_text(encoding="utf-8")
    assert "可能仍为演示目录" not in mcp_text
    assert "POWER_FAN_DEMO_CATALOG_DISCLAIMER_ZH" in mcp_text
    for path in AILY_API_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "cold_storage.modules.calculations" not in text, path.name
        assert "five_stage_execution" not in text, path.name
        assert "_PREVIEW_POWER_FAN_DEMO" not in text, path.name


def test_v16_v15_skill_stays_frozen_and_v16_skill_has_fan_catalog() -> None:
    v15 = V15_SKILL_PATH.read_text(encoding="utf-8")
    v16 = V16_SKILL_PATH.read_text(encoding="utf-8")
    v16_json = V16_SKILL_JSON.read_text(encoding="utf-8")
    assert "风机可能仍为演示目录" in v15 or "可能仍为演示目录" in v15
    assert "v05 演示目录（10 / 8 kW(e)）" in v16
    assert "正方形平面 + 演示层高" in v16
    assert '"schema_version": "1.6.0"' in v16_json
    assert '"KEEP_AILY_V15_SKILL_FROZEN": "YES"' in v16_json
    assert '"FAN_KW_FROM_EQUIPMENT": "NO"' in v16_json
    formula_needles = (
        "P_refrig = compressor",
        "compressor + evaporator_fans + condenser_fans",
    )
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".vue", ".ts", ".js"}:
            continue
        text = path.read_text(encoding="utf-8")
        for needle in formula_needles:
            assert needle not in text, path.name
    assert RUNBOOK_PATH.is_file()
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "v05 演示目录" in runbook
    assert "AILY_OUTBOUND_LIVE_SESSION=NO" in runbook
