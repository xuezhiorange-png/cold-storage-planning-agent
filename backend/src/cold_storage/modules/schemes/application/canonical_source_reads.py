"""Anti-corruption helpers for scheme canonical source reads (V0.5 P3)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

from cold_storage.modules.orchestration.application.canonical_calculation_index import (
    index_canonical_calculation_records,
)
from cold_storage.modules.orchestration.domain.consumer_bindings import (
    CANONICAL_CALCULATOR_NAMES,
    CANONICAL_STAGE_ORDER,
    STAGE_TO_CALCULATOR_NAME,
)
from cold_storage.modules.schemes.application.source_domain_mapping import (
    map_cooling_load_snapshot,
    map_equipment_snapshot,
    map_investment_snapshot,
    map_power_snapshot,
    map_zone_snapshot,
)
from cold_storage.modules.schemes.domain.errors import (
    SourceCalculationMissingError,
    SourceSnapshotInvalidError,
    VersionConflictError,
)
from cold_storage.modules.schemes.domain.models import (
    CoolingLoadResult,
    EquipmentResult,
    InvestmentResult,
    PowerResult,
    ZoneResult,
)


@dataclass(frozen=True)
class CanonicalSchemeSourceBundle:
    """Validated canonical source rows keyed by orchestration stage."""

    project_id: str
    project_version_id: str
    calculations_by_stage: dict[str, Any]
    source_calculation_ids: dict[str, str]
    source_snapshot_hashes: dict[str, str]


def _canonical_json(obj: object) -> str:
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _per_calc_hash(snapshot: dict[str, object]) -> str:
    return sha256(_canonical_json(snapshot).encode("utf-8")).hexdigest()


def require_canonical_scheme_sources(
    records: list[Any],
    *,
    project_id: str,
    project_version_id: str,
) -> CanonicalSchemeSourceBundle:
    for record in records:
        if str(record.project_id) != project_id:
            raise VersionConflictError(
                f"calculation run {record.id!r} project_id mismatch for {project_id!r}"
            )
        if str(record.project_version_id) != project_version_id:
            raise VersionConflictError(
                f"calculation run {record.id!r} project_version_id mismatch for "
                f"{project_version_id!r}"
            )
    indexed = index_canonical_calculation_records(
        records,
        project_id=project_id,
        project_version_id=project_version_id,
    )
    for stage in CANONICAL_STAGE_ORDER:
        calculator_name = STAGE_TO_CALCULATOR_NAME[stage]
        if stage not in indexed:
            raise SourceCalculationMissingError(calculator_name)

    source_calc_ids = {stage: str(indexed[stage].id) for stage in CANONICAL_STAGE_ORDER}
    source_snapshot_hashes: dict[str, str] = {}
    for stage in CANONICAL_STAGE_ORDER:
        record = indexed[stage]
        persisted_hash = record.result_hash
        if persisted_hash:
            source_snapshot_hashes[stage] = str(persisted_hash)
        else:
            snapshot = record.result_snapshot
            source_snapshot_hashes[stage] = _per_calc_hash(
                snapshot if isinstance(snapshot, dict) else {}
            )
    return CanonicalSchemeSourceBundle(
        project_id=project_id,
        project_version_id=project_version_id,
        calculations_by_stage=indexed,
        source_calculation_ids=source_calc_ids,
        source_snapshot_hashes=source_snapshot_hashes,
    )


def _to_decimal(val: object) -> Decimal:
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise SourceSnapshotInvalidError(f"invalid decimal value: {val!r}") from exc


def _legacy_zone_results(snapshot: dict[str, Any]) -> list[ZoneResult]:
    zone_snapshots_raw = snapshot.get("zone_results", [])
    if not isinstance(zone_snapshots_raw, list) or not zone_snapshots_raw:
        raise SourceSnapshotInvalidError("Missing zone_results in zone snapshot")
    results: list[ZoneResult] = []
    for zone in zone_snapshots_raw:
        if not isinstance(zone, dict):
            raise SourceSnapshotInvalidError("zone_results entries must be objects")
        results.append(
            ZoneResult(
                zone_code=str(zone["zone_code"]),
                zone_name=str(zone["zone_name"]),
                temperature_level=str(zone["temperature_level"]),
                area_m2=_to_decimal(zone["area_m2"]),
                position_count=int(str(zone["position_count"])),
                storage_capacity_kg=_to_decimal(zone["storage_capacity_kg"]),
                process_compatibility=(
                    str(zone["process_compatibility"])
                    if zone.get("process_compatibility") is not None
                    else None
                ),
                hygiene_zone=(
                    str(zone["hygiene_zone"]) if zone.get("hygiene_zone") is not None else None
                ),
            )
        )
    return results


def _legacy_cooling_load(snapshot: dict[str, Any]) -> CoolingLoadResult:
    latent_raw = snapshot.get("latent_load_kw_r")
    return CoolingLoadResult(
        design_cooling_load_kw_r=_to_decimal(snapshot["design_cooling_load_kw_r"]),
        sensible_load_kw_r=_to_decimal(snapshot["sensible_load_kw_r"]),
        infiltration_load_kw_r=_to_decimal(snapshot["infiltration_load_kw_r"]),
        latent_load_kw_r=_to_decimal(latent_raw) if latent_raw is not None else None,
    )


def _legacy_equipment(snapshot: dict[str, Any]) -> EquipmentResult:
    installed_raw = snapshot.get("compressor_installed_capacity_kw_r")
    operating = _to_decimal(snapshot["compressor_operating_capacity_kw_r"])
    installed = _to_decimal(installed_raw) if installed_raw is not None else None
    standby = (installed or Decimal("0")) - operating
    return EquipmentResult(
        compressor_operating_capacity_kw_r=operating,
        compressor_installed_capacity_kw_r=installed,
        compressor_standby_capacity_kw_r=standby,
        condenser_heat_rejection_kw=_to_decimal(snapshot["condenser_heat_rejection_kw"]),
        installed_power_kw_e=_to_decimal(snapshot["installed_power_kw_e"]),
    )


def _legacy_investment(snapshot: dict[str, Any]) -> InvestmentResult:
    total = _to_decimal(snapshot["total_investment_cny"])
    zone_investments = {
        str(key): _to_decimal(value)
        for key, value in (snapshot.get("zone_investments") or {}).items()
    }
    return InvestmentResult(total_investment_cny=total, zone_investments=zone_investments)


def parse_zone_results(snapshot: dict[str, Any]) -> list[ZoneResult]:
    if "zones" in snapshot:
        return map_zone_snapshot(snapshot)
    return _legacy_zone_results(snapshot)


def parse_cooling_load_result(snapshot: dict[str, Any]) -> CoolingLoadResult:
    if "total_cooling_load_kw" in snapshot:
        return map_cooling_load_snapshot(snapshot)
    return _legacy_cooling_load(snapshot)


def parse_equipment_result(snapshot: dict[str, Any]) -> EquipmentResult:
    if "compressor_operating_capacity_kw" in snapshot:
        return map_equipment_snapshot(snapshot)
    return _legacy_equipment(snapshot)


def parse_investment_result(snapshot: dict[str, Any]) -> InvestmentResult:
    if "items" in snapshot:
        return map_investment_snapshot(snapshot)
    return _legacy_investment(snapshot)


def parse_power_result(snapshot: dict[str, Any]) -> PowerResult:
    return map_power_snapshot(snapshot)


def required_canonical_calculator_names() -> frozenset[str]:
    return CANONICAL_CALCULATOR_NAMES
