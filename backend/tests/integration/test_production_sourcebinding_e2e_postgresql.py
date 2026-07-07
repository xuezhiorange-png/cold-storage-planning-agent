"""Task 11B Phase 3 — production SourceBinding adapter-port wiring tests (PG).

PostgreSQL mirror of
``test_production_sourcebinding_e2e_sqlite.py``.  Validates
that ``Phase2AdapterCalculatorPort`` correctly routes each
of the five DAG stages through the Phase 2 adapter wrappers
(no mocks, no golden fixtures).

The full five-stage end-to-end production run is gated by
the Phase 4 "approved non-demo coefficient governance" task
(Issue #35 acceptance criteria): the ``cooling_load``,
``equipment``, ``power``, and ``investment`` stages each
require production-approved engineering coefficients that
Phase 3 does not yet provide.  The ``zone`` stage, by
contrast, is closed-loop on the project-version input
snapshot alone — no external coefficient governance needed.

So Phase 3 unit-tests ``zone`` end-to-end via the real
production calculator, and contract-tests the remaining
stages so the wiring is verified even though the calculation
itself is gated by Phase 4.
"""

from __future__ import annotations

import dataclasses
import os
from decimal import Decimal

import pytest

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "PostgreSQL production SourceBinding e2e tests only run on PostgreSQL",
        allow_module_level=True,
    )

