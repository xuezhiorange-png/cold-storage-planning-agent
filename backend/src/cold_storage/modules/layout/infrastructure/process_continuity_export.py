"""Actual coordinate projection, readable engineering preview, no recalculation."""

from __future__ import annotations

import csv
import json
import math
from html import escape
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.domain.process_transfer_interfaces import (
    ASSUMED,
    GEOMETRY,
    route_is_conditionally_usable,
)
from cold_storage.modules.layout.infrastructure.autonomous_layout_export import COLORS, INK, _Sheet


def draw_process_candidate(
    c: dict[str, Any],
    path: Path,
    layer: str = "main",
    *,
    revision: str = "V1.2",
    candidate_label: str = "",
) -> None:
    s = _Sheet()
    flows = c["process_continuity"]

    def p(x: float, y: float) -> tuple[float, float]:
        return 36 + x / 200, 500 - y / 200

    def box(b: list[int], fill: str, stroke: str = INK, lw: float = 0.12, data: str = "") -> None:
        x, y = p(b[0], b[3])
        s.rect(x, y, (b[2] - b[0]) / 200, (b[3] - b[1]) / 200, fill, stroke, lw, data)

    def route(points: list[list[int]], color: str, lw: float = 0.45, dashed: bool = False) -> None:
        if len(points) < 2:
            return
        pts = [p(*q) for q in points]
        s.line(pts, color, lw, dashed)
        for a, b in zip(reversed(pts[:-1]), reversed(pts[1:]), strict=False):
            d = math.hypot(b[0] - a[0], b[1] - a[1])
            if d < 1:
                continue
            ux, uy = (b[0] - a[0]) / d, (b[1] - a[1]) / d
            s.line(
                [
                    (b[0] - 1.5 * ux + 0.6 * uy, b[1] - 1.5 * uy - 0.6 * ux),
                    b,
                    (b[0] - 1.5 * ux - 0.6 * uy, b[1] - 1.5 * uy + 0.6 * ux),
                ],
                color,
                lw,
            )
            break

    titles = {
        "main": f"自主布局 {revision} · 工艺物流贯通",
        "process": "主产品 · 实际设备端点与门洞",
        "cartons": "五台折箱机 · 六线供箱与补料",
    }
    s.text(17, 20, "蓝莓加工厂 / " + titles[layer] + " " + candidate_label, 6)
    s.text(17, 29, "20t/天设计条件 · 非Native确定性生成 · 条件性概念设计，非施工图", 3.1, "#637c88")
    s.text(690, 20, "A1横版 / 1:200 / mm", 3.8)
    s.line([(17, 35), (824, 35)], lw=0.4)
    b = c["original_building"]
    for i, x in enumerate(b["coordinate_mapping"]["axis_x_mm"], 1):
        s.line([p(x, 0), p(x, 80300)], "#dbe3e8", 0.1, True)
        s.text(p(x, 0)[0], 92, str(i), 2.8, center=True)
        s.text(p(x, 0)[0], 511, str(i), 2.8, center=True)
        if i < 19:
            s.text(p(x, 0)[0] + 15, 81, "6000", 2.1, center=True)
    for key, y in b["coordinate_mapping"]["axis_y_mm"].items():
        s.line([p(0, y), p(108000, y)], "#dbe3e8", 0.1, True)
        s.text(26, p(0, y)[1] + 1, key, 2.8, center=True)
    s.line([(36, 69), (576, 69)], "#8399a6", 0.2)
    s.text(306, 65, "108000 = 18 × 6000", 3.3, center=True)
    box(b["outer_building_bbox_mm"], "#fafbfc", lw=0.5)
    for q in c["rooms"]:
        box(
            q["bbox_mm"],
            COLORS.get(q["zone_code"], "#edf1ed"),
            lw=0.32,
            data=f'data-room="{q["zone_code"]}"',
        )
    for a in c["equipment"]["operating_spaces"]:
        box(a["bbox_mm"], "#edf5f6", "#c6dfe4", 0.04)
    for q in c["equipment"]["items"]:
        kind = q["kind"]
        fill = (
            "#e5e8e8"
            if "pallet" in kind
            else "#a8bfce"
            if kind == "packing_line"
            else "#d7b88f"
            if kind == "case_erector"
            else "#c4d6ba"
            if kind == "ten_door_locker"
            else "#b8d5d7"
            if kind == "precooling_buffer"
            else "#d4c8b5"
        )
        box(q["bbox_mm"], fill, "#7b8b94", 0.09, data=f'data-equipment="{q["id"]}"')
        if kind in ("packing_line", "case_erector", "raw_crate_handoff", "pallet_handoff"):
            z = q["bbox_mm"]
            x, y = p((z[0] + z[2]) / 2, (z[1] + z[3]) / 2)
            s.text(x, y + 0.7, q["id"], 1.7, "#284758", True)
    for q in c["equipment"].get("process_operator_zones", []):
        box(q["bbox_mm"], "#d7b9b3", "#9f6f67", 0.1)
    for layout in c["equipment"]["layouts"].values():
        for q in layout.get("operator_positions", []):
            box(q["bbox_mm"], "#e6d7ca", "#b9a48f", 0.05)
    for col in b["columns"]:
        box(col["bbox_mm"], "#344b57", lw=0.1)
    for wall in b["retained_walls"]:
        for a, z in wall["segments_mm"]:
            s.line([p(*a), p(*z)], "#344b57", 0.35)
    for row in c["access_results"]:
        if row.get("status") != "PASS":
            continue
        color = (
            "#9673a8"
            if row["flow_kind"] == "PEOPLE"
            else "#a47c45"
            if row["flow_kind"] == "PACKAGING"
            else "#278a72"
        )
        for side in ("from", "to"):
            seg = row["portal_" + side]["segment"]
            pts = [
                p(float(seg[k]["x"]) * 1000, float(seg[k]["y"]) * 1000) for k in ("start", "end")
            ]
            s.line(pts, "#ffffff", 1.2)
            s.line(pts, color, 0.65)
        if row["flow_kind"] == "PEOPLE":
            route(
                [
                    [round(float(a["x"]) * 1000), round(float(a["y"]) * 1000)]
                    for a in row.get("centerline", [])
                ],
                color,
                0.3,
                True,
            )
    verified = {r["id"]: r for r in flows["routes"] if route_is_conditionally_usable(r)}
    chain = next(
        (q for q in flows["product_chains"] if q["status"] == "CONTINUOUS_CONDITIONAL_CHAIN"), None
    )
    selected = []
    if layer in ("main", "process") and chain:
        selected = [
            (verified[x["route_id"]], "#188574")
            for product_chain in flows["product_chains"]
            for x in product_chain["stages"]
            if x["route_id"] in verified
        ]
    if layer in ("main", "cartons"):
        selected.extend(
            (verified[x["route_id"]], "#b06f32")
            for x in flows["case_supply"]["line_assignments"]
            if x["route_id"] in verified
        )
    if layer == "cartons":
        selected.extend(
            (verified[id_], "#6f70a4")
            for id_ in flows["case_supply"]["blank_supply_routes"]
            if id_ in verified
        )
    if layer in ("main", "process"):
        selected.extend(
            (verified[rid], "#3d6aaf" if branch["flow_kind"] == "SECONDARY" else "#a34d79")
            for branch in flows["auxiliary_branches"]
            for rid in branch["route_ids"]
            if rid in verified
        )
    selected = list({r["id"]: (r, color) for r, color in selected}.values())
    selected_ids = {r["id"] for r, _ in selected}
    for transfer in flows["transfers"]:
        if (
            transfer["upstream_route"] not in selected_ids
            or transfer["downstream_route"] not in selected_ids
            or transfer["geometry_status"] != GEOMETRY
        ):
            continue
        route(transfer["load_path_mm"], "#a15b40", 0.35, transfer["validation_status"] == ASSUMED)
        for workspace in transfer["operation_spaces"]:
            a, b, r, t = workspace["bbox_mm"]
            s.line([p(a, b), p(r, b), p(r, t), p(a, t), p(a, b)], "#ad7d55", 0.12, True)
    for r, color in selected:
        route(
            r["centerline_mm"],
            color,
            0.35 if layer == "main" else 0.55,
            r["status"] == ASSUMED or layer == "cartons",
        )
        for contact in r.get("endpoint_contact_transfers", []):
            if contact["kind"] == "REGISTERED_MANUAL_LOAD_HANDOFF":
                route(contact["centerline_mm"], color, 0.25)
    for e in flows["endpoints"]:
        if e["object_id"].startswith(("PACK-", "ERECT-", "FILM-")):
            x, y = p(*e["contact_mm"])
            s.rect(x - 0.35, y - 0.35, 0.7, 0.7, "#c9634d", "#ffffff", 0.05)
    for i, r in enumerate(c["rooms"], 1):
        z = r["bbox_mm"]
        x, y = p(z[0] + 900, z[3] - 1000)
        s.rect(x - 2.5, y - 2.8, 8, 4.5, "#ffffff", "#ffffff", 0)
        s.text(x + 1.3, y, f"{i:02}", 2.7, center=True)
    s.line([(598, 44), (598, 550)], "#cbd8df", 0.2)
    s.text(609, 50, "12区 · 真实计算尺寸", 3.8)
    for i, r in enumerate(c["rooms"], 1):
        y = 61 + (i - 1) * 12.5
        s.text(609, y, f"{i:02} {r['name']}", 2.9)
        s.text(
            609,
            y + 4.8,
            f"{r['width_mm']} × {r['depth_mm']} / {float(r['area_m2']):.3f}㎡",
            2.55,
            "#617c89",
        )
    notes = [
        "候选状态：" + c["status"],
        f"主产品完整条件链 {flows['continuous_main_product_chain_count']}/6",
        f"设备路线 {flows['verified_route_count']}通过 / {flows['failed_route_count']}未贯通",
        "绿色：六线产品；蓝色：次果；玫色：冻果",
        "虚线机内/人工交接：条件操作，非厂家通过",
        "褐色：成箱配送 / 紫虚线：纸板补给",
        "紫色：人员路径 / 红点：待审设备接口",
        "14待冷缓冲位与6包装工作位分别计数",
        "N/S为两服务组，重排于本方案北侧工作带",
        "主通道2500；包材主通道5000（mm）",
        "托盘车及载荷1300×1800为待审假设",
        "转向2222方包络 ≠ 真实车辆运动学",
        "操作点600×900为未批准几何假设",
        "共用通道需调度；未证明同时交通/20t吞吐",
        "储存：保留原有序取放，非任意直接存取",
        "Truck、完整P2D及工程批准未成立",
    ]
    for i, n in enumerate(notes):
        s.text(609, 223 + i * 7.5, n, 2.7, "#526f7c")
    s.text(609, 360, "六线运输/机内参考段长度", 3.1)
    for i, q in enumerate(flows["product_chains"]):
        s.text(
            609,
            370 + i * 8.5,
            f"{q['line']}  {q['length_mm'] / 1000:.3f}m / {q['status'][:10]}",
            2.7,
        )
    s.text(609, 436, "交接载荷路径另存；不合并为单一车辆里程", 2.5, "#617c89")
    s.text(609, 452, "封膜机内部输送由声明接口连接，厂家能力待确认", 2.5, "#617c89")
    if "current_storage_requirements" in c:
        req = c["current_storage_requirements"]
        total = sum(x["required_positions"] for x in req.values())
        s.text(
            609,
            471,
            f"当前P1成品网格 {req['finished_goods_room']['required_positions']}位 / 总储位 {total}",
            3.0,
        )
        s.text(609, 481, "各方案保持当前容量；不同P1不作正式Pareto", 2.7, "#617c89")
    s.text(36, 532, "20m校尺段 = 100mm纸面长度 / 按100%打印", 2.8, "#617c89")
    for i in range(4):
        s.rect(36 + i * 25, 537, 25, 2, INK if i % 2 == 0 else "#ffffff", lw=0.12)
    s.text(36, 552, "数据源为同次计算坐标；未贯通路线不绘制完整箭头。所有结构柱保留。", 2.8)
    s.text(36, 561, "候选Hash：" + c["result_hash"], 2.15, "#617c89")
    s.line([(17, 570), (824, 570)], "#cbd8df", 0.2)
    s.text(17, 580, f"自主布局 {revision} / 设备端点、实际门洞、载荷与条件转向包络 / 非施工图", 2.8)
    s.save(path)


