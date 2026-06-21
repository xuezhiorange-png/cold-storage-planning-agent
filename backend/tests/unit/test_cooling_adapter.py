"""Tests for CoolingLoadEquipmentAdapter — no derivations, no fixed ratios.

Reviewer 4540414919 requires proof that:
1. Adapter does not call any fixed multiplier or fixed operating hours.
2. Adapter maps upstream values 1:1.
3. Missing required fields → fail closed.
4. Missing optional fields → warning, field omitted from output.
5. Output values are deeply equal to upstream result values.
"""

from __future__ import annotations

import types
from typing import Any

import pytest

from cold_storage.modules.planning_agent.domain.errors import PlanningAgentError
from cold_storage.modules.planning_agent.infrastructure.tool_adapters.planning_adapter import (
    CoolingLoadEquipmentAdapter,
)


def _make_orchestration_result(
    *,
    cooling_load_kw_r: float | None = None,
    compressor_capacity_kw_r: float | None = None,
    compressor_input_kw_e: float | None = None,
    condenser_rejection_kw: float | None = None,
    installed_power_kw_e: float | None = None,
) -> Any:
    """Build a fake CoreCalculationOrchestrationResult with realistic .result dicts."""
    result = types.SimpleNamespace()

    if cooling_load_kw_r is not None:
        result.cooling_load = types.SimpleNamespace(
            result={"design_refrigeration_load_kw_r": cooling_load_kw_r}
        )
    else:
        result.cooling_load = None

    if compressor_capacity_kw_r is not None or compressor_input_kw_e is not None:
        eq_result: dict[str, Any] = {}
        if compressor_capacity_kw_r is not None:
            eq_result["total_compressor_capacity_kw_r"] = compressor_capacity_kw_r
        if compressor_input_kw_e is not None:
            eq_result["total_compressor_input_power_kw_e"] = compressor_input_kw_e
        if condenser_rejection_kw is not None:
            eq_result["total_condenser_rejection_kw"] = condenser_rejection_kw
        eq_result["systems"] = [{"name": "sys1"}]
        result.equipment = types.SimpleNamespace(result=eq_result)
    else:
        result.equipment = None

    if installed_power_kw_e is not None:
        result.installed_power = types.SimpleNamespace(
            result={"total_installed_power_kw_e": installed_power_kw_e}
        )
    else:
        result.installed_power = None

    return result


class _FakeCoolingService:
    """Deterministic fake — returns pre-configured orchestration result."""

    def __init__(self, result: Any) -> None:
        self._result = result

    def orchestrate_core_calculation(self, arguments: dict[str, Any]) -> Any:
        return self._result


