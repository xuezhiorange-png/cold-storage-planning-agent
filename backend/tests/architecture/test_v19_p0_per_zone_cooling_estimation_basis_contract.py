"""Architecture tests for the V1.9 P0 per-zone cooling basis contract."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = (
    REPO_ROOT / "docs" / "tasks" / "V1_9-P0-per-zone-cooling-estimation-basis-contract.md"
)
PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V1_9-version-plan.md"
ADR_PATH = REPO_ROOT / "docs" / "architecture" / "ADR-041-per-zone-cooling-estimation-basis.md"

TEST_PATH = "backend/tests/architecture/test_v19_p0_per_zone_cooling_estimation_basis_contract.py"
ALLOWED_PATHS = {
    "docs/tasks/V1_9-version-plan.md",
    "docs/tasks/V1_9-P0-per-zone-cooling-estimation-basis-contract.md",
    "docs/architecture/ADR-041-per-zone-cooling-estimation-basis.md",
    "docs/TECH_DEBT.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    TEST_PATH,
}

EXPECTED_RULES = {
    "primary_precooling_room": {
        "basis": "FINAL_POSITION_COUNT",
        "source_field": "position_count",
        "reference_factor": 20,
        "reference_factor_unit": "kW(r)/final position",
        "formula": "position_count * 20",
    },
    "secondary_precooling_room": {
        "basis": "FINAL_POSITION_COUNT",
        "source_field": "position_count",
        "reference_factor": 15,
        "reference_factor_unit": "kW(r)/final position",
        "formula": "position_count * 15",
    },
    "raw_fruit_buffer": {
        "basis": "ZONE_AREA",
        "source_field": "required_area_m2",
        "reference_factor": 400,
        "reference_factor_unit": "W/m2",
        "formula": "required_area_m2 * 0.40",
    },
    "sorting_packaging_room": {
        "basis": "ZONE_AREA",
        "source_field": "required_area_m2",
        "reference_factor": 300,
        "reference_factor_unit": "W/m2",
        "formula": "required_area_m2 * 0.30",
    },
    "coating_room": {
        "basis": "ZONE_AREA",
        "source_field": "required_area_m2",
        "reference_factor": 300,
        "reference_factor_unit": "W/m2",
        "formula": "required_area_m2 * 0.30",
    },
    "finished_goods_room": {
        "basis": "ZONE_AREA",
        "source_field": "required_area_m2",
        "reference_factor": 300,
        "reference_factor_unit": "W/m2",
        "formula": "required_area_m2 * 0.30",
    },
    "secondary_fruit_buffer": {
        "basis": "ZONE_AREA",
        "source_field": "required_area_m2",
        "reference_factor": 400,
        "reference_factor_unit": "W/m2",
        "formula": "required_area_m2 * 0.40",
    },
    "frozen_fruit_room": {
        "basis": "ZONE_AREA",
        "source_field": "required_area_m2",
        "reference_factor": 550,
        "reference_factor_unit": "W/m2",
        "formula": "required_area_m2 * 0.55",
    },
    "shipping_channel": {
        "basis": "ZONE_AREA",
        "source_field": "required_area_m2",
        "reference_factor": 300,
        "reference_factor_unit": "W/m2",
        "formula": "required_area_m2 * 0.30",
    },
}


def _contract_text() -> str:
    return CONTRACT_PATH.read_text(encoding="utf-8")


def _contract_data() -> dict[str, object]:
    match = re.search(r"```json\n(.*?)\n```", _contract_text(), flags=re.DOTALL)
    assert match is not None, "contract must contain a canonical JSON rule matrix"
    parsed = json.loads(match.group(1))
    assert isinstance(parsed, dict)
    return parsed


def _changed_paths() -> set[str]:
    diff = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return {
        line.strip()
        for output in (diff.stdout, untracked.stdout)
        for line in output.splitlines()
        if line.strip()
    }


def test_v19_p0_contract_files_exist_and_scope_is_docs_only() -> None:
    assert CONTRACT_PATH.is_file()
    assert PLAN_PATH.is_file()
    assert ADR_PATH.is_file()
    for path in (PLAN_PATH, ADR_PATH):
        text = path.read_text(encoding="utf-8")
        assert "PER_ZONE_COOLING_ESTIMATION_BASIS" in text
        assert "minimum_estimated_cooling_load_kw_r" in text
        assert "required_area_m2" in text
        assert "RUNTIME_IMPLEMENTATION_AUTHORIZED=NO" in text
    assert _changed_paths() <= ALLOWED_PATHS


def test_v19_p0_freezes_nine_authoritative_rules() -> None:
    data = _contract_data()
    assert data["direction"] == "PER_ZONE_COOLING_ESTIMATION_BASIS"
    assert data["output_field"] == "minimum_estimated_cooling_load_kw_r"
    assert data["output_relation"] == (
        "minimum_estimated_cooling_load_kw_r = frozen_reference_basis"
    )
    assert data["area_semantic"] == "PLANNED_ZONE_AREA"
    assert data["area_source_field"] == "required_area_m2"
    assert data["authority_source"] == "CHARLES_CONFIRMED_ENGINEERING_REFERENCE"

    rules = data["zone_rules"]
    assert isinstance(rules, list)
    assert len(rules) == 9
    by_zone = {rule["zone_code"]: rule for rule in rules}
    assert set(by_zone) == set(EXPECTED_RULES)
    for zone_code, expected in EXPECTED_RULES.items():
        rule = by_zone[zone_code]
        assert "reference_factor" in rule
        assert "reference_factor_unit" in rule
        assert "reference" not in rule
        assert "reference_unit" not in rule
        assert rule["requires_review"] is True
        for key, value in expected.items():
            assert rule[key] == value
        assert rule["result_semantics"] == "MINIMUM_ESTIMATE"
    assert by_zone["primary_precooling_room"]["forbidden_source_fields"] == ["raw_position_count"]
    assert by_zone["secondary_precooling_room"]["forbidden_source_fields"] == ["raw_position_count"]


def test_v19_p0_locks_minimum_semantics_fail_closed_and_authorization() -> None:
    data = _contract_data()
    semantic_lock = data["semantic_lock"]
    assert semantic_lock["minimum_estimate_semantics"] == "YES"
    assert semantic_lock["minimum_computed_value_relation"] == (
        "minimum_estimated_cooling_load_kw_r = frozen_reference_basis"
    )
    assert semantic_lock["engineering_reference_relation"] == (
        "required cooling capacity >= frozen_reference_basis"
    )
    assert semantic_lock["engineering_required_capacity_is_lower_bound"] is True
    assert "minimum estimated cooling load" in semantic_lock["allowed_terms"]
    assert "最低估算制冷量" in semantic_lock["allowed_terms"]
    assert "exact cooling load" in semantic_lock["forbidden_terms"]

    fail_closed = data["fail_closed"]
    assert set(fail_closed["missing_or_unmapped_inputs"]) == {
        "position_count",
        "required_area_m2",
        "zone_code",
        "reference_factor",
    }
    assert {
        "raw_position_count",
        "demo thermal catalog",
        "U × A × ΔT",
        "product sensible heat",
        "infiltration model",
        "legacy cooling output",
        "AI guessed values",
        "arbitrary defaults",
    } <= set(fail_closed["forbidden_fallbacks"])

    authorization = data["authorization"]
    assert authorization["EXISTING_ZONE_PLAN_REUSE"] == "YES"
    assert authorization["USER_CONFIRMED_ESTIMATION_REFERENCE"] == "YES"
    assert authorization["MINIMUM_ESTIMATE_SEMANTICS"] == "YES"
    for flag in (
        "RUNTIME_IMPLEMENTATION_AUTHORIZED",
        "DETAILED_THERMAL_LOAD_ALGORITHM_AUTHORIZED",
        "COOLING_LOAD_FORMULA_RECUT_AUTHORIZED",
        "EQUIPMENT_SELECTION_RECUT_AUTHORIZED",
        "INSTALLED_POWER_RECUT_AUTHORIZED",
        "INVESTMENT_RECUT_AUTHORIZED",
        "FRONTEND_IMPLEMENTATION_AUTHORIZED",
    ):
        assert authorization[flag] == "NO"

    pr_252 = data["pr_252"]
    assert pr_252["PR_252_FORMULA_AUDIT_DIRECTION"] == (
        "SUPERSEDED_BY_PER_ZONE_COOLING_ESTIMATION_BASIS"
    )
    assert pr_252["PR_252_MERGE_AUTHORIZED"] == "NO"
    assert pr_252["PR_252_CLOSE_AUTHORIZED"] == "NO"
    assert pr_252["PR_252_RUNTIME_IMPLEMENTATION_AUTHORIZED"] == "NO"
