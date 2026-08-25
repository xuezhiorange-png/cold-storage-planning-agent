"""Unit tests for LineageAwareCalculatorPort fail-closed lineage (V0.5 P1 R2/R3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from cold_storage.modules.orchestration.application.transaction_b import (
    StageExecutionResult,
    TransactionBFailure,
)
from cold_storage.modules.projects.application.engineering_input_bundle import (
    coefficient_context_from_bundle,
    project_execution_snapshot_from_bundle,
)
from cold_storage.modules.projects.application.five_stage_execution import (
    LineageAwareCalculatorPort,
)
from tests.integration.v05_p1_bundle_fixtures import build_valid_engineering_input_bundle


def _default_cooling_snapshot() -> dict[str, Any]:
    return {
        "total_cooling_load_kw": "999.0",
        "zones": [{"zone_code": "Z1", "subtotal_load_kw_r": "42.5"}],
    }


@dataclass
class _FakeInnerPort:
    cooling_result_snapshot: dict[str, Any] = field(default_factory=_default_cooling_snapshot)
    last_equipment_snapshot: dict[str, Any] | None = None

    def execute_stage(
        self,
        *,
        stage_name: str,
        execution_snapshot: dict[str, Any],
        coefficient_context: dict[str, Any],
        upstream_results: dict[str, Any],
        actor: str = "",
        correlation_id: str = "",
    ) -> StageExecutionResult:
        if stage_name == "cooling_load":
            return StageExecutionResult(
                calculator_name="cooling_load",
                calculator_version="1.0.0",
                calculation_type="cooling_load",
                result_snapshot=dict(self.cooling_result_snapshot),
                formulas=[],
                coefficients=[],
                assumptions=[],
                warnings=[],
                source_references=[],
                requires_review=True,
            )
        if stage_name == "equipment":
            self.last_equipment_snapshot = dict(execution_snapshot.get("equipment", {}))
            return StageExecutionResult(
                calculator_name="equipment",
                calculator_version="1.0.0",
                calculation_type="equipment",
                result_snapshot={"evaporator_total_cooling_capacity_kw": "1"},
                formulas=[],
                coefficients=[],
                assumptions=[],
                warnings=[],
                source_references=[],
                requires_review=True,
            )
        if stage_name == "zone":
            return StageExecutionResult(
                calculator_name="cold_room_zone_plan",
                calculator_version="1.0.0",
                calculation_type="zone",
                result_snapshot={
                    "total_area_m2": "5000.0",
                    "zones": [{"position_count": 40}, {"position_count": 60}],
                },
                formulas=[],
                coefficients=[],
                assumptions=[],
                warnings=[],
                source_references=[],
                requires_review=True,
            )
        if stage_name == "power":
            return StageExecutionResult(
                calculator_name="installed_power",
                calculator_version="1.0.0",
                calculation_type="power",
                result_snapshot={"total_installed_power_kw_e": "250.0"},
                formulas=[],
                coefficients=[],
                assumptions=[],
                warnings=[],
                source_references=[],
                requires_review=True,
            )
        if stage_name == "investment":
            self.last_equipment_snapshot = dict(execution_snapshot.get("investment", {}))
            return StageExecutionResult(
                calculator_name="investment_estimate",
                calculator_version="1.0.0",
                calculation_type="investment",
                result_snapshot={"total_investment_cny": "1"},
                formulas=[],
                coefficients=[],
                assumptions=[],
                warnings=[],
                source_references=[],
                requires_review=True,
            )
        raise AssertionError(f"unexpected stage {stage_name}")


def _build_port(
    *,
    equipment_lineage_confirmed: bool = False,
    investment_lineage_confirmed: bool = True,
    cooling_result_snapshot: dict[str, Any] | None = None,
) -> tuple[LineageAwareCalculatorPort, _FakeInnerPort, dict[str, Any]]:
    bundle = build_valid_engineering_input_bundle(
        project_id="p-1",
        project_version_id="pv-1",
        version_number=1,
    )
    provenance = dict(bundle["source_metadata"]["input_group_provenance"])
    provenance["equipment_inputs"] = (
        "persisted_upstream_confirmed" if equipment_lineage_confirmed else "user_entry"
    )
    provenance["investment_inputs"] = (
        "persisted_upstream_confirmed" if investment_lineage_confirmed else "user_entry"
    )
    execution_snapshot = project_execution_snapshot_from_bundle(bundle)
    coefficient_context = coefficient_context_from_bundle(bundle)
    inner = _FakeInnerPort(
        cooling_result_snapshot=cooling_result_snapshot or _default_cooling_snapshot()
    )
    port = LineageAwareCalculatorPort(
        inner=inner,  # type: ignore[arg-type]
        execution_snapshot=execution_snapshot,
        input_group_provenance=provenance,
    )
    return port, inner, coefficient_context


def test_equipment_does_not_overwrite_without_lineage_confirmation() -> None:
    port, inner, coefficient_context = _build_port(equipment_lineage_confirmed=False)
    port.execute_stage(
        stage_name="cooling_load",
        execution_snapshot=dict(port._execution_snapshot),
        coefficient_context=coefficient_context,
        upstream_results={},
    )
    port.execute_stage(
        stage_name="equipment",
        execution_snapshot=dict(port._execution_snapshot),
        coefficient_context=coefficient_context,
        upstream_results={},
    )
    assert inner.last_equipment_snapshot is not None
    zone = inner.last_equipment_snapshot["systems"][0]["zones"][0]
    assert str(zone["design_cooling_load_kw_r"]) in {"120", "120.0"}


def test_equipment_binds_per_zone_cooling_load_when_lineage_confirmed() -> None:
    port, inner, coefficient_context = _build_port(equipment_lineage_confirmed=True)
    port.execute_stage(
        stage_name="cooling_load",
        execution_snapshot=dict(port._execution_snapshot),
        coefficient_context=coefficient_context,
        upstream_results={},
    )
    port.execute_stage(
        stage_name="equipment",
        execution_snapshot=dict(port._execution_snapshot),
        coefficient_context=coefficient_context,
        upstream_results={},
    )
    assert inner.last_equipment_snapshot is not None
    zone = inner.last_equipment_snapshot["systems"][0]["zones"][0]
    assert str(zone["design_cooling_load_kw_r"]) in {"42.5", "42.500"}


def test_equipment_lineage_bind_fails_closed_when_zones_missing_from_snapshot() -> None:
    port, _, coefficient_context = _build_port(
        equipment_lineage_confirmed=True,
        cooling_result_snapshot={"total_cooling_load_kw": "999.0"},
    )
    port.execute_stage(
        stage_name="cooling_load",
        execution_snapshot=dict(port._execution_snapshot),
        coefficient_context=coefficient_context,
        upstream_results={},
    )
    with pytest.raises(TransactionBFailure) as exc_info:
        port.execute_stage(
            stage_name="equipment",
            execution_snapshot=dict(port._execution_snapshot),
            coefficient_context=coefficient_context,
            upstream_results={},
        )
    assert exc_info.value.code == "UPSTREAM_LINEAGE_BIND_FAILED"


def test_equipment_lineage_bind_fails_closed_on_zone_code_mismatch() -> None:
    port, _, coefficient_context = _build_port(equipment_lineage_confirmed=True)
    port._execution_snapshot["equipment"]["systems"][0]["zones"][0]["zone_code"] = "UNKNOWN"
    port.execute_stage(
        stage_name="cooling_load",
        execution_snapshot=dict(port._execution_snapshot),
        coefficient_context=coefficient_context,
        upstream_results={},
    )
    with pytest.raises(TransactionBFailure) as exc_info:
        port.execute_stage(
            stage_name="equipment",
            execution_snapshot=dict(port._execution_snapshot),
            coefficient_context=coefficient_context,
            upstream_results={},
        )
    assert exc_info.value.code == "UPSTREAM_LINEAGE_BIND_FAILED"


def test_investment_binds_only_explicit_upstream_fields() -> None:
    port, inner, coefficient_context = _build_port(
        equipment_lineage_confirmed=False,
        investment_lineage_confirmed=True,
    )
    for stage_name in ("zone", "power"):
        port.execute_stage(
            stage_name=stage_name,
            execution_snapshot=dict(port._execution_snapshot),
            coefficient_context=coefficient_context,
            upstream_results={},
        )
    port.execute_stage(
        stage_name="investment",
        execution_snapshot=dict(port._execution_snapshot),
        coefficient_context=coefficient_context,
        upstream_results={},
    )
    assert inner.last_equipment_snapshot is not None
    investment = inner.last_equipment_snapshot
    assert str(investment["total_area_m2"]) == "5000.0"
    assert investment["position_count"] == 100
    assert str(investment["total_power_kw"]) == "250.0"
    assert str(investment["refrigerated_area_m2"]) in {"800", "800.0"}
    assert str(investment["frozen_area_m2"]) in {"200", "200.0"}


def test_power_stage_asserts_canonical_calculator_identity() -> None:
    port, _, coefficient_context = _build_port()
    inner = MagicMock()
    inner.execute_stage.return_value = StageExecutionResult(
        calculator_name="power_configuration",
        calculator_version="1.0.0",
        calculation_type="power",
        result_snapshot={},
        formulas=[],
        coefficients=[],
        assumptions=[],
        warnings=[],
        source_references=[],
        requires_review=True,
    )
    bad_port = LineageAwareCalculatorPort(
        inner=inner,
        execution_snapshot=port._execution_snapshot,
        input_group_provenance={},
    )
    with pytest.raises(TransactionBFailure) as exc_info:
        bad_port.execute_stage(
            stage_name="power",
            execution_snapshot=dict(port._execution_snapshot),
            coefficient_context=coefficient_context,
            upstream_results={},
        )
    assert exc_info.value.code == "INVALID_CANONICAL_POWER_SLOT"
