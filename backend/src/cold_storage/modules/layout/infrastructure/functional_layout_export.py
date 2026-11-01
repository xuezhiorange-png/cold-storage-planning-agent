"""A1 1:200 projection and compact evidence from one persisted joint result."""

from __future__ import annotations

import csv
import json
from html import escape
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.infrastructure.autonomous_layout_export import COLORS, INK, _Sheet


def draw_functional_candidate(c: dict[str, Any], path: Path) -> None:
    s = _Sheet()

    def p(x: float, y: float) -> tuple[float, float]:
        return 36 + x / 200, 500 - y / 200

    def box(b: list[int], fill: str, stroke: str = INK, lw: float = 0.16, data: str = "") -> None:
        x, y = p(b[0], b[3])
        s.rect(x, y, (b[2] - b[0]) / 200, (b[3] - b[1]) / 200, fill, stroke, lw, data)

    building = c["original_building"]
    s.text(17, 20, "蓝莓加工厂 · 自主布局 A1", 6.3)
    s.text(
        17, 29, "房间—设备—货位—门洞联合迭代 / 20t/天 / 条件性概念方案，非施工图", 3.2, "#627987"
    )
    s.text(691, 20, "A1横版 · 1:200 · mm", 3.8)
    s.line([(17, 35), (824, 35)], lw=0.45)
    for i, x in enumerate(building["coordinate_mapping"]["axis_x_mm"], 1):
        s.line([p(x, 0), p(x, 80300)], "#d5dfe5", 0.12, True)
        s.text(p(x, 0)[0], 92, str(i), 2.8, center=True)
        s.text(p(x, 0)[0], 511, str(i), 2.8, center=True)
        if i < 19:
            s.text(p(x, 0)[0] + 15, 81, "6000", 2.2, center=True)
    for key, y in building["coordinate_mapping"]["axis_y_mm"].items():
        s.line([p(0, y), p(108000, y)], "#d5dfe5", 0.12, True)
        s.text(26, p(0, y)[1] + 1, key, 2.9, center=True)
    s.line([(36, 69), (576, 69)], "#81939e", 0.2)
    s.text(306, 65, "108000 = 18 × 6000", 3.5, center=True)
    box(building["outer_building_bbox_mm"], "#f8fafb", lw=0.5)
    for q in c["rooms"]:
        box(
            q["bbox_mm"],
            COLORS.get(q["zone_code"], "#edf1ed"),
            lw=0.35,
            data=f'data-room="{q["zone_code"]}"',
        )
    for a in c["equipment"]["operating_spaces"]:
        box(a["bbox_mm"], "#e6f3f4" if not a["conflicts"] else "#ffe1dd", "#b6d5dc", 0.05)
    for q in c["equipment"]["items"]:
        kind = q["kind"]
        fill = (
            "#f4f6f7"
            if "pallet" in kind
            else "#a9bdc9"
            if kind == "packing_line"
            else "#d7bb99"
            if kind == "case_erector"
            else "#c3d8c0"
            if kind == "ten_door_locker"
            else "#cbbda9"
        )
        box(q["bbox_mm"], fill, "#687c89", 0.1, data=f'data-equipment="{q["id"]}"')
        if kind in ("packing_line", "case_erector"):
            b = q["bbox_mm"]
            x, y = p((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
            s.text(x, y + 0.8, q["id"], 1.8, "#334d5d", True)
    g = c["equipment"]["layouts"]["changing_room"].get("functional_geometry")
    if g and g["status"] == "STATIC_GEOMETRY_READY":
        room = next(r for r in c["rooms"] if r["zone_code"] == "changing_room")
        a, b, _, _ = room["bbox_mm"]
        for h in g["homes"]:
            u, v, r, t = h["bounds_mm"]
            box([a + u, b + v, a + r, b + t], "#e2c49f", "#b18c5b", 0.08)
        # The paths are computed, not manually added to improve the drawing.
        events = c["changing_function"].get("entry_exit", {}).get("shifts", [])
        if events:
            for ev in events[0]["events"][:1]:
                if ev["centerline_mm"]:
                    s.line([p(a + x, b + y) for x, y in ev["centerline_mm"]], "#89619a", 0.25, True)
    for route in c["equipment_aware_interior_paths"]:
        if route["centerline_mm"]:
            s.line([p(*a) for a in route["centerline_mm"]], "#2b879a", 0.32, True)
    for row in c["access_results"]:
        if row.get("status") != "PASS":
            continue
        color = (
            "#8a62a1"
            if row["flow_kind"] == "PEOPLE"
            else "#b17e40"
            if row["flow_kind"] == "PACKAGING"
            else "#278a72"
        )
        for side in ("from", "to"):
            seg = row["portal_" + side]["segment"]
            points = [
                p(float(seg[k]["x"]) * 1000, float(seg[k]["y"]) * 1000) for k in ("start", "end")
            ]
            s.line(points, "#ffffff", 1.3)
            s.line(points, color, 0.65)
        line = row.get("centerline", [])
        if len(line) > 1:
            s.line([p(float(a["x"]) * 1000, float(a["y"]) * 1000) for a in line], color, 0.45)
    for wall in building["retained_walls"]:
        for a, b in wall["segments_mm"]:
            s.line([p(*a), p(*b)], "#354752", 0.35)
    for col in building["columns"]:
        box(col["bbox_mm"], "#334752", lw=0.1)
    for i, r in enumerate(c["rooms"], 1):
        b = r["bbox_mm"]
        x, y = p(b[0] + 1100, b[3] - 1100)
        s.rect(x - 3, y - 2.7, 8, 4.2, "#ffffff", "#ffffff", 0)
        s.text(x + 1, y, f"{i:02}", 2.6, center=True)
    s.line([(598, 44), (598, 550)], "#cbd8df", 0.2)
    s.text(610, 50, "12区实际计算坐标", 4)
    for i, r in enumerate(c["rooms"], 1):
        yy = 62 + (i - 1) * 14
        s.text(610, yy, f"{i:02} {r['name']}", 3)
        s.text(
            610,
            yy + 5,
            f"{r['width_mm']} × {r['depth_mm']}  /  {float(r['area_m2']):.3f}㎡",
            2.7,
            "#5b7280",
        )
    eq = c["equipment"]["placed_counts"]
    m = c["metrics"]
    notes = [
        "联合计算结果",
        f"12区 / MUST 7条 / 原非货车Access {c['non_truck_access_pass_count']}/11",
        f"设备：包装线{eq.get('packing_line')}/6 · 折箱机{eq.get('case_erector')}/5 · 整柜11",
        f"门前主体冲突：{m['portal_approach_conflict_count']}",
        f"已验证室内全宽路线：{m['verified_interior_route_count']}",
        "浅蓝：保留通道；蓝虚线：已查室内段",
        "绿：产品；褐：包材；紫：人员",
        "",
        "仓储：有顺序的取放几何见证",
    ]
    for stock in c["equipment"]["storage"]:
        layout = stock["layout"]
        name = next(r["name"] for r in c["rooms"] if r["zone_code"] == layout["room"])
        notes.append(f"{name} {layout['placed_positions']} / 最低{layout['minimum_positions']}")
    notes += [
        "非任意直接取放；搬运设备运动学待审",
        "",
        "更衣室：53本位 / 两班独立柜位",
        "600×900活动、450×650人体为未批准假设",
        "实际柜门、储物、卫生及维护输入仍缺失",
        "Truck、完整P2D及工程批准未成立",
    ]
    for i, n in enumerate(notes):
        s.text(610, 247 + i * 9.6, n, 3.1 if i == 0 else 2.65, "#5b7280")
    s.text(36, 532, "20m校尺段 = 100mm纸面长度 / 按100%打印", 2.8, "#5b7280")
    for i in range(4):
        s.rect(36 + i * 25, 537, 25, 2, INK if i % 2 == 0 else "#ffffff", lw=0.12)
    s.text(36, 552, "同次计算的房间、设备、货位与路线；原建筑未分配部分保留空白。", 2.8)
    s.text(36, 561, "候选Hash：" + c["result_hash"], 2.2, "#5b7280")
    s.line([(17, 570), (824, 570)], "#cbd8df", 0.2)
    s.text(
        17,
        580,
        "自主布局 V1.1 / 条件性工程讨论图 / 保留柱体，净面积差异单列 / 不改变P1或生产默认",
        2.8,
    )
    s.save(path)


def export_functional_package(
    result: dict[str, Any], project: dict[str, Any], output: Path, *, drawings: bool = True
) -> None:
    output.mkdir(parents=True, exist_ok=True)

    def dump(name: str, data: Any) -> None:
        (output / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n"
        )

    dump("project-input.json", project)
    dump(
        "layout-generation-results.json",
        {
            **{k: v for k, v in result.items() if k not in ("candidates", "result_hash")},
            "source_generation_result_hash": result["result_hash"],
            "candidates": [
                {"file": "autonomous-layout-A1.json", "result_hash": c["result_hash"]}
                for c in result["candidates"]
            ],
            "export_note": (
                "Index only; complete candidate and raw witnesses are in the referenced JSON, "
                "without duplicating them here"
            ),
        },
    )
    if not result["candidates"]:
        return
    c = result["candidates"][0]
    dump("autonomous-layout-A1.json", c)
    dump("iteration-feedback.json", result["attempts"])
    dump(
        "functional-movement.json",
        {
            "status": c["changing_function"]["status"],
            "conditional_complete_sequence_verified": c["changing_function"][
                "conditional_complete_sequence_verified"
            ],
            "functional_status": "INPUT_REQUIRED",
            "raw_evidence": {
                "file": "autonomous-layout-A1.json",
                "json_pointer": "/changing_function",
            },
            "shifts": [
                {k: v for k, v in s.items() if k != "events"}
                for s in c["changing_function"]["shifts"]
            ],
        },
    )
    dump(
        "storage-pick-put.json",
        {
            "raw_evidence": {
                "file": "autonomous-layout-A1.json",
                "json_pointer": "/equipment/storage",
            },
            "storage": [
                {
                    "room": s["layout"]["room"],
                    "positions": s["layout"]["placed_positions"],
                    "minimum": s["layout"]["minimum_positions"],
                    "retrieved": s["movement"]["retrieved_positions"],
                    "returned": s["movement"]["putaway_positions"],
                    "conditional_pick_put_geometry_pass": s["movement"][
                        "conditional_pick_put_geometry_pass"
                    ],
                }
                for s in c["equipment"]["storage"]
            ],
        },
    )
    for name, rows, fields in (
        (
            "room-coordinates.csv",
            c["rooms"],
            [
                "zone_code",
                "name",
                "x_mm",
                "y_mm",
                "width_mm",
                "depth_mm",
                "rotation_deg",
                "area_m2",
                "required_area_m2",
                "column_area_m2",
            ],
        ),
        (
            "equipment-placement.csv",
            c["equipment"]["items"],
            ["id", "room", "kind", "bbox_mm", "rotation_deg", "basis"],
        ),
    ):
        with (output / name).open("w", newline="") as stream:
            w = csv.DictWriter(
                stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
            )
            w.writeheader()
            w.writerows(rows)
    if drawings:
        draw_functional_candidate(c, output / "autonomous-layout-A1")
    rows = "".join(
        (
            f"<tr><td>{escape(r['name'])}</td><td>{r['width_mm']}×{r['depth_mm']}</td>"
            f"<td>{r['area_m2']}</td><td>{r['column_area_m2']}</td></tr>"
        )
        for r in c["rooms"]
    )
    stocks = "".join(
        (
            f"<tr><td>{escape(stock['layout']['room'])}</td>"
            f"<td>{stock['layout']['placed_positions']}/"
            f"{stock['layout']['minimum_positions']}</td>"
            f"<td>{stock['movement']['retrieved_positions']}取 / "
            f"{stock['movement']['putaway_positions']}放</td></tr>"
        )
        for stock in c["equipment"]["storage"]
    )
    html = f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>自主布局A1 V1.1</title>
<style>body{{font:15px/1.6 system-ui;color:#233c4b;margin:24px auto;max-width:1400px;
padding:0 16px}}
img{{width:100%;border:1px solid #d3dee4}}
table{{border-collapse:collapse;width:100%;margin:16px 0}}
td,th{{text-align:left;border-bottom:1px solid #d3dee4;padding:8px}}
a{{color:#167d85}}
.scroll{{overflow:auto}}
p{{max-width:1000px}}</style>
<h1>房间与设备联合生成 · A1</h1>
<p>同次程序计算12区、设备、货位、门洞和实际路线。原P1最低需求与固定尺寸保持；柔性房间根据功能几何反馈扩大。不是施工图、工程批准或完整P2D。</p>
<p>
<a href="autonomous-layout-A1.pdf">A1 1:200 PDF</a> ·
<a href="autonomous-layout-A1.svg">SVG</a> ·
<a href="autonomous-layout-A1.json">完整坐标和见证JSON</a> ·
<a href="functional-movement.json">两班53人运动</a> ·
<a href="storage-pick-put.json">逐货位取放</a> ·
<a href="iteration-feedback.json">失败与迭代反馈</a>
</p>
<img src="autonomous-layout-A1.svg" alt="程序生成的真实比例整厂平面图">
<h2>房间与柱体净面积差异</h2>
<div class="scroll">
<table>
<tr>
<th>房间</th>
<th>mm</th>
<th>面积㎡</th>
<th>柱体㎡</th>
</tr>{rows}</table>
</div>
<h2>条件性有序取放</h2>
<p>取货时保留其他存货，放货按实测反向顺序验证。只证明指定荷载包络的几何，不证明叉车转弯、任意顺序存取或运营批准。</p>
<table>
<tr>
<th>库房</th>
<th>货位/最低</th>
<th>实际路径见证</th>
</tr>{stocks}</table>
<h2>53人功能计算</h2>
<p>两班独立分配柜格，进入、初始53人在室、柜前往返、600×900mm活动区、两种假设铰链及离室分别计算。
当前条件完整序列：{c["changing_function"]["conditional_complete_sequence_verified"]}。
柜体净尺寸、实际铰链、人体尺度、衣物卫生、门扇和运营时间仍为INPUT_REQUIRED。</p>
<h2>未成立的范围</h2>
<p>搬运设备运动学、冷却性能、实际设备维护空间、Truck、完整P2D、整厂适用性及工程批准未成立。货位顺序、人员单人移动与材料操作均为待审条件模型。</p>
<pre>{escape(json.dumps(c["remaining_geometry_issues"], ensure_ascii=False, indent=2))}</pre>
</html>"""
    (output / "autonomous-layout-review.html").write_text(html)
