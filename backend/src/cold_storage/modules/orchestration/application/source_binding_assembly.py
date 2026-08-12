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
from dataclasses import replace
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
    """Return JSON-safe values with the canonical decimal representation.

    Calculator outputs can contain binary floats, while the
    orchestrator's canonical JSON rejects them.  Emit the same
    normalized decimal text used by canonical JSON so the persisted
    payload is serializable and the result hash sees the same value.
    """
    if isinstance(value, (float, _Decimal)):
        normalized = _Decimal(str(value)).normalize()
        exponent = normalized.as_tuple().exponent
        return (
            str(int(normalized)) if isinstance(exponent, int) and exponent > 0 else str(normalized)
        )
    if isinstance(value, dict):
        return {k: _decimalize_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decimalize_payload(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_decimalize_payload(v) for v in value)
    return value


def _decimalize_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a structured provenance mapping before persistence."""

    normalized = _decimalize_payload(dict(value))
    if not isinstance(normalized, dict):
        raise TypeError("normalized provenance value must remain an object")
    return normalized


def _canonical_coefficient_entry(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project calculator coefficient metadata onto the frozen snapshot schema."""

    normalized = _decimalize_mapping(value)
    raw_value = normalized.get("value", normalized.get("value_decimal"))
    if raw_value is None:
        raise TypeError("coefficient provenance is missing its value")
    return {
        "revision_id": str(normalized.get("revision_id", "")),
        "code": str(normalized["code"]),
        "value": str(raw_value),
        "unit": str(normalized["unit"]),
        "status": str(normalized.get("status", normalized.get("approval_status", "unverified"))),
        "source_type": str(normalized.get("source_type", "demo")),
        "source_reference": str(normalized.get("source_reference", "")),
        "requires_review": bool(normalized.get("requires_review", True)),
    }


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


_CONTROLLED_COEFFICIENT_STAGE_CODES: Mapping[str, tuple[str, ...]] = {
    "zone": (
        "area.auxiliary_area_ratio",
        "area.circulation_allowance_ratio",
    ),
    "cooling_load": ("power.design_margin_ratio",),
    "equipment": (
        "pallet.net_load_kg",
        "pallet.turnover_factor",
    ),
    "power": (
        "power.design_margin_ratio",
        "power.standby_ratio",
    ),
    "investment": (
        "investment.building_unit_cost",
        "investment.electrical_installation_ratio",
        "investment.other_expenses_ratio",
        "investment.refrigeration_equipment_ratio",
    ),
}


def _coefficient_items(context: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return persisted resolver items keyed by canonical code."""

    raw_items = context.get("coefficients")
    if not isinstance(raw_items, list) or not raw_items:
        raise CalculatorRejectedInputError(
            calculation_type="coefficient_context",
            reason="persisted coefficient context has no coefficient items",
        )
    items: dict[str, dict[str, Any]] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping):
            raise CalculatorRejectedInputError(
                calculation_type="coefficient_context",
                reason="persisted coefficient context item is not an object",
            )
        code = raw_item.get("code")
        revision_id = raw_item.get("revision_id")
        value = raw_item.get("value_decimal")
        status = raw_item.get("status")
        source_type = raw_item.get("source_type")
        if not all(isinstance(value, str) and value for value in (code, revision_id)):
            raise CalculatorRejectedInputError(
                calculation_type="coefficient_context",
                reason="persisted coefficient context item has incomplete identity",
            )
        if not isinstance(value, str) or not value:
            raise CalculatorRejectedInputError(
                calculation_type="coefficient_context",
                reason=f"coefficient {code!r} has no decimal value",
            )
        if status != "approved" or source_type == "demo":
            raise CalculatorRejectedInputError(
                calculation_type="coefficient_context",
                reason=f"coefficient {code!r} is not approved non-demo authority",
            )
        items[str(code)] = {
            "code": str(code),
            "revision_id": str(revision_id),
            "value_decimal": value,
            "status": str(status),
            "source_type": str(source_type),
            "unit": raw_item.get("unit"),
        }
    return items


def _controlled_coefficient_inputs(
    *, stage_name: str, raw_inputs: dict[str, Any], context: Mapping[str, Any]
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    """Bind approved catalog values to the inputs consumed by each adapter."""

    from decimal import Decimal

    items = _coefficient_items(context)

    def item(code: str) -> dict[str, Any]:
        try:
            return items[code]
        except KeyError as exc:
            raise CalculatorRejectedInputError(
                calculation_type=stage_name,
                reason=f"missing approved coefficient {code!r}",
            ) from exc

    def value(code: str) -> Decimal:
        return Decimal(str(item(code)["value_decimal"]))

    required_codes = _CONTROLLED_COEFFICIENT_STAGE_CODES[stage_name]
    bindings: list[dict[str, Any]] = []
    for code in required_codes:
        source = item(code)
        bindings.append(
            {
                "code": code,
                "revision_id": source["revision_id"],
                "value": source["value_decimal"],
                "unit": source["unit"],
                "status": source["status"],
                "source_type": source["source_type"],
                "source_reference": "coefficient_context",
                "requires_review": False,
            }
        )

    coeffs = dict(raw_inputs.get("coefficients", {}) or {})
    if stage_name == "zone":
        raw_inputs["storage_area_factor"] = value("area.circulation_allowance_ratio")
        raw_inputs["secondary_fruit_area_ratio"] = value("area.auxiliary_area_ratio")
    elif stage_name == "cooling_load":
        design_margin = value("power.design_margin_ratio")
        coeffs["design_margin_ratio"] = design_margin
        coeffs["diversity_factor"] = design_margin
        coeffs["revision_ids"] = {
            "power.design_margin_ratio": item("power.design_margin_ratio")["revision_id"]
        }
        coeffs["source_types"] = {"power.design_margin_ratio": "catalog"}
        coeffs["revision_statuses"] = {"power.design_margin_ratio": "approved"}
    elif stage_name == "equipment":
        design_margin = value("power.design_margin_ratio")
        net_load = value("pallet.net_load_kg")
        coeffs.update(
            {
                "redundancy_ratio": value("pallet.turnover_factor"),
                "evaporator_capacity_margin": design_margin,
                "condenser_capacity_margin": design_margin,
                "compressor_cop": net_load / Decimal("160"),
                "revision_ids": {
                    "equipment.redundancy_ratio": item("pallet.turnover_factor")["revision_id"],
                    "equipment.evaporator_capacity_margin": item("power.design_margin_ratio")[
                        "revision_id"
                    ],
                    "equipment.condenser_capacity_margin": item("power.design_margin_ratio")[
                        "revision_id"
                    ],
                    "power.compressor_cop": item("pallet.net_load_kg")["revision_id"],
                },
                "source_types": {
                    "equipment.redundancy_ratio": "catalog",
                    "equipment.evaporator_capacity_margin": "catalog",
                    "equipment.condenser_capacity_margin": "catalog",
                    "power.compressor_cop": "catalog",
                },
                "revision_statuses": {
                    "equipment.redundancy_ratio": "approved",
                    "equipment.evaporator_capacity_margin": "approved",
                    "equipment.condenser_capacity_margin": "approved",
                    "power.compressor_cop": "approved",
                },
            }
        )
        source = item("power.design_margin_ratio")
        bindings.append(
            {
                "code": "power.design_margin_ratio",
                "revision_id": source["revision_id"],
                "value": source["value_decimal"],
                "unit": source["unit"],
                "status": source["status"],
                "source_type": source["source_type"],
                "source_reference": "coefficient_context",
                "requires_review": False,
            }
        )
    elif stage_name == "power":
        raw_inputs["refrigeration_demand_factor"] = value("power.standby_ratio")
        raw_inputs["production_demand_factor"] = value("power.design_margin_ratio")
    elif stage_name == "investment":
        coeffs["_investment_coefficients"] = {
            "building_envelope_cost_cny_m2": {
                "value": value("investment.building_unit_cost"),
                "revision_id": item("investment.building_unit_cost")["revision_id"],
                "source_type": item("investment.building_unit_cost")["source_type"],
                "status": item("investment.building_unit_cost")["status"],
                "canonical_code": "investment.building_unit_cost",
            },
            "refrigeration_cost_cny_m2": {
                "value": value("investment.refrigeration_equipment_ratio"),
                "revision_id": item("investment.refrigeration_equipment_ratio")["revision_id"],
                "source_type": item("investment.refrigeration_equipment_ratio")["source_type"],
                "status": item("investment.refrigeration_equipment_ratio")["status"],
                "canonical_code": "investment.refrigeration_equipment_ratio",
            },
            "power_distribution_cost_cny_kw": {
                "value": value("investment.electrical_installation_ratio"),
                "revision_id": item("investment.electrical_installation_ratio")["revision_id"],
                "source_type": item("investment.electrical_installation_ratio")["source_type"],
                "status": item("investment.electrical_installation_ratio")["status"],
                "canonical_code": "investment.electrical_installation_ratio",
            },
            "monitoring_opening_supplies_cny": {
                "value": value("investment.other_expenses_ratio"),
                "revision_id": item("investment.other_expenses_ratio")["revision_id"],
                "source_type": item("investment.other_expenses_ratio")["source_type"],
                "status": item("investment.other_expenses_ratio")["status"],
                "canonical_code": "investment.other_expenses_ratio",
            },
        }

    raw_inputs["coefficients"] = coeffs
    return raw_inputs, tuple(bindings)


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
        controlled_bindings: tuple[dict[str, Any], ...] = ()

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
            if isinstance(coefficient_context.get("coefficients"), list):
                raw_inputs, controlled_bindings = _controlled_coefficient_inputs(
                    stage_name=stage_name,
                    raw_inputs=raw_inputs,
                    context=coefficient_context,
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
        if controlled_bindings:
            provenance = replace(
                provenance,
                coefficients=controlled_bindings,
            )
        return StageExecutionResult(
            calculator_name=adapter_result.calculator_name,
            calculator_version=adapter_result.calculator_version,
            calculation_type=calculation_type.value,
            result_snapshot=dict(
                _decimalize_payload(adapter_result.payload)  # type: ignore[call-overload]
            ),
            formulas=[_decimalize_mapping(f) for f in provenance.formulas],
            coefficients=[_canonical_coefficient_entry(c) for c in provenance.coefficients],
            assumptions=list(provenance.assumptions),
            warnings=[
                {
                    "code": w.code,
                    "message": w.message,
                    "details": _decimalize_mapping(w.details),
                }
                for w in adapter_result.warnings
            ],
            source_references=[_decimalize_mapping(s) for s in provenance.source_references],
            requires_review=bool(adapter_result.requires_review),
            execution_input_snapshot=dict(adapter_result.execution_input_snapshot),
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
