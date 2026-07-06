"""Task 11B Phase 2 — adapter boundary wrappers.

Five adapter wrappers, one per calculation type, each wrapping an
existing production calculator (or class).  The adapters are the
**only** entry points the orchestrator (Phase 3+) is allowed to
use to invoke the production calculators.

Invariants enforced by every adapter
------------------------------------
* Inputs come from a typed :class:`CalculatorInputProjection` —
  evaluation fixtures are forbidden.
* The calculator's ``requires_review`` verdict is propagated
  verbatim (no suppression, no reclassification).
* The adapter does not write to the database, does not commit
  sessions, and does not call ``SchemeService.run``.
* Formula / threshold / weight / review rules of the underlying
  calculator are NOT modified.  If a calculator sets
  ``requires_review=True``, the adapter surfaces ``True``.
* The returned ``AdapterResult`` is contract-validated before
  the adapter returns.

Each adapter exposes a single ``execute(projection)`` method that
returns a :class:`AdapterResult`.  No other public surface is
provided.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from cold_storage.modules.calculations.domain.cooling_load import (
    calculate_cooling_load,
)
from cold_storage.modules.calculations.domain.equipment import (
    EquipmentCapabilityCalcInput,
    calculate_equipment_capability,
)
from cold_storage.modules.calculations.domain.errors import CoreCalculationError
from cold_storage.modules.calculations.domain.investment import (
    InvestmentEstimateInput,
    InvestmentEstimator,
)
from cold_storage.modules.calculations.domain.models import (
    CalculationResult as NewCalculationResult,
)
from cold_storage.modules.calculations.domain.power import (
    InstalledPowerCalcInput,
    calculate_installed_power,
)
from cold_storage.modules.calculations.domain.result import (
    CalculationResult,
    FormulaReference,
)
from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.orchestration.application.production_calculation.contract import (
    assert_requires_review_propagated,
    freeze_for_hash,
    validate_adapter_result,
)
from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    AdapterBlocker,
    AdapterProvenance,
    AdapterResult,
    AdapterWarning,
    CalculatorInputProjection,
)
from cold_storage.modules.orchestration.application.production_calculation.errors import (
    CalculatorRejectedInputError,
)
from cold_storage.modules.orchestration.application.production_calculation.threading import (
    compute_content_hash,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType

# The codebase carries two parallel ``CalculationResult`` shapes:
#
# * the legacy ``result.CalculationResult`` (used by the
#   zone_planning, investment, and ``build_cooling_load_input``
#   paths), which exposes ``errors``, ``formula_references``,
#   ``source_references``;
# * the newer ``models.CalculationResult`` (used by
#   ``calculate_cooling_load``, ``calculate_equipment_capability``,
#   ``calculate_installed_power``), which exposes ``steps``,
#   ``coefficient_references`` and omits ``errors`` /
#   ``formula_references``.
#
# Phase 2 adapters wrap both.  ``LegacyOrNewCalculationResult``
# is the union of the two so the helper signatures accept
# either shape.  All result-shape discrimination is in the
# polymorphic helper functions.
LegacyOrNewCalculationResult = CalculationResult | NewCalculationResult

# ── Internal helpers ───────────────────────────────────────────────────────


def _to_decimal(value: Any) -> Decimal:
    """Decimal-safe conversion reused by adapters that need typed Decimals."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        # Reject NaN/inf explicitly — adapters are typed boundaries
        if math.isnan(value) or math.isinf(value):
            raise CalculatorRejectedInputError(
                calculation_type="<adapter>",
                reason=f"non-finite float: {value!r}",
            )
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value)
    raise CalculatorRejectedInputError(
        calculation_type="<adapter>",
        reason=f"cannot convert {type(value).__name__} to Decimal",
    )


def _build_warning_dicts(
    result: LegacyOrNewCalculationResult,
) -> tuple[AdapterWarning, ...]:
    """Translate a calculator's warnings into typed ``AdapterWarning``s.

    The mapping is verbatim — no message rewriting, no code
    remapping.  This is the surface the orchestrator (Phase 3)
    relies on for fail-closed warning propagation.
    """
    return tuple(
        AdapterWarning(
            code=w.code,
            message=w.message,
            details=dict(w.details),
        )
        for w in result.warnings
    )


