"""Architecture tests for V1.5 envelope wall/roof geometry definition freeze."""

from __future__ import annotations

from pathlib import Path

from cold_storage.modules.calculations.domain.cooling_load import CALCULATOR_VERSION
from cold_storage.modules.calculations.domain.zone_planning import VERSION as ZONE_VERSION
from cold_storage.modules.orchestration.domain.dag import CALCULATOR_BINDINGS
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V1_5-P0-envelope-geometry-contract.md"
PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V1_5-version-plan.md"
ADR_PATH = (
    REPO_ROOT / "docs" / "architecture" / "ADR-037-envelope-wall-roof-from-zone-geometry.md"
)
ADR_028 = REPO_ROOT / "docs" / "architecture" / "ADR-028-operator-minimal-process-input.md"
ADR_035 = REPO_ROOT / "docs" / "architecture" / "ADR-035-aily-preview-workbench-lineage.md"
AILY_API_DIR = REPO_ROOT / "backend" / "src" / "cold_storage" / "modules" / "aily"
V13_SKILL_PATH = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.3" / "doubao-skill.v1.md"
V15_SKILL_PATH = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.5" / "doubao-skill.v1.md"
V15_SKILL_JSON = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.5" / "doubao-skill.v1.json"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "v15-doubao-aily-connector.md"
COOLING_KERNEL = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "calculations"
    / "domain"
    / "cooling_load.py"
)
BINDER = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "projects"
    / "application"
    / "preview_lineage_bind.py"
)
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"


def test_v15_plan_files_exist() -> None:
    assert CONTRACT_PATH.is_file()
    assert PLAN_PATH.is_file()
    assert ADR_PATH.is_file()
    assert V13_SKILL_PATH.is_file()
    assert V15_SKILL_PATH.is_file()
    assert V15_SKILL_JSON.is_file()
    assert RUNBOOK_PATH.is_file()
    assert ADR_028.is_file()
    assert ADR_035.is_file()


def test_v15_keeps_frozen_operator_keys_and_calculator_identities() -> None:
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
        "KEEP_AILY_V13_SKILL_FROZEN=YES",
        "KEEP_AILY_V15_SKILL=YES",
    ):
        assert flag in contract
        assert flag in plan
    assert CALCULATOR_BINDINGS["zone"] == "cold_room_zone_plan"
    assert CALCULATOR_BINDINGS["cooling_load"] == "cooling_load"
    assert CALCULATOR_BINDINGS["equipment"] == "equipment"
    assert CALCULATOR_BINDINGS["power"] == "installed_power"
    assert CALCULATOR_BINDINGS["investment"] == "investment_estimate"


def test_v15_definition_freeze_authorizes_envelope_recut_only() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    plan = PLAN_PATH.read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    for flag in (
        "V15_IMPLEMENTATION_AUTHORIZED=YES",
        "V15_P0_IMPLEMENTATION_AUTHORIZED=YES",
        "FORMULA_RECUT_AUTHORIZED=YES",
        "COOLING_LOAD_FORMULA_RECUT=envelope_wall_roof_geometry_only",
        "ENVELOPE_WALL_ROOF_FROM_PLAN=YES",
        "AILY_OUTBOUND_LIVE_SESSION=NO",
        "DELETE_PATH_A_SAVE_INPUTS=NO",
        "TD008_POWER_EQUIPMENT_CATALOG_UNIFIED=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
        "AGENT_TO_ENGINEERING_VALUE=NO",
    ):
        assert flag in contract
        assert flag in plan
    assert "Accepted" in adr
    assert "room_height × 4 × √floor_area" in plan
    assert "required_area_m2" in plan
    assert "KEEP_COOLING_LOAD_VERSION=YES" in adr
    kernel = COOLING_KERNEL.read_text(encoding="utf-8")
    assert 'CALCULATOR_VERSION = "1.0.0"' in kernel
    assert "4 × √" not in kernel
    assert "4 * sqrt" not in kernel


def test_v15_does_not_rewrite_historical_adr_bodies() -> None:
    adr_028 = ADR_028.read_text(encoding="utf-8")
    adr_035 = ADR_035.read_text(encoding="utf-8")
    assert "ZONE_RESULT_TO_COOLING_LOAD_ENVELOPE_AUTO_FEED=NO" in adr_028
    assert "ENVELOPE_WALL_ROOF_FROM_PLAN=NO" in adr_035
    assert "FORMULA_RECUT_AUTHORIZED=NO" in adr_035


def test_v15_aily_still_must_not_import_calculations() -> None:
    for path in AILY_API_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "cold_storage.modules.calculations" not in text, path.name
        assert "five_stage_execution" not in text, path.name


def test_v15_v13_skill_stays_frozen_and_v15_skill_has_new_honesty() -> None:
    v13 = V13_SKILL_PATH.read_text(encoding="utf-8")
    v15 = V15_SKILL_PATH.read_text(encoding="utf-8")
    v15_json = V15_SKILL_JSON.read_text(encoding="utf-8")
    assert "envelope_wall_roof_from_plan: false" in v13
    assert "envelope_wall_roof_from_plan: true" in v15
    assert "正方形平面 + 演示层高" in v15
    assert "4 × √" not in v15
    assert "room_height × 4" not in v15
    assert '"envelope_wall_roof_from_plan": true' in v15_json
    assert '"FORMULA_RECUT_AUTHORIZED": "YES"' in v15_json
    mcp_text = (
        REPO_ROOT / "backend" / "src" / "cold_storage" / "modules" / "aily" / "api" / "mcp_sse.py"
    ).read_text(encoding="utf-8")
    assert "正方形平面 + 演示层高" in mcp_text
    assert "preview_zone_plan" in mcp_text

    needles = (
        "4 × √",
        "4 * Math.sqrt",
        "room_height * 4",
        "roomHeight * 4",
    )
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".vue", ".ts", ".js"}:
            continue
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            assert needle not in text, path.name
    assert BINDER.is_file()
