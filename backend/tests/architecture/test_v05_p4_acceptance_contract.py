"""Architecture tests for V0.5 P4 five-stage acceptance contract."""

from __future__ import annotations

import json
from pathlib import Path

from cold_storage.bootstrap.v05_local_sample import (
    EXPECTED_CANONICAL_CALCULATORS,
    load_manifest,
)
from cold_storage.modules.orchestration.domain.consumer_bindings import CANONICAL_CALCULATOR_NAMES
from cold_storage.modules.orchestration.domain.dag import CALCULATOR_BINDINGS

REPO_ROOT = Path(__file__).resolve().parents[3]
V05_SAMPLE_LOADER = (
    REPO_ROOT / "backend" / "src" / "cold_storage" / "bootstrap" / "v05_local_sample.py"
)
V05_MANIFEST = REPO_ROOT / "samples" / "v05-local-workbench" / "manifest.json"
V05_RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "v05-local-run.md"

KEY_LEAF_PATHS: tuple[str, ...] = (
    "zone_planning_inputs.daily_inbound_mass_kg",
    "zone_planning_inputs.working_time_h_per_day",
    "zone_planning_inputs.finished_storage_days",
    "zone_planning_inputs.packaging_storage_days",
    "zone_planning_inputs.precooling_required_ratio",
    "cooling_load_inputs.zones",
    "cooling_load_inputs.coefficients",
    "cooling_load_inputs.zones[0].zone_code",
    "cooling_load_inputs.zones[0].zone_area",
    "cooling_load_inputs.zones[0].room_height",
    "cooling_load_inputs.zones[0].wall_area",
    "cooling_load_inputs.zones[0].roof_area",
    "cooling_load_inputs.zones[0].floor_area",
    "cooling_load_inputs.zones[0].outdoor_design_temperature",
    "cooling_load_inputs.zones[0].room_design_temperature",
    "cooling_load_inputs.zones[0].product_mass_per_day",
    "cooling_load_inputs.zones[0].product_entry_temperature",
    "cooling_load_inputs.zones[0].product_target_temperature",
    "cooling_load_inputs.zones[0].cooling_duration",
    "equipment_inputs.condensing_temperature_c",
    "equipment_inputs.systems",
    "equipment_inputs.coefficients",
    "equipment_inputs.systems[0].zones[0].evaporator_count",
    "installed_power_inputs.compressor_input_power_kw_e",
    "installed_power_inputs.evaporator_fan_power_kw_e",
    "installed_power_inputs.condenser_fan_power_kw_e",
    "investment_inputs.total_area_m2",
    "investment_inputs.refrigerated_area_m2",
    "investment_inputs.frozen_area_m2",
    "investment_inputs.position_count",
    "investment_inputs.total_power_kw",
)


def _resolve_path(bundle: dict, dotted_path: str):
    cursor = bundle
    for part in dotted_path.split("."):
        if "[" in part:
            name, index_text = part[:-1].split("[")
            cursor = cursor[name][int(index_text)]
        else:
            cursor = cursor[part]
    return cursor


def test_p4_sample_loader_does_not_call_planning_run() -> None:
    loader_source = V05_SAMPLE_LOADER.read_text(encoding="utf-8")
    assert "/planning-run" not in loader_source
    assert "planning_run" not in loader_source
    assert "five-stage-execution" in loader_source


def test_p4_canonical_calculator_names_frozen() -> None:
    assert tuple(EXPECTED_CANONICAL_CALCULATORS) == (
        "cold_room_zone_plan",
        "cooling_load",
        "equipment",
        "installed_power",
        "investment_estimate",
    )
    assert frozenset(EXPECTED_CANONICAL_CALCULATORS) == CANONICAL_CALCULATOR_NAMES
    assert CALCULATOR_BINDINGS["power"] == "installed_power"
    assert "power_configuration" not in CALCULATOR_BINDINGS.values()


def test_p4_manifest_contains_explicit_key_leaves_with_provided_state() -> None:
    manifest = load_manifest()
    bundle = manifest["engineering_input_bundle"]
    assert bundle["schema_id"] == "EngineeringInputBundleV1"
    for path in KEY_LEAF_PATHS:
        leaf = _resolve_path(bundle, path)
        if path in {"cooling_load_inputs.zones", "equipment_inputs.systems"}:
            assert isinstance(leaf, list) and leaf
            continue
        if path == "cooling_load_inputs.coefficients":
            assert leaf["state"] == "provided"
            continue
        assert leaf["state"] == "provided", f"{path} must be explicit provided state"


def test_p4_manifest_demo_coefficients_remain_unverified_and_review_required() -> None:
    manifest = load_manifest()
    bundle = manifest["engineering_input_bundle"]
    demo_leaves = bundle["coefficient_context"].get("demo_coefficient_leaves") or []
    assert demo_leaves
    for leaf in demo_leaves:
        assert leaf["source_type"] == "demo"
        assert leaf["validity_status"] in {"unverified", "conflict"}
        assert leaf["requires_review"] is True

    for optional_demo_path in (
        "zone_planning_inputs.raw_holding_hours",
        "zone_planning_inputs.storage_position_capacity_kg",
    ):
        leaf = _resolve_path(bundle, optional_demo_path)
        assert leaf["source_type"] == "demo"
        assert leaf["validity_status"] in {"unverified", "conflict"}
        assert leaf["requires_review"] is True


def test_p4_runbook_and_manifest_exist() -> None:
    assert V05_MANIFEST.is_file()
    assert V05_RUNBOOK.is_file()
    manifest = json.loads(V05_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["sample_id"] == "v05-local-workbench"
    runbook = V05_RUNBOOK.read_text(encoding="utf-8")
    assert "make seed-v05-sample" in runbook
    assert "make smoke-v05-local" in runbook
    assert "five-stage-execution" in runbook
    assert "POST /api/v1/projects/{id}/versions/{version}/planning-run" not in runbook
