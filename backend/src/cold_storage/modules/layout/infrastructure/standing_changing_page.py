# ruff: noqa: E501 -- static local review HTML/SVG, consumes persisted calculations
"""Standing-operation evidence viewer; no engineering calculation or approval UI."""

import base64
import gzip
import html
import json
from typing import Any


def plan_svg(case: dict[str, Any], shift: int = 1) -> str:
    g = case["geometry"]
    s = case["shifts"][shift - 1]
    event = next((e for e in s["events"] if e["operation"] == "PARALLEL_STANDING_CHANGE"), None)
    proof = event["proof"] if event else {}
    snap = next(s for s in g["snapshots"] if s["shift"] == shift)
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-600 -4100 27931 5100">',
        '<rect x="-600" y="-4100" width="27931" height="5100" fill="white"/>',
    ]

    def rect(box: list[int], fill: str, title: str, stroke: str = "#8c9ba3") -> None:
        x, y, r, t = box
        parts.append(
            f'<rect x="{x}" y="{-t}" width="{r - x}" height="{t - y}" fill="{fill}" stroke="{stroke}" stroke-width="15"><title>{html.escape(title)}</title></rect>'
        )

    rect(g["room"]["local_bounds_mm"], "#f7f9fa", "H5 original room", "#213c4c")
    for b in snap["aisles"]:
        rect(b, "#d7eee8", "1200mm hypothetical net passage")
    for u in g["inventory"]["cabinet_units"]:
        rect(u["bounds_mm"], "#7294af", u["id"])
    for p in proof.get("people_before", snap["home_people"]):
        rect(p["bounds_mm"], "#bbc5cb", p["id"])
    for p in proof.get("activity_volumes", []):
        rect(p["bounds_mm"], "#dbb27699", p["id"] + " hypothetical standing activity", "#ad6d22")
    for c in proof.get("conflicts", []):
        b = c.get("bounds_mm")
        if "volume_mm" in c:
            v = c["volume_mm"]
            b = [v[0], v[1], v[3], v[4]]
        if b:
            rect(b, "none", c["code"], "#cc3434")
    for q in g["room"]["portals"]:
        a, b = q["segment_mm"]
        parts.append(
            f'<line x1="{a[0]}" y1="{-a[1]}" x2="{b[0]}" y2="{-b[1]}" stroke="#008b74" stroke-width="70"/>'
        )
    parts.extend(
        [
            '<text x="13165" y="-3650" font-size="220" text-anchor="middle">H5 26331 × 3250 mm · 22列110格 · 0座凳 · 初始53人</text>',
            '<text x="25200" y="-2750" font-size="170">东入口1500</text>',
            '<text x="13165" y="420" font-size="180" text-anchor="middle">南侧包装Portal1500mm</text>',
            '<text x="0" y="850" font-size="175">无坐凳/站立：Owner已确认；人体/活动/柜型/通道：假设；实际功能 INPUT_REQUIRED</text>',
            "</svg>",
        ]
    )
    return "".join(parts)