def export_process_package(
    result: dict[str, Any],
    project: dict[str, Any],
    parameters: dict[str, Any],
    output: Path,
    *,
    drawings: bool = True,
) -> None:
    output.mkdir(parents=True, exist_ok=False)

    def dump(name: str, data: Any) -> None:
        (output / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n"
        )

    dump("project-input.json", project)
    dump("process-parameters.json", parameters)
    dump(
        "layout-generation-results.json",
        {
            **{k: v for k, v in result.items() if k != "candidates"},
            "candidates": [
                {"file": "autonomous-layout-A12.json", "result_hash": c["result_hash"]}
                for c in result["candidates"]
            ],
        },
    )
    if not result["candidates"]:
        return
    c = result["candidates"][0]
    flows = c["process_continuity"]
    # Each raw witness is persisted once. Endpoint JSON is a compact independent
    # index into the immutable candidate rather than a second copy of all motion.
    dump("autonomous-layout-A12.json", c)
    dump(
        "equipment-endpoints-and-routes.json",
        {
            "source_candidate_hash": c["result_hash"],
            "endpoints": flows["endpoints"],
            "product_chains": flows["product_chains"],
            "case_supply": flows["case_supply"],
            "routes_file": "autonomous-layout-A12.json",
            "routes_json_pointer": "/process_continuity/routes",
            "route_summaries": [
                {
                    k: r[k]
                    for k in (
                        "id",
                        "source_endpoint",
                        "target_endpoint",
                        "purpose",
                        "centerline_mm",
                        "length_mm",
                        "status",
                    )
                }
                for r in flows["routes"]
            ],
        },
    )
    dump("iteration-feedback.json", result["attempts"])
    dump("process-admission.json", c["process_admission"])
    dump(
        "process-interfaces.json",
        {
            "candidate_hash": c["result_hash"],
            "transfers": flows["transfers"],
            "auxiliary_branches": flows["auxiliary_branches"],
        },
    )
    dump(
        "v11-function-coverage.json",
        {
            "candidate_hash": c["result_hash"],
            "original_required_identities": flows["v11_required_coverage"],
            "interior": c["equipment_aware_interior_paths"],
            "storage": c["storage_portal_interfaces"],
        },
    )
    original_ids = {
        r["id"] for r in flows["routes"] if not r["id"].startswith(("SECONDARY-", "FROZEN-"))
    }
    chosen_ids = set(c["process_admission"]["selected_route_ids"])
    dump(
        "route-selection.json",
        {
            **c["process_admission"]["counts"],
            "original_route_count": len(original_ids),
            "original_selected_count": len(original_ids & chosen_ids),
            "original_alternative_count": len(original_ids - chosen_ids),
            "selected_route_ids": sorted(chosen_ids),
            "exploratory_alternative_ids": c["process_admission"]["alternative_route_ids"],
            "categories_overlap": (
                "Machine-internal and short-operation routes are subsets of selected routes"
            ),
        },
    )
    detail = [
        "# R1补正：工艺支线、载具交接与全量准入",
        "",
        "几何核验不等于厂家内部工艺、人工操作或工程批准；所有条件操作的实际输入仍需确认。",
        "",
        "## 辅助物料支线",
        "|支线|来源|实际库位|运输段|",
        "|---|---|---|---|",
    ]
    detail.extend(
        f"|{b['flow_kind']}|{b['source_interface']}|{b['stock_handoff_object']}|"
        f"{', '.join(b['route_ids'])}|"
        for b in flows["auxiliary_branches"]
    )
    detail.extend(
        [
            "",
            "## 显式交接（参考点差与载荷实际连接路径分别保存）",
            "|交接|载具/载荷转换|参考点差mm|投影几何|操作|",
            "|---|---|---:|---|---|",
        ]
    )
    detail.extend(
        f"|{t['id']}|{t['kind']}|{t['reference_gap_mm']}|{t['geometry_status']}|{t['validation_status']}|"
        for t in flows["transfers"]
    )
    detail.extend(["", "## V1.1功能重新覆盖", "|房间|原需求|新证据|状态|", "|---|---|---|---|"])
    detail.extend(
        f"|{q['room']}|{q.get('from_access', q.get('requirement_identity'))} → "
        f"{q.get('to_access', '库内主通道')}|{q['coverage_id']}|{q['status']}|"
        for q in [*c["equipment_aware_interior_paths"], *c["storage_portal_interfaces"]]
    )
    detail.extend(
        [
            "",
            "## 全量准入",
            "```json",
            json.dumps(c["process_admission"], ensure_ascii=False, indent=2),
            "```",
            "",
            "## 实际输入仍需确认",
            "分选设备分流口、周转筐卸料/散果输送、包装机内输送与成箱出口、组托/拆托/复托方式、封膜机内部输送与能力；搬运工具、载荷稳定性、人体操作与调度、次果及冻果容器/储存工艺、H5实际柜门/活动尺度/洁污条件。全部保持INPUT_REQUIRED。",
        ]
    )
    (output / "process-detail.md").write_text("\n".join(detail) + "\n")
    for name, rows, fields in (
        (
            "equipment-placement.csv",
            c["equipment"]["items"],
            ["id", "room", "kind", "bbox_mm", "rotation_deg", "basis"],
        ),
        (
            "a1-a12-equipment-changes.csv",
            result["equipment_changes"],
            ["id", "kind", "old_bbox_mm", "new_bbox_mm", "reason"],
        ),
        (
            "a1-a12-room-changes.csv",
            result["room_changes"],
            [
                "zone_code",
                "original_bbox_mm",
                "new_bbox_mm",
                "translation_x_mm",
                "translation_y_mm",
                "added_area_m2",
            ],
        ),
        (
            "room-coordinates.csv",
            c["rooms"],
            [
                "zone_code",
                "name",
                "bbox_mm",
                "width_mm",
                "depth_mm",
                "area_m2",
                "required_area_m2",
                "column_area_m2",
            ],
        ),
        (
            "device-route-lengths.csv",
            flows["routes"],
            ["id", "source_object", "target_object", "purpose", "status", "length_mm", "failure"],
        ),
    ):
        with (output / name).open("w", newline="") as stream:
            w = csv.DictWriter(
                stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
            )
            w.writeheader()
            w.writerows(rows)
    if drawings:
        for label, layer in (
            ("autonomous-layout-A12", "main"),
            ("main-product-logistics", "process"),
            ("six-line-case-supply", "cartons"),
        ):
            draw_process_candidate(c, output / label, layer)
        import fitz

        mm = 72 / 25.4
        chosen = [
            q["bbox_mm"]
            for q in c["rooms"]
            if q["zone_code"]
            in ("sorting_packaging_room", "secondary_precooling_room", "coating_room")
        ]
        extent = [
            min(q[0] for q in chosen) - 1000,
            min(q[1] for q in chosen) - 1000,
            max(q[2] for q in chosen) + 1000,
            max(q[3] for q in chosen) + 1000,
        ]
        clip = fitz.Rect(
            (36 + extent[0] / 200) * mm,
            (500 - extent[3] / 200) * mm,
            (36 + extent[2] / 200) * mm,
            (500 - extent[1] / 200) * mm,
        )
        with fitz.open(output / "autonomous-layout-A12.pdf") as doc:
            doc[0].get_pixmap(dpi=200, clip=clip, alpha=False).save(
                output / "A12-process-detail.png"
            )
    stocks = "\n".join(
        f"|{s['layout']['room']}|{s['layout']['minimum_positions']}|{s['layout']['placed_positions']}|"
        for s in c["equipment"]["storage"]
    )
    routes = "\n".join(
        f"|{q['line']}|{q['length_mm'] / 1000:.3f}|{q['status']}|" for q in flows["product_chains"]
    )
    before_coat = next(q for q in result["baseline"]["rooms"] if q["zone_code"] == "coating_room")
    after_coat = next(q for q in c["rooms"] if q["zone_code"] == "coating_room")
    coat_change = next(q for q in result["room_changes"] if q["zone_code"] == "coating_room")
    capacity_trials = [q for q in result["attempts"] if "required_existing_positions" in q]
    capacity_feedback = "；".join(
        f"{q['variant']}：成品{q.get('placed_positions', {}).get('finished_goods_room', '未评估')}"
        f"/原{q['required_existing_positions']['finished_goods_room']}，{q['status']}"
        + (
            f"，关联组北移{q['group_translation_north_mm']}mm"
            if "group_translation_north_mm" in q
            else ""
        )
        for q in capacity_trials
    )
    comparison = f"""# 自主布局 V1.2 / 设备工艺物流贯通

本次从结构输入重新计算A1，再由实际设备、托盘工作位和人员操作带冲突触发新候选。
没有读取Owner/V2/V3的功能区或设备世界坐标。


12区、7条MUST、非货车Access {c["non_truck_access_pass_count"]}/11；
实际路径 {flows["verified_route_count"]} 条具有分级几何见证，
{flows["failed_route_count"]} 条未贯通。
全量准入：{c["status"]}；选用{c["process_admission"]["counts"]["selected_routes"]}条、
备用{c["process_admission"]["counts"]["exploratory_alternatives"]}条；
其中机内投影10条及短交接5条仅CONDITIONAL_OPERATION_ASSUMED，不是厂家验证。
次果、冻果及包材三支线与全部10+6项V1.1通行功能均纳入集中门禁；详见process-detail.md。
主产品完整链 {flows["continuous_main_product_chain_count"]}/6。
厂车运动学、多人同时交通、热工批次能力、20t吞吐、Truck及完整P2D均未由本轮证明。


## A1到V1.2的实际变化

四台分选间折箱机保持完整外形并旋转90°，中部保留2500mm通道、两列间1800mm补料操作带；
第五台保留包材库。
R1补正把四机中部间隔从2500扩至2540mm，各机沿Y向外移20mm；外围未通行空隙从50降至30mm，需厂家安装复核。
实际保留的主通道仍为2500mm，原封闭障碍相交谓词未放宽。
六线三对1000mm人员操作带不变，只缩小非通行的对间空隙。
新增14个独立缓冲位、6个线端托位及1个周转筐卸料托位，N/S为原B4服务组在自主房间中的位置映射，并非照搬两厅世界坐标。


包材库增放第二台折箱机的6次实际尝试均因货位不足被拒绝，未降低67位要求。
封膜房间为纳入完整托盘和南侧操作位，
从{before_coat["width_mm"]}×{before_coat["depth_mm"]}增加至
{after_coat["width_mm"]}×{after_coat["depth_mm"]}mm：
增加{coat_change["added_area_m2"]}㎡，不改变P1最低面积。
反馈导致成品库、办公室、出货区位置变化；
详见坐标差异CSV。
货位保留反馈：{capacity_feedback}。
封膜通道状态：{c["coating_actual_aisle_feedback"]["status"]}。
被柱体占据的矩形提案不被判为通过；若采用实际路线替换，保留同宽2500mm，
另对全部固定设备、托位和柱体复核。
首次7100深度操作带冲突记录保留。


V1.1只核验房间内部Portal接口，未建立完整设备端点链；
其端到端长度与冲突数为NOT_EVALUATED，不能伪称本次缩短了某个旧总长度。
当前各段参考线合计如下，包含代表性缓冲路径及机内声明输送；
跨载具交接的载荷锚点路径另存process-interfaces.json，不含在此合计中；
不是车辆行驶距离或产能指标。
每条链真正经过6条原合法物料门洞。


|包装线|条件中心线m|结果|
|---|---:|---|
{routes}

|库房|原最低货位|当前货位|
|---|---:|---:|
{stocks}

5台折箱机全部具备原料供给路径，6条线的成箱分配由30条实际路径及1800个合法覆盖组合中按长度选择；
不是产能分配证明。
共享道路、补料与出箱交会需要时间分离，不假定同时运行无冲突。
所有路线核查时保留其他载荷，源托位随载荷移动，目标为该批次预留空位；
原有序取放见证保留，但非所有货位都已按新的整车包络验证。


## 使用条件

托盘1200×1000，假设整车与载荷1300×1800；
直角转向保守外接方形2222mm。
主材料通道2500mm，包材库主通道5000mm；
门洞2400mm只作直线通过，禁止门内旋转。
短柜机/包装接口、柜机纸板入口及进出料方向均为待审设计假设。
局部操作带与主通道的验证分别保存，不以短窄交接替代主通道。


柜机原尺寸、原冷库工艺、原H5两班53人条件流程均保留；
若人员Portal变动，仅调用原适配器重新核验入口/离室路径，不更改H5模型。
真实柜门、人体、卫生要求仍INPUT_REQUIRED。
4.8kg与3.2kg、两端60s及重叠45s、6线人员10/10/10/8/8/7来自B3/B4参数条件，仅衔接几何，本轮没有重算产能或制冷。


## 复算

在backend中，使用Python3.12锁定依赖；
以functional_native_guard作为继承PYTHONPATH首项，运行scripts/generate_autonomous_process_layout.py，传入本目录project-input.json、process-parameters.json和预先不存在的输出目录。
可用--finished-storage-days改变输入；
结果重新计算或明确返回有界搜索未找到，不复用原坐标。


NEW_MAIN=false / Native未调用 / Grant与Claim未访问 / 正式CI未请求 / 概念设计非施工图。

"""
    (output / "layout-comparison.md").write_text(comparison.rstrip() + "\n")
    rows = "".join(
        f"<tr><td>{escape(q['line'])}</td><td>{q['length_mm'] / 1000:.3f}m</td>"
        f"<td>{escape(q['status'])}</td></tr>"
        for q in flows["product_chains"]
    )
    html = f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>自主布局V1.2</title>
