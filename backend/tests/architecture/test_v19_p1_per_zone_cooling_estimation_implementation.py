"""Architecture contracts for the separately authorized V1.9 P1 runtime slice."""

from __future__ import annotations

import json
import re
import subprocess
from decimal import Decimal
from pathlib import Path

from cold_storage.modules.calculations.domain.cooling_load import (
    CALCULATOR_VERSION as COOLING_LOAD_VERSION,
)
from cold_storage.modules.calculations.domain.per_zone_cooling_estimation import (
    AUTHORITY_SOURCE,
    EXPECTED_REFRIGERATED_ZONE_CODES,
    MINIMUM_OUTPUT_FIELD,
    PER_ZONE_COOLING_ESTIMATION_RULES,
    PROVENANCE_FIELD,
)
from cold_storage.modules.calculations.domain.zone_planning import VERSION as ZONE_PLAN_VERSION
from cold_storage.modules.orchestration.domain.contracts import CalculationType
from cold_storage.modules.orchestration.domain.dag import CALCULATOR_BINDINGS

REPO_ROOT = Path(__file__).resolve().parents[3]
P0_CONTRACT_PATH = (
    REPO_ROOT / "docs" / "tasks" / "V1_9-P0-per-zone-cooling-estimation-basis-contract.md"
)
P1_TASK_PATH = (
    REPO_ROOT / "docs" / "tasks" / "V1_9-P1-per-zone-cooling-estimation-implementation.md"
)
VERSION_PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V1_9-version-plan.md"
CURRENT_STATE_PATH = REPO_ROOT / "docs" / "audit" / "current-state.md"
ADR_PATH = REPO_ROOT / "docs" / "architecture" / "ADR-041-per-zone-cooling-estimation-basis.md"
RUNTIME_MODULE_PATH = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "calculations"
    / "domain"
    / "per_zone_cooling_estimation.py"
)
ZONE_PLANNER_PATH = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "calculations"
    / "domain"
    / "zone_planning.py"
)
SOURCE_SNAPSHOT_PATH = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "orchestration"
    / "application"
    / "source_snapshots.py"
)
COOLING_LOAD_PATH = ZONE_PLANNER_PATH.with_name("cooling_load.py")

EXPECTED_CHANGED_PATHS = {
    "backend/src/cold_storage/modules/calculations/domain/per_zone_cooling_estimation.py",
    "backend/src/cold_storage/modules/calculations/domain/zone_planning.py",
    "backend/src/cold_storage/modules/orchestration/application/source_snapshots.py",
    "backend/src/cold_storage/modules/reports/infrastructure/real_data_provider.py",
    "backend/tests/architecture/test_v19_p0_per_zone_cooling_estimation_basis_contract.py",
    "backend/tests/architecture/test_v19_p1_per_zone_cooling_estimation_implementation.py",
    "backend/tests/integration/test_v19_p1_per_zone_cooling_estimation.py",
    "backend/tests/golden/v07_cross_consumer_v1.json",
    "backend/tests/test_v03_p1_report_unit_quality.py",
    "backend/tests/unit/test_real_report_data_provider.py",
    "backend/tests/unit/test_v19_p1_per_zone_cooling_estimation.py",
    "docs/architecture/ADR-041-per-zone-cooling-estimation-basis.md",
    "docs/TECH_DEBT.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/tasks/V1_9-P1-per-zone-cooling-estimation-implementation.md",
    "docs/tasks/V1_9-version-plan.md",
}
V19_LANE_MARKERS = {
    "docs/tasks/V1_9-version-plan.md",
    "docs/tasks/V1_9-P0-per-zone-cooling-estimation-basis-contract.md",
    "docs/tasks/V1_9-P1-per-zone-cooling-estimation-implementation.md",
    "docs/architecture/ADR-041-per-zone-cooling-estimation-basis.md",
}


