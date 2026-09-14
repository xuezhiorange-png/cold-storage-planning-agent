"""Approved shipping pit-module envelope; no capacity or site placement solver."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, Context, Decimal, localcontext
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import (
    GRID,
    LayoutAuthorityError,
    ZoneDimensionV1,
    canonical_hash,
    decimal_value,
)

SHIPPING_ZONE = "shipping_channel"


@dataclass(frozen=True)
class ShippingDimensionProfileV1:
    identity: str = "shipping-pit-module-envelope@1.0.0"
    dimensioning_authority: str = "Charles:V2_2_P1D1_REMAINING_ZONE_OWNER_AUTHORITY_R1"
    fixed_width_m: Decimal = Decimal("6.5")
    loading_face: str = "LONG_EDGE"
    pit_width_m: Decimal = Decimal("2.0")
    min_pit_to_pit_clearance_m: Decimal = Decimal("2.5")
    min_pit_to_side_wall_clearance_m: Decimal = Decimal("2.5")


def shipping_profile() -> ShippingDimensionProfileV1:
    return ShippingDimensionProfileV1()


def dimension_shipping_zone(zone: Mapping[str, Any]) -> dict[str, Any]:
    """Backend-only binding: read N/area unchanged, no caller profile override.

    width_m is the approved short edge; depth_m is the loading long edge.
    Clearances constrain the envelope only, not positioned pits or access routes.
    """
    count = zone.get("platform_count")
    if (
        zone.get("zone_code") != SHIPPING_ZONE
        or type(count) is not int
        or not 1 <= count <= 10**12
        or type(zone.get("position_count")) is not int
        or zone["position_count"] != count
    ):
        raise LayoutAuthorityError("INVALID_UPSTREAM_SHIPPING_AUTHORITY", zone_code=SHIPPING_ZONE)
    required = decimal_value(zone.get("required_area_m2"), positive=True)
    profile = shipping_profile()
    with localcontext(Context(prec=80)):
        minimum = (
            2 * profile.min_pit_to_side_wall_clearance_m
            + count * profile.pit_width_m
            + (count - 1) * profile.min_pit_to_pit_clearance_m
        )
        area_edge = required / profile.fixed_width_m
        depth = (max(minimum, area_edge) / GRID).to_integral_value(rounding=ROUND_CEILING) * GRID
        dimension = ZoneDimensionV1(
            SHIPPING_ZONE,
            required,
            profile.fixed_width_m,
            depth,
            profile.fixed_width_m * depth,
            0,
            profile.identity,
            profile.dimensioning_authority,
            canonical_hash(zone),
        )
        # Compare exact areas rather than rounded division to identify the controlling rule.
        module_area = minimum * profile.fixed_width_m
        controlling = (
            "AREA" if required > module_area else "PIT_MODULE" if required < module_area else "BOTH"
        )
    return {
        **asdict(dimension),
        "platform_count": count,
        "loading_face": profile.loading_face,
        "loading_edge_dimension": "depth_m",
        "loading_edge_min_m": minimum,
        "pit_width_m": profile.pit_width_m,
        "min_pit_to_pit_clearance_m": profile.min_pit_to_pit_clearance_m,
        "min_pit_to_side_wall_clearance_m": profile.min_pit_to_side_wall_clearance_m,
        "controlling_constraint": controlling,
    }
