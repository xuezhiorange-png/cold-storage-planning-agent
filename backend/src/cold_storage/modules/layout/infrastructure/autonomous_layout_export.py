"""Conditional concept drawings from one persisted autonomous result only."""

from __future__ import annotations

import csv
import json
from html import escape
from pathlib import Path
from types import MappingProxyType
from typing import Any

import fitz

MM = 72 / 25.4
INK = "#233c4b"
COLORS = MappingProxyType(
    {
        "sorting_packaging_room": "#f1e7d4",
        "coating_room": "#e4eee8",
        "primary_precooling_room": "#e0eeed",
        "secondary_precooling_room": "#e0eeed",
        "finished_goods_room": "#e2edf5",
        "frozen_fruit_room": "#e3e7f3",
        "changing_room": "#e7eedc",
        "office": "#eef0df",
        "packaging_material_storage": "#ece5f1",
    }
)


class _Sheet:
    def __init__(self) -> None:
        self.svg: list[str] = []
        self.doc = fitz.open()
        self.page = self.doc.new_page(width=841 * MM, height=594 * MM)
        self.font = fitz.Font("china-s")
        self.page.insert_font(fontname="CJK", fontbuffer=self.font.buffer)

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: str,
        stroke: str = INK,
        lw: float = 0.2,
        data: str = "",
    ) -> None:
        self.svg.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{lw}" {data}/>'
        )
        self.page.draw_rect(
            fitz.Rect(x * MM, y * MM, (x + w) * MM, (y + h) * MM),
            color=_rgb(stroke),
            fill=_rgb(fill),
            width=lw * MM,
        )

    def line(
        self,
        points: list[tuple[float, float]],
        color: str = INK,
        lw: float = 0.2,
        dashed: bool = False,
    ) -> None:
        dash = ' stroke-dasharray="1.2 1"' if dashed else ""
        self.svg.append(
            f'<polyline points="{" ".join(f"{x},{y}" for x, y in points)}" '
            f'fill="none" stroke="{color}" stroke-width="{lw}"{dash}/>'
        )
        self.page.draw_polyline(
            [fitz.Point(x * MM, y * MM) for x, y in points],
            color=_rgb(color),
            width=lw * MM,
            dashes="[3 2] 0" if dashed else None,
        )

    def text(
        self,
        x: float,
        y: float,
        value: str,
        size: float = 3,
        color: str = INK,
        center: bool = False,
    ) -> None:
        anchor = "middle" if center else "start"
        self.svg.append(
            f'<text x="{x}" y="{y}" '
            'font-family="Arial Unicode MS,Noto Sans CJK SC,Microsoft YaHei,sans-serif" '
            f'font-size="{size}" fill="{color}" text-anchor="{anchor}">{escape(value)}</text>'
        )
        width = self.font.text_length(value, fontsize=size * MM)
        self.page.insert_text(
            (x * MM - (width / 2 if center else 0), y * MM),
            value,
            fontsize=size * MM,
            fontname="CJK",
            color=_rgb(color),
        )

    def save(self, path: Path) -> None:
        svg = (
            (
                '<svg xmlns="http://www.w3.org/2000/svg" width="841mm" h'
                'eight="594mm" viewBox="0 0 841 594"><rect width="841" h'
                'eight="594" fill="white"/>'
            )
            + "".join(self.svg)
            + "</svg>"
        )
        path.with_suffix(".svg").write_text(svg)
        self.doc.subset_fonts()
        self.doc.save(path.with_suffix(".pdf"), deflate=True)
        self.page.get_pixmap(dpi=200, alpha=False).save(path.with_suffix(".png"))
        self.doc.close()


