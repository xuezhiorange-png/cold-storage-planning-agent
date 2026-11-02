"""Read-only projection of current-run multi-root coordinates and witnesses."""

from __future__ import annotations

import csv
import json
from collections import Counter
from html import escape
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import canonical_json
from cold_storage.modules.layout.infrastructure.process_continuity_export import (
    draw_process_candidate,
)


def export_multi_root_suite(
    cases: list[dict[str, Any]], parameters: dict[str, Any], output: Path, *, drawings: bool = True
) -> None:
    output.mkdir(parents=True, exist_ok=False)

    def dump(folder: Path, name: str, data: Any) -> None:
        (folder / name).write_text(canonical_json(data) + "\n")

    dump(output, "process-parameters.json", parameters)
    summary = []
    table = []
    buttons = []
    failures = []
    root_links = []
    for case in cases:
        project, result = case["project"], case["result"]
        days = project["business"]["finished_storage_days"]
        folder = output / f"{days}-days"
        folder.mkdir()
        dump(folder, "project-input.json", project)
        dump(folder, "search-configuration.json", result["search_configuration"])
        dump(folder, "root-searches.json", result["root_searches"])
        dump(folder, "root-coordinate-and-failure-ledger.json", result["roots"])
        stage_counts = Counter(q["status"] for q in result["roots"])
        partial_counts: Counter[str] = Counter()
        for search in result["root_searches"]:
            partial_counts.update(search["stats"].get("partial_constraint_rejection_counts", {}))
        stage_summary = {
            "source_result_hash": result["result_hash"],
            "root_option_evaluations": len(result["roots"]),
            "unique_complete_room_geometries": len(
                {q["room_geometry_hash"] for q in result["roots"]}
            ),
            "partial_rejection_event_counts": dict(partial_counts),
            "complete_state_status_counts": dict(stage_counts),
            "new_qualified_organisations": result.get("new_qualified_organisation_count", 0),
            "qualified_non_novel_variants": result.get("qualified_variant_count", 0),
            "full_pipeline_attempts": result["search_budget"]["full_pipeline_attempts_used"],
            "local_search_limits": result.get("local_search_limits"),
            "failure_counts_are_finite_search_events_not_global_unsat_proofs": True,
        }
        dump(folder, "constraint-stage-summary.json", stage_summary)
        dump(folder, "reference-execution.json", result["reference_execution"])
        rows = []
        coordinates: list[dict[str, Any]] = []
        for i, candidate in enumerate(result["candidates"]):
            label = f"A14-{chr(65 + i)}"
            stem = f"autonomous-layout-{label}"
            is_reference = candidate["multi_root_origin"]["kind"] == "V13_RECOMPUTED_REFERENCE"
            dump(folder, stem + ".json", candidate)
            if drawings:
                draw_process_candidate(
                    candidate,
                    folder / stem,
                    revision="V1.4",
                    candidate_label=f"{days}d / {label} / "
                    + ("参考重算" if is_reference else "多根合格"),
                )
            flows = candidate["process_continuity"]
            dump(
                folder,
                label + "-process-network.json",
                {
                    "source_candidate_hash": candidate["result_hash"],
                    "endpoints": flows["endpoints"],
                    "routes": flows["routes"],
                    "product_chains": flows["product_chains"],
                    "auxiliary_branches": flows["auxiliary_branches"],
                    "case_supply": flows["case_supply"],
                    "transfers": flows["transfers"],
                },
            )
            stock = {
                q["layout"]["room"]: q["layout"]["placed_positions"]
                for q in candidate["equipment"]["storage"]
            }
            row = {
                "label": label,
                "file": stem + ".json",
                "hash": candidate["result_hash"],
                "origin": candidate["multi_root_origin"],
                "organisation_key": candidate["organisation_key"],
                "difference_from_reference": candidate["difference_from_current_reference"],
                "metrics": candidate["adaptive_metrics"],
                "stock": stock,
                "total_stock": sum(stock.values()),
                "admission": candidate["process_admission"],
                "equipment_counts": candidate["equipment"]["placed_counts"],
                "changing_two_shifts_53": candidate["changing_function"][
                    "conditional_complete_sequence_verified"
                ],
                "candidate_classification": candidate.get("candidate_classification"),
            }
            rows.append(row)
            coordinates.extend({"candidate": label, **q} for q in candidate["equipment"]["items"])
            m = row["metrics"]
            diff = row["difference_from_reference"]
            changed = len(diff["changed_material_core_rooms"]) if diff else 0
            table.append(
                f"|{days}|{label}|{row['origin']['kind']}|{changed}|"
                f"{stock['finished_goods_room']} / {row['total_stock']}|"
                f"{m['footprint_area_m2']}|"
                f"{m['selected_transport_reference_length_mm'] / 1000:.3f}|"
                f"{m['selected_transport_turns']}|{m['potential_route_crossings']}|"
            )
            display = {
                k: row[k]
                for k in (
                    "label",
                    "origin",
                    "metrics",
                    "stock",
                    "total_stock",
                    "changing_two_shifts_53",
                )
            }
            display["engineering_checks"] = candidate["process_admission"]["engineering_checks"]
            display["functional_coverage"] = candidate["process_admission"]["v11_coverage"]
            buttons.append(
                f'<button data-file="{days}-days/{stem}.svg" '
                f'data-json="{days}-days/{stem}.json" '
                f'data-summary="{escape(json.dumps(display, ensure_ascii=False), quote=True)}">'
                f"{days}天 {label} · {'当前输入重算参考' if is_reference else '多根候选'}</button>"
            )
        with (folder / "equipment-placement.csv").open("w", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
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
            for q in coordinates:
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
        dump(folder, "actual-equipment-coordinates.json", coordinates)
        dump(
            folder,
            "actual-room-coordinates.json",
            [
                {"candidate": f"A14-{chr(65 + i)}", **q}
                for i, c in enumerate(result["candidates"])
                for q in c["rooms"]
            ],
        )
        dump(
            folder,
            "layout-generation-results.json",
            {
                **{k: v for k, v in result.items() if k != "candidates"},
                "candidates": rows,
            },
        )
        summary.append(
            {
                "days": days,
                "result_hash": result["result_hash"],
                "status": result["status"],
                "search_budget": result["search_budget"],
                "resources": case["resources"],
                "candidates": rows,
                "constraint_stages": stage_summary,
            }
        )
        for root in result["roots"]:
            if root["status"] != "CONDITIONAL_PROCESS_CANDIDATE":
                failures.append(
                    f"|{days}|{root['root_id']}|{root['origin']['profile']}|{root['status']}|"
                    f"{len(root.get('static_conflicts', []))}|{root.get('capacity_deficit', 0)}|"
                )
        for root in root_examples(result):
            stem = f"rejected-{root['root_id']}"
            dump(folder, stem + ".json", root)
            if drawings:
                draw_rejected_root(root, project, folder / (stem + ".svg"))
            root_links.append(
                f"<li>{days}天 {escape(root['root_id'])}："
                f'<a href="{days}-days/{stem}.svg">本次未通过选项图</a> · '
                f'<a href="{days}-days/{stem}.json">坐标与拒绝</a> · '
                f"{escape(root['status'])}</li>"
            )
    dump(output, "case-comparison.json", summary)
    execution_note = "；".join(
        f"{case['project']['business']['finished_storage_days']}天："
        f"{len({q['room_geometry_hash'] for q in case['result']['roots']})}个不同完整房间几何 / "
        f"{len(case['result']['roots'])}次房间与局部选项评估，"
        + (
            "有界搜索未取得新的合格组织"
            if case["result"]["status"] == "NO_NEW_ORGANISATION_WITHIN_BOUNDED_SEARCH"
            else "已取得不同合格组织"
        )
        for case in cases
    )
    (output / "layout-comparison.md").write_text(
        "# 自主整厂布局 V1.4 · 多根空间搜索\n\n"
        "仅由当前业务、P1、建筑结构和设备规格重新生成。A14-A是本次重算的V1.3参考，"
        "不是读取历史坐标或历史PASS。候选名称与profile名称均不作为结构多样性证据。\n\n"
        "|天数|候选|来源|核心房间变更数|成品/总储位|Footprint㎡|运输参考段m|转弯|潜在交会|\n"
        "|---:|---|---|---:|---:|---:|---:|---:|---:|\n"
        + "\n".join(table)
        + "\n\n同一工况内先全量准入，再按真实核心空间关系区分组织，"
        "最后按交会、参考段、转弯、面积排序。"
        "全局平移、镜像、90度转动和仅覆膜间变化不计新组织。"
        "这些指标不替代原九/十二指标正式比较，不在7/8天不同P1之间宣称Pareto改善。\n\n"
        "完整条件准入保留12区、7MUST、11非货车Access、原货位、设备、柱体、六线三支线、"
        "57交接、10室内+6仓储接口及两班53人。机内与人工交接仍含待审条件操作；"
        "真实车辆运动学、同时交通、吞吐、Truck、完整P2D和工程批准未成立。\n\n"
        "根搜索记录真实DFS节点、柱体/房间拒绝、当前房间与设备坐标、货位试排、"
        "门面与精确轮廓失败及反馈来源。必要预检查不继承为完整PASS；接受候选重新执行全部验收。"
        "有界未找到新组织不构成全局不可行证明。\n\n"
        "## 实际失败节点\n\n"
        "|天数|根|偏好|状态|静态冲突记录|缺少储位|\n|---:|---|---|---|---:|---:|\n"
        + "\n".join(failures)
        + "\n\n完整原始对象、位置和原因见各工况root-coordinate-and-failure-ledger.json。\n"
    )
    (output / "layout-review.html").write_text(
        """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>V1.4 多根整厂方案</title>
<style>body{margin:0;background:#eef2f4;color:#173343;font:15px system-ui,sans-serif}
header{padding:18px 24px;background:#173343;color:white}h1{font-size:23px;margin:0 0 8px}
nav{display:flex;gap:8px;flex-wrap:wrap;padding:14px 20px}
button{padding:10px;border:1px solid #9aafb9;
background:white;border-radius:4px;color:#173343;cursor:pointer}button.active{background:#d5e5eb}
main{display:grid;grid-template-columns:minmax(0,1fr) 290px;gap:12px;padding:0 20px 24px}
object{width:100%;min-height:68vh;background:white}
aside{background:white;padding:16px;overflow:auto;max-height:75vh}
pre{white-space:pre-wrap;word-break:break-word;font-size:12px}a{color:#1b688a}
@media(max-width:900px){main{grid-template-columns:1fr}object{min-height:45vh}header{padding:15px}}
</style><header><h1>自主布局 V1.4 · 多根空间方案</h1>
同次计算坐标 / A1 · 1:200 / 条件性概念设计，非施工图
</header>"""
        + '<p style="margin:14px 20px;color:#874123">'
        + escape(execution_note)
        + "</p><nav>"
        + "".join(buttons)
        + '</nav><details style="margin:0 20px 15px">'
        "<summary>不同空间组织的实际淘汰根（非合格方案）</summary><ul>"
        + "".join(root_links)
        + "</ul></details>"
        + """<main><section><object id="plan" type="image/svg+xml"></object>
<p><a id="svg">SVG原图</a> · <a id="pdf">A1 PDF</a> · <a id="png">高清PNG</a> ·
<a id="json">完整JSON</a>
 · <a href="layout-comparison.md">比较及失败记录</a></p></section>
<aside><strong>本候选计算记录</strong>
<pre id="details"></pre><p>功能条件验证 ≠ 工程批准 ≠ 整厂最终适用。各方案独立重算，
全局镜像或仅覆膜变化不计结构新方案。</p></aside></main><script>
const all=[...document.querySelectorAll('button')];for(const b of all)b.onclick=()=>{
all.forEach(x=>x.classList.toggle('active',x===b));const f=b.dataset.file;
document.querySelector('#plan').data=f;for(const k of ['svg','pdf','png']){
document.querySelector('#'+k).href=f.slice(0,-4)+'.'+k}
document.querySelector('#json').href=b.dataset.json;
document.querySelector('#details').textContent=JSON.stringify(JSON.parse(b.dataset.summary),null,2)};
if(all.length)all[0].click();</script></html>"""
    )


def root_examples(result: dict[str, Any]) -> list[dict[str, Any]]:
    """A bounded visual selection, never admission or a replacement candidate."""
    from cold_storage.modules.layout.domain.multi_root_space import organisation_key

    selected = []
    seen = set()
    for profile in ("LINEAR_BANDED", "CENTRAL_PROCESS_CORE", "PROCESS_SPINE_WITH_PERIPHERAL_BANKS"):
        rows = [
            q
            for q in result["roots"]
            if q["origin"]["profile"] == profile
            and q.get("equipment_coordinates")
            and not q.get("process_admission", {}).get("accepted")
        ]
        rows.sort(
            key=lambda q: (
                -int("process_admission" in q),
                -int("current_necessary_portal_footprint_check" in q),
                q["capacity_deficit"],
                len(q["static_conflicts"]),
                q["root_id"],
            )
        )
        for row in rows:
            key = organisation_key({"rooms": row["room_coordinates"]})
            if key not in seen:
                selected.append(row)
                seen.add(key)
                break
    return selected


def draw_rejected_root(root: dict[str, Any], project: dict[str, Any], path: Path) -> None:
    """Actual rejected coordinates in a separate SVG; never a fake valid plan."""
    from cold_storage.modules.layout.infrastructure.autonomous_layout_export import COLORS

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="841mm" height="594mm" '
        'viewBox="0 0 841 594"><rect width="841" height="594" fill="white"/>'
    ]

    def text(x: float, y: float, value: str, size: float = 3, color: str = "#173343") -> None:
        parts.append(
            f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
            f'font-family="system-ui,sans-serif">{escape(value)}</text>'
        )

    def point(x: int, y: int) -> tuple[float, float]:
        return 36 + x / 200, 500 - y / 200

    def box(b: list[int], fill: str, stroke: str = "#78909d", lw: float = 0.1) -> None:
        x, y = point(b[0], b[3])
        parts.append(
            f'<rect x="{x}" y="{y}" width="{(b[2] - b[0]) / 200}" '
            f'height="{(b[3] - b[1]) / 200}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{lw}"/>'
        )

    text(17, 22, f"V1.4 · 淘汰根 {root['root_id']} · 未通过完整准入", 6, "#a23b3b")
    text(17, 32, "当前输入实际计算坐标 / 非合格工程方案 / 非施工图")
    building = project["building"]
    box(building["outer_building_bbox_mm"], "#fafbfc", lw=0.4)
    for i, x in enumerate(building["coordinate_mapping"]["axis_x_mm"], 1):
        a, b = point(x, 0), point(x, 80300)
        parts.append(
            f'<path d="M{a[0]} {a[1]}L{b[0]} {b[1]}" stroke="#dae2e6" '
            'stroke-width=".1" stroke-dasharray="2 2"/>'
        )
        text(a[0], 92, str(i), 2.7)
    for q in root["room_coordinates"]:
        b = q["bbox_mm"]
        box(b, COLORS.get(q["zone_code"], "#edf1ed"), lw=0.3)
    for q in root["equipment_coordinates"]:
        box(q["bbox_mm"], "#b4c4cd", lw=0.06)
    for q in building["columns"]:
        box(q["bbox_mm"], "#2e4551")
    for q in root["room_coordinates"]:
        b = q["bbox_mm"]
        x, y = point(b[0] + 700, b[3] - 900)
        text(x, y, q["zone_code"], 2.2)
        text(x, y + 3.5, f"{b[2] - b[0]} × {b[3] - b[1]} mm", 2.2)
    for q in root["static_conflicts"]:
        if q.get("moving_bbox_mm"):
            box(q["moving_bbox_mm"], "none", "#c33d3d", 0.45)
    pre = root.get("current_necessary_portal_footprint_check", {})
    for q in pre.get("uncovered_pockets", []):
        for b in q["cells_mm"]:
            box(b, "#f9d9d5", "#c33d3d", 0.4)
    witness = root.get("rejected_full_witness", {})
    endpoints = {q["id"]: q for q in witness.get("process_continuity", {}).get("endpoints", [])}
    failures = root.get("failed_route_witnesses", [])
    affected_rooms = set()
    for failed in failures:
        for side in ("source_endpoint", "target_endpoint"):
            ep = endpoints[failed[side]]
            affected_rooms.add(ep["room"])
            x, y = point(*ep["dock_reference_mm"])
            parts.append(
                f'<path d="M{x - 1.2} {y - 1.2}L{x + 1.2} {y + 1.2}'
                f'M{x - 1.2} {y + 1.2}L{x + 1.2} {y - 1.2}" stroke="#c33d3d" '
                'stroke-width=".45"/>'
            )
    for row in witness.get("access_results", []):
        for side in ("from", "to"):
            if row.get(side + "_ref") not in affected_rooms:
                continue
            seg = row["portal_" + side]["segment"]
            a, b = [
                point(round(float(seg[k]["x"]) * 1000), round(float(seg[k]["y"]) * 1000))
                for k in ("start", "end")
            ]
            parts.append(
                f'<path d="M{a[0]} {a[1]}L{b[0]} {b[1]}" stroke="#c33d3d" stroke-width=".65"/>'
            )
    text(607, 106, "A1 · 1:200 · mm", 4)
    text(607, 121, root["origin"]["profile"], 2.5)
    text(607, 135, root["status"], 2.2, "#a23b3b")
    text(
        607, 153, f"储位缺口 {root['capacity_deficit']} / 静态记录 {len(root['static_conflicts'])}"
    )
    text(607, 174, "红框：设备/柱体/预留通道冲突", 2.8)
    text(607, 186, "红面：当前精确并集的封闭空区", 2.8)
    text(607, 203, "本图不表示工艺贯通或工程通过", 2.8)
    text(607, 215, "红叉/粗门线：未贯通段端点与相关门洞", 2.8)
    for i, q in enumerate(root["storage"]):
        text(607, 230 + i * 14, q["room"], 2.5)
        text(607, 236 + i * 14, f"{q['placed']} / {q['required']}位；有序取放={q['pick_put']}", 2.5)
    for i, row in enumerate(failures[:6]):
        text(607, 330 + i * 14, row["id"], 2.5, "#a23b3b")
        text(607, 336 + i * 14, row.get("failure", row["status"]), 2.4, "#a23b3b")
    text(36, 546, "20m = 100mm纸面长度 / 原始拒绝与坐标见同名JSON")
    parts.append('<path d="M36 535H136" stroke="#173343" stroke-width=".4"/>')
    text(36, 560, "房间Hash：" + root["room_geometry_hash"], 2.2)
    parts.append("</svg>")
    path.write_text("".join(parts))