def _build_formula_refs(
    result: LegacyOrNewCalculationResult,
) -> tuple[dict[str, Any], ...]:
    """Translate formula references into plain dicts.

    The legacy :class:`result.CalculationResult` exposes
    ``formula_references`` (a list of :class:`FormulaReference` or
    mapping).  The newer :class:`models.CalculationResult` exposes
    ``steps`` (a list of :class:`CalculationStep`) and
    ``coefficient_references`` (a list of
    :class:`CoefficientReference`).  The adapter surfaces
    whichever shape the calculator returned — verbatim, no
    remapping — so the orchestrator (Phase 3) and the audit
    layer can trust the provenance.
    """
    refs: list[dict[str, Any]] = []
    for ref in getattr(result, "formula_references", []) or []:
        if isinstance(ref, FormulaReference):
            refs.append(
                {
                    "formula_id": ref.formula_id,
                    "formula_version": ref.formula_version,
                    "expression": ref.expression,
                    "description": ref.description,
                }
            )
        elif isinstance(ref, Mapping):
            refs.append(dict(ref))
    return tuple(refs)


def _build_steps(
    result: LegacyOrNewCalculationResult,
) -> tuple[dict[str, Any], ...]:
    """Translate ``CalculationStep`` into plain dicts when present.

    The newer :class:`models.CalculationResult` carries its
    traceability in ``steps``; the legacy class does not.  The
    helper is a no-op on the legacy class so the result is
    always a tuple.
    """
    out: list[dict[str, Any]] = []
    for step in getattr(result, "steps", []) or []:
        to_dict = getattr(step, "to_dict", None)
        if callable(to_dict):
            out.append(dict(to_dict()))
        elif isinstance(step, Mapping):
            out.append(dict(step))
    return tuple(out)


def _build_coefficient_refs(
    result: LegacyOrNewCalculationResult,
) -> tuple[dict[str, Any], ...]:
    """Translate coefficient references into plain dicts.

    The legacy class exposes ``coefficients`` (a list of
    mappings).  The newer class exposes
    ``coefficient_references`` (a list of
    :class:`CoefficientReference`).  Both surfaces are
    surfaced verbatim, no remapping.
    """
    out: list[dict[str, Any]] = []
    for coeff in getattr(result, "coefficients", []) or []:
        if isinstance(coeff, Mapping):
            out.append(dict(coeff))
    for ref in getattr(result, "coefficient_references", []) or []:
        to_dict = getattr(ref, "to_dict", None)
        if callable(to_dict):
            out.append(dict(to_dict()))
        elif isinstance(ref, Mapping):
            out.append(dict(ref))
    return tuple(out)


def _build_source_refs(
    result: LegacyOrNewCalculationResult,
) -> tuple[dict[str, Any], ...]:
    return tuple(dict(s) for s in getattr(result, "source_references", []) or [])


def _build_provenance(result: LegacyOrNewCalculationResult) -> AdapterProvenance:
    return AdapterProvenance(
        formulas=_build_formula_refs(result),
        coefficients=_build_coefficient_refs(result),
        source_references=_build_source_refs(result),
        assumptions=tuple(getattr(result, "assumptions", []) or []),
    )


def _build_calculator_errors(
    result: LegacyOrNewCalculationResult,
) -> tuple[AdapterBlocker, ...]:
    """Translate the calculator's ``errors`` list into typed blockers.

    The legacy class exposes ``errors`` (a list of
    :class:`CalculationError`).  The newer class does not — it
    encodes failure via ``success=False`` plus warnings.  The
    adapter surfaces whichever shape the calculator returned.
    """
    return tuple(
        AdapterBlocker(
            code=err.code,
            message=err.message,
            field_name="calculator_error",
            details=dict(err.details),
        )
        for err in getattr(result, "errors", []) or []
    )


