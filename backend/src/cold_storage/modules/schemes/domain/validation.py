"""Scheme hard-constraint validation — deterministic, no side effects."""

from __future__ import annotations

from decimal import Decimal

from cold_storage.modules.schemes.domain.models import (
    SchemeCandidate,
    SchemeConstraintResult,
    SchemeGenerationInput,
    ZoneResult,
)

# Calculation types expected in source_calculation_ids / source_snapshot_hashes
_REQUIRED_CALCULATION_TYPES = frozenset(
    {
        "zone",
        "investment",
        "cooling_load",
        "equipment",
    }
)


def _zone_map(zones: list[ZoneResult]) -> dict[str, ZoneResult]:
    return {z.zone_code: z for z in zones}


# ---------------------------------------------------------------------------
# Individual constraint checks
# ---------------------------------------------------------------------------


def check_throughput_adequacy(
    candidate: SchemeCandidate, total_throughput_kg_day: float | Decimal
) -> SchemeConstraintResult:
    passed = candidate.daily_throughput_kg_day >= total_throughput_kg_day
    return SchemeConstraintResult(
        constraint_code="throughput_adequacy",
        passed=passed,
        detail=(
            f"daily_throughput={candidate.daily_throughput_kg_day}"
            f" >= required={total_throughput_kg_day}"
        ),
        expected=total_throughput_kg_day,
        actual=candidate.daily_throughput_kg_day,
    )


def check_storage_capacity_adequacy(
    candidate: SchemeCandidate, required_kg: float | Decimal
) -> SchemeConstraintResult:
    total = sum(r.storage_capacity_kg for r in candidate.room_modules)
    passed = total >= required_kg
    return SchemeConstraintResult(
        constraint_code="storage_capacity_adequacy",
        passed=passed,
        detail=f"storage={total} >= required={required_kg}",
        expected=required_kg,
        actual=total,
    )


def check_pallet_position_adequacy(
    candidate: SchemeCandidate, required_positions: int
) -> SchemeConstraintResult:
    total = sum(r.position_count for r in candidate.room_modules)
    passed = total >= required_positions
    return SchemeConstraintResult(
        constraint_code="pallet_position_adequacy",
        passed=passed,
        detail=f"positions={total} >= required={required_positions}",
        expected=required_positions,
        actual=total,
    )


def check_temperature_compatibility(
    candidate: SchemeCandidate, zone_map: dict[str, ZoneResult]
) -> SchemeConstraintResult:
    """Rooms must not contain incompatible temperature levels."""
    for rm in candidate.room_modules:
        levels_in_room = set()
        for zc in rm.zone_codes:
            z = zone_map.get(zc)
            if z:
                levels_in_room.add(z.temperature_level)
        if len(levels_in_room) > 1:
            return SchemeConstraintResult(
                constraint_code="temperature_compatibility",
                passed=False,
                detail=f"Room '{rm.room_code}' contains mixed temperature levels: {levels_in_room}",
                expected="single temperature level per room",
                actual=list(levels_in_room),
            )
    return SchemeConstraintResult(
        constraint_code="temperature_compatibility",
        passed=True,
        detail="All rooms have compatible temperature levels",
    )


def check_process_separation(
    candidate: SchemeCandidate, zone_map: dict[str, ZoneResult]
) -> SchemeConstraintResult:
    """Rooms must not merge incompatible process types (raw vs finished).

    P0-5: Skipped (always passes) when any zone has process_compatibility=None.
    """
    for rm in candidate.room_modules:
        compatibilities: set[str] = set()
        for zc in rm.zone_codes:
            z = zone_map.get(zc)
            if z and z.process_compatibility is not None:
                compatibilities.add(z.process_compatibility)
        # Skip check if any zone lacks process_compatibility data
        if not compatibilities:
            continue
        if "raw" in compatibilities and "finished" in compatibilities:
            return SchemeConstraintResult(
                constraint_code="process_separation",
                passed=False,
                detail=f"Room '{rm.room_code}' merges raw and finished process types",
                expected="process type separation",
                actual=list(compatibilities),
            )
    return SchemeConstraintResult(
        constraint_code="process_separation",
        passed=True,
        detail="Process separation maintained",
    )


def check_hygiene_separation(
    candidate: SchemeCandidate, zone_map: dict[str, ZoneResult]
) -> SchemeConstraintResult:
    """Rooms must not merge incompatible hygiene zones.

    P0-5: Skipped (always passes) when any zone has hygiene_zone=None.
    """
    for rm in candidate.room_modules:
        hygiene_zones: set[str] = set()
        for zc in rm.zone_codes:
            z = zone_map.get(zc)
            if z and z.hygiene_zone is not None:
                hygiene_zones.add(z.hygiene_zone)
        # Skip check if any zone lacks hygiene_zone data
        if not hygiene_zones:
            continue
        if len(hygiene_zones) > 1:
            return SchemeConstraintResult(
                constraint_code="hygiene_separation",
                passed=False,
                detail=f"Room '{rm.room_code}' merges hygiene zones: {hygiene_zones}",
                expected="hygiene zone separation",
                actual=list(hygiene_zones),
            )
    return SchemeConstraintResult(
        constraint_code="hygiene_separation",
        passed=True,
        detail="Hygiene separation maintained",
    )


