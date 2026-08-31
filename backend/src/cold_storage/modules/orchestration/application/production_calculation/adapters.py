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


def _to_float(value: Any) -> Any:
    """Boundary helper: accept serialized numeric values, return ``float``.

    The production calculators (e.g. ``ColdRoomZonePlanInput``)
    are typed ``float`` and Python's ``Decimal * float`` raises
    ``TypeError``.  Adapters are the typed boundary between the
    orchestrator's ``Decimal`` world and the calculators' ``float``
    world; this helper makes that boundary explicit.
    """
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _decimalize_execution_input(value: object) -> object:
    """Normalize the calculator's returned input snapshot for JSON storage."""

    if isinstance(value, (float, Decimal)):
        normalized = _to_decimal(value).normalize()
        exponent = normalized.as_tuple().exponent
        return (
            str(int(normalized)) if isinstance(exponent, int) and exponent > 0 else str(normalized)
        )
    if isinstance(value, Mapping):
        return {str(key): _decimalize_execution_input(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimalize_execution_input(item) for item in value]
    if isinstance(value, tuple):
        return [_decimalize_execution_input(item) for item in value]
    return value


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


_ZONE_COMPONENT_FIELDS: tuple[str, ...] = (
    "transmission_load_kw_r",
    "product_load_kw_r",
    "infiltration_load_kw_r",
    "internal_load_kw_r",
    "defrost_load_kw_r",
)
_ZONE_INPUT_ECHO_FIELDS: tuple[str, ...] = (
    "room_design_temperature",
    "room_height",
)


def _canonical_cooling_snapshot_payload(
    result: LegacyOrNewCalculationResult,
) -> dict[str, Any]:
    """Project the cooling calculator result onto the persisted snapshot schema.

    The Phase 2 cooling calculator reports a detailed zone-oriented payload.
    Durable orchestration keeps plant-wide aggregate component rows and, as of
    V1.7, copies kernel per-zone five components for operator audit. V1.8 also
    copies kernel input echo for room_design_temperature and room_height.
    Equipment lineage still binds on zone_code + subtotal only. The calculator
    remains the sole producer of engineering values.
    """

    payload = result.result
    if not isinstance(payload, Mapping) or not isinstance(payload.get("zones"), list):
        return dict(payload) if isinstance(payload, Mapping) else {}

    def decimal(value: object) -> Decimal:
        return Decimal(str(value))

    def text(value: Decimal) -> str:
        normalized = value.normalize()
        exponent = normalized.as_tuple().exponent
        if isinstance(exponent, int) and exponent > 0:
            return str(int(normalized))
        return str(normalized)

    totals = {
        "envelope_heat_transfer_load_kw": Decimal("0"),
        "product_sensible_heat_load_kw": Decimal("0"),
        "packaging_load_kw": Decimal("0"),
        "infiltration_load_kw": Decimal("0"),
        "personnel_load_kw": Decimal("0"),
        "lighting_load_kw": Decimal("0"),
        "evaporator_fan_load_kw": Decimal("0"),
        "defrost_additional_load_kw": Decimal("0"),
    }
    zone_snapshots: list[dict[str, str]] = []
    steps = list(getattr(result, "steps", []) or [])
    for zone in payload["zones"]:
        if not isinstance(zone, Mapping):
            continue
        zone_code = zone.get("zone_code")
        subtotal_load = zone.get("subtotal_load_kw_r")
        if zone_code is not None and subtotal_load is not None:
            zone_row: dict[str, str] = {
                "zone_code": str(zone_code),
                "subtotal_load_kw_r": text(decimal(subtotal_load)),
            }
            zone_name = zone.get("zone_name")
            if zone_name is not None:
                zone_row["zone_name"] = str(zone_name)
            temperature_level = zone.get("temperature_level")
            if temperature_level is not None:
                zone_row["temperature_level"] = str(temperature_level)
            for field_name in _ZONE_COMPONENT_FIELDS:
                raw = zone.get(field_name)
                if raw is not None:
                    zone_row[field_name] = text(decimal(raw))
            for field_name in _ZONE_INPUT_ECHO_FIELDS:
                raw = zone.get(field_name)
                if raw is not None:
                    zone_row[field_name] = text(decimal(raw))
            zone_snapshots.append(zone_row)
        totals["envelope_heat_transfer_load_kw"] += decimal(zone.get("transmission_load_kw_r", 0))
        product_total = decimal(zone.get("product_load_kw_r", 0))
        packaging = Decimal("0")
        respiration = Decimal("0")
        zone_name = str(zone.get("zone_name", ""))
        for step in steps:
            description = str(getattr(step, "description", ""))
            if zone_name and not description.endswith(zone_name):
                continue
            if getattr(step, "output_name", "") != "total_product_load_kw_r":
                continue
            inputs = getattr(step, "inputs", {})
            if isinstance(inputs, Mapping):
                packaging = decimal(inputs.get("packaging_load_kw", 0))
                respiration = decimal(inputs.get("respiration_load_kw", 0))
            break
        totals["product_sensible_heat_load_kw"] += product_total - packaging - respiration
        totals["packaging_load_kw"] += packaging
        totals["infiltration_load_kw"] += decimal(zone.get("infiltration_load_kw_r", 0))
        totals["personnel_load_kw"] += decimal(zone.get("people_load_kw_r", 0))
        totals["lighting_load_kw"] += decimal(zone.get("lighting_load_kw_r", 0))
        totals["evaporator_fan_load_kw"] += decimal(zone.get("evaporator_fan_load_kw_r", 0))
        totals["defrost_additional_load_kw"] += decimal(zone.get("defrost_load_kw_r", 0))

    return {
        "total_cooling_load_kw": text(decimal(payload.get("design_refrigeration_load_kw_r", 0))),
        "safety_margin_load_kw": text(decimal(payload.get("design_margin_kw_r", 0))),
        "envelope_heat_transfer_load_kw": text(totals["envelope_heat_transfer_load_kw"]),
        "product_sensible_heat_load_kw": text(totals["product_sensible_heat_load_kw"]),
        "packaging_load_kw": text(totals["packaging_load_kw"]),
        "infiltration_load_kw": text(totals["infiltration_load_kw"]),
        "personnel_load_kw": text(totals["personnel_load_kw"]),
        "lighting_load_kw": text(totals["lighting_load_kw"]),
        "evaporator_fan_load_kw": text(totals["evaporator_fan_load_kw"]),
        "defrost_additional_load_kw": text(totals["defrost_additional_load_kw"]),
        "other_configuration_load_kw": "0",
        "zones": zone_snapshots,
    }


def _canonical_equipment_snapshot_payload(
    result: LegacyOrNewCalculationResult,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    """Project equipment capability output onto the durable snapshot schema."""

    payload = result.result
    if not isinstance(payload, Mapping) or not isinstance(payload.get("systems"), list):
        return dict(payload) if isinstance(payload, Mapping) else {}

    from decimal import Decimal

    def decimal(value: object) -> Decimal:
        return Decimal(str(value))

    def text(value: Decimal) -> str:
        normalized = value.normalize()
        exponent = normalized.as_tuple().exponent
        if isinstance(exponent, int) and exponent > 0:
            return str(int(normalized))
        return str(normalized)

    systems = [system for system in payload["systems"] if isinstance(system, Mapping)]
    if not systems:
        return {}
    first_system = systems[0]
    zones = [
        zone for system in systems for zone in system.get("zones", []) if isinstance(zone, Mapping)
    ]
    condensing_temperature = context.get("condensing_temperature_c")
    if condensing_temperature is None:
        raise CalculatorRejectedInputError(
            calculation_type=CalculationType.EQUIPMENT.value,
            reason="equipment snapshot requires condensing_temperature_c input",
        )

    return {
        "evaporator_total_cooling_capacity_kw": text(
            sum(
                (decimal(system.get("evaporator_total_capacity_kw_r", 0)) for system in systems),
                Decimal("0"),
            )
        ),
        "evaporator_quantity": sum(int(system.get("evaporator_count", 0)) for system in systems),
        "single_evaporator_capacity_kw": text(
            sum(
                (decimal(system.get("evaporator_total_capacity_kw_r", 0)) for system in systems),
                Decimal("0"),
            )
            / max(sum(int(system.get("evaporator_count", 0)) for system in systems), 1)
        ),
        "compressor_operating_capacity_kw": text(
            sum(
                (
                    decimal(system.get("compressor_operating_capacity_kw_r", 0))
                    for system in systems
                ),
                Decimal("0"),
            )
        ),
        "compressor_installed_capacity_kw": text(
            sum(
                (
                    decimal(system.get("compressor_installed_capacity_kw_r", 0))
                    for system in systems
                ),
                Decimal("0"),
            )
        ),
        "standby_capacity_kw": text(
            sum(
                (decimal(system.get("compressor_standby_capacity_kw_r", 0)) for system in systems),
                Decimal("0"),
            )
        ),
        "condenser_heat_rejection_capacity_kw": text(
            sum(
                (decimal(system.get("condenser_heat_rejection_kw", 0)) for system in systems),
                Decimal("0"),
            )
        ),
        "evaporation_temperature_c": str(
            first_system.get(
                "design_evaporating_temperature_c", zones[0].get("evaporation_temperature_c")
            )
        ),
        "condensing_temperature_c": str(condensing_temperature),
        "defrost_method": ",".join(
            sorted(
                {str(method) for system in systems for method in system.get("defrost_methods", [])}
            )
        ),
        "review_requirement": "",
    }


def _canonical_power_snapshot_payload(
    result: LegacyOrNewCalculationResult,
) -> dict[str, Any]:
    """Project installed-power output onto the durable snapshot schema."""

    payload = result.result
    if not isinstance(payload, Mapping):
        return {}

    from decimal import Decimal

    def decimal(value: object) -> Decimal:
        return Decimal(str(value))

    def text(value: Decimal) -> str:
        normalized = value.normalize()
        exponent = normalized.as_tuple().exponent
        if isinstance(exponent, int) and exponent > 0:
            return str(int(normalized))
        return str(normalized)

    component_rows = (
        ("refrigeration", "refrigeration_system_installed_power_kw_e"),
        ("processing", "process_equipment_installed_power_kw_e"),
        ("lighting", "lighting_installed_power_kw_e"),
        ("auxiliary", "auxiliary_installed_power_kw_e"),
    )
    demand_factors = {"refrigeration": Decimal("1"), "processing": Decimal("1")}
    for step in list(getattr(result, "steps", []) or []):
        if getattr(step, "output_name", "") != "estimated_peak_demand_kw_e":
            continue
        inputs = getattr(step, "inputs", {})
        if isinstance(inputs, Mapping):
            demand_factors["refrigeration"] = decimal(
                inputs.get("refrigeration_demand_factor", "1")
            )
            demand_factors["processing"] = decimal(inputs.get("production_demand_factor", "1"))
        break

    items: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for category, field_name in component_rows:
        installed = decimal(payload.get(field_name, 0))
        demand_factor = demand_factors.get(category, Decimal("1"))
        items.append(
            {
                "category": category,
                "installed_power_kw": text(installed),
                "demand_factor": text(demand_factor),
                "estimated_demand_kw": text(installed * demand_factor),
            }
        )
        summary_rows.append(
            {
                "name": category,
                "basis": "canonical_installed_power_calculator",
                "total_power_kw": text(installed),
            }
        )

    equipment_rows = []
    for sequence, raw_item in enumerate(payload.get("equipment_items", []), start=1):
        if not isinstance(raw_item, Mapping):
            continue
        equipment_rows.append(
            {
                "sequence": sequence,
                "name": str(raw_item.get("name", "")),
                "area": str(raw_item.get("category", "")),
                "quantity": text(decimal(raw_item.get("quantity", 0))),
                "defrost_power_kw": None,
                "defrost_total_power_kw": None,
                "running_power_kw": str(raw_item.get("unit_power_kw_e", "0")),
                "total_power_kw": str(raw_item.get("total_power_kw_e", "0")),
                "section": str(raw_item.get("category", "")),
            }
        )

    return {
        "total_installed_power_kw_e": text(decimal(payload.get("total_installed_power_kw_e", 0))),
        "total_estimated_demand_kw": text(decimal(payload.get("estimated_peak_demand_kw_e", 0))),
        "equipment_rows": equipment_rows,
        "summary_rows": summary_rows,
        "items": items,
        "assumptions": list(getattr(result, "assumptions", []) or []),
    }


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
    snapshot_context: Mapping[str, Any] | None = None,
    execution_input_snapshot: Mapping[str, Any] | None = None,
) -> AdapterResult:
    """Translate a :class:`CalculationResult` into an :class:`AdapterResult`.

    This is the single source of truth for adapter result
    construction.  Adapters call this helper after invoking the
    underlying calculator.
    """
    if calculation_type is CalculationType.COOLING_LOAD:
        result_payload = _canonical_cooling_snapshot_payload(result)
    elif calculation_type is CalculationType.EQUIPMENT:
        result_payload = _canonical_equipment_snapshot_payload(result, snapshot_context or {})
    elif calculation_type is CalculationType.POWER:
        result_payload = _canonical_power_snapshot_payload(result)
    else:
        result_payload = result.result
    payload = freeze_for_hash(result_payload) if result_payload else {}
    content_hash = compute_content_hash(payload) if payload else ""
    raw_execution_input: object = execution_input_snapshot
    if raw_execution_input is None:
        raw_execution_input = getattr(result, "input_snapshot", None)
    if raw_execution_input is None:
        raw_execution_input = getattr(result, "input", {})
    normalized_execution_input = _decimalize_execution_input(raw_execution_input)
    if not isinstance(normalized_execution_input, dict):
        raise TypeError("calculator execution input snapshot must be an object")
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
        execution_input_snapshot=normalized_execution_input,
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
        """Filter ``raw_inputs`` to the dataclass' field names.

        The orchestrator threads ``Decimal`` values into the
        raw input payload so the canonical-JSON hash is
        stable.  ``ColdRoomZonePlanInput`` is typed ``float``;
        convert ``Decimal`` back to ``float`` at this
        boundary so the calculator's ``Decimal * float``
        type error never surfaces.
        """
        allowed = set(ColdRoomZonePlanInput.__dataclass_fields__.keys())
        return {k: _to_float(v) for k, v in raw_inputs.items() if k in allowed}


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
            snapshot_context=projection.raw_inputs,
            execution_input_snapshot=projection.raw_inputs,
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
            "refrigeration_demand_factor",
            "production_demand_factor",
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
            execution_input_snapshot=projection.raw_inputs,
        )


__all__ = [
    "CoolingLoadAdapter",
    "EquipmentCapabilityAdapter",
    "InstalledPowerAdapter",
    "InvestmentAdapter",
    "ZonePlanningAdapter",
]
