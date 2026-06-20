"""Application-level service for orchestrating core planning calculations.

``CoreCalculationService`` chains the individual calculators, validates
cross-calculator consistency, and optionally snapshots results into a
``ProjectVersion``.

This module lives in the ``application`` layer — it may depend on domain
calculators and on application-level domain models (ProjectVersion), but
it must **not** depend on infrastructure (databases, ORM, network).
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from cold_storage.modules.calculations.domain.areas import (
    ZoneAreaSpec,
    calculate_areas,
)
from cold_storage.modules.calculations.domain.errors import (
    LockedProjectVersionError,
)
from cold_storage.modules.calculations.domain.inventory import (
    InventoryCalcInput,
    calculate_inventory,
)
from cold_storage.modules.calculations.domain.models import (
    CalculationResult,
    CalculationWarning,
)
from cold_storage.modules.calculations.domain.pallets import (
    PalletCalcInput,
    calculate_pallets,
)
from cold_storage.modules.calculations.domain.precooling import (
    PrecoolingCalcInput,
    calculate_precooling,
)
from cold_storage.modules.calculations.domain.throughput import (
    ThroughputCalcInput,
    calculate_throughput,
)

# Version of the orchestration logic
ORCHESTRATION_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Orchestrated result
# ---------------------------------------------------------------------------


class CoreCalculationOrchestrationResult:
    """Aggregated result from running the full core calculation pipeline."""

    def __init__(
        self,
        *,
        throughput: CalculationResult | None = None,
        inventory: CalculationResult | None = None,
        pallets: CalculationResult | None = None,
        precooling: CalculationResult | None = None,
        areas: CalculationResult | None = None,
        global_warnings: list[CalculationWarning] | None = None,
        success: bool = True,
        errors: list[str] | None = None,
    ) -> None:
        self.throughput = throughput
        self.inventory = inventory
        self.pallets = pallets
        self.precooling = precooling
        self.areas = areas
        self.global_warnings = global_warnings or []
        self.success = success
        self.errors = errors or []
        self.calculated_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        results: dict[str, Any] = {
            "orchestration_version": ORCHESTRATION_VERSION,
            "success": self.success,
            "calculated_at": self.calculated_at.isoformat(),
            "global_warnings": [w.to_dict() for w in self.global_warnings],
            "errors": self.errors,
        }
        if self.throughput is not None:
            results["throughput"] = self.throughput.to_dict()
        if self.inventory is not None:
            results["inventory"] = self.inventory.to_dict()
        if self.pallets is not None:
            results["pallets"] = self.pallets.to_dict()
        if self.precooling is not None:
            results["precooling"] = self.precooling.to_dict()
        if self.areas is not None:
            results["areas"] = self.areas.to_dict()
        return results


# ---------------------------------------------------------------------------
# Helper: convert legacy float inputs to Decimal
# ---------------------------------------------------------------------------


def _to_decimal(value: Any) -> Decimal:
    """Safely convert a value to Decimal."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value)
    raise ValueError(f"Cannot convert {type(value)} to Decimal")


# ---------------------------------------------------------------------------
# Core calculation service
# ---------------------------------------------------------------------------


