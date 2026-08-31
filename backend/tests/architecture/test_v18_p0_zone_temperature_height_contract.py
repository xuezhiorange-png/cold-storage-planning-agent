"""Architecture tests for V1.8 per-zone temperature and height."""

from __future__ import annotations

from pathlib import Path

from cold_storage.modules.calculations.domain.cooling_load import CALCULATOR_VERSION
from cold_storage.modules.calculations.domain.zone_planning import VERSION as ZONE_VERSION
from cold_storage.modules.orchestration.domain.dag import CALCULATOR_BINDINGS
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V1_8-P0-zone-temperature-height-contract.md"
PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V1_8-version-plan.md"
ADR_PATH = REPO_ROOT / "docs" / "architecture" / "ADR-040-per-zone-temperature-height-surface.md"
V17_SKILL_PATH = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.7" / "doubao-skill.v1.md"
V17_SKILL_JSON = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.7" / "doubao-skill.v1.json"
V18_SKILL_PATH = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.8" / "doubao-skill.v1.md"
V18_SKILL_JSON = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.8" / "doubao-skill.v1.json"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "v18-doubao-aily-connector.md"
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
CATALOG = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "projects"
    / "application"
    / "demo_zone_thermal_catalog.py"
)
COOLING_TABLE = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "aily"
    / "application"
    / "cooling_load_table.py"
)
MCP_SSE = REPO_ROOT / "backend" / "src" / "cold_storage" / "modules" / "aily" / "api" / "mcp_sse.py"
FRONTEND_LABELS = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "features"
    / "calculations"
    / "components"
    / "persistedResultLabels.ts"
)
AILY_API_DIR = REPO_ROOT / "backend" / "src" / "cold_storage" / "modules" / "aily"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"


def test_v18_plan_files_exist() -> None:
    assert CONTRACT_PATH.is_file()
    assert PLAN_PATH.is_file()
    assert ADR_PATH.is_file()
    assert V17_SKILL_PATH.is_file()
    assert V17_SKILL_JSON.is_file()
    assert V18_SKILL_PATH.is_file()
    assert V18_SKILL_JSON.is_file()
    assert RUNBOOK_PATH.is_file()
    assert CATALOG.is_file()


def test_v18_keeps_frozen_operator_keys_and_calculator_identities() -> None:
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
        "KEEP_AILY_V17_SKILL_FROZEN=YES",
        "KEEP_AILY_V18_SKILL=YES",
    ):
        assert flag in contract
        assert flag in plan
    assert CALCULATOR_BINDINGS["cooling_load"] == "cooling_load"


def test_v18_implementation_authorized_stamps_cold_end_and_four_meter_height() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    plan = PLAN_PATH.read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    for flag in (
        "V18_IMPLEMENTATION_AUTHORIZED=YES",
        "V18_P0_IMPLEMENTATION_AUTHORIZED=YES",
        "ZONE_THERMAL_INPUT_SURFACE=YES",
        "ZONE_TEMPERATURE_FROM_ZONE_PLAN_BAND=YES",
        "ZONE_TEMPERATURE_BAND_POINT=COLD_END",
        "ZONE_TEMPERATURE_CATALOG_RECUT=YES",
        "ZONE_HEIGHT_CATALOG_RECUT=YES",
        "ZONE_PRODUCT_MASS_CATALOG_RECUT=NO",
        "ZONE_THERMAL_CATALOG_RECUT=NO",
        "FORMULA_RECUT_AUTHORIZED=NO",
        "KEEP_COOLING_LOAD_VERSION=YES",
        "AILY_OUTBOUND_LIVE_SESSION=NO",
        "AGENT_TO_ENGINEERING_VALUE=NO",
    ):
        assert flag in contract
        assert flag in plan
    assert "Accepted" in adr
    kernel = COOLING_KERNEL.read_text(encoding="utf-8")
    assert 'CALCULATOR_VERSION = "1.0.0"' in kernel
    assert "Q = U × A × ΔT" in kernel
    catalog = CATALOG.read_text(encoding="utf-8")
    assert 'ROOM_HEIGHT_M = "4.0"' in catalog
    assert '"8~10℃": "8.0"' in catalog
    assert '"1~3℃": "1.0"' in catalog
    assert '"-18℃": "-18.0"' in catalog
    assembler = ASSEMBLER.read_text(encoding="utf-8")
    assert "_WORKBENCH_ROOM_DESIGN_TEMPERATURE_C" not in assembler
    assert "V18_T1_SOURCE" in assembler
    assert "V18_H1_SOURCE" in assembler
    assert "room_design_temperature_c_for_band" in assembler
    assert "ROOM_HEIGHT_M" in assembler
    adapter = ADAPTER.read_text(encoding="utf-8")
    assert "room_design_temperature" in adapter
    assert "room_height" in adapter
    snapshot = SNAPSHOT.read_text(encoding="utf-8")
    assert "room_design_temperature" in snapshot
    assert "room_height" in snapshot
    assert 'extra="forbid"' in snapshot
    assert "room_design_temperature" in plan
    assert "room_height" in plan
    assert "4.0 m" in plan
    assert "V18-H1" in plan
    assert "V18-T1" in plan
    assert "8.0 °C" in plan
    assert "1.0 °C" in plan
    assert "COLD_END" in plan
    assert "*待填*" not in plan


