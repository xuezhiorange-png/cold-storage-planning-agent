"""Private source-aligned review overlays. Rectangles are review ROIs, not walls."""

from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path
from typing import Any

import fitz

from offline_drawing_extract import inventory
from offline_drawing_validate import validate


def render(pdf: Path, review: dict[str, Any], layer: str) -> bytes:
    source = inventory(pdf)
    validate(source, review)
    if layer not in {"axes", "rooms", "mapping"}:
        raise ValueError("UNKNOWN_LAYER")
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3370 2504">']
    if source["pdf_page_count"] != 1:
        raise ValueError("SELECT_SINGLE_PAGE_FOR_REVIEW_RENDER")
    with fitz.open(pdf) as document:
        page = document[0]
        w, h = page.rect.width, page.rect.height
        parts[0] = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h + 120}">'
        )
        image = base64.b64encode(
            page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).tobytes("png")
        ).decode()
    parts.append(
        f'<image width="{w}" height="{h}" href="data:image/png;base64,{image}"/>'
    )
    parts.append('<g fill="none" stroke="#c05216" stroke-width="2">')
    objects = [] if layer == "axes" else review["objects"]
    if layer == "mapping":
        selected = {
            i for m in review.get("logical_mapping", []) for i in m["physical_objects"]
        }
        objects = [o for o in objects if o["object_id"] in selected]
    for obj in objects:
        x0, y0, x1, y1 = obj["source_region"]
        label = html.escape(
            obj["object_id"] + " | " + str(obj.get("source_label")), quote=True
        )
        parts.append(
            f'<rect id="{html.escape(obj["object_id"], quote=True)}" x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}"><title>{label}; REVIEW ROI, NOT WALL</title></rect>'
        )
        parts.append(
            f'<text x="{x0 + 3}" y="{y0 + 15}" stroke="none" fill="#a43200" font-size="13">{html.escape(obj["object_id"])}</text>'
        )
    if layer == "axes":
        page_data = source["pages"][0]
        from offline_drawing_validate import line_points

        for anchor in review.get("anchors", []):
            (x0, y0), (x1, y1) = line_points(page_data, anchor)
            parts.append(
                f'<path d="M {x0} {y0} L {x1} {y1}" stroke="#007b87" stroke-width="6"><title>Dimension source path {anchor["path_id"]}</title></path>'
            )
    parts.append("</g>")
    note = "PRIVATE REVIEW | ROI NOT ROOM BOUNDARY | ENGINEERING AUTHORITY UNVERIFIED"
    parts.append(f'<rect y="{h}" width="{w}" height="120" fill="#fff2d8"/>')
    parts.append(f'<text x="40" y="{h + 45}" font-size="30">{note}</text>')
    parts.append(
        f'<text x="40" y="{h + 90}" font-size="24">{source["source_sha256"]} | {layer}</text></svg>'
    )
    return "\n".join(parts).encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("review", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    review = json.loads(args.review.read_bytes())
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for layer in ("axes", "rooms", "mapping"):
        with (args.output_directory / f"{layer}.svg").open("xb") as stream:
            stream.write(render(args.pdf, review, layer))


if __name__ == "__main__":
    main()
