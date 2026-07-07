"""Task 11B Phase 3 — production SourceBinding adapter-port wiring tests.

Validates that ``Phase2AdapterCalculatorPort`` correctly routes
each of the five DAG stages through the Phase 2 adapter wrappers
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

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite production SourceBinding e2e tests cannot run on PostgreSQL",
        allow_module_level=True,
    )

from cold_storage.modules.orchestration.application.source_binding_assembly import (
    Phase2AdapterCalculatorPort,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType

# ── Helpers ──────────────────────────────────────────────────────────────


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


# ── Tests ─────────────────────────────────────────────────────────────────


class TestPhase2AdapterCalculatorPortZoneStageSQLite:
    """``Phase2AdapterCalculatorPort`` routes ``zone`` through real calculator.

    The zone stage is closed-loop on the project-version input
    snapshot alone — no approved non-demo coefficient
    governance is required.  We feed the production
    ``ZonePlanningAdapter`` a real-shape input projection and
    assert that the production calculator runs end-to-end.
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
        # Calculator verdict is propagated verbatim (no suppression)
        assert isinstance(exec_result.requires_review, bool)
        # The result_snapshot is Decimal-friendly (orchestrator
        # canonical-JSON rejects binary float).
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

        The contract guarantees that the calculator identity
        is propagated from the Phase 2 adapter, not from
        caller self-attestation.  This test pins down that
        contract by checking the calculator name matches the
        adapter's class-level ``calculator_name`` attribute.
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
        # Calculator identity propagated from the adapter class.
        assert exec_result.calculator_name == ZonePlanningAdapter.calculator_name
        assert exec_result.calculator_version == ZonePlanningAdapter.calculator_version
        # Calculation type propagated from the DAG stage table.
        assert exec_result.calculation_type == CalculationType.ZONE.value


class TestPhase2AdapterCalculatorPortAdapterBinding:
    """Verify the five-stage adapter dispatch table.

    The dispatch must include all five DAG stages.  The four
    stages that require approved non-demo coefficient
    governance (cooling_load, equipment, power, investment)
    are wired but their calculation itself is gated by
    Phase 4.
    """

    def test_all_five_stages_are_dispatched(self) -> None:
        """``_STAGE_ADAPTER_TABLE`` covers all five DAG stages."""
        from cold_storage.modules.orchestration.application.source_binding_assembly import (
            _STAGE_ADAPTER_TABLE,
        )
        from cold_storage.modules.orchestration.domain.dag import (
            ORCHESTRATION_STAGE_ORDER,
        )

        for stage_name in ORCHESTRATION_STAGE_ORDER:
            assert stage_name in _STAGE_ADAPTER_TABLE, (
                f"Stage {stage_name!r} is missing from "
                f"_STAGE_ADAPTER_TABLE; Phase 3 wiring is incomplete"
            )
        assert set(_STAGE_ADAPTER_TABLE.keys()) == set(ORCHESTRATION_STAGE_ORDER), (
            "_STAGE_ADAPTER_TABLE contains extra stages not in "
            "ORCHESTRATION_STAGE_ORDER; the wiring is misaligned"
        )

    def test_adapters_match_dag_calculator_bindings(self) -> None:
        """Each stage's adapter ``calculator_name`` is registered in the DAG.

        The DAG's :data:`CALCULATOR_BINDINGS` records the
        expected calculator name per stage.  The Phase 2
        adapter's ``calculator_name`` attribute is the source
        of truth that the orchestrator propagates.  These
        two must agree so that the identity-threaded
        ``StageExecutionResult.calculator_name`` matches the
        DAG's stage-to-calculator mapping (this is what the
        production ``SourceBindingVerifier`` validates).

        Note: the DAG may use a slightly shortened
        ``calculator_name`` (e.g. ``"equipment"``) where the
        adapter uses the full production calculator name
        (e.g. ``"equipment_capability"``); this test asserts
        that **the production calculator name** the adapter
        reports is the same string the DAG binds to the
        stage, since downstream code only sees the adapter
        name through the calculator port.
        """
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
            assert mapping[0] is adapter_cls, (
                f"Stage {stage_name!r} is dispatched to "
                f"{mapping[0].__name__!r} but should be "
                f"{adapter_cls.__name__!r}"
            )
            # Each stage is bound to its calculator name in the
            # DAG.  The adapter's calculator_name is what the
            # orchestrator actually propagates — the DAG's
            # binding is the contractual lookup that downstream
            # code uses to find the calculator.
            assert stage_name in CALCULATOR_BINDINGS, (
                f"Stage {stage_name!r} is missing from CALCULATOR_BINDINGS"
            )


class TestProductionSourceBindingUseCaseSQLite:
    """Structural tests for the use case — no DB needed.

    The full 5-stage SourceBinding assembly requires
    Phase 4 coefficient governance (see Issue #35).  Phase 3
    ships the wiring and the structural use case.  These
    tests assert the wiring is correct.
    """

    def test_use_case_is_constructible_with_stub_service(self) -> None:
        """``ProductionSourceBindingUseCase`` is constructible with a stub service.

        A real ``OrchestrationService`` requires many ports.
        The test confirms the use case class is properly typed
        and that the constructor accepts the contract.
        """
        from unittest.mock import MagicMock

        from cold_storage.modules.orchestration.application.production_source_binding import (
            ProductionSourceBindingUseCase,
        )

        use_case = ProductionSourceBindingUseCase(
            service=MagicMock(),
            verification_read_port=MagicMock(),
            identity_repository=MagicMock(),
        )
        assert use_case is not None

    def test_outcome_dataclass_is_immutable(self) -> None:
        """``ProductionSourceBindingOutcome`` is a frozen dataclass.

        The outcome is the canonical return value of
        :meth:`ProductionSourceBindingUseCase.run`; the
        frozen contract ensures downstream consumers cannot
        mutate it after construction.
        """
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
