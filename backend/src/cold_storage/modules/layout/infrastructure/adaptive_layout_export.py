"""Read-only projection of the same-run adaptive results, never a calculator."""

from __future__ import annotations

import csv
import json
from html import escape
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import canonical_json
from cold_storage.modules.layout.infrastructure.process_continuity_export import (
    draw_process_candidate,
)


def export_adaptive_package(
    result: dict[str, Any],
    project: dict[str, Any],
    parameters: dict[str, Any],
    output: Path,
    *,
    drawings: bool = True,
) -> list[dict[str, Any]]:
    output.mkdir(parents=True, exist_ok=False)

    def dump(name: str, data: Any, *, compact: bool = False) -> None:
        (output / name).write_text(
            (
                canonical_json(data)
                if compact
                else json.dumps(data, ensure_ascii=False, indent=2, default=str)
            )
            + "\n"
        )

    dump("project-input.json", project)
    dump("process-parameters.json", parameters)
    dump("search-configuration.json", result["search_configuration"])
    dump("candidate-search.json", result["attempts"])
    dump("current-p1-storage-requirements.json", result["current_storage_requirements"])
    summaries = []
    coordinate_rows: list[dict[str, Any]] = []
    item_rows: list[dict[str, Any]] = []
    days = project["business"]["finished_storage_days"]
    for i, c in enumerate(result["candidates"]):
        label = f"A13-{chr(65 + i)}"
        stem = f"autonomous-layout-{label}"
        dump(stem + ".json", c, compact=True)
        if drawings:
            draw_process_candidate(
                c, output / stem, revision="V1.3", candidate_label=f"{days}d / {label}"
            )
        f = c["process_continuity"]
        a = c["process_admission"]
        stock = {
            s["layout"]["room"]: s["layout"]["placed_positions"] for s in c["equipment"]["storage"]
        }
        row = {
            "label": label,
            "file": stem + ".json",
            "hash": c["result_hash"],
            "origin": c["adaptive_origin"],
            "search_node": c["adaptive_search_node"],
            "status": c["status"],
            "metrics": c["adaptive_metrics"],
            "stock": stock,
            "total_stock": sum(stock.values()),
            "non_truck_access": c["non_truck_access_pass_count"],
            "main_lines": a["main_line_count"],
            "auxiliary": a["auxiliary_flows"],
            "transfer_count": len(f["transfers"]),
            "v11_coverage": a["v11_coverage"],
            "equipment_counts": c["equipment"]["placed_counts"],
            "changing_two_shifts_53": c["changing_function"][
                "conditional_complete_sequence_verified"
            ],
        }
        summaries.append(row)
        dump(
            f"{label}-process-network.json",
            {
                "source_candidate_hash": c["result_hash"],
                "endpoints": f["endpoints"],
                "routes": [
                    {
                        k: r[k]
                        for k in (
                            "id",
                            "source_object",
                            "target_object",
                            "source_endpoint",
                            "target_endpoint",
                            "centerline_mm",
                            "length_mm",
                            "status",
                        )
                    }
                    for r in f["routes"]
                ],
                "product_chains": f["product_chains"],
                "auxiliary_branches": f["auxiliary_branches"],
                "case_supply": f["case_supply"],
                "transfers": f["transfers"],
                "full_geometry_witness": stem + ".json",
                "geometry_json_pointer": "/process_continuity",
            },
        )
        coordinate_rows.extend({"candidate": label, **r} for r in c["rooms"])
        item_rows.extend({"candidate": label, **q} for q in c["equipment"]["items"])
    dump(
        "layout-generation-results.json",
        {**{k: v for k, v in result.items() if k != "candidates"}, "candidates": summaries},
    )
    dump("actual-room-coordinates.json", coordinate_rows)
    dump("actual-equipment-coordinates.json", item_rows)
    with (output / "equipment-placement.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "candidate",
                "id",
                "room",
                "kind",
                "x_mm",
                "y_mm",
                "right_mm",
                "top_mm",
                "rotation_deg",
            ]
        )
        for q in item_rows:
            writer.writerow(
                [
                    q["candidate"],
                    q["id"],
                    q["room"],
                    q["kind"],
                    *q["bbox_mm"],
                    q.get("rotation_deg", 0),
                ]
            )
    return summaries


