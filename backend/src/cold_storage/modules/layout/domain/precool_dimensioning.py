"""Charles-approved room envelopes; consume, never choose, upstream schemes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Context, Decimal, localcontext
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    ZoneDimensionV1,
    canonical_hash,
    decimal_value,
)

PRECOOL_ZONES = ("primary_precooling_room", "secondary_precooling_room")
AUTHORITY = "Charles:V2_2_P1B_PRECOOL_DIMENSION_AUTHORITY_R1"
ARRANGEMENT = "LONG_SIDES_PARALLEL"


@dataclass(frozen=True)
class PrecoolRoomProfileV1:
    identity: str
    selected_scheme_id: str
    positions_per_room: int
    single_room_width_m: Decimal
    single_room_depth_m: Decimal
    dimensioning_authority: str = AUTHORITY
    room_arrangement: str = ARRANGEMENT


def precool_profiles() -> tuple[PrecoolRoomProfileV1, ...]:
    return (
        PrecoolRoomProfileV1(
            "precool-room-6-position@1.0.0", "6_position", 6, Decimal("4.90"), Decimal("10.05")
        ),
        PrecoolRoomProfileV1(
            "precool-room-8-position@1.0.0", "8_position", 8, Decimal("4.90"), Decimal("12.95")
        ),
    )


def dimension_precool_zone(zone: Mapping[str, Any]) -> dict[str, Any]:
    """No caller profile override, capacity calculation, scheme selection or stretching."""
    code = zone.get("zone_code")
    if code not in PRECOOL_ZONES:
        raise LayoutAuthorityError("INVALID_PRECOOL_ZONE", zone_code=code)
    scheme_id = zone.get("reporting_scheme_id")
    profile = next((p for p in precool_profiles() if p.selected_scheme_id == scheme_id), None)
    if profile is None:
        raise LayoutAuthorityError(
            "UNKNOWN_PRECOOL_GEOMETRY_PROFILE", zone_code=code, selected_scheme_id=scheme_id
        )
    schemes = zone.get("schemes")
    if not isinstance(schemes, list) or any(not isinstance(s, Mapping) for s in schemes):
        raise LayoutAuthorityError("INVALID_UPSTREAM_PRECOOL_SCHEME", zone_code=code)
    matches = [s for s in schemes if s.get("scheme_id") == scheme_id]
    if len(matches) != 1:
        raise LayoutAuthorityError("INVALID_UPSTREAM_PRECOOL_SCHEME", zone_code=code)
    selected = matches[0]
    rooms, positions, per_room = (
        selected.get(key) for key in ("room_count", "position_count", "positions_per_room")
    )
    if any(type(v) is not int or v <= 0 or v > 10**12 for v in (rooms, positions, per_room)):
        raise LayoutAuthorityError("INVALID_UPSTREAM_PRECOOL_SCHEME", zone_code=code)
    # Product equality is an integrity check, never a replacement capacity value.
    if (
        per_room != profile.positions_per_room
        or positions != rooms * per_room
        or type(zone.get("position_count")) is not int
        or zone["position_count"] != positions
        or (
            "room_count" in zone
            and (type(zone["room_count"]) is not int or zone["room_count"] != rooms)
        )
    ):
        raise LayoutAuthorityError("INVALID_UPSTREAM_PRECOOL_SCHEME", zone_code=code)
    required = decimal_value(zone.get("required_area_m2"))
    if decimal_value(selected.get("required_area_m2")) != required:
        raise LayoutAuthorityError("UPSTREAM_PRECOOL_AREA_MISMATCH", zone_code=code)
    with localcontext(Context(prec=80)):
        width = rooms * profile.single_room_width_m
        depth = profile.single_room_depth_m
        actual = width * depth
        if actual < required:
            raise LayoutAuthorityError(
                "PRECOOL_GEOMETRY_AREA_INSUFFICIENT",
                zone_code=code,
                selected_scheme_id=scheme_id,
                room_count=rooms,
                required_area_m2=str(required),
                actual_area_m2=str(actual),
                combined_width_m=str(width),
                combined_depth_m=str(depth),
            )
        dimension = ZoneDimensionV1(
            str(code),
            required,
            width,
            depth,
            actual,
            0,
            profile.identity,
            profile.dimensioning_authority,
            canonical_hash(zone),
        )
    return {
        **asdict(dimension),
        "selected_scheme_id": scheme_id,
        "room_count": rooms,
        "position_count": positions,
        "positions_per_room": per_room,
        "single_room_width_m": profile.single_room_width_m,
        "single_room_depth_m": profile.single_room_depth_m,
        "combined_width_m": width,
        "combined_depth_m": depth,
        "room_arrangement": profile.room_arrangement,
    }
