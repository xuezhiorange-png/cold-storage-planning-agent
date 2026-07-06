"""Unit tests for the production calculation adapter wrappers (Phase 2).

The adapter contract requires:

* ``requires_review`` is propagated verbatim from the calculator
  (no suppression, no reclassification)
* The adapter never writes to the database
* The adapter accepts typed ``CalculatorInputProjection`` only
* Warnings and blockers are surfaced verbatim
* ``content_hash`` matches the canonical SHA-256 of the payload

These tests cover all five adapters and the shared result builder.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from cold_storage.modules.orchestration.application.production_calculation import (
    adapters,
    projection,
)
from cold_storage.modules.orchestration.application.production_calculation.contract import (
    assert_requires_review_propagated,
    freeze_for_hash,
    validate_adapter_result,
)
from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    AdapterResult,
    CalculatorInputProjection,
)
from cold_storage.modules.orchestration.application.production_calculation.errors import (
    AdapterContractViolationError,
    CalculatorRejectedInputError,
    UnsupportedReviewRequiredOutputError,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType

# ── Reusable valid input dictionaries ─────────────────────────────────────


def _zone_inputs() -> dict[str, Any]:
    return {
        "daily_inbound_mass_kg": 5000.0,
        "working_time_h_per_day": 8.0,
        "finished_storage_days": 5.0,
        "packaging_storage_days": 3.0,
        "precooling_required_ratio": 0.8,
    }


def _cooling_load_inputs() -> dict[str, Any]:
    return {
        "zones": [
            {
                "zone_code": "Z1",
                "zone_name": "Freezer",
                "zone_area": "100.0",
                "room_height": "5.0",
                "wall_area": "200.0",
                "roof_area": "100.0",
                "floor_area": "100.0",
                "u_value_wall": "0.25",
                "u_value_roof": "0.20",
                "u_value_floor": "0.30",
                "outdoor_design_temperature": "30.0",
                "room_design_temperature": "-18.0",
                "operating_hours_per_day": "16.0",
                "product_entry_temperature": "20.0",
                "product_target_temperature": "-18.0",
                "cooling_duration": "8.0",
                "temperature_level": "low_temperature",
            }
        ],
        "coefficients": {
            "design_margin_ratio": "1.1",
            "diversity_factor": "0.85",
            "product_specific_heat": "3.6",
            "respiration_heat": "0.0",
            "air_change_rate": "0.5",
            # The adapter threads these onto the zone so the
            # calculator (which reads them from the zone) has
            # what it needs.
            "worker_heat_gain": "0.275",
            "motor_efficiency": "0.85",
        },
    }


def _equipment_inputs() -> dict[str, Any]:
    return {
        "systems": [
            {
                "system_code": "S1",
                "system_name": "Frozen system",
                "design_evaporating_temperature": "-25.0",
                "zones": [
                    {
                        "zone_code": "Z1",
                        "zone_name": "Freezer",
                        "design_cooling_load_kw_r": "120.0",
                        "evaporator_count": 2,
                        "evaporation_temperature_c": "-25.0",
                        "defrost_method": "electric",
                    }
                ],
            }
        ],
        "coefficients": {
            "redundancy_ratio": "1.0",
            "evaporator_capacity_margin": "1.1",
            "condenser_capacity_margin": "1.1",
            "compressor_cop": "2.5",
        },
    }


def _power_inputs() -> dict[str, Any]:
    return {
        "compressor_input_power_kw_e": "120.0",
        "evaporator_fan_power_kw_e": "10.0",
        "condenser_fan_power_kw_e": "8.0",
    }


def _investment_inputs() -> dict[str, Any]:
    return {
        "total_area_m2": 1000.0,
        "refrigerated_area_m2": 800.0,
        "frozen_area_m2": 200.0,
        "position_count": 100,
        "total_power_kw": 150.0,
    }


def _projection(
    calc_type: CalculationType,
    raw_inputs: Mapping[str, Any],
) -> CalculatorInputProjection:
    return projection.project_calculator_input(
        calculation_type=calc_type,
        raw_inputs=dict(raw_inputs),
        actor="test-actor",
        correlation_id="corr-1",
        database_backend="sqlite",
    )


# ── Investment adapter ────────────────────────────────────────────────────


class TestInvestmentAdapter:
    def test_happy_path(self) -> None:
        adapter = adapters.InvestmentAdapter()
        result = adapter.execute(_projection(CalculationType.INVESTMENT, _investment_inputs()))

        assert result.calculation_type is CalculationType.INVESTMENT
        assert result.calculator_name == "investment_estimate"
        assert result.calculator_success is True
        # Demo coefficients are always requires_review=True — the
        # adapter MUST propagate this verbatim.
        assert result.requires_review is True
        assert any(w.code == "DEMO_INVESTMENT_REQUIRES_REVIEW" for w in result.warnings)
        assert result.content_hash == _expected_hash(result.payload)
        # content_hash is the canonical SHA-256 of the payload
        assert len(result.content_hash) == 64

    def test_rejects_invalid_input(self) -> None:
        adapter = adapters.InvestmentAdapter()
        bad = _investment_inputs()
        bad["total_area_m2"] = 0  # non-positive → calculator returns error
        result = adapter.execute(_projection(CalculationType.INVESTMENT, bad))
        assert result.calculator_success is False
        assert any(b.code == "INVALID_ENGINEERING_INPUT" for b in result.blockers)
        # The calculator's ``requires_review=True`` flag must be
        # propagated even when the calculator rejected the input.
        assert result.requires_review is True

    def test_wrong_projection_type_rejected(self) -> None:
        adapter = adapters.InvestmentAdapter()
        # A ZONE projection is not acceptable for an investment adapter.
        with pytest.raises(CalculatorRejectedInputError) as exc:
            adapter.execute(_projection(CalculationType.ZONE, _zone_inputs()))
        assert exc.value.code.value == "CALCULATOR_REJECTED_INPUT"


# ── Zone planning adapter ──────────────────────────────────────────────────


class TestZonePlanningAdapter:
    def test_happy_path(self) -> None:
        adapter = adapters.ZonePlanningAdapter()
        result = adapter.execute(_projection(CalculationType.ZONE, _zone_inputs()))

        assert result.calculation_type is CalculationType.ZONE
        assert result.calculator_name == "cold_room_zone_plan"
        assert result.calculator_success is True
        assert result.requires_review is True  # demo coefficients
        assert result.content_hash == _expected_hash(result.payload)

    def test_rejects_non_positive_input(self) -> None:
        adapter = adapters.ZonePlanningAdapter()
        bad = _zone_inputs()
        bad["daily_inbound_mass_kg"] = 0  # invalid
        result = adapter.execute(_projection(CalculationType.ZONE, bad))
        assert result.calculator_success is False
        assert any(b.code == "INVALID_ENGINEERING_INPUT" for b in result.blockers)
        assert result.requires_review is True

    def test_wrong_projection_type_rejected(self) -> None:
        adapter = adapters.ZonePlanningAdapter()
        with pytest.raises(CalculatorRejectedInputError):
            adapter.execute(_projection(CalculationType.INVESTMENT, _investment_inputs()))


# ── Cooling load adapter ───────────────────────────────────────────────────


class TestCoolingLoadAdapter:
    def test_happy_path(self) -> None:
        adapter = adapters.CoolingLoadAdapter()
        result = adapter.execute(_projection(CalculationType.COOLING_LOAD, _cooling_load_inputs()))
        assert result.calculation_type is CalculationType.COOLING_LOAD
        assert result.calculator_name == "cooling_load"
        assert result.calculator_success is True
        # Cooling load calculator surfaces demo warnings → requires_review=True
        assert result.requires_review is True
        assert result.content_hash == _expected_hash(result.payload)

    def test_rejects_missing_zones(self) -> None:
        adapter = adapters.CoolingLoadAdapter()
        bad = _cooling_load_inputs()
        bad["zones"] = []
        with pytest.raises(CalculatorRejectedInputError):
            adapter.execute(_projection(CalculationType.COOLING_LOAD, bad))

    def test_rejects_missing_coefficients(self) -> None:
        adapter = adapters.CoolingLoadAdapter()
        bad = _cooling_load_inputs()
        bad["coefficients"] = {}
        with pytest.raises(CalculatorRejectedInputError):
            adapter.execute(_projection(CalculationType.COOLING_LOAD, bad))

    def test_wrong_projection_type_rejected(self) -> None:
        adapter = adapters.CoolingLoadAdapter()
        with pytest.raises(CalculatorRejectedInputError):
            adapter.execute(_projection(CalculationType.INVESTMENT, _investment_inputs()))


# ── Equipment capability adapter ──────────────────────────────────────────


class TestEquipmentCapabilityAdapter:
    def test_happy_path(self) -> None:
        adapter = adapters.EquipmentCapabilityAdapter()
        result = adapter.execute(_projection(CalculationType.EQUIPMENT, _equipment_inputs()))
        assert result.calculation_type is CalculationType.EQUIPMENT
        # The equipment calculator's CALCULATOR_NAME is "equipment".
        # The adapter propagates this verbatim.
        assert result.calculator_name == "equipment"
        assert result.calculator_success is True
        # demo coefficients → requires_review=True
        assert result.requires_review is True
        assert result.content_hash == _expected_hash(result.payload)

    def test_rejects_empty_systems(self) -> None:
        adapter = adapters.EquipmentCapabilityAdapter()
        bad = _equipment_inputs()
        bad["systems"] = []
        with pytest.raises(CalculatorRejectedInputError):
            adapter.execute(_projection(CalculationType.EQUIPMENT, bad))

    def test_wrong_projection_type_rejected(self) -> None:
        adapter = adapters.EquipmentCapabilityAdapter()
        with pytest.raises(CalculatorRejectedInputError):
            adapter.execute(_projection(CalculationType.INVESTMENT, _investment_inputs()))


# ── Installed power adapter ───────────────────────────────────────────────


class TestInstalledPowerAdapter:
    def test_happy_path(self) -> None:
        adapter = adapters.InstalledPowerAdapter()
        result = adapter.execute(_projection(CalculationType.POWER, _power_inputs()))
        assert result.calculation_type is CalculationType.POWER
        assert result.calculator_name == "installed_power"
        assert result.calculator_success is True
        # The installed power calculator does not auto-set
        # ``requires_review=True`` (it is determined by the
        # specific warnings and coefficient state).  The adapter
        # MUST propagate whatever the calculator returned.
        assert isinstance(result.requires_review, bool)
        assert result.content_hash == _expected_hash(result.payload)

    def test_wrong_projection_type_rejected(self) -> None:
        adapter = adapters.InstalledPowerAdapter()
        with pytest.raises(CalculatorRejectedInputError):
            adapter.execute(_projection(CalculationType.INVESTMENT, _investment_inputs()))


# ── Requires-review propagation contract ─────────────────────────────────


class TestRequiresReviewPropagation:
    def test_suppression_raises(self) -> None:
        with pytest.raises(UnsupportedReviewRequiredOutputError) as exc:
            assert_requires_review_propagated(
                calculator_requires_review=True,
                adapter_requires_review=False,
                calculation_type="cooling_load",
            )
        assert exc.value.code.value == "CALC_OUTPUT_REVIEW_REQUIRED"

    def test_propagation_passes(self) -> None:
        # No raise.
        assert_requires_review_propagated(
            calculator_requires_review=True,
            adapter_requires_review=True,
            calculation_type="cooling_load",
        )
        assert_requires_review_propagated(
            calculator_requires_review=False,
            adapter_requires_review=False,
            calculation_type="investment",
        )


# ── Adapter result contract ──────────────────────────────────────────────


class TestAdapterResultContract:
    def test_content_hash_mismatch_violates_contract(self) -> None:
        # Build a result, then forge the content_hash to a wrong value.
        adapter = adapters.InvestmentAdapter()
        result = adapter.execute(_projection(CalculationType.INVESTMENT, _investment_inputs()))
        forged = AdapterResult(
            calculation_type=result.calculation_type,
            payload=result.payload,
            content_hash="0" * 64,  # wrong hash
            requires_review=result.requires_review,
            warnings=result.warnings,
            blockers=result.blockers,
            provenance=result.provenance,
            calculator_name=result.calculator_name,
            calculator_version=result.calculator_version,
            calculator_success=result.calculator_success,
        )
        with pytest.raises(AdapterContractViolationError) as exc:
            validate_adapter_result(forged)
        assert exc.value.code.value == "ADAPTER_CONTRACT_VIOLATION"

    def test_empty_payload_violates_contract(self) -> None:
        from cold_storage.modules.orchestration.application.production_calculation.dtos import (
            AdapterProvenance,
        )

        # Build a result that is non-empty (so the calculator would
        # actually compute something) but then forge an empty
        # payload+hash.
        forged = AdapterResult(
            calculation_type=CalculationType.INVESTMENT,
            payload={},
            content_hash=_expected_hash({}),
            requires_review=True,
            warnings=(),
            blockers=(),
            provenance=AdapterProvenance(),
            calculator_name="investment_estimate",
            calculator_version="1.0.0",
            calculator_success=True,
        )
        with pytest.raises(AdapterContractViolationError):
            validate_adapter_result(forged)

    def test_empty_calculator_name_violates_contract(self) -> None:
        adapter = adapters.InvestmentAdapter()
        result = adapter.execute(_projection(CalculationType.INVESTMENT, _investment_inputs()))
        forged = AdapterResult(
            calculation_type=result.calculation_type,
            payload=result.payload,
            content_hash=result.content_hash,
            requires_review=result.requires_review,
            warnings=result.warnings,
            blockers=result.blockers,
            provenance=result.provenance,
            calculator_name="",
            calculator_version=result.calculator_version,
            calculator_success=result.calculator_success,
        )
        with pytest.raises(AdapterContractViolationError):
            validate_adapter_result(forged)

    def test_calculator_success_false_requires_blockers(self) -> None:
        # Manually construct a result with success=False but no blockers.
        adapter = adapters.InvestmentAdapter()
        result = adapter.execute(_projection(CalculationType.INVESTMENT, _investment_inputs()))
        # ``calculator_success=True`` and no blockers is OK.
        assert result.calculator_success is True
        # Now construct success=False with no blockers — must violate.
        forged = AdapterResult(
            calculation_type=result.calculation_type,
            payload=result.payload,
            content_hash=result.content_hash,
            requires_review=result.requires_review,
            warnings=result.warnings,
            blockers=(),  # empty
            provenance=result.provenance,
            calculator_name=result.calculator_name,
            calculator_version=result.calculator_version,
            calculator_success=False,
        )
        with pytest.raises(AdapterContractViolationError):
            validate_adapter_result(forged)


# ── Freeze for hash ──────────────────────────────────────────────────────


class TestFreezeForHash:
    def test_dict_keys_are_sorted(self) -> None:
        out = freeze_for_hash({"b": 2, "a": 1})
        assert list(out.keys()) == ["a", "b"]

    def test_lists_become_tuples(self) -> None:
        out = freeze_for_hash([1, 2, 3])
        assert isinstance(out, tuple)
        assert out == (1, 2, 3)

    def test_nested_mixed(self) -> None:
        out = freeze_for_hash({"a": [{"x": 1, "y": 2}]})
        assert out == {"a": ({"x": 1, "y": 2},)}


# ── Helpers ──────────────────────────────────────────────────────────────


def _expected_hash(payload: Mapping[str, Any]) -> str:
    from cold_storage.modules.orchestration.application.production_calculation.threading import (
        compute_content_hash,
    )

    return compute_content_hash(freeze_for_hash(payload))
