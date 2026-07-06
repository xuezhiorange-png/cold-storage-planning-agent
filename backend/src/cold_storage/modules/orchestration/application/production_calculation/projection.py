"""Task 11B Phase 2 — project version → calculator input projection.

The projection helper is the **only** code path that translates an
approved project version snapshot into a typed
``CalculatorInputProjection``.  Adapters MUST receive a projection
and MUST NOT read the raw ``input_snapshot`` directly.

The helper is a pure function — no session, no ORM, no I/O.  It
exposes a single entry point per calculation type so the
orchestrator (Phase 3) can compose the projections in a typed
manner.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    CalculatorInputProjection,
)
from cold_storage.modules.orchestration.application.production_calculation.errors import (
    InvalidProjectInputError,
)
from cold_storage.modules.orchestration.application.production_calculation.threading import (
    assert_database_backend_supported,
    assert_identity_complete,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType

# Field names that must be present in the raw input payload for each
# calculation type.  These are checked at projection time so the
# adapter never has to deal with a partial input.
_REQUIRED_FIELDS: Mapping[CalculationType, tuple[str, ...]] = {
    CalculationType.ZONE: (
        "daily_inbound_mass_kg",
        "working_time_h_per_day",
        "finished_storage_days",
        "packaging_storage_days",
        "precooling_required_ratio",
    ),
    CalculationType.COOLING_LOAD: ("zones", "coefficients"),
    CalculationType.EQUIPMENT: ("systems", "coefficients"),
    CalculationType.POWER: (
        "compressor_input_power_kw_e",
        "evaporator_fan_power_kw_e",
        "condenser_fan_power_kw_e",
    ),
    CalculationType.INVESTMENT: (
        "total_area_m2",
        "refrigerated_area_m2",
        "frozen_area_m2",
        "position_count",
        "total_power_kw",
    ),
}


def project_calculator_input(
    *,
    calculation_type: CalculationType,
    raw_inputs: Mapping[str, Any],
    actor: str,
    correlation_id: str,
    database_backend: str,
    upstream_calculation_ids: Mapping[str, str] | None = None,
    calculator_name: str = "",
    calculator_version: str = "",
) -> CalculatorInputProjection:
    """Build a typed ``CalculatorInputProjection`` for the given stage.

    The function defensively copies the inputs so external mutation
    cannot affect the projection.  It validates identity fields and
    the per-type required fields, raising a typed
    :class:`InvalidProjectInputError` on any failure (fail-closed).
    """
    assert_database_backend_supported(database_backend)
    assert_identity_complete(
        actor=actor,
        correlation_id=correlation_id,
        database_backend=database_backend,
    )

    required = _REQUIRED_FIELDS.get(calculation_type, ())
    missing = [field for field in required if field not in raw_inputs]
    if missing:
        raise InvalidProjectInputError(
            field_name=missing[0],
            reason=(f"calculator type {calculation_type.value!r} requires fields {missing!r}"),
        )

    upstream = dict(upstream_calculation_ids) if upstream_calculation_ids else {}
    return CalculatorInputProjection(
        calculation_type=calculation_type,
        raw_inputs=dict(raw_inputs),
        actor=actor,
        correlation_id=correlation_id,
        database_backend=database_backend,
        upstream_calculation_ids=upstream,
        calculator_name=calculator_name,
        calculator_version=calculator_version,
    )
