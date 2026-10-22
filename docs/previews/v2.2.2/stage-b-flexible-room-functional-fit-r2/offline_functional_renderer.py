"""Deterministic standalone SVG: real source rooms or explicit synthetic scenarios."""

from __future__ import annotations

from fractions import Fraction
from functools import lru_cache
from typing import Any
from xml.sax.saxutils import escape

import offline_functional_fit as fit

COLORS = {"office": "#417da3", "changing_room": "#338579", "coating_room": "#a56a36"}
ROLE_COLORS = {
    "BODY": "#506f94",
    "STANDING": "#2c967f",
    "AISLE": "#a6d8e8",
    "REACH": "#e5b96c",
    "CHAIR": "#ce9f65",
    "DOOR_SWEEP": "#c890c5",
    "SUPPLY": "#9cc36a",
    "OUTFEED": "#ad9473",
    "BUFFER": "#c8bb81",
    "SERVICE": "#d49e81",
}


def fmt(value: Any) -> str:
    return cast_fmt(value)


def cast_fmt(value: Any) -> str:
    # R1 formatter refuses non-terminating rationals instead of silently rounding.
    return str(renderer().fmt(value))


@lru_cache
def renderer() -> Any:
    return fit.dependencies()[1].load_r1()[1]


def text(x: Any, y: Any, value: Any, size: int = 14, color: str = "#203448") -> str:
    return (
        f'<text x="{fmt(x)}" y="{fmt(y)}" font-size="{size}" '
        f'fill="{color}">{escape(str(value))}</text>'
    )


def shell(width: int, height: int, body: str, scale: str) -> bytes:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" data-scale-px-per-mm="{scale}">'
        '<rect width="100%" height="100%" fill="#f6f8fb"/>'
        '<g font-family="sans-serif">' + body + "</g></svg>\n"
    ).encode()


def real_candidate(rooms: list[dict[str, Any]]) -> bytes:
    """Same world XY scale/origin and page size for every real candidate."""
    scale = Fraction(1, 100)
    origin_x, origin_y = 60, 720
    body = text(35, 34, "FUNCTIONAL ROOM REVIEW R2 / " + rooms[0]["CANDIDATE_ID"], 19)
    body += text(
        35, 61, ("ACTUAL SEALED GEOMETRY | INPUT_REQUIRED | NOT FUNCTIONAL APPROVAL"), 14, "#a33d17"
    )
    body += text(35, 86, ("World XY / 0.01 px per mm / same origin and scale on all eight sheets"))
    body += text(
        35,
        109,
        (
            "Colored segments: recorded Portals o"
            "nly; no invented furniture, door swi"
            "ng or internal routes."
        ),
        13,
    )
    for i in range(8):
        x, y = origin_x + i * 100, origin_y - i * 100
        body += f'<path d="M {x} 140 V {origin_y}" stroke="#e1e8ef" fill="none"/>'
        body += text(x, origin_y + 22, str(i * 10) + "m", 11)
        if i <= 5:
            body += f'<path d="M {origin_x} {y} H 860" stroke="#e1e8ef"/>'
            body += text(12, y, str(i * 10) + "m", 11)
    for n, room in enumerate(rooms, 1):
        x0, y0, x1, y1 = room["WORLD_BOUNDS_MM"]
        x, y = origin_x + x0 * scale, origin_y - y1 * scale
        body += (
            f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt((x1 - x0) * scale)}" '
            f'height="{fmt((y1 - y0) * scale)}" fill="{COLORS[room["ZONE_CODE"]]}" '
            'fill-opacity="0.22" stroke="#37526c" stroke-width="1.4"/>'
        )
        body += f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="12" fill="#fff" stroke="#37526c"/>'
        body += text(x - 4, y + 5, n)
        for portal in room["PORTALS"]:
            a, b = portal["WORLD_SEGMENT_MM"]
            body += (
                f'<path d="M {fmt(origin_x + a[0] * scale)} {fmt(origin_y - a[1] * scale)} '
                f'L {fmt(origin_x + b[0] * scale)} {fmt(origin_y - b[1] * scale)}" '
                'stroke="#d93658" stroke-width="4" fill="none"/>'
            )
    for n, room in enumerate(rooms, 1):
        y = 170 + (n - 1) * 178
        body += text(900, y, f"{n}. {room['ZONE_CODE']}", 19, COLORS[room["ZONE_CODE"]])
        body += text(900, y + 26, f"{room['ROOM_WIDTH_MM']} x {room['ROOM_DEPTH_MM']} mm")
        body += text(900, y + 49, "Area " + fmt(Fraction(room["ROOM_AREA_MM2"], 1000000)) + " m2")
        body += text(
            900,
            y + 72,
            f"Recorded portals: {len(room['PORTALS'])}; indoor access NOT_EVALUATED",
            12,
        )
        body += text(900, y + 95, "Missing: project staff/model, clear finish, operation", 12)
        body += text(900, y + 116, ("door swing, internal circulation, cleaning/maintenance"), 12)
        body += text(
            900,
            y + 137,
            "INPUT_REQUIRED / source geometry is not clear usable space",
            12,
            "#a33d17",
        )
    body += text(35, 785, "Geometry source: " + rooms[0]["SOURCE_GEOMETRY_HASH"], 11)
    body += text(35, 810, "Raw candidate SHA256: " + rooms[0]["RAW_CANDIDATE_SHA256"], 11)
    body += text(
        35,
        839,
        (
            "Office adjacency is NOT a door. Port"
            "al presence is NOT indoor accessibil"
            "ity. Truck BLOCKED / P2D=0."
        ),
        13,
    )
    return shell(1470, 870, body, "0.01")


