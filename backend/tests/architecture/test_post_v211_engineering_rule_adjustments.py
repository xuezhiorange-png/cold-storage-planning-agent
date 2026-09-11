"""Architecture locks for the current POST-v2.1.1 rule adjustment lane."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from cold_storage.modules.calculations.domain.factory_power_estimation import (
    CALCULATOR_IDENTITY,
    CALCULATOR_VERSION,
    DEFROST_SIMULTANEOUS_USE_FACTOR,
    POOL_A_SIMULTANEITY_FACTOR,
)
from cold_storage.modules.calculations.domain.zone_planning import (
    FORMULA_AUTHORITY,
    HISTORICAL_FORMULA_AUTHORITY,
    PRIMARY_PRECOOL_BATCHES_PER_DAY,
    PRIMARY_PRECOOL_Q_D_KG_DAY,
    PRIMARY_PRECOOL_WORKING_HOURS_PER_DAY,
    SORTING_PACKAGING_AREA_FACTOR,
    VERSION,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType

REPO_ROOT = Path(__file__).resolve().parents[3]
HISTORICAL_P1_CALCULATOR_VERSION = "2.0.0-p1"
HISTORICAL_P1_CALCULATOR_IDENTITY = "factory_power_estimation@2.0.0-p1"
TASK_PATH = REPO_ROOT / "docs/tasks/POST-V2_1_1-engineering-rule-adjustments.md"
ZONE_PLAN_PATH = REPO_ROOT / "backend/src/cold_storage/modules/calculations/domain/zone_planning.py"
FACTORY_POWER_PATH = (
    REPO_ROOT / "backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py"
)
FACTORY_POWER_PRESENTATION_PATH = (
    REPO_ROOT
    / "backend/src/cold_storage/modules/calculations/application/factory_power_presentation.py"
)
MCP_FACTORY_POWER_PATH = REPO_ROOT / "backend/src/cold_storage/modules/aily/api/mcp_sse.py"
FRONTEND_FACTORY_POWER_MAPPER_PATH = (
    REPO_ROOT / "frontend/src/features/calculations/model/mapFactoryPowerPresentation.ts"
)
PLANNING_SERVICE_PATH = (
    REPO_ROOT / "backend/src/cold_storage/modules/planning/application/service.py"
)


def test_post_v211_current_authority_and_parameter_locks() -> None:
    assert VERSION == "1.0.0"
    assert FORMULA_AUTHORITY == "POST-V2.1.1-charles-engineering-rule-adjustments"
    assert HISTORICAL_FORMULA_AUTHORITY == "POST-V0.9-P4-charles-zone-area-recut"
    assert PRIMARY_PRECOOL_BATCHES_PER_DAY == 7
    assert PRIMARY_PRECOOL_WORKING_HOURS_PER_DAY == 7
    assert PRIMARY_PRECOOL_Q_D_KG_DAY == 1540
    assert SORTING_PACKAGING_AREA_FACTOR == 1.1
    assert Decimal("0.20") == DEFROST_SIMULTANEOUS_USE_FACTOR
    assert POOL_A_SIMULTANEITY_FACTOR == DEFROST_SIMULTANEOUS_USE_FACTOR


def test_post_v211_preserves_calculator_identity_and_five_stage_boundary() -> None:
    assert CALCULATOR_IDENTITY == "factory_power_estimation@2.0.0-p2"
    assert CALCULATOR_VERSION == "2.0.0-p2"
    assert HISTORICAL_P1_CALCULATOR_IDENTITY == "factory_power_estimation@2.0.0-p1"
    assert HISTORICAL_P1_CALCULATOR_VERSION == "2.0.0-p1"
    assert [member.value for member in CalculationType] == [
        "zone",
        "cooling_load",
        "equipment",
        "power",
        "investment",
    ]


def test_post_v211_runtime_sources_expose_current_rule_authority() -> None:
    zone_plan = ZONE_PLAN_PATH.read_text(encoding="utf-8")
    factory_power = FACTORY_POWER_PATH.read_text(encoding="utf-8")
    presentation = FACTORY_POWER_PRESENTATION_PATH.read_text(encoding="utf-8")
    mcp = MCP_FACTORY_POWER_PATH.read_text(encoding="utf-8")
    frontend_mapper = FRONTEND_FACTORY_POWER_MAPPER_PATH.read_text(encoding="utf-8")
    planning_service = PLANNING_SERVICE_PATH.read_text(encoding="utf-8")

    assert 'FORMULA_AUTHORITY = "POST-V2.1.1-charles-engineering-rule-adjustments"' in zone_plan
    assert "PRIMARY_PRECOOL_BATCHES_PER_DAY = 7" in zone_plan
    assert "SORTING_PACKAGING_AREA_FACTOR = 1.1" in zone_plan
    assert 'DEFROST_SIMULTANEOUS_USE_FACTOR = Decimal("0.20")' in factory_power
    assert 'CALCULATOR_VERSION = "2.0.0-p2"' in factory_power
    assert 'RESULT_SCHEMA_VERSION = "2.0.0-p1"' in factory_power
    assert 'FACTORY_POWER_CALCULATOR_VERSION = "2.0.0-p2"' in presentation
    assert 'FACTORY_POWER_RESULT_SCHEMA_VERSION = "2.0.0-p1"' in presentation
    assert "factory_power_estimation@2.0.0-p2" in mcp
    assert "FACTORY_POWER_CALCULATOR_VERSION = '2.0.0-p2'" in frontend_mapper
    assert "float(DEFROST_SIMULTANEOUS_USE_FACTOR)" in planning_service
    assert "defrost_factor_percent" in planning_service
    assert "DEFROST_SIMULTANEOUS_USE_FACTOR * 100" in planning_service


def test_post_v211_task_evidence_records_history_and_scope_boundaries() -> None:
    task = TASK_PATH.read_text(encoding="utf-8")
    for marker in (
        "TASK_ID=POST_V2_1_1_ENGINEERING_RULE_ADJUSTMENTS_R1",
        "BASE_MAIN_SHA=c9ce6e7399ec2a163ab4c7c7339b828a86abbf08",
        "FORMULA_AUTHORITY_BEFORE=POST-V0.9-P4-charles-zone-area-recut",
        "FORMULA_AUTHORITY_AFTER=POST-V2.1.1-charles-engineering-rule-adjustments",
        "TASK_ID=POST_V2_1_1_ENGINEERING_RULE_ADJUSTMENTS_R2",
        "NEW_FACTORY_POWER_CALCULATOR_IDENTITY=factory_power_estimation@2.0.0-p2",
        "RESULT_SCHEMA_VERSION=2.0.0-p1",
        "HISTORICAL_P1_IDENTITY_PRESERVED=YES",
        "HISTORICAL_P1_FACTOR_PRESERVED=YES",
        "HISTORICAL_GOLDEN_CHANGED=NO",
        "MCP_TOOL_COUNT=6",
        "DATABASE_MIGRATION_CHANGED=NO",
        "READY_AUTHORIZED=NO",
        "MERGE_AUTHORIZED=NO",
        "NO_STEP_IMPLIES_THE_NEXT=TRUE",
    ):
        assert marker in task
