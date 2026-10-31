# ruff: noqa: E501 -- persisted review diagrams and engineering prose
"""R15 review views of persisted geometry; no browser engineering calculations."""

import html
import json
from typing import Any

from cold_storage.modules.layout.infrastructure.ten_door_locker_page import (
    _rect,
    _text,
    complete_plan,
)


def case_plan(case: dict[str, Any], *, doors: bool = False) -> str:
    profiles = case.get("profiles", case.get("door_profiles"))
    return complete_plan(
        dict(case, room_dimensions_mm=[26331, 3850], door_profiles=profiles), doors=doors
    )


def comparison_plan(base: dict[str, Any], candidate: dict[str, Any]) -> str:
    g = candidate["geometry"]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-600 -5100 27600 6600"><rect x="-600" y="-5100" width="27600" height="6600" fill="white"/>',
        _rect(g["room"]["local_bounds_mm"], "#f5f8f9", "26331×3850mm固定边界"),
    ]
    for a in g["waiting_snapshots"]["1"]["aisles"]:
        parts.append(_rect(a, "#deece2", "1300mm原净通道"))
    for u in g["inventory"]["cabinet_units"]:
        parts.append(_rect(u["bounds_mm"], "#b7d6e3", u["id"] + " 完整柜体未动"))
    old = {tuple(h["bounds_mm"]) for h in base["geometry"]["model"]["homes"]}
    new = {tuple(h["bounds_mm"]) for h in g["model"]["homes"]}
    for b in sorted(old - new):
        parts.append(_rect(list(b), "none", "旧本位", "#aa5149"))
    for b in sorted(new - old):
        parts.append(_rect(list(b), "#387a8b88", "新本位"))
    for b in sorted(old & new):
        parts.append(_rect(list(b), "#d9e0e3", "保留坐标"))
    for p in g["room"]["portals"]:
        a, b = p["segment_mm"]
        parts.append(
            f'<line x1="{a[0]}" y1="{-a[1]}" x2="{b[0]}" y2="{-b[1]}" stroke="#087766" stroke-width="65"><title>{html.escape(p["id"])}</title></line>'
        )
    parts += [
        _text(0, -4650, "R14 52本位 → R15 条件重排；房间、柜体和Portal不动", 220),
        _text(0, -4250, "红线：被替换本位；蓝绿：新本位；灰：保留坐标；完整运动另行验证", 165),
        _text(0, 500, "600×900活动、450×650人体、200mm等待间隔、1300mm通道均保留", 165),
        _text(0, 900, "柜门65mm条件间隙 < 100mm未批准目标；不是实际功能或整厂适用PASS", 165),
    ]
    return "".join(parts) + "</svg>"


