"""Architecture tests for V1.4 workbench debt definition freeze."""

from __future__ import annotations

from pathlib import Path

from cold_storage.modules.calculations.domain.zone_planning import VERSION as ZONE_VERSION
from cold_storage.modules.orchestration.domain.dag import CALCULATOR_BINDINGS
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)
from cold_storage.modules.workflow.domain.steps import (
    OPERATOR_PROCESS_INPUT_STEP,
    WORKFLOW_CONTRACT_VERSION,
    WORKFLOW_STEPS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V1_4-P0-workbench-debt-contract.md"
PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V1_4-version-plan.md"
ADR_PATH = (
    REPO_ROOT / "docs" / "architecture" / "ADR-036-workbench-operator-input-and-demo-defaults.md"
)
AILY_API_DIR = REPO_ROOT / "backend" / "src" / "cold_storage" / "modules" / "aily"
V13_SKILL_PATH = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.3" / "doubao-skill.v1.md"
V09_MANIFEST = REPO_ROOT / "samples" / "v09-process-input" / "manifest.json"


def test_v14_plan_files_exist() -> None:
    assert CONTRACT_PATH.is_file()
    assert PLAN_PATH.is_file()
    assert ADR_PATH.is_file()
    assert V13_SKILL_PATH.is_file()
    assert V09_MANIFEST.is_file()


def test_v14_keeps_frozen_operator_keys_and_calculator_identities() -> None:
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
        assert identity in contract
        assert identity in plan
    for flag in (
        "KEEP_ZONE_PLAN_VERSION=YES",
        "KEEP_COOLING_LOAD_VERSION=YES",
        "KEEP_EQUIPMENT_VERSION=YES",
        "KEEP_INSTALLED_POWER_VERSION=YES",
        "KEEP_INVESTMENT_VERSION=YES",
        "KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0",
        "KEEP_AILY_V13_SKILL=YES",
    ):
        assert flag in contract
        assert flag in plan
    assert CALCULATOR_BINDINGS["zone"] == "cold_room_zone_plan"
    assert CALCULATOR_BINDINGS["cooling_load"] == "cooling_load"
    assert CALCULATOR_BINDINGS["equipment"] == "equipment"
    assert CALCULATOR_BINDINGS["power"] == "installed_power"
    assert CALCULATOR_BINDINGS["investment"] == "investment_estimate"


def test_v14_definition_freeze_keeps_non_goals_and_authorization() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    plan = PLAN_PATH.read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    for flag in (
        "V14_IMPLEMENTATION_AUTHORIZED=YES",
        "V14_P0_IMPLEMENTATION_AUTHORIZED=YES",
        "TD023_OPERATOR_PROCESS_INPUT_STEP=YES",
        "TD008_OPERATOR_DEMO_FIVE_KEY_AUTHORITY=YES",
        "TD008_POWER_EQUIPMENT_CATALOG_UNIFIED=NO",
        "FORMULA_RECUT_AUTHORIZED=NO",
        "COOLING_LOAD_FORMULA_RECUT=NO",
        "ENVELOPE_WALL_ROOF_FROM_PLAN=NO",
        "AILY_OUTBOUND_LIVE_SESSION=NO",
        "DELETE_PATH_A_SAVE_INPUTS=NO",
        "POWER_CONFIGURATION_REPLACES_INSTALLED_POWER=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
        "AGENT_TO_ENGINEERING_VALUE=NO",
    ):
        assert flag in contract
        assert flag in plan
    assert "Accepted" in adr
    assert "OPERATOR_PROCESS_INPUT" in plan
    assert "WorkflowAggregateV2" in contract
    assert "samples/v09-process-input/manifest.json" in contract
    assert "20000" in plan
    assert "save_inputs" in plan


def test_v14_aily_still_must_not_import_calculations() -> None:
    for path in AILY_API_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "cold_storage.modules.calculations" not in text, path.name
        assert "five_stage_execution" not in text, path.name


def test_v14_workflow_step_and_demo_authority_are_wired() -> None:
    assert WORKFLOW_CONTRACT_VERSION == "WorkflowAggregateV2"
    assert WORKFLOW_STEPS[0] == OPERATOR_PROCESS_INPUT_STEP
    assert "PROJECT_INPUT" not in WORKFLOW_STEPS
    steps_text = (
        REPO_ROOT
        / "backend"
        / "src"
        / "cold_storage"
        / "modules"
        / "workflow"
        / "domain"
        / "steps.py"
    ).read_text(encoding="utf-8")
    assert "PROJECT_INPUT" not in steps_text
    catalog = (
        REPO_ROOT / "frontend" / "src" / "features" / "design-inputs" / "parameterCatalog.ts"
    ).read_text(encoding="utf-8")
    assert "25000" not in catalog
    assert "'2.5'" not in catalog
    assert "operatorDemoZoneValue" in catalog
    design_inputs = (
        REPO_ROOT / "frontend" / "src" / "features" / "project" / "model" / "designInputs.ts"
    ).read_text(encoding="utf-8")
    assert "finishedStorageDays: 2.5" not in design_inputs
    assert "operatorDemoZoneNumeric" in design_inputs
    app_text = (REPO_ROOT / "backend" / "src" / "cold_storage" / "bootstrap" / "app.py").read_text(
        encoding="utf-8"
    )
    assert "/api/v1/demo/operator-process-input" in app_text
    panel = (
        REPO_ROOT
        / "frontend"
        / "src"
        / "features"
        / "workflow"
        / "components"
        / "WorkflowGuidancePanel.vue"
    ).read_text(encoding="utf-8")
    assert "OPERATOR_PROCESS_INPUT" in panel
    assert "'PROJECT_INPUT'" not in panel