def check_cooling_capacity_adequacy(
    candidate: SchemeCandidate, design_load_kw_r: float | Decimal
) -> SchemeConstraintResult:
    passed = candidate.design_cooling_load_kw_r >= design_load_kw_r
    return SchemeConstraintResult(
        constraint_code="cooling_capacity_adequacy",
        passed=passed,
        detail=f"cooling={candidate.design_cooling_load_kw_r} >= design_load={design_load_kw_r}",
        expected=design_load_kw_r,
        actual=candidate.design_cooling_load_kw_r,
    )


def check_compressor_capacity_adequacy(
    candidate: SchemeCandidate, equipment_result: object
) -> SchemeConstraintResult:
    """Verify both operating and installed capacity.

    P0-5: When equipment_result.compressor_installed_capacity_kw_r is None,
    the installed-capacity check is skipped (only operating check applies).
    """
    from cold_storage.modules.schemes.domain.models import EquipmentResult

    if not isinstance(equipment_result, EquipmentResult):
        return SchemeConstraintResult(
            constraint_code="compressor_capacity_adequacy",
            passed=False,
            detail="Equipment result not available",
            expected="EquipmentResult",
            actual=type(equipment_result).__name__,
        )
    op_ok = (
        candidate.compressor_installed_capacity_kw_r
        >= equipment_result.compressor_operating_capacity_kw_r
    )
    installed_ok = True
    if equipment_result.compressor_installed_capacity_kw_r is not None:
        installed_ok = (
            candidate.compressor_installed_capacity_kw_r
            >= equipment_result.compressor_installed_capacity_kw_r
        )
    passed = op_ok and installed_ok
    return SchemeConstraintResult(
        constraint_code="compressor_capacity_adequacy",
        passed=passed,
        detail=(
            f"installed={candidate.compressor_installed_capacity_kw_r}"
            f" >= operating={equipment_result.compressor_operating_capacity_kw_r}"
            f" and installed_cap={equipment_result.compressor_installed_capacity_kw_r}"
        ),
        expected={
            "operating": equipment_result.compressor_operating_capacity_kw_r,
            "installed": equipment_result.compressor_installed_capacity_kw_r,
        },
        actual=candidate.compressor_installed_capacity_kw_r,
    )


def check_electrical_capacity_traceability(
    candidate: SchemeCandidate, power_result: object | None
) -> SchemeConstraintResult:
    """Verify installed_power_kw_e > 0 using Power authority.

    The PowerResult is the sole authority for whole-project installed power.
    Equipment.installed_power_kw_e is NOT used for this check.
    """
    from cold_storage.modules.schemes.domain.models import PowerResult

    if not isinstance(power_result, PowerResult):
        return SchemeConstraintResult(
            constraint_code="electrical_capacity_traceability",
            passed=False,
            detail="Power result not available — cannot verify installed power",
            expected="PowerResult",
            actual=type(power_result).__name__ if power_result is not None else "None",
        )
    passed = candidate.installed_power_kw_e > 0
    return SchemeConstraintResult(
        constraint_code="electrical_capacity_traceability",
        passed=passed,
        detail=(
            f"installed_power={candidate.installed_power_kw_e}"
            f" > 0 (from PowerResult.total_installed_power_kw_e"
            f"={power_result.total_installed_power_kw_e})"
        ),
        expected="installed_power_kw_e > 0",
        actual=candidate.installed_power_kw_e,
    )


def check_project_version_consistency(
    candidate: SchemeCandidate, input_data: SchemeGenerationInput
) -> SchemeConstraintResult:
    """Verify input_data source calculations are internally consistent.

    Checks:
    - All required calculation types (zone, investment, cooling_load, equipment)
      are present in source_calculation_ids.
    - All required calculation types are present in source_snapshot_hashes.
    - All source snapshot hashes are non-empty (basic integrity check).
    - All source calculation IDs are non-empty strings.
    """
    errors: list[str] = []

    # --- source_calculation_ids: required keys and non-empty values ---
    missing_calc_ids = _REQUIRED_CALCULATION_TYPES - set(input_data.source_calculation_ids)
    if missing_calc_ids:
        errors.append(
            f"missing calculation types in source_calculation_ids: {sorted(missing_calc_ids)}"
        )

    empty_calc_ids = {k for k, v in input_data.source_calculation_ids.items() if not v}
    if empty_calc_ids:
        errors.append(f"empty calculation IDs: {sorted(empty_calc_ids)}")

    # --- source_snapshot_hashes: required keys and non-empty values ---
    missing_hashes = _REQUIRED_CALCULATION_TYPES - set(input_data.source_snapshot_hashes)
    if missing_hashes:
        errors.append(
            f"missing calculation types in source_snapshot_hashes: {sorted(missing_hashes)}"
        )

    empty_hashes = {k for k, v in input_data.source_snapshot_hashes.items() if not v}
    if empty_hashes:
        errors.append(f"empty snapshot hashes: {sorted(empty_hashes)}")

    if errors:
        return SchemeConstraintResult(
            constraint_code="project_version_consistency",
            passed=False,
            detail="; ".join(errors),
            expected="all required calculation types present with non-empty IDs and hashes",
            actual={
                "source_calculation_ids_keys": sorted(input_data.source_calculation_ids.keys()),
                "source_snapshot_hashes_keys": sorted(input_data.source_snapshot_hashes.keys()),
            },
        )

    return SchemeConstraintResult(
        constraint_code="project_version_consistency",
        passed=True,
        detail=f"Version {input_data.project_version_id} consistent",
    )


