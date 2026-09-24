"""Render one-off visual overlays for the V2.2.2 P0C normalized references.

This evidence utility is intentionally outside application/runtime packages.
It accepts Owner-provided source PDF paths at invocation time; no source PDF
path or original drawing binary is stored in the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / "docs/tasks/evidence/v2_2_2_p0c"
REFERENCES = {
    "GD-001_ZHUYUAN": "GD-001_ZHUYUAN.normalized-layout.json",
    "GD-002_XIAOXIANG": "GD-002_XIAOXIANG.normalized-layout.json",
    "GD-003_MOUDING": "GD-003_MOUDING.normalized-layout.json",
    "GD-004_SHUANGLONGYING": "GD-004_SHUANGLONGYING.normalized-layout.json",
    "GD-005_PANLONG": "GD-005_PANLONG.normalized-layout.json",
}
GROUP_COLORS = {
    "RAW_SIDE_GROUP": (49, 93, 119),
    "PROCESSING_CORE_GROUP": (139, 91, 59),
    "FINISHED_SIDE_GROUP": (54, 112, 91),
    "COLD_STORAGE_GROUP": (103, 96, 143),
    "SUPPORT_GROUP": (128, 87, 105),
}


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Verdana.ttf",
    ):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _verified_source_sha256(source: Path, expected_sha256: str) -> str:
    actual_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError("source PDF hash does not match normalized reference provenance")
    return actual_sha256


def _page_point(
    x: float,
    y: float,
    page_bbox: list[float],
    image_size: tuple[int, int],
) -> tuple[int, int]:
    left, top, right, bottom = page_bbox
    return (
        round((left + x * (right - left)) * image_size[0]),
        round((top + y * (bottom - top)) * image_size[1]),
    )


def _dashed_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int, int],
    width: int,
    dash: int,
) -> None:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = max(abs(dx), abs(dy))
    if length == 0:
        return
    step_x = dx / length
    step_y = dy / length
    position = 0
    while position < length:
        finish = min(position + dash, length)
        if (position // dash) % 2 == 0:
            draw.line(
                (
                    round(start[0] + position * step_x),
                    round(start[1] + position * step_y),
                    round(start[0] + finish * step_x),
                    round(start[1] + finish * step_y),
                ),
                fill=color,
                width=width,
            )
        position += dash


def _draw_depth_family(
    draw: ImageDraw.ImageDraw,
    family: dict[str, Any],
    rectangles: dict[str, list[float]],
    page_bbox: list[float],
    image_size: tuple[int, int],
    *,
    line_width: int,
    dash: int,
    label_font: ImageFont.ImageFont,
) -> None:
    members = [rectangles[item] for item in family["members"] if item in rectangles]
    if not members:
        return
    common_top = max(rect[1] for rect in members)
    common_bottom = min(rect[1] + rect[3] for rect in members)
    if common_bottom <= common_top:
        return
    marker_x = min(rect[0] for rect in members)
    px, top = _page_point(marker_x, common_top, page_bbox, image_size)
    _, bottom = _page_point(marker_x, common_bottom, page_bbox, image_size)
    color = (83, 83, 83, 190)
    _dashed_line(draw, (px, top), (px, bottom), color, line_width, dash)
    cap = max(4, line_width * 3)
    draw.line((px - cap, top, px + cap, top), fill=color, width=line_width)
    draw.line((px - cap, bottom, px + cap, bottom), fill=color, width=line_width)
    label = str(family["id"])
    draw.text((px + cap + 2, (top + bottom) // 2), label, fill=(55, 55, 55, 235), font=label_font)


def _group_label(group: dict[str, Any]) -> str:
    labels = {
        "RAW_SIDE_GROUP": "RAW SIDE",
        "PROCESSING_CORE_GROUP": "PROCESS CORE",
        "FINISHED_SIDE_GROUP": "FINISHED SIDE",
        "COLD_STORAGE_GROUP": "COLD / STORAGE",
        "SUPPORT_GROUP": "SUPPORT",
    }
    return str(group.get("display_label") or labels.get(group["functional_group"], "OTHER GROUP"))


def _draw_closed_polygon(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    color: tuple[int, int, int, int],
    width: int,
    dash: int,
) -> None:
    if len(points) < 3:
        raise ValueError("overlay polygon requires at least three points")
    for index, point in enumerate(points):
        _dashed_line(draw, point, points[(index + 1) % len(points)], color, width, dash)


def _draw_tag(
    draw: ImageDraw.ImageDraw,
    text: str,
    anchor: tuple[int, int],
    font: ImageFont.ImageFont,
    color: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = draw.textbbox(anchor, text, font=font)
    draw.rectangle((left - 4, top - 2, right + 4, bottom + 2), fill=(255, 255, 255, 224))
    draw.text(anchor, text, fill=color, font=font)


def _render_one(reference_id: str, source: Path, output_dir: Path) -> dict[str, Any]:
    abstraction_path = EVIDENCE_DIR / REFERENCES[reference_id]
    abstraction = json.loads(abstraction_path.read_text(encoding="utf-8"))
    actual_source_sha256 = _verified_source_sha256(source, abstraction["source_sha256"])
    page_bbox = abstraction["normalization"]["primary_envelope_page_bbox_norm"]
    output_name = reference_id.lower().replace("_", "-") + "-normalized-overlay.png"
    with tempfile.TemporaryDirectory(prefix="p0c-render-") as temp_dir:
        prefix = Path(temp_dir) / "source"
        subprocess.run(
            ["pdftoppm", "-f", "1", "-singlefile", "-r", "48", "-png", str(source), str(prefix)],
            check=True,
            capture_output=True,
            text=True,
        )
        original = Image.open(prefix.with_suffix(".png")).convert("RGB")
        base = Image.blend(Image.new("RGB", original.size, "white"), original, 0.52).convert("RGBA")
    draw = ImageDraw.Draw(base, "RGBA")
    width, height = base.size
    page_rect = [
        _page_point(0, 0, page_bbox, base.size),
        _page_point(1, 1, page_bbox, base.size),
    ]
    envelope_width = max(2, width // 1600)
    envelope_dash = max(8, width // 140)
    envelope_font = _font(max(12, width // 210))

    site_context = abstraction.get("site_boundary_context")
    if isinstance(site_context, dict):
        page_coordinate_frame = [0.0, 0.0, 1.0, 1.0]
        for polygon in site_context.get("polygons", []):
            site_points = [
                _page_point(float(x), float(y), page_coordinate_frame, base.size)
                for x, y in polygon
            ]
            _draw_closed_polygon(
                draw,
                site_points,
                (80, 80, 80, 185),
                max(2, width // 1700),
                max(10, width // 110),
            )
        site_anchor = site_context.get("label_anchor_page_norm")
        if isinstance(site_anchor, list) and len(site_anchor) == 2:
            _draw_tag(
                draw,
                str(site_context["display_label"]),
                _page_point(float(site_anchor[0]), float(site_anchor[1]), page_coordinate_frame, base.size),
                envelope_font,
                (70, 70, 70, 245),
            )

    outline_polygons = abstraction["building_outline"]["polygons"]
    for outline in outline_polygons:
        outline_points = [_page_point(float(x), float(y), page_bbox, base.size) for x, y in outline]
        _draw_closed_polygon(
            draw,
            outline_points,
            (35, 35, 35, 215),
            envelope_width,
            envelope_dash,
        )
    principal_mass = abstraction.get("principal_building_mass", {})
    envelope_tag = str(principal_mass.get("display_label", "APPROX. PRIMARY ENVELOPE"))
    envelope_top_left = _page_point(0, 0, page_bbox, base.size)
    tag_x = envelope_top_left[0] + 4
    envelope_tag_box = draw.textbbox((0, 0), envelope_tag, font=envelope_font)
    envelope_tag_height = envelope_tag_box[3] - envelope_tag_box[1]
    tag_y = max(4, envelope_top_left[1] - envelope_tag_height - 10)
    _draw_tag(draw, envelope_tag, (tag_x + 5, tag_y + 3), envelope_font, (45, 45, 45, 245))

    for excluded in abstraction.get("excluded_areas", []):
        polygon = excluded.get("polygon_page_norm", [])
        points = [_page_point(float(x), float(y), [0.0, 0.0, 1.0, 1.0], base.size) for x, y in polygon]
        _draw_closed_polygon(
            draw,
            points,
            (95, 95, 95, 235),
            max(2, width // 1500),
            max(8, width // 150),
        )
        if points:
            label_x = min(point[0] for point in points) + 4
            label_y = min(point[1] for point in points) + 4
            _draw_tag(
                draw,
                str(excluded.get("display_label", "ANNEX / EXCLUDED")),
                (label_x, label_y),
                envelope_font,
                (75, 75, 75, 250),
            )

    normalized_rectangles: dict[str, list[float]] = {}
    for group in abstraction["major_zone_rectangles"]:
        x, y, rect_width, rect_height = (float(value) for value in group["rect"])
        normalized_rectangles[group["id"]] = [x, y, rect_width, rect_height]
        top_left = _page_point(x, y, page_bbox, base.size)
        bottom_right = _page_point(x + rect_width, y + rect_height, page_bbox, base.size)
        rgb = GROUP_COLORS.get(group["functional_group"], (100, 100, 100))
        stroke_width = max(2, width // 1400)
        draw.rectangle((top_left, bottom_right), outline=(*rgb, 220), width=stroke_width)
        label = _group_label(group)
        label_font = _font(max(12, width // 210))
        label_box = draw.textbbox((0, 0), label, font=label_font)
        label_width = label_box[2] - label_box[0]
        label_height = label_box[3] - label_box[1]
        chip = (
            top_left[0] + 3,
            top_left[1] + 3,
            top_left[0] + label_width + 11,
            top_left[1] + label_height + 9,
        )
        draw.rectangle(chip, fill=(255, 255, 255, 222))
        draw.text((chip[0] + 4, chip[1] + 3), label, fill=(*rgb, 255), font=label_font)

    left, top = page_rect[0]
    right, bottom = page_rect[1]
    dash = max(8, width // 180)
    for x in abstraction["axis_families"]["x"]:
        px, _ = _page_point(float(x), 0, page_bbox, base.size)
        _dashed_line(draw, (px, top), (px, bottom), (93, 93, 93, 150), max(1, width // 1500), dash)
    for y in abstraction["axis_families"]["y"]:
        _, py = _page_point(0, float(y), page_bbox, base.size)
        _dashed_line(draw, (left, py), (right, py), (93, 93, 93, 150), max(1, width // 1500), dash)

    for family in abstraction["depth_families"]:
        _draw_depth_family(
            draw,
            family,
            normalized_rectangles,
            page_bbox,
            base.size,
            line_width=max(2, width // 1200),
            dash=max(6, width // 250),
            label_font=_font(max(12, width // 210)),
        )

    title_font = _font(max(18, width // 95))
    small_font = _font(max(14, width // 170))
    draw.rounded_rectangle((24, 22, min(width - 24, 890), 122), radius=12, fill=(255, 255, 255, 232), outline=(65, 65, 65, 220), width=2)
    draw.text((42, 34), f"{reference_id}  |  normalized abstraction overlay", fill=(20, 20, 20, 255), font=title_font)
    draw.text((42, 82), "Approximate group envelopes; no engineering scale or project dimensions", fill=(65, 65, 65, 255), font=small_font)
    base.convert("RGB").save(output_dir / output_name, format="PNG", optimize=True)
    digest = hashlib.sha256((output_dir / output_name).read_bytes()).hexdigest()
    return {
        "reference_id": reference_id,
        "png": output_name,
        "sha256": digest,
        "source_sha256": actual_source_sha256,
    }


def render_pack(sources: dict[str, Path], output_dir: Path) -> dict[str, Any]:
    if not sources or not set(sources).issubset(REFERENCES):
        raise ValueError("one or more known reference PDF paths are required")
    output_dir.mkdir(parents=True, exist_ok=True)
    existing_manifest_path = EVIDENCE_DIR / "overlay-review-pack.json"
    existing_manifest = (
        json.loads(existing_manifest_path.read_text(encoding="utf-8"))
        if existing_manifest_path.is_file()
        else {}
    )
    overlays_by_id = {
        item["reference_id"]: item for item in existing_manifest.get("overlays", [])
    }
    for reference_id, source in sources.items():
        overlays_by_id[reference_id] = {
            **_render_one(reference_id, source, output_dir),
            "reference_derived": True,
            "engineering_authority": False,
            "approximate_group_envelope": True,
        }
    overlays = [overlays_by_id[reference_id] for reference_id in REFERENCES]
    prior_review = existing_manifest.get("owner_review_by_reference", {})
    initial_review = {
        "GD-001_ZHUYUAN": "PENDING",
        "GD-002_XIAOXIANG": "PENDING",
        "GD-003_MOUDING": "PENDING",
        "GD-004_SHUANGLONGYING": "PASS",
        "GD-005_PANLONG": "PASS",
    }
    review_by_reference = {
        reference_id: (
            "PENDING"
            if reference_id in sources
            else prior_review.get(reference_id, initial_review[reference_id])
        )
        for reference_id in REFERENCES
    }
    manifest = {
        "identity": "v2.2.2-p0c-overlay-review-pack@1.0.0",
        "correction_task_id": "V2_2_2_P0C_OWNER_OVERLAY_CORRECTION_R1",
        "abstraction_visual_overlay_created": True,
        "owner_visual_review": "PENDING",
        "owner_review_by_reference": review_by_reference,
        "reference_derived": True,
        "engineering_authority": False,
        "approximate_group_envelope": True,
        "runtime_project_input": False,
        "original_pdf_bytes_committed": False,
        "overlay_method": "faded_full_page_source_render_plus_context_boundary_principal_mass_group_envelopes_axes_and_shared_depth_brackets",
        "overlays": overlays,
        "overlay_disclaimer": "Visual review aid only; page envelopes and group outlines are provisional manual traces and must not be interpreted as room-accurate engineering geometry.",
    }
    (output_dir / "overlay-review-pack.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", action="append", required=True, help="REFERENCE_ID=/path/to/source.pdf")
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE_DIR)
    args = parser.parse_args()
    sources: dict[str, Path] = {}
    for item in args.source:
        reference_id, separator, source_path = item.partition("=")
        if not separator or reference_id in sources:
            raise SystemExit("each --source must be a unique REFERENCE_ID=PATH")
        sources[reference_id] = Path(source_path)
    result = render_pack(sources, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