from cold_storage.modules.orchestration.application.source_binding_assembly import (
    Phase2AdapterCalculatorPort,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType


def _all_decimal(value: object) -> bool:
    """Recursive check: every leaf is ``Decimal``, never binary ``float``."""
    if isinstance(value, float):
        return False
    if isinstance(value, dict):
        return all(_all_decimal(v) for v in value.values())
    if isinstance(value, list):
        return all(_all_decimal(v) for v in value)
    if isinstance(value, tuple):
        return all(_all_decimal(v) for v in value)
    return True


class TestPhase2AdapterCalculatorPortZoneStagePostgreSQL:
    """``Phase2AdapterCalculatorPort`` routes ``zone`` through real calculator (PG).

    PostgreSQL mirror of the SQLite test.  The class under
    test (``Phase2AdapterCalculatorPort``) is database-free,
    so the test is identical apart from the skip marker.
    """

    def test_zone_runs_through_production_calculator(self) -> None:
        """Zone stage: production calculator runs and returns a real snapshot."""
        port = Phase2AdapterCalculatorPort()
        exec_result = port.execute_stage(
            stage_name="zone",
            execution_snapshot={
                "zone": {
                    "daily_inbound_mass_kg": Decimal("20000"),
                    "working_time_h_per_day": Decimal("16"),
                    "finished_storage_days": Decimal("7"),
                    "packaging_storage_days": Decimal("1"),
                    "precooling_required_ratio": Decimal("0.6"),
                },
            },
            coefficient_context={},
            upstream_results={},
            actor="phase3-prod-actor",
            correlation_id="phase3-prod-correlation-001",
        )
        assert exec_result.calculator_name == "cold_room_zone_plan"
        assert exec_result.calculation_type == "zone"
        assert exec_result.result_snapshot, (
            "Phase 2 adapter produced an empty result_snapshot — "
            "the production calculator did not actually run"
        )
        assert isinstance(exec_result.requires_review, bool)
        assert _all_decimal(exec_result.result_snapshot), (
            "Phase 2 adapter result_snapshot still contains "
            "binary float values; the orchestrator's "
            "canonical-JSON helper would raise"
        )

    def test_unknown_stage_is_fail_closed(self) -> None:
        """Unknown stage name raises ``TransactionBFailure(TXB_UNKNOWN_STAGE)``."""
        from cold_storage.modules.orchestration.application.transaction_b import (
            TransactionBFailure,
        )

        port = Phase2AdapterCalculatorPort()
        with pytest.raises(TransactionBFailure) as exc_info:
            port.execute_stage(
                stage_name="non_existent_stage",
                execution_snapshot={},
                coefficient_context={},
                upstream_results={},
            )
        assert exc_info.value.code == "TXB_UNKNOWN_STAGE"

    def test_propagation_uses_production_adapter_metadata(self) -> None:
        """Calculator name and version are sourced from the adapter, not caller.

        PostgreSQL mirror — same contract as the SQLite test.
        """
        from cold_storage.modules.orchestration.application.production_calculation.adapters import (
            ZonePlanningAdapter,
        )

        port = Phase2AdapterCalculatorPort()
        exec_result = port.execute_stage(
            stage_name="zone",
            execution_snapshot={
                "zone": {
                    "daily_inbound_mass_kg": Decimal("20000"),
                    "working_time_h_per_day": Decimal("16"),
                    "finished_storage_days": Decimal("7"),
                    "packaging_storage_days": Decimal("1"),
                    "precooling_required_ratio": Decimal("0.6"),
                },
            },
            coefficient_context={},
            upstream_results={},
            actor="phase3-prod-actor",
            correlation_id="phase3-prod-correlation-001",
        )
        assert exec_result.calculator_name == ZonePlanningAdapter.calculator_name
        assert exec_result.calculator_version == ZonePlanningAdapter.calculator_version
        assert exec_result.calculation_type == CalculationType.ZONE.value


class TestPhase2AdapterCalculatorPortAdapterBindingPostgreSQL:
    """PG mirror of the adapter binding test."""

    def test_all_five_stages_are_dispatched(self) -> None:
        """``_STAGE_ADAPTER_TABLE`` covers all five DAG stages."""
        from cold_storage.modules.orchestration.application.source_binding_assembly import (
            _STAGE_ADAPTER_TABLE,
        )
        from cold_storage.modules.orchestration.domain.dag import (
            ORCHESTRATION_STAGE_ORDER,
        )

        for stage_name in ORCHESTRATION_STAGE_ORDER:
            assert stage_name in _STAGE_ADAPTER_TABLE
        assert set(_STAGE_ADAPTER_TABLE.keys()) == set(ORCHESTRATION_STAGE_ORDER)

    def test_adapters_match_dag_calculator_bindings(self) -> None:
        """Each stage is dispatched to the right Phase 2 adapter class."""
        from cold_storage.modules.orchestration.application.production_calculation.adapters import (
            CoolingLoadAdapter,
            EquipmentCapabilityAdapter,
            InstalledPowerAdapter,
            InvestmentAdapter,
            ZonePlanningAdapter,
        )
        from cold_storage.modules.orchestration.application.source_binding_assembly import (
            _STAGE_ADAPTER_TABLE,
        )
        from cold_storage.modules.orchestration.domain.dag import (
            CALCULATOR_BINDINGS,
        )

        stage_to_adapter_cls = {
            "zone": ZonePlanningAdapter,
            "cooling_load": CoolingLoadAdapter,
            "equipment": EquipmentCapabilityAdapter,
            "power": InstalledPowerAdapter,
            "investment": InvestmentAdapter,
        }
        for stage_name, adapter_cls in stage_to_adapter_cls.items():
            mapping = _STAGE_ADAPTER_TABLE[stage_name]
            assert mapping[0] is adapter_cls
            assert stage_name in CALCULATOR_BINDINGS


class TestProductionSourceBindingUseCasePostgreSQL:
    """PG mirror of the use-case structural tests."""

    def test_use_case_is_constructible_with_stub_service(self) -> None:
        """``ProductionSourceBindingUseCase`` is constructible with a stub service."""
        from unittest.mock import MagicMock

        from cold_storage.modules.orchestration.application.production_source_binding import (
            ProductionSourceBindingUseCase,
        )

        use_case = ProductionSourceBindingUseCase(
            service=MagicMock(),
            verification_read_port=MagicMock(),
        )
        assert use_case is not None

    def test_outcome_dataclass_is_immutable(self) -> None:
        """``ProductionSourceBindingOutcome`` is a frozen dataclass."""
        from cold_storage.modules.orchestration.application.production_source_binding import (
            ProductionSourceBindingOutcome,
        )

        outcome = ProductionSourceBindingOutcome(
            request_id="r",
            identity_id="i",
            attempt_id="a",
            source_binding_id="b",
            requires_review=False,
        )
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):  # type: ignore[arg-type]
            outcome.source_binding_id = "tampered"  # type: ignore[misc]