def _rgb(value: str) -> tuple[float, float, float]:
    return tuple(int(value[i : i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


def draw_autonomous_candidate(candidate: dict[str, Any], path: Path, label: str) -> None:
    s = _Sheet()
    x: float
    y: float

    def p(x: float, y: float) -> tuple[float, float]:
        return (40 + x / 200, 500 - y / 200)

    building = candidate["original_building"]
    s.text(17, 20, "蓝莓加工厂 · 程序自主整厂布局 " + label, 6.5)
    s.text(
        17,
        29,
        "20t/天 · 原建筑结构约束 + 原P1尺寸规则 · 独立生成坐标 / 条件性概念设计，非施工图",
        3.0,
        "#637986",
    )
    s.text(706, 20, "A1 横版  1:200", 4)
    s.line([(17, 34), (825, 34)], lw=0.5)
    for i, x in enumerate(building["coordinate_mapping"]["axis_x_mm"], 1):
        a, b = p(x, 0), p(x, 80300)
        s.line([a, b], "#d4dde2", 0.13, True)
        for y in (90, 510):
            s.text(a[0], y, str(i), 2.8, center=True)
        if i < 19:
            s.text(a[0] + 15, 82, "6000", 2.5, center=True)
    for name, y in building["coordinate_mapping"]["axis_y_mm"].items():
        a, b = p(0, y), p(108000, y)
        s.line([a, b], "#d4dde2", 0.13, True)
        s.text(30, a[1] + 1, name, 3.1, center=True)
        s.text(592, a[1] + 1, name, 3.1, center=True)
    s.line([(40, 70), (580, 70)], "#6a7b85", 0.2)
    s.text(310, 66, "108000 = 18 × 6000", 3.4, center=True)
    o = building["outer_building_bbox_mm"]
    x, y = p(o[0], o[3])
    s.rect(x, y, (o[2] - o[0]) / 200, (o[3] - o[1]) / 200, "#f8fafb", INK, 0.55)
    # No Owner function-zone/equipment underlay is present in this drawing.
    for room in candidate["rooms"]:
        b = room["bbox_mm"]
        x, y = p(b[0], b[3])
        s.rect(
            x,
            y,
            (b[2] - b[0]) / 200,
            (b[3] - b[1]) / 200,
            COLORS.get(room["zone_code"], "#edf0ed"),
            "#617b89",
            0.3,
            f'data-zone="{room["zone_code"]}" data-world-bbox-mm="{",".join(map(str, b))}"',
        )
    for item in candidate["equipment"]["items"]:
        b = item["bbox_mm"]
        x, y = p(b[0], b[3])
        w, h = (b[2] - b[0]) / 200, (b[3] - b[1]) / 200
        kind = item["kind"]
        fill, stroke = ("#f7fafb", "#708793") if "pallet" in kind else ("#fcfdfd", "#376d86")
        s.rect(
            x,
            y,
            w,
            h,
            fill,
            stroke,
            0.13,
            f'data-equipment="{escape(item["id"])}" data-world-bbox-mm="{",".join(map(str, b))}"',
        )
        if kind == "packing_line":
            if w > h:
                for j in range(1, 14):
                    s.line([(x + j * w / 14, y), (x + j * w / 14, y + h)], stroke, 0.08)
            else:
                for j in range(1, 14):
                    s.line([(x, y + j * h / 14), (x + w, y + j * h / 14)], stroke, 0.08)
        elif kind == "case_erector":
            s.line(
                [
                    (x + w * 0.2, y + h * 0.2),
                    (x + w * 0.8, y + h * 0.2),
                    (x + w * 0.8, y + h * 0.8),
                    (x + w * 0.2, y + h * 0.8),
                    (x + w * 0.2, y + h * 0.2),
                ],
                stroke,
                0.15,
            )
            s.text(x + w / 2, y + h / 2, item["id"].replace("ERECT-", "E"), 2.1, stroke, True)
        elif kind == "case_film_component":
            s.text(x + w / 2, y + h / 2, item["id"].replace("FILM-", ""), 1.8, stroke, True)
    for wall in building["retained_walls"]:
        for a, b in wall["segments_mm"]:
            s.line([p(*a), p(*b)], "#344752", 0.35)
    for col in building["columns"]:
        b = col["bbox_mm"]
        x, y = p(b[0], b[3])
        s.rect(x, y, (b[2] - b[0]) / 200, (b[3] - b[1]) / 200, "#334953", INK, 0.12)
    for route in candidate["equipment_aware_interior_paths"]:
        points = route["centerline_mm"]
        if points:
            s.line([p(*point) for point in points], "#4a91a7", 0.4, True)
    for access in candidate["access_results"]:
        if access.get("status") != "PASS":
            continue
        route_color = (
            "#806493"
            if access.get("flow_kind") == "PERSONNEL"
            else "#aa793b"
            if access.get("from_ref") == "packaging_material_storage"
            else "#ba6739"
            if access.get("from_ref") == "raw_fruit_buffer"
            else "#228775"
        )
        for key in ("portal_from", "portal_to"):
            portal = access.get(key)
            if portal:
                a, b = portal["segment"]["start"], portal["segment"]["end"]
                s.line(
                    [
                        p(float(a["x"]) * 1000, float(a["y"]) * 1000),
                        p(float(b["x"]) * 1000, float(b["y"]) * 1000),
                    ],
                    route_color,
                    0.8,
                )
        line = access.get("centerline", [])
        if len(line) > 1:
            s.line(
                [p(float(q["x"]) * 1000, float(q["y"]) * 1000) for q in line],
                route_color,
                0.5,
            )
    for opening in building["openings"]:
        a, b = opening["segment_mm"]
        s.line([p(*a), p(*b)], "#a55d37", 1)
        x, y = p((a[0] + b[0]) / 2, a[1])
        s.text(x, y + 7, opening["id"].replace("SOUTH-", ""), 2.3, "#8c5735", True)
    for i, room in enumerate(candidate["rooms"], 1):
        b = room["bbox_mm"]
        x, y = p((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        if min(b[2] - b[0], b[3] - b[1]) < 9000:
            y = p(0, b[3])[1] + 6
        size = max(2.2, min(3.6, (b[2] - b[0]) / 200 / 7))
        name = f"{i:02} {room['name']}"
        plate = max(len(name) * size * 0.58, 27)
        s.rect(x - plate / 2, y - 4, plate, 10, "#ffffff", "#ffffff", 0)
        s.text(x, y, name, size, center=True)
        s.text(
            x,
            y + 4.3,
            f"{room['width_mm']}×{room['depth_mm']}  {room['area_m2']}m²",
            2.25,
            center=True,
        )
    s.line([(609, 43), (609, 548)], "#d4dde2", 0.2)
    s.text(620, 50, "独立计算结果", 4)
    for i, room in enumerate(candidate["rooms"], 1):
        yy = 62 + (i - 1) * 15
        s.text(620, yy, f"{i:02} {room['name']}", 3.0)
        s.text(
            620,
            yy + 5,
            f"{room['width_mm']} × {room['depth_mm']} mm  /  {room['area_m2']}m²",
            2.65,
            "#597381",
        )
    eq = candidate["equipment"]["placed_counts"]
    notes = [
        "验证范围",
        "12区 / 原7条MUST / 房间互不重叠",
        "原P1尺寸与面积规则保持不变",
        f"原非货车Access：{candidate['non_truck_access_pass_count']}/11",
        "柱体保留；净面积损失见JSON",
        "Truck、完整P2D：未通过 / 未验证",
        "",
        f"设备主体：包装线{eq.get('packing_line', 0)}/6",
        f"折箱机{eq.get('case_erector', 0)}/5，整柜{eq.get('ten_door_locker', 0)}/11",
        "冷却性能、维护、53人流程未验收",
        "绿/橙/褐/紫：产品/原果/包材/人员",
        "蓝虚线：扣除设备后的已查室内段",
        "棕色：原建筑开口，使用分配待审",
        "门喉连接、未画室内段未验证",
        "",
        "底图仅含原建筑墙柱及轴网",
        "没有使用Owner功能分区/设备坐标",
        "未分配区域保留，不虚构功能房间",
        "",
        "实测尺寸精度受原PDF矢量限制",
        "不是施工图或整厂工程批准",
    ]
    for i, note in enumerate(notes):
        s.text(620, 258 + i * 10, note, 3.1 if i == 0 else 2.8, "#597381" if i else INK)
    s.text(40, 544, "20m校尺段 = 100mm纸面长度；按100%打印，勿适合页面。", 2.8, "#657d89")
    for i in range(4):
        s.rect(40 + i * 25, 531, 25, 2, INK if i % 2 == 0 else "#ffffff", INK, 0.15)
    s.text(40, 560, "结果 " + candidate["result_hash"], 2.3, "#657d89")
    s.line([(17, 568), (825, 568)], "#cbd7de", 0.2)
    s.text(
        17, 579, "程序生成的条件性整厂候选 · 房间/设备/门洞均来自同次JSON · 不改变历史工程结果", 2.8
    )
    s.text(680, 579, "单位mm / A1 841×594", 2.8)
    s.save(path)


def export_autonomous_package(
    result: dict[str, Any], project: dict[str, Any], output: Path, *, drawings: bool = True
) -> None:
    output.mkdir(parents=True, exist_ok=True)

    def dump(p: Path, d: Any) -> None:
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2, default=str) + "\n")

    dump(output / "project-input.json", project)
    dump(output / "layout-generation-results.json", result)
    rows: list[dict[str, Any]] = []
    links = []
    for i, c in enumerate(result["candidates"]):
        label = chr(65 + i)
        name = "autonomous-layout-" + label
        dump(output / (name + ".json"), c)
        if drawings:
            draw_autonomous_candidate(c, output / name, label)
        rows.extend(
            {
                "candidate": label,
                "id": q["id"],
                "kind": q["kind"],
                "room": q["room"],
                "bbox_mm": q["bbox_mm"],
                "basis": q["basis"],
                "status": q["status"],
            }
            for q in c["equipment"]["items"]
        )
        links.append(
            f"<section><h2>方案 {label} · {escape(c['profile_requested'])}</h2>"
            f"<p>12区 / MUST 7条；非货车Access {c['non_truck_access_pass_count']}/11。"
            "完整P2D和整厂批准未取得。</p>"
            f'<p><a href="{name}.pdf">A1 PDF</a> · <a href="{name}.svg">可缩放SVG</a> · '
            f'<a href="{name}.png">高清PNG</a> · <a href="{name}.json">原始JSON</a></p>'
            f'<div class="view"><img src="{name}.png" '
            f'alt="方案{label}自主整厂布局"></div></section>'
        )
    if rows:
        with (output / "equipment-placement.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    report = [
        "# 自主整厂布局生成 V1",
        "",
        "本轮仅输入原建筑结构、业务参数及设备规格，没有读取V2/V3功能分区或历史候选坐标。",
        "",
        "Owner已确认允许室内保留柱体；新墙线、设备和通道仍避让，柱体损失从净面积单列。原尺寸Authority未修改。",
        "",
        "|候选|独立房间|原MUST|非货车Access|包装线|折箱机|十门柜|原P2房间检查|",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for i, c in enumerate(result["candidates"]):
        eq = c["equipment"]["placed_counts"]
        report.append(
            f"|{chr(65 + i)}|12|7/7|{c['non_truck_access_pass_count']}/11|"
            f"{eq.get('packing_line', 0)}/6|{eq.get('case_erector', 0)}/5|"
            f"{eq.get('ten_door_locker', 0)}/11|{c['legacy_room_obstacle_oracle']['status']}|"
        )
        report.extend(
            [
                "",
                f"## 方案{chr(65 + i)}",
                "",
                f"结构接触图Hash：{c['structural_signature']}。"
                f"占用房间毛面积{c['metrics']['gross_room_area_m2']}m²，"
                f"室内柱投影{c['metrics']['retained_internal_column_area_m2']}m²；"
                "不能以毛面积自动证明货位取放或功能可用。",
                "",
                "|功能区|X/Y mm|宽×深mm|毛面积m²|扣柱面积m²|",
                "|---|---|---|---:|---:|",
            ]
        )
        report.extend(["", "设备布置后的室内通道复核（与原室间Access分别报告）：", ""])
        for path in c["equipment_aware_interior_paths"]:
            report.append(
                f"- {path['room']}：{path['status']}，净宽{path['clear_width_mm']}mm；"
                f"{path['failure_code'] or '已核实完整宽度的室内段'}。"
                "门洞变宽连接段、车辆回转和全货位取放尚未验证。"
            )
        for z in c["rooms"]:
            report.append(
                f"|{z['name']}|{z['x_mm']} / {z['y_mm']}|{z['width_mm']}×{z['depth_mm']}|"
                f"{z['area_m2']}|{z['floor_minus_columns_m2']}|"
            )
        report.extend(
            ["", "设备拒绝记录（未将冲突设备画成通过）：", ""]
            + [
                f"- {q['id']}：{', '.join(q['conflicts'])}"
                for q in c["equipment"]["rejected_items"]
            ]
        )
        report.extend(
            ["", "|存储区|原计算最低货位|实际主体位置|缺口|取放验证|", "|---|---:|---:|---:|---|"]
        )
        for stock in c["equipment"]["storage_body_capacity_checks"]:
            report.append(
                f"|{stock['zone_code']}|{stock['required_positions']}|"
                f"{stock['body_positions_placed']}|{stock['body_position_shortfall']}|未验证全货位取放|"
            )
        report.extend(["", "设备后门前预留/操作带冲突：", ""])
        for space in c["equipment"]["operating_spaces"]:
            if space["conflicts"]:
                report.append(f"- {space['id']}：{', '.join(space['conflicts'])}")
    report.extend(
        [
            "",
            "所有图纸为同次计算结果的投影；不能将候选占用Footprint当作Owner原建筑外轮廓。",
            "Truck缺少真实车辆/场地输入，完整P2D、冷却能力、设备维修、全货位取放及53人更衣流程均没有被本轮证明。",
            "原成品规则保留10%冻果扣减（20t/天、7天对应126000kg和315最低货位）；"
            "没有将其悄悄改成20t/天全量成品7天的容量承诺。包材货位缺口及柱体影响须另行处理。",
            "原建筑3处南侧开口的几何来自墙线端点；人员、进料及出货的用途分配为本轮设计建议，门型未批准。",
            "新增代码仅显式入口启用，生产默认/MCP/历史P1及比较器保持不变。Native=0；MAIN=false；Grant/Claim=false。",
        ]
    )
    (output / "layout-comparison.md").write_text("\n".join(report) + "\n")
    (output / "autonomous-layout-review.html").write_text(
        (
            '<!doctype html><html lang="zh-CN"><meta charset="utf-8"'
            '><meta name="viewport" content="width=device-width, ini'
            'tial-scale=1"><title>蓝莓加工厂 自主布局V1</title><style>body{ma'
            "rgin:0;background:#edf2f4;color:#263f4e;font:15px/1.6 s"
            'ystem-ui,"PingFang SC",sans-serif}main{max-width:1500px'
            ";margin:auto;padding:20px}h1{font-size:26px}h2{font-siz"
            "e:20px}section{background:white;border:1px solid #d1dce"
            "2;padding:16px;margin:18px 0}a{color:#216681}.view{over"
            "flow:auto;border:1px solid #d8e0e5}.view img{width:100%"
            ";min-width:1000px;display:block}p{max-width:1000px}@med"
            "ia(max-width:700px){main{padding:10px}.view img{min-wid"
            "th:1100px}}</style><main><h1>蓝莓加工厂 · 自主整厂布局 V1</h1><p>原"
            "建筑结构与P1需求驱动的独立生成。以下为条件性候选，未宣称完整P2D或实际工程批准。原房间、设备坐标没有作为生"
            '成输入。</p><p><a href="layout-comparison.md">方案比较与限制</a> ·'
            ' <a href="equipment-placement.csv">设备坐标</a> · <a href="'
            'layout-generation-results.json">生成记录</a> · <a href="pro'
            'ject-input.json">可复算输入</a></p>'
        )
        + "".join(links)
        + "</main></html>"
    )
