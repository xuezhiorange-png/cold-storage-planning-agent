# ruff: noqa: E501 -- persisted engineering labels
"""R15 R4 views read persisted coordinates/results; no browser calculations."""

import html
import json
from typing import Any

from cold_storage.modules.layout.infrastructure.ten_door_locker_page import (
    _rect,
    _text,
    complete_plan,
)


def plan_svg(case: dict[str, Any]) -> str:
    view = dict(
        case, room_dimensions_mm=[26331, 3850], home_count=53, door_profiles=case["profiles"]
    )
    return complete_plan(view, doors=True).replace(
        '<svg xmlns="http://www.w3.org/2000/svg"',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="371"',
        1,
    )


def coordinate_comparison(base: dict[str, Any], case: dict[str, Any]) -> str:
    g = case["geometry"]
    old = base["geometry"]["snapshots"][0]
    new = g["snapshots"][0]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="568" viewBox="-300 -4400 14500 5150"><rect x="-300" y="-4400" width="14500" height="5150" fill="white"/>'
    ]
    parts.append(
        _rect(g["room"]["local_bounds_mm"], "#f4f7f8", "固定房间；此图放大柜区，完整平面另附")
    )
    for aisle in old["aisles"]:
        parts.append(_rect(aisle, "none", "R15-03原通道", "#b37344"))
    for aisle in new["aisles"]:
        parts.append(_rect(aisle, "#bad2c366", "新1300mm通道；完整运动已另行复核"))
    for u in g["inventory"]["cabinet_units"]:
        parts.append(_rect(u["bounds_mm"], "#b7d6e3", u["id"] + " 柜体未动"))
    for h in g["model"]["homes"]:
        parts.append(_rect(h["bounds_mm"], "#d5dfe8", "53个初始本位之一；操作前时刻"))
    for s, color in ((old, "#b37344"), (new, "#197b91")):
        for p in s["people"]:
            if p["role"] == "FRONT_OPERATOR":
                parts.append(
                    _rect(p["bounds_mm"], "none", p["id"] + " 操作时刻；不是额外人员", color)
                )
    flow = case["closed_door_flows"][0]
    event = next(e for e in flow["events"] if e["operation"] == "TO_PERSONAL_LOCKER")

    def paths(proof: dict[str, Any]) -> list[list[list[int]]]:
        own = [proof["points_mm"]] if proof.get("points_mm") else []
        return own + [p for leg in proof.get("legs", []) for p in paths(leg)]

    for route in paths(event["proof"]):
        points = " ".join(f"{x},{-y}" for x, y in route)
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="#176b94" stroke-width="18"><title>原连续运动校核输出的真实中心线；非直线距离替代</title></polyline>'
        )
    parts += [
        _text(0, -4150, f"R15-03 → {case['id']} · 柜区同尺度叠加", 190),
        _text(0, 300, "棕线=原站位/通道；蓝线=新站位；绿=新通道；深蓝=首个实际到柜路径", 135),
        _text(
            0, 570, "房间、11台柜与Portal不动；本位和柜前人体属于不同时间，不可叠加计算人数", 130
        ),
    ]
    return "".join(parts) + "</svg>"


