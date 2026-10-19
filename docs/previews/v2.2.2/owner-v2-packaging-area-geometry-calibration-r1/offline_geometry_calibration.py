"""Offline legacy geometry audit and source-bound interface facts; no layout search."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from dataclasses import asdict
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

from cold_storage.modules.calculations.domain import zone_planning as legacy
from cold_storage.modules.layout.application.sorting_dimension_authority import (
    dimension_sorting_zone,
    sorting_profile,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_json

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
BASE = HERE.parent / "stage-b/layout-quality-baseline-01"
V2 = HERE.parent / "owner-functional-input-contract-r2"
REFERENCE = "15d2d7759bc0192813122c7aba16dcc11e4be0cd"
TASK = "V2_2_2_OWNER_V2_PACKAGING_AREA_GEOMETRY_CALIBRATION_R1"
VERSION = "offline-packing-geometry-calibration@1.0.0"
COMPONENTS = (
    "PACKING_STATION_ENVELOPE",
    "OPERATOR_ENVELOPE",
    "MATERIAL_SUPPLY_ENVELOPE",
    "PRODUCT_OUTFEED_ENVELOPE",
    "CIRCULATION_ENVELOPE",
    "CLEANING_MAINTENANCE_ENVELOPE",
)


def encode(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(folder: Path, script: str) -> Any:
    for name, digest in json.loads((folder / "source_manifest.json").read_text())["files"].items():
        digest = digest["sha256"] if isinstance(digest, dict) else digest
        if sha(folder / name) != digest:
            raise ValueError("SEALED_SOURCE_CHANGED")
    spec = importlib.util.spec_from_file_location("offline_" + folder.name, folder / script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exact_text(value: Decimal | Fraction | int) -> str:
    if isinstance(value, Decimal):
        return format(value, "f").rstrip("0").rstrip(".") if "." in str(value) else str(value)
    fraction = Fraction(value)
    if fraction.denominator == 1:
        return str(fraction.numerator)
    return f"{fraction.numerator}/{fraction.denominator}"


def projection(need: int) -> dict[str, Any]:
    if type(need) is not int or need <= 0:
        raise ValueError("POSITIVE_TABLE_COUNT_REQUIRED_FOR_DIAGNOSTIC")
    chosen = legacy.ColdRoomZonePlanner()._pack_sorting_rectangle(need)
    a, b = chosen.n_long, chosen.n_short
    length = (a - 1) * Decimal(str(legacy.PACKING_TABLE_PITCH_LONG_M)) + Decimal(
        str(legacy.SORTING_CLEARANCE_LONG_M)
    )
    depth = (b - 1) * Decimal(str(legacy.PACKING_TABLE_PITCH_SHORT_M)) + Decimal(
        str(legacy.SORTING_CLEARANCE_SHORT_M)
    )
    profile = sorting_profile()
    lx, dx = (
        a * profile.width_m + profile.width_offset_m,
        b * profile.depth_m + profile.depth_offset_m,
    )
    assert lx == length * Decimal("1.1") and dx == depth
    raw_reported = round(chosen.required_area_m2, 2)
    assert Decimal(str(raw_reported)) == length * depth
    return {
        "status": "HYPOTHETICAL_LEGACY_GEOMETRY_PROJECTION",
        "n_need": need,
        "n_long": a,
        "n_short": b,
        "n_actual": chosen.n_actual,
        "unused_cells": chosen.unused_cells,
        "L_raw_m": exact_text(length),
        "D_raw_m": exact_text(depth),
        "A_raw_exact_m2": exact_text(length * depth),
        "native_float_area_repr": repr(chosen.required_area_m2),
        "raw_area_reported_m2": str(raw_reported),
        "L_p1c_form_m": exact_text(lx),
        "D_p1c_form_m": exact_text(dx),
        "A_exact_p1c_form_m2": exact_text(lx * dx),
        "A_reported_m2": str(round(raw_reported * legacy.SORTING_PACKAGING_AREA_FACTOR, 2)),
        "factor_long_only": "1.1",
        "factor_depth": "1",
        "count_ratio": exact_text(Fraction(a, b)),
        "physical_raw_aspect_ratio": exact_text(Fraction(length) / Fraction(depth)),
        "physical_expanded_aspect_ratio": exact_text(Fraction(lx) / Fraction(dx)),
        "actual_device_footprint_m2": None,
        "v2_formal_p1_area_m2": None,
        "new_factory_total_area_m2": None,
        "functional_pass": None,
    }


def ranking_audit(need: int) -> dict[str, Any]:
    rows = []
    for a in range(1, need + 200):
        for b in range(1, a + 1):
            if a * b < need:
                continue
            ratio = a / b
            raw = (
                (a - 1) * legacy.PACKING_TABLE_PITCH_LONG_M + legacy.SORTING_CLEARANCE_LONG_M
            ) * ((b - 1) * legacy.PACKING_TABLE_PITCH_SHORT_M + legacy.SORTING_CLEARANCE_SHORT_M)
            rank = (0 if 1.67 <= ratio <= 2.40 else 1, a * b - need, abs(ratio - 2.0), raw)
            rows.append((rank, a, b))
    selected = min(rows)
    actual = legacy.ColdRoomZonePlanner()._pack_sorting_rectangle(need)
    assert (selected[1], selected[2]) == (actual.n_long, actual.n_short)
    smallest = min(rows, key=lambda item: (item[0][3], item[1], item[2]))

    def describe(row: tuple[tuple[int, int, float, float], int, int]) -> dict[str, Any]:
        rank, a, b = row
        return {
            "n_long": a,
            "n_short": b,
            "n_actual": a * b,
            "rank": rank,
            "raw_area_reported_m2": str(round(rank[3], 2)),
        }

    return {
        "n_need": need,
        "finite_search_range": {"n_long": f"1..{need + 199}", "n_short": "1..n_long"},
        "eligible_pair_count": len(rows),
        "selected": describe(selected),
        "smallest_raw_area_in_same_finite_domain": describe(smallest),
        "is_area_minimal_in_this_finite_domain": selected[0][3] == smallest[0][3],
        "global_engineering_optimality": "NOT_PROVEN",
        "range_meaning": (
            "Existing implementation bound; not a physical room capacity or global layout proof"
        ),
        "rank_order": [
            "n_long/n_short within1.67..2.40",
            "unused cells",
            "distance from2.0",
            "raw area",
        ],
        "continuity_and_internal_logistics": (
            "UNAVAILABLE_NO_STATION_COORDINATES_OR_INTERNAL_ROUTES"
        ),
    }


def mm(value: Any) -> int:
    q = Fraction(str(value)) * 1000
    if q.denominator != 1:
        raise ValueError("OFF_MM_GRID")
    return q.numerator


def box(zone: dict[str, Any]) -> tuple[int, int, int, int]:
    x, y, w, d = (mm(zone[k]) for k in ("x", "y", "width_m", "depth_m"))
    if zone["rotation_deg"] == 90:
        w, d = d, w
    elif zone["rotation_deg"] != 0:
        raise ValueError("UNSUPPORTED_ROTATION")
    return x, y, x + w, y + d


def wall(segment: dict[str, Any], rect: tuple[int, int, int, int]) -> dict[str, Any]:
    a, b = segment["start"], segment["end"]
    x, y, u, v = mm(a["x"]), mm(a["y"]), mm(b["x"]), mm(b["y"])
    x0, y0, x1, y1 = rect
    if x == u and x in (x0, x1) and y0 <= min(y, v) < max(y, v) <= y1:
        side, span, other = "X_MIN" if x == x0 else "X_MAX", y1 - y0, x1 - x0
    elif y == v and y in (y0, y1) and x0 <= min(x, u) < max(x, u) <= x1:
        side, span, other = "Y_MIN" if y == y0 else "Y_MAX", x1 - x0, y1 - y0
    else:
        raise ValueError("RECORDED_PORTAL_NOT_ON_ROOM_WALL")
    return {
        "world_side": side,
        "edge_class": "LONG_EDGE" if span >= other else "SHORT_EDGE",
        "length_mm": abs(x - u) + abs(y - v),
    }


def interface_review() -> dict[str, Any]:
    sources = json.loads((BASE / "sources.json").read_text())
    manifest = json.loads((BASE / "source_manifest.json").read_text())["files"]
    rows = []
    for record in sources["candidates"]:
        path = BASE / record["input"]
        assert sha(path) == record["projection_sha256"] == manifest[record["input"]]["sha256"]
        assert sha(REPO / record["svg_path"]) == record["svg_sha256"]
        candidate = json.loads(path.read_text())
        app = candidate["engineering_validation"]
        zones = {z["zone_code"]: z for z in app["zones"]}
        rect = box(zones["sorting_packaging_room"])
        interfaces = []
        for route in app["access_results"]:
            if "sorting_packaging_room" not in (route["from_ref"], route["to_ref"]):
                continue
            own_key = (
                "portal_from" if route["from_ref"] == "sorting_packaging_room" else "portal_to"
            )
            other_key = "portal_to" if own_key == "portal_from" else "portal_from"
            own = route[own_key]
            physical = wall(own["segment"], rect)
            assert physical["edge_class"] == own["edge_class"]
            assert physical["length_mm"] == mm(own["clear_width_m"])
            other = route[other_key]
            other_physical = wall(other["segment"], box(zones[other["access_ref"]]))
            packaging = "packaging_material_storage" in (route["from_ref"], route["to_ref"])
            if packaging:
                assert physical["edge_class"] == "SHORT_EDGE"
                assert other_physical["edge_class"] == other["edge_class"] == "LONG_EDGE"
                assert (
                    route["edge_alignment_verified"]
                    and route["route_shape_constraint"] == "STRAIGHT_ONLY"
                )
            interfaces.append(
                {
                    "requirement_identity": route["requirement_identity"],
                    "route_hash": route["canonical_hash"],
                    "from_ref": route["from_ref"],
                    "to_ref": route["to_ref"],
                    "flow_kind": route["flow_kind"],
                    "historical_status": route["status"],
                    "topology": route["topology"],
                    "sorting_portal": own,
                    "sorting_physical_wall": physical,
                    "other_portal": other,
                    "other_physical_wall": other_physical,
                    "centerline": route["centerline"],
                    "corridor_envelope": route["corridor_envelope"],
                    "route_length_m": route["route_length_m"],
                    "packaging_authority_applies": packaging,
                }
            )
        neighbors = []
        for name in (
            "primary_precooling_room",
            "secondary_precooling_room",
            "packaging_material_storage",
            "changing_room",
        ):
            other = box(zones[name])
            sides = []
            if rect[0] == other[2] and min(rect[3], other[3]) > max(rect[1], other[1]):
                sides.append("X_MIN")
            if rect[2] == other[0] and min(rect[3], other[3]) > max(rect[1], other[1]):
                sides.append("X_MAX")
            if rect[1] == other[3] and min(rect[2], other[2]) > max(rect[0], other[0]):
                sides.append("Y_MIN")
            if rect[3] == other[1] and min(rect[2], other[2]) > max(rect[0], other[0]):
                sides.append("Y_MAX")
            neighbors.append(
                {
                    "role": name,
                    "actual_room": zones[name],
                    "world_box_mm": other,
                    "positive_shared_boundary_sides": sides,
                }
            )
        rows.append(
            {
                "candidate_id": record["candidate_id"],
                "candidate_projection_sha256": sha(path),
                "raw_candidate_sha256": record["raw_candidate_sha256"],
                "geometry_hash": candidate["provenance"]["geometry_hash"],
                "application_hash": app["canonical_result_hash"],
                "svg_path": record["svg_path"],
                "svg_sha256": record["svg_sha256"],
                "room": zones["sorting_packaging_room"],
                "world_box_mm": rect,
                "actual_interfaces": interfaces,
                "relative_organization": neighbors,
                "station_positions_and_internal_routes": "UNAVAILABLE",
                "functional_station_layout_pass": None,
                "v2_area_authority_pass": False,
            }
        )
    return {
        "scope": (
            "Exact sealed Portal/room facts only; no new Access search, "
            "station fit or process-flow acceptance"
        ),
        "candidate_count": len(rows),
        "sorting_interface_count": sum(len(r["actual_interfaces"]) for r in rows),
        "layouts": rows,
    }


def envelope_diagnostic(
    components: dict[str, list[tuple[int, int, int, int]] | None], active: list[str] | None
) -> dict[str, Any]:
    missing = [key for key in COMPONENTS if components.get(key) is None]
    if missing or active is None:
        return {
            "status": "OWNER_INPUT_REQUIRED",
            "missing": missing + (["EXPLICIT_STATE_AND_SIMULTANEITY"] if active is None else []),
            "formal_area_m2": None,
            "functional_pass": None,
        }
    if (
        not active
        or any(key not in COMPONENTS for key in active)
        or len(set(active)) != len(active)
    ):
        raise ValueError("INVALID_ACTIVE_COMPONENT_SET")
    shapes = []
    for key in active:
        for rect in components[key] or []:
            if (
                len(rect) != 4
                or any(type(v) is not int for v in rect)
                or rect[2] <= rect[0]
                or rect[3] <= rect[1]
            ):
                raise ValueError("INVALID_INTEGER_MM_ENVELOPE")
            shapes.append((key, rect))
    if not shapes:
        raise ValueError("EMPTY_EXPLICIT_STATE")
    overlaps = []
    for i, (key, a) in enumerate(shapes):
        for other, b in shapes[i + 1 :]:
            area = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
                0, min(a[3], b[3]) - max(a[1], b[1])
            )
            if area:
                overlaps.append({"first": key, "second": other, "positive_overlap_mm2": area})
    xs = sorted({v for _, r in shapes for v in (r[0], r[2])})
    ys = sorted({v for _, r in shapes for v in (r[1], r[3])})
    union = sum(
        (b - a) * (d - c)
        for a, b in zip(xs, xs[1:], strict=False)
        for c, d in zip(ys, ys[1:], strict=False)
        if any(r[0] <= a < b <= r[2] and r[1] <= c < d <= r[3] for _, r in shapes)
    )
    return {
        "status": "EXPLICIT_SYNTHETIC_OR_SUPPLIED_ENVELOPE_DIAGNOSTIC_ONLY",
        "bounding_box_mm": [xs[0], ys[0], xs[-1], ys[-1]],
        "union_area_mm2": union,
        "simultaneous_positive_overlaps_requiring_review": overlaps,
        "time_sharing_automatically_approved": False,
        "formal_area_m2": None,
        "functional_pass": None,
    }


def source_audit() -> dict[str, Any]:
    names = (
        "backend/src/cold_storage/modules/calculations/domain/zone_planning.py",
        "backend/src/cold_storage/modules/layout/application/sorting_dimension_authority.py",
        "backend/src/cold_storage/modules/layout/domain/dimensioning.py",
        "backend/src/cold_storage/modules/layout/domain/dimension_handoff.py",
        "docs/tasks/V2_2-P1C-sorting-packaging-dimension-authority.md",
        "docs/tasks/V2_2-P1D3-flexible-rectangle-handoff-contract.md",
        "docs/architecture/ADR-044-site-constrained-factory-layout-authority.md",
        "docs/tasks/V2_1_2-patch-release-closure-readiness.md",
        "docs/tasks/V2_2_2-version-plan.md",
    )
    files = {}
    for name in names:
        path = REPO / name
        symbols = {}
        constants = {}
        if path.suffix == ".py":
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    symbols[node.name] = {"line": node.lineno, "end_line": node.end_lineno}
            for statement in tree.body:
                if isinstance(statement, ast.Assign):
                    for target in statement.targets:
                        if isinstance(target, ast.Name):
                            constants[target.id] = {
                                "line": statement.lineno,
                                "expression": ast.unparse(statement.value),
                            }
        files[name] = {"sha256": sha(path), "symbols": symbols, "constants": constants}
    return files


def build() -> dict[str, Any]:
    v2 = load(V2, "offline_contract_v2.py")
    stored = json.loads((V2 / "staffing-and-locker-calculation.json").read_text())["examples"]
    new_results = [v2.calculate(row["input"], evidence_root=V2) for row in stored[:2]]
    for old, new in zip(stored[:2], new_results, strict=True):
        assert old["result"] == new
    compatibility = load(
        HERE.parent / "owner-factory-p1-compatibility-readiness-r1", "offline_compatibility.py"
    )
    replay = compatibility.legacy_replay()
    sorting = next(
        z
        for z in replay["canonical_result"]["result"]["zones"]
        if z["zone_code"] == "sorting_packaging_room"
    )
    actual_dimension = json.loads(canonical_json(asdict(dimension_sorting_zone(sorting))))
    assert str(actual_dimension["actual_area_m2"]) == "622.336"
    scenarios = [
        {
            "name": "LEGACY_RAW_20T",
            "source_basis": "RAW_INBOUND_FRUIT",
            "geometry": projection(sorting["table_count"]),
            "authority_scope": "EXISTING_LEGACY_ONLY",
        },
        *[
            {
                "name": name,
                "source_basis": "PACKAGED_PRODUCT_MASS",
                "owner_v2_result_hash": result["offline_result_sha256"],
                "staffing": result["staffing_and_tables"],
                "geometry": projection(result["staffing_and_tables"]["PACKING_TABLE_COUNT"]),
                "authority_scope": "HYPOTHETICAL_LEGACY_GEOMETRY_PROJECTION",
            }
            for name, result in zip(
                ("V2_EQUAL_20T_PRODUCT", "V2_UNEQUAL_20T_PRODUCT"), new_results, strict=True
            )
        ],
    ]
    outputs = {
        "legacy-geometry-authority-audit.json": {
            "reference_head": REFERENCE,
            "files": source_audit(),
            "actual_legacy_sorting_dimension": actual_dimension,
            "legacy_canonical_hash": replay["canonical_result_hash"],
            "legacy_p1_hash": replay["dimension_handoff_hash"],
            "legacy_replay_equals_sealed": True,
            "code_sum_long": "3.0+5.0=8.0",
            "code_sum_short": "3.0+4.6=7.6",
            "sum_meaning": (
                "Arithmetic expressions only; individual physical aisle/body allocations not proven"
            ),
            "equivalent_raw_form": "(5.6*n_long+2.4)*(3*n_short+4.6)",
            "factor": "Legacy P1C long edge once; V2 physical decomposition UNVERIFIED",
            "ranking": [ranking_audit(n) for n in (18, 20, 28)],
        },
        "legacy-projection-scenarios.json": {
            "scenarios": scenarios,
            "legacy_vs_owner_mass_comparison": "NOT_COMPARABLE",
            "new_formal_sorting_area_m2": None,
            "new_factory_total_area_m2": None,
            "equipment_or_internal_fit_pass": None,
        },
        "real-layout-interface-review.json": interface_review(),
        "station-space-requirements.json": {
            "status": "ENGINEERING_PROPOSAL_NOT_APPROVED",
            "components": [
                {
                    "name": key,
                    "actual_project_geometry": None,
                    "status": "UNAVAILABLE",
                    "source_required": True,
                }
                for key in COMPONENTS
            ],
            "state_policy": (
                "All simultaneously active envelopes use actual geometric union "
                "with overlap review; no automatic max or temporal sharing"
            ),
            "normal_state": (
                "Equipment, all3operator activities, supply, outfeed and circulation; "
                "explicit buffers/line connections needed"
            ),
            "cleaning_maintenance_state": (
                "Equipment/guards/service access and retained circulation; "
                "production stopped/shared only if specifically approved"
            ),
            "formula": (
                "L=max(x)-min(x),D=max(y)-min(y) of actual state geometry plus only separately "
                "documented, non-duplicated perimeter allowances"
            ),
            "missing_case": envelope_diagnostic({}, None),
            "actual_station_dimensions": None,
            "formal_area_m2": None,
            "functional_pass": None,
        },
    }
    for name, value in outputs.items():
        (HERE / name).write_bytes(encode(value))
    return outputs


if __name__ == "__main__":
    build()
