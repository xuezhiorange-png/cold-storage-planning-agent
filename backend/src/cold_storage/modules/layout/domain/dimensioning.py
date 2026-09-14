"""Versioned, explicit rectangle authority. Never solve capacity or place zones."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from dataclasses import field as dataclass_field
from decimal import ROUND_CEILING, Context, Decimal, InvalidOperation, localcontext
from typing import Any, cast

IDENTITY = "zone_dimensioning_foundation@1.0.0"
GRID = Decimal("0.001")
AREA_PROJECTION_IDENTITY = "cold-room-zone-plan-binary64-product-2dp@1.0.0"
REPORTED_AREA_SOURCE = "cold_room_zone_plan@1.0.0:required_area_m2"


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
class ExactAreaAuthorityV1:
    """Backend-owned formula evidence, never user input or proof of Owner approval.

    An approved profile binder must obtain operands from its verified source.
    P1C0 ships no production binder. Test fixtures may exercise this contract.
    Ordered operands describe the pre-reporting product, not reverse-rounded area.
    """

    source_identity: str
    source_authority: str
    source_snapshot_hash: str
    operand_source_paths: tuple[str, ...]
    operands: tuple[Decimal, ...]
    source_snapshot_json: str
    formula_identity: str = "exact-decimal-product@1.0.0"
    exact_geometry_required_area_m2: Decimal = dataclass_field(init=False)

    def __post_init__(self) -> None:
        if (
            not re.fullmatch(r"[^\s@]+@\d+\.\d+\.\d+", self.source_identity)
            or not self.source_authority
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", self.source_snapshot_hash)
            or self.formula_identity != "exact-decimal-product@1.0.0"
            or not isinstance(self.operands, tuple)
            or not isinstance(self.operand_source_paths, tuple)
            or not 1 <= len(self.operands) <= 4
            or len(self.operands) != len(self.operand_source_paths)
            or any(not isinstance(path, str) or not path for path in self.operand_source_paths)
        ):
            raise LayoutAuthorityError("INVALID_EXACT_AREA_AUTHORITY")
        object.__setattr__(self, "operands", tuple(decimal_value(v) for v in self.operands))
        try:
            snapshot = json.loads(self.source_snapshot_json)
            if canonical_hash(snapshot) != self.source_snapshot_hash:
                raise ValueError
            for path, operand in zip(self.operand_source_paths, self.operands, strict=True):
                current = snapshot
                # Restricted JSON Pointer: mappings only, literal field names.
                if not path.startswith("/") or "~" in path:
                    raise ValueError
                for key in path[1:].split("/"):
                    if not isinstance(current, dict):
                        raise ValueError
                    current = current[key]
                if decimal_value(current) != operand:
                    raise ValueError
        except (ValueError, KeyError, TypeError):
            raise LayoutAuthorityError("EXACT_AREA_SOURCE_BINDING_MISMATCH") from None
        object.__setattr__(self, "source_snapshot_json", canonical_json(snapshot))

        with localcontext(Context(prec=128)):
            product = Decimal(1)
            for value in self.operands:
                product *= value
            object.__setattr__(self, "exact_geometry_required_area_m2", decimal_value(product))


@dataclass(frozen=True)
class AreaReportingProjectionV1:
    identity: str = AREA_PROJECTION_IDENTITY
    quantum: Decimal = Decimal("0.01")
    source_authority: str = REPORTED_AREA_SOURCE
    projection_method: str = "PYTHON_BINARY64_ORDERED_PRODUCT_THEN_ROUND_2"

    def __post_init__(self) -> None:
        if (
            self.identity != AREA_PROJECTION_IDENTITY
            or type(self.quantum) is not Decimal
            or self.quantum != Decimal("0.01")
            or self.source_authority != REPORTED_AREA_SOURCE
            or self.projection_method != "PYTHON_BINARY64_ORDERED_PRODUCT_THEN_ROUND_2"
        ):
            raise LayoutAuthorityError("INVALID_REPORTING_PROJECTION")

    def project(self, source: ExactAreaAuthorityV1) -> Decimal:
        # Deliberately reproduce Python float arithmetic. Decimal quantize or
        # float(exact product) can differ at ties from upstream operand replay.
        product = float(source.operands[0])
        for operand in source.operands[1:]:
            product *= float(operand)
        if not math.isfinite(product):
            raise LayoutAuthorityError("INVALID_REPORTING_PROJECTION")
        return Decimal(str(round(product, 2)))


@dataclass(frozen=True)
class AreaRequirementV1:
    reported_required_area_m2: Decimal
    reported_area_source_identity: str = REPORTED_AREA_SOURCE
    exact_authority: ExactAreaAuthorityV1 | None = None
    reporting_projection: AreaReportingProjectionV1 | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reported_required_area_m2", decimal_value(self.reported_required_area_m2)
        )
        if self.reported_area_source_identity != REPORTED_AREA_SOURCE:
            raise LayoutAuthorityError("INVALID_REPORTED_AREA_AUTHORITY")
        if self.exact_authority is None:
            if self.reporting_projection is not None:
                raise LayoutAuthorityError("EXACT_AREA_AUTHORITY_REQUIRED")
            return
        if (
            type(self.exact_authority) is not ExactAreaAuthorityV1
            or type(self.reporting_projection) is not AreaReportingProjectionV1
        ):
            raise LayoutAuthorityError("INVALID_EXACT_AREA_AUTHORITY")
        if (
            self.reporting_projection.project(self.exact_authority)
            != self.reported_required_area_m2
        ):
            raise LayoutAuthorityError("AREA_REPORTING_PROJECTION_MISMATCH")

    @property
    def geometric_lower_bound_m2(self) -> Decimal:
        if self.exact_authority is None:
            return self.reported_required_area_m2
        return self.exact_authority.exact_geometry_required_area_m2


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
    area_requirement: AreaRequirementV1 | None = None

    def __post_init__(self) -> None:
        area = decimal_value(self.required_area_m2)
        width = decimal_value(self.width_m, positive=True)
        depth = decimal_value(self.depth_m, positive=True)
        actual = decimal_value(self.actual_area_m2, positive=True)
        requirement = self.area_requirement
        if requirement is None:
            requirement = AreaRequirementV1(area)
            object.__setattr__(self, "area_requirement", requirement)
        if (
            type(requirement) is not AreaRequirementV1
            or requirement.reported_required_area_m2 != area
        ):
            raise LayoutAuthorityError("INVALID_AREA_REQUIREMENT")
        exact = requirement.exact_authority
        if exact is not None and (
            exact.source_snapshot_hash != self.capacity_geometry_reference
            or exact.source_identity != self.dimensioning_profile_identity
            or exact.source_authority != self.dimensioning_authority
        ):
            raise LayoutAuthorityError("EXACT_AREA_SOURCE_BINDING_MISMATCH")
        with localcontext(Context(prec=80)):
            if (
                width % GRID
                or depth % GRID
                or actual != width * depth
                or actual < requirement.geometric_lower_bound_m2
            ):
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
