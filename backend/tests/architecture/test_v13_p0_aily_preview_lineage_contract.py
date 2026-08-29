"""Architecture tests for V1.3 Aily preview lineage definition freeze."""

from __future__ import annotations

from pathlib import Path

from cold_storage.modules.calculations.domain.zone_planning import VERSION as ZONE_VERSION
from cold_storage.modules.orchestration.domain.dag import CALCULATOR_BINDINGS
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V1_3-P0-aily-preview-lineage-contract.md"
PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V1_3-version-plan.md"
ADR_PATH = REPO_ROOT / "docs" / "architecture" / "ADR-035-aily-preview-workbench-lineage.md"
AILY_API_DIR = REPO_ROOT / "backend" / "src" / "cold_storage" / "modules" / "aily"


def test_v13_plan_files_exist() -> None:
    assert CONTRACT_PATH.is_file()
    assert PLAN_PATH.is_file()
    assert ADR_PATH.is_file()


def test_v13_keeps_frozen_operator_keys_and_calculator_identities() -> None:
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
    ):
        assert flag in contract
        assert flag in plan
    assert CALCULATOR_BINDINGS["zone"] == "cold_room_zone_plan"
    assert CALCULATOR_BINDINGS["cooling_load"] == "cooling_load"
    assert CALCULATOR_BINDINGS["equipment"] == "equipment"
    assert CALCULATOR_BINDINGS["power"] == "installed_power"
    assert CALCULATOR_BINDINGS["investment"] == "investment_estimate"


def test_v13_definition_freeze_keeps_non_goals_and_authorization() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    plan = PLAN_PATH.read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    for flag in (
        "V13_IMPLEMENTATION_AUTHORIZED=YES",
        "V13_P0_IMPLEMENTATION_AUTHORIZED=YES",
        "FORMULA_RECUT_AUTHORIZED=NO",
        "COOLING_LOAD_FORMULA_RECUT=NO",
        "ENVELOPE_WALL_ROOF_FROM_PLAN=NO",
        "ENVELOPE_FROM_ZONE_AREA=floor_and_zone_area_only",
        "AILY_OUTBOUND_LIVE_SESSION=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
        "AGENT_TO_ENGINEERING_VALUE=NO",
    ):
        assert flag in contract
        assert flag in plan
    assert "Accepted" in adr
    assert "floor_area" in plan
    assert "required_area_m2" in plan


def test_v13_aily_still_must_not_import_calculations() -> None:
    for path in AILY_API_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "cold_storage.modules.calculations" not in text, path.name
