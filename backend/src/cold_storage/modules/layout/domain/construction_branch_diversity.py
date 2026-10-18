"""Conservative functional-interface diversity, not quality or P2D acceptance.

V1 remains unchanged. V2 adds two actual personnel interfaces to the main
process word. Coordinates, lengths, bends, sizes and labels alone earn nothing.
Missing/invalid interface evidence abstains rather than manufacturing coverage.
"""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from itertools import product
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.domain.adjacency import PROCESS_FLOW
from cold_storage.modules.layout.domain.construction_diversity import (
    _attachment,
    _variants,
    construction_diversity,
    physical_boxes,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash

POLICY = "main-process-and-personnel-interface-organization@2.0.0"
BRANCHES = (("main_entrance", "changing_room"), ("changing_room", "sorting_packaging_room"))
NORMALS = MappingProxyType({"E": (1, 0), "W": (-1, 0), "N": (0, 1), "S": (0, -1)})


def _face(box: tuple[int, int, int, int], portal: Mapping[str, Any]) -> str:
    points = []
    for key in ("start", "end"):
        point = portal["segment"][key]
        values = [Decimal(str(point[axis])) * 1000 for axis in ("x", "y")]
        if any(not v.is_finite() or v != v.to_integral_value() for v in values):
            raise ValueError("non-mm portal")
        points.append(tuple(map(int, values)))
    a, b = points
    x, y, right, top = box
    if a == b:
        raise ValueError("zero-width portal")
    if a[0] == b[0] and a[0] in (x, right) and y <= min(a[1], b[1]) < max(a[1], b[1]) <= top:
        return "W" if a[0] == x else "E"
    if a[1] == b[1] and a[1] in (y, top) and x <= min(a[0], b[0]) < max(a[0], b[0]) <= right:
        return "S" if a[1] == y else "N"
    raise ValueError("portal not on physical face")


def construction_branch_diversity(
    zones: Sequence[Mapping[str, Any]], access_results: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    legacy = construction_diversity(zones)
    boxes = physical_boxes(zones)
    facts = []
    try:
        for source, target in BRANCHES:
            rows = [
                r
                for r in access_results
                if (r.get("from_ref"), r.get("to_ref")) == (source, target)
            ]
            if len(rows) != 1 or rows[0].get("status") != "PASS":
                raise ValueError("missing independently validated branch")
            row = rows[0]
            if row["topology"] not in ("DIRECT_SHARED_EDGE", "CORRIDOR_MEDIATED"):
                raise ValueError("unsupported branch topology")
            faces = tuple(
                _face(boxes[role], row[key]) if role in boxes else "BOUNDARY"
                for role, key in ((source, "portal_from"), (target, "portal_to"))
            )
            facts.append((source, target, row["topology"], *faces))
    except (KeyError, ValueError, TypeError, ArithmeticError):
        return dict(
            legacy=legacy, policy=POLICY, countable=False, reason="BRANCH_EVIDENCE_INCOMPLETE"
        )
    signatures = []
    for transformed, (swap, sx, sy) in zip(
        _variants(boxes), product((False, True), (-1, 1), (-1, 1)), strict=True
    ):

        def direction(face: str, swap: bool = swap, sx: int = sx, sy: int = sy) -> str:
            if face == "BOUNDARY":
                return face
            a, b = NORMALS[face]
            normal = (sx * b, sy * a) if swap else (sx * a, sy * b)
            return next(k for k, value in NORMALS.items() if value == normal)

        main = tuple(
            _attachment(transformed[a], transformed[b])
            for a, b in zip(PROCESS_FLOW[:-1], PROCESS_FLOW[1:], strict=True)
        )
        branches = tuple(
            (a, b, topology, direction(f), direction(t)) for a, b, topology, f, t in facts
        )
        signatures.append((main, branches))
    signature = min(signatures)
    return dict(
        policy=POLICY,
        legacy=legacy,
        countable=True,
        meaningful_construction_hash=canonical_hash((POLICY, signature)),
        canonical_functional_signature=signature,
        physical_branch_facts=facts,
        major_family_hash=legacy["major_family_hash"],
        symmetry_invariant_geometry_hash=legacy["symmetry_invariant_geometry_hash"],
        quality_or_p2d_acceptance=False,
    )