def page(cases: dict[str, Any]) -> str:
    data = base64.b64encode(
        gzip.compress(
            json.dumps(cases, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0
        )
    ).decode()
    return TEMPLATE.replace("__DATA__", data)


TEMPLATE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>H5 · 无坐凳站立更衣评审</title>
<style>:root{font:14px system-ui,"PingFang SC",sans-serif;color:#253746;background:#edf1f3}body{margin:0}header{background:#203544;color:#fff;padding:24px 28px}h1{margin:0;font-size:25px}header p{color:#c8d6df}main{max-width:1550px;margin:auto;padding:18px}section{background:#fff;border:1px solid #d3dce2;border-radius:5px;padding:16px;margin-bottom:16px}h2{font-size:17px;margin-top:0}.notice{padding:12px;background:#fff1d6;line-height:1.8}.controls{display:flex;gap:14px;flex-wrap:wrap;margin:14px 0;align-items:end}label{display:grid;gap:6px}select,button{padding:8px;border:1px solid #a8b9c4;background:#fff;border-radius:4px;max-width:100%}#case{max-width:600px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.card{background:#edf4f5;padding:12px}.card b{display:block;font-size:22px;margin-bottom:5px}.small{color:#536a79;line-height:1.65}.split{display:grid;grid-template-columns:1.3fr 1fr;gap:16px}.scroll{overflow:auto;max-height:360px}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:8px;border-bottom:1px solid #d7e0e5;text-align:left;vertical-align:top}th{background:#edf2f4;position:sticky;top:0}tr[data-i]{cursor:pointer}tr[data-i]:hover,tr.selected{background:#fff1d8}.drawing{overflow:auto;border:1px solid #d7e0e5}.drawing svg{width:100%;min-width:1100px;display:block}pre{white-space:pre-wrap;word-break:break-word;font-size:12px;max-height:350px;overflow:auto}.bad{color:#ae3f2c}.good{color:#087b6d}a{color:#077c70}@media(max-width:850px){.split{grid-template-columns:1fr}.cards{grid-template-columns:repeat(2,1fr)}main{padding:10px}}</style>
<header><h1>H5 · 无坐凳站立更衣</h1><p>R11 R7｜两班各53人 · 五层22列110格 · 原东入口 / 南包装门 · 真实房间26331×3250mm</p></header><main>
<section><div class="notice"><b>CONFIRMED_PROJECT_BASIS：</b>本项目不设坐凳，人员站立更衣，初始53人在室基准保留。<br><b>INPUT_REQUIRED：</b>柜前或分散更衣、具体人体活动空间、柜型、1200mm净通道、门开向、时间及洁污流程仍未批准。以下为条件模拟，非施工图、非吞吐合格结论。</div>
<div class="controls"><label>条件方案<select id="case"></select></label><label>班次<select id="shift"><option value="1">第1班 · 53人</option><option value="2">第2班 · 53人</option></select></label></div><div class="cards" id="cards"></div><p id="result" class="bad"></p></section>
<section><h2>真实比例平面 · 人员活动与路线</h2><div class="controls"><label>流程步骤<select id="step"></select></label><button id="prev">上一步</button><button id="next">下一步</button><button id="changing">首个站立更衣批次</button></div><p class="small">蓝：柜体；灰：实际在室人员；黄：同时更衣活动包络；绿：净通道及真实Portal；红：移动扫掠或冲突。无坐凳、无座位、无唯一更衣操作区。</p><div class="drawing" id="plan"></div><p id="caption" class="small"></p></section>
<div class="split"><section><h2>完整人员时间线</h2><p class="small">柜前取放衣物及站立更衣按批次并行；通道移动保守串行，其他在室人员均参与碰撞检查。更衣前先关闭柜门。同步批次时间只计算一次，不把并发人数除入步行时间。</p><div class="scroll"><table><thead><tr><th>批次 / 步骤</th><th>人员及操作</th><th>条件秒数</th><th>结果</th></tr></thead><tbody id="timeline"></tbody></table></div></section><section><h2>当前位置与冲突证据</h2><pre id="proof"></pre><h2>条件时间与实际路线</h2><pre id="timing"></pre></section></div>
<section><h2>并发与人体活动尺度对照</h2><div class="scroll"><table><thead><tr><th>方案</th><th>完成服务 / 每班</th><th>条件总秒数 / 每班</th><th>首个阻塞</th></tr></thead><tbody id="compare"></tbody></table></div><p class="small">400×600mm是未批准的运输身体占位。420×700mm也只是较小的活动假设；600×900mm等扩大条件的失败保留。静态身体边界通过不得解释为更衣人体工学通过。</p></section>
<section><h2>Owner来源、适用Scope与缺失输入</h2><pre id="binding"></pre><p>还需真实柜型、五层取物能力、衣物体积与分隔、人体穿脱/转身/弯腰范围、经允许的柜前或分散更衣方式、实际门扇与完成面、洁污和清洁维护流程、经审阅的动作时间及允许班次窗口。外部Access是原封存记录，不代表本轮重新验证外部人员流量。</p><p><a href="standing-operation-report.md">完整工程报告</a> · <a href="standing-operation-results.json.gz">完整原始模拟JSON</a> · <a href="comparison.json">条件指标对照</a> · <a href="project-binding.json">项目输入来源</a> · <a href="source-manifest.json">来源Hash</a></p></section></main>
<script>
let cases,active,events=[];const $=id=>document.getElementById(id),esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const labels={ENTER_AND_REACH_WAITING_POSITION:'东入口进入并到等候位',TO_PERSONAL_LOCKER:'到本人柜位',PARALLEL_LOCKER_USE_AND_CLOSE:'并行取放衣物 / 关闭柜门',TO_DISTRIBUTED_STANDING_POSITION:'到分散站立位',PARALLEL_STANDING_CHANGE:'并行站立更衣',TO_PACKAGING_PORTAL:'到南侧包装门',EXIT_PORTAL:'完成服务后离室'};
function rect(b,color,title,stroke='#899ba7'){return `<rect x="${b[0]}" y="${-b[3]}" width="${b[2]-b[0]}" height="${b[3]-b[1]}" fill="${color}" stroke="${stroke}" stroke-width="15"><title>${esc(title)}</title></rect>`}
function draw(proof){let g=active.geometry,snap=g.snapshots.find(s=>s.shift===+$('shift').value);let v='<svg xmlns="http://www.w3.org/2000/svg" viewBox="-600 -4100 27931 5100"><rect x="-600" y="-4100" width="27931" height="5100" fill="white"/>'+rect(g.room.local_bounds_mm,'#f7f9fa','原H5','#213c4c');snap.aisles.forEach(b=>v+=rect(b,'#d7eee8','假设1200mm净通道'));g.inventory.cabinet_units.forEach(u=>v+=rect(u.bounds_mm,'#7294af',u.id));(proof.people_before||snap.home_people).forEach(p=>v+=rect(p.bounds_mm,'#bbc5cb',p.id));(proof.activity_volumes||[]).forEach(p=>v+=rect(p.bounds_mm,'#dbb27699',p.id+' 未批准活动空间','#ad6d22'));(proof.swept_volumes_mm||[]).forEach(b=>v+=rect([b[0],b[1],b[3],b[4]],'#cf484433','连续身体扫掠'));(proof.doors||[]).forEach(d=>{if(d.kind!=='NO_PLAN_INTRUSION')v+=`<polygon points="${[d.hinge_mm,...d.arc_mm].map(p=>p[0]+','+(-p[1])).join(' ')}" fill="#ed994877"><title>${esc(d.id)} 高度${d.z_interval_mm}mm</title></polygon>`});(proof.conflicts||[]).forEach(c=>{let b=c.bounds_mm;if(c.volume_mm){let z=c.volume_mm;b=[z[0],z[1],z[3],z[4]]}if(b)v+=rect(b,'none',c.code,'#cd3434')});if(proof.points_mm)v+=`<polyline points="${proof.points_mm.map(p=>p[0]+','+(-p[1])).join(' ')}" fill="none" stroke="#c63e32" stroke-width="28"/>`;g.room.portals.forEach(q=>{let [a,b]=q.segment_mm;v+=`<line x1="${a[0]}" y1="${-a[1]}" x2="${b[0]}" y2="${-b[1]}" stroke="#008b74" stroke-width="70"/>`});v+='<text x="13165" y="-3650" font-size="220" text-anchor="middle">H5 26331 × 3250 mm · 22列110格 · 0座凳 · 初始53人</text><text x="25200" y="-2750" font-size="170">东入口1500</text><text x="13165" y="420" font-size="180" text-anchor="middle">南侧包装Portal 1500mm</text><text x="0" y="850" font-size="175">实际功能 INPUT_REQUIRED · 人体、柜型、通道和时间均为条件假设</text></svg>';$('plan').innerHTML=v}
function show(){let e=events[+$('step').value],p=e?.proof||{};draw(p);let compact={...p};delete compact.people_before;$('proof').textContent=JSON.stringify(compact,null,2);$('caption').textContent=e?`${e.batch||'进室'} · ${labels[e.operation]} · ${e.active_people.join(', ')} · 在室${e.inside_people} / 已离室${e.departed_people} / 尚未进入${e.not_entered_people}。${p.status}`:'前置静态校核未通过；没有制造后续人员路径。';document.querySelectorAll('tr[data-i]').forEach(r=>r.classList.toggle('selected',r.dataset.i===$('step').value))}
function refresh(){active=cases[$('case').value];let s=active.shifts[+$('shift').value-1];events=s.events;$('cards').innerHTML=[['设计人数',53],['完成服务并离室',s.completed_users],['完整条件秒数',s.full_shift_seconds?.toFixed(2)??'未建立'],['实际功能','INPUT_REQUIRED']].map(([l,v])=>`<div class="card"><b>${esc(v)}</b>${l}</div>`).join('');$('result').textContent=`${s.status}；初始服务占用${s.initial_service_occupancy}人；完成批次${s.completed_batches.length}/${s.expected_batches}；阻塞：${s.blocker?.operation||'无'}。不是工程批准。`;$('step').innerHTML=events.map((e,i)=>`<option value="${i}">${i+1} · ${esc(e.batch||'进入')} · ${labels[e.operation]}</option>`).join('');$('timeline').innerHTML=events.map((e,i)=>`<tr data-i="${i}"><td>${i+1} / ${esc(e.batch||'进室')}</td><td>${labels[e.operation]}<br>${esc(e.active_people.join(', '))}</td><td>${e.start_seconds?.toFixed(2)??'未定'} → ${e.end_seconds?.toFixed(2)??'未完成'}</td><td>${esc(e.proof.status)}</td></tr>`).join('');document.querySelectorAll('tr[data-i]').forEach(r=>r.onclick=()=>{$('step').value=r.dataset.i;show()});$('binding').textContent=JSON.stringify(active.binding,null,2);$('timing').textContent=JSON.stringify({hypothetical:active.timing,protocol:s.concurrency_model,total_seconds:s.full_shift_seconds,seconds_by_operation:s.duration_by_operation_seconds,route_mm:s.total_route_mm,per_person_route_mm:s.personnel_route_mm,blocker:s.blocker},null,2);$('step').selectedIndex=Math.max(0,events.findIndex(e=>e.operation==='PARALLEL_STANDING_CHANGE'));show()}
(async()=>{const b=Uint8Array.from(atob('__DATA__'),c=>c.charCodeAt(0));cases=JSON.parse(await new Response(new Blob([b]).stream().pipeThrough(new DecompressionStream('gzip'))).text());$('case').innerHTML=Object.keys(cases).map(k=>`<option>${esc(k)}</option>`).join('');$('compare').innerHTML=Object.entries(cases).map(([k,c])=>`<tr><td>${esc(k)}</td><td>${c.shifts.map(s=>s.completed_users+'/53').join(' / ')}</td><td>${c.shifts.map(s=>s.full_shift_seconds?.toFixed(2)??'未建立').join(' / ')}</td><td>${esc(c.shifts[0].blocker?.operation||'无')}</td></tr>`).join('');$('case').onchange=refresh;$('shift').onchange=refresh;$('step').onchange=show;$('prev').onclick=()=>{$('step').selectedIndex=Math.max(0,$('step').selectedIndex-1);show()};$('next').onclick=()=>{$('step').selectedIndex=Math.min(events.length-1,$('step').selectedIndex+1);show()};$('changing').onclick=()=>{$('step').selectedIndex=Math.max(0,events.findIndex(e=>e.operation==='PARALLEL_STANDING_CHANGE'));show()};refresh()})().catch(e=>{$('result').textContent='加载失败：'+e.message});
</script></html>"""
