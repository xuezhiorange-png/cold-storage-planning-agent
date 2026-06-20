import pytest

from cold_storage.modules.calculations.domain.coefficients import CalculationCoefficient
from cold_storage.modules.calculations.domain.inputs import (
    InventoryInput,
    PrecoolingInput,
    StorageCapacityInput,
    ThroughputInput,
)
from cold_storage.modules.calculations.domain.service import CalculationService


def demo_coefficient(code: str, value: float, unit: str) -> CalculationCoefficient:
    return CalculationCoefficient(
        code=code,
        name=code.replace("_", " "),
        value=value,
        unit=unit,
        category="demo",
        source_type="demo",
        source_reference="示例演示系数，未作为正式标准",
        version="demo-1",
        validity_status="unverified",
        approval_status="unverified",
        requires_review=True,
    )


def test_throughput_calculator_returns_traceable_result() -> None:
    service = CalculationService()

    result = service.run_throughput(
        ThroughputInput(
            daily_inbound_mass_kg=25_000,
            working_time_h_per_day=16,
            utilization_factor=0.85,
        )
    )

    assert result.success is True
    assert result.calculator_name == "throughput"
    assert result.result["average_hourly_throughput_kg_h"] == 1562.5
    assert result.result["design_hourly_throughput_kg_h"] == pytest.approx(1838.235294117647)
    assert result.formula_references[0].formula_id == "TH-001"
    assert result.requires_review is False


def test_storage_capacity_marks_unapproved_coefficients_for_review() -> None:
    service = CalculationService()

    result = service.run_storage_capacity(
        StorageCapacityInput(
            maximum_design_inventory_kg=75_000,
            effective_volume_loading_kg_m3=demo_coefficient(
                "blueberry_effective_volume_loading_kg_m3", 280, "kg/m3"
            ),
            volume_utilization_factor=demo_coefficient("volume_utilization_factor", 0.72, "ratio"),
            clear_height_m=4.5,
        )
    )

    assert result.success is True
    assert result.requires_review is True
    assert result.result["effective_storage_volume_m3"] == 267.85714285714283
    assert result.result["nominal_storage_volume_m3"] == pytest.approx(372.02380952380946)
    assert len(result.warnings) == 2


def test_inventory_and_precooling_do_not_silently_accept_missing_values() -> None:
    service = CalculationService()

    inventory = service.run_inventory(
        InventoryInput(
            daily_inbound_mass_kg=25_000,
            storage_days=0,
            reserve_factor=1.05,
        )
    )
    precooling = service.run_precooling(
        PrecoolingInput(
            daily_inbound_mass_kg=25_000,
            precooling_required_ratio=0.8,
            batch_product_mass_kg=0,
            cooling_duration_h=3,
            loading_duration_h=0.5,
            unloading_duration_h=0.5,
            working_time_h_per_day=16,
            positions_per_room=8,
            product_mass_per_position_kg=500,
            equipment_utilization_factor=0.85,
            precooling_reserve_factor=1.1,
        )
    )

    assert inventory.success is False
    assert inventory.errors[0].code == "INVALID_ENGINEERING_INPUT"
    assert precooling.success is False
    assert precooling.errors[0].details["field"] == "batch_product_mass_kg"
