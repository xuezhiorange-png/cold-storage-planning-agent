"""Deterministic integer-grid envelope search, never area or capacity planning.

Candidate family: uniform-orientation rectangular pallet rows, a longitudinal
aisle strip, and optional residual envelope space. No pallet/portal placement or
accessibility claim. Both approved pallet orientations are enumerated.
"""

from collections.abc import Mapping
from dataclasses import asdict
from decimal import ROUND_CEILING, Context, Decimal, localcontext
from math import isqrt
from typing import Any

from cold_storage.modules.layout.domain.dimension_handoff import OWNER
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    ZoneDimensionV1,
    canonical_hash,
    decimal_value,
)

IDENTITY = "packaging-integer-envelope@1.0.0"
ZONE = "packaging_material_storage"
# Resource limits, not engineering rules. Exhaustion fails closed, never truncates search.
MAX_POSITIONS = 10000
MAX_CANDIDATES = 2000000


def dimension_packaging_zone(zone: Mapping[str, Any]) -> dict[str, Any]:
    n = zone.get("position_count")
    if zone.get("zone_code") != ZONE or type(n) is not int or n <= 0:
        raise LayoutAuthorityError("INVALID_UPSTREAM_PACKAGING_AUTHORITY")
    if n > MAX_POSITIONS:
        raise LayoutAuthorityError("PACKAGING_SEARCH_RESOURCE_LIMIT")
    required = decimal_value(zone.get("required_area_m2"), positive=True)
    with localcontext(Context(prec=80)):
        # Integer millimetres preserve the 0.001m grid exactly; no float/epsilon.
        lower = int((required * 1000000).to_integral_value(rounding=ROUND_CEILING))
        # Tuple order: area, perimeter, ratio (redundant given first two), rows,
        # columns, orientation, long edge, short edge. Equal area/perimeter
        # determine the same unordered edges, hence the same long/short ratio.
        best: tuple[int, ...] | None = None
        visited = 0
        for rows in range(1, n + 1):
            columns = (n + rows - 1) // rows
            for angle, pitch_long, pitch_depth in ((0, 1200, 1000), (90, 1000, 1200)):
                min_long = columns * pitch_long
                min_short = rows * pitch_depth + 3000
                first_long = max(min_long, min_short, (lower + min_short - 1) // min_short)
                initial = (
                    first_long * min_short,
                    2 * (first_long + min_short),
                    rows,
                    columns,
                    angle,
                    first_long,
                    min_short,
                )
                if best is None or initial < best:
                    best = initial
                # Every better/equal candidate has short <= sqrt(best area).
                # For each short, the smallest legal long dominates longer ones.
                stop = isqrt(best[0])
                visited += max(0, stop - min_short + 1)
                if visited > MAX_CANDIDATES:
                    raise LayoutAuthorityError("PACKAGING_SEARCH_RESOURCE_LIMIT")
                for short in range(min_short, stop + 1):
                    long = max(min_long, short, (lower + short - 1) // short)
                    candidate = (
                        long * short,
                        2 * (long + short),
                        rows,
                        columns,
                        angle,
                        long,
                        short,
                    )
                    if candidate < best:
                        best = candidate
        assert best is not None
        area, _, rows, columns, angle, long, short = best
        width, depth = Decimal(long) / 1000, Decimal(short) / 1000
        result = ZoneDimensionV1(
            ZONE,
            required,
            width,
            depth,
            Decimal(area) / 1000000,
            0,
            IDENTITY,
            OWNER,
            canonical_hash(zone),
        )
        return {
            **asdict(result),
            "position_count": n,
            "rows": rows,
            "columns": columns,
            "unused_cells": rows * columns - n,
            "pallet_rotation_deg": angle,
            "pallet_module_m": [Decimal("1.2"), Decimal("1.0")],
            "long_edge_aisle_min_m": Decimal("3.0"),
            "aisle_geometry_width_m": Decimal("3.0"),
            "aisle_added_to_required_area": False,
            "k_semantics": "UNDECOMPOSED_AREA_FACTOR",
            "search_profile_identity": IDENTITY,
            "access_status": "ACCESS_PROFILE_REQUIRED",
        }
