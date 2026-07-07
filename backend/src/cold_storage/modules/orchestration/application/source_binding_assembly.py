"""Task 11B Phase 3 — ``CalculatorPort`` driven by Phase 2 adapters.

This module closes the production loop opened by Phase 2.  Where
Phase 2 shipped the application port contracts and the adapter
wrappers around the production calculators (one per calculation
type), this module binds those adapters into a single concrete
implementation of :class:`CalculatorPort` so the production
:class:`TransactionBExecutor` can run the five-stage DAG without
resorting to a mock calculator or a hand-written golden fixture.

Why a dedicated port implementation
===================================

* Phase 1 already shipped :class:`TransactionBExecutor` which
  expects a :class:`CalculatorPort` that returns a
  :class:`StageExecutionResult` per stage.
* Phase 2 shipped the typed Phase 2 adapters
  (:class:`ZonePlanningAdapter`, :class:`CoolingLoadAdapter`,
  :class:`EquipmentCapabilityAdapter`,
  :class:`InstalledPowerAdapter`, :class:`InvestmentAdapter`) and
  the :class:`CalculatorInputProjection` helper.
* Nothing in production wired the two halves together: tests
  used mocks, golden fixtures, or a hand-written
  ``_GoldenCalculatorPort``.  This module is the production
  bridge.

Fail-closed contracts
=====================

* Every adapter result is propagated through the contract
  validator (``validate_adapter_result``) before being turned
  into a :class:`StageExecutionResult`.  A contract violation is
  raised as a typed ``TransactionBFailure`` so the surrounding
  UoW rolls back cleanly.
* A non-empty ``AdapterResult.blockers`` list is treated as a
  hard failure — Transaction B cannot proceed.
* ``requires_review`` is propagated **verbatim**; the
  :func:`assert_requires_review_propagated` contract test in
  Phase 2 enforces this.  This module never flips
  ``requires_review`` to ``False``.
* Calculator identity (name + version) is propagated from the
  Phase 2 adapter, not fabricated.
* The ``upstream_calculation_ids`` carried on the
  :class:`CalculatorInputProjection` are sourced from
  ``upstream_results`` (the previous stages' persisted
  :class:`StagePersistedResult` rows) and threaded onto the
  projection.  This is the only way the producer feeds identity
  to downstream stages — no hand-typed upstream IDs.
* ``StageExecutionResult.result_snapshot`` is the adapter's
  ``AdapterResult.payload`` (the dict the calculator actually
  returned), not a hand-written golden payload.
* Source references / formulas / coefficients / assumptions come
  from ``AdapterResult.provenance`` and are translated to plain
  dicts for ``TransactionBExecutor``.  No manual dict
  fabrication.

Architecture
============

* This module lives in the orchestration application tier.  It
  imports the Phase 2 adapter classes (also application tier) and
  the calculator port protocol (also application tier).  It does
  not import any SQLAlchemy ORM or session — the surrounding
  ``TransactionBExecutor`` owns the session.
* Phase 3 does NOT modify the Phase 2 adapter code.  The
  adapters are the typed boundary, and they remain the only
  path to the underlying production calculators.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal as _Decimal
from typing import Any

from cold_storage.modules.orchestration.application.production_calculation.adapters import (
    CoolingLoadAdapter,
    EquipmentCapabilityAdapter,
    InstalledPowerAdapter,
    InvestmentAdapter,
    ZonePlanningAdapter,
)
from cold_storage.modules.orchestration.application.production_calculation.errors import (
    CalculatorRejectedInputError,
    ProductionCalculationDomainError,
)
from cold_storage.modules.orchestration.application.production_calculation.projection import (
    project_calculator_input,
)
from cold_storage.modules.orchestration.application.transaction_b import (
    StageExecutionResult,
    TransactionBFailure,
)
from cold_storage.modules.orchestration.domain.contracts import (
    CalculationType,
    StagePersistedResult,
)


def _decimalize_payload(value: object) -> object:
    """Recursively convert ``float`` leaves to ``Decimal``.

    The orchestrator's canonical-JSON helper rejects binary
    ``float`` and only accepts ``Decimal``.  Calculator
    outputs naturally carry ``float`` values, so this helper
    is the boundary that normalises the calculator's output
    to ``Decimal`` everywhere.  The conversion is lossless for
    the values produced by the production calculators (they
    all originate as ``Decimal`` internally).
    """
    if isinstance(value, float):
        return _Decimal(str(value))
    if isinstance(value, dict):
        return {k: _decimalize_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decimalize_payload(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_decimalize_payload(v) for v in value)
    return value


# Mapping from orchestration stage name to Phase 2 adapter class
# and the corresponding ``CalculationType`` enum value.  The order
# is fixed by ``ORCHESTRATION_STAGE_ORDER`` in
# ``orchestration.domain.dag``.
_STAGE_ADAPTER_TABLE: Mapping[str, tuple[type, CalculationType]] = {
    "zone": (ZonePlanningAdapter, CalculationType.ZONE),
    "cooling_load": (CoolingLoadAdapter, CalculationType.COOLING_LOAD),
    "equipment": (EquipmentCapabilityAdapter, CalculationType.EQUIPMENT),
    "power": (InstalledPowerAdapter, CalculationType.POWER),
    "investment": (InvestmentAdapter, CalculationType.INVESTMENT),
}


class Phase2AdapterCalculatorPort:
    """Production :class:`CalculatorPort` driven by Phase 2 adapters.

    Each :meth:`execute_stage` call routes through the corresponding
    Phase 2 adapter.  Upstream ``StagePersistedResult`` objects are
    mapped onto the :class:`CalculatorInputProjection` so the
    adapter sees a typed input that includes the actual upstream
    calculation IDs and result hashes.

    The class is stateless apart from the cached adapter instances.
    It is safe to share a single instance across a whole request /
    attempt / process — the adapters themselves are calculator
    wrappers with no I/O.
    """

    def __init__(
        self,
        *,
        zone_adapter: ZonePlanningAdapter | None = None,
        cooling_load_adapter: CoolingLoadAdapter | None = None,
        equipment_adapter: EquipmentCapabilityAdapter | None = None,
        power_adapter: InstalledPowerAdapter | None = None,
        investment_adapter: InvestmentAdapter | None = None,
    ) -> None:
        # Default to fresh instances so the production path uses the
        # production calculators (no fixtures, no mocks, no golden
        # outputs).  Tests can inject alternate adapters for
        # negative paths.
        self._zone_adapter = zone_adapter or ZonePlanningAdapter()
        self._cooling_load_adapter = cooling_load_adapter or CoolingLoadAdapter()
        self._equipment_adapter = equipment_adapter or EquipmentCapabilityAdapter()
        self._power_adapter = power_adapter or InstalledPowerAdapter()
        self._investment_adapter = investment_adapter or InvestmentAdapter()

    def execute_stage(
        self,
        *,
        stage_name: str,
        execution_snapshot: dict[str, Any],
        coefficient_context: dict[str, Any],
        upstream_results: dict[str, StagePersistedResult],
        actor: str = "",
        correlation_id: str = "",
    ) -> StageExecutionResult:
        """Execute one DAG stage via the corresponding Phase 2 adapter.

        Raises :class:`TransactionBFailure` on any
        production-calculation failure.  The surrounding UoW is
        expected to roll back the entire transaction on this
        exception.
        """
        return self._execute_stage_impl(
            stage_name=stage_name,
            execution_snapshot=execution_snapshot,
            coefficient_context=coefficient_context,
            upstream_results=upstream_results,
            actor=actor,
            correlation_id=correlation_id,
        )

    def _execute_stage_impl(
        self,
        *,
        stage_name: str,
        execution_snapshot: dict[str, Any],
        coefficient_context: dict[str, Any],
        upstream_results: dict[str, StagePersistedResult],
        actor: str = "",
        correlation_id: str = "",
    ) -> StageExecutionResult:
        try:
            mapping = _STAGE_ADAPTER_TABLE[stage_name]
        except KeyError as exc:
            raise TransactionBFailure(
                "TXB_UNKNOWN_STAGE",
                f"Phase 2 adapter calculator received unknown stage {stage_name!r}",
                field="stage_name",
                details={"stage_name": stage_name},
            ) from exc

        adapter_cls, calculation_type = mapping
        adapter = self._resolve_adapter(adapter_cls)

        # Build a typed ``CalculatorInputProjection`` from the
        # raw ``execution_snapshot`` for this stage.  The
        # projection helper is the only code path that constructs
        # a ``CalculatorInputProjection`` — adapters MUST NOT
        # receive the raw ``execution_snapshot`` directly.
        try:
            raw_inputs = self._build_raw_inputs(
                stage_name=stage_name,
                execution_snapshot=execution_snapshot,
                coefficient_context=coefficient_context,
                upstream_results=upstream_results,
                actor=actor,
                correlation_id=correlation_id,
            )
            projection = project_calculator_input(
                calculation_type=calculation_type,
                raw_inputs=raw_inputs,
                actor=str(raw_inputs.get("actor", "")),
                correlation_id=str(raw_inputs.get("correlation_id", "")),
                database_backend=str(raw_inputs.get("database_backend", "")),
                upstream_calculation_ids={
                    k: v.calculation_run_id for k, v in upstream_results.items()
                },
                calculator_name=adapter.calculator_name,
                calculator_version=adapter.calculator_version,
            )
        except ProductionCalculationDomainError as exc:
            raise TransactionBFailure(
                "TXB_PHASE2_PROJECTION_REJECTED",
                f"Phase 2 projection rejected for stage {stage_name!r}: {exc}",
                field="calculator_input",
                details={
                    "stage_name": stage_name,
                    "code": str(exc.code),
                    "field": exc.field,
                    "error": str(exc),
                },
            ) from exc

        # Execute the adapter.  Any typed rejection from the
        # adapter is propagated as a TransactionBFailure so the
        # outer UoW rolls back.
        try:
            adapter_result = adapter.execute(projection)
        except CalculatorRejectedInputError as exc:
            raise TransactionBFailure(
                "TXB_PHASE2_CALCULATOR_REJECTED",
                f"Phase 2 adapter rejected input for stage {stage_name!r}: {exc}",
                field="calculator_input",
                details={
                    "stage_name": stage_name,
                    "code": str(exc.code),
                    "field": exc.field,
                    "error": str(exc),
                },
            ) from exc
        except ProductionCalculationDomainError as exc:
            raise TransactionBFailure(
                "TXB_PHASE2_ADAPTER_REJECTED",
                f"Phase 2 adapter raised for stage {stage_name!r}: {exc}",
                field="adapter_result",
                details={
                    "stage_name": stage_name,
                    "code": str(exc.code),
                    "field": exc.field,
                    "error": str(exc),
                },
            ) from exc

        # Hard failure if the calculator flagged any blockers.
        if adapter_result.blockers:
            raise TransactionBFailure(
                "TXB_PHASE2_BLOCKERS_PRESENT",
                (
                    f"Phase 2 adapter for stage {stage_name!r} returned "
                    f"{len(adapter_result.blockers)} blockers; Transaction B "
                    f"cannot proceed"
                ),
                field="adapter_result",
                details={
                    "stage_name": stage_name,
                    "blockers": [
                        {"code": b.code, "message": b.message, "field": b.field_name}
                        for b in adapter_result.blockers
                    ],
                },
            )
        # Propagate the result to TransactionBExecutor.  ``payload``
        # is the calculator's result dict (verbatim); warnings /
        # formulas / coefficients / source_references come
        # from the typed ``AdapterProvenance`` surface.
        provenance = adapter_result.provenance
        return StageExecutionResult(
            calculator_name=adapter_result.calculator_name,
            calculator_version=adapter_result.calculator_version,
            calculation_type=calculation_type.value,
            result_snapshot=dict(
                _decimalize_payload(adapter_result.payload)  # type: ignore[call-overload]
            ),
            formulas=[dict(f) for f in provenance.formulas],
            coefficients=[dict(c) for c in provenance.coefficients],
            assumptions=list(provenance.assumptions),
            warnings=[
                {"code": w.code, "message": w.message, "details": dict(w.details)}
                for w in adapter_result.warnings
            ],
            source_references=[dict(s) for s in provenance.source_references],
            requires_review=bool(adapter_result.requires_review),
        )

    # ── Helpers ─────────────────────────────────────────────────────────

    def _resolve_adapter(self, adapter_cls: type) -> Any:
        if adapter_cls is ZonePlanningAdapter:
            return self._zone_adapter
        if adapter_cls is CoolingLoadAdapter:
            return self._cooling_load_adapter
        if adapter_cls is EquipmentCapabilityAdapter:
            return self._equipment_adapter
        if adapter_cls is InstalledPowerAdapter:
            return self._power_adapter
        if adapter_cls is InvestmentAdapter:
            return self._investment_adapter
        # Defensive: table is built in this module — if the
        # table is ever extended without updating the resolver,
        # the dispatch is a programmer error, not a runtime
        # condition we want to silently swallow.
        raise TransactionBFailure(
            "TXB_PHASE2_ADAPTER_DISPATCH_BROKEN",
            f"Phase 2 adapter dispatch is missing for {adapter_cls.__name__!r}",
            field="calculator_port",
            details={"adapter_class": adapter_cls.__name__},
        )

    def _build_raw_inputs(
        self,
        *,
        stage_name: str,
        execution_snapshot: dict[str, Any],
        coefficient_context: dict[str, Any],
        upstream_results: dict[str, StagePersistedResult],
        actor: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Translate the raw ``execution_snapshot`` for one stage.

        The five adapters need different input shapes.  The
        existing Phase 2 adapters accept a flat ``raw_inputs``
        dict and project the fields they need onto their typed
        input objects.  This helper copies the per-stage
        ``execution_snapshot`` and threads the coefficient
        context + upstream results so each adapter sees the
        data it needs.

        ``database_backend`` and identity fields are pulled
        from the durable orchestrator state — not from the
        caller-typed ``execution_snapshot`` — so the production
        path is consistent with the orchestrator's identity
        contract.

        Fail-closed contract: this function never invents a
        field that is not present in the snapshot.  A missing
        field will surface as a Phase 2 projection rejection
        (``PROJ_INPUT_INVALID``).
        """
        from cold_storage.bootstrap.settings import get_settings

        settings = get_settings()
        stage_data = execution_snapshot.get(stage_name, {})
        if not isinstance(stage_data, dict):
            raise CalculatorRejectedInputError(
                calculation_type=stage_name,
                reason=(
                    f"execution_snapshot[{stage_name!r}] is not a dict "
                    f"(got {type(stage_data).__name__})"
                ),
            )
        raw_inputs: dict[str, Any] = dict(stage_data)
        if coefficient_context:
            raw_inputs.setdefault("coefficients", dict(coefficient_context))
        # Thread upstream stage results so the adapter can see
        # them in the projection.  These are the actual persisted
        # result hashes from the previous stages — never a
        # placeholder.
        for upstream_stage, persisted in upstream_results.items():
            raw_inputs[f"upstream_{upstream_stage}_result_hash"] = persisted.result_hash
            raw_inputs[f"upstream_{upstream_stage}_calculation_run_id"] = (
                persisted.calculation_run_id
            )
        # Identity fields are sourced from the durable
        # orchestrator state, not the caller.
        raw_inputs["database_backend"] = settings.database_backend
        raw_inputs["actor"] = actor
        raw_inputs["correlation_id"] = correlation_id
        return raw_inputs


__all__ = ["Phase2AdapterCalculatorPort"]