<style>body{{font:15px/1.6 system-ui;
color:#243e4b;
margin:24px auto;
max-width:1600px;
padding:0 16px}}a{{color:#197d79}}button{{padding:9px 14px;
margin:3px;
background:#edf3f3;
border:1px solid #b6cbd0;
color:#243e4b;
cursor:pointer}}.plan{{overflow:auto;
border:1px solid #d2dfe3}}img{{width:100%;
min-width:1100px}}table{{border-collapse:collapse;
width:100%}}td,th{{padding:8px;
text-align:left;
border-bottom:1px solid #d2dfe3}}p{{max-width:1120px}}</style>
<h1>自主布局V1.2 · 设备到设备物流</h1>
<p>实际生成12区、设备端点、14待冷缓冲与6线托位。
整体候选状态：{result["status"]}。
{flows["continuous_main_product_chain_count"]}条完整条件产品链；
{flows["case_supply"]["status"]}。
图中实线为条件几何运输，机内/人工交接虚线仅作CONDITIONAL_OPERATION_ASSUMED。
次果、冻果分流口均是待审条件接口。
条件矩形转向不是实际车辆运动学，厂区工程批准及连续产能未成立。
</p>
<p>
<a href="autonomous-layout-A12.pdf">A1 1:200 PDF</a> ·
<a href="autonomous-layout-A12.png">高清PNG</a> ·
<a href="autonomous-layout-A12.svg">可缩放SVG</a> ·
<a href="equipment-endpoints-and-routes.json">端点和路径索引</a> ·
<a href="autonomous-layout-A12.json">原始候选及全部见证</a> ·
<a href="layout-comparison.md">A1对照</a> ·
<a href="process-detail.md">支线/交接/16项通行明细</a> ·
<a href="process-admission.json">全量准入</a> ·
<a href="route-selection.json">选用与备用计数</a>
</p>
<div>
<button data-file="autonomous-layout-A12.svg">整厂平面</button>
<button data-file="main-product-logistics.svg">主产品设备链</button>
<button data-file="six-line-case-supply.svg">五台折箱机/六线供箱</button>
</div>
<div class="plan">
<img id="drawing" src="autonomous-layout-A12.svg" alt="真实比例自主布局">
</div>
<p>全量功能门禁：{c["process_admission"]["status"]}；六线{c["process_admission"]["main_line_count"]}/6，三条辅助物料支线纳入。
原室内{c["process_admission"]["v11_coverage"][0]["verified"]}/10、
仓储接口{c["process_admission"]["v11_coverage"][1]["verified"]}/6按新布局重算。
原87条：选用{len(original_ids & chosen_ids)}、备用{len(original_ids - chosen_ids)}；
新增次果/冻果4条。
机内投影与实际操作尚未确认，完整P2D与工厂适用性NOT_EVALUATED。</p>
<h2>各线运输与机内参考段（跨载具交接另列）</h2>
<table>
<tr>
<th>包装线</th>
<th>中心线长度</th>
<th>状态</th>
</tr>{rows}</table>
<p>14缓冲位与6线工作位不重复计数；
N/S为服务组，在本方案独立北侧工作带重新组织。
包材货位仍满足67位。
全部源、目标、门洞、转向及障碍身份可在JSON复核；
未以旧房间中心连线代替设备路径。
</p>
<p>柜机门面、搬运包络和操作空间为未批准假设。
共享通道需调度，逐条几何通过不代表同时交通通过。
4.8kg/3.2kg及生产节拍保持B3/B4条件，未重新计算产能。
H5真实功能仍INPUT_REQUIRED。
Truck、完整P2D、工程批准和工厂适用性均未成立。
</p>
<script>document.querySelectorAll('button').forEach(b=>b.onclick=()=>document.getElementById('drawing').src=b.dataset.file)</script>
</html>"""
    (output / "autonomous-layout-review.html").write_text(html)