def synthetic(documents: list[dict[str, Any]], results: list[dict[str, Any]]) -> bytes:
    geo = fit.dependencies()[0]
    body = text(28, 32, documents[0]["MODEL"] + " / SOFTWARE GEOMETRY EXAMPLES", 19)
    body += text(
        28,
        58,
        ("SYNTHETIC_TEST_GEOMETRY | NOT PROJECT DIMENSIONS | NO P1 AUTHORITY"),
        15,
        "#a33d17",
    )
    scale = Fraction(1, 20)
    states = ("NORMAL_OPERATION", "MAINTENANCE")
    for index, (doc, result) in enumerate(zip(documents, results, strict=True)):
        base_x = 35 + index * 730
        body += text(base_x, 92, doc["EXAMPLE_NAME"], 17)
        body += text(base_x, 116, result["FUNCTIONAL_FIT_STATUS"], 12, "#a33d17")
        for row, state in enumerate(states):
            top = 155 + row * 365
            room = doc["ROOM_BOUNDS_MM"]
            height = Fraction(room[3] - room[1]) * scale
            body += text(base_x, top - 12, state, 13)
            body += (
                f'<rect x="{base_x}" y="{top}" width="{fmt((room[2] - room[0]) * scale)}" '
                f'height="{fmt(height)}" fill="#fff" stroke="#263f57" stroke-width="2"/>'
            )
            clear = doc["CONFIGURATION"]["finished_clear_bounds_mm"]
            body += (
                f'<rect x="{fmt(base_x + clear[0] * scale)}" '
                f'y="{fmt(top + height - clear[3] * scale)}" '
                f'width="{fmt((clear[2] - clear[0]) * scale)}" '
                f'height="{fmt((clear[3] - clear[1]) * scale)}" '
                'fill="none" stroke="#c42c4d" stroke-width="2" stroke-dasharray="7 4"/>'
            )
            state_conflicts = result["STATE_RESULTS"].get(state, {}).get("CONFLICTS", [])
            hard_ids = {
                key
                for c in state_conflicts
                if c["CLASS"] == "HARD_GEOMETRY_CONFLICT"
                for key in c["COMPONENT_IDS"]
            }
            for component in doc["COMPONENTS"]:
                if state not in component["ACTIVE_STATES"]:
                    continue
                x0, y0, x1, y1 = geo.transform_rect(
                    component["BOUNDS_MM"], [component["TRANSFORM"]]
                )
                x, y = base_x + x0 * scale, top + height - y1 * scale
                color = ROLE_COLORS[component["ROLE"]]
                stroke = "#ce2146" if component["ID"] in hard_ids else "#65778a"
                body += (
                    f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt((x1 - x0) * scale)}" '
                    f'height="{fmt((y1 - y0) * scale)}" fill="{color}" '
                    f'fill-opacity="0.60" stroke="{stroke}" stroke-width="2"/>'
                )
                body += text(x + 3, y + 13, component["ID"], 10)
            for route in doc["ROUTES"]:
                if state not in route["ACTIVE_STATES"]:
                    continue
                points = " ".join(
                    fmt(base_x + x * scale) + "," + fmt(top + height - y * scale)
                    for x, y in route["POINTS_MM"]
                )
                body += (
                    f'<polyline points="{points}" fill="none" stroke="#206274" stroke-width="2"/>'
                )
            for portal in doc["PORTALS"]:
                a, b = portal["SEGMENT_MM"]
                body += (
                    f'<path d="M {fmt(base_x + a[0] * scale)} {fmt(top + height - a[1] * scale)} '
                    f'L {fmt(base_x + b[0] * scale)} {fmt(top + height - b[1] * scale)}" '
                    'stroke="#d93658" stroke-width="4"/>'
                )
            conflicts = result["STATE_RESULTS"].get(state, {}).get("CONFLICTS", [])
            body += text(
                base_x,
                top + 320,
                f"Room {room[2]} x {room[3]} / clear {clear[2]} x {clear[3]} mm; "
                f"conflicts {len(conflicts)}",
                12,
            )
            if conflicts:
                primary = next((c for c in conflicts if c["CODE"] == "ACTIVE_BODY"), conflicts[0])
                body += text(base_x, top + 342, primary["CODE"], 11, "#a33d17")
    body += text(
        28,
        902,
        (
            "BODY blue | STANDING green | AISLE c"
            "yan | REACH/CHAIR amber | SERVICE sa"
            "lmon | Portal red"
        ),
        13,
    )
    body += text(
        28,
        930,
        (
            "Negative proof applies ONLY to the s"
            "upplied configuration/orientation. O"
            "ther layouts are not excluded."
        ),
        13,
    )
    return shell(1480, 955, body, "0.05")