def _build_adapter_result(
    *,
    calculation_type: CalculationType,
    result: LegacyOrNewCalculationResult,
) -> AdapterResult:
    """Translate a :class:`CalculationResult` into an :class:`AdapterResult`.

    This is the single source of truth for adapter result
    construction.  Adapters call this helper after invoking the
    underlying calculator.
    """
    payload = freeze_for_hash(result.result) if result.result else {}
    content_hash = compute_content_hash(payload) if payload else ""
    # The calculator may have flagged failure via ``success=False``
    # without populating a structured ``errors`` list.  The newer
    # ``models.CalculationResult`` uses this pattern.  The legacy
    # class adds structured ``errors``.  The adapter surfaces the
    # success flag verbatim and translates ``errors`` when present.
    adapter_result = AdapterResult(
        calculation_type=calculation_type,
        payload=payload,
        content_hash=content_hash,
        requires_review=bool(result.requires_review),
        warnings=_build_warning_dicts(result),
        blockers=_build_calculator_errors(result),
        provenance=_build_provenance(result),
        calculator_name=result.calculator_name,
        calculator_version=result.calculator_version,
        calculator_success=bool(result.success),
    )
    assert_requires_review_propagated(
        calculator_requires_review=bool(result.requires_review),
        adapter_requires_review=adapter_result.requires_review,
        calculation_type=calculation_type.value,
    )
    validate_adapter_result(adapter_result)
    return adapter_result


# ── Zone planning adapter ──────────────────────────────────────────────────


