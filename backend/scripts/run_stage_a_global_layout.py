"""Reproducible controlled server generation from a real business/site fixture.

No historical candidate is opened. Run from backend with uv run python.
Output is persistent and must be an empty/new evidence directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from cold_storage.bootstrap.global_composition import generate_controlled_global_layout
from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.application.p1_project_handoff import build_p1_project_handoff
from cold_storage.modules.layout.application.site_geometry import validate_site_geometry
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1, normalize_polygon
from cold_storage.modules.layout.domain.svg_projection import (
    SvgProjectionTransformV1,
    _element,
    _polygon_points,
    _text,
    build_projection_payload,
)


def dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")


def diagnostic_svg(result: dict[str, Any], site: Any) -> str:
    """Existing engineering SVG primitives; no invented/filled footprint.

    Model witnesses are explicitly not native Access PASS. Coordinates are
    read solely from this invocation's candidate and witness JSON.
    """
    geometry = site.to_dict()
    boundary = normalize_polygon(
        geometry["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    transform = SvgProjectionTransformV1(
        Decimal(0),
        Decimal(max(y for _, y in boundary)) / 1000,
        Decimal(10),
        Decimal(35),
        Decimal(100),
    )
    parts = [
        _text(
            35,
            30,
            "STAGE A — CONCEPT ONLY / NOT ENGINEERING ACCEPTED",
            attrs={"fill": "#ad2831", "font-size": 20},
        ),
        _text(
            35,
            58,
            "Model Access witnesses shown; native validation incomplete. Truck NOT EVALUATED.",
            attrs={"font-size": 14},
        ),
        _element(
            "polygon",
            attrs={
                "points": _polygon_points(boundary, transform),
                "fill": "#fafafa",
                "stroke": "#374151",
                "stroke-width": 2,
            },
        ),
    ]
    for obstacle in geometry["obstacles"]["hard_obstacles"]:
        polygon = normalize_polygon(obstacle["footprint"], allow_numeric_string=True)
        parts.append(
            _element(
                "polygon",
                attrs={
                    "points": _polygon_points(polygon, transform),
                    "fill": "#b45309",
                    "fill-opacity": 0.4,
                },
            )
        )
    rectangles = {}
    for index, row in enumerate(result["proposal"]["zones"], 1):
        r = PlacedRectangleV1(
            row["zone_code"],
            Decimal(row["x"]),
            Decimal(row["y"]),
            Decimal(row["width_m"]),
            Decimal(row["depth_m"]),
            row["rotation_deg"],
        )
        rectangles[row["zone_code"]] = r
        parts.append(
            _element(
                "polygon",
                attrs={
                    "data-zone-code": row["zone_code"],
                    "points": _polygon_points(r.polygon_mm, transform),
                    "fill": f"hsl({index * 31} 50% 85%)",
                    "stroke": "#334155",
                    "stroke-width": 1,
                },
            )
        )
        cx = sum(x for x, _ in r.polygon_mm) // 4
        cy = sum(y for _, y in r.polygon_mm) // 4
        parts.append(
            _text(
                *transform.point((cx, cy)),
                str(index),
                attrs={"font-size": 13, "text-anchor": "middle"},
            )
        )
        parts.append(
            _text(830, 115 + index * 32, f"{index:02} {row['zone_code']}", attrs={"font-size": 14})
        )
        parts.append(
            _text(
                850,
                131 + index * 32,
                (
                    f"{row['width_m']} × {row['depth_m']} m | "
                    f"{row['actual_area_m2']} m² | {row['rotation_deg']}°"
                ),
                attrs={"font-size": 12, "fill": "#475569"},
            )
        )
    for route in result["proposal"]["routes"]:
        color = "#2563eb" if route["from_ref"] in {"main_entrance", "changing_room"} else "#15803d"
        for x, y, right, top in route["envelopes_mm"]:
            parts.append(
                _element(
                    "polygon",
                    attrs={
                        "points": _polygon_points(
                            ((x, y), (right, y), (right, top), (x, top)), transform
                        ),
                        "fill": color,
                        "fill-opacity": 0.22,
                    },
                )
            )
        points = " ".join(
            f"{x},{y}" for x, y in (transform.point(tuple(p)) for p in route["path_mm"])
        )
        if points:
            parts.append(
                _element(
                    "polyline",
                    attrs={
                        "points": points,
                        "fill": "none",
                        "stroke": color,
                        "stroke-width": 2,
                        "stroke-dasharray": "5 3",
                    },
                )
            )
        for key in ("portal_from_center_mm", "portal_to_center_mm"):
            x, y = transform.point(tuple(route[key]))
            parts.append(_element("circle", attrs={"cx": x, "cy": y, "r": 3, "fill": color}))
        if route["topology"] == "DIRECT_SHARED_EDGE":
            # Local transfer direction at the actual shared portal, not a
            # fabricated full interior transport route through either room.
            px, py = route["portal_from_center_mm"]
            poly = rectangles[route["from_ref"]].polygon_mm
            left, right = min(x for x, _ in poly), max(x for x, _ in poly)
            top = max(y for _, y in poly)
            dx, dy = (
                (1, 0)
                if px == right
                else (-1, 0)
                if px == left
                else (0, 1)
                if py == top
                else (0, -1)
            )
            start = transform.point((px - 400 * dx, py - 400 * dy))
            end = transform.point((px + 400 * dx, py + 400 * dy))
            parts.append(
                _element(
                    "line",
                    attrs={
                        "x1": start[0],
                        "y1": start[1],
                        "x2": end[0],
                        "y2": end[1],
                        "stroke": color,
                        "stroke-width": 2,
                    },
                )
            )
            arrow = (
                (end[0], end[1]),
                (end[0] - 5 * dx + 3 * dy, end[1] + 5 * dy + 3 * dx),
                (end[0] - 5 * dx - 3 * dy, end[1] + 5 * dy - 3 * dx),
            )
            parts.append(
                _element(
                    "polygon",
                    attrs={"points": " ".join(f"{x},{y}" for x, y in arrow), "fill": color},
                )
            )
    loading = result.get("placement", {}).get("shipping_loading_face_segment")
    if loading:
        a, b = [
            transform.point(
                tuple(int(Decimal(str(loading[end][axis])) * 1000) for axis in ("x", "y"))
            )
            for end in ("start", "end")
        ]
        parts.append(
            _element(
                "line",
                attrs={
                    "x1": a[0],
                    "y1": a[1],
                    "x2": b[0],
                    "y2": b[1],
                    "stroke": "#b45309",
                    "stroke-width": 4,
                },
            )
        )
    witness = result["proposal"].get("model_witness_footprint", {})
    if witness.get("derived"):
        footprint = normalize_polygon(witness["polygon"], allow_numeric_string=True)
        parts.append(
            _element(
                "polygon",
                attrs={
                    "points": _polygon_points(footprint, transform),
                    "fill": "none",
                    "stroke": "#b91c1c",
                    "stroke-width": 2,
                    "stroke-dasharray": "7 4",
                },
            )
        )
    for key in ("main_entrance", "truck_entrance"):
        raw = geometry["entrances"][key]
        entrance_points = [
            tuple(int(Decimal(str(raw[end][axis])) * 1000) for axis in ("x", "y"))
            for end in ("start", "end")
        ]
        a, b = (transform.point((p[0], p[1])) for p in entrance_points)
        parts.append(
            _element(
                "line",
                attrs={
                    "x1": a[0],
                    "y1": a[1],
                    "x2": b[0],
                    "y2": b[1],
                    "stroke": "#111827",
                    "stroke-width": 4,
                },
            )
        )
        parts.append(
            _text(
                a[0] - 10,
                a[1] - 8,
                key,
                attrs={
                    "font-size": 11,
                    "text-anchor": "end" if key == "main_entrance" else "start",
                },
            )
        )
    parts.append(
        _text(
            35,
            690,
            (
                "Blue: personnel | Green: material transfer | Dots: portals | "
                "Brown: Shipping loading face"
            ),
            attrs={"font-size": 14},
        )
    )
    parts.append(
        _text(
            35,
            715,
            "Building footprint: "
            + (
                "native witness derived, not final application acceptance"
                if witness.get("derived")
                else "NOT DERIVED — no fabricated perimeter shown"
            ),
            attrs={"font-size": 14, "fill": "#ad2831"},
        )
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1380 750">'
        + "".join(parts)
        + "</svg>"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output
    root.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    fixture = (
        Path(__file__).resolve().parents[1]
        / "tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"
    )
    raw = fixture.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e"
    )
    source = json.loads(raw)
    business = {
        k: source[k]
        for k in (
            "daily_inbound_mass_kg",
            "finished_storage_days",
            "frozen_storage_days",
            "main_packaging_storage_days",
            "auxiliary_packaging_storage_days",
        )
    }
    dump(
        root / "solver_input.json",
        {
            "business_parameters": business,
            "source_fixture": source,
            "fixture_sha256": hashlib.sha256(raw).hexdigest(),
            "historical_candidate_opened": False,
        },
    )
    plan = asdict(
        ColdRoomZonePlanner().plan(
            ColdRoomZonePlanInput(
                **business,
                working_time_h_per_day=16,
                packaging_storage_days=3,
                precooling_required_ratio=1,
            )
        )
    )
    p1 = build_p1_project_handoff(plan, source["truck_access"])
    site = validate_site_geometry(
        {"site_constraints": source["site_constraints"], "truck_access": source["truck_access"]},
        plan,
        p1_handoff=p1,
    )
    binding = bind_layout_authority(plan, p1, site)
    dump(
        root / "server_authorities.json",
        {
            "canonical_zone_plan": plan,
            "p1_handoff": p1.to_dict(),
            "typed_site": site.to_dict(),
            "dimension_authorities": binding.dimension_authorities,
            "access_requirements": binding.access_requirements,
            "spatial_relationships": binding.spatial_relationships,
        },
    )
    try:
        result = generate_controlled_global_layout(plan, p1.to_dict(), site)
        dump(root / "new_generated_candidate.json", result)
        dump(
            root / "solver_provenance.json",
            {
                k: v
                for k, v in result.items()
                if k not in {"proposal", "engineering_validation", "placement"}
            },
        )
        dump(root / "resource_ledger.json", result["resource_ledger"])
        dump(
            root / "independent_validation.json",
            result.get("independent_validation", {"status": "NOT_EVALUATED"}),
        )
        app = result.get("engineering_validation", {})
        observations = {
            row["identity"]: row for row in result["resource_ledger"]["native_requirement_results"]
        }
        native_rows = [
            observations.get(
                r["identity"],
                {
                    "identity": r["identity"],
                    "status": "NOT_EVALUATED",
                    "reason": "APPLICATION_INTERRUPTED_BEFORE_REQUIREMENT",
                },
            )
            for r in binding.access_requirements
            if r["flow_kind"] != "TRUCK"
        ]
        dump(
            root / "access_validation.json",
            app
            or {
                "application_status": "INTERRUPTED",
                "error": result.get("engineering_validation_error"),
                "requirements": native_rows,
                "native_pass_count": sum(r["status"] == "PASS" for r in native_rows),
                "resource_interrupted_count": sum(
                    r["status"] == "RESOURCE_INTERRUPTED" for r in native_rows
                ),
                "not_evaluated_count": sum(r["status"] == "NOT_EVALUATED" for r in native_rows),
            },
        )
        dump(
            root / "building_footprint_validation.json",
            {
                "actual_application_footprint": {k: v for k, v in app.items() if "building" in k},
                "actual_application_status": "COMPLETED"
                if app
                else "NOT_EVALUATED_APPLICATION_INTERRUPTED",
                "model_witness_footprint": result["proposal"].get(
                    "model_witness_footprint", {"status": "NOT_EVALUATED"}
                ),
                "scope": "Model witness footprint is not native application acceptance",
            },
        )
        if app.get("building_footprint"):
            projected = build_projection_payload(
                app, site.to_dict(), source_layout_hash=canonical_hash(app)
            )
            svg = projected["svg"]
            svg = svg.replace(
                "<svg ", '<svg data-stage="STAGE_A_CONCEPT_ONLY_TRUCK_NOT_EVALUATED" ', 1
            )
            (root / "generated_factory_layout.svg").write_text(svg)
        elif result["proposal"].get("zones"):
            (root / "generated_factory_layout.svg").write_text(diagnostic_svg(result, site))
        summary = {
            "status": result["proposal"]["solver_status"],
            "zones": len(result["proposal"].get("zones", [])),
            "independent": result.get("independent_validation"),
            "access_pass_count": app.get("access_pass_count"),
            "building": app.get("building_footprint_derived"),
            "seconds": time.monotonic() - started,
        }
        dump(root / "run_summary.json", summary)
        print(json.dumps(summary, default=str))
    except Exception as error:
        dump(
            root / "execution_failure.json",
            {
                "type": type(error).__name__,
                "message": str(error),
                "seconds": time.monotonic() - started,
            },
        )
        raise


if __name__ == "__main__":
    main()