def section_svg(base: dict[str, Any], case: dict[str, Any]) -> str:
    """Actual y/z projection at the critical lower-tier door, same axes/scale."""
    sections = [("R15-03 原断面", base["section"]), (case["id"] + " 条件断面", case["section"])]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1908" viewBox="-180 -2350 4550 6200"><rect x="-180" y="-2350" width="4550" height="6200" fill="white"/>'
    ]
    for index, (label, s) in enumerate(sections):
        offset = index * 3000

        def yz(
            low: int, high: int, z: int, top: int, fill: str, title: str, offset: int = offset
        ) -> str:
            return f'<rect x="{low}" y="{offset - top}" width="{high - low}" height="{top - z}" fill="{fill}" stroke="#536d79" stroke-width="3"><title>{html.escape(title)}</title></rect>'

        parts += [
            _text(0, offset - 2110, label + " · 横轴y向北，纵轴z向上，单位mm", 62),
            _text(
                40,
                offset - 2000,
                "蓝=柜体/开柜人体；绿=通道；灰=本位；空框=关门后更衣；红=条件门扇投影",
                43,
            ),
            yz(
                s["cabinet_mm"][1],
                s["cabinet_mm"][3],
                0,
                1800,
                "#a9cbd9",
                "柜体390mm深、1800mm标称外高",
            ),
            yz(545, 975, 100, 420, "#d9918455", "原保守门扇扫掠y/z投影；不等于真实五金"),
            yz(s["body_mm"][1], s["body_mm"][3], 0, 1800, "#c7d9e1", "开柜时450×650×1800静态人体"),
            yz(
                s["activity_mm"][1],
                s["activity_mm"][3],
                0,
                1800,
                "none",
                "关柜后600×900活动体积的y/z投影；另一操作阶段",
            ),
            yz(s["branch_south_mm"], s["branch_north_mm"], 0, 1800, "#c4dec9", "1300mm有效支廊"),
            yz(
                s["north_home_south_mm"],
                s["north_home_north_mm"],
                0,
                1800,
                "#d9e2e7",
                "北侧旋转本位，450mm法向占用",
            ),
            f'<line x1="0" y1="{offset}" x2="3850" y2="{offset}" stroke="#344f5d" stroke-width="6"/>',
            f'<line x1="3820" y1="{offset}" x2="3820" y2="{offset - 1850}" stroke="#344f5d" stroke-width="6"/>',
        ]
        for low, high, text in [
            (975, s["body_mm"][1], f"门—人 {s['gaps']['conditional_own_door_mm']}"),
            (
                s["body_mm"][3],
                s["branch_south_mm"],
                f"更衣—通道 {s['gaps']['standing_activity_to_branch_mm']}",
            ),
            (s["branch_south_mm"], s["branch_north_mm"], "支廊1300"),
            (
                s["branch_north_mm"],
                s["north_home_south_mm"],
                f"本位—廊 {s['gaps']['north_home_to_branch_mm']}",
            ),
        ]:
            line_y = offset + (180 if low < 1700 else 340)
            parts.append(
                f'<path d="M{low},{line_y - 30}v60 M{low},{line_y}H{high} M{high},{line_y - 30}v60" stroke="#386a7a" fill="none" stroke-width="3"/>'
            )
            parts.append(_text((low + high) // 2, line_y + 100, text + "mm", 41, "middle"))
        parts.append(
            _text(
                40,
                offset - 1900,
                f"柜后/完成面不变；北墙剩余{s['gaps']['north_home_to_finished_wall_mm']}mm；门z=100～420mm",
                46,
            )
        )
    parts.append(
        _text(
            0,
            3650,
            "100mm仅为未批准敏感性目标；关柜更衣与开柜人体属不同工序；实际弯腰/伸手/取衣未批准",
            48,
        )
    )
    return "".join(parts) + "</svg>"


def review_page(summary: dict[str, Any]) -> str:
    encoded = json.dumps(summary, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return TEMPLATE.replace("__DATA__", encoded)


TEMPLATE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>H5 R15 R4 · 柜前站位与支廊协调</title>
<style>body{margin:0;background:#edf2f4;color:#253e4b;font:15px system-ui,sans-serif}header{background:#233f4d;color:white;padding:24px}main{max-width:1420px;margin:auto;padding:14px}section{background:white;border:1px solid #c7d4da;padding:18px;margin-bottom:14px}h1{font-size:24px;margin:0 0 9px}h2{font-size:19px}p{line-height:1.7}.notice{border-left:4px solid #b67836;background:#fff3df;padding:12px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;min-width:970px}td,th{padding:9px;border-bottom:1px solid #d6e0e4;text-align:left}th{background:#edf3f5}.plan{overflow:auto}.plan img{width:100%;min-width:1100px}.section img{width:100%;max-width:1100px}a{color:#176d80}select{font:inherit;padding:8px}pre{white-space:pre-wrap;word-break:break-word;background:#f1f5f7;padding:12px;max-height:340px;overflow:auto}@media(max-width:650px){main{padding:6px}section{padding:12px}header{padding:18px}}</style>
<header><h1>H5 · 柜前站位与支廊的最小协调</h1><div>26331×3850mm固定房间 · 11台完整十门柜 · 两班各53人 · 53人初始同时在室</div></header><main>
<section><p class="notice">条件几何距离达到100mm，不等于实际操作净距或工程批准。门扇、人体、完成面及安装仍是既有未批准假设。照片核验暂停NOT_EVALUATED；未读取或公开原图。</p><p><a href="engineering-report.md">完整报告</a> · <a href="review-summary.json">结果JSON</a> · <a href="coordinate-difference.json">坐标变化</a> · <a href="full-witnesses.json.gz">完整新流程与失败/未达目标记录</a> · <a href="source-manifest.json">来源与证据Hash</a></p></section>
<section><h2>六项有限对照</h2><div class="scroll"><table><thead><tr><th>对照</th><th>人员/支廊/北侧本位位移mm</th><th>门扇最小解析距离mm</th><th>更衣—廊 / 北侧—廊mm</th><th>两班完成</th><th>原空间余量 / 全部100目标</th></tr></thead><tbody id="rows"></tbody></table></div><p>R4-01仅为必要断面负对照：只移人员会把更衣至通道余量降至65mm，未创建完整布局或流程见证，不能宣称物理不可行。其余五套实际几何均重新执行原完整非Native流程及逐门校核。</p></section>
<section><h2>真实比例平面与操作路径</h2><label>候选 <select id="candidate"></select></label><div class="plan"><img id="plan" alt="完整固定房间内柜体、53个初始本位、实际通道和开柜时刻"></div><div class="plan"><img id="difference" alt="柜区坐标叠加与原运动校核返回的真实路径"></div><p>初始本位、开柜人体与关柜后的更衣包络属于不同时间；没有增加或隐藏人员。</p></section>
<section><h2>最不利门扇横断面</h2><div class="section"><img id="section" alt="E110柜门—本人—支廊—北侧本位的原新等比例y/z断面"></div><pre id="detail"></pre></section>
<section><h2>仍需实物和现场确认</h2><p>真实铰链、门厚、角度和五金突出；弯腰伸手、携衣与关柜动作；实际内净格和衣物分隔；五层取放可达性、洁污流程和房门开启。柜前站距变大可能影响取衣，不能用600mm假设参考值证明实际可达。</p><p>ACTUAL_CALIBRATION=INPUT_REQUIRED · ENGINEERING_APPROVAL=NOT_EVALUATED · FACTORY_APPLICABILITY=NOT_EVALUATED</p></section></main>
<script>const data=__DATA__,$=x=>document.querySelector(x);for(const r of data.reports){const tr=document.createElement('tr');for(const text of [r.id,[r.choice.operator_delta_mm,r.choice.branch_delta_mm,r.section.north_home_delta_mm].join(' / '),r.exact_min_mm===null?'仅断面 '+r.section.gaps.conditional_own_door_mm:r.exact_min_mm.join(' / '),r.section.gaps.standing_activity_to_branch_mm+' / '+r.section.gaps.north_home_to_branch_mm,JSON.stringify(r.completed_users),JSON.stringify(r.closed_min_mm)+' / '+r.all_100_met]){const td=document.createElement('td');td.textContent=text;tr.append(td)}$('#rows').append(tr);if(r.has_geometry)$('#candidate').add(new Option(r.id,r.id))}$('#candidate').value=data.selected_candidate_id||'R4-00';function show(){const r=data.reports.find(x=>x.id===$('#candidate').value);$('#plan').src=r.id+'-plan.svg';$('#difference').src=r.id+'-difference.svg';$('#section').src=r.id+'-section.svg';$('#detail').textContent=JSON.stringify(r,null,2)}$('#candidate').onchange=show;show();</script></html>"""
