"""Versioned, explicit rectangle authority. Never solve capacity or place zones."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, Context, Decimal, InvalidOperation, localcontext
from typing import Any, cast

IDENTITY = "zone_dimensioning_foundation@1.0.0"
GRID = Decimal("0.001")


class LayoutAuthorityError(ValueError):
    def __init__(self, code: str, **details: object) -> None:
        self.code = code
        self.details = details
        super().__init__(code)


def decimal_value(value: object, *, positive: bool = False) -> Decimal:
    try:
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
            raise ValueError
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or (positive and number == 0):
            raise ValueError
        # Bound precision to keep arithmetic exact and resource usage predictable.
        if len(number.as_tuple().digits) > 24 or abs(int(number.as_tuple().exponent)) > 12:
            raise ValueError
        return number
    except (InvalidOperation, ValueError, TypeError):
        raise LayoutAuthorityError("INVALID_DIMENSIONING_VALUE", value=str(value)) from None


def canonical_json(value: object) -> str:
    def normalize(item: Any) -> Any:
        if isinstance(item, bool) or item is None or isinstance(item, str):
            return item
        if isinstance(item, (Decimal, float)):
            number = Decimal(str(item))
            if not number.is_finite():
                raise LayoutAuthorityError("INVALID_CANONICAL_NUMBER")
            return (
                "0"
                if number == 0
                else format(number, "f").rstrip("0").rstrip(".")
                if "." in format(number, "f")
                else format(number, "f")
            )
        if isinstance(item, Mapping):
            return {str(key): normalize(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(val) for val in item]
        if isinstance(item, int):
            return item
        raise LayoutAuthorityError("INVALID_CANONICAL_VALUE")

    return json.dumps(normalize(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def canonical_hash(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ZoneDimensionProfileV1:
    """Backend-owned profile, not user/MCP input or evidence of engineering approval.

    FIXED_ENVELOPE explicitly supplies both edges; UPSTREAM_GRID preserves grid
    counts and only projects frozen pitch/aisle dimensions. No ratio search.
    """

    profile_id: str
    profile_version: str
    zone_code: str
    dimensioning_mode: str
    width_m: Decimal
    depth_m: Decimal
    source: str
    width_offset_m: Decimal = Decimal("0")
    depth_offset_m: Decimal = Decimal("0")
    width_increment_m: Decimal = GRID
    depth_increment_m: Decimal = GRID
    rotation_allowed: tuple[int, ...] = (0, 90)
    capacity_geometry_policy: str = "PRESERVE_UPSTREAM"

    @property
    def identity(self) -> str:
        return f"{self.profile_id}@{self.profile_version}"

    def __post_init__(self) -> None:
        if not all((self.profile_id, self.profile_version, self.zone_code, self.source)):
            raise LayoutAuthorityError("INVALID_DIMENSIONING_PROFILE")
        if self.dimensioning_mode not in {"FIXED_ENVELOPE", "UPSTREAM_GRID"}:
            raise LayoutAuthorityError("INVALID_DIMENSIONING_PROFILE")
        if self.capacity_geometry_policy != "PRESERVE_UPSTREAM":
            raise LayoutAuthorityError("UPSTREAM_CAPACITY_GEOMETRY_MAY_NOT_BE_REPACKED")
        if not self.rotation_allowed or any(
            type(r) is not int or r not in (0, 90) for r in self.rotation_allowed
        ):
            raise LayoutAuthorityError("INVALID_ROTATION")
        for field in ("width_m", "depth_m", "width_increment_m", "depth_increment_m"):
            number = decimal_value(getattr(self, field), positive=True)
            object.__setattr__(self, field, number)
        for field in ("width_offset_m", "depth_offset_m"):
            object.__setattr__(self, field, decimal_value(getattr(self, field)))
        with localcontext(Context(prec=80)):
            if any(v % GRID for v in (self.width_increment_m, self.depth_increment_m)):
                raise LayoutAuthorityError("INVALID_DIMENSIONING_PROFILE")


@dataclass(frozen=True)
class ZoneDimensionV1:
    zone_code: str
    required_area_m2: Decimal
    width_m: Decimal
    depth_m: Decimal
    actual_area_m2: Decimal
    rotation_deg: int
    dimensioning_profile_identity: str
    dimensioning_authority: str
    capacity_geometry_reference: str

    def __post_init__(self) -> None:
        area = decimal_value(self.required_area_m2)
        width = decimal_value(self.width_m, positive=True)
        depth = decimal_value(self.depth_m, positive=True)
        actual = decimal_value(self.actual_area_m2, positive=True)
        with localcontext(Context(prec=80)):
            if width % GRID or depth % GRID or actual != width * depth or actual < area:
                raise LayoutAuthorityError("INVALID_ZONE_DIMENSION")
        if type(self.rotation_deg) is not int or self.rotation_deg not in (0, 90):
            raise LayoutAuthorityError("INVALID_ROTATION")


def dimension_zone(
    zone: Mapping[str, Any],
    profile: ZoneDimensionProfileV1 | None,
    *,
    rotation_deg: int = 0,
) -> ZoneDimensionV1:
    code = str(zone["zone_code"])
    area = decimal_value(zone["required_area_m2"])
    if profile is None:
        raise LayoutAuthorityError(
            "ZONE_DIMENSIONING_AUTHORITY_REQUIRED",
            zone_code=code,
            missing_profile=True,
            required_area_m2=str(area),
        )
    if profile.zone_code != code:
        raise LayoutAuthorityError("INVALID_DIMENSIONING_PROFILE", zone_code=code)
    if type(rotation_deg) is not int or rotation_deg not in profile.rotation_allowed:
        raise LayoutAuthorityError("INVALID_ROTATION", zone_code=code)
    with localcontext(Context(prec=80)):
        width, depth = profile.width_m, profile.depth_m
        if profile.dimensioning_mode == "UPSTREAM_GRID":
            counts = [zone.get(key) for key in ("n_long", "n_short", "n_actual", "position_count")]
            if any(type(value) is not int or value <= 0 for value in counts):
                raise LayoutAuthorityError("INVALID_UPSTREAM_CAPACITY_GEOMETRY", zone_code=code)
            n_long, n_short, n_actual, positions = (cast(int, value) for value in counts)
            layout = zone.get("layout")
            if (
                n_long * n_short != n_actual
                or positions != n_actual
                or not isinstance(layout, Mapping)
                or layout.get("n_long") != n_long
                or layout.get("n_short") != n_short
            ):
                raise LayoutAuthorityError("INVALID_UPSTREAM_CAPACITY_GEOMETRY", zone_code=code)
            width = n_long * width + profile.width_offset_m
            depth = n_short * depth + profile.depth_offset_m
        elif any(key in zone for key in ("layout", "schemes", "reporting_scheme_id")):
            # Generic fixed rectangles cannot assert that a capacity arrangement fits.
            raise LayoutAuthorityError(
                "ZONE_DIMENSIONING_AUTHORITY_REQUIRED",
                zone_code=code,
                missing_profile="capacity_envelope_binding",
                required_area_m2=str(area),
            )
        width = (width / profile.width_increment_m).to_integral_value(
            rounding=ROUND_CEILING
        ) * profile.width_increment_m
        depth = (depth / profile.depth_increment_m).to_integral_value(
            rounding=ROUND_CEILING
        ) * profile.depth_increment_m
        actual = width * depth
        if actual < area:
            raise LayoutAuthorityError(
                "ZONE_DIMENSIONING_AUTHORITY_REQUIRED",
                zone_code=code,
                missing_profile="larger_explicit_envelope",
                required_area_m2=str(area),
            )
        return ZoneDimensionV1(
            code,
            area,
            width,
            depth,
            actual,
            rotation_deg,
            profile.identity,
            profile.source,
            canonical_hash(zone),
        )


@dataclass(frozen=True)
class AccessProfileV1:
    identity: str
    source: str
    clear_width_m: Decimal

    def __post_init__(self) -> None:
        if not self.identity or not self.source:
            raise LayoutAuthorityError("ACCESS_PROFILE_REQUIRED")
        object.__setattr__(self, "clear_width_m", decimal_value(self.clear_width_m, positive=True))


def require_access_profile(profile: AccessProfileV1 | None) -> AccessProfileV1:
    """Authority prerequisite only; never claims route/access compliance."""
    if not isinstance(profile, AccessProfileV1):
        raise LayoutAuthorityError("ACCESS_PROFILE_REQUIRED")
    return profile


def profile_payload(profile: ZoneDimensionProfileV1) -> dict[str, Any]:
    return asdict(profile)