def clearance_svg(trace: dict[str, Any]) -> str:
    d, p = trace["door"], trace["person"]
    hx, hy = d["hinge_mm"]
    radius = d["radius_mm"]
    pad = d["thickness_mm"]
    x0, y0, right, top = p["bounds_mm"]
    left = min(hx - 150, x0 - 100)
    low = hy - 120
    span_x = max(right + 130 - left, 1050)
    span_y = top + 180 - low
    poly = " ".join(f"{x},{-y}" for x, y in d["arc_mm"])
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{left} {-top - 450} {span_x + 950} {span_y + 700}"><rect x="{left}" y="{-top - 450}" width="{span_x + 950}" height="{span_y + 700}" fill="white"/>'
    ]
    parts.append(_rect([x0, y0, right, top], "#d4e4e8", p["id"] + "450×650×1800mm条件人体"))
    parts.append(
        f'<polygon points="{hx},{-hy} {poly}" fill="#cd847955" stroke="#a84b3e" stroke-width="3"><title>解析四分之一圆盘；绘图折线不用于距离证明</title></polygon>'
    )
    b = [
        min(hx, hx + d["direction"][0] * (radius + pad)),
        hy,
        max(hx, hx + d["direction"][0] * (radius + pad)),
        hy + radius + pad,
    ]
    parts.append(_rect(b, "none", "原扫掠包围盒", "#b99375"))
    parts.append(
        f'<line x1="{hx}" y1="{-hy - radius - pad}" x2="{hx}" y2="{-y0}" stroke="#ad4337" stroke-width="4"/>'
    )
    proof = trace["distance"]
    parts += [
        _text(
            left + 15,
            -top - 330,
            f"S{trace['shift']} E{trace['event']} · {d['id']} → {p['id']}",
            36,
        ),
        _text(
            left + 15,
            -top - 240,
            f"层{trace['tier']} z={d['z_interval_mm']}mm；人体z=0..1800mm",
            33,
        ),
        _text(right + 80, -y0 - 60, f"包围盒下界 {trace['archived_lower_bound_mm']}mm", 31),
        _text(
            right + 80,
            -y0 + 30,
            f"解析模型 [{proof['model_distance_lower_um']}, {proof['model_distance_upper_um']}] ×0.001mm",
            31,
        ),
        _text(
            right + 80, -y0 + 120, "原解析碰撞：" + str(proof["collision_original_predicate"]), 31
        ),
        _text(
            left + 15,
            -low + 180,
            "400mm叶宽＋15mm保守厚度模型；非实测五金；600×900更衣阶段柜门关闭",
            32,
        ),
        _text(
            left + 15,
            -low + 270,
            "原15mm不能升级为50mm；实际门型、人体动作与净距仍INPUT_REQUIRED",
            32,
        ),
    ]
    return "".join(parts) + "</svg>"


