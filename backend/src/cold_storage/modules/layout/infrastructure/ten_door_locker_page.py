# ruff: noqa: E501 -- persisted engineering diagrams and review prose
"""Render calculated complete-unit evidence; no browser engineering formulas."""

import html
import json
from typing import Any


def _rect(b: list[int], fill: str, label: str, stroke: str = "#546f7a") -> str:
    x, y, r, t = b
    return f'<rect x="{x}" y="{-t}" width="{r - x}" height="{t - y}" fill="{fill}" stroke="{stroke}" stroke-width="9"><title>{html.escape(label)}</title></rect>'


def _text(x: int, y: int, value: str, size: int = 130, anchor: str = "start") -> str:
    return f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="#294656">{html.escape(value)}</text>'


def complete_plan(case: dict[str, Any], *, doors: bool = False) -> str:
    g = case["geometry"]
    width = case["room_dimensions_mm"][1]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-600 {-width - 1000} 27600 {width + 2550}"><rect x="-600" y="{-width - 1000}" width="27600" height="{width + 2550}" fill="white"/>'
    ]
    parts.append(
        _rect(g["room"]["local_bounds_mm"], "#f5f8f9", "独立反事实房间；原H5不改", "#284656")
    )
    for a in g["waiting_snapshots"]["1"]["aisles"]:
        parts.append(_rect(a, "#ddecdf", "实际保留净通道"))
    for u in g["inventory"]["cabinet_units"]:
        for col in g["inventory"]["vertical_columns"]:
            if col["unit_id"] == u["id"]:
                parts.append(
                    _rect(
                        col["bounds_mm"],
                        "#b7d6e3" if col["shift"] == 1 else "#c9d9bd",
                        col["id"] + f"；分配班{col['shift']}；425mm不是净宽",
                    )
                )
        parts.append(_rect(u["bounds_mm"], "none", f"{u['id']} 完整850×390标称柜体；班次不拆柜"))
        x, y, r, top = u["bounds_mm"]
        parts.append(
            f'<line x1="{x + 425}" y1="{-top}" x2="{x + 425}" y2="{-y}" stroke="#637a8b" stroke-width="8" stroke-dasharray="30 20"/>'
        )
        parts.append(_text(x + 425, -y + 140, u["id"], 115, "middle"))
    for i, h in enumerate(g["model"]["homes"], 1):
        b = h["bounds_mm"]
        parts.append(
            _rect(b, "#b9d2d2" if h["yaw_degrees"] else "#d5dfe8", f"本位{i:02} {h['region']}")
        )
        parts.append(_text((b[0] + b[2]) // 2, -(b[1] + b[3]) // 2 + 40, str(i), 110, "middle"))
    profile = case["door_profiles"][1]
    event = next(iter(profile["doors"]["events"]), None)
    if doors and event:
        for person in case["closed_door_flows"][0]["events"]:
            if person["operation"] == "OPEN_FOR_RETRIEVE":
                for o in person["proof"]["people_before"]:
                    if o["role"] == "FRONT_OPERATOR":
                        parts.append(_rect(o["bounds_mm"], "#dfb765", o["id"] + " 柜前取衣时刻"))
                break
    if doors:
        displayed = (
            event["proof"]["doors"] if event else [profile["doors"]["registry"][i] for i in (0, 5)]
        )
        for d in displayed:
            x, y = d["hinge_mm"]
            points = " ".join(f"{a},{-b}" for a, b in d["arc_mm"])
            parts.append(
                f'<polygon points="{x},{-y} {points}" fill="#d5948a88" stroke="#ad4337" stroke-width="12"><title>{html.escape(d["id"])}；假设{d["hinge_side"]}90°，z={d["z_interval_mm"]}mm；不是已审五金</title></polygon>'
            )
    elif g["snapshots"]:
        for a in g["snapshots"][0]["front_activity_evaluation"]["activity_volumes"]:
            parts.append(
                _rect(a["bounds_mm"], "#e8c47e88", "另一时刻的600×900mm条件活动；非额外人员")
            )
    for p in g["room"]["portals"]:
        a, b = p["segment_mm"]
        parts.append(
            f'<line x1="{a[0]}" y1="{-a[1]}" x2="{b[0]}" y2="{-b[1]}" stroke="#0b7b67" stroke-width="60"><title>{html.escape(p["id"])}；1500mm原Portal</title></line>'
        )
    parts += [
        _text(0, -width - 600, f"{case['id']} · 26331×{width}mm · 11台完整柜 / 22列 / 110格", 220),
        _text(
            0,
            -width - 260,
            f"本位{case['home_count']}/53；柜体850×390×1800为Owner标称选型；425分列/人体/安装/门型均未批准",
            155,
        ),
        _text(
            0, 450, "绿色＝连续净通道；蓝色＝初始本位；金色＝另一操作时刻，不能叠加为更多人员", 155
        ),
        _text(
            0, 800, "红色＝逐门假设扫掠投影；无完整事件时仅示意U01两扇门，不代表动态验证通过", 155
        ),
        _text(
            0,
            1150,
            "INPUT_REQUIRED · 概念评审，非施工图；外部Site/Access、储物卫生及实际可达性未批准",
            155,
        ),
    ]
    return "".join(parts) + "</svg>"


def complete_elevation(case: dict[str, Any]) -> str:
    inv = case["geometry"]["inventory"]
    cells = [c for c in inv["compartments"] if c["unit_id"] == "U06"]
    doors = {d["compartment_id"]: d for d in case["door_profiles"][1]["doors"]["registry"]}
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-180 -2250 2450 2650"><rect x="-180" y="-2250" width="2450" height="2650" fill="white"/>',
        _rect([0, 0, 850, 1800], "#eff3f6", "850×1800标称正面", "#294656"),
    ]
    for c in cells:
        d = doors[c["id"]]
        x = 12 if c["column_id"].endswith("-L") else 437
        z, top = d["z_interval_mm"]
        parts.append(
            _rect(
                [x, z, x + 400, top],
                "#b7d6e3" if c["shift"] == 1 else "#c9d9bd",
                c["id"] + f"；班{c['shift']}；净格宽深高均INPUT_REQUIRED",
            )
        )
        parts.append(_text(x + 200, -(z + top) // 2, c["id"], 30, "middle"))
        assignment = (
            f"S{c['shift']} 备用" if c["assigned_person_id"] is None else c["assigned_person_id"]
        )
        parts.append(_text(x + 200, -(z + top) // 2 + 48, assignment, 35, "middle"))
    parts += [
        _text(0, -2110, "U06 · 一台完整柜，左右列分别分配两班", 58),
        _text(0, -1960, "850 × 390 × 1800mm · Owner选定标称外包络", 48),
        _text(1000, -1730, "外高1800mm / 外宽850mm / 外深390mm", 42),
        _text(1000, -1600, "425mm只是均分前缘，不是净宽", 42),
        _text(1000, -1450, "门面400×320mm为图示标称参考", 42),
        _text(1000, -1320, "360mm深度标签不是已审内净深", 42),
        _text(1000, -1130, "立面层位100+4×340→最高门面1780mm", 40),
        _text(1000, -1000, "该层位/间隙/铰链/90°均为未批准演示", 40),
        _text(1000, -800, "衣杆0、额外层板0：仅Owner转述图示", 40),
        _text(1000, -620, "内部板厚、分隔、真实净尺寸与取放待确认", 40),
        _text(0, 150, "每个门独立编号；不把完整850mm柜体拆为半柜产品", 48),
        _text(0, 290, "原照片未取得，照片Hash为null；此图不是供应商实物图纸", 45),
    ]
    return "".join(parts) + "</svg>"


def review_page(summary: dict[str, Any]) -> str:
    data = json.dumps(summary, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return TEMPLATE.replace("__DATA__", data)


TEMPLATE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>H5 · Owner选定十门柜实物评审</title>
<style>body{margin:0;background:#edf1f3;color:#263e4c;font:14px system-ui,"PingFang SC",sans-serif}header{padding:22px;background:#203e50;color:white}h1{font-size:24px;margin:0 0 10px}main{max-width:1500px;margin:auto;padding:14px}section{background:white;border:1px solid #cad5dc;padding:16px;margin-bottom:14px}h2{font-size:18px;margin:0 0 12px}p{line-height:1.8}.notice{border-left:4px solid #a46d35;padding:12px;background:#fff3df}table{border-collapse:collapse;width:100%}td,th{padding:9px;text-align:left;border-bottom:1px solid #dce3e7;vertical-align:top}th{background:#edf3f5}.scroll{overflow:auto}select,button{font:inherit;padding:8px;border:1px solid #9db1bc;background:white;color:#263e4c}.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:12px 0}.plan{overflow:auto;border:1px solid #c7d5dc}.plan img{display:block;width:100%;min-width:1150px}.elevation img{width:100%;max-width:1100px}.bad{color:#9d392e}.muted{color:#536e7c}pre{white-space:pre-wrap;word-break:break-word;font-size:12px;background:#f2f6f7;padding:12px;max-height:330px;overflow:auto}a{color:#087666}#allocation{max-height:400px;overflow:auto}@media(max-width:650px){main{padding:7px}section{padding:12px}header{padding:18px}h1{font-size:21px}}</style>
<header><h1>H5 · 11台完整五层十门柜</h1><div>850×390×1800mm 标称选型｜两班各53人｜22列110格｜无坐凳、本人柜前站立</div></header><main>
<section><div class="notice"><b>Owner确认的是柜型选择及标称规格，尚非供应商技术审核。</b><br>实际照片文件未取得，照片Hash为null。400×360×320mm不是已证实的内部净尺寸。425mm均分前缘、层位、门扇镜像/90°、人体活动及现场安装均为未批准条件。实际储物、卫生、可达性及工程批准仍未成立。</div></section>
<section><h2>实体柜与人员分配分离</h2><p>11台完整850mm柜体，不使用单列半柜。每班分配11列55格，其中53格对应设计人员、2格备用；U06左右两列分属两班，柜体本身不拆分，同一格口不跨班共享。</p><p><a href="compartment-allocation.csv">下载110格分配表（106人＋4备用）</a> · <a href="owner-selection.json">Owner选型来源</a> · <a href="review-summary.json">结构化结果</a> · <a href="engineering-report.md">完整报告</a></p></section>
<section><h2>C / 3850mm 同条件重新验证</h2><div class="scroll"><table><thead><tr><th>房间与条件</th><th>本位/完成</th><th>闭门运动子校核</th><th>逐门开启＋完整条件流程</th><th>最小余量下界 / 目标</th><th>实际功能</th></tr></thead><tbody id="rows"></tbody></table></div><p class="muted">安装输入基值与加余量后的有效尺寸分别列出。不满足53本位时停止完整流程，不删除人员、不缩小人体、不降低通道。模板失败不代表全局不可行。闭门子校核不能替代开门检查。20/20mm组开柜后的保守间隙下界为15mm，低于50mm余量目标；条件流程完成不等于余量目标满足或实际可用。</p></section>
<section><h2>11台实物柜、53个人位与原Portal</h2><div class="controls"><label>方案 <select id="case"></select></label><button id="normal">本位与柜前活动</button><button id="doors">逐门扫掠时刻</button><button id="zoom">柜区放大 / 全景</button></div><div class="plan"><img id="plan" alt="按实际毫米绘制的11台完整柜体及人位"></div><pre id="detail"></pre></section>
<section><h2>五层十门柜正立面 · U06跨班分列</h2><div class="elevation"><img id="elevation" alt="850×1800mm真实比例标称立面，蓝绿两列分属两班"></div><p class="muted">此处层位只是条件演示；五层实际净高、衣物体积、无衣杆条件下的折叠取放、门扇五金与最高/最低格口可达范围均需资料。没有自动增加隔板。</p></section>
<section><h2>110格唯一分配</h2><div id="allocation"><table><thead><tr><th>完整柜</th><th>列/层</th><th>班次</th><th>设计人员</th><th>独立格口</th></tr></thead><tbody id="people"></tbody></table></div></section>
<section><h2>与旧400×500mm参考的差异</h2><pre id="difference"></pre><p class="muted">只是柜体标称外包络差异；长边总占用增加，不代表人员组织必然改善。实际安装总长含柜间隙，见每个方案结果。旧R3～R13结果不改写。</p></section>
<section><h2>实际缺失输入</h2><ul id="missing"></ul><p class="bad">ACTUAL_CALIBRATION=INPUT_REQUIRED · ENGINEERING_APPROVAL=NOT_EVALUATED · FACTORY_APPLICABILITY=NOT_EVALUATED</p></section></main>
<script>const data=__DATA__;const $=s=>document.querySelector(s);const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let mode='plan',zoomed=false;for(const r of data.reports){$('#case').add(new Option(r.id,r.id));const tr=document.createElement('tr');tr.innerHTML='<td>'+esc(r.id)+'<br>'+esc(r.conditions.finish_mm)+'mm完成面 / '+esc(r.conditions.installation_gap_mm)+'mm安装基值；目标'+esc(r.margin_target_mm)+'mm</td><td>'+r.home_count+'/53；两班'+esc(JSON.stringify(r.completed_users))+'</td><td>'+esc(r.closed_status)+'</td><td>'+r.door_profiles.map(p=>esc(p.hinges)+'：'+esc(p.status)).join('<br>')+'</td><td>'+r.door_profiles.map(p=>esc(p.hinges)+'：'+esc(p.minimum_declared_margin_lower_bound_mm)+' / '+r.margin_target_mm+'mm；达到目标='+p.margin_target_met).join('<br>')+'</td><td>INPUT_REQUIRED</td>';$('#rows').append(tr)}
function show(){const r=data.reports.find(r=>r.id===$('#case').value);$('#plan').src=r.id+'-'+mode+'.svg';$('#plan').style.width=zoomed?'3600px':'100%';$('#elevation').src=r.id+'-elevation.svg';$('#detail').textContent=JSON.stringify(r,null,2)}
$('#case').onchange=show;$('#normal').onclick=()=>{mode='plan';show()};$('#doors').onclick=()=>{mode='doors';show()};$('#zoom').onclick=()=>{zoomed=!zoomed;show()};$('#difference').textContent=JSON.stringify(data.difference,null,2);for(const c of data.allocation){let tr=document.createElement('tr');tr.innerHTML=[c.unit_id,c.column_id+'/T'+c.tier,c.shift,c.person_id||'SPARE',c.compartment_id].map(v=>'<td>'+esc(v)+'</td>').join('');$('#people').append(tr)}for(const m of data.missing_inputs){const li=document.createElement('li');li.textContent=m;$('#missing').append(li)}show();</script></html>"""
