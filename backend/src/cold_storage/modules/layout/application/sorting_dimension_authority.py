"""Bind the approved long-edge envelope to existing canonical sorting geometry.

No grid search, capacity calculation or area replacement. Redundant upstream
geometry is checked before exact product evidence is constructed internally.
"""

from collections.abc import Mapping
from decimal import Context, Decimal, localcontext
from typing import Any

from cold_storage.modules.calculations.domain.zone_planning import (
    FORMULA_AUTHORITY,
    PACKING_TABLE_PITCH_LONG_M,
    PACKING_TABLE_PITCH_SHORT_M,
    SORTING_CLEARANCE_LONG_M,
    SORTING_CLEARANCE_SHORT_M,
    SORTING_PACKAGING_AREA_FACTOR,
)
from cold_storage.modules.layout.domain.dimensioning import (
    AreaReportingProjectionV1,
    AreaRequirementV1,
    ExactAreaAuthorityV1,
    LayoutAuthorityError,
    ZoneDimensionProfileV1,
    ZoneDimensionV1,
    canonical_hash,
    canonical_json,
    decimal_value,
    dimension_zone,
)

SORTING_ZONE = "sorting_packaging_room"


def sorting_profile() -> ZoneDimensionProfileV1:
    """Charles P1C: expand the long edge only, never repack selected tables."""
    with localcontext(Context(prec=80)):
        factor = Decimal(str(SORTING_PACKAGING_AREA_FACTOR))
        long_pitch = Decimal(str(PACKING_TABLE_PITCH_LONG_M))
        short_pitch = Decimal(str(PACKING_TABLE_PITCH_SHORT_M))
        return ZoneDimensionProfileV1(
            profile_id="upstream-sorting-long-edge-envelope",
            profile_version="1.0.0",
            zone_code=SORTING_ZONE,
            dimensioning_mode="UPSTREAM_GRID",
            width_m=long_pitch * factor,
            depth_m=short_pitch,
            width_offset_m=(Decimal(str(SORTING_CLEARANCE_LONG_M)) - long_pitch) * factor,
            depth_offset_m=Decimal(str(SORTING_CLEARANCE_SHORT_M)) - short_pitch,
            source=f"{FORMULA_AUTHORITY}:_pack_sorting_rectangle/Charles-P1C-long-edge/ADR-044",
        )


def dimension_sorting_zone(zone: Mapping[str, Any]) -> ZoneDimensionV1:
    """Internal binder called only after application canonical identity validation.

    Never accepts caller-supplied profiles, hashes, exact areas or projection rules.
    The snapshot hash is recomputed; it binds provenance, not external authenticity.
    """
    with localcontext(Context(prec=80)):
        _validate_sorting_geometry(zone)
        profile = sorting_profile()
        authority = ExactAreaAuthorityV1(
            source_identity=profile.identity,
            source_authority=profile.source,
            source_snapshot_hash=canonical_hash(zone),
            operand_source_paths=("/raw_required_area_m2", "/sorting_packaging_area_factor"),
            operands=(
                decimal_value(zone["raw_required_area_m2"]),
                decimal_value(zone["sorting_packaging_area_factor"]),
            ),
            source_snapshot_json=canonical_json(zone),
        )
        requirement = AreaRequirementV1(
            reported_required_area_m2=decimal_value(zone["required_area_m2"]),
            exact_authority=authority,
            reporting_projection=AreaReportingProjectionV1(),
        )
        return dimension_zone(zone, profile, area_requirement=requirement)


def _validate_sorting_geometry(zone: Mapping[str, Any]) -> None:
    error = "INVALID_UPSTREAM_CAPACITY_GEOMETRY"
    if (
        zone.get("zone_code") != SORTING_ZONE
        or zone.get("aisle_layout") != "four_side_architectural"
    ):
        raise LayoutAuthorityError(error, zone_code=SORTING_ZONE)
    fields = ("n_long", "n_short", "n_actual", "position_count", "n_need", "table_count")
    if any(type(zone.get(key)) is not int or zone[key] <= 0 for key in fields):
        raise LayoutAuthorityError(error, zone_code=SORTING_ZONE)
    layout = zone.get("layout")
    if (
        not isinstance(layout, Mapping)
        or any(
            type(layout.get(key)) is not int or layout[key] != zone[key]
            for key in ("n_long", "n_short")
        )
        or zone["n_long"] < zone["n_short"]
        or zone["n_long"] * zone["n_short"] != zone["n_actual"]
        or zone["position_count"] != zone["n_actual"]
        or zone["table_count"] != zone["n_need"]
        or zone["n_actual"] < zone["n_need"]
        or type(zone.get("unused_cells")) is not int
        or zone["unused_cells"] != zone["n_actual"] - zone["n_need"]
    ):
        raise LayoutAuthorityError(error, zone_code=SORTING_ZONE)
    # Integrity cross-check of the supplied rectangle, not an area authority or
    # candidate search. The actual required area is always read from the source.
    width = (zone["n_long"] - 1) * Decimal(str(PACKING_TABLE_PITCH_LONG_M)) + Decimal(
        str(SORTING_CLEARANCE_LONG_M)
    )
    depth = (zone["n_short"] - 1) * Decimal(str(PACKING_TABLE_PITCH_SHORT_M)) + Decimal(
        str(SORTING_CLEARANCE_SHORT_M)
    )
    if decimal_value(zone.get("raw_required_area_m2")) != width * depth:
        raise LayoutAuthorityError("SORTING_RAW_AREA_GEOMETRY_MISMATCH", zone_code=SORTING_ZONE)
    if decimal_value(zone.get("sorting_packaging_area_factor")) != Decimal(
        str(SORTING_PACKAGING_AREA_FACTOR)
    ):
        raise LayoutAuthorityError("SORTING_AREA_FACTOR_AUTHORITY_MISMATCH", zone_code=SORTING_ZONE)
