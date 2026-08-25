"""Architecture tests for V0.5 P0 five-stage workbench contract.

Enforces the frozen contract in
``docs/tasks/V0_5-P0-five-stage-workbench-contract.md`` without introducing
engineering formula values or changing application behavior.

Contract authority SHA: ``eec12b9d1ee956ce9f02e8c92bec32dfcf31308f``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from cold_storage.modules.orchestration.domain.dag import (
    CALCULATOR_BINDINGS,
    ORCHESTRATION_STAGE_ORDER,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V0_5-P0-five-stage-workbench-contract.md"

FROZEN_STAGE_ORDER: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)

FROZEN_CALCULATOR_IDENTITIES: dict[str, str] = {
    "zone": "cold_room_zone_plan",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "power": "installed_power",
    "investment": "investment_estimate",
}

KEY_FIELD_PATHS: tuple[str, ...] = (
    "zone_planning_inputs.daily_inbound_mass_kg",
    "zone_planning_inputs.working_time_h_per_day",
    "zone_planning_inputs.finished_storage_days",
    "zone_planning_inputs.packaging_storage_days",
    "zone_planning_inputs.precooling_required_ratio",
    "cooling_load_inputs.zones",
    "cooling_load_inputs.coefficients",
    "cooling_load_inputs.zones[].zone_code",
    "cooling_load_inputs.zones[].zone_name",
    "cooling_load_inputs.zones[].temperature_level",
    "cooling_load_inputs.zones[].zone_area",
    "cooling_load_inputs.zones[].room_height",
    "cooling_load_inputs.zones[].wall_area",
    "cooling_load_inputs.zones[].roof_area",
    "cooling_load_inputs.zones[].floor_area",
    "cooling_load_inputs.zones[].outdoor_design_temperature",
    "cooling_load_inputs.zones[].room_design_temperature",
    "cooling_load_inputs.zones[].operating_hours_per_day",
    "cooling_load_inputs.zones[].product_mass_per_day",
    "cooling_load_inputs.zones[].product_entry_temperature",
    "cooling_load_inputs.zones[].product_target_temperature",
    "cooling_load_inputs.zones[].cooling_duration",
    "equipment_inputs.systems",
    "equipment_inputs.coefficients",
    "equipment_inputs.systems[].system_code",
    "equipment_inputs.systems[].system_name",
    "equipment_inputs.systems[].design_evaporating_temperature",
    "equipment_inputs.systems[].zones[].zone_code",
    "equipment_inputs.systems[].zones[].zone_name",
    "equipment_inputs.systems[].zones[].evaporator_count",
    "equipment_inputs.systems[].zones[].defrost_method",
    "equipment_inputs.systems[].zones[].design_cooling_load_kw_r",
    "installed_power_inputs.compressor_input_power_kw_e",
    "installed_power_inputs.evaporator_fan_power_kw_e",
    "installed_power_inputs.condenser_fan_power_kw_e",
    "investment_inputs.total_area_m2",
    "investment_inputs.refrigerated_area_m2",
    "investment_inputs.frozen_area_m2",
    "investment_inputs.position_count",
    "investment_inputs.total_power_kw",
    "project_version_identity.project_id",
    "coefficient_context.coefficient_context_id",
    "units_metadata.leaf_unit_by_path",
    "source_metadata.input_group_provenance",
    "review_metadata.overall_requires_review",
)

NEGATIVE_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("zone_planning_inputs.daily_inbound_mass_kg", "MISSING_ENGINEERING_PARAMETER"),
    ("cooling_load_inputs.zones[0].zone_area", "MISSING_ENGINEERING_PARAMETER"),
    ("cooling_load_inputs.zones[0].outdoor_design_temperature", "MISSING_ENGINEERING_PARAMETER"),
    ("cooling_load_inputs.zones[0].product_entry_temperature", "MISSING_ENGINEERING_PARAMETER"),
    ("equipment_inputs.systems[0].zones[0].evaporator_count", "MISSING_ENGINEERING_PARAMETER"),
    ("installed_power_inputs.compressor_input_power_kw_e", "MISSING_ENGINEERING_PARAMETER"),
    ("investment_inputs.total_area_m2", "MISSING_ENGINEERING_PARAMETER"),
    ("cooling_load_inputs.zones[0].zone_area.unit", "MISSING_ENGINEERING_PARAMETER"),
    ("schema_version", "MISSING_ENGINEERING_PARAMETER"),
)

FORBIDDEN_POSITIVE_EXAMPLE_FRAGMENTS: tuple[str, ...] = (
    "utilization_factor",
    "reserve_factor",
)

# Patterns that would indicate engineering formula values leaked into tests.
_ENGINEERING_VALUE_PATTERNS = (
    re.compile(r"\b\d+\.?\d*\s*kW\b", re.IGNORECASE),
    re.compile(r"\butilization_factor\s*=\s*0\.\d+"),
    re.compile(r"\breserve_factor\s*=\s*0\.\d+"),
    re.compile(r"\b\d{2,}_\d{3}\b"),  # grouped numeric literals
)


def _read_contract() -> str:
    assert CONTRACT_PATH.is_file(), f"P0 contract missing: {CONTRACT_PATH}"
    return CONTRACT_PATH.read_text(encoding="utf-8")


def _extract_fenced_block(contract: str, marker: str) -> str:
    start = contract.index(marker)
    fence_start = contract.index("```", start)
    fence_end = contract.index("```", fence_start + 3)
    content = contract[fence_start + 3 : fence_end].strip()
    if content.startswith(("json", "yaml")):
        content = content.split("\n", 1)[1].strip()
    return content


def test_orchestration_stage_order_is_exactly_five_frozen_stages() -> None:
    """ORCHESTRATION_STAGE_ORDER must match the frozen five-stage chain."""
    assert len(ORCHESTRATION_STAGE_ORDER) == 5
    assert ORCHESTRATION_STAGE_ORDER == FROZEN_STAGE_ORDER


def test_calculator_bindings_contain_five_canonical_identities() -> None:
    """CALCULATOR_BINDINGS must map each stage to its canonical calculator."""
    assert set(CALCULATOR_BINDINGS.keys()) == set(FROZEN_STAGE_ORDER)
    for stage, calculator_name in FROZEN_CALCULATOR_IDENTITIES.items():
        assert CALCULATOR_BINDINGS[stage] == calculator_name


def test_power_configuration_is_not_canonical_power_binding() -> None:
    """power_configuration must never satisfy the canonical power stage slot."""
    assert CALCULATOR_BINDINGS["power"] == "installed_power"
    assert CALCULATOR_BINDINGS["power"] != "power_configuration"
    for stage_name, calculator_name in CALCULATOR_BINDINGS.items():
        if stage_name != "power":
            assert calculator_name != "power_configuration", (
                f"power_configuration must not appear on stage {stage_name!r}"
            )


def test_p0_contract_documents_fail_closed_and_no_auto_feed() -> None:
    """Contract must freeze fail-closed, no-auto-feed, and auth boundaries."""
    contract = _read_contract()
    required_fragments = (
        "MISSING_ENGINEERING_PARAMETER",
        "ZONE_AREA_TO_COOLING_LOAD_AUTO_FEED=NO",
        "ZONE_AREA_TO_COOLING_LOAD_GEOMETRY_AUTO_FEED=NO",
        "POWER_CONFIGURATION_TO_INSTALLED_POWER_AUTO_FEED=NO",
        "PERSISTED_UPSTREAM_RESULT_TO_DOWNSTREAM_TYPED_INPUT=YES",
        "V05_P1_IMPLEMENTATION_AUTHORIZED=NO",
        "MERGE_AUTHORIZED=NO",
        "TAG_PUBLICATION_AUTHORIZED=NO",
        "RELEASE_PUBLICATION_AUTHORIZED=NO",
        "power_configuration",
        "installed_power",
        "Reports MUST read persisted calculation results",
    )
    for fragment in required_fragments:
        assert fragment in contract, f"P0 contract missing required fragment: {fragment!r}"


def test_p0_contract_documents_atomicity_idempotency_and_lineage() -> None:
    """Contract must document atomic commit, idempotency, and stale lineage."""
    contract = _read_contract()
    required_fragments = (
        "No partial five-stage chain is committed",
        "idempotency_key",
        "result_hash",
        "upstream_calculation_ids",
        "PROJECT_VERSION_LOCKED",
        "SQLite",
        "PostgreSQL",
        "EngineeringInputBundleV1",
    )
    for fragment in required_fragments:
        assert fragment in contract, f"P0 contract missing required fragment: {fragment!r}"


def test_p0_contract_field_inventory_exists_and_lists_key_paths() -> None:
    """EngineeringInputBundleV1FieldInventory must list every KEY field path."""
    contract = _read_contract()
    assert "EngineeringInputBundleV1FieldInventory" in contract
    inventory = _extract_fenced_block(contract, "EngineeringInputBundleV1FieldInventory")
    for path in KEY_FIELD_PATHS:
        assert f"path: {path}" in inventory, f"Field inventory missing KEY path: {path!r}"


def test_p0_contract_positive_example_uses_placeholders_only() -> None:
    """Positive example must exist and avoid engineering formula literals."""
    contract = _read_contract()
    assert "EngineeringInputBundleV1PositiveExample" in contract
    example = _extract_fenced_block(contract, "EngineeringInputBundleV1PositiveExample")
    assert "<PROVIDED>" in example
    parsed = json.loads(example)
    assert parsed["schema_id"] == "EngineeringInputBundleV1"
    for fragment in FORBIDDEN_POSITIVE_EXAMPLE_FRAGMENTS:
        assert fragment not in example, (
            f"Positive example contains forbidden fragment: {fragment!r}"
        )
    for pattern in _ENGINEERING_VALUE_PATTERNS:
        match = pattern.search(example)
        assert match is None, (
            f"Positive example contains engineering literal pattern {pattern.pattern!r}: "
            f"{match.group()!r}"
        )


def test_p0_contract_negative_examples_document_fail_closed_paths() -> None:
    """Negative examples must document MISSING_ENGINEERING_PARAMETER field paths."""
    contract = _read_contract()
    assert "EngineeringInputBundleV1NegativeExamples" in contract
    examples = _extract_fenced_block(contract, "EngineeringInputBundleV1NegativeExamples")
    parsed = json.loads(examples)
    assert isinstance(parsed, list)
    for field_path, error_code in NEGATIVE_EXAMPLES:
        assert field_path in examples, f"Negative examples missing field_path: {field_path!r}"
        assert error_code in examples, f"Negative examples missing error_code: {error_code!r}"
    assert "INVALID_CANONICAL_POWER_SLOT" in examples
    assert "power_configuration offered as canonical power slot" in examples


def test_p0_contract_consumer_alias_table_documents_drift() -> None:
    """Consumer alias table must freeze current drift and canonical targets."""
    contract = _read_contract()
    required_fragments = (
        "REQUIRED_SCHEME_CALCULATOR_NAMES",
        "_REQUIRED_CALC_TYPES",
        "cold_room_zone_plan",
        "installed_power",
        "investment_estimate",
        "power_configuration",
        "SILENT_UI_ALIASING=NO",
    )
    for fragment in required_fragments:
        assert fragment in contract, f"Consumer alias table missing fragment: {fragment!r}"


def test_p0_contract_and_tests_contain_no_engineering_formula_values() -> None:
    """Neither the contract file nor this test module may embed formula numbers."""
    this_file = Path(__file__).read_text(encoding="utf-8")
    contract = _read_contract()

    for label, content in (("contract", contract), ("test module", this_file)):
        for pattern in _ENGINEERING_VALUE_PATTERNS:
            match = pattern.search(content)
            assert match is None, (
                f"Engineering formula value pattern {pattern.pattern!r} "
                f"found in {label}: {match.group()!r}"
            )