def check_compressor_operating_adequacy(
    candidate: SchemeCandidate, design_cooling_load_kw_r: Decimal
) -> SchemeConstraintResult:
    """Total operating compressor capacity must cover the design cooling load."""
    passed = candidate.compressor_operating_capacity_kw_r >= design_cooling_load_kw_r
    return SchemeConstraintResult(
        constraint_code="compressor_operating_adequacy",
        passed=passed,
        detail=(
            f"operating_capacity={candidate.compressor_operating_capacity_kw_r}"
            f" >= design_cooling_load={design_cooling_load_kw_r}"
        ),
        expected=design_cooling_load_kw_r,
        actual=candidate.compressor_operating_capacity_kw_r,
    )


def check_compressor_installed_adequacy(
    candidate: SchemeCandidate,
) -> SchemeConstraintResult:
    """Total installed compressor capacity must cover the operating capacity."""
    passed = (
        candidate.compressor_installed_capacity_kw_r >= candidate.compressor_operating_capacity_kw_r
    )
    return SchemeConstraintResult(
        constraint_code="compressor_installed_adequacy",
        passed=passed,
        detail=(
            f"installed_capacity={candidate.compressor_installed_capacity_kw_r}"
            f" >= operating_capacity={candidate.compressor_operating_capacity_kw_r}"
        ),
        expected=candidate.compressor_operating_capacity_kw_r,
        actual=candidate.compressor_installed_capacity_kw_r,
    )


def check_zone_code_existence(
    candidate: SchemeCandidate, zone_map: dict[str, ZoneResult]
) -> SchemeConstraintResult:
    """All zone_codes referenced by room_modules must exist in zone_results."""
    available_zones = set(zone_map.keys())
    missing: list[str] = []
    for rm in candidate.room_modules:
        for zc in rm.zone_codes:
            if zc not in available_zones:
                missing.append(f"{rm.room_code}->{zc}")

    if missing:
        return SchemeConstraintResult(
            constraint_code="zone_code_existence",
            passed=False,
            detail=f"Zone codes not found in zone_results: {missing}",
            expected="all zone_codes exist in zone_results",
            actual=sorted(missing),
        )

    return SchemeConstraintResult(
        constraint_code="zone_code_existence",
        passed=True,
        detail="All zone codes exist in zone_results",
    )


# ---------------------------------------------------------------------------
# Run all constraints
# ---------------------------------------------------------------------------


def validate_candidate(
    candidate: SchemeCandidate,
    input_data: SchemeGenerationInput,
    zone_map: dict[str, ZoneResult],
) -> list[SchemeConstraintResult]:
    """Run all hard constraints on a candidate. Returns list of results."""
    results = [
        # --- Capacity adequacy ---
        check_throughput_adequacy(candidate, input_data.total_daily_throughput_kg_day),
        check_storage_capacity_adequacy(candidate, input_data.total_storage_capacity_kg),
        check_pallet_position_adequacy(candidate, input_data.total_position_count),
        # --- Compatibility ---
        check_temperature_compatibility(candidate, zone_map),
        check_process_separation(candidate, zone_map),
        check_hygiene_separation(candidate, zone_map),
        # --- Cooling / equipment ---
        check_cooling_capacity_adequacy(
            candidate, input_data.cooling_load_result.design_cooling_load_kw_r
        ),
        check_compressor_operating_adequacy(
            candidate, input_data.cooling_load_result.design_cooling_load_kw_r
        ),
        check_compressor_installed_adequacy(candidate),
        check_compressor_capacity_adequacy(candidate, input_data.equipment_result),
        check_electrical_capacity_traceability(candidate, input_data.power_result),
        # --- Zone existence ---
        check_zone_code_existence(candidate, zone_map),
        # --- Version / provenance ---
        check_project_version_consistency(candidate, input_data),
    ]
    return results
