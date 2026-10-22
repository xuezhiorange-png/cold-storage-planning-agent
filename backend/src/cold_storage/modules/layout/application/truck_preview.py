"""Callable JSON application/CLI entry for additive parameterized Truck preview.

Run: python -m cold_storage.modules.layout.application.truck_preview < input.json
Existing Tool 7 and V1 handoff/typed-Site/P2D source contracts are untouched.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from html import escape
from typing import Any, cast

from cold_storage.modules.layout.domain.truck_parameter_input import preview_parameterized_truck


def invoke_truck_preview(arguments: object) -> dict[str, Any]:
    """JSON-ready application entry, also directly callable by service adapters."""
    result = preview_parameterized_truck(arguments)
    body = cast(dict[str, Any], json.loads(json.dumps(result, default=str)))
    truck = body.get("truck", {})
    if body["status"] == "PASS" and truck.get("truck_route_validated"):
        assert isinstance(arguments, Mapping)
        site = arguments["site_geometry"]
        points = [p for envelope in truck["truck_envelopes"] for p in envelope["points"]]
        points.extend(site["effective_buildable_boundary"]["points"])
        xs = [float(p["x"]) for p in points]
        ys = [float(p["y"]) for p in points]
        # Floats below are projection only; every accepted geometry predicate
        # already used exact millimetres. No visual relocation of coordinates.
        x, y = min(xs) - 1, min(ys) - 1
        width, height = max(xs) - x + 1, max(ys) - y + 1
        polygons = "".join(
            '<polygon points="'
            + " ".join(escape(str(p["x"])) + "," + escape(str(p["y"])) for p in envelope["points"])
            + '" fill="#2b87c8" fill-opacity="0.25" stroke="#17658c" stroke-width="0.08"/>'
            for envelope in truck["truck_envelopes"]
        )
        context = ""
        for polygon, color in (
            (site["effective_buildable_boundary"], "#f4f7fa"),
            *((p, "#444") for p in site["hard_obstacles"]),
            *((p, "#b3dac2") for p in site["personnel_corridors"]),
        ):
            coords = " ".join(
                escape(str(p["x"])) + "," + escape(str(p["y"])) for p in polygon["points"]
            )
            context += (
                f'<polygon points="{coords}" fill="{color}" stroke="#667" stroke-width="0.1"/>'
            )
        for z in site["zones"]:
            w, d = float(z["width_m"]), float(z["depth_m"])
            if z["rotation_deg"] == 90:
                w, d = d, w
            zx, zy = float(z["x"]), float(z["y"])
            context += (
                f'<rect x="{zx}" y="{zy}" width="{w}" height="{d}" '
                'fill="#efe0bf" stroke="#765" stroke-width="0.1"/>'
                f'<text x="{zx + 0.2}" y="{zy + 0.9}" font-size="0.7">'
                f"{escape(z['zone_code'])}</text>"
            )
        for segment, color in (
            (arguments["entrance"]["clear_opening_segment"], "#c33"),
            (arguments["shipping_loading_face"], "#b70"),
        ):
            a, b = segment["start"], segment["end"]
            context += (
                f'<line x1="{escape(str(a["x"]))}" y1="{escape(str(a["y"]))}" '
                f'x2="{escape(str(b["x"]))}" y2="{escape(str(b["y"]))}" '
                f'stroke="{color}" stroke-width="0.25"/>'
            )
        label = (
            "SYNTHETIC_TEST_ONLY"
            if body["SYNTHETIC_TEST_ONLY"]
            else "PROJECT_TEMPLATE_PREVIEW_REQUIRES_REVIEW"
        )
        body["svg"] = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="600" '
            f'viewBox="{x} {y} {width} {height}"><title>{label}</title>{context}{polygons}'
            f'<text x="{x}" y="{y + 0.7}" font-size="0.5">{label}; coordinates: m</text></svg>'
        )
    return body


def main() -> None:
    """Bounded stdin JSON; result stdout only. No paths/network authority lookup."""
    raw = sys.stdin.buffer.read(12_000_001)
    if len(raw) > 12_000_000:
        arguments: object = None
    else:
        try:
            arguments = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            arguments = None
    print(json.dumps(invoke_truck_preview(arguments), ensure_ascii=False))


if __name__ == "__main__":
    main()
