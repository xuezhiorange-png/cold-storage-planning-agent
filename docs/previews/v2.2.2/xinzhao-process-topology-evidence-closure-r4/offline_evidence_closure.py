"""R4 exact evidence checks, delegating source geometry/topology to frozen R2/R3.

No inferred wall, tolerance, automatic ring classification or production Authority.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
R3_MANIFEST_SHA = "c1e86b3df8d7cfa646f3e842db138b465123cc836ce5a8105d9d636da4ca91c5"


@lru_cache
def frozen() -> Any:
    root = HERE.parent / "xinzhao-real-process-room-topology-r3"
    raw = (root / "source_manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != R3_MANIFEST_SHA:
        raise ValueError("R3_MANIFEST_CHANGED")
    for name, record in json.loads(raw)["files"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("R3_FILE_CHANGED:" + name)
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location(
        "offline_process_topology", root / "offline_process_topology.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source_extension(
    page: dict[str, Any], existing: list[Any], reviewed_refs: list[dict[str, Any]]
) -> dict[str, Any]:
    """Add only manually selected original segments; never create a gap bridge."""
    core, _ = frozen().dependencies()
    existing = [tuple(core.point(p) for p in edge) for edge in existing]
    if not reviewed_refs or any(not r.get("review_basis") for r in reviewed_refs):
        raise ValueError("EXPLICIT_SOURCE_REVIEW_REQUIRED")
    additions = [core.source_segment(page, r) for r in reviewed_refs]
    return {
        "before": core.topology(existing),
        "after": core.topology(existing + additions),
        "added_source_refs": reviewed_refs,
        "added_points": [[core.export_point(p) for p in e] for e in additions],
        "classification": "REVIEWED_JUNCTION_GEOMETRY_NOT_AUTOMATIC_EXTERIOR_WALL",
        "engineering_approved": False,
    }


def ring_relationships(
    outer_edges: list[Any], inner_edges: list[list[Any]]
) -> dict[str, Any]:
    """Strict orthogonal containment; do not infer whether a ring is an occupied void."""
    core, _ = frozen().dependencies()
    outer_edges = [tuple(core.point(p) for p in edge) for edge in outer_edges]
    inner_edges = [
        [tuple(core.point(p) for p in edge) for edge in ring] for ring in inner_edges
    ]
    outer = core.topology(outer_edges)
    inners = [core.topology(edges) for edges in inner_edges]
    if not outer["closed"] or any(not ring["closed"] for ring in inners):
        raise ValueError("CLOSED_VALID_ORTHOGONAL_RINGS_REQUIRED")

    def locate(p: Any, edges: list[Any]) -> str:
        if any(core.on_segment(p, edge) for edge in edges):
            return "BOUNDARY"
        crossings = sum(
            a[0] == b[0] and min(a[1], b[1]) <= p[1] < max(a[1], b[1]) and a[0] > p[0]
            for a, b in edges
        )
        return "INSIDE" if crossings % 2 else "OUTSIDE"

    relations = []
    for edges in inner_edges:
        contacts = [
            core.intersection_kind(a, b)
            for a in edges
            for b in outer_edges
            if core.intersection_kind(a, b) is not None
        ]
        relations.append(
            {
                "strictly_inside_outer": not contacts
                and locate(edges[0][0], outer_edges) == "INSIDE",
                "outer_contacts": contacts,
            }
        )
    conflicts = []
    for i, a in enumerate(inner_edges):
        for j, b in enumerate(inner_edges[:i]):
            if (
                any(core.intersection_kind(x, y) for x in a for y in b)
                or locate(a[0][0], b) != "OUTSIDE"
                or locate(b[0][0], a) != "OUTSIDE"
            ):
                conflicts.append([j, i])
    valid = all(r["strictly_inside_outer"] for r in relations) and not conflicts
    return {
        "outer": outer,
        "inner_rings": inners,
        "relations": relations,
        "inner_conflicts": conflicts,
        "strict_ring_relationships_valid": valid,
        "outer_reference_area_pdf_points_squared": outer[
            "exact_area_pdf_points_squared"
        ],
        "internal_ring_geometric_area_pdf_points_squared": [
            r["exact_area_pdf_points_squared"] for r in inners
        ],
        "internal_occupancy_area": None,
        "reference_area_excluding_confirmed_voids": None,
        "finished_clear_area": None,
        "approved_net_area": None,
        "ring_type_status": "UNVERIFIED_REQUIRES_ARCHITECTURAL_OR_STRUCTURAL_SOURCE",
        "status": "PARTIAL_SOURCE_BOUND" if valid else "BLOCKED_INSUFFICIENT_EVIDENCE",
    }


def symbol_alignment(
    opening: Any, symbol_points: list[Any], reviewed_roi: list[Any]
) -> dict[str, Any]:
    """Mechanical compatibility, not symbol identity/door approval from existence alone."""
    core, _ = frozen().dependencies()
    a, b = [core.point(p) for p in opening]
    if a == b or (a[0] != b[0] and a[1] != b[1]) or not symbol_points:
        raise ValueError("STRAIGHT_OPENING_AND_SOURCE_SYMBOL_REQUIRED")
    points = [core.point(p) for p in symbol_points]
    x0, y0, x1, y1 = map(core.rational, reviewed_roi)
    axis = 0 if a[1] == b[1] else 1
    local = all(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in points)
    overlap = min(max(a[axis], b[axis]), max(p[axis] for p in points)) > max(
        min(a[axis], b[axis]), min(p[axis] for p in points)
    )
    return {
        "source_symbol_in_reviewed_local_region": local,
        "opening_projection_overlaps_symbol": overlap,
        "door_symbol_spatial_binding": "SPATIALLY_COMPATIBLE_REQUIRES_SOURCE_VISUAL_IDENTITY_REVIEW"
        if local and overlap
        else "UNVERIFIED",
        "verified_clear_width_mm": None,
        "route_validated": False,
        "engineering_approved": False,
    }
