"""Equipment adapter that preserves typed electrical totals from calculator output."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from cold_storage.modules.calculations.domain.equipment import calculate_equipment_capability
from cold_storage.modules.calculations.domain.errors import CoreCalculationError
from cold_storage.modules.orchestration.application.production_calculation.adapters import (
    EquipmentCapabilityAdapter,
    _build_adapter_result,
)
from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    AdapterResult,
    CalculatorInputProjection,
)
from cold_storage.modules.orchestration.application.production_calculation.errors import (
    CalculatorRejectedInputError,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType


def _decimalize(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class ElectricalCapturingEquipmentAdapter(EquipmentCapabilityAdapter):
    """Preserve typed electrical totals from equipment calculator output."""

    last_total_compressor_input_power_kw_e: str | None = None

    def execute(self, projection: CalculatorInputProjection) -> AdapterResult:
        if projection.calculation_type is not CalculationType.EQUIPMENT:
            return super().execute(projection)

        self.last_total_compressor_input_power_kw_e = None
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

        raw_result = result.result
        if isinstance(raw_result, Mapping):
            electrical = raw_result.get("total_compressor_input_power_kw_e")
            if electrical is not None:
                self.last_total_compressor_input_power_kw_e = str(_decimalize(electrical))

        return _build_adapter_result(
            calculation_type=CalculationType.EQUIPMENT,
            result=result,
            snapshot_context=projection.raw_inputs,
            execution_input_snapshot=projection.raw_inputs,
        )
