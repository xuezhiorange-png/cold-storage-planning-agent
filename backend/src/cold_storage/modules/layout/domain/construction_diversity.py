"""Conservative geometric diversity evidence, never an engineering authority.

Exact room geometry is quotiented by translation and the eight square
symmetries. Major organization is the ordered physical attachment directions
of the authoritative main process chain, under the SAME symmetries. Only a
change to that organization counts as another construction candidate for now.
This deliberately undercounts different support branches within one main
organization; tail swaps, small offsets and room resizing cannot earn coverage.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from itertools import groupby, product
from typing import Any

from cold_storage.modules.layout.domain.adjacency import PROCESS_FLOW, ZONE_CODES
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1

POLICY = "main-process-positive-edge-organization@1.0.0"
Box = tuple[int, int, int, int]


def physical_boxes(rows: Sequence[Mapping[str, Any]]) -> dict[str, Box]:
    """Preserve millimetres and physical rotation; never round malformed input."""
    result: dict[str, Box] = {}
    for row in rows:
        code = row.get("zone_code")
        if not isinstance(code, str) or code not in ZONE_CODES or code in result:
            raise LayoutAuthorityError("DIVERSITY_ROLE_SET_INVALID")
        try:
            values = [Decimal(str(row[k])) for k in ("x", "y", "width_m", "depth_m")]
            if any(not v.is_finite() or v * 1000 != (v * 1000).to_integral_value() for v in values):
                raise ValueError("non-millimetre geometry")
            if (
                values[2] <= 0
                or values[3] <= 0
                or type(row["rotation_deg"]) is not int
                or row["rotation_deg"] not in (0, 90)
            ):
                raise ValueError("invalid rectangle")
            room = PlacedRectangleV1(
                code, values[0], values[1], values[2], values[3], row["rotation_deg"]
            )
            xs, ys = zip(*room.polygon_mm, strict=True)
            result[code] = (min(xs), min(ys), max(xs), max(ys))
        except (InvalidOperation, ValueError, TypeError, KeyError) as error:
            raise LayoutAuthorityError("DIVERSITY_GEOMETRY_INVALID", role=code) from error
    if set(result) != set(ZONE_CODES):
        raise LayoutAuthorityError("DIVERSITY_ROLE_SET_INVALID")
    return result


def _variants(boxes: Mapping[str, Box]) -> list[dict[str, Box]]:
    variants: list[dict[str, Box]] = []
    for swap, sx, sy in product((False, True), (-1, 1), (-1, 1)):
        transformed = {}
        for role, (x, y, right, top) in boxes.items():
            points = [
                (sx * b, sy * a) if swap else (sx * a, sy * b) for a, b in ((x, y), (right, top))
            ]
            xs, ys = zip(*points, strict=True)
            transformed[role] = (min(xs), min(ys), max(xs), max(ys))
        low_x = min(b[0] for b in transformed.values())
        low_y = min(b[1] for b in transformed.values())
        variants.append(
            {
                k: (a - low_x, b - low_y, c - low_x, d - low_y)
                for k, (a, b, c, d) in transformed.items()
            }
        )
    return variants


def _attachment(a: Box, b: Box) -> str:
    x, y, right, top = a
    bx, by, br, bt = b
    if min(top, bt) > max(y, by):
        if right == bx:
            return "E"
        if br == x:
            return "W"
    if min(right, br) > max(x, bx):
        if top == by:
            return "N"
        if bt == y:
            return "S"
    raise LayoutAuthorityError("DIVERSITY_MAIN_MUST_EDGE_MISSING")


def construction_diversity(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    variants = _variants(physical_boxes(rows))
    geometry = min(tuple((k, *b[k]) for k in sorted(b)) for b in variants)
    directions = min(
        tuple(
            _attachment(b[a], b[z])
            for a, z in zip(PROCESS_FLOW[:-1], PROCESS_FLOW[1:], strict=True)
        )
        for b in variants
    )
    return {
        "policy": POLICY,
        "symmetry_invariant_geometry_hash": canonical_hash(geometry),
        "major_organization_hash": canonical_hash((POLICY, directions)),
        "major_family_hash": canonical_hash((POLICY, tuple(k for k, _ in groupby(directions)))),
        "canonical_major_band_directions": [k for k, _ in groupby(directions)],
        "main_process_roles": list(PROCESS_FLOW),
        "canonical_attachment_directions": list(directions),
        "major_family_basis": "ACTUAL_MAIN_PROCESS_POSITIVE_EDGE_DIRECTIONS",
        "support_only_changes_counted": False,
        "quality_or_p2d_acceptance": False,
    }
