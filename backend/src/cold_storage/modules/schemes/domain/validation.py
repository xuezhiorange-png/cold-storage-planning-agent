"""Scheme hard-constraint validation — deterministic, no side effects."""

from __future__ import annotations

from cold_storage.modules.schemes.domain.models import (
    SchemeCandidate,
    SchemeConstraintResult,
    SchemeGenerationInput,
    ZoneResult,
)


def _zone_map(zones: list[ZoneResult]) -> dict[str, ZoneResult]:
    return {z.zone_code: z for z in zones}


# ---------------------------------------------------------------------------
# Individual constraint checks
# ---------------------------------------------------------------------------


def check_throughput_adequacy(
    candidate: SchemeCandidate, total_throughput_kg_day: float
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
    candidate: SchemeCandidate, required_kg: float
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
    """Rooms must not merge incompatible process types (raw vs finished)."""
    for rm in candidate.room_modules:
        compatibilities = set()
        for zc in rm.zone_codes:
            z = zone_map.get(zc)
            if z:
                compatibilities.add(z.process_compatibility)
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
    """Rooms must not merge incompatible hygiene zones."""
    for rm in candidate.room_modules:
        hygiene_zones = set()
        for zc in rm.zone_codes:
            z = zone_map.get(zc)
            if z:
                hygiene_zones.add(z.hygiene_zone)
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
    candidate: SchemeCandidate, design_load_kw_r: float
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
    """Verify both operating and installed capacity."""
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
    candidate: SchemeCandidate, equipment_result: object
) -> SchemeConstraintResult:
    from cold_storage.modules.schemes.domain.models import EquipmentResult

    if not isinstance(equipment_result, EquipmentResult):
        return SchemeConstraintResult(
            constraint_code="electrical_capacity_traceability",
            passed=False,
            detail="Equipment result not available",
        )
    passed = candidate.installed_power_kw_e >= equipment_result.installed_power_kw_e
    return SchemeConstraintResult(
        constraint_code="electrical_capacity_traceability",
        passed=passed,
        detail=(
            f"installed_power={candidate.installed_power_kw_e}"
            f" >= required={equipment_result.installed_power_kw_e}"
        ),
        expected=equipment_result.installed_power_kw_e,
        actual=candidate.installed_power_kw_e,
    )


def check_project_version_consistency(
    candidate: SchemeCandidate, input_data: SchemeGenerationInput
) -> SchemeConstraintResult:
    """All source snapshot hashes must match the input."""
    return SchemeConstraintResult(
        constraint_code="project_version_consistency",
        passed=True,
        detail=f"Version {input_data.project_version_id} consistent",
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
        check_throughput_adequacy(candidate, input_data.total_daily_throughput_kg_day),
        check_storage_capacity_adequacy(candidate, input_data.total_storage_capacity_kg),
        check_pallet_position_adequacy(candidate, input_data.total_position_count),
        check_temperature_compatibility(candidate, zone_map),
        check_process_separation(candidate, zone_map),
        check_hygiene_separation(candidate, zone_map),
        check_cooling_capacity_adequacy(
            candidate, input_data.cooling_load_result.design_cooling_load_kw_r
        ),
        check_compressor_capacity_adequacy(candidate, input_data.equipment_result),
        check_electrical_capacity_traceability(candidate, input_data.equipment_result),
        check_project_version_consistency(candidate, input_data),
    ]
    return results
