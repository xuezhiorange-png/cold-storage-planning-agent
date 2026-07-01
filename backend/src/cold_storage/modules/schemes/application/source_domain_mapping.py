"""Map five verified typed source snapshots to SchemeGenerationInput.

Power is the sole authority for whole-project installed power.
Equipment.installed_power_kw_e must NOT be used for whole-project power.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from cold_storage.modules.schemes.application.production_ports import (
    VerifiedSourceMapping,
)
from cold_storage.modules.schemes.domain.models import (
    CoolingLoadResult,
    EquipmentResult,
    InvestmentResult,
    SchemeGenerationInput,
    ZoneResult,
)

# ── Power authority ────────────────────────────────────────────────────────

POWER_AUTHORITY_FIELD: str = "total_installed_power_kw_e"


class PowerAuthorityError(Exception):
    """Raised when Power source is missing or invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "power_authority_error"


class EquipmentFallbackRejectedError(Exception):
    """Raised when Equipment.installed_power_kw_e is incorrectly used."""

    def __init__(self) -> None:
        super().__init__(
            "Equipment.installed_power_kw_e must NOT be used as "
            "whole-project installed power. Use PowerSourceSnapshotV1."
            "total_installed_power_kw_e instead."
        )
        self.code = "equipment_fallback_rejected"


# ── Snapshot → Domain mapping ──────────────────────────────────────────────


def _safe_decimal(val: Any, field_name: str) -> Decimal:
    """Convert a value to Decimal, raising on failure."""
    if val is None:
        return Decimal(0)
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PowerAuthorityError(
            f"Cannot convert {field_name!r} value {val!r} to Decimal: {exc}"
        ) from exc


def map_zone_snapshot(snap: dict[str, Any]) -> ZoneResult:
    """Map zone result snapshot to domain ZoneResult."""
    zones = snap.get("zones", [])
    total_area = sum(float(z.get("required_area_m2", 0) or 0) for z in zones)
    total_positions = sum(z.get("position_count", 0) or 0 for z in zones)
    total_capacity = sum(float(z.get("design_storage_mass_kg", 0) or 0) for z in zones)
    return ZoneResult(
        zone_code="ALL",
        zone_name="All Zones",
        temperature_level=zones[0].get("temperature_band", "") if zones else "",
        area_m2=total_area,
        position_count=total_positions,
        storage_capacity_kg=total_capacity,
        process_compatibility="mixed",
        hygiene_zone="standard",
    )


def map_cooling_load_snapshot(snap: dict[str, Any]) -> CoolingLoadResult:
    """Map cooling load result snapshot to domain CoolingLoadResult."""
    return CoolingLoadResult(
        design_cooling_load_kw_r=_safe_decimal(
            snap.get("total_cooling_load_kw", 0), "total_cooling_load_kw"
        ),
        sensible_heat_load_kw_r=_safe_decimal(
            snap.get("product_sensible_heat_load_kw", 0),
            "product_sensible_heat_load_kw",
        ),
        latent_heat_load_kw_r=_safe_decimal(0, "latent_heat_load_kw_r"),
        infiltration_load_kw_r=_safe_decimal(
            snap.get("infiltration_load_kw", 0), "infiltration_load_kw"
        ),
    )


def map_equipment_snapshot(snap: dict[str, Any]) -> EquipmentResult:
    """Map equipment result snapshot to domain EquipmentResult.

    Note: Equipment.installed_power_kw_e is NOT the whole-project power.
    It is only used for equipment-level capacity checks.
    """
    return EquipmentResult(
        compressor_operating_capacity_kw_r=_safe_decimal(
            snap.get("compressor_operating_capacity_kw", 0),
            "compressor_operating_capacity_kw",
        ),
        compressor_installed_capacity_kw_r=_safe_decimal(
            snap.get("compressor_operating_capacity_kw", 0),
            "compressor_operating_capacity_kw",
        ),
        compressor_standby_capacity_kw_r=_safe_decimal(
            snap.get("standby_capacity_kw", 0), "standby_capacity_kw"
        ),
        condenser_heat_rejection_kw_r=_safe_decimal(
            snap.get("condenser_heat_rejection_capacity_kw", 0),
            "condenser_heat_rejection_capacity_kw",
        ),
        installed_power_kw_e=_safe_decimal(0, "installed_power_kw_e"),
    )


def map_power_snapshot(snap: dict[str, Any]) -> Decimal:
    """Extract whole-project installed power from Power snapshot.

    This is the SOLE authority for installed power.
    Returns Decimal value of total_installed_power_kw_e.
    """
    val = snap.get(POWER_AUTHORITY_FIELD)
    if val is None:
        raise PowerAuthorityError(f"Power source missing {POWER_AUTHORITY_FIELD!r}")
    return _safe_decimal(val, POWER_AUTHORITY_FIELD)


def map_investment_snapshot(snap: dict[str, Any]) -> InvestmentResult:
    """Map investment result snapshot to domain InvestmentResult."""
    total = _safe_decimal(snap.get("total_investment_cny", 0), "total_investment_cny")
    items = snap.get("items", [])
    zone_investments = {}
    for item in items:
        name = item.get("item_name", "")
        amount = _safe_decimal(item.get("amount_cny", 0), "amount_cny")
        zone_investments[name] = amount
    return InvestmentResult(
        total_investment_cny=total,
        zone_investments=zone_investments,
    )


def map_source_to_generation_input(
    source: VerifiedSourceMapping,
    *,
    profile_codes: tuple[str, ...],
    profile_parameters: dict[str, dict[str, Any]],
    generator_version: str,
) -> SchemeGenerationInput:
    """Map verified source to SchemeGenerationInput.

    Power power is the sole installed-power authority.
    Equipment power is used only for equipment-level checks.
    """
    zone = map_zone_snapshot(source.zone_result_snapshot)
    cooling = map_cooling_load_snapshot(source.cooling_load_result_snapshot)
    equipment = map_equipment_snapshot(source.equipment_result_snapshot)
    investment = map_investment_snapshot(source.investment_result_snapshot)
    # Validate power is present (sole installed-power authority)
    map_power_snapshot(source.power_result_snapshot)

    # Compute totals from zone snapshot
    zone_snap = source.zone_result_snapshot
    zones = zone_snap.get("zones", [])
    total_daily_throughput = sum(float(z.get("daily_throughput_kg_day", 0) or 0) for z in zones)
    total_storage_capacity = sum(float(z.get("design_storage_mass_kg", 0) or 0) for z in zones)
    total_position_count = sum(z.get("position_count", 0) or 0 for z in zones)

    return SchemeGenerationInput(
        project_id=source.project_id,
        project_version_id=source.project_version_id,
        weight_set_id="",  # set by caller
        profile_codes=list(profile_codes),
        profile_parameters=dict(profile_parameters),
        source_calculation_ids={
            "zone": source.zone_calculation_id,
            "cooling_load": source.cooling_load_calculation_id,
            "equipment": source.equipment_calculation_id,
            "power": source.power_calculation_id,
            "investment": source.investment_calculation_id,
        },
        source_snapshot_hashes=source.per_calculation_result_hashes,
        zone_results=[zone],
        investment_result=investment,
        cooling_load_result=cooling,
        equipment_result=equipment,
        generator_version=generator_version,
        total_daily_throughput_kg_day=total_daily_throughput,
        total_storage_capacity_kg=total_storage_capacity,
        total_position_count=total_position_count,
    )
