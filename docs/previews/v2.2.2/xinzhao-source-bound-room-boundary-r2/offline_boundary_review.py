"""Reuse immutable R1 PDF source/anchor reader; emit private SVG and exact topology."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import fitz

from offline_room_boundary import (
    boundary_result,
    encode,
    rational,
    source_item,
    transform,
)

HERE = Path(__file__).resolve().parent
R1_MANIFEST_SHA = "4dd009feef6d861382ad46c1b657acc26323a57c1c5839ea43faa31086a8c82d"


def r1_reader() -> tuple[Any, Any]:
    root = HERE.parent / "xinzhao-real-drawing-geometry-ingest-r1"
    manifest = (root / "source_manifest.json").read_bytes()
    if hashlib.sha256(manifest).hexdigest() != R1_MANIFEST_SHA:
        raise ValueError("R1_MANIFEST_CHANGED")
    for name, record in json.loads(manifest)["files"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("R1_SOURCE_CHANGED:" + name)
    # Its imports use the original filenames. Do not rewrite the historical delivery.
    sys.path.insert(0, str(root))
    modules = []
    for name in ("offline_drawing_extract", "offline_drawing_validate"):
        spec = importlib.util.spec_from_file_location(name, root / (name + ".py"))
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        modules.append(module)
    return modules[0], modules[1]


def analyze(pdf: Path, review: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    extractor, validator = r1_reader()
    source = extractor.inventory(pdf)
    if source["source_sha256"] != review["source_sha256"]:
        raise ValueError("SOURCE_HASH_MISMATCH")
    if source["pdf_page_count"] != 1:
        raise ValueError("THIS_REVIEW_SELECTS_ONE_SOURCE_PAGE")
    calibration = validator.calibrate(source["pages"][0], review["anchors"])
    metric = calibration["metric_transform"]
    scales = {
        axis: metric[axis]["mm_per_pdf_point"] if metric else None
        for axis in ("X", "Y")
    }
    results = [boundary_result(source, room, scales) for room in review["rooms"]]
    return source, {"dimension_anchor_validation": calibration, "rooms": results}


def svg(pdf: Path, source: dict[str, Any], room: dict[str, Any]) -> bytes:
    x0, y0, x1, y1 = room["source_roi"]
    margin = 24
    box = fitz.Rect(x0 - margin, y0 - margin, x1 + margin, y1 + margin)
    with fitz.open(pdf) as doc:
        image = doc[room["source_page"] - 1].get_pixmap(
            matrix=fitz.Matrix(4, 4), clip=box, alpha=False
        )
    png = base64.b64encode(image.tobytes("png")).decode()
    w, h = box.width, box.height
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{box.x0} {box.y0} {w} {h + 58}">',
        f'<image x="{box.x0}" y="{box.y0}" width="{w}" height="{h}" href="data:image/png;base64,{png}"/>',
    ]
    page = source["pages"][room["source_page"] - 1]
    refs = room["boundary_segments"]
    # Raw source candidates are distinct from reviewed architectural semantics.
    for record in refs:
        coords = [[float(rational(v)) for v in p] for p in record["points"]]
        (a, b), (c, d) = coords
        group = (
            "classified-wall"
            if record["kind"] in {"WALL_SEGMENT", "COLUMN_GEOMETRY"}
            else "source-vector"
        )
        color = "#00734d" if group == "classified-wall" else "#005bb5"
        label = html.escape(
            f"{record['kind']} path={record['path_id']} item={record['item_id']} edge={record.get('edge')}"
        )
        parts.append(
            f'<g class="{group}"><path d="M {a} {b} L {c} {d}" stroke="{color}" stroke-width="0.8" fill="none"><title>{label}</title></path></g>'
        )
    for door in room["door_openings"]:
        (a, b), (c, d) = [[float(rational(v)) for v in p] for p in door["points"]]
        label = html.escape(
            door["door_id"] + " | DOOR OPENING NOT WALL | clear width unavailable"
        )
        parts.append(
            f'<g class="door-opening"><path d="M {a} {b} L {c} {d}" stroke="#de8500" stroke-width="1.1" stroke-dasharray="2 1"><title>{label}</title></path></g>'
        )
        curve = source_item(page, door["swing_ref"])
        points = [transform(p, page["rotation_matrix"]) for p in curve[1:]]
        values = [f"{float(x)} {float(y)}" for x, y in points]
        path = "M " + values[0] + " C " + " ".join(values[1:])
        parts.append(
            f'<g class="source-vector"><path d="{path}" stroke="#005bb5" fill="none" stroke-width="0.45"><title>Original cubic door swing; NOT FLATTENED</title></path></g>'
        )
    if room["boundary_closed"]:
        values = [
            f"{float(rational(x))} {float(rational(y))}"
            for x, y in room["boundary_vertex_sequence"]
        ]
        parts.append(
            '<g class="provisional-boundary"><path d="M '
            + " L ".join(values)
            + ' Z" fill="none" stroke="#9a259d" stroke-width="0.35" stroke-dasharray="1 2"><title>TOPOLOGICAL REFERENCE WITH OPENINGS; NOT CONTINUOUS WALL</title></path></g>'
        )
    for x, y in room["reference_topology"]["unbound_endpoints"]:
        parts.append(
            f'<g class="unverified-gap"><circle cx="{float(rational(x))}" cy="{float(rational(y))}" r="1.4" fill="#c20000"><title>UNBOUND ENDPOINT; NO SNAP</title></circle></g>'
        )
    footer = [
        room["room_id"] + " | SOURCE-BOUND DRAWING REVIEW ONLY",
        "GREEN: WALL FACE | BLUE: SOURCE WINDOW/ARC | ORANGE: DOOR GAP",
        "PURPLE: REFERENCE CLOSURE | RED: UNKNOWN GAP | NO SNAP",
        "FINISHED CLEAR AREA UNAVAILABLE | ENGINEERING APPROVAL UNVERIFIED",
        source["source_sha256"],
    ]
    parts.append(
        f'<rect x="{box.x0}" y="{box.y1}" width="{w}" height="58" fill="#fff0d1"/>'
    )
    for n, line in enumerate(footer):
        size = min(4.4, (w - 6) / (len(line) * 0.66))
        parts.append(
            f'<text x="{box.x0 + 3}" y="{box.y1 + 9 + n * 10}" font-family="sans-serif" font-size="{size}">{html.escape(line)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts).encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("private_review", type=Path)
    parser.add_argument("private_output", type=Path)
    args = parser.parse_args()
    source, result = analyze(args.pdf, json.loads(args.private_review.read_bytes()))
    args.private_output.mkdir(exist_ok=False, parents=True)
    with (args.private_output / "room-results.json").open("xb") as stream:
        stream.write(encode(result))
    for room in result["rooms"]:
        with (args.private_output / (room["room_id"] + "-boundary-review.svg")).open(
            "xb"
        ) as stream:
            stream.write(svg(args.pdf, source, room))


if __name__ == "__main__":
    main()