class TestAdapterNoDerivations:
    """Prove adapter does not apply fixed ratios or fixed hours."""

    def test_output_matches_upstream_1_to_1(self):
        """Output values must equal upstream values exactly."""
        upstream = _make_orchestration_result(
            cooling_load_kw_r=250.0,
            compressor_capacity_kw_r=275.0,
            compressor_input_kw_e=95.0,
        )
        svc = _FakeCoolingService(upstream)
        adapter = CoolingLoadEquipmentAdapter(svc)
        result = adapter.execute({})

        out = result.output["payload"]["result"]
        assert out["total_cooling_load_kw"] == 250.0
        assert out["total_equipment_capacity_kw"] == 275.0
        assert out["total_electrical_input_kw"] == 95.0

    def test_no_condenser_when_upstream_omits(self):
        """When upstream equipment calc has no condenser, output omits it."""
        upstream = _make_orchestration_result(
            cooling_load_kw_r=100.0,
            compressor_capacity_kw_r=110.0,
            compressor_input_kw_e=40.0,
            # No condenser_rejection_kw
        )
        svc = _FakeCoolingService(upstream)
        adapter = CoolingLoadEquipmentAdapter(svc)
        result = adapter.execute({})

        out = result.output["payload"]["result"]
        assert "condenser_heat_rejection_kw" not in out
        assert "condenser_heat_rejection_unit" not in out
        assert any("condenser_heat_rejection" in w for w in result.output["warnings"])

    def test_no_energy_when_upstream_omits(self):
        """When upstream has no installed_power, output omits daily energy."""
        upstream = _make_orchestration_result(
            cooling_load_kw_r=100.0,
            compressor_capacity_kw_r=110.0,
            compressor_input_kw_e=40.0,
            # No installed_power
        )
        svc = _FakeCoolingService(upstream)
        adapter = CoolingLoadEquipmentAdapter(svc)
        result = adapter.execute({})

        out = result.output["payload"]["result"]
        assert "daily_energy_kwh" not in out
        assert "daily_energy_unit" not in out
        assert any("daily_energy" in w for w in result.output["warnings"])

    def test_condenser_included_when_upstream_provides(self):
        """When upstream provides condenser, it appears with kW(th)."""
        upstream = _make_orchestration_result(
            cooling_load_kw_r=100.0,
            compressor_capacity_kw_r=110.0,
            compressor_input_kw_e=40.0,
            condenser_rejection_kw=185.0,
        )
        svc = _FakeCoolingService(upstream)
        adapter = CoolingLoadEquipmentAdapter(svc)
        result = adapter.execute({})

        out = result.output["payload"]["result"]
        assert out["condenser_heat_rejection_kw"] == 185.0
        assert out["condenser_heat_rejection_unit"] == "kW(th)"

    def test_energy_included_when_upstream_provides(self):
        """When upstream provides installed_power, energy appears with kWh."""
        upstream = _make_orchestration_result(
            cooling_load_kw_r=100.0,
            compressor_capacity_kw_r=110.0,
            compressor_input_kw_e=40.0,
            installed_power_kw_e=120.0,
        )
        svc = _FakeCoolingService(upstream)
        adapter = CoolingLoadEquipmentAdapter(svc)
        result = adapter.execute({})

        out = result.output["payload"]["result"]
        assert out["daily_energy_kwh"] == 120.0
        assert out["daily_energy_unit"] == "kWh"

    def test_no_125x_condenser_derivation(self):
        """Condenser must NOT be cooling_load * 1.25."""
        upstream = _make_orchestration_result(
            cooling_load_kw_r=100.0,
            compressor_capacity_kw_r=110.0,
            compressor_input_kw_e=40.0,
            condenser_rejection_kw=999.0,  # Deliberately not 125.0
        )
        svc = _FakeCoolingService(upstream)
        adapter = CoolingLoadEquipmentAdapter(svc)
        result = adapter.execute({})

        out = result.output["payload"]["result"]
        assert out["condenser_heat_rejection_kw"] == 999.0
        assert out["condenser_heat_rejection_kw"] != 100.0 * 1.25

    def test_no_10x_energy_derivation(self):
        """Energy must NOT be electrical_input * 10."""
        upstream = _make_orchestration_result(
            cooling_load_kw_r=100.0,
            compressor_capacity_kw_r=110.0,
            compressor_input_kw_e=40.0,
            installed_power_kw_e=888.0,  # Deliberately not 400.0
        )
        svc = _FakeCoolingService(upstream)
        adapter = CoolingLoadEquipmentAdapter(svc)
        result = adapter.execute({})

        out = result.output["payload"]["result"]
        assert out["daily_energy_kwh"] == 888.0
        assert out["daily_energy_kwh"] != 40.0 * 10.0


class TestAdapterFailClosed:
    """Missing required fields must raise PlanningAgentError."""

    def test_missing_cooling_load_fails(self):
        upstream = _make_orchestration_result(
            compressor_capacity_kw_r=110.0,
            compressor_input_kw_e=40.0,
        )
        svc = _FakeCoolingService(upstream)
        adapter = CoolingLoadEquipmentAdapter(svc)
        with pytest.raises(PlanningAgentError, match="cooling_load"):
            adapter.execute({})

    def test_missing_equipment_capacity_fails(self):
        upstream = _make_orchestration_result(
            cooling_load_kw_r=100.0,
            compressor_input_kw_e=40.0,
        )
        svc = _FakeCoolingService(upstream)
        adapter = CoolingLoadEquipmentAdapter(svc)
        with pytest.raises(PlanningAgentError, match="equipment_capacity"):
            adapter.execute({})

    def test_missing_electrical_input_fails(self):
        upstream = _make_orchestration_result(
            cooling_load_kw_r=100.0,
            compressor_capacity_kw_r=110.0,
        )
        svc = _FakeCoolingService(upstream)
        adapter = CoolingLoadEquipmentAdapter(svc)
        with pytest.raises(PlanningAgentError, match="electrical_input"):
            adapter.execute({})

    def test_all_required_missing_fails(self):
        upstream = types.SimpleNamespace(cooling_load=None, equipment=None, installed_power=None)
        svc = _FakeCoolingService(upstream)
        adapter = CoolingLoadEquipmentAdapter(svc)
        with pytest.raises(PlanningAgentError, match="missing required fields"):
            adapter.execute({})
