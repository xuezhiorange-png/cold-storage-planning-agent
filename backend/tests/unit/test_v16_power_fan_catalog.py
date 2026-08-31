"""V1.6 assembler and Aily fan catalog alignment tests."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from cold_storage.modules.aily.application.concept_preview import preview_concept
from cold_storage.modules.aily.application.preview_bundle import (
    assemble_preview_context,
    prepare_power_fan_catalog_inputs,
)
from cold_storage.modules.aily.application.stage_preview import preview_installed_power
from cold_storage.modules.projects.application.demo_power_fan_catalog import (
    DEMO_POWER_FAN_SOURCE,
    POWER_FAN_DEMO_CATALOG_DISCLAIMER_ZH,
)
from cold_storage.modules.projects.application.engineering_input_bundle import (
    LINEAGE_PENDING_STATE,
    project_execution_snapshot_from_bundle,
)
from cold_storage.modules.projects.application.operator_process_input import (
    assemble_engineering_input_bundle,
)
from cold_storage.modules.projects.domain.models import ProjectVersion

AILY_DIR = Path(__file__).resolve().parents[2] / "src" / "cold_storage" / "modules" / "aily"


def _five_keys(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "daily_inbound_mass_kg": 20000,
        "finished_storage_days": 7,
        "frozen_storage_days": 10,
        "main_packaging_storage_days": 4,
        "auxiliary_packaging_storage_days": 12,
    }
    payload.update(overrides)
    return payload


def _v09_operator_payload() -> dict[str, object]:
    return {
        "schema_id": "OperatorProcessInputV1",
        "schema_version": "1.1.0",
        "zone_planning_inputs": {
            "daily_inbound_mass_kg": {"value": "20000", "unit": "kg/day", "state": "provided"},
            "finished_storage_days": {"value": "7", "unit": "day", "state": "provided"},
            "frozen_storage_days": {"value": "10", "unit": "day", "state": "provided"},
            "main_packaging_storage_days": {"value": "4", "unit": "day", "state": "provided"},
            "auxiliary_packaging_storage_days": {
                "value": "12",
                "unit": "day",
                "state": "provided",
            },
        },
    }


def _assemble() -> dict[str, object]:
    return assemble_engineering_input_bundle(
        operator_input=_v09_operator_payload(),
        project_id="p-v16",
        version=ProjectVersion(
            project_id="p-v16",
            version_number=1,
            change_summary="v16-fan-catalog",
            id="pv-v16",
        ),
        actor="test-actor",
    )


def test_v16_assembler_fan_leaves_from_v05_demo_catalog() -> None:
    bundle = _assemble()
    fans = bundle["installed_power_inputs"]
    evaporator = fans["evaporator_fan_power_kw_e"]
    condenser = fans["condenser_fan_power_kw_e"]
    assert Decimal(str(evaporator["value"])) == Decimal("10")
    assert Decimal(str(condenser["value"])) == Decimal("8")
    assert evaporator["source_type"] == "demo"
    assert condenser["source_type"] == "demo"
    assert evaporator["validity_status"] == "unverified"
    assert evaporator["requires_review"] is True
    assert evaporator["source_path"] == DEMO_POWER_FAN_SOURCE
    assert condenser["source_path"] == DEMO_POWER_FAN_SOURCE
    assert fans["compressor_input_power_kw_e"]["state"] == LINEAGE_PENDING_STATE


def test_v16_snapshot_and_aily_prepare_same_fan_leaves() -> None:
    bundle = _assemble()
    snapshot = project_execution_snapshot_from_bundle(bundle)
    power_inputs = dict(snapshot["power"])
    prepared, used_catalog = prepare_power_fan_catalog_inputs(power_inputs)
    assert used_catalog is True
    assert Decimal(str(power_inputs["evaporator_fan_power_kw_e"])) == Decimal("10")
    assert Decimal(str(power_inputs["condenser_fan_power_kw_e"])) == Decimal("8")
    assert Decimal(str(prepared["evaporator_fan_power_kw_e"])) == Decimal("10")
    assert Decimal(str(prepared["condenser_fan_power_kw_e"])) == Decimal("8")
    context = assemble_preview_context(_five_keys())
    preview_power = dict(context.snapshot["power"])
    assert Decimal(str(preview_power["evaporator_fan_power_kw_e"])) == Decimal("10")
    assert Decimal(str(preview_power["condenser_fan_power_kw_e"])) == Decimal("8")


def test_v16_power_preview_disclaimer_and_not_compressor_120() -> None:
    power = preview_installed_power(_five_keys())
    assert power["persisted"] is False
    assert power["power_from_demo_catalog"] is False
    assert float(power["summary"]["total_installed_power_kw_e"]) != 120.0
    assert float(power["summary"]["total_installed_power_kw_e"]) > 18.0
    assert POWER_FAN_DEMO_CATALOG_DISCLAIMER_ZH in power["table"]["caption"]
    assert POWER_FAN_DEMO_CATALOG_DISCLAIMER_ZH in power["markdown_table"]
    assert "v05" in power["table"]["caption"]
    assert "10" in power["table"]["caption"]
    assert "8" in power["table"]["caption"]


def test_v16_concept_preview_power_caption_mentions_v05_fans() -> None:
    result = preview_concept(_five_keys())
    assert result["persisted"] is False
    power = result["stages"]["power"]
    assert power["power_from_demo_catalog"] is False
    assert POWER_FAN_DEMO_CATALOG_DISCLAIMER_ZH in power["markdown_table"]


def test_v16_prepare_fills_pending_zero_from_loader() -> None:
    prepared, used_catalog = prepare_power_fan_catalog_inputs(
        {
            "compressor_input_power_kw_e": "50",
            "evaporator_fan_power_kw_e": "0",
            "condenser_fan_power_kw_e": "",
        }
    )
    assert used_catalog is True
    assert Decimal(str(prepared["evaporator_fan_power_kw_e"])) == Decimal("10")
    assert Decimal(str(prepared["condenser_fan_power_kw_e"])) == Decimal("8")
    assert prepared["demo_catalog_source"] == DEMO_POWER_FAN_SOURCE
    assert Decimal(str(prepared["compressor_input_power_kw_e"])) == Decimal("50")


def test_v16_aily_does_not_import_calculations_or_hardcode_fans() -> None:
    for path in AILY_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "cold_storage.modules.calculations" not in text, path.name
        assert "_PREVIEW_POWER_FAN_DEMO" not in text, path.name
        assert '"evaporator_fan_power_kw_e": "10.0"' not in text, path.name
        assert '"condenser_fan_power_kw_e": "8.0"' not in text, path.name