def review_page(summary: dict[str, Any]) -> str:
    data = json.dumps(summary, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return TEMPLATE.replace("__DATA__", data)


TEMPLATE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>H5 · R15 本位重排与柜门间隙</title>
<style>body{margin:0;background:#eef2f4;color:#253e4d;font:14px system-ui,"PingFang SC",sans-serif}header{background:#213f50;color:white;padding:24px}h1{font-size:25px;margin:0 0 8px}main{max-width:1500px;margin:auto;padding:14px}section{background:white;border:1px solid #ccd7de;margin:0 0 14px;padding:16px}h2{font-size:18px;margin:0 0 10px}p{line-height:1.8}.notice{border-left:4px solid #b1753e;background:#fff3e0;padding:12px;line-height:1.8}.scroll,.plan{overflow:auto}table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #dce4e8;text-align:left;vertical-align:top}th{background:#eff4f6}.plan img{display:block;width:100%;min-width:1100px}.local img{width:100%;max-width:1400px}select,button{font:inherit;padding:8px;border:1px solid #a0b3be;background:white}.controls{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}pre{white-space:pre-wrap;word-break:break-word;background:#f2f6f7;padding:12px;max-height:360px;overflow:auto;font-size:12px}a{color:#087766}.bad{color:#9e3d30}@media(max-width:650px){main{padding:6px}section{padding:12px}header{padding:18px}h1{font-size:21px}}</style>
<header><h1>H5 · 11台十门柜，本位重排与柜门间隙</h1><div>R15独立条件评审｜26331×3850mm固定边界｜两班各53人｜不改变R14历史</div></header><main>
<section><div class="notice">保持11台850×390×1800mm完整柜、22列110格、U06跨班分列及原两处1500mm Portal。完成面30/安装基值40/目标100mm、450×650人体、600×900活动和1300mm有效通道均未降低。条件流程完成、余量目标满足、实际工程批准是三个独立结论。</div><p><a href="engineering-report.md">工程报告</a> · <a href="review-summary.json">结果JSON</a> · <a href="coordinate-difference.json">新旧坐标差异</a> · <a href="photo-source-supplement.json">照片来源补充</a> · <a href="full-new-witnesses.json.gz">新完整见证</a></p></section>
<section><h2>照片证据</h2><pre id="photo"></pre><p>Owner报告的Hash仅用于核对原始文件。未获取原始字节时不声称原图已验证；照片不公开、不嵌入页面。标称门尺寸不是内部净尺寸，也不证明铰链、门厚和开门角度。</p></section>
<section><h2>12组有限检查与完整流程</h2><div class="scroll"><table><thead><tr><th>组合</th><th>本位</th><th>两班完成</th><th>逐门 / 联合流程</th><th>最低下界 /100目标</th><th>阻断</th></tr></thead><tbody id="rows"></tbody></table></div><p class="bad">静态53本位不能替代连续进入、换位与离室；失败轨迹保留。完整流程完成也不等于100mm目标满足。有限模板失败不是全局不可行。</p></section>
<section><h2>原52本位与新重排</h2><div class="controls"><label for="candidate">候选</label><select id="candidate"></select><button id="normal">本位与活动</button><button id="doors">开柜时刻</button><button id="zoom">放大 / 全景</button></div><p>原52本位：</p><div class="plan"><img src="original-52-plan.svg" alt="R14原3850mm严格条件52个本位"></div><p>新候选：</p><div class="plan"><img id="plan" alt="R15确定性本位重排毫米比例图"></div><details><summary>该候选的完整流程与条件</summary><pre id="detail"></pre></details></section>
<section><h2>具体坐标变化</h2><div class="plan"><img id="comparison" alt="原本位与新本位坐标叠加"></div><pre id="changes"></pre></section>
<section><h2>最不利15mm事件 · 原R14独立复算</h2><div class="local"><img src="r14-worst-clearance.svg" alt="原柜门与人员的15mm局部解析距离图"></div><pre id="clearance"></pre><p>采用原解析四分之一圆盘加保守厚度方形模型，整数平方根给出0.001mm有界证明；不是抽样绘图测距。在该最不利事件中15mm下界恰好等于该条件模型距离，不能改称50mm或实际可用净距。</p></section>
<section><h2>历史对照和剩余真实输入</h2><pre id="history"></pre><ul id="missing"></ul><p class="bad">ACTUAL_CALIBRATION=INPUT_REQUIRED · ENGINEERING_APPROVAL=NOT_EVALUATED · FACTORY_APPLICABILITY=NOT_EVALUATED</p></section></main>
<script>const data=__DATA__,$=x=>document.querySelector(x),esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let mode='plan',zoom=false;for(const r of data.reports){$('#candidate').add(new Option(r.id,r.id));const tr=document.createElement('tr');tr.innerHTML='<td>'+esc(r.id)+'<br>'+esc(JSON.stringify(r.organization))+'</td><td>'+r.home_count+'/53</td><td>'+esc(JSON.stringify(r.completed_users))+'</td><td>'+r.profiles.map(p=>esc(p.hinges)+': '+esc(p.combined.status)+'; 开柜'+p.checked_open_events+'/212').join('<br>')+'</td><td>'+r.profiles.map(p=>(p.combined.minimum_declared_margin_lower_bound_mm===null?'未评估':esc(p.combined.minimum_declared_margin_lower_bound_mm)+'mm')+'; 目标满足='+p.combined.margin_target_met).join('<br>')+'</td><td>'+esc(JSON.stringify(r.static_conflicts.length?r.static_conflicts:r.blockers))+'</td>';$('#rows').append(tr)}$('#candidate').value=data.selected_candidate_id||data.reports[0].id;function show(){const r=data.reports.find(r=>r.id===$('#candidate').value);$('#plan').src=r.id+'-'+mode+'.svg';$('#plan').style.width=zoom?'3600px':'100%';$('#comparison').src=r.id+'-difference.svg';$('#detail').textContent=JSON.stringify(r,null,2);$('#changes').textContent=JSON.stringify(r.coordinate_diff,null,2)}$('#candidate').onchange=show;$('#normal').onclick=()=>{mode='plan';show()};$('#doors').onclick=()=>{mode='doors';show()};$('#zoom').onclick=()=>{zoom=!zoom;show()};$('#photo').textContent=JSON.stringify(data.photo_source_supplement,null,2);$('#clearance').textContent=JSON.stringify(data.clearance_traces[0],null,2);$('#history').textContent=JSON.stringify(data.historical_r14_summary,null,2);for(const s of data.missing_inputs){const li=document.createElement('li');li.textContent=s;$('#missing').append(li)}show();</script></html>"""
