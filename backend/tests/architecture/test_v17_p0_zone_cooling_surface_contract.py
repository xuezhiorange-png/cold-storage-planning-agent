"""Architecture tests for V1.7 per-zone cooling component surface freeze."""

from __future__ import annotations

from pathlib import Path

from cold_storage.modules.calculations.domain.cooling_load import CALCULATOR_VERSION
from cold_storage.modules.calculations.domain.zone_planning import VERSION as ZONE_VERSION
from cold_storage.modules.orchestration.domain.dag import CALCULATOR_BINDINGS
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V1_7-P0-zone-cooling-surface-contract.md"
PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V1_7-version-plan.md"
ADR_PATH = REPO_ROOT / "docs" / "architecture" / "ADR-039-per-zone-cooling-component-surface.md"
V16_SKILL_PATH = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.6" / "doubao-skill.v1.md"
V17_SKILL_PATH = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.7" / "doubao-skill.v1.md"
V17_SKILL_JSON = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.7" / "doubao-skill.v1.json"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "v17-doubao-aily-connector.md"
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
ADAPTER = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "orchestration"
    / "application"
    / "production_calculation"
    / "adapters.py"
)
AILY_API_DIR = REPO_ROOT / "backend" / "src" / "cold_storage" / "modules" / "aily"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
SNAPSHOT = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "orchestration"
    / "application"
    / "source_snapshots.py"
)


def test_v17_plan_files_exist() -> None:
    assert CONTRACT_PATH.is_file()
    assert PLAN_PATH.is_file()
    assert ADR_PATH.is_file()
    assert V16_SKILL_PATH.is_file()
    assert V17_SKILL_PATH.is_file()
    assert V17_SKILL_JSON.is_file()
    assert RUNBOOK_PATH.is_file()


def test_v17_keeps_frozen_operator_keys_and_calculator_identities() -> None:
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
        "KEEP_AILY_V16_SKILL_FROZEN=YES",
        "KEEP_AILY_V17_SKILL=YES",
    ):
        assert flag in contract
        assert flag in plan
    assert CALCULATOR_BINDINGS["cooling_load"] == "cooling_load"


def test_v17_definition_freeze_surfaces_components_without_formula_recut() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    plan = PLAN_PATH.read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    for flag in (
        "V17_IMPLEMENTATION_AUTHORIZED=YES",
        "V17_P0_IMPLEMENTATION_AUTHORIZED=YES",
        "COOLING_ZONE_COMPONENT_SURFACE=YES",
        "FORMULA_RECUT_AUTHORIZED=NO",
        "ZONE_THERMAL_CATALOG_RECUT=NO",
        "KEEP_COOLING_LOAD_VERSION=YES",
        "AILY_OUTBOUND_LIVE_SESSION=NO",
        "AGENT_TO_ENGINEERING_VALUE=NO",
    ):
        assert flag in contract
        assert flag in plan
    assert "Accepted" in adr
    kernel = COOLING_KERNEL.read_text(encoding="utf-8")
    assert 'CALCULATOR_VERSION = "1.0.0"' in kernel
    adapter = ADAPTER.read_text(encoding="utf-8")
    assert "transmission_load_kw_r" in adapter
    assert "internal_load_kw_r" in adapter
    snapshot = SNAPSHOT.read_text(encoding="utf-8")
    assert "transmission_load_kw_r" in snapshot
    assert 'extra="forbid"' in snapshot


def test_v17_aily_does_not_import_calculations_or_embed_formulas() -> None:
    for path in AILY_API_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "cold_storage.modules.calculations" not in text, path.name
        assert "five_stage_execution" not in text, path.name
        assert "U × A × ΔT" not in text, path.name
        assert "U * A *" not in text, path.name
    needles = ("U × A × ΔT", "U * A *", "m × c × ΔT")
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".vue", ".ts", ".js"}:
            continue
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            assert needle not in text, path.name


def test_v17_v16_skill_stays_frozen_and_v17_skill_has_zone_audit() -> None:
    v16 = V16_SKILL_PATH.read_text(encoding="utf-8")
    v17 = V17_SKILL_PATH.read_text(encoding="utf-8")
    v17_json = V17_SKILL_JSON.read_text(encoding="utf-8")
    assert "v05 演示目录（10 / 8 kW(e)）" in v16
    assert "分区冷量按内核五项加总" in v17
    assert "正方形平面 + 演示层高" in v17
    assert "U × A" not in v17
    assert '"schema_version": "1.7.0"' in v17_json
    assert '"KEEP_AILY_V16_SKILL_FROZEN": "YES"' in v17_json
    assert '"ZONE_THERMAL_CATALOG_RECUT": "NO"' in v17_json
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "五项" in runbook
    assert "AILY_OUTBOUND_LIVE_SESSION=NO" in runbook
    mcp_text = (
        REPO_ROOT / "backend" / "src" / "cold_storage" / "modules" / "aily" / "api" / "mcp_sse.py"
    ).read_text(encoding="utf-8")
    assert "分区冷量按内核五项加总" in mcp_text
    assert "正方形平面 + 演示层高" in mcp_text
