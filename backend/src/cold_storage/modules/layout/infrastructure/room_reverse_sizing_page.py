# ruff: noqa: E501 -- standalone review presentation, no engineering calculations
"""Render persisted preview geometry, selected designs and finite input controls."""

import base64
import gzip
import html
import json
from typing import Any


def plot_record(case: dict[str, Any]) -> dict[str, Any]:
    g = case["geometry"]
    flow = next((s for s in case["shifts"] if s["shift"] == 1), None)
    event = (
        next((e for e in flow["events"] if e["operation"] == "PARALLEL_STANDING_CHANGE"), None)
        if flow
        else None
    )
    return dict(
        summary=case["summary"],
        conditions=g["conditions"],
        room=g["room"]["local_bounds_mm"],
        original_room=[0, 0, 26331, 3250],
        clear=g["model"]["clear"],
        units=[
            dict(id=u["id"], bounds_mm=u["bounds_mm"], shift=u["shift"])
            for u in g["inventory"]["cabinet_units"]
        ],
        homes=g["model"]["homes"],
        aisles=g["waiting_snapshots"]["1"]["aisles"],
        portals=g["room"]["portals"],
        mapping=g["room"]["boundary_mapping"],
        activity=(event["proof"]["activity_volumes"] if event else []),
        margins=case["margins"],
        rejected_probes=g["rejected_home_probes"][:3],
        column_count=22,
        compartment_count=110,
    )


def plan_svg(plot: dict[str, Any], *, detail: bool = False) -> str:
    length, width = plot["room"][2:]
    view = f"-700 {-width - 1200} {min(length + 2300, 14500) if detail else length + 2300} {width + 2900}"
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}"><rect x="-700" y="{-width - 1200}" width="{length + 2300}" height="{width + 2900}" fill="white"/>'
    ]

    def text(x: int, y: int, label: str, size: int = 160, anchor: str = "start") -> None:
        out.append(
            f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="#284353">{html.escape(label)}</text>'
        )

    def box(
        b: list[int], color: str, title: str, stroke: str = "#8195a0", dash: bool = False
    ) -> None:
        x, y, r, t = b
        out.append(
            f'<rect x="{x}" y="{-t}" width="{r - x}" height="{t - y}" fill="{color}" stroke="{stroke}" stroke-width="13"'
            + (' stroke-dasharray="60 40"' if dash else "")
            + f"><title>{html.escape(title)}</title></rect>"
        )

    box(plot["room"], "#f5f8fa", "当前独立假设房间边界", "#223f53")
    for a in plot["aisles"]:
        box(a, "#d9ece2", "实际保留净通道")
    if plot["room"] != plot["original_room"]:
        box(plot["original_room"], "none", "原H5边界，仅作尺寸对照", "#c38546", True)
    for u in plot["units"]:
        box(u["bounds_mm"], "#7296b2" if u["shift"] == 1 else "#566f92", u["id"])
    for i, h in enumerate(plot["homes"], 1):
        b = h["bounds_mm"]
        box(b, "#83b7af" if h["yaw_degrees"] == 90 else "#b7c8d6", f"本位{i:02} {h['region']}")
        text((b[0] + b[2]) // 2, -(b[1] + b[3]) // 2 + 45, f"{i:02}", 130, "middle")
    for a in plot["activity"]:
        box(
            a["bounds_mm"], "#efc47577", "完整流程中实际验证的柜前活动（另一个使用时刻）", "#b77b28"
        )
    worst = plot["summary"]["limiting_margin"]
    if worst and worst["bounds_mm"]:
        box(worst["bounds_mm"], "none", worst["location"], "#c34e3c")
    for p in plot["portals"]:
        a, b = p["segment_mm"]
        out.append(
            f'<line x1="{a[0]}" y1="{-a[1]}" x2="{b[0]}" y2="{-b[1]}" stroke="#087c6a" stroke-width="65"/>'
        )
    text(
        length // 2,
        -width - 650,
        f"{length} × {width}mm · {plot['summary']['area_m2']}m²",
        220,
        "middle",
    )
    text(
        0,
        -width - 1000,
        f"22列110格 · 本位{len(plot['homes'])}/53 · 四阶段状态独立 · INPUT_REQUIRED",
        165,
    )
    text(
        0, 350, "两处1500mm Portal：北/东扩展映射见明细；外部Access、Site及Footprint待重新验证", 160
    )
    text(
        0,
        700,
        "蓝/青＝初始等候本位；金色＝已校核柜前活动的另一时刻，不是额外人员；红＝最不利余量位置",
        150,
    )
    text(
        0,
        1050,
        f"最小已定义空间余量 {plot['summary']['minimum_margin_mm']}mm；北侧本位至完成面 {plot['summary']['north_wall_margin_mm']}mm",
        160,
    )
    text(
        0,
        1450,
        "HYPOTHETICAL_NOT_APPROVED · 仅功能房间评审；不修改原H5、P1、Stage B或实际工程状态",
        150,
    )
    return "".join(out) + "</svg>"


def comparison_svg(selected: dict[str, Any]) -> str:
    # Common scale for comparison, rather than separately scaling each plan to fill.
    stride = max(p["room"][3] for p in selected.values()) + 3500 if selected else 8000
    canvas_width = max(p["room"][2] for p in selected.values()) + 2300 if selected else 32500
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-700 -1200 {canvas_width} {stride * len(selected) + 1000}"><rect x="-700" y="-1200" width="{canvas_width}" height="{stride * len(selected) + 1000}" fill="white"/>'
    ]
    for i, (label, plot) in enumerate(selected.items()):
        offset = i * stride + 500
        svg = plan_svg(plot)
        content = svg[svg.index(">") + 1 : svg.rfind("</svg>")]
        out.append(f'<g transform="translate(0,{offset + plot["room"][3] + 950})">{content}</g>')
        out.append(
            f'<text x="0" y="{offset - 600}" font-size="280" fill="#254354">{html.escape(label)} · {plot["summary"]["area_m2"]}m² · 最小余量{plot["summary"]["minimum_margin_mm"]}mm</text>'
        )

    return "".join(out) + "</svg>"


