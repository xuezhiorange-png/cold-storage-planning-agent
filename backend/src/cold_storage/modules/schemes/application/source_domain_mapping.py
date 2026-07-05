"""Map five verified typed source snapshots to SchemeGenerationInput.

Power is the sole authority for whole-project installed power.
Equipment.installed_power_kw_e must NOT be used for whole-project power.

P0-3: Fail-closed mapping — no _safe_decimal(), all required fields
validated with _require_decimal(), zones preserved as list, no binary float.

P0-4/P0-5: Decimal-only strict accumulation; optional fields
(process_compatibility, hygiene_zone, latent_load_kw, compressor_installed_capacity_kw)
pass through as None when absent from source snapshot.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from cold_storage.modules.schemes.application.production_ports import (
    VerifiedSourceMapping,
)
from cold_storage.modules.schemes.domain.errors import MappingError
from cold_storage.modules.schemes.domain.models import (
    CoolingLoadResult,
    EquipmentResult,
    InvestmentResult,
    PowerResult,
    SchemeGenerationInput,
    ZoneResult,
)

# ── Power authority ────────────────────────────────────────────────────────

POWER_AUTHORITY_FIELD: str = "total_installed_power_kw_e"


# ── Fail-closed helpers ────────────────────────────────────────────────────


def _require_decimal(val: Any, field_name: str) -> Decimal:
    """Convert a value to Decimal, raising MappingError if None, empty, or invalid.

    Fail-closed: never returns 0 for missing data.
    """
    if val is None:
        raise MappingError(
            code="missing_required_field",
            field=field_name,
            detail=f"Value for '{field_name}' is None — cannot proceed",
        )
    if isinstance(val, str) and val.strip() == "":
        raise MappingError(
            code="empty_required_field",
            field=field_name,
            detail=f"Value for '{field_name}' is empty string",
        )
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise MappingError(
            code="invalid_decimal",
            field=field_name,
            detail=f"Cannot convert {val!r} to Decimal: {exc}",
        ) from exc


def _require_string(val: Any, field_name: str) -> str:
    """Validate a value is a non-empty string, raising MappingError otherwise.

    Fail-closed: never returns "" for missing data.
    """
    if val is None:
        raise MappingError(
            code="missing_required_field",
            field=field_name,
            detail=f"Value for '{field_name}' is None",
        )
    if not isinstance(val, str) or val.strip() == "":
        raise MappingError(
            code="empty_required_field",
            field=field_name,
            detail=f"Value for '{field_name}' is empty or not a string",
        )
    return val


def _require_nonneg_int(val: Any, field_name: str) -> int:
    """Validate a value is a non-negative integer, raising MappingError otherwise."""
    if val is None:
        raise MappingError(
            code="missing_required_field",
            field=field_name,
            detail=f"Value for '{field_name}' is None",
        )
    try:
        ival = int(val)
    except (TypeError, ValueError) as exc:
        raise MappingError(
            code="invalid_integer",
            field=field_name,
            detail=f"Cannot convert {val!r} to int: {exc}",
        ) from exc
    if ival < 0:
        raise MappingError(
            code="negative_value",
            field=field_name,
            detail=f"Value for '{field_name}' is negative: {ival}",
        )
    return ival


# ── Snapshot → Domain mapping ──────────────────────────────────────────────


def map_zone_snapshot(snap: dict[str, Any]) -> list[ZoneResult]:
    """Map zone result snapshot to a list of domain ZoneResult objects.

    Preserves ALL zones in their original order — never merges into ALL.
    Each zone is returned individually with its original zone_code, zone_name,
    process_compatibility, and hygiene_zone.

    P0-5: zone_code, zone_name, temperature_band, position_count are required.
    process_compatibility and hygiene_zone are optional (None when absent).
    """
    zones = snap.get("zones", [])
    if not zones:
        raise MappingError(
            code="empty_zone_list",
            field="zones",
            detail="Zone snapshot contains no zones",
        )
    results: list[ZoneResult] = []
    for i, z in enumerate(zones):
        zone_code = _require_string(z.get("zone_code"), f"zones[{i}].zone_code")
        zone_name = _require_string(z.get("zone_name"), f"zones[{i}].zone_name")
        temperature_level = _require_string(
            z.get("temperature_band"), f"zones[{i}].temperature_band"
        )
        # Optional fields — None when absent
        process_compat = z.get("process_compatibility")
        hygiene = z.get("hygiene_zone")
        results.append(
            ZoneResult(
                zone_code=zone_code,
                zone_name=zone_name,
                temperature_level=temperature_level,
                area_m2=_require_decimal(z.get("required_area_m2"), f"zones[{i}].required_area_m2"),
                position_count=_require_nonneg_int(
                    z.get("position_count"), f"zones[{i}].position_count"
                ),
                storage_capacity_kg=_require_decimal(
                    z.get("design_storage_mass_kg"),
                    f"zones[{i}].design_storage_mass_kg",
                ),
                process_compatibility=str(process_compat) if process_compat is not None else None,
                hygiene_zone=str(hygiene) if hygiene is not None else None,
            )
        )
    return results


def map_cooling_load_snapshot(snap: dict[str, Any]) -> CoolingLoadResult:
    """Map cooling load result snapshot to domain CoolingLoadResult.

    Uses _require_decimal for required fields — fail-closed.
    P0-5: latent_load_kw is optional (None when absent from source).
    """
    latent_raw = snap.get("latent_load_kw")
    return CoolingLoadResult(
        design_cooling_load_kw_r=_require_decimal(
            snap.get("total_cooling_load_kw"), "total_cooling_load_kw"
        ),
        sensible_load_kw_r=_require_decimal(
            snap.get("product_sensible_heat_load_kw"),
            "product_sensible_heat_load_kw",
        ),
        infiltration_load_kw_r=_require_decimal(
            snap.get("infiltration_load_kw"), "infiltration_load_kw"
        ),
        latent_load_kw_r=(
            _require_decimal(latent_raw, "latent_load_kw") if latent_raw is not None else None
        ),
    )


def map_equipment_snapshot(snap: dict[str, Any]) -> EquipmentResult:
    """Map equipment result snapshot to domain EquipmentResult.

    Note: Equipment.installed_power_kw_e is set to Decimal(0) because
    power is NOT sourced from Equipment — the PowerResult is the sole
    authority for whole-project installed power.

    P0-5: compressor_installed_capacity_kw is optional (None when absent).
    """
    installed_raw = snap.get("compressor_installed_capacity_kw")
    return EquipmentResult(
        compressor_operating_capacity_kw_r=_require_decimal(
            snap.get("compressor_operating_capacity_kw"),
            "compressor_operating_capacity_kw",
        ),
        compressor_standby_capacity_kw_r=_require_decimal(
            snap.get("standby_capacity_kw"), "standby_capacity_kw"
        ),
        condenser_heat_rejection_kw=_require_decimal(
            snap.get("condenser_heat_rejection_capacity_kw"),
            "condenser_heat_rejection_capacity_kw",
        ),
        # Power is NOT from Equipment — use PowerResult instead
        installed_power_kw_e=Decimal("0"),
        compressor_installed_capacity_kw_r=(
            _require_decimal(installed_raw, "compressor_installed_capacity_kw")
            if installed_raw is not None
            else None
        ),
    )


def map_power_snapshot(snap: dict[str, Any]) -> PowerResult:
    """Extract whole-project installed power from Power snapshot.

    This is the SOLE authority for installed power.
    Returns a full PowerResult with all typed fields.
    """
    total_installed = _require_decimal(snap.get(POWER_AUTHORITY_FIELD), POWER_AUTHORITY_FIELD)
    total_demand = _require_decimal(
        snap.get("total_estimated_demand_kw"), "total_estimated_demand_kw"
    )
    equipment_rows = snap.get("equipment_rows", [])
    summary_rows = snap.get("summary_rows", [])
    items = snap.get("items", [])
    assumptions = snap.get("assumptions", [])
    return PowerResult(
        total_installed_power_kw_e=total_installed,
        total_estimated_demand_kw=total_demand,
        equipment_rows=equipment_rows,
        summary_rows=summary_rows,
        items=items,
        assumptions=assumptions,
    )


def map_investment_snapshot(snap: dict[str, Any]) -> InvestmentResult:
    """Map investment result snapshot to domain InvestmentResult.

    Uses _require_decimal for all fields — fail-closed.
    P0-5: item_name is required (non-empty string).
    """
    total = _require_decimal(snap.get("total_investment_cny"), "total_investment_cny")
    items = snap.get("items", [])
    zone_investments: dict[str, Decimal] = {}
    for idx, item in enumerate(items):
        name = _require_string(item.get("item_name"), f"items[{idx}].item_name")
        amount = _require_decimal(item.get("amount_cny"), f"items[{idx}].amount_cny")
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

    Power is the sole installed-power authority.
    Equipment power is used only for equipment-level checks.
    """
    zones = map_zone_snapshot(source.zone_result_snapshot)
    cooling = map_cooling_load_snapshot(source.cooling_load_result_snapshot)
    equipment = map_equipment_snapshot(source.equipment_result_snapshot)
    investment = map_investment_snapshot(source.investment_result_snapshot)
    # Validate power is present and extract full typed result (sole authority)
    power_result = map_power_snapshot(source.power_result_snapshot)

    # Compute totals from zone snapshot — strict Decimal accumulation, no float()
    zone_snap = source.zone_result_snapshot
    raw_zones = zone_snap.get("zones", [])
    total_daily_throughput = Decimal("0")
    total_storage_capacity = Decimal("0")
    total_position_count = 0
    for z in raw_zones:
        total_daily_throughput += _require_decimal(
            z.get("daily_throughput_kg_day"), "daily_throughput_kg_day"
        )
        total_storage_capacity += _require_decimal(
            z.get("design_storage_mass_kg"), "design_storage_mass_kg"
        )
        total_position_count += _require_nonneg_int(z.get("position_count"), "position_count")

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
        zone_results=zones,
        investment_result=investment,
        cooling_load_result=cooling,
        equipment_result=equipment,
        generator_version=generator_version,
        total_daily_throughput_kg_day=total_daily_throughput,
        total_storage_capacity_kg=total_storage_capacity,
        total_position_count=total_position_count,
        power_result=power_result,
    )
