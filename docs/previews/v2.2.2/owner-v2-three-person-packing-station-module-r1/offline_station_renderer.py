"""Deterministic, self-contained SVG projections of source-bound offline geometry."""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from html import escape
from pathlib import Path
from typing import Any

import offline_station_geometry as geo

COLORS = {
    geo.TYPES[0]: "#c5ccd5",
    geo.TYPES[1]: "#c6e8e0",
    geo.TYPES[2]: "#ffe0a1",
    geo.TYPES[3]: "#dbc9f0",
    geo.TYPES[4]: "#d3e8fa",
    geo.TYPES[5]: "#f8cbb9",
}


def fmt(value: Fraction | int) -> str:
    q = Fraction(value)
    denominator = q.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise geo.InputError("NON_TERMINATING_SVG_COORDINATE_NOT_APPROXIMATED")
    places = max(twos, fives)
    scaled = abs(q.numerator) * 2 ** (places - twos) * 5 ** (places - fives)
    digits = str(scaled).zfill(places + 1)
    body = digits if places == 0 else digits[:-places] + "." + digits[-places:]
    return ("-" if q < 0 else "") + body


def text(x: Any, y: Any, value: str, size: int = 13, fill: str = "#172b42") -> str:
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}">{escape(value)}</text>'


def render(doc: dict[str, Any], evidence_root: Path, state: str = "NORMAL_PRODUCTION") -> bytes:
    if state not in geo.STATES:
        raise geo.InputError("UNKNOWN_RENDER_STATE")
    result = geo.evaluate(doc, evidence_root)
    if result["GEOMETRY_INPUT_STATUS"] != "VALID_SOURCE_BOUND_OFFLINE_INPUT":
        body = text(30, 45, "INPUT REQUIRED — NO DIMENSIONED PROJECT DRAWING", 18)
        body += text(30, 85, "SCHEMATIC_NOT_TO_SCALE | NOT ENGINEERING APPROVED")
        body += text(30, 125, str(result["DIAGNOSTICS"][0]))
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="180" '
            'viewBox="0 0 960 180"><rect width="960" height="180" fill="#fff7ee"/>'
            '<g font-family="sans-serif">' + body + "</g></svg>\n"
        ).encode()
    components, routes, operators = geo.flatten(doc, evidence_root)
    b = [Fraction(v) for v in result["MODULE_BOUNDS"]]
    x0, y0, x1, y1 = b
    scale = Fraction(1, 10)
    scene_w, scene_h = (x1 - x0 + 800) * scale, (y1 - y0 + 800) * scale
    width, height = max(Fraction(900), scene_w + 350), max(Fraction(650), scene_h + 130)
    mark = (
        "SYNTHETIC_TEST_GEOMETRY"
        if doc["MODE"] == "SYNTHETIC_TEST"
        else "OWNER_PROJECT_UNAPPROVED_GEOMETRY"
    )
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(width)}" '
        f'height="{fmt(height)}" viewBox="0 0 {fmt(width)} {fmt(height)}" '
        'data-scale-px-per-mm="0.1">',
        '<rect width="100%" height="100%" fill="#f7f9fc"/>',
        '<g font-family="sans-serif">',
        text(24, 30, "PACKING STATION MODULE R1 / " + doc["ARRANGEMENT"], 21),
        text(24, 56, mark + " | " + state, 15, "#a33d17"),
        text(24, 79, "NOT PROJECT APPROVED · NO P1 AREA · XY y-up · integer mm inputs", 13),
        '<g transform="translate(40,115) scale(0.1)">',
    ]
    labeled: set[geo.Rect] = set()
    for component in sorted(
        components, key=lambda c: (c["ROLE"] in ("REACH", "STANDING"), c["KEY"])
    ):
        x, y, u, v = component["RECT"]
        active = state in component["ACTIVE_STATES"]
        color = COLORS[component["COMPONENT_TYPE"]]
        opacity = "0.12" if not active else "0.40" if component["ROLE"] == "REACH" else "0.80"
        dash = ' stroke-dasharray="55 30"' if component["ROLE"] == "REACH" or not active else ""
        out.append(
            f'<rect x="{fmt(x - x0 + 400)}" y="{fmt(y1 - v + 400)}" '
            f'width="{fmt(u - x)}" height="{fmt(v - y)}" fill="{color}" '
            f'fill-opacity="{opacity}" stroke="#5b7186" stroke-width="8"{dash}/>'
        )
        if (
            active
            and component["ROLE"] != "REACH"
            and u - x >= 500
            and component["RECT"] not in labeled
        ):
            labeled.add(component["RECT"])
            out.append(
                text(
                    fmt(x - x0 + 430),
                    fmt(y1 - v + 560),
                    component["KEY"]
                    .replace("STAND_", "OP")
                    .replace("_AISLE", "")
                    .replace("ASSEMBLY/", "ASM/"),
                    94,
                )
            )
            if component["ROLE"] == "BODY":
                out.append(
                    text(
                        fmt(x - x0 + 430),
                        fmt(y1 - v + 720),
                        fmt(u - x) + " x " + fmt(v - y) + " mm",
                        100,
                    )
                )
    for route in routes:
        if state not in route["ACTIVE_STATES"]:
            continue
        points = " ".join(
            fmt(p[0] - x0 + 400) + "," + fmt(y1 - p[1] + 400) for p in route["POINTS"]
        )
        color = (
            "#227c69"
            if route["FLOW_KIND"] == "PERSONNEL"
            else "#d1841b"
            if route["FLOW_KIND"] == "MATERIAL_IN"
            else "#7043a0"
        )
        out.append(
            f'<polyline points="{points}" stroke="{color}" stroke-opacity="0.22" '
            f'stroke-width="{route["WIDTH_MM"]}" stroke-linejoin="miter" '
            'stroke-linecap="square" fill="none"/>'
        )
        out.append(f'<polyline points="{points}" stroke="{color}" stroke-width="15" fill="none"/>')
    if state == "NORMAL_PRODUCTION":
        for op in operators:
            px, py = (Fraction(v) for v in op["POSITION"])
            dx, dy = (Fraction(v) for v in op["DIRECTION"])
            sx, sy = px - x0 + 400, y1 - py + 400
            ex, ey = sx + dx * 300, sy - dy * 300
            out.append(
                f'<path d="M {fmt(sx)} {fmt(sy)} L {fmt(ex)} {fmt(ey)}" '
                'stroke="#125947" stroke-width="22"/>'
            )
            # Arrow head is local geometry, not an external SVG resource.
            arrow_points = [
                (ex, ey),
                (ex - dx * 95 - dy * 55, ey + dy * 95 - dx * 55),
                (ex - dx * 95 + dy * 55, ey + dy * 95 + dx * 55),
            ]
            out.append(
                '<polygon points="'
                + " ".join(fmt(a) + "," + fmt(b) for a, b in arrow_points)
                + '" fill="#125947"/>'
            )
    out.extend(
        [
            text(150, 180, "Y+", 110),
            text(fmt(scene_w * 10 - 250), fmt(scene_h * 10 - 160), "X+", 110),
            "</g>",
        ]
    )
    legend_x = fmt(scene_w + 70)
    lines = [
        "SOURCE / STATUS",
        "All depicted dimensions: " + mark,
        "Input source IDs: " + ", ".join(sorted(doc["SOURCES"])),
        "Source content SHA: " + next(iter(doc["SOURCES"].values()))["SHA256"][:24],
        "Input SHA256: " + result["INPUT_SHA256"][:24],
        "Same scale: 0.1 px per mm in every SVG",
        "Uncalibrated: all project fit / aisle values",
        "Each station: exactly OP1, OP2, OP3",
        "Solid gray: equipment body",
        "Green: standing; dashed green: reach",
        "Amber: supply | Purple: outfeed",
        "Blue: circulation | Coral: service",
        "Faded: inactive in displayed state",
        "Lines: full-width paths + centerlines",
        "Arrows: declared work direction",
        "Overlap is not automatically permitted",
        "Envelope: " + fmt(x1 - x0) + " x " + fmt(y1 - y0) + " mm",
        "Displayed state union: "
        + str(result["STATES"][state]["GEOMETRIC_UNION_AREA_MM2"])
        + " mm2",
        "Bounding rectangle differs from union",
        "FUNCTIONAL_ROOM_AREA = null",
        "Physical collisions: " + str(len(result["GEOMETRIC_COLLISIONS"])),
        "Functional reviews: " + str(len(result["FUNCTIONAL_CONFLICTS"])),
        "Turnover time / safety still require review",
    ]
    for i, line in enumerate(lines):
        out.append(text(legend_x, 125 + i * 21, line, 11 if i else 15))
    out.append("</g></svg>\n")
    return "\n".join(out).encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--state", choices=geo.STATES, default=geo.STATES[0])
    args = parser.parse_args()
    print(
        render(json.loads(args.input.read_bytes()), args.evidence_root, args.state).decode(), end=""
    )


if __name__ == "__main__":
    main()