def page(data: dict[str, Any], plots: dict[str, Any]) -> str:
    encoded = base64.b64encode(
        gzip.compress(
            json.dumps(
                dict(data=data, plots=plots), ensure_ascii=False, separators=(",", ":")
            ).encode(),
            mtime=0,
        )
    ).decode()
    return TEMPLATE.replace("__DATA__", encoded)


TEMPLATE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>H5功能房间尺寸反推 · R11 R10</title>
<style>body{margin:0;color:#263d4c;background:#eef2f4;font:14px system-ui,"PingFang SC",sans-serif}header{background:#213d50;color:white;padding:24px}h1{margin:0;font-size:26px}main{max-width:1720px;margin:auto;padding:18px}section{background:white;border:1px solid #cdd9e1;margin-bottom:16px;padding:18px}h2{font-size:18px;margin-top:0}.notice{padding:13px;background:#fff1d6;line-height:1.8}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.controls{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:15px 0}label{display:grid;gap:6px}input,select,button{padding:8px;border:1px solid #a5bac7;background:white;color:#263d4c}input{width:100px}#scheme{max-width:100%;width:660px}.drawing{overflow:auto;border:1px solid #cdd9df}.drawing svg{width:100%;min-width:1600px;display:block}pre{white-space:pre-wrap;word-break:break-word;font-size:12px;background:#f4f7f9;padding:12px;max-height:420px;overflow:auto}.scroll{max-height:500px;overflow:auto}table{border-collapse:collapse;width:100%}th,td{padding:9px;border-bottom:1px solid #d7e0e6;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#eaf0f3}tr[data-id]{cursor:pointer}tr[data-id]:hover{background:#fff1d6}.small{color:#526e7f;line-height:1.8}.bad{color:#a5492f}.stages{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.stages p{background:#edf4f4;padding:12px}#request{width:96%;min-height:100px}a{color:#087b6a}@media(max-width:850px){.grid{grid-template-columns:1fr}.stages{grid-template-columns:1fr 1fr}main{padding:8px}}</style>
<header><h1>H5 · 从功能使用条件反推房间尺寸</h1><p>R11 R10｜两班各53人 · 22列110格 · 本人柜前站立 · 无坐凳/独立更衣区</p></header><main>
<section><div class="notice"><b>Owner确认的是设计需求：</b>53人初始同时在室、两班独立格口、五层五门柜和柜前站立工艺。默认示例中的柜体400×500mm、人体450×650mm、活动600×900mm、1200mm通道、完成面20mm等仍是未批准假设。<br><b>不要把最小面积作为推荐：</b>A只是测试集合内最小已验证面积；B提高已定义局部余量；C比较达到假设50mm余量的最少边界调整。50/100/150mm不是规范限值。所有实际功能与工程批准仍为INPUT_REQUIRED。</div></section>
<section><h2>参数输入与预览请求</h2><p class="small">本地文件可切换已计算的有限条件。修改参数不会由浏览器重新计算工程公式；可导出JSON，交给Python预览接口。使用随附本地服务时可直接提交试算，结果仍不写入Authority。</p><div class="controls" id="params"></div><div class="controls"><label>固定长度mm<input id="length" type="number" value="26331"></label><label>宽度点（逗号分隔）<input id="widths" style="width:340px" value="3250,3300,3350,3400,3440,3460,3500,3600"></label><label>假设余量mm<select id="target"><option>0</option><option selected>50</option><option>100</option><option>150</option></select></label><button id="export">导出条件请求</button><button id="calculate">本地Python接口试算</button></div><textarea id="request" spellcheck="false"></textarea><p id="api" class="small"></p></section>
<section><h2>A / B / C 设计目标</h2><table><thead><tr><th>目标</th><th>长×宽mm</th><th>面积 / 增量㎡</th><th>最小余量 / 北侧</th><th>两班完整流程</th></tr></thead><tbody id="designs"></tbody></table><p class="small">面积只计P01/P02对应的一个物理房间。A触及本次搜索下边界，不能作为全局最小面积或P1所需面积。反事实扩展均保留西、南边界；加长时东入口映射到新东边界，外部连接未重新验收。</p></section>
<section><h2>实际比例平面与最不利局部位置</h2><div class="controls"><label>已计算组合<select id="scheme"></select></label><button id="overview">全景</button><button id="detail">柜区放大</button></div><div id="stages" class="stages"></div><div id="plan" class="drawing"></div><p class="small">金色活动是完整流程中校核过的另一个使用时刻；灰/青为初始本位，不是增加人员。虚线是原H5边界，仅作尺寸对照。图纸为概念评审，不是施工图。</p></section>
<div class="grid"><section><h2>真实尺寸链与余量</h2><table><thead><tr><th>截面组成</th><th>mm</th></tr></thead><tbody id="chainTable"></tbody></table><div class="scroll"><table><thead><tr><th>余量项</th><th>实测 / 假设基准 / 额外mm</th><th>最不利位置</th></tr></thead><tbody id="marginTable"></tbody></table></div><details><summary>本平面条件与原始计算结果</summary><pre id="margins"></pre></details></section><section><h2>冲突、Portal映射与工程边界</h2><pre id="conflicts"></pre></section></div>
<section><h2>模式A/B宽度、长度与空间余量敏感性</h2><div class="controls"><label>模式<select id="mode"><option value="">全部</option><option>A_FIXED_LENGTH</option><option>B_JOINT_DIMENSIONS</option></select></label><label>仅完整条件流程通过<input type="checkbox" id="valid"></label></div><div class="scroll"><table><thead><tr><th>模式/组织</th><th>长×宽mm</th><th>假设余量</th><th>本位</th><th>完整流程</th><th>实测最小余量</th><th>新增面积㎡</th></tr></thead><tbody id="rows"></tbody></table></div></section>
<section><h2>历史R9参照与真实缺失输入</h2><p>R9三方案、原10mm北侧余量、30mm完成面失败及Native越界异常原件只读保留。R10计算不调用Native；继承的自动快速CI包含原有合成Native测试，应单独识别，不能因此宣称任务总Native次数为零。</p><pre id="binding"></pre><p><a href="reverse-sizing-report.md">工程报告</a> · <a href="sizing-preview.json">结构化预览接口结果</a> · <a href="design-comparison.svg">统一比例方案对照</a> · <a href="evaluation-grid.jsonl.gz">全部原始几何与流程</a> · <a href="r9-reference-and-sensitivity.json">R9与完成面/安装敏感性</a> · <a href="source-manifest.json">来源Hash</a></p></section></main>
<script>
const $=x=>document.getElementById(x),esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');let data,plots;
const labels={column_width_mm:'柜列宽mm',column_depth_mm:'柜深mm',cabinet_height_mm:'柜总高mm',transport_width_mm:'运输人体宽mm',transport_depth_mm:'运输人体深mm',activity_width_mm:'更衣活动宽mm',activity_depth_mm:'更衣活动深mm',waiting_gap_mm:'本位净距mm',aisle_required_mm:'净通道要求mm',finish_mm:'完成面mm',installation_gap_mm:'安装间隙mm'};
function rect(b,c,t){return `<rect x="${b[0]}" y="${-b[3]}" width="${b[2]-b[0]}" height="${b[3]-b[1]}" fill="${c}" stroke="#8195a0" stroke-width="12"><title>${esc(t)}</title></rect>`}
function draw(p){let [,,L,W]=p.room,s=p.summary,v=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="-700 ${-W-1000} ${L+2200} ${W+2400}"><rect x="-700" y="${-W-1000}" width="${L+2200}" height="${W+2400}" fill="white"/>`+rect(p.room,'#f5f8fa','当前独立假设房间');p.aisles.forEach(a=>v+=rect(a,'#d9ece2','实际净通道'));if(p.room.join()!==p.original_room.join())v+=`<rect x="0" y="-3250" width="26331" height="3250" fill="none" stroke="#c38546" stroke-width="16" stroke-dasharray="60 40"/>`;p.units.forEach(u=>v+=rect(u.bounds_mm,u.shift===1?'#7296b2':'#566f92',u.id));p.homes.forEach((h,i)=>{v+=rect(h.bounds_mm,h.yaw_degrees===90?'#83b7af':'#b7c8d6','本位'+(i+1));let b=h.bounds_mm;v+=`<text x="${(b[0]+b[2])/2}" y="${-(b[1]+b[3])/2+45}" text-anchor="middle" font-size="130">${i+1}</text>`});p.activity.forEach(a=>v+=rect(a.bounds_mm,'#efc47577','已验证使用时刻的活动范围'));if(s.limiting_margin?.bounds_mm)v+=rect(s.limiting_margin.bounds_mm,'#c4493722','最不利余量');p.portals.forEach(q=>{let [a,b]=q.segment_mm;v+=`<line x1="${a[0]}" y1="${-a[1]}" x2="${b[0]}" y2="${-b[1]}" stroke="#087c6a" stroke-width="65"/>`});v+=`<text x="${L/2}" y="${-W-600}" text-anchor="middle" font-size="220">${L} × ${W}mm · ${esc(s.area_m2)}m² · 最小余量${s.minimum_margin_mm}mm</text><text x="0" y="420" font-size="160">HYPOTHETICAL_NOT_APPROVED · 两班完成${s.completed_users.length?s.completed_users.join('/'):'NOT_EVALUATED'} · ${esc(s.full_flow_status)} · 实际工程INPUT_REQUIRED</text></svg>`;$('plan').innerHTML=v}
function choose(){let id=$('scheme').value,p=plots[id],s=p.summary;draw(p);$('stages').innerHTML=[['截面必要条件',s.section_status],['实际静态布置',s.static_status],['两班完整条件流程',s.full_flow_status],['实际工程批准','INPUT_REQUIRED']].map(x=>`<p><b>${x[0]}</b><br>${esc(x[1])}</p>`).join('');$('margins').textContent=JSON.stringify({conditions_for_this_plan:p.conditions,margins:p.margins},null,2);$('chainTable').innerHTML=p.margins.section_chain_mm.map(r=>`<tr><td>${esc(r.label)}</td><td>${r.mm}</td></tr>`).join('');$('marginTable').innerHTML=Object.values(p.margins.families).map(r=>`<tr><td>${esc(r.family)}</td><td>${r.actual_mm} / ${r.required_mm} / ${r.extra_mm}</td><td>${esc(r.location)}</td></tr>`).join('');$('conflicts').textContent=JSON.stringify({static:s.static_conflicts,flow:s.conditional_flow_conflicts,portal_mapping:s.boundary_mapping},null,2)}
function table(){let rows=data.candidates.filter(r=>(!$('mode').value||r.point.mode===$('mode').value)&&(!$('valid').checked||r.full_flow_verified));$('rows').innerHTML=rows.map(r=>`<tr data-id="${esc(r.id)}"><td>${esc(r.point.mode)}<br>${esc(r.point.profile)}</td><td>${r.point.length_mm}×${r.point.width_mm}</td><td>${r.point.margin_mm}mm</td><td>${r.home_count}/53</td><td>${esc(r.full_flow_status)}</td><td>${r.minimum_margin_mm}mm</td><td>${r.added_area_m2}</td></tr>`).join('');$('rows').querySelectorAll('tr').forEach(tr=>tr.onclick=()=>{$('scheme').value=tr.dataset.id;choose()})}
function request(){let conditions={...data.conditions};Object.keys(labels).forEach(k=>conditions[k]=Number($('p-'+k).value));return {conditions,search:{fixed_length_mm:Number($('length').value),widths_mm:$('widths').value.split(',').map(x=>Number(x.trim())),joint_lengths_mm:[27000,28000,30000],joint_widths_mm:[3250,3500,3600,3750,4050,4350],margin_targets_mm:[Number($('target').value)],derived_width_checkpoints:false,change_review_target_mm:Number($('target').value)}}}
function install(d,p){data=d;plots=p;$('params').innerHTML=Object.entries(labels).map(([k,label])=>`<label>${label}（假设）<input id="p-${k}" type="number" value="${data.conditions[k]}"></label>`).join('');$('scheme').innerHTML=data.candidates.map(r=>`<option value="${esc(r.id)}">${esc(r.id)} · ${esc(r.full_flow_status)}</option>`).join('');let designLabels={A_MIN_VERIFIED_AREA:'A 集合最小面积（不推荐裸余量）',B_LARGER_MARGIN:'B 更大局部余量',C_MIN_BOUNDARY_CHANGE:'C 较少边界改动'};$('designs').innerHTML=Object.entries(designLabels).map(([k,label])=>{let r=data.candidates.find(r=>r.id===data.designs[k]);return r?`<tr><td><button data-design-id="${esc(r.id)}">${label}</button><br><span class="small">${esc(r.point.profile)}</span></td><td>${r.point.length_mm}×${r.point.width_mm}</td><td>${r.area_m2} / +${r.added_area_m2}</td><td>${r.minimum_margin_mm} / ${r.north_wall_margin_mm??'无北侧本位'}</td><td>${r.completed_users.join(' / ')}</td></tr>`:`<tr><td>${label}</td><td colspan="4">范围内无完整已验证见证</td></tr>`}).join('');$('designs').querySelectorAll('button[data-design-id]').forEach(b=>b.onclick=()=>{$('scheme').value=b.dataset.designId;choose()});$('binding').textContent=JSON.stringify({provenance:data.input_provenance,missing:data.binding.missing_inputs,scope:data.scope_limits},null,2);$('scheme').value=data.designs.C_MIN_BOUNDARY_CHANGE||data.candidates[0].id;table();choose();$('request').value=JSON.stringify(request(),null,2)}
(async()=>{let bytes=Uint8Array.from(atob('__DATA__'),x=>x.charCodeAt(0)),v=JSON.parse(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text());install(v.data,v.plots);$('scheme').onchange=choose;$('mode').onchange=table;$('valid').onchange=table;$('detail').onclick=()=>{let p=plots[$('scheme').value];$('plan').querySelector('svg').setAttribute('viewBox',`-700 ${-p.room[3]-1000} 14500 ${p.room[3]+2400}`)};$('overview').onclick=choose;$('export').onclick=()=>{let req=request();$('request').value=JSON.stringify(req,null,2);let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([$('request').value],{type:'application/json'}));a.download='room-sizing-preview-request.json';a.click();URL.revokeObjectURL(a.href)};$('calculate').onclick=async()=>{if(!/^https?:$/.test(location.protocol)){$('api').textContent='本地文件不运行工程计算。请使用随附Python预览服务，或导出JSON后用生成器试算。';return}try{$('api').textContent='Python正在进行有限静态与完整流程校核；不运行Native。';let r=await fetch('/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request())}),v=await r.json();if(!r.ok)throw Error(v.error);install(v.data,v.plots);$('api').textContent='条件预览已完成，实际工程仍为INPUT_REQUIRED。'}catch(e){$('api').textContent='未取得预览：'+e.message}}})().catch(e=>{$('api').textContent='证据加载失败：'+e.message});
</script></html>"""