def _changed_paths() -> set[str]:
    merge_base = subprocess.run(
        ["git", "merge-base", "origin/main", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert merge_base
    diff = subprocess.run(
        ["git", "diff", "--name-only", merge_base, "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.strip() for line in diff.stdout.splitlines() if line.strip()}


def _p0_data() -> dict[str, object]:
    text = P0_CONTRACT_PATH.read_text(encoding="utf-8")
    match = re.search(r"```json\n(.*?)\n```", text, flags=re.DOTALL)
    assert match is not None
    parsed = json.loads(match.group(1))
    assert isinstance(parsed, dict)
    return parsed


def test_p1_documents_and_scope_are_present() -> None:
    assert P0_CONTRACT_PATH.is_file()
    assert P1_TASK_PATH.is_file()
    assert VERSION_PLAN_PATH.is_file()
    assert CURRENT_STATE_PATH.is_file()
    assert ADR_PATH.is_file()
    changed = _changed_paths()
    if changed.intersection(V19_LANE_MARKERS):
        assert changed <= EXPECTED_CHANGED_PATHS


def test_p1_is_separately_authorized_without_rewriting_p0_history() -> None:
    p0 = _p0_data()
    p1 = P1_TASK_PATH.read_text(encoding="utf-8")
    plan = VERSION_PLAN_PATH.read_text(encoding="utf-8")
    current_state = CURRENT_STATE_PATH.read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")

    assert p0["authorization"]["RUNTIME_IMPLEMENTATION_AUTHORIZED"] == "NO"
    assert "V1.9 P1 is not authorized" in P0_CONTRACT_PATH.read_text(encoding="utf-8")
    for text in (p1, plan, current_state, adr):
        assert "V19_P1_IMPLEMENTATION_AUTHORIZED=YES" in text
        assert "P0_CONTRACT_FROZEN=YES" in text
        assert "P1_IMPLEMENTATION_SEPARATELY_AUTHORIZED=YES" in text
    assert "V19_P1_IMPLEMENTATION_EXECUTED=YES" in p1


def test_runtime_registry_matches_the_p0_machine_readable_rules() -> None:
    p0 = _p0_data()
    p0_rules = {rule["zone_code"]: rule for rule in p0["zone_rules"]}
    assert set(p0_rules) == EXPECTED_REFRIGERATED_ZONE_CODES
    assert set(PER_ZONE_COOLING_ESTIMATION_RULES) == set(p0_rules)
    assert len(PER_ZONE_COOLING_ESTIMATION_RULES) == 9

    expected_kw_r_factor = {
        "primary_precooling_room": Decimal("20"),
        "secondary_precooling_room": Decimal("15"),
        "raw_fruit_buffer": Decimal("0.40"),
        "sorting_packaging_room": Decimal("0.30"),
        "coating_room": Decimal("0.30"),
        "finished_goods_room": Decimal("0.30"),
        "secondary_fruit_buffer": Decimal("0.40"),
        "frozen_fruit_room": Decimal("0.55"),
        "shipping_channel": Decimal("0.30"),
    }
    for code, p0_rule in p0_rules.items():
        runtime_rule = PER_ZONE_COOLING_ESTIMATION_RULES[code]
        assert runtime_rule.basis_type == p0_rule["basis"]
        assert runtime_rule.source_field == p0_rule["source_field"]
        assert int(runtime_rule.reference_factor or 0) == p0_rule["reference_factor"]
        assert runtime_rule.reference_factor_unit == p0_rule["reference_factor_unit"]
        assert runtime_rule.minimum_factor_kw_r == expected_kw_r_factor[code]
        assert runtime_rule.authority_source == AUTHORITY_SOURCE
        assert runtime_rule.requires_review is True


def test_p1_adds_only_the_minimum_surface_and_keeps_five_stage_boundaries() -> None:
    runtime_text = RUNTIME_MODULE_PATH.read_text(encoding="utf-8")
    planner_text = ZONE_PLANNER_PATH.read_text(encoding="utf-8")
    source_snapshot_text = SOURCE_SNAPSHOT_PATH.read_text(encoding="utf-8")
    cooling_load_text = COOLING_LOAD_PATH.read_text(encoding="utf-8")
    p1_text = P1_TASK_PATH.read_text(encoding="utf-8")

    assert MINIMUM_OUTPUT_FIELD in runtime_text
    assert PROVENANCE_FIELD in runtime_text
    assert "raw_position_count" not in runtime_text
    assert "modules.calculations.domain.cooling_load" not in runtime_text
    assert "apply_per_zone_cooling_estimation" in planner_text
    assert "minimum_estimated_cooling_load_kw_r" in source_snapshot_text
    assert "cooling_estimation_basis" in source_snapshot_text
    assert 'source_snapshot_schema_version: Literal["1.0.0"]' in source_snapshot_text
    assert "selected_cooling_capacity" not in runtime_text
    assert "design_cooling_capacity" not in runtime_text
    assert "equipment_capacity" not in runtime_text
    assert "max(existing_cooling_load" not in runtime_text
    assert "Q = U × A × ΔT" in cooling_load_text
    assert 'CALCULATOR_VERSION = "1.0.0"' in cooling_load_text
    assert ZONE_PLAN_VERSION == "1.0.0"
    assert COOLING_LOAD_VERSION == "1.0.0"
    assert len(CalculationType) == 5
    assert CALCULATOR_BINDINGS == {
        "zone": "cold_room_zone_plan",
        "cooling_load": "cooling_load",
        "equipment": "equipment",
        "power": "installed_power",
        "investment": "investment_estimate",
    }
    for flag in (
        "EQUIPMENT_INPUT_CHANGED=NO",
        "POWER_INPUT_CHANGED=NO",
        "INVESTMENT_INPUT_CHANGED=NO",
        "SOURCE_SNAPSHOT_SCHEMA_PRESERVES_V19_FIELDS=YES",
        "FRONTEND_CHANGED=NO",
        "MIGRATION_CREATED=NO",
        "COOLING_LOAD_FORMULA_RECUT=NO",
    ):
        assert flag in p1_text


def test_p1_scope_has_no_forbidden_runtime_surfaces() -> None:
    paths = _changed_paths()
    if not paths.intersection(V19_LANE_MARKERS):
        return
    forbidden = {
        "backend/src/cold_storage/modules/calculations/domain/cooling_load.py",
        "backend/src/cold_storage/modules/calculations/domain/equipment.py",
        "backend/src/cold_storage/modules/calculations/domain/power.py",
        "backend/src/cold_storage/modules/calculations/domain/investment.py",
    }
    assert paths.isdisjoint(forbidden)
    assert not any(path.startswith("frontend/") for path in paths)
    assert not any(path.startswith("migrations/") for path in paths)
