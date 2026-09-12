"""Bind current canonical zone-plan metadata; no area/capacity recalculation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Context, Decimal, localcontext
from typing import Any

from cold_storage.modules.calculations.domain.zone_planning import (
    FORMULA_AUTHORITY,
    PALLET_PITCH_ALONG_WALL_M,
    PALLET_PITCH_DEPTH_M,
    RAW_AISLE_M,
    STORAGE_ONE_AISLE_M,
)
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.dimensioning import (
    IDENTITY,
    LayoutAuthorityError,
    ZoneDimensionProfileV1,
    canonical_hash,
    canonical_json,
    decimal_value,
    dimension_zone,
    profile_payload,
)

GRID_ZONES = (
    "raw_fruit_buffer",
    "finished_goods_room",
    "secondary_fruit_buffer",
    "frozen_fruit_room",
)


def upstream_profiles() -> tuple[ZoneDimensionProfileV1, ...]:
    """Only project the existing storage grid edges; no new engineering coefficients."""
    with localcontext(Context(prec=80)):
        return _bind_storage_grid_profiles()


def _bind_storage_grid_profiles() -> tuple[ZoneDimensionProfileV1, ...]:
    return tuple(
        ZoneDimensionProfileV1(
            profile_id=f"upstream-storage-grid-{code}",
            profile_version="1.0.0",
            zone_code=code,
            dimensioning_mode="UPSTREAM_GRID",
            width_m=Decimal(str(PALLET_PITCH_ALONG_WALL_M)),
            depth_m=Decimal(str(PALLET_PITCH_DEPTH_M)),
            width_offset_m=Decimal(str(RAW_AISLE_M)) * 2
            if code == "raw_fruit_buffer"
            else Decimal(0),
            depth_offset_m=Decimal(
                str(RAW_AISLE_M if code == "raw_fruit_buffer" else STORAGE_ONE_AISLE_M)
            ),
            source=(
                f"{FORMULA_AUTHORITY}:zone_planning."
                + (
                    "_pack_three_side_aisle_rectangle"
                    if code == "raw_fruit_buffer"
                    else "_pack_one_long_side_aisle_rectangle"
                )
                + "/ADR-044"
            ),
        )
        for code in GRID_ZONES
    )


@dataclass(frozen=True)
class ZoneDimensioningResultV1:
    """Immutable serialized result; mutable consumer copies cannot change its hash."""

    payload_json: str

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self.payload_json)
        return result

    def canonical_json(self) -> str:
        return self.payload_json

    @property
    def canonical_result_hash(self) -> str:
        return canonical_hash(self.to_dict())


def dimension_zones(
    zone_plan_snapshot: Mapping[str, Any] | None,
) -> ZoneDimensioningResultV1:
    """Backend snapshot only. Missing engineering authority is reported per zone.

    P1A deliberately exposes no arbitrary user profile injection route. Future
    approved profiles must be bound here by a separately reviewed revision.
    """
    if zone_plan_snapshot is None:
        raise LayoutAuthorityError("ZONE_PLAN_REQUIRED")
    if not isinstance(zone_plan_snapshot, Mapping):
        raise LayoutAuthorityError("ZONE_PLAN_IDENTITY_INVALID")
    if (
        zone_plan_snapshot.get("success") is not True
        or zone_plan_snapshot.get("calculator_name") != "cold_room_zone_plan"
        or zone_plan_snapshot.get("calculator_version") != "1.0.0"
    ):
        raise LayoutAuthorityError("ZONE_PLAN_IDENTITY_INVALID")
    result = zone_plan_snapshot.get("result")
    if not isinstance(result, Mapping):
        raise LayoutAuthorityError("ZONE_PLAN_IDENTITY_INVALID")
    params = result.get("planning_parameters")
    if not isinstance(params, Mapping) or params.get("formula_authority") != FORMULA_AUTHORITY:
        raise LayoutAuthorityError("ZONE_PLAN_IDENTITY_INVALID")
    zones = result.get("zones")
    if not isinstance(zones, list) or any(not isinstance(zone, Mapping) for zone in zones):
        raise LayoutAuthorityError("ZONE_PLAN_IDENTITY_INVALID")
    codes = [zone.get("zone_code") for zone in zones]
    if (
        any(not isinstance(code, str) for code in codes)
        or len(codes) != 12
        or set(codes) != set(ZONE_CODES)
    ):
        raise LayoutAuthorityError("ZONE_PLAN_IDENTITY_INVALID")
    for zone in zones:
        try:
            decimal_value(zone.get("required_area_m2"))
        except LayoutAuthorityError:
            raise LayoutAuthorityError(
                "ZONE_PLAN_IDENTITY_INVALID", zone_code=zone["zone_code"]
            ) from None
    # Validate serialization and bind the whole source, not a caller-supplied hash.
    source_hash = canonical_hash(zone_plan_snapshot)
    profiles = {profile.zone_code: profile for profile in upstream_profiles()}
    matrix: list[dict[str, Any]] = []
    dimensions = []
    for zone in sorted(zones, key=lambda row: row["zone_code"]):
        code = zone["zone_code"]
        profile = profiles.get(code)
        entry: dict[str, Any] = {
            "zone_code": code,
            "area_authority": "cold_room_zone_plan@1.0.0",
            "required_area_m2": zone["required_area_m2"],
            "capacity_geometry_available": "layout" in zone or "schemes" in zone,
            "dimensioning_profile_available": profile is not None,
            "capacity_geometry_reference": canonical_hash(zone),
            "upstream_zone": zone,
            "dimensioning_result": "BLOCKED",
            "block_reason": None,
        }
        try:
            if profile is not None:
                expected = "three_side_2.2m" if code == "raw_fruit_buffer" else "one_long_side_3m"
                if zone.get("aisle_layout") != expected:
                    raise LayoutAuthorityError("INVALID_UPSTREAM_CAPACITY_GEOMETRY", zone_code=code)
            dimension = dimension_zone(zone, profile)
            dimensions.append(asdict(dimension))
            entry["dimensioning_result"] = "DIMENSIONED"
        except LayoutAuthorityError as error:
            entry["block_reason"] = {"code": error.code, "details": error.details}
        matrix.append(entry)
    payload = {
        "schema_version": "1.0.0",
        "calculator_identity": IDENTITY,
        "source_zone_plan_calculator_identity": "cold_room_zone_plan@1.0.0",
        "source_formula_authority": params["formula_authority"],
        "source_zone_plan_result_hash": source_hash,
        "status": "PARTIAL_ENGINEERING_AUTHORITY" if len(dimensions) != 12 else "DIMENSIONED",
        "dimensions": dimensions,
        "authority_matrix": matrix,
        "profiles": [profile_payload(profiles[code]) for code in sorted(profiles)],
        "adjacency_graph": asdict(process_graph()),
        "constraint_evaluation": {
            "area_invariants_passed_for_dimensioned_zones": True,
            "adjacency_status": "NOT_EVALUATED_NO_PLACEMENT",
            "access_status": "ACCESS_PROFILE_REQUIRED",
            "site_constraints_status": "NOT_IMPLEMENTED",
        },
        "units": {"length": "m", "area": "m2"},
        "requires_review": True,
        "assumptions": [
            "Storage grid envelope only; not construction drawings or access approval."
        ],
        "warnings": ["Unresolved zone dimensions and access authority prevent layout acceptance."],
    }
    return ZoneDimensioningResultV1(canonical_json(payload))