class ZonePlanningAdapter:
    """Adapter wrapping :class:`ColdRoomZonePlanner`."""

    calculator_name = "cold_room_zone_plan"
    calculator_version = "1.0.0"

    def __init__(self, *, planner: ColdRoomZonePlanner | None = None) -> None:
        # The default planner uses the production demo coefficients.
        # Phase 2 does not swap coefficients — that is a Phase 3+
        # concern requiring the approved non-demo coefficient
        # resolver.  Tests can inject an alternate planner.
        self._planner = planner or ColdRoomZonePlanner()

    def execute(self, projection: CalculatorInputProjection) -> AdapterResult:
        if projection.calculation_type is not CalculationType.ZONE:
            raise CalculatorRejectedInputError(
                calculation_type=projection.calculation_type.value,
                reason="ZonePlanningAdapter only accepts ZONE projections",
            )

        # Build the typed input from the raw dict.  ``asdict`` on
        # ``ColdRoomZonePlanInput`` would require us to first
        # construct the typed object; we project the raw dict onto
        # the dataclass' field names (defaults fill in any
        # unspecified fields).  This is the only point where the
        # adapter translates dict→typed input.
        try:
            typed_input = ColdRoomZonePlanInput(
                **self._project_to_zone_input_fields(projection.raw_inputs),
            )
        except CoreCalculationError as exc:
            raise CalculatorRejectedInputError(
                calculation_type=CalculationType.ZONE.value,
                reason=f"zone planner input rejected: {exc}",
            ) from exc
        except (TypeError, ValueError) as exc:
            raise CalculatorRejectedInputError(
                calculation_type=CalculationType.ZONE.value,
                reason=f"zone planner input rejected: {exc}",
            ) from exc

        result = self._planner.plan(typed_input)
        return _build_adapter_result(
            calculation_type=CalculationType.ZONE,
            result=result,
        )

    @staticmethod
    def _project_to_zone_input_fields(
        raw_inputs: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Filter ``raw_inputs`` to the dataclass' field names."""
        allowed = set(ColdRoomZonePlanInput.__dataclass_fields__.keys())
        return {k: v for k, v in raw_inputs.items() if k in allowed}


# ── Cooling load adapter ──────────────────────────────────────────────────


class CoolingLoadAdapter:
    """Adapter wrapping :func:`calculate_cooling_load`.

    The cooling load calculator expects a typed
    :class:`CoolingLoadCalcInput`.  The adapter reuses the
    existing :func:`build_cooling_load_input` helper from the
    ``calculations`` application layer — that helper is the
    single boundary that turns a flat dict into the typed input.
    """

    calculator_name = "cooling_load"
    calculator_version = "1.0.0"

    def execute(self, projection: CalculatorInputProjection) -> AdapterResult:
        if projection.calculation_type is not CalculationType.COOLING_LOAD:
            raise CalculatorRejectedInputError(
                calculation_type=projection.calculation_type.value,
                reason="CoolingLoadAdapter only accepts COOLING_LOAD projections",
            )

        from cold_storage.modules.calculations.application.cooling_load_api import (
            build_cooling_load_input,
        )

        try:
            typed_input = build_cooling_load_input(dict(projection.raw_inputs))
        except CoreCalculationError as exc:
            raise CalculatorRejectedInputError(
                calculation_type=CalculationType.COOLING_LOAD.value,
                reason=f"cooling load input rejected: {exc}",
            ) from exc
        except (TypeError, ValueError) as exc:
            raise CalculatorRejectedInputError(
                calculation_type=CalculationType.COOLING_LOAD.value,
                reason=f"cooling load input rejected: {exc}",
            ) from exc

        # The cooling load calculator reads ``worker_heat_gain``
        # and ``motor_efficiency`` from the *zone*, not the
        # coefficient set.  ``build_cooling_load_input`` places
        # them on the coefficient set, so the adapter re-binds
        # them on each zone.  This is a *boundary translation* —
        # the underlying calculator is not modified.
        coeff_data_raw: object = projection.raw_inputs.get("coefficients", {})
        coeff_data: dict[str, object] = coeff_data_raw if isinstance(coeff_data_raw, dict) else {}
        worker_heat_gain: object = coeff_data.get("worker_heat_gain")
        motor_efficiency: object = coeff_data.get("motor_efficiency")
        if worker_heat_gain is not None or motor_efficiency is not None:
            from dataclasses import replace

            from cold_storage.modules.calculations.domain.cooling_load import (
                ZoneCoolingLoadInput,
            )

            new_zones: list[ZoneCoolingLoadInput] = []
            for zone in typed_input.zones:
                new_zones.append(
                    replace(
                        zone,
                        worker_heat_gain=(
                            _to_decimal(worker_heat_gain)
                            if worker_heat_gain is not None
                            else zone.worker_heat_gain
                        ),
                        motor_efficiency=(
                            _to_decimal(motor_efficiency)
                            if motor_efficiency is not None
                            else zone.motor_efficiency
                        ),
                    )
                )
            typed_input = replace(typed_input, zones=new_zones)

        try:
            result = calculate_cooling_load(typed_input)
        except CoreCalculationError as exc:
            raise CalculatorRejectedInputError(
                calculation_type=CalculationType.COOLING_LOAD.value,
                reason=f"cooling load input rejected: {exc}",
            ) from exc
        return _build_adapter_result(
            calculation_type=CalculationType.COOLING_LOAD,
            result=result,
        )


# ── Equipment capability adapter ───────────────────────────────────────────


class EquipmentCapabilityAdapter:
    """Adapter wrapping :func:`calculate_equipment_capability`.

    The calculator expects a structured
    :class:`EquipmentCapabilityCalcInput` with typed
    :class:`TemperatureSystemInput` and
    :class:`ZoneEquipmentInput` lists.  The adapter builds those
    typed objects from the raw ``systems`` / ``coefficients``
    keys in the projection.  Coefficients carry the
    ``revision_id`` / ``source_type`` / ``revision_status``
    metadata that gates the ``requires_review`` flag.
    """

    calculator_name = "equipment_capability"
    calculator_version = "1.0.0"

    def execute(self, projection: CalculatorInputProjection) -> AdapterResult:
        if projection.calculation_type is not CalculationType.EQUIPMENT:
            raise CalculatorRejectedInputError(
                calculation_type=projection.calculation_type.value,
                reason="EquipmentCapabilityAdapter only accepts EQUIPMENT projections",
            )

        try:
            typed_input = self._build_equipment_input(projection.raw_inputs)
        except CoreCalculationError as exc:
            raise CalculatorRejectedInputError(
                calculation_type=CalculationType.EQUIPMENT.value,
                reason=f"equipment capability input rejected: {exc}",
            ) from exc
        except (TypeError, KeyError, ValueError) as exc:
            raise CalculatorRejectedInputError(
                calculation_type=CalculationType.EQUIPMENT.value,
                reason=f"equipment capability input rejected: {exc}",
            ) from exc

        try:
            result = calculate_equipment_capability(typed_input)
        except CoreCalculationError as exc:
            raise CalculatorRejectedInputError(
                calculation_type=CalculationType.EQUIPMENT.value,
                reason=f"equipment capability input rejected: {exc}",
            ) from exc
        return _build_adapter_result(
            calculation_type=CalculationType.EQUIPMENT,
            result=result,
        )

    @staticmethod
    def _build_equipment_input(
        raw_inputs: Mapping[str, Any],
    ) -> EquipmentCapabilityCalcInput:
        from cold_storage.modules.calculations.domain.equipment import (
            EquipmentCoefficientSet,
            TemperatureSystemInput,
            ZoneEquipmentInput,
        )

        systems_raw = raw_inputs.get("systems", [])
        systems: list[TemperatureSystemInput] = []
        for sys in systems_raw:
            zones = [
                ZoneEquipmentInput(
                    zone_code=z["zone_code"],
                    zone_name=z["zone_name"],
                    design_cooling_load_kw_r=_to_decimal(z["design_cooling_load_kw_r"]),
                    evaporator_count=int(z.get("evaporator_count", 1)),
                    evaporation_temperature_c=_to_decimal(
                        z.get("evaporation_temperature_c", "-10")
                    ),
                    defrost_method=str(z.get("defrost_method", "electric")),
                )
                for z in sys.get("zones", [])
            ]
            systems.append(
                TemperatureSystemInput(
                    system_code=sys["system_code"],
                    system_name=sys["system_name"],
                    design_evaporating_temperature=_to_decimal(
                        sys["design_evaporating_temperature"]
                    ),
                    zones=zones,
                )
            )

        coeff_raw = raw_inputs.get("coefficients", {}) or {}
        coefficients = EquipmentCoefficientSet(
            redundancy_ratio=(
                _to_decimal(coeff_raw["redundancy_ratio"])
                if coeff_raw.get("redundancy_ratio") is not None
                else None
            ),
            evaporator_capacity_margin=(
                _to_decimal(coeff_raw["evaporator_capacity_margin"])
                if coeff_raw.get("evaporator_capacity_margin") is not None
                else None
            ),
            condenser_capacity_margin=(
                _to_decimal(coeff_raw["condenser_capacity_margin"])
                if coeff_raw.get("condenser_capacity_margin") is not None
                else None
            ),
            compressor_cop=(
                _to_decimal(coeff_raw["compressor_cop"])
                if coeff_raw.get("compressor_cop") is not None
                else None
            ),
            revision_ids=dict(coeff_raw.get("revision_ids", {}) or {}),
            source_types=dict(coeff_raw.get("source_types", {}) or {}),
            revision_statuses=dict(coeff_raw.get("revision_statuses", {}) or {}),
        )
        return EquipmentCapabilityCalcInput(
            systems=systems,
            coefficients=coefficients,
        )


# ── Installed power adapter ───────────────────────────────────────────────


class InstalledPowerAdapter:
    """Adapter wrapping :func:`calculate_installed_power`."""

    calculator_name = "installed_power"
    calculator_version = "1.0.0"

    def execute(self, projection: CalculatorInputProjection) -> AdapterResult:
        if projection.calculation_type is not CalculationType.POWER:
            raise CalculatorRejectedInputError(
                calculation_type=projection.calculation_type.value,
                reason="InstalledPowerAdapter only accepts POWER projections",
            )

        try:
            typed_input = self._build_power_input(projection.raw_inputs)
        except CoreCalculationError as exc:
            raise CalculatorRejectedInputError(
                calculation_type=CalculationType.POWER.value,
                reason=f"installed power input rejected: {exc}",
            ) from exc
        except (TypeError, KeyError, ValueError) as exc:
            raise CalculatorRejectedInputError(
                calculation_type=CalculationType.POWER.value,
                reason=f"installed power input rejected: {exc}",
            ) from exc

        result = calculate_installed_power(typed_input)
        return _build_adapter_result(
            calculation_type=CalculationType.POWER,
            result=result,
        )

    @staticmethod
    def _build_power_input(
        raw_inputs: Mapping[str, Any],
    ) -> InstalledPowerCalcInput:
        from cold_storage.modules.calculations.domain.power import (
            InstalledPowerCalcInput as PowerInput,
        )
        from cold_storage.modules.calculations.domain.power import (
            PowerEquipmentItem,
        )

        decimal_fields = (
            "compressor_input_power_kw_e",
            "evaporator_fan_power_kw_e",
            "condenser_fan_power_kw_e",
            "pump_power_kw_e",
            "defrost_power_kw_e",
            "processing_equipment_power_kw_e",
            "lighting_power_kw_e",
            "other_auxiliary_power_kw_e",
        )
        kwargs: dict[str, Any] = {}
        for field_name in decimal_fields:
            if field_name in raw_inputs:
                kwargs[field_name] = _to_decimal(raw_inputs[field_name])

        # Build equipment_items from the raw_inputs
        equipment_items_raw = raw_inputs.get("equipment_items", []) or []
        equipment_items: list[PowerEquipmentItem] = []
        for item in equipment_items_raw:
            equipment_items.append(
                PowerEquipmentItem(
                    name=item["name"],
                    category=item["category"],
                    quantity=int(item["quantity"]),
                    unit_power_kw_e=_to_decimal(item["unit_power_kw_e"]),
                    demand_factor=_to_decimal(item.get("demand_factor", "1.0")),
                )
            )
        if equipment_items:
            kwargs["equipment_items"] = tuple(equipment_items)

        return PowerInput(**kwargs)


# ── Investment adapter ────────────────────────────────────────────────────


class InvestmentAdapter:
    """Adapter wrapping :class:`InvestmentEstimator`."""

    calculator_name = "investment_estimate"
    calculator_version = "1.0.0"

    def __init__(self, *, estimator: InvestmentEstimator | None = None) -> None:
        self._estimator = estimator or InvestmentEstimator()

    def execute(self, projection: CalculatorInputProjection) -> AdapterResult:
        if projection.calculation_type is not CalculationType.INVESTMENT:
            raise CalculatorRejectedInputError(
                calculation_type=projection.calculation_type.value,
                reason="InvestmentAdapter only accepts INVESTMENT projections",
            )

        try:
            # ``InvestmentEstimateInput`` is a ``float``-typed
            # dataclass.  The adapter converts Decimal inputs to
            # ``float`` at the boundary so the calculator's
            # arithmetic (which multiplies by ``int`` coefficients)
            # stays a ``float`` and the existing ``_number``
            # type-narrow check continues to work.  This is
            # a *boundary conversion*, not a formula change.
            typed_input = InvestmentEstimateInput(
                total_area_m2=float(_to_decimal(projection.raw_inputs["total_area_m2"])),
                refrigerated_area_m2=float(
                    _to_decimal(projection.raw_inputs["refrigerated_area_m2"]),
                ),
                frozen_area_m2=float(_to_decimal(projection.raw_inputs["frozen_area_m2"])),
                position_count=int(str(projection.raw_inputs["position_count"])),
                total_power_kw=float(_to_decimal(projection.raw_inputs["total_power_kw"])),
            )  # boundary conversion
        except (TypeError, KeyError, ValueError) as exc:
            raise CalculatorRejectedInputError(
                calculation_type=CalculationType.INVESTMENT.value,
                reason=f"investment input rejected: {exc}",
            ) from exc

        result = self._estimator.estimate(typed_input)
        return _build_adapter_result(
            calculation_type=CalculationType.INVESTMENT,
            result=result,
        )


__all__ = [
    "CoolingLoadAdapter",
    "EquipmentCapabilityAdapter",
    "InstalledPowerAdapter",
    "InvestmentAdapter",
    "ZonePlanningAdapter",
]