def test_v18_aily_does_not_import_calculations_or_embed_formulas() -> None:
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


def test_v18_v17_skill_stays_frozen_and_v18_skill_has_temp_height() -> None:
    v17 = V17_SKILL_PATH.read_text(encoding="utf-8")
    v17_json = V17_SKILL_JSON.read_text(encoding="utf-8")
    v18 = V18_SKILL_PATH.read_text(encoding="utf-8")
    v18_json = V18_SKILL_JSON.read_text(encoding="utf-8")
    assert "分区冷量按内核五项加总" in v17
    assert "正方形平面 + 演示层高" in v17
    assert "U × A" not in v17
    assert '"schema_version": "1.7.0"' in v17_json
    assert '"ZONE_THERMAL_CATALOG_RECUT": "NO"' in v17_json
    assert '"KEEP_COOLING_LOAD_VERSION": "YES"' in v17_json
    assert "1.8.0" in v18
    assert "温区低端" in v18
    assert "4.0 m" in v18
    assert "U × A" not in v18
    assert '"schema_version": "1.8.0"' in v18_json
    assert '"ZONE_TEMPERATURE_BAND_POINT": "COLD_END"' in v18_json
    assert '"ZONE_HEIGHT_CATALOG_RECUT": "YES"' in v18_json
    assert '"ZONE_PRODUCT_MASS_CATALOG_RECUT": "NO"' in v18_json
    assert '"KEEP_AILY_V17_SKILL_FROZEN": "YES"' in v18_json
    plan = PLAN_PATH.read_text(encoding="utf-8")
    assert "docs/contracts/aily/v1.7/**" in plan
    assert "ZONE_TEMPERATURE_FROM_ZONE_PLAN_BAND=YES" in plan
    assert "ZONE_TEMPERATURE_BAND_POINT=COLD_END" in plan
    assert "ZONE_TEMPERATURE_CATALOG_RECUT=YES" in plan
    assert "ZONE_TEMPERATURE_CATALOG_RECUT=NO" not in plan
    assert "ZONE_HEIGHT_CATALOG_RECUT=YES" in plan
    assert "ZONE_HEIGHT_CATALOG_RECUT=NO" not in plan
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "温区低端" in runbook
    assert "4.0 m" in runbook
    assert "AILY_OUTBOUND_LIVE_SESSION=NO" in runbook
    cooling_table = COOLING_TABLE.read_text(encoding="utf-8")
    assert "分区冷量按内核五项加总" in cooling_table
    assert "正方形平面 + 演示层高" in cooling_table
    assert "U 值与设计温度仍为演示目录" in cooling_table
    assert "ZONE_THERMAL_CATALOG_DISCLAIMER_ZH" in cooling_table
    mcp_text = MCP_SSE.read_text(encoding="utf-8")
    assert "COOLING_CAPTION" in mcp_text
    assert "分区冷量按内核五项加总" in mcp_text
    assert "正方形平面 + 演示层高" in mcp_text
    assert "室内设计温度取分区规划温区低端" in mcp_text
    assert "4.0 m" in mcp_text
    labels = FRONTEND_LABELS.read_text(encoding="utf-8")
    assert "room_design_temperature" in labels
    assert "room_height" in labels
    assert "室内设计温度" in labels
    assert "层高" in labels
