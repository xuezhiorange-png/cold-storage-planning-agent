"""Architecture tests for V1.9 per-zone cooling formula audit freeze."""

from __future__ import annotations

from pathlib import Path

from cold_storage.modules.calculations.domain.cooling_load import CALCULATOR_VERSION
from cold_storage.modules.calculations.domain.zone_planning import VERSION as ZONE_VERSION
from cold_storage.modules.orchestration.domain.dag import CALCULATOR_BINDINGS
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V1_9-P0-zone-cooling-formula-audit-contract.md"
PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V1_9-version-plan.md"
ADR_PATH = REPO_ROOT / "docs" / "architecture" / "ADR-041-per-zone-cooling-formula-audit.md"
V18_SKILL_PATH = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.8" / "doubao-skill.v1.md"
V18_SKILL_JSON = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.8" / "doubao-skill.v1.json"
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


def test_v19_plan_files_exist() -> None:
    assert CONTRACT_PATH.is_file()
    assert PLAN_PATH.is_file()
    assert ADR_PATH.is_file()
    assert V18_SKILL_PATH.is_file()
    assert V18_SKILL_JSON.is_file()


def test_v19_keeps_frozen_operator_keys_and_calculator_identities() -> None:
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
        "KEEP_AILY_V18_SKILL_FROZEN=YES",
        "KEEP_AILY_V19_SKILL=YES",
    ):
        assert flag in contract
        assert flag in plan
    assert CALCULATOR_BINDINGS["cooling_load"] == "cooling_load"


def test_v19_definition_freeze_surfaces_steps_without_formula_recut() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    plan = PLAN_PATH.read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    for flag in (
        "V19_IMPLEMENTATION_AUTHORIZED=NO",
        "V19_P0_IMPLEMENTATION_AUTHORIZED=NO",
        "COOLING_ZONE_FORMULA_AUDIT_SURFACE=YES",
        "FORMULA_RECUT_AUTHORIZED=NO",
        "ZONE_PRODUCT_MASS_CATALOG_RECUT=NO",
        "ZONE_THERMAL_CATALOG_RECUT=NO",
        "KEEP_COOLING_LOAD_VERSION=YES",
        "AILY_OUTBOUND_LIVE_SESSION=NO",
        "AGENT_TO_ENGINEERING_VALUE=NO",
    ):
        assert flag in contract
        assert flag in plan
    assert "Proposed" in adr
    assert "Accepted" not in adr.split("Status:", 1)[-1].splitlines()[0]
    kernel = COOLING_KERNEL.read_text(encoding="utf-8")
    assert 'CALCULATOR_VERSION = "1.0.0"' in kernel
    assert "Q = U × A × ΔT" in kernel
    adapter = ADAPTER.read_text(encoding="utf-8")
    assert "def _build_steps(" in adapter
    assert "zone_formula_steps" not in adapter
    assert "CalculationStep" in plan
    assert "逐个区域核算" in plan or "核算冷量计算" in plan


def test_v19_aily_does_not_import_calculations_or_embed_formulas() -> None:
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


def test_v19_v18_skill_stays_frozen_without_formula_recut() -> None:
    v18 = V18_SKILL_PATH.read_text(encoding="utf-8")
    v18_json = V18_SKILL_JSON.read_text(encoding="utf-8")
    assert "温区低端" in v18
    assert "4.0 m" in v18
    assert "U × A" not in v18
    assert '"schema_version": "1.8.0"' in v18_json
    assert '"KEEP_COOLING_LOAD_VERSION": "YES"' in v18_json
    assert '"FORMULA_RECUT_AUTHORIZED": "NO"' in v18_json
    plan = PLAN_PATH.read_text(encoding="utf-8")
    assert "docs/contracts/aily/v1.8/**" in plan
    assert "FORMULA_RECUT_AUTHORIZED=NO" in plan
    assert "V19_IMPLEMENTATION_AUTHORIZED=NO" in plan
    v19_skill = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.9" / "doubao-skill.v1.md"
    assert not v19_skill.exists()