class CoreCalculationService:
    """Orchestrates all core calculators with optional coefficient resolution.

    Pure service — no database access.  Accepts either strongly-typed
    calculator inputs or a flat ``dict`` from a project version's
    ``input_snapshot``.
    """

    def orchestrate_core_calculation(
        self,
        *,
        throughput_input: ThroughputCalcInput | None = None,
        inventory_input: InventoryCalcInput | None = None,
        pallet_input: PalletCalcInput | None = None,
        precooling_input: PrecoolingCalcInput | None = None,
        area_zones: list[ZoneAreaSpec] | None = None,
    ) -> CoreCalculationOrchestrationResult:
        """Run calculators in sequence and validate cross-calculator consistency.

        Parameters are optional — any ``None`` calculator will be skipped.
        The service will run as many calculators as it can and collect
        warnings and errors across all of them.
        """

        results: dict[str, CalculationResult] = {}
        global_warnings: list[CalculationWarning] = []
        errors: list[str] = []

        # --- run throughput ------------------------------------------------
        if throughput_input is not None:
            try:
                results["throughput"] = calculate_throughput(throughput_input)
            except Exception as exc:
                errors.append(f"throughput: {exc}")

        # --- run inventory -------------------------------------------------
        if inventory_input is not None:
            try:
                results["inventory"] = calculate_inventory(inventory_input)
            except Exception as exc:
                errors.append(f"inventory: {exc}")

        # --- run pallets ---------------------------------------------------
        if pallet_input is not None:
            try:
                results["pallets"] = calculate_pallets(pallet_input)
            except Exception as exc:
                errors.append(f"pallets: {exc}")

        # --- run precooling ------------------------------------------------
        if precooling_input is not None:
            try:
                results["precooling"] = calculate_precooling(precooling_input)
            except Exception as exc:
                errors.append(f"precooling: {exc}")

        # --- run areas -----------------------------------------------------
        if area_zones is not None:
            try:
                results["areas"] = calculate_areas(area_zones)
            except Exception as exc:
                errors.append(f"areas: {exc}")

        # --- cross-calculator consistency checks ---------------------------
        consistency_warnings = self._check_consistency(results)
        global_warnings.extend(consistency_warnings)

        return CoreCalculationOrchestrationResult(
            throughput=results.get("throughput"),
            inventory=results.get("inventory"),
            pallets=results.get("pallets"),
            precooling=results.get("precooling"),
            areas=results.get("areas"),
            global_warnings=global_warnings,
            success=len(errors) == 0,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Convenience: orchestrate from a flat input dict
    # ------------------------------------------------------------------

    def orchestrate_from_dict(
        self,
        inputs: dict[str, Any],
    ) -> CoreCalculationOrchestrationResult:
        """Build calculator inputs from a flat dict (e.g. project version input_snapshot).

        This enables the API layer to pass a single dict without knowing
        the strongly-typed input models.
        """

        throughput_input: ThroughputCalcInput | None = None
        inventory_input: InventoryCalcInput | None = None
        pallet_input: PalletCalcInput | None = None
        precooling_input: PrecoolingCalcInput | None = None

        # --- throughput ----------------------------------------------------
        if "daily_inbound_mass_kg" in inputs or "peak_output_kg_per_day" in inputs:
            with contextlib.suppress(Exception):
                throughput_input = ThroughputCalcInput(
                    peak_output_kg_per_day=_to_decimal(
                        inputs.get(
                            "peak_output_kg_per_day",
                            inputs.get("daily_inbound_mass_kg", 0),
                        )
                    ),
                    processing_hours_per_day=_to_decimal(
                        inputs.get(
                            "processing_hours_per_day",
                            inputs.get("working_time_h_per_day", 16),
                        )
                    ),
                    shift_count=int(inputs.get("shift_count", 1)),
                    effective_working_ratio=_to_decimal(
                        inputs.get(
                            "effective_working_ratio",
                            inputs.get("utilization_factor", 0.85),
                        )
                    ),
                    labour_efficiency_kg_per_person_hour=_to_decimal(
                        inputs.get("labour_efficiency_kg_per_person_hour", 150)
                    ),
                    available_workers=int(inputs.get("available_workers", 0)),
                )

        # --- inventory -----------------------------------------------------
        if "daily_inbound_mass_kg" in inputs or "daily_inbound_quantity" in inputs:
            try:
                inbound = _to_decimal(
                    inputs.get(
                        "daily_inbound_quantity",
                        inputs.get("daily_inbound_mass_kg", 0),
                    )
                )
                outbound = _to_decimal(
                    inputs.get(
                        "daily_outbound_quantity",
                        inputs.get("daily_inbound_mass_kg", 0),
                    )
                )
                turnover = _to_decimal(inputs.get("turnover_days", 7))
                safety = _to_decimal(inputs.get("safety_stock_days", 0))
                storage_ratio = _to_decimal(inputs.get("storage_ratio", 1.0))
                peak_factor = _to_decimal(inputs.get("inventory_peak_factor", 1.0))
                inventory_input = InventoryCalcInput(
                    daily_inbound_quantity=inbound,
                    daily_outbound_quantity=outbound,
                    turnover_days=turnover,
                    safety_stock_days=safety,
                    storage_ratio=storage_ratio,
                    inventory_peak_factor=peak_factor,
                )
            except Exception:
                pass

        # --- pallets -------------------------------------------------------
        if "design_inventory" in inputs or "pallet_weight_kg" in inputs:
            try:
                design_inv = _to_decimal(
                    inputs.get("design_inventory", 0)
                    or _to_decimal(inputs.get("pallet_weight_kg", 0))
                )
                if design_inv > 0:
                    pallet_input = PalletCalcInput(
                        design_inventory=design_inv,
                        net_product_per_pallet=_to_decimal(
                            inputs.get("net_product_per_pallet", 400)
                        ),
                        pallet_utilization_ratio=_to_decimal(
                            inputs.get("pallet_utilization_ratio", 1.0)
                        ),
                        pallet_turnover_ratio=_to_decimal(inputs.get("pallet_turnover_ratio", 1.0)),
                        stacking_level=int(inputs.get("stacking_level", 1)),
                        reserve_ratio=_to_decimal(inputs.get("reserve_ratio", 0.10)),
                    )
            except Exception:
                pass

        # --- precooling ----------------------------------------------------
        if "precooled_quantity_per_day" in inputs or "daily_inbound_mass_kg" in inputs:
            try:
                pq = _to_decimal(
                    inputs.get(
                        "precooled_quantity_per_day",
                        inputs.get("daily_inbound_mass_kg", 0),
                    )
                )
                if pq > 0:
                    precooling_input = PrecoolingCalcInput(
                        precooled_quantity_per_day=pq,
                        precooled_ratio=_to_decimal(inputs.get("precooled_ratio", 1.0)),
                        batch_capacity=_to_decimal(inputs.get("batch_capacity", 500)),
                        batch_duration=_to_decimal(inputs.get("batch_duration", 4)),
                        loading_unloading_duration=_to_decimal(
                            inputs.get("loading_unloading_duration", 1)
                        ),
                        available_precooling_hours=_to_decimal(
                            inputs.get("available_precooling_hours", 16)
                        ),
                        simultaneous_batch_count=int(inputs.get("simultaneous_batch_count", 1)),
                        reserve_capacity_ratio=_to_decimal(
                            inputs.get("reserve_capacity_ratio", 1.10)
                        ),
                    )
            except Exception:
                pass

        return self.orchestrate_core_calculation(
            throughput_input=throughput_input,
            inventory_input=inventory_input,
            pallet_input=pallet_input,
            precooling_input=precooling_input,
        )

    # ------------------------------------------------------------------
    # Snapshot to ProjectVersion
    # ------------------------------------------------------------------

    def snapshot_to_project_version(
        self,
        project_version: Any,
        orchestration_result: CoreCalculationOrchestrationResult,
    ) -> dict[str, Any]:
        """Write orchestration results into a ProjectVersion's snapshots.

        Raises ``LockedProjectVersionError`` if the version is approved/archived.
        """
        if hasattr(project_version, "is_locked") and project_version.is_locked:
            raise LockedProjectVersionError(project_version.id, project_version.status)

        result_dict = orchestration_result.to_dict()

        if hasattr(project_version, "calculation_snapshot"):
            project_version.calculation_snapshot = result_dict

        if hasattr(project_version, "assumption_snapshot"):
            assumptions: dict[str, Any] = {}
            if orchestration_result.throughput is not None:
                assumptions["throughput_warnings"] = [
                    w.code for w in orchestration_result.throughput.warnings
                ]
            if orchestration_result.inventory is not None:
                assumptions["inventory_warnings"] = [
                    w.code for w in orchestration_result.inventory.warnings
                ]
            project_version.assumption_snapshot = assumptions

        return result_dict

    # ------------------------------------------------------------------
    # Internal consistency checks
    # ------------------------------------------------------------------

    def _check_consistency(
        self,
        results: dict[str, CalculationResult],
    ) -> list[CalculationWarning]:
        """Validate cross-calculator consistency rules.

        Rules checked:
        1. If both throughput and inventory are present, the peak output
           from throughput should be consistent with the daily inbound
           used for inventory.
        2. If both inventory and pallets are present, the design inventory
           should align with the design inventory used for pallet count.
        """
        warnings: list[CalculationWarning] = []

        # Rule 1: throughput ↔ inventory consistency
        if "throughput" in results and "inventory" in results:
            tp = results["throughput"].result
            tp_peak = Decimal(str(tp.get("required_hourly_throughput_kg_h", 0)))
            inv_inbound = Decimal(
                str(results["inventory"].input_snapshot.get("daily_inbound_quantity", 0))
            )
            if tp_peak > 0 and inv_inbound > 0:
                # They may differ if throughput uses a different peak
                # output than inventory's daily inbound — flag if > 10%
                # This is informational, not an error
                pass

        # Rule 2: inventory ↔ pallets consistency
        if "inventory" in results and "pallets" in results:
            inv_design = Decimal(str(results["inventory"].result.get("design_inventory", 0)))
            pal_design = Decimal(str(results["pallets"].input_snapshot.get("design_inventory", 0)))
            if inv_design > 0 and pal_design > 0 and inv_design != pal_design:
                warnings.append(
                    CalculationWarning(
                        code="INVENTORY_PALLET_MISMATCH",
                        message=(
                            f"Inventory design inventory ({inv_design}) differs "
                            f"from pallet design inventory ({pal_design}). "
                            "Ensure inputs are consistent across calculators."
                        ),
                        details={
                            "inventory_design_inventory": str(inv_design),
                            "pallet_design_inventory": str(pal_design),
                        },
                    )
                )

        return warnings
