"""Unit tests for cooling load, equipment capability, and installed power calculators.

Tests cover:
  - Cooling load: envelope, product, packaging, infiltration, internal, defrost,
    multi-zone grouping, diversity, margin, errors, warnings, determinism,
    traceability.
  - Equipment: single/multi-zone systems, redundancy, condenser, COP, errors,
    traceability.
  - Power: refrigeration components, processing, total, peak demand, kW(e) units,
    equipment item breakdown.

All calculators use Decimal arithmetic and must be deterministic.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cold_storage.modules.calculations.domain.cooling_load import (
    CoefficientSet,
    CoolingLoadCalcInput,
    TemperatureLevel,
    ZoneCoolingLoadInput,
    calculate_cooling_load,
)
from cold_storage.modules.calculations.domain.equipment import (
    EquipmentCapabilityCalcInput,
    EquipmentCoefficientSet,
    TemperatureSystemInput,
    ZoneEquipmentInput,
    calculate_equipment_capability,
)
from cold_storage.modules.calculations.domain.errors import (
    CoefficientMissingError,
    MissingCalculationInputError,
)
from cold_storage.modules.calculations.domain.power import (
    InstalledPowerCalcInput,
    PowerEquipmentItem,
    calculate_installed_power,
)

_D = Decimal


# ============================================================================
# Shared fixtures
# ============================================================================


def _make_zone(**overrides):
    """Create a ZoneCoolingLoadInput with sensible defaults.

    The zone carries U-values, worker_heat_gain, motor_efficiency, and
    product_specific_heat directly — the calculator reads them from the zone
    (not from the CoefficientSet) via ``_require_coefficient``.
    """
    defaults = {
        "zone_code": "test_room",
        "zone_name": "Test Room",
        "temperature_level": TemperatureLevel.MEDIUM_TEMPERATURE,
        "zone_area": _D("100"),
        "room_height": _D("4"),
        "wall_area": _D("200"),
        "roof_area": _D("100"),
        "floor_area": _D("100"),
        "room_design_temperature": _D("0"),
        "outdoor_design_temperature": _D("35"),
        "operating_hours_per_day": _D("24"),
        "product_entry_temperature": _D("25"),
        "product_target_temperature": _D("0"),
        "cooling_duration": _D("4"),
        # Coefficients that the calculator reads from the zone object
        "u_value_wall": _D("0.5"),
        "u_value_roof": _D("0.4"),
        "u_value_floor": _D("0.3"),
        "product_specific_heat": _D("3.85"),
        "worker_heat_gain": _D("270"),
        "motor_efficiency": _D("0.90"),
    }
    defaults.update(overrides)
    return ZoneCoolingLoadInput(**defaults)


COEFFICIENTS = CoefficientSet(
    # U-values live on the zone, but the CoefficientSet can carry them too
    wall_u_value=_D("0.5"),
    roof_u_value=_D("0.4"),
    floor_u_value=_D("0.3"),
    product_specific_heat=_D("3.85"),
    # These are read from the CoefficientSet directly
    air_change_rate=_D("1.5"),
    worker_heat_gain=_D("270"),
    motor_efficiency=_D("0.90"),
    design_margin_ratio=_D("1.10"),
    diversity_factor=_D("1.0"),
)


def _make_zone_equipment(
    zone_code="Z1",
    zone_name="Zone 1",
    design_load=Decimal("10"),
    evaporator_count=1,
    defrost_method="electric",
    evap_temp=Decimal("-10"),
):
    """Create a ZoneEquipmentInput."""
    return ZoneEquipmentInput(
        zone_code=zone_code,
        zone_name=zone_name,
        design_cooling_load_kw_r=design_load,
        evaporator_count=evaporator_count,
        evaporation_temperature_c=evap_temp,
        defrost_method=defrost_method,
    )


EQUIPMENT_COEFFICIENTS = EquipmentCoefficientSet(
    redundancy_ratio=_D("1.10"),
    evaporator_capacity_margin=_D("1.10"),
    condenser_capacity_margin=_D("1.15"),
    compressor_cop=_D("3.0"),
)


# ============================================================================
# Cooling load calculator tests
# ============================================================================


class TestCoolingLoadEnvelope:
    """Envelope (transmission) load tests."""

    def test_single_zone_envelope_load(self) -> None:
        """Wall + roof + floor transmission load with known U-values."""
        zone = _make_zone()
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        assert result.success is True
        assert result.calculator_name == "cooling_load"

        zone_data = result.result["zones"][0]
        # wall: 0.5 × 200 × 35 = 3500 W = 3.500 kW
        assert zone_data["wall_transmission_load_kw_r"] == pytest.approx(3.500)
        # roof: 0.4 × 100 × 35 = 1400 W = 1.400 kW
        assert zone_data["roof_transmission_load_kw_r"] == pytest.approx(1.400)
        # floor: 0.3 × 100 × 35 = 1050 W = 1.050 kW
        assert zone_data["floor_transmission_load_kw_r"] == pytest.approx(1.050)
        # total: 3.500 + 1.400 + 1.050 = 5.950 kW
        assert zone_data["transmission_load_kw_r"] == pytest.approx(5.950)

    def test_zero_temperature_difference(self) -> None:
        """When outdoor == room temperature, all loads are zero."""
        zone = _make_zone(
            outdoor_design_temperature=_D("0"),
            room_design_temperature=_D("0"),
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        zone_data = result.result["zones"][0]
        assert zone_data["transmission_load_kw_r"] == pytest.approx(0.0)
        assert zone_data["infiltration_load_kw_r"] == pytest.approx(0.0)
        assert zone_data["subtotal_load_kw_r"] == pytest.approx(0.0)

    def test_adjacent_temperature_for_floor(self) -> None:
        """When adjacent_temperature is set, floor uses it instead of outdoor."""
        zone = _make_zone(
            adjacent_temperature=_D("20"),
            room_design_temperature=_D("0"),
            outdoor_design_temperature=_D("35"),
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        zone_data = result.result["zones"][0]
        # floor delta_t = 20 - 0 = 20 (adjacent, not outdoor)
        # floor: 0.3 × 100 × 20 = 600 W = 0.600 kW
        assert zone_data["floor_transmission_load_kw_r"] == pytest.approx(0.600)

    def test_negative_adjacent_temperature_clamps_to_zero(self) -> None:
        """When adjacent is colder than room, floor load is clamped to zero."""
        zone = _make_zone(
            adjacent_temperature=_D("-10"),
            room_design_temperature=_D("0"),
            outdoor_design_temperature=_D("35"),
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        zone_data = result.result["zones"][0]
        # floor delta_t clamped to 0
        assert zone_data["floor_transmission_load_kw_r"] == pytest.approx(0.0)


class TestCoolingLoadProduct:
    """Product load tests (sensible heat + packaging)."""

    def test_product_sensible_heat(self) -> None:
        """Product sensible heat: Q = m × c × ΔT / (t × 3600)."""
        zone = _make_zone(
            product_mass_per_day=_D("1000"),
            product_entry_temperature=_D("25"),
            product_target_temperature=_D("0"),
            cooling_duration=_D("4"),
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        zone_data = result.result["zones"][0]
        # 1000 × 3.85 × 25 / 4 / 3600 = 96250 / 14400 ≈ 6.684 kW
        assert zone_data["product_load_kw_r"] == pytest.approx(6.684, abs=0.001)

    def test_packaging_load(self) -> None:
        """Packaging heat load is added on top of product load."""
        zone = _make_zone(
            product_mass_per_day=_D("1000"),
            product_entry_temperature=_D("25"),
            product_target_temperature=_D("0"),
            cooling_duration=_D("4"),
            packaging_mass=_D("100"),
            packaging_specific_heat=_D("1.67"),
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        zone_data = result.result["zones"][0]
        # product sensible: ≈6.684
        # packaging: 100 × 1.67 × 25 / 4 / 3600 = 4175 / 14400 ≈ 0.290
        # total product: 6.684 + 0.290 = 6.974
        assert zone_data["product_load_kw_r"] == pytest.approx(6.974, abs=0.001)

    def test_product_step_appears_when_mass_positive(self) -> None:
        """A product load calculation step is recorded when product_mass > 0."""
        zone = _make_zone(product_mass_per_day=_D("500"))
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        step_formulas = [s.formula for s in result.steps]
        assert any("Q_product" in f for f in step_formulas)

    def test_no_product_step_when_mass_zero(self) -> None:
        """No product load step when product_mass_per_day is zero."""
        zone = _make_zone(product_mass_per_day=_D("0"))
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        step_formulas = [s.formula for s in result.steps]
        assert not any("Q_product" in f for f in step_formulas)


class TestCoolingLoadInfiltration:
    """Infiltration/ventilation load tests."""

    def test_infiltration_load(self) -> None:
        """Infiltration load: Q = ρ × V̇ × cp × ΔT / 3600."""
        zone = _make_zone(
            room_volume=_D("500"),
        )
        # air_change_rate is read from the CoefficientSet, not the zone
        cs = CoefficientSet(
            wall_u_value=_D("0.5"),
            roof_u_value=_D("0.4"),
            floor_u_value=_D("0.3"),
            air_change_rate=_D("2.0"),
            worker_heat_gain=_D("270"),
            motor_efficiency=_D("0.90"),
            design_margin_ratio=_D("1.10"),
            diversity_factor=_D("1.0"),
            revision_statuses={},
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=cs)
        result = calculate_cooling_load(inp)

        zone_data = result.result["zones"][0]
        # volume=500, airflow=2.0×500=1000, delta_t=35
        # 1.2 × 1000 × 1.006 × 35 / 3600 = 42252 / 3600 ≈ 11.737
        assert zone_data["infiltration_load_kw_r"] == pytest.approx(11.737, abs=0.001)

    def test_infiltration_with_door_opening_factor(self) -> None:
        """Door opening factor scales the infiltration airflow."""
        zone = _make_zone(
            room_volume=_D("500"),
            door_opening_factor=_D("1.5"),
            air_curtain_factor=_D("1.0"),
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        # air_change_rate=1.5 (from COEFFICIENTS), volume=500, airflow=750
        # effective = 750 × 1.5 × 1 = 1125
        # 1.2 × 1125 × 1.006 × 35 / 3600 ≈ 13.204
        zone_data = result.result["zones"][0]
        assert zone_data["infiltration_load_kw_r"] == pytest.approx(13.204, abs=0.001)


class TestCoolingLoadInternal:
    """Internal loads (people, lighting, equipment, fans)."""

    def test_people_load(self) -> None:
        """People load = count × worker_heat_gain × operating_fraction / 1000."""
        zone = _make_zone(worker_count=5)
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        zone_data = result.result["zones"][0]
        # 5 × 270 × 1.0 / 1000 = 1.350
        assert zone_data["people_load_kw_r"] == pytest.approx(1.350)

    def test_lighting_load(self) -> None:
        """Lighting load = power × operating_fraction / 1000."""
        zone = _make_zone(lighting_power=_D("500"))
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        zone_data = result.result["zones"][0]
        # 500 × 1.0 / 1000 = 0.500
        assert zone_data["lighting_load_kw_r"] == pytest.approx(0.500)

    def test_equipment_dissipation(self) -> None:
        """Equipment load = power × (1 - motor_efficiency) × fraction / 1000."""
        zone = _make_zone(equipment_power=_D("2000"))
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        zone_data = result.result["zones"][0]
        # motor_efficiency = 0.90 → dissipation = 0.10
        # 2000 × 1.0 × 0.10 / 1000 = 0.200
        assert zone_data["internal_equipment_load_kw_r"] == pytest.approx(0.200)

    def test_fan_load(self) -> None:
        """Fan motor load = power × operating_fraction / 1000."""
        zone = _make_zone(fan_motor_power=_D("300"))
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        zone_data = result.result["zones"][0]
        # 300 × 1.0 / 1000 = 0.300
        assert zone_data["evaporator_fan_load_kw_r"] == pytest.approx(0.300)

    def test_combined_internal_loads(self) -> None:
        """All internal load components summed correctly."""
        zone = _make_zone(
            worker_count=5,
            lighting_power=_D("500"),
            equipment_power=_D("2000"),
            fan_motor_power=_D("300"),
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        zone_data = result.result["zones"][0]
        # people=1.350, lighting=0.500, equipment=0.200, fan=0.300 → total=2.350
        assert zone_data["internal_load_kw_r"] == pytest.approx(2.350)


class TestCoolingLoadDefrost:
    """Defrost load tests."""

    def test_defrost_load(self) -> None:
        """Defrost average load = P × t × (1-η) / operating_hours / 1000."""
        zone = _make_zone(
            defrost_power=_D("2000"),
            defrost_duration=_D("2"),
            heat_recovery_fraction=_D("0"),
            operating_hours_per_day=_D("24"),
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        zone_data = result.result["zones"][0]
        # 2000 × 2 × 1 / 24 / 1000 = 4000 / 24000 ≈ 0.167
        assert zone_data["defrost_load_kw_r"] == pytest.approx(0.167, abs=0.001)

    def test_defrost_with_heat_recovery(self) -> None:
        """Heat recovery reduces the defrost load."""
        zone = _make_zone(
            defrost_power=_D("2000"),
            defrost_duration=_D("2"),
            heat_recovery_fraction=_D("0.5"),
            operating_hours_per_day=_D("24"),
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        zone_data = result.result["zones"][0]
        # 2000 × 2 × 0.5 / 24 / 1000 = 2000 / 24000 ≈ 0.083
        assert zone_data["defrost_load_kw_r"] == pytest.approx(0.083, abs=0.001)

    def test_no_defrost_step_when_zero(self) -> None:
        """No defrost calculation step when defrost power is zero."""
        zone = _make_zone(defrost_power=_D("0"))
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        step_formulas = [s.formula for s in result.steps]
        assert not any("Q_defrost" in f for f in step_formulas)


class TestCoolingLoadMultiZone:
    """Multi-zone and temperature level grouping tests."""

    def test_multi_zone_temperature_level_grouping(self) -> None:
        """Zones are grouped by temperature level."""
        zone_mt = _make_zone(
            zone_code="mt_room",
            zone_name="Medium Temp Room",
            temperature_level=TemperatureLevel.MEDIUM_TEMPERATURE,
        )
        zone_lt = _make_zone(
            zone_code="lt_room",
            zone_name="Low Temp Room",
            temperature_level=TemperatureLevel.LOW_TEMPERATURE,
        )
        inp = CoolingLoadCalcInput(zones=[zone_mt, zone_lt], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        levels = result.result["temperature_levels"]
        level_codes = [ls["temperature_level_code"] for ls in levels]
        assert "medium_temperature" in level_codes
        assert "low_temperature" in level_codes
        assert len(levels) == 2

    def test_two_zones_same_level(self) -> None:
        """Two zones at the same level share a level summary."""
        zone1 = _make_zone(zone_code="R1", zone_name="Room 1")
        zone2 = _make_zone(zone_code="R2", zone_name="Room 2")
        inp = CoolingLoadCalcInput(zones=[zone1, zone2], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        levels = result.result["temperature_levels"]
        assert len(levels) == 1
        assert levels[0]["room_count"] == 2
        assert set(levels[0]["zones"]) == {"R1", "R2"}


class TestCoolingLoadDiversity:
    """Diversity factor application tests."""

    def test_diversity_factor_applied_per_level(self) -> None:
        """Diversity factor scales each temperature level subtotal."""
        zone = _make_zone()
        cs = CoefficientSet(
            wall_u_value=_D("0.5"),
            roof_u_value=_D("0.4"),
            floor_u_value=_D("0.3"),
            air_change_rate=_D("1.5"),
            worker_heat_gain=_D("270"),
            motor_efficiency=_D("0.90"),
            design_margin_ratio=_D("1.10"),
            diversity_factor=_D("0.85"),
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=cs)
        result = calculate_cooling_load(inp)

        levels = result.result["temperature_levels"]
        subtotal = levels[0]["subtotal_load_kw_r"]
        diversified = levels[0]["diversified_load_kw_r"]
        assert diversified == pytest.approx(subtotal * 0.85, abs=0.01)

    def test_diversity_factor_overridden_by_input(self) -> None:
        """Input-level diversity_factor overrides coefficient."""
        zone = _make_zone()
        cs = CoefficientSet(
            wall_u_value=_D("0.5"),
            roof_u_value=_D("0.4"),
            floor_u_value=_D("0.3"),
            air_change_rate=_D("1.5"),
            worker_heat_gain=_D("270"),
            motor_efficiency=_D("0.90"),
            design_margin_ratio=_D("1.10"),
            diversity_factor=_D("0.85"),
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=cs, diversity_factor=_D("0.70"))
        result = calculate_cooling_load(inp)

        # Input override takes precedence: 0.70 not 0.85
        assert result.result["diversity_factor"] == "0.70"


class TestCoolingLoadDesignMargin:
    """Design margin application tests."""

    def test_design_margin_applied(self) -> None:
        """Design margin adds a percentage on top of diversified load."""
        zone = _make_zone()
        cs = CoefficientSet(
            wall_u_value=_D("0.5"),
            roof_u_value=_D("0.4"),
            floor_u_value=_D("0.3"),
            air_change_rate=_D("1.5"),
            worker_heat_gain=_D("270"),
            motor_efficiency=_D("0.90"),
            design_margin_ratio=_D("1.15"),
            diversity_factor=_D("1.0"),
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=cs)
        result = calculate_cooling_load(inp)

        total_diversified = result.result["total_diversified_load_kw_r"]
        design_load = result.result["design_refrigeration_load_kw_r"]
        margin = result.result["design_margin_kw_r"]

        # design_load = total_diversified + total_diversified × 0.15
        expected_margin = round(total_diversified * 0.15, 3)
        assert margin == pytest.approx(expected_margin, abs=0.01)
        assert design_load == pytest.approx(total_diversified + margin, abs=0.01)

    def test_design_margin_overridden_by_input(self) -> None:
        """Input-level design_margin_ratio overrides coefficient."""
        zone = _make_zone()
        cs = CoefficientSet(
            wall_u_value=_D("0.5"),
            roof_u_value=_D("0.4"),
            floor_u_value=_D("0.3"),
            air_change_rate=_D("1.5"),
            worker_heat_gain=_D("270"),
            motor_efficiency=_D("0.90"),
            design_margin_ratio=_D("1.10"),
            diversity_factor=_D("1.0"),
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=cs, design_margin_ratio=_D("1.20"))
        result = calculate_cooling_load(inp)

        assert result.result["design_margin_ratio"] == "1.20"


class TestCoolingLoadErrors:
    """Error handling tests."""

    def test_empty_zones_raises_error(self) -> None:
        """MissingCalculationInputError for empty zones list."""
        inp = CoolingLoadCalcInput(zones=[], coefficients=COEFFICIENTS)
        with pytest.raises(MissingCalculationInputError) as exc_info:
            calculate_cooling_load(inp)
        assert "zones" in str(exc_info.value)

    def test_missing_wall_u_value_raises_error(self) -> None:
        """CoefficientMissingError when wall U-value is absent."""
        zone = _make_zone(u_value_wall=None)
        cs = CoefficientSet(
            wall_u_value=None,
            roof_u_value=_D("0.4"),
            floor_u_value=_D("0.3"),
            air_change_rate=_D("1.5"),
            worker_heat_gain=_D("270"),
            motor_efficiency=_D("0.90"),
            design_margin_ratio=_D("1.10"),
            diversity_factor=_D("1.0"),
            revision_statuses={},
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=cs)
        with pytest.raises(CoefficientMissingError) as exc_info:
            calculate_cooling_load(inp)
        assert "wall_u_value" in str(exc_info.value)

    def test_missing_product_specific_heat_raises_error(self) -> None:
        """CoefficientMissingError when product specific heat is absent and product exists."""
        zone = _make_zone(product_mass_per_day=_D("1000"), product_specific_heat=None)
        cs = CoefficientSet(
            wall_u_value=_D("0.5"),
            roof_u_value=_D("0.4"),
            floor_u_value=_D("0.3"),
            product_specific_heat=None,
            air_change_rate=_D("1.5"),
            worker_heat_gain=_D("270"),
            motor_efficiency=_D("0.90"),
            design_margin_ratio=_D("1.10"),
            diversity_factor=_D("1.0"),
            revision_statuses={},
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=cs)
        with pytest.raises(CoefficientMissingError):
            calculate_cooling_load(inp)

    def test_missing_worker_heat_gain_raises_error(self) -> None:
        """CoefficientMissingError when worker heat gain is absent."""
        zone = _make_zone(worker_count=1, worker_heat_gain=None)
        cs = CoefficientSet(
            wall_u_value=_D("0.5"),
            roof_u_value=_D("0.4"),
            floor_u_value=_D("0.3"),
            air_change_rate=_D("1.5"),
            worker_heat_gain=None,
            motor_efficiency=_D("0.90"),
            design_margin_ratio=_D("1.10"),
            diversity_factor=_D("1.0"),
            revision_statuses={},
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=cs)
        with pytest.raises(CoefficientMissingError):
            calculate_cooling_load(inp)


class TestCoolingLoadWarnings:
    """Warning and review status tests."""

    def test_demo_coefficient_warning(self) -> None:
        """No source metadata triggers NO_COEFFICIENT_SOURCES warning."""
        zone = _make_zone()
        cs = CoefficientSet(
            wall_u_value=_D("0.5"),
            roof_u_value=_D("0.4"),
            floor_u_value=_D("0.3"),
            air_change_rate=_D("1.5"),
            worker_heat_gain=_D("270"),
            motor_efficiency=_D("0.90"),
            design_margin_ratio=_D("1.10"),
            diversity_factor=_D("1.0"),
            # source_types deliberately empty (demo)
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=cs)
        result = calculate_cooling_load(inp)

        warning_codes = [w.code for w in result.warnings]
        assert "NO_COEFFICIENT_SOURCES" in warning_codes

    def test_requires_review_when_demo(self) -> None:
        """requires_review is True when coefficients have no approved sources."""
        zone = _make_zone()
        cs = CoefficientSet(
            wall_u_value=_D("0.5"),
            roof_u_value=_D("0.4"),
            floor_u_value=_D("0.3"),
            air_change_rate=_D("1.5"),
            worker_heat_gain=_D("270"),
            motor_efficiency=_D("0.90"),
            design_margin_ratio=_D("1.10"),
            diversity_factor=_D("1.0"),
            revision_statuses={},
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=cs)
        result = calculate_cooling_load(inp)

        assert result.requires_review is True

    def test_approved_source_no_requires_review(self) -> None:
        """When all sources are approved, requires_review is False."""
        zone = _make_zone(
            outdoor_relative_humidity=_D("0.70"),
            indoor_relative_humidity=_D("0.80"),
        )
        cs = CoefficientSet(
            wall_u_value=_D("0.5"),
            roof_u_value=_D("0.4"),
            floor_u_value=_D("0.3"),
            air_change_rate=_D("1.5"),
            worker_heat_gain=_D("270"),
            motor_efficiency=_D("0.90"),
            design_margin_ratio=_D("1.10"),
            diversity_factor=_D("1.0"),
            source_types={
                "cooling.wall_u_value": "approved",
                "cooling.roof_u_value": "approved",
                "cooling.floor_u_value": "approved",
                "cooling.air_change_rate": "approved",
                "cooling.worker_heat_gain": "approved",
                "power.motor_efficiency": "approved",
            },
            revision_statuses={
                "cooling.wall_u_value": "approved",
                "cooling.roof_u_value": "approved",
                "cooling.floor_u_value": "approved",
                "cooling.air_change_rate": "approved",
                "cooling.worker_heat_gain": "approved",
                "power.motor_efficiency": "approved",
            },
        )
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=cs)
        result = calculate_cooling_load(inp)

        assert result.requires_review is False
        warning_codes = [w.code for w in result.warnings]
        assert "NO_COEFFICIENT_SOURCES" not in warning_codes


class TestCoolingLoadDeterminism:
    """Determinism and traceability tests."""

    def test_deterministic_results(self) -> None:
        """Same inputs produce identical outputs."""
        zone = _make_zone()
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        r1 = calculate_cooling_load(inp)
        r2 = calculate_cooling_load(inp)
        assert r1.result == r2.result

    def test_step_traceability(self) -> None:
        """All steps have non-empty formula, description, output_name, output_value."""
        zone = _make_zone()
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        for step in result.steps:
            assert step.formula != ""
            assert step.description != ""
            assert step.output_name != ""
            assert step.output_value != ""

    def test_envelope_step_present(self) -> None:
        """The envelope transmission step is always present."""
        zone = _make_zone()
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        step_formulas = [s.formula for s in result.steps]
        assert any("U × A × ΔT" in f for f in step_formulas)

    def test_subtotal_step_present(self) -> None:
        """The zone subtotal step is always present."""
        zone = _make_zone()
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        step_formulas = [s.formula for s in result.steps]
        assert any("subtotal" in f for f in step_formulas)

    def test_grouping_step_present(self) -> None:
        """The CL-GROUP step records temperature level grouping."""
        zone = _make_zone()
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        step_ids = [s.step_id for s in result.steps]
        assert "CL-GROUP" in step_ids

    def test_final_step_present(self) -> None:
        """The CL-FINAL step records the design refrigeration load."""
        zone = _make_zone()
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)

        step_ids = [s.step_id for s in result.steps]
        assert "CL-FINAL" in step_ids

    def test_result_version(self) -> None:
        """Calculator version is reported."""
        zone = _make_zone()
        inp = CoolingLoadCalcInput(zones=[zone], coefficients=COEFFICIENTS)
        result = calculate_cooling_load(inp)
        assert result.calculator_version == "1.0.0"


# ============================================================================
# Equipment capability calculator tests
# ============================================================================


class TestEquipmentSingleSystem:
    """Single system with single zone tests."""

    def test_single_system_single_zone(self) -> None:
        """Basic equipment capability for one zone at 10 kW(r)."""
        zone_eq = _make_zone_equipment(design_load=Decimal("10"))
        system = TemperatureSystemInput(
            system_code="SYS-MT",
            system_name="Medium Temperature System",
            design_evaporating_temperature=_D("-10"),
            zones=[zone_eq],
        )
        inp = EquipmentCapabilityCalcInput(systems=[system], coefficients=EQUIPMENT_COEFFICIENTS)
        result = calculate_equipment_capability(inp)

        assert result.success is True
        assert result.calculator_name == "equipment"

        sys_result = result.result["systems"][0]
        # system_simultaneous = 10
        assert sys_result["system_simultaneous_load_kw_r"] == pytest.approx(10.0)
        # evaporator_total = 10 × 1.10 = 11.0
        assert sys_result["evaporator_total_capacity_kw_r"] == pytest.approx(11.0)
        # compressor_operating = 10
        assert sys_result["compressor_operating_capacity_kw_r"] == pytest.approx(10.0)
        # compressor_installed = 10 × 1.10 = 11.0
        assert sys_result["compressor_installed_capacity_kw_r"] == pytest.approx(11.0)
        # standby = 11 - 10 = 1.0
        assert sys_result["compressor_standby_capacity_kw_r"] == pytest.approx(1.0)


class TestEquipmentMultiZone:
    """Multi-zone system tests."""

    def test_multi_zone_system(self) -> None:
        """Two zones in the same system sum their loads."""
        zone1 = _make_zone_equipment(zone_code="Z1", design_load=Decimal("10"))
        zone2 = _make_zone_equipment(zone_code="Z2", design_load=Decimal("15"))
        system = TemperatureSystemInput(
            system_code="SYS-MT",
            system_name="Medium Temp System",
            design_evaporating_temperature=_D("-10"),
            zones=[zone1, zone2],
        )
        inp = EquipmentCapabilityCalcInput(systems=[system], coefficients=EQUIPMENT_COEFFICIENTS)
        result = calculate_equipment_capability(inp)

        sys_result = result.result["systems"][0]
        # system_simultaneous = 10 + 15 = 25
        assert sys_result["system_simultaneous_load_kw_r"] == pytest.approx(25.0)
        # evaporator_total = 25 × 1.10 = 27.5
        assert sys_result["evaporator_total_capacity_kw_r"] == pytest.approx(27.5)
        # compressor_installed = 25 × 1.10 = 27.5
        assert sys_result["compressor_installed_capacity_kw_r"] == pytest.approx(27.5)


class TestEquipmentRedundancy:
    """N+1 redundancy tests."""

    def test_n_plus_one_redundancy(self) -> None:
        """Standby capacity = installed - operating (redundancy ratio)."""
        zone_eq = _make_zone_equipment(design_load=Decimal("20"))
        cs = EquipmentCoefficientSet(
            redundancy_ratio=_D("1.25"),  # 25% standby
            evaporator_capacity_margin=_D("1.10"),
            condenser_capacity_margin=_D("1.15"),
            compressor_cop=_D("3.0"),
        )
        system = TemperatureSystemInput(
            system_code="SYS-LT",
            system_name="Low Temp System",
            design_evaporating_temperature=_D("-25"),
            zones=[zone_eq],
        )
        inp = EquipmentCapabilityCalcInput(systems=[system], coefficients=cs)
        result = calculate_equipment_capability(inp)

        sys_result = result.result["systems"][0]
        # installed = 20 × 1.25 = 25.0
        assert sys_result["compressor_installed_capacity_kw_r"] == pytest.approx(25.0)
        # standby = 25 - 20 = 5.0
        assert sys_result["compressor_standby_capacity_kw_r"] == pytest.approx(5.0)


class TestEquipmentCondenser:
    """Condenser heat rejection tests."""

    def test_condenser_heat_rejection(self) -> None:
        """Condenser = (operating + input_power) × condenser_margin."""
        zone_eq = _make_zone_equipment(design_load=Decimal("10"))
        system = TemperatureSystemInput(
            system_code="SYS-MT",
            system_name="Medium Temp System",
            design_evaporating_temperature=_D("-10"),
            zones=[zone_eq],
        )
        inp = EquipmentCapabilityCalcInput(systems=[system], coefficients=EQUIPMENT_COEFFICIENTS)
        result = calculate_equipment_capability(inp)

        sys_result = result.result["systems"][0]
        # operating=10, COP=3, input_power=10/3≈3.333
        # condenser_base = 10 + 3.333 = 13.333
        # condenser_with_margin = 13.333 × 1.15 = 15.333
        assert sys_result["condenser_heat_rejection_kw"] == pytest.approx(15.333, abs=0.01)

    def test_condenser_margin_only(self) -> None:
        """Custom condenser margin changes condenser output (no rejection factor)."""
        zone_eq = _make_zone_equipment(design_load=Decimal("10"))
        cs = EquipmentCoefficientSet(
            redundancy_ratio=_D("1.10"),
            evaporator_capacity_margin=_D("1.10"),
            condenser_capacity_margin=_D("1.0"),  # no margin
            compressor_cop=_D("3.0"),
        )
        system = TemperatureSystemInput(
            system_code="SYS-MT",
            system_name="Medium Temp System",
            design_evaporating_temperature=_D("-10"),
            zones=[zone_eq],
        )
        inp = EquipmentCapabilityCalcInput(systems=[system], coefficients=cs)
        result = calculate_equipment_capability(inp)

        sys_result = result.result["systems"][0]
        # operating=10, input_power≈3.333
        # condenser_base = 10 + 3.333 = 13.333
        # no margin (1.0) → 13.333
        assert sys_result["condenser_heat_rejection_kw"] == pytest.approx(13.333, abs=0.01)


class TestEquipmentCOP:
    """COP-based input power tests."""

    def test_cop_input_power(self) -> None:
        """Input power = refrigeration_capacity / COP."""
        zone_eq = _make_zone_equipment(design_load=Decimal("10"))
        cs = EquipmentCoefficientSet(
            redundancy_ratio=_D("1.10"),
            evaporator_capacity_margin=_D("1.10"),
            condenser_capacity_margin=_D("1.15"),
            compressor_cop=_D("2.5"),
        )
        system = TemperatureSystemInput(
            system_code="SYS-MT",
            system_name="Medium Temp System",
            design_evaporating_temperature=_D("-10"),
            zones=[zone_eq],
        )
        inp = EquipmentCapabilityCalcInput(systems=[system], coefficients=cs)
        result = calculate_equipment_capability(inp)

        sys_result = result.result["systems"][0]
        # input_power = 10 / 2.5 = 4.0
        assert sys_result["compressor_input_power_kw_e"] == pytest.approx(4.0)

    def test_cop_zero_raises_error(self) -> None:
        """COP = 0 raises InvalidCalculationInputError."""
        zone_eq = _make_zone_equipment(design_load=Decimal("10"))
        cs = EquipmentCoefficientSet(
            redundancy_ratio=_D("1.10"),
            evaporator_capacity_margin=_D("1.10"),
            condenser_capacity_margin=_D("1.15"),
            compressor_cop=_D("0"),
        )
        system = TemperatureSystemInput(
            system_code="SYS-MT",
            system_name="Medium Temp System",
            design_evaporating_temperature=_D("-10"),
            zones=[zone_eq],
        )
        inp = EquipmentCapabilityCalcInput(systems=[system], coefficients=cs)
        from cold_storage.modules.calculations.domain.errors import InvalidCalculationInputError

        with pytest.raises(InvalidCalculationInputError):
            calculate_equipment_capability(inp)

    def test_cop_negative_raises_error(self) -> None:
        """COP < 0 raises InvalidCalculationInputError."""
        zone_eq = _make_zone_equipment(design_load=Decimal("10"))
        cs = EquipmentCoefficientSet(
            redundancy_ratio=_D("1.10"),
            evaporator_capacity_margin=_D("1.10"),
            condenser_capacity_margin=_D("1.15"),
            compressor_cop=_D("-1.5"),
        )
        system = TemperatureSystemInput(
            system_code="SYS-MT",
            system_name="Medium Temp System",
            design_evaporating_temperature=_D("-10"),
            zones=[zone_eq],
        )
        inp = EquipmentCapabilityCalcInput(systems=[system], coefficients=cs)
        from cold_storage.modules.calculations.domain.errors import InvalidCalculationInputError

        with pytest.raises(InvalidCalculationInputError):
            calculate_equipment_capability(inp)

    def test_cop_missing_raises_error(self) -> None:
        """COP = None raises CoefficientMissingError."""
        zone_eq = _make_zone_equipment(design_load=Decimal("10"))
        cs = EquipmentCoefficientSet(
            redundancy_ratio=_D("1.10"),
            evaporator_capacity_margin=_D("1.10"),
            condenser_capacity_margin=_D("1.15"),
            compressor_cop=None,
        )
        system = TemperatureSystemInput(
            system_code="SYS-MT",
            system_name="Medium Temp System",
            design_evaporating_temperature=_D("-10"),
            zones=[zone_eq],
        )
        inp = EquipmentCapabilityCalcInput(systems=[system], coefficients=cs)
        with pytest.raises(CoefficientMissingError):
            calculate_equipment_capability(inp)


class TestEquipmentErrors:
    """Equipment error handling tests."""

    def test_empty_systems_raises_error(self) -> None:
        """MissingCalculationInputError when systems list is empty."""
        inp = EquipmentCapabilityCalcInput(systems=[], coefficients=EQUIPMENT_COEFFICIENTS)
        with pytest.raises(MissingCalculationInputError) as exc_info:
            calculate_equipment_capability(inp)
        assert "systems" in str(exc_info.value)


class TestEquipmentDeterminism:
    """Equipment determinism and traceability tests."""

    def test_deterministic_results(self) -> None:
        """Same inputs produce identical outputs."""
        zone_eq = _make_zone_equipment(design_load=Decimal("10"))
        system = TemperatureSystemInput(
            system_code="SYS-MT",
            system_name="Medium Temp System",
            design_evaporating_temperature=_D("-10"),
            zones=[zone_eq],
        )
        inp = EquipmentCapabilityCalcInput(systems=[system], coefficients=EQUIPMENT_COEFFICIENTS)
        r1 = calculate_equipment_capability(inp)
        r2 = calculate_equipment_capability(inp)
        assert r1.result == r2.result

    def test_step_traceability(self) -> None:
        """All steps have non-empty formula, description, output_name."""
        zone_eq = _make_zone_equipment(design_load=Decimal("10"))
        system = TemperatureSystemInput(
            system_code="SYS-MT",
            system_name="Medium Temp System",
            design_evaporating_temperature=_D("-10"),
            zones=[zone_eq],
        )
        inp = EquipmentCapabilityCalcInput(systems=[system], coefficients=EQUIPMENT_COEFFICIENTS)
        result = calculate_equipment_capability(inp)

        assert len(result.steps) > 0
        for step in result.steps:
            assert step.formula != ""
            assert step.description != ""
            assert step.output_name != ""
            assert step.output_value != ""

    def test_sum_step_present(self) -> None:
        """EQ-SUM step is recorded for zone load summation."""
        zone_eq = _make_zone_equipment(design_load=Decimal("10"))
        system = TemperatureSystemInput(
            system_code="SYS-MT",
            system_name="Medium Temp System",
            design_evaporating_temperature=_D("-10"),
            zones=[zone_eq],
        )
        inp = EquipmentCapabilityCalcInput(systems=[system], coefficients=EQUIPMENT_COEFFICIENTS)
        result = calculate_equipment_capability(inp)

        step_ids = [s.step_id for s in result.steps]
        assert "EQ-SUM-SYS-MT" in step_ids

    def test_total_step_present(self) -> None:
        """EQ-TOTAL step records aggregate totals."""
        zone_eq = _make_zone_equipment(design_load=Decimal("10"))
        system = TemperatureSystemInput(
            system_code="SYS-MT",
            system_name="Medium Temp System",
            design_evaporating_temperature=_D("-10"),
            zones=[zone_eq],
        )
        inp = EquipmentCapabilityCalcInput(systems=[system], coefficients=EQUIPMENT_COEFFICIENTS)
        result = calculate_equipment_capability(inp)

        step_ids = [s.step_id for s in result.steps]
        assert "EQ-TOTAL" in step_ids

    def test_version(self) -> None:
        """Calculator version is reported."""
        zone_eq = _make_zone_equipment(design_load=Decimal("10"))
        system = TemperatureSystemInput(
            system_code="SYS-MT",
            system_name="Medium Temp System",
            design_evaporating_temperature=_D("-10"),
            zones=[zone_eq],
        )
        inp = EquipmentCapabilityCalcInput(systems=[system], coefficients=EQUIPMENT_COEFFICIENTS)
        result = calculate_equipment_capability(inp)
        assert result.calculator_version == "1.0.0"


class TestEquipmentEvaporatorCount:
    """Evaporator count and per-unit capacity tests."""

    def test_single_evaporator_per_zone(self) -> None:
        """Evaporator count and per-evaporator capacity."""
        zone1 = _make_zone_equipment(zone_code="Z1", design_load=Decimal("10"), evaporator_count=2)
        system = TemperatureSystemInput(
            system_code="SYS-MT",
            system_name="Medium Temp System",
            design_evaporating_temperature=_D("-10"),
            zones=[zone1],
        )
        inp = EquipmentCapabilityCalcInput(systems=[system], coefficients=EQUIPMENT_COEFFICIENTS)
        result = calculate_equipment_capability(inp)

        sys_result = result.result["systems"][0]
        assert sys_result["evaporator_count"] == 2
        # evaporator_total = 10 × 1.10 = 11.0
        # single = 11.0 / 2 = 5.5
        assert sys_result["single_evaporator_capacity_kw_r"] == pytest.approx(5.5)


# ============================================================================
# Installed power calculator tests
# ============================================================================


class TestPowerRefrigerationComponents:
    """Refrigeration power component tests."""

    def test_refrigeration_power_sum(self) -> None:
        """Refrigeration power = compressor + fans + pumps + defrost."""
        inp = InstalledPowerCalcInput(
            compressor_input_power_kw_e=_D("10"),
            evaporator_fan_power_kw_e=_D("5"),
            condenser_fan_power_kw_e=_D("3"),
            pump_power_kw_e=_D("2"),
            defrost_power_kw_e=_D("1"),
        )
        result = calculate_installed_power(inp)

        assert result.success is True
        assert result.calculator_name == "installed_power"
        assert result.result["refrigeration_system_installed_power_kw_e"] == pytest.approx(21.0)

    def test_refrigeration_zero_components(self) -> None:
        """All refrigeration components zero gives zero total."""
        inp = InstalledPowerCalcInput()
        result = calculate_installed_power(inp)
        assert result.result["refrigeration_system_installed_power_kw_e"] == pytest.approx(0.0)


class TestPowerProcessingEquipment:
    """Processing equipment power tests."""

    def test_processing_power(self) -> None:
        """Processing equipment power is reported directly."""
        inp = InstalledPowerCalcInput(
            processing_equipment_power_kw_e=_D("15"),
        )
        result = calculate_installed_power(inp)
        assert result.result["process_equipment_installed_power_kw_e"] == pytest.approx(15.0)


class TestPowerTotal:
    """Total installed power tests."""

    def test_total_installed_power(self) -> None:
        """Total = refrigeration + processing + lighting + auxiliary."""
        inp = InstalledPowerCalcInput(
            compressor_input_power_kw_e=_D("10"),
            evaporator_fan_power_kw_e=_D("5"),
            condenser_fan_power_kw_e=_D("3"),
            pump_power_kw_e=_D("2"),
            defrost_power_kw_e=_D("1"),
            processing_equipment_power_kw_e=_D("15"),
            lighting_power_kw_e=_D("5"),
            other_auxiliary_power_kw_e=_D("3"),
        )
        result = calculate_installed_power(inp)

        # refrigeration=21, processing=15, lighting=5, auxiliary=3 → total=44
        assert result.result["total_installed_power_kw_e"] == pytest.approx(44.0)

    def test_lighting_power(self) -> None:
        """Lighting power is reported directly."""
        inp = InstalledPowerCalcInput(lighting_power_kw_e=_D("5"))
        result = calculate_installed_power(inp)
        assert result.result["lighting_installed_power_kw_e"] == pytest.approx(5.0)

    def test_auxiliary_power(self) -> None:
        """Auxiliary power is reported directly."""
        inp = InstalledPowerCalcInput(other_auxiliary_power_kw_e=_D("3"))
        result = calculate_installed_power(inp)
        assert result.result["auxiliary_installed_power_kw_e"] == pytest.approx(3.0)


class TestPowerPeakDemand:
    """Estimated peak demand tests."""

    def test_estimated_peak_demand(self) -> None:
        """Peak demand = refrig×df_ref + process×df_proc + lighting + aux."""
        inp = InstalledPowerCalcInput(
            compressor_input_power_kw_e=_D("10"),
            evaporator_fan_power_kw_e=_D("5"),
            condenser_fan_power_kw_e=_D("3"),
            pump_power_kw_e=_D("2"),
            defrost_power_kw_e=_D("1"),
            processing_equipment_power_kw_e=_D("15"),
            lighting_power_kw_e=_D("5"),
            other_auxiliary_power_kw_e=_D("3"),
            refrigeration_demand_factor=_D("0.90"),
            production_demand_factor=_D("0.90"),
        )
        result = calculate_installed_power(inp)

        # refrigeration=21, refrig_demand=21×0.9=18.9
        # processing=15, proc_demand=15×0.9=13.5
        # peak = 18.9 + 13.5 + 5 + 3 = 40.4
        assert result.result["estimated_peak_demand_kw_e"] == pytest.approx(40.4, abs=0.01)

    def test_peak_demand_less_than_installed(self) -> None:
        """Peak demand ≤ total installed power (demand factors ≤ 1)."""
        inp = InstalledPowerCalcInput(
            compressor_input_power_kw_e=_D("10"),
            evaporator_fan_power_kw_e=_D("5"),
            condenser_fan_power_kw_e=_D("3"),
            pump_power_kw_e=_D("2"),
            defrost_power_kw_e=_D("1"),
            processing_equipment_power_kw_e=_D("15"),
            lighting_power_kw_e=_D("5"),
            other_auxiliary_power_kw_e=_D("3"),
            refrigeration_demand_factor=_D("0.90"),
            production_demand_factor=_D("0.90"),
        )
        result = calculate_installed_power(inp)
        assert (
            result.result["estimated_peak_demand_kw_e"]
            <= result.result["total_installed_power_kw_e"]
        )


class TestPowerKWeUnits:
    """kW(e) unit verification tests."""

    def test_all_outputs_are_kw_e(self) -> None:
        """All output keys contain 'kw_e' suffix."""
        inp = InstalledPowerCalcInput(
            compressor_input_power_kw_e=_D("10"),
            processing_equipment_power_kw_e=_D("5"),
        )
        result = calculate_installed_power(inp)

        kw_e_keys = [k for k in result.result if k.endswith("_kw_e") and k != "equipment_items"]
        # At minimum: refrigeration, processing, lighting, auxiliary, total, peak
        assert len(kw_e_keys) >= 5

    def test_peak_demand_step_output(self) -> None:
        """The peak demand step outputs estimated_peak_demand_kw_e."""
        inp = InstalledPowerCalcInput(
            compressor_input_power_kw_e=_D("10"),
            processing_equipment_power_kw_e=_D("5"),
        )
        result = calculate_installed_power(inp)

        demand_steps = [s for s in result.steps if s.step_id == "PW-DEMAND"]
        assert len(demand_steps) == 1
        assert demand_steps[0].output_name == "estimated_peak_demand_kw_e"


class TestPowerEquipmentItems:
    """Equipment item breakdown tests."""

    def test_equipment_item_breakdown(self) -> None:
        """Equipment items produce a breakdown in the result."""
        items = [
            PowerEquipmentItem(
                name="Compressor A",
                category="refrigeration",
                quantity=2,
                unit_power_kw_e=_D("5.0"),
                demand_factor=_D("0.90"),
            ),
            PowerEquipmentItem(
                name="Conveyor Belt",
                category="production",
                quantity=1,
                unit_power_kw_e=_D("3.0"),
                demand_factor=_D("1.0"),
            ),
        ]
        inp = InstalledPowerCalcInput(equipment_items=items)
        result = calculate_installed_power(inp)

        breakdown = result.result["equipment_items"]
        assert len(breakdown) == 2
        assert breakdown[0]["name"] == "Compressor A"
        assert breakdown[0]["category"] == "refrigeration"
        assert breakdown[0]["quantity"] == 2
        assert breakdown[0]["unit_power_kw_e"] == "5.0"
        assert breakdown[0]["total_power_kw_e"] == "10.000"
        assert breakdown[0]["demand_factor"] == "0.90"
        assert breakdown[0]["demand_power_kw_e"] == "9.000"

    def test_equipment_item_demand_power(self) -> None:
        """demand_power = total_power × demand_factor."""
        item = PowerEquipmentItem(
            name="Pump",
            category="refrigeration",
            quantity=3,
            unit_power_kw_e=_D("2.0"),
            demand_factor=_D("0.80"),
        )
        # total = 3 × 2.0 = 6.0
        # demand = 6.0 × 0.80 = 4.800
        assert item.total_power_kw_e == _D("6.000")
        assert item.demand_power_kw_e == _D("4.800")

    def test_empty_items_list(self) -> None:
        """Empty equipment items list produces empty breakdown."""
        inp = InstalledPowerCalcInput(equipment_items=[])
        result = calculate_installed_power(inp)
        assert result.result["equipment_items"] == []

    def test_input_snapshot_has_item_count(self) -> None:
        """Input snapshot records equipment_item_count."""
        items = [
            PowerEquipmentItem(
                name="Motor",
                category="auxiliary",
                quantity=1,
                unit_power_kw_e=_D("1.0"),
            )
        ]
        inp = InstalledPowerCalcInput(equipment_items=items)
        result = calculate_installed_power(inp)
        assert result.input_snapshot["equipment_item_count"] == 1


class TestPowerDeterminism:
    """Power calculator determinism and traceability tests."""

    def test_deterministic_results(self) -> None:
        """Same inputs produce identical outputs."""
        inp = InstalledPowerCalcInput(
            compressor_input_power_kw_e=_D("10"),
            evaporator_fan_power_kw_e=_D("5"),
            processing_equipment_power_kw_e=_D("15"),
            lighting_power_kw_e=_D("5"),
        )
        r1 = calculate_installed_power(inp)
        r2 = calculate_installed_power(inp)
        assert r1.result == r2.result

    def test_step_traceability(self) -> None:
        """All steps have non-empty formula, description, output_name."""
        inp = InstalledPowerCalcInput(
            compressor_input_power_kw_e=_D("10"),
            processing_equipment_power_kw_e=_D("5"),
        )
        result = calculate_installed_power(inp)

        assert len(result.steps) > 0
        for step in result.steps:
            assert step.formula != ""
            assert step.description != ""
            assert step.output_name != ""
            assert step.output_value != ""

    def test_all_step_ids_present(self) -> None:
        """Expected step IDs are all present."""
        inp = InstalledPowerCalcInput(
            compressor_input_power_kw_e=_D("10"),
            processing_equipment_power_kw_e=_D("5"),
        )
        result = calculate_installed_power(inp)

        step_ids = [s.step_id for s in result.steps]
        assert "PW-REFRIG" in step_ids
        assert "PW-PROC" in step_ids
        assert "PW-LIGHT" in step_ids
        assert "PW-AUX" in step_ids
        assert "PW-TOTAL" in step_ids
        assert "PW-DEMAND" in step_ids

    def test_version(self) -> None:
        """Calculator version is reported."""
        inp = InstalledPowerCalcInput()
        result = calculate_installed_power(inp)
        assert result.calculator_version == "1.0.0"


class TestPowerWarnings:
    """Power calculator warning tests."""

    def test_high_demand_factor_with_defrost_warning(self) -> None:
        """High refrigeration demand factor with defrost triggers a warning."""
        inp = InstalledPowerCalcInput(
            defrost_power_kw_e=_D("5"),
            refrigeration_demand_factor=_D("0.90"),
        )
        result = calculate_installed_power(inp)

        warning_codes = [w.code for w in result.warnings]
        assert "DEFAULT_DEMAND_FACTOR" in warning_codes

    def test_no_warning_when_defrost_zero(self) -> None:
        """No warning when defrost power is zero regardless of demand factor."""
        inp = InstalledPowerCalcInput(
            defrost_power_kw_e=_D("0"),
            refrigeration_demand_factor=_D("0.90"),
        )
        result = calculate_installed_power(inp)

        warning_codes = [w.code for w in result.warnings]
        assert "DEFAULT_DEMAND_FACTOR" not in warning_codes

    def test_no_warning_when_low_demand_factor(self) -> None:
        """No warning when refrigeration demand factor is low."""
        inp = InstalledPowerCalcInput(
            defrost_power_kw_e=_D("5"),
            refrigeration_demand_factor=_D("0.40"),
        )
        result = calculate_installed_power(inp)

        warning_codes = [w.code for w in result.warnings]
        assert "DEFAULT_DEMAND_FACTOR" not in warning_codes
