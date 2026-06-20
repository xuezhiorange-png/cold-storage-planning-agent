"""Unit tests for core planning calculators (Task 4).

Tests cover:
  - Throughput calculator
  - Inventory calculator
  - Pallet calculator
  - Precooling calculator
  - Area calculator
  - CoreCalculationService orchestration
  - Error handling and validation

All calculators use Decimal arithmetic and must be deterministic.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cold_storage.modules.calculations.application.service import (
    CoreCalculationService,
)
from cold_storage.modules.calculations.domain.areas import (
    SUPPORTED_ZONE_CODES,
    ZoneAreaSpec,
    calculate_areas,
)
from cold_storage.modules.calculations.domain.errors import (
    InvalidCalculationInputError,
)
from cold_storage.modules.calculations.domain.inventory import (
    InventoryCalcInput,
    calculate_inventory,
)
from cold_storage.modules.calculations.domain.pallets import (
    PalletCalcInput,
    calculate_pallets,
)
from cold_storage.modules.calculations.domain.precooling import (
    PrecoolingCalcInput,
    calculate_precooling,
)

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from cold_storage.modules.calculations.domain.throughput import (
    ThroughputCalcInput,
    calculate_throughput,
)

# ============================================================================
# Throughput calculator tests
# ============================================================================


class TestThroughputCalculator:
    """Tests for the throughput calculator."""

    def test_basic_throughput(self) -> None:
        """Standard throughput calculation with typical values."""
        inp = ThroughputCalcInput(
            peak_output_kg_per_day=Decimal("25000"),
            processing_hours_per_day=Decimal("16"),
        )
        result = calculate_throughput(inp)

        assert result.success is True
        assert result.calculator_name == "throughput"
        assert result.result["required_hourly_throughput_kg_h"] == pytest.approx(1562.50)
        assert result.result["available_hourly_throughput_kg_h"] == pytest.approx(1838.24, abs=0.01)
        assert result.result["capacity_utilisation_ratio"] == pytest.approx(0.85)
        assert len(result.steps) > 0
        assert result.calculator_version == "1.0.0"

    def test_traceability_steps(self) -> None:
        """Each step carries a unique ID, formula, and output."""
        inp = ThroughputCalcInput(
            peak_output_kg_per_day=Decimal("10000"),
            processing_hours_per_day=Decimal("8"),
        )
        result = calculate_throughput(inp)

        step_ids = [s.step_id for s in result.steps]
        assert len(set(step_ids)) == len(step_ids)  # all unique
        for step in result.steps:
            assert step.formula != ""
            assert step.description != ""
            assert step.output_name != ""
            assert step.output_value != ""

    def test_worker_shortfall_warning(self) -> None:
        """When available_workers < required_workers, a CAPACITY_SHORTFALL warning."""
        inp = ThroughputCalcInput(
            peak_output_kg_per_day=Decimal("25000"),
            processing_hours_per_day=Decimal("16"),
            labour_efficiency_kg_per_person_hour=Decimal("150"),
            available_workers=10,  # less than needed
        )
        result = calculate_throughput(inp)

        assert result.result["required_worker_count"] > 10
        assert result.result["capacity_shortfall_workers"] > 0
        warning_codes = [w.code for w in result.warnings]
        assert "CAPACITY_SHORTFALL" in warning_codes

    def test_rejects_zero_peak_output(self) -> None:
        inp = ThroughputCalcInput(
            peak_output_kg_per_day=Decimal("0"),
            processing_hours_per_day=Decimal("16"),
        )
        with pytest.raises(InvalidCalculationInputError):
            calculate_throughput(inp)

    def test_rejects_negative_hours(self) -> None:
        inp = ThroughputCalcInput(
            peak_output_kg_per_day=Decimal("25000"),
            processing_hours_per_day=Decimal("-1"),
        )
        with pytest.raises(InvalidCalculationInputError):
            calculate_throughput(inp)

    def test_deterministic_results(self) -> None:
        """Same inputs must produce identical outputs (Decimal determinism)."""
        inp = ThroughputCalcInput(
            peak_output_kg_per_day=Decimal("25000"),
            processing_hours_per_day=Decimal("16"),
        )
        r1 = calculate_throughput(inp)
        r2 = calculate_throughput(inp)
        assert r1.result == r2.result

    def test_input_snapshot_uses_strings(self) -> None:
        """Decimal values in input_snapshot are serialised as strings."""
        inp = ThroughputCalcInput(
            peak_output_kg_per_day=Decimal("25000"),
            processing_hours_per_day=Decimal("16"),
        )
        result = calculate_throughput(inp)
        assert isinstance(result.input_snapshot["peak_output_kg_per_day"], str)


# ============================================================================
# Inventory calculator tests
# ============================================================================


class TestInventoryCalculator:
    """Tests for the inventory calculator."""

    def test_basic_inventory(self) -> None:
        """Standard inventory with turnover and safety stock."""
        inp = InventoryCalcInput(
            daily_inbound_quantity=Decimal("25000"),
            daily_outbound_quantity=Decimal("25000"),
            turnover_days=Decimal("7"),
            safety_stock_days=Decimal("2"),
        )
        result = calculate_inventory(inp)

        assert result.success is True
        assert result.calculator_name == "inventory"
        assert result.result["base_inventory"] == pytest.approx(175000.0)
        assert result.result["safety_inventory"] == pytest.approx(50000.0)
        assert result.result["peak_inventory"] == pytest.approx(225000.0)
        assert result.result["design_inventory"] == pytest.approx(225000.0)

    def test_with_peak_factor(self) -> None:
        inp = InventoryCalcInput(
            daily_inbound_quantity=Decimal("25000"),
            daily_outbound_quantity=Decimal("25000"),
            turnover_days=Decimal("7"),
            safety_stock_days=Decimal("2"),
            inventory_peak_factor=Decimal("1.2"),
        )
        result = calculate_inventory(inp)
        # peak_inventory = (175000 + 50000) * 1.2 = 270000
        assert result.result["peak_inventory"] == pytest.approx(270000.0)

    def test_with_storage_ratio(self) -> None:
        inp = InventoryCalcInput(
            daily_inbound_quantity=Decimal("25000"),
            daily_outbound_quantity=Decimal("25000"),
            turnover_days=Decimal("7"),
            safety_stock_days=Decimal("2"),
            storage_ratio=Decimal("1.1"),
        )
        result = calculate_inventory(inp)
        # design_inventory = 225000 * 1.1 = 247500
        assert result.result["design_inventory"] == pytest.approx(247500.0)

    def test_zero_safety_stock_warning(self) -> None:
        inp = InventoryCalcInput(
            daily_inbound_quantity=Decimal("25000"),
            daily_outbound_quantity=Decimal("25000"),
            turnover_days=Decimal("7"),
            safety_stock_days=Decimal("0"),
        )
        result = calculate_inventory(inp)
        warning_codes = [w.code for w in result.warnings]
        assert "NO_SAFETY_STOCK" in warning_codes

    def test_rejects_negative_turnover(self) -> None:
        inp = InventoryCalcInput(
            daily_inbound_quantity=Decimal("25000"),
            daily_outbound_quantity=Decimal("25000"),
            turnover_days=Decimal("-1"),
        )
        with pytest.raises(InvalidCalculationInputError):
            calculate_inventory(inp)

    def test_traceability_steps(self) -> None:
        inp = InventoryCalcInput(
            daily_inbound_quantity=Decimal("25000"),
            daily_outbound_quantity=Decimal("25000"),
            turnover_days=Decimal("7"),
        )
        result = calculate_inventory(inp)
        assert len(result.steps) == 4
        for step in result.steps:
            assert step.step_id.startswith("INV-")


# ============================================================================
# Pallet calculator tests
# ============================================================================


class TestPalletCalculator:
    """Tests for the pallet calculator."""

    def test_basic_pallets(self) -> None:
        """Standard pallet calculation."""
        inp = PalletCalcInput(
            design_inventory=Decimal("75000"),
            net_product_per_pallet=Decimal("400"),
        )
        result = calculate_pallets(inp)

        assert result.success is True
        assert result.calculator_name == "pallets"
        assert result.result["net_pallet_quantity"] == 188  # ceil(75000/400)
        assert result.result["reserve_pallet_quantity"] >= 0
        assert result.result["design_pallet_quantity"] > 0
        assert result.result["required_pallet_positions"] > 0

    def test_with_utilization_ratio(self) -> None:
        inp = PalletCalcInput(
            design_inventory=Decimal("75000"),
            net_product_per_pallet=Decimal("400"),
            pallet_utilization_ratio=Decimal("0.9"),
        )
        result = calculate_pallets(inp)
        # effective = 400 * 0.9 = 360, net = ceil(75000/360) = 209
        assert result.result["net_pallet_quantity"] == 209

    def test_with_stacking(self) -> None:
        inp = PalletCalcInput(
            design_inventory=Decimal("75000"),
            net_product_per_pallet=Decimal("400"),
            stacking_level=3,
        )
        result = calculate_pallets(inp)
        # Net = 188, reserve = ceil(188*0.10)=19, design = 207
        # positions = ceil(207/3) = 69
        assert result.result["net_pallet_quantity"] == 188
        assert result.result["required_pallet_positions"] == 69

    def test_high_stacking_warning(self) -> None:
        inp = PalletCalcInput(
            design_inventory=Decimal("75000"),
            net_product_per_pallet=Decimal("400"),
            stacking_level=5,
        )
        result = calculate_pallets(inp)
        warning_codes = [w.code for w in result.warnings]
        assert "HIGH_STACKING" in warning_codes

    def test_zero_reserve_warning(self) -> None:
        inp = PalletCalcInput(
            design_inventory=Decimal("75000"),
            net_product_per_pallet=Decimal("400"),
            reserve_ratio=Decimal("0"),
        )
        result = calculate_pallets(inp)
        warning_codes = [w.code for w in result.warnings]
        assert "NO_RESERVE" in warning_codes

    def test_rejects_zero_inventory(self) -> None:
        inp = PalletCalcInput(
            design_inventory=Decimal("0"),
            net_product_per_pallet=Decimal("400"),
        )
        with pytest.raises(InvalidCalculationInputError):
            calculate_pallets(inp)

    def test_rejects_zero_pallet_capacity(self) -> None:
        inp = PalletCalcInput(
            design_inventory=Decimal("75000"),
            net_product_per_pallet=Decimal("0"),
        )
        with pytest.raises(InvalidCalculationInputError):
            calculate_pallets(inp)


# ============================================================================
# Precooling calculator tests
# ============================================================================


class TestPrecoolingCalculator:
    """Tests for the precooling calculator."""

    def test_basic_precooling(self) -> None:
        """Standard precooling calculation."""
        inp = PrecoolingCalcInput(
            precooled_quantity_per_day=Decimal("25000"),
            precooled_ratio=Decimal("0.8"),
            batch_capacity=Decimal("500"),
            batch_duration=Decimal("4"),
            loading_unloading_duration=Decimal("1"),
            available_precooling_hours=Decimal("16"),
        )
        result = calculate_precooling(inp)

        assert result.success is True
        assert result.calculator_name == "precooling"
        assert result.result["required_precooling_quantity"] == pytest.approx(20000.0)
        assert result.result["effective_cycle_duration"] == pytest.approx(5.0)
        assert result.result["available_cycles_per_day"] == pytest.approx(3.2)

    def test_room_count(self) -> None:
        inp = PrecoolingCalcInput(
            precooled_quantity_per_day=Decimal("25000"),
            precooled_ratio=Decimal("0.8"),
            batch_capacity=Decimal("500"),
            batch_duration=Decimal("4"),
            loading_unloading_duration=Decimal("1"),
            available_precooling_hours=Decimal("16"),
            simultaneous_batch_count=4,
            reserve_capacity_ratio=Decimal("1.1"),
        )
        result = calculate_precooling(inp)
        assert result.result["required_precooling_rooms"] >= 1
        assert result.result["capacity_margin"] >= 0

    def test_no_margin_warning(self) -> None:
        """When capacity_margin <= 0, a NO_CAPACITY_MARGIN warning fires."""
        inp = PrecoolingCalcInput(
            precooled_quantity_per_day=Decimal("100000"),
            precooled_ratio=Decimal("1.0"),
            batch_capacity=Decimal("500"),
            batch_duration=Decimal("4"),
            loading_unloading_duration=Decimal("1"),
            available_precooling_hours=Decimal("8"),
            simultaneous_batch_count=1,
            reserve_capacity_ratio=Decimal("1.0"),
        )
        result = calculate_precooling(inp)
        # With low hours and no reserve, capacity may be tight
        # The warning should appear if margin is <= 0
        warning_codes = [w.code for w in result.warnings]
        assert "NO_CAPACITY_MARGIN" in warning_codes

    def test_traceability_steps(self) -> None:
        inp = PrecoolingCalcInput(
            precooled_quantity_per_day=Decimal("25000"),
            precooled_ratio=Decimal("0.8"),
            batch_capacity=Decimal("500"),
            batch_duration=Decimal("4"),
            loading_unloading_duration=Decimal("1"),
            available_precooling_hours=Decimal("16"),
        )
        result = calculate_precooling(inp)
        assert len(result.steps) == 8
        for step in result.steps:
            assert step.step_id.startswith("PC-")


# ============================================================================
# Area calculator tests
# ============================================================================


class TestAreaCalculator:
    """Tests for the area calculator."""

    def test_single_zone(self) -> None:
        """Area calculation for a single zone."""
        zones = [
            ZoneAreaSpec(
                zone_code="raw_material_staging",
                zone_name="原果暂存区",
                net_area=Decimal("100"),
            )
        ]
        result = calculate_areas(zones)

        assert result.success is True
        assert result.calculator_name == "areas"
        breakdown = result.result["zone_area_breakdown"]
        assert len(breakdown) == 1
        zone = breakdown[0]
        assert zone["zone_code"] == "raw_material_staging"
        assert zone["net_area"] == pytest.approx(100.0)
        assert zone["circulation_area"] == pytest.approx(15.0)  # 100 * 0.15
        assert zone["design_area"] == pytest.approx(115.0)  # 100 + 15 + 0

    def test_multiple_zones(self) -> None:
        zones = [
            ZoneAreaSpec(
                zone_code="raw_material_staging",
                zone_name="原果暂存区",
                net_area=Decimal("100"),
            ),
            ZoneAreaSpec(
                zone_code="precooling",
                zone_name="预冷区",
                net_area=Decimal("200"),
                circulation_allowance=Decimal("0.10"),
            ),
            ZoneAreaSpec(
                zone_code="sorting_and_packing",
                zone_name="分选包装区",
                net_area=Decimal("150"),
                auxiliary_allowance=Decimal("0.05"),
            ),
        ]
        result = calculate_areas(zones)

        assert result.success is True
        # 100 + 200 + 150 = 450
        assert result.result["total_net_area"] == "450"
        # circulation: 100*0.15 + 200*0.10 + 150*0.15 = 15+20+22.5 = 57.5
        assert result.result["total_circulation_area"] == "57.50"
        # auxiliary: 100*0 + 200*0 + 150*0.05 = 7.5
        assert result.result["total_auxiliary_area"] == "7.50"
        # total: 450 + 57.5 + 7.5 = 515.0
        assert result.result["total_design_area"] == "515.00"

    def test_override_circulation(self) -> None:
        zones = [
            ZoneAreaSpec(
                zone_code="raw_material_staging",
                zone_name="原果暂存区",
                net_area=Decimal("100"),
                circulation_allowance=Decimal("0.20"),
            )
        ]
        result = calculate_areas(zones, circulation_allowance_override=Decimal("0.30"))
        breakdown = result.result["zone_area_breakdown"]
        # 100 * 0.30 = 30
        assert breakdown[0]["circulation_area"] == pytest.approx(30.0)

    def test_invalid_zone_code(self) -> None:
        zones = [
            ZoneAreaSpec(
                zone_code="nonexistent_zone",
                zone_name="不存在的区域",
                net_area=Decimal("100"),
            )
        ]
        with pytest.raises(InvalidCalculationInputError):
            calculate_areas(zones)

    def test_negative_net_area(self) -> None:
        zones = [
            ZoneAreaSpec(
                zone_code="precooling",
                zone_name="预冷区",
                net_area=Decimal("-10"),
            )
        ]
        with pytest.raises(InvalidCalculationInputError):
            calculate_areas(zones)

    def test_all_supported_zones(self) -> None:
        """Every SUPPORTED_ZONE_CODE can be used."""
        zones = [
            ZoneAreaSpec(
                zone_code=code,
                zone_name=f"Zone {code}",
                net_area=Decimal("50"),
            )
            for code in SUPPORTED_ZONE_CODES
        ]
        result = calculate_areas(zones)
        assert result.success is True
        assert len(result.result["zone_area_breakdown"]) == len(SUPPORTED_ZONE_CODES)

    def test_steps_created_per_zone(self) -> None:
        zones = [
            ZoneAreaSpec(zone_code="precooling", zone_name="预冷区", net_area=Decimal("100")),
            ZoneAreaSpec(
                zone_code="shipping_staging",
                zone_name="发货暂存区",
                net_area=Decimal("50"),
            ),
        ]
        result = calculate_areas(zones)
        # 2 zone steps + 1 total step
        assert len(result.steps) == 3
        assert result.steps[-1].step_id == "AR-TOTAL"


# ============================================================================
# CoreCalculationService orchestration tests
# ============================================================================


class TestCoreCalculationService:
    """Tests for the orchestration service."""

    def test_orchestrate_with_explicit_inputs(self) -> None:
        """Run all calculators with explicit typed inputs."""
        svc = CoreCalculationService()
        result = svc.orchestrate_core_calculation(
            throughput_input=ThroughputCalcInput(
                peak_output_kg_per_day=Decimal("25000"),
                processing_hours_per_day=Decimal("16"),
            ),
            inventory_input=InventoryCalcInput(
                daily_inbound_quantity=Decimal("25000"),
                daily_outbound_quantity=Decimal("25000"),
                turnover_days=Decimal("7"),
            ),
        )

        assert result.success is True
        assert result.throughput is not None
        assert result.inventory is not None
        assert result.throughput.result["required_hourly_throughput_kg_h"] == pytest.approx(1562.50)

    def test_orchestrate_from_dict(self) -> None:
        """Build inputs from a flat dict (e.g. project version input_snapshot)."""
        svc = CoreCalculationService()
        inputs = {
            "daily_inbound_mass_kg": 25000,
            "working_time_h_per_day": 16,
            "utilization_factor": 0.85,
            "turnover_days": 7,
        }
        result = svc.orchestrate_from_dict(inputs)

        assert result.success is True
        assert result.throughput is not None
        assert result.inventory is not None

    def test_partial_calculation(self) -> None:
        """Only some calculators are run when inputs only cover those."""
        svc = CoreCalculationService()
        result = svc.orchestrate_core_calculation(
            throughput_input=ThroughputCalcInput(
                peak_output_kg_per_day=Decimal("10000"),
                processing_hours_per_day=Decimal("8"),
            ),
        )

        assert result.success is True
        assert result.throughput is not None
        assert result.inventory is None
        assert result.pallets is None

    def test_invalid_input_captured_as_error(self) -> None:
        """Invalid inputs are captured, not raised."""
        svc = CoreCalculationService()
        inputs = {
            "daily_inbound_mass_kg": -100,
            "working_time_h_per_day": 16,
        }
        result = svc.orchestrate_from_dict(inputs)

        # Should not raise — errors are collected
        # throughput will fail, inventory may also fail
        assert isinstance(result.errors, list)

    def test_to_dict_serialisation(self) -> None:
        """Orchestration result serialises to a clean dict."""
        svc = CoreCalculationService()
        result = svc.orchestrate_core_calculation(
            throughput_input=ThroughputCalcInput(
                peak_output_kg_per_day=Decimal("25000"),
                processing_hours_per_day=Decimal("16"),
            ),
        )
        d = result.to_dict()
        assert "throughput" in d
        assert d["orchestration_version"] == "1.0.0"
        assert "success" in d
        assert "calculated_at" in d


# ============================================================================
# Units tests
# ============================================================================


class TestUnits:
    """Tests for unit management."""

    def test_unit_enum_values(self) -> None:
        from cold_storage.modules.calculations.domain.units import Unit

        assert Unit.KG.value == "kg"
        assert Unit.TONNE.value == "t"
        assert Unit.HOUR.value == "h"
        assert Unit.DAY.value == "day"
        assert Unit.M2.value == "m2"

    def test_conversions(self) -> None:
        from cold_storage.modules.calculations.domain.units import (
            days_to_hours,
            hours_to_days,
            kg_to_tonnes,
            tonnes_to_kg,
        )

        assert tonnes_to_kg(1) == 1000.0
        assert kg_to_tonnes(1000) == 1.0
        assert hours_to_days(24) == 1.0
        assert days_to_hours(1) == 24.0