def export_adaptive_suite(
    cases: list[dict[str, Any]],
    parameters: dict[str, Any],
    output: Path,
    *,
    drawings: bool = True,
) -> None:
    output.mkdir(parents=True, exist_ok=False)
    summary = []
    for case in cases:
        days = case["project"]["business"]["finished_storage_days"]
        rows = export_adaptive_package(
            case["result"], case["project"], parameters, output / f"{days}-days", drawings=drawings
        )
        summary.append(
            {
                "days": days,
                "result_hash": case["result"]["result_hash"],
                "status": case["result"]["status"],
                "search_budget": case["result"]["search_budget"],
                "operation_counts": case["result"]["operation_counts"],
                "resource_usage": case["resources"],
                "candidates": rows,
            }
        )
    (output / "case-comparison.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    table = []
    buttons = []
    for case in summary:
        for c in case["candidates"]:
            metrics = c["metrics"]
            folder = f"{case['days']}-days"
            stem = c["file"].removesuffix(".json")
            table.append(
                f"|{case['days']}|{c['label']}|{c['origin']}|"
                f"{c['stock']['finished_goods_room']} / {c['total_stock']}|"
                f"{metrics['footprint_area_m2']}|"
                f"{metrics['selected_transport_reference_length_mm'] / 1000:.3f}|"
                f"{metrics['selected_transport_turns']}|{metrics['potential_route_crossings']}|"
            )
            buttons.append(
                f'<button data-file="{folder}/{stem}.svg" data-link="{folder}/{c["file"]}">'
                f"{case['days']}天 {escape(c['label'])}</button>"
            )
    report = "\n".join(table)
    (output / "layout-comparison.md").write_text(f"""# 自主布局 V1.3 · 动态业务与空间反馈

当前输入重新计算P1并生成房间；未读取旧候选坐标。以下为同次程序计算结果。
7天网格324位、8天网格364位；原8天最低360位不能代替364位网格需求。
其余库存、预冷位置和设备数量均按各自当前P1或当前设备规格获取。

|存储天数|候选|空间方案|成品/总储位|Footprint㎡|选中运输参考段m|转弯|潜在中心线交会|
|---:|---|---|---:|---:|---:|---:|---:|
{report}

仅完整准入后的候选参与字典序排序：潜在交会、运输参考段、转弯、房间面积。
这是设计候选排序，不是原九/十二指标正式Pareto；不同P1不能跨工况宣称正式改善。
中心线交会不是同时交通冲突；参考段总长不是某台车的实际行驶里程。
七天不退化是原容量与全量条件功能均保留，不声称全部路线数值均更优。

搜索先检查原Authority、MUST、柱体和当前网格，再进行设备、合法门洞及全部工艺验证。
房间旋转、柱边联动移位、柔性连接房间延伸、生产组位置变体均有实际坐标记录。
设备/门洞失败时尝试另一个当前网格与真实库位端点；失败不计为合格候选。
托盘旋转时原网格间距一同旋转，50mm载荷余量、3000mm仓储主通道、
2500mm工艺主通道及1300×1800mm整车假设均保留。
当前完整检查包括12区/7MUST/11Access、六线/三支线/57交接、10室内+6仓储接口、两班53人条件流程。
57项中部分操作仍为CONDITIONAL_OPERATION_ASSUMED；供应商机内、真实车辆运动学、
同时调度、柜型与人体、吞吐、Truck及完整P2D未批准，不因几何通过而升级。

candidate-search.json保留每个实际节点、房间坐标、失败位置和容量；预算耗尽不是全局不可行证明。
实际网格节点和运动操作分别统计，不发行或消费Stage A/B资源份额，不把非Native操作计数冒充原Work。
原V1.2的8天失败与所有历史证据保持原样。生成器不读取它们。

## 复算

在backend使用锁定Python3.12环境，将tests/functional_native_guard置于PYTHONPATH首项，
并保留该环境给子进程，运行scripts/generate_autonomous_adaptive_layout.py。
传入本次输入、工艺参数、search-configuration.json、天数及不存在的输出目录。
Native禁用的两个API若被请求将抛错，不能执行实际Solve。

独立opt-in；生产MCP、默认、原面积Authority、正式9/12比较器均未改变。
NEW_MAIN=false / Native=0 / Grant或Claim未访问 / FULL_CI=NOT_REQUESTED。
""")
    first = next(
        (
            f"{c['days']}-days/{r['file'].removesuffix('.json')}.svg"
            for c in summary
            for r in c["candidates"]
        ),
        "",
    )
    html = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>自主布局V1.3</title>
<style>body{{font:15px/1.6 system-ui;color:#213e4b;
max-width:1600px;margin:24px auto;padding:0 14px}}
button{{padding:10px 16px;margin:4px;background:#edf4f3;
border:1px solid #aec8c8;color:#213e4b;cursor:pointer}}
.plan{{overflow:auto;border:1px solid #c9d7dc}}img{{width:100%;min-width:1000px}}
a{{color:#127b72}}p{{max-width:1150px}}</style>
<h1>自主布局V1.3 · 7→8天实际再布局</h1>
<p>从当前项目输入、真实建筑结构和P1重新计算。原7天容量与全量功能保留，8天采用364个成品网格位。
每套候选均重新验证六条主产品链、三条辅助支线、57项交接、11条非货车Access和16项室内/仓储接口。
未通过的空间与设备尝试保留在各工况搜索记录中。</p>
<p>条件性概念设计；机内与人工交接仍需工程输入。几何验证不等于设备批准、同时交通、Truck或完整P2D通过。</p>
<p><a href="layout-comparison.md">完整对照</a> · <a href="case-comparison.json">结构化比较</a> ·
<a id="raw" href="">当前原始坐标及见证</a></p>
<div>{"".join(buttons)}</div><div class="plan">
<img id="drawing" src="{first}" alt="同次计算的真实比例整厂布局"></div>
<p>A1横版、1:200，按100%打印。原建筑1～19轴、108000mm；室内柱保留并分别避让设备与通道。
不同存储天数属于不同P1，不能跨工况冒充正式Pareto。潜在中心线交会仍需生产调度。</p>
<script>const bs=document.querySelectorAll('button');bs.forEach(b=>b.onclick=()=>{{
document.getElementById('drawing').src=b.dataset.file;document.getElementById('raw').href=b.dataset.link;
}});if(bs.length)bs[0].click();</script></html>"""
    (output / "autonomous-adaptive-review.html").write_text(html)

    if len(cases) > 1 and all(c["result"]["candidates"] for c in cases[:2]):
        a, b = (c["result"]["candidates"][0] for c in cases[:2])
        with (output / "input-change-room-equipment-diff.csv").open("w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(
                ["object_type", "id", "before_bbox_mm", "after_bbox_mm", "same_position"]
            )
            for kind, aa, bb, key in (
                ("room", a["rooms"], b["rooms"], "zone_code"),
                ("equipment", a["equipment"]["items"], b["equipment"]["items"], "id"),
            ):
                first_items, last_items = (
                    {q[key]: q["bbox_mm"] for q in rows} for rows in (aa, bb)
                )
                for id_ in sorted(set(first_items) | set(last_items)):
                    old, new = first_items.get(id_), last_items.get(id_)
                    writer.writerow([kind, id_, old, new, old == new])
