# ruff: noqa: E501 -- persisted engineering evidence viewer, no formulas in UI
"""R8 scale drawing and local batch/door/waiting evidence viewer."""

import base64
import gzip
import html
import json
from typing import Any


def initial_proof(case: dict[str, Any], shift: int) -> dict[str, Any]:
    s = case["shifts"][shift - 1]
    event = next((e for e in s["events"] if e["operation"] == "PARALLEL_STANDING_CHANGE"), None)
    if event:
        return dict(event["proof"])
    g = case["geometry"]
    ref = g["waiting_snapshots"][str(shift)]
    conflicts = list(g["waiting_evaluation"]["conflicts"])
    for d in g["schedule_diagnostics"]:
        if d["shift"] == shift and d["rejected_groups"]:
            conflicts += d["rejected_groups"][0]["conflicts"]
    return dict(
        people_before=ref["people"],
        conflicts=conflicts,
        scope="TEMPLATE_ONLY_NO_COMPLETE_FLOW_GENERATED",
    )


def plan_svg(case: dict[str, Any], shift: int = 1, detail: bool = False) -> str:
    g = case["geometry"]
    proof = initial_proof(case, shift)
    view = "0 -3300 11000 3700" if detail else "-600 -4100 27931 5100"
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}">',
        '<rect x="-600" y="-4100" width="27931" height="5100" fill="white"/>',
    ]

    def rect(box: list[int], fill: str, title: str, stroke: str = "#8d9da7") -> None:
        x, y, r, t = box
        out.append(
            f'<rect x="{x}" y="{-t}" width="{r - x}" height="{t - y}" fill="{fill}" stroke="{stroke}" stroke-width="14"><title>{html.escape(title)}</title></rect>'
        )

    rect(g["room"]["local_bounds_mm"], "#f6f8fa", "原H5矩形", "#283f50")
    for b in g["waiting_snapshots"][str(shift)]["aisles"]:
        rect(b, "#dcefe9", "假设1200mm净通道")
    for u in g["inventory"]["cabinet_units"]:
        rect(u["bounds_mm"], "#7997af", u["id"])
    for c in g["inventory"]["vertical_columns"]:
        rect(c["bounds_mm"], "none", c["id"], "#36566e")
        x, y, r, t = c["bounds_mm"]
        label = c["id"].replace("-C", "·")
        out.append(
            f'<text x="{(x + r) // 2}" y="{-y - 140}" text-anchor="middle" font-size="100" fill="white">{html.escape(label)}</text>'
        )
    for p in proof.get("people_before", []):
        rect(p["bounds_mm"], "#b5c1c8", p["id"])
    for p in proof.get("activity_volumes", []):
        rect(p["bounds_mm"], "#dfb56b99", p["id"] + "活动范围", "#b16c1f")
    for c in proof.get("conflicts", []):
        b = c.get("bounds_mm")
        if "volume_mm" in c:
            v = c["volume_mm"]
            b = [v[0], v[1], v[3], v[4]]
        if b:
            rect(b, "none", c["code"], "#c83436")
    for q in g["room"]["portals"]:
        a, b = q["segment_mm"]
        out.append(
            f'<line x1="{a[0]}" y1="{-a[1]}" x2="{b[0]}" y2="{-b[1]}" stroke="#078371" stroke-width="65"/>'
        )
    out.extend(
        [
            '<text x="13165" y="-3650" text-anchor="middle" font-size="215">H5 26331 × 3250mm · 本人柜前站立 · 初始53人 · 22列110格</text>',
            '<text x="25500" y="-2700" font-size="160">东入口1500</text>',
            '<text x="13165" y="420" text-anchor="middle" font-size="175">南侧包装Portal 1500mm</text>',
            '<text x="0" y="850" font-size="170">位置工艺已确认；柜型、活动范围、并发、时间、洁污 INPUT_REQUIRED · 非施工图</text>',
            "</svg>",
        ]
    )
    return "".join(out)


def page(cases: dict[str, Any]) -> str:
    packed = base64.b64encode(
        gzip.compress(
            json.dumps(cases, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0
        )
    ).decode()
    return TEMPLATE.replace("__DATA__", packed)


TEMPLATE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>H5 柜前错峰更衣 · R11 R8</title>
<style>:root{font:14px system-ui,"PingFang SC",sans-serif;color:#263b49;background:#edf1f3}body{margin:0}header{background:#203848;color:white;padding:22px 28px}h1{font-size:25px;margin:0}header p{color:#c6d5df}main{max-width:1600px;padding:18px;margin:auto}section{padding:16px;background:white;border:1px solid #d2dce2;border-radius:5px;margin-bottom:15px}h2{font-size:17px;margin-top:0}.notice{padding:12px;background:#fff1d7;line-height:1.8}.controls{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0;align-items:end}label{display:grid;gap:5px}select,button{max-width:100%;padding:8px;border:1px solid #a7bbc7;border-radius:4px;background:white}#case{width:510px}.cards{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.card{background:#edf4f5;padding:12px}.card b{display:block;font-size:22px;margin-bottom:5px}.small{color:#536d7d;line-height:1.7}.bad{color:#a8412b}.split{display:grid;grid-template-columns:1.3fr 1fr;gap:15px}.drawing{overflow:auto;border:1px solid #cddbe3}.drawing svg{display:block;width:100%;min-width:1100px}.scroll{max-height:350px;overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:8px;border-bottom:1px solid #d8e1e6;text-align:left;vertical-align:top}th{background:#edf2f4;position:sticky;top:0}tr[data-i]{cursor:pointer}tr[data-i]:hover,tr.selected{background:#fff1d7}pre{white-space:pre-wrap;word-break:break-word;max-height:320px;overflow:auto;font-size:12px}a{color:#08796b}@media(max-width:850px){.split{grid-template-columns:1fr}.cards{grid-template-columns:repeat(2,1fr)}main{padding:10px}}</style>
<header><h1>H5 · 本人柜前站立更衣 / 间隔柜列错峰</h1><p>R11 R8｜两班各53人 · 22列110格 · 原矩形与两处1500mm Portal</p></header><main>
<section><div class="notice"><b>OWNER_CONFIRMED：</b>本人柜前直接站立更衣，无坐凳、无独立更衣区。R7分散更衣仅留作历史对照。<br><b>实际功能 INPUT_REQUIRED：</b>柜型、人体活动范围、柜间距、并发、门扇、取放顺序、时间和洁污尚待批准。以下是完整条件流程，不是现场吞吐或工程合格结论。</div><div class="controls"><label>条件方案<select id="case"></select></label><label>班次<select id="shift"><option value="1">第1班 · 53人</option><option value="2">第2班 · 53人</option></select></label></div><div class="cards" id="cards"></div><p id="result" class="bad"></p></section>
<section><h2>柜前操作区域、实际分组与等候人员</h2><div class="controls"><label>批次<select id="batch"></select></label><label>步骤<select id="step"></select></label><button id="prev">上一步</button><button id="next">下一步</button><button id="overview">全景</button><button id="detail">柜区放大</button><button id="openDoor">开门更衣负面对照</button></div><p class="small">蓝：实际柜组/列；黄：同时更衣范围；灰：当时实际在室者；绿：1200mm假设净通道及原Portal；红：移动扫掠或冲突。柜区放大只裁切同一几何。</p><div id="plan" class="drawing"></div><p id="caption" class="small"></p><pre id="group"></pre></section>
<div class="split"><section><h2>完整流程时间线</h2><p class="small">全53人先入室。组内开柜/取衣/关柜/更衣/再开柜存放/关柜并行；人员移动串行，其他在室者始终作为碰撞对象。站立更衣阶段按关柜假设校核，工艺顺序仍须审阅。</p><div class="scroll"><table><thead><tr><th>序号 / 批次</th><th>人员与动作</th><th>条件秒数</th><th>状态</th></tr></thead><tbody id="timeline"></tbody></table></div></section><section><h2>当前动作证据 / 冲突</h2><pre id="proof"></pre><h2>共同时间与资源瓶颈</h2><pre id="timing"></pre></section></div>
<section><h2>个人路线、操作与串行等待</h2><p class="small">等待=本人自进入Portal至离开Portal的在室时段−本人实际行走−本人操作。组内操作共享同一时间窗口；个人等待之和不是班次墙钟时间。外部排队未验证。</p><div class="scroll"><table><thead><tr><th>人员</th><th>行走mm / 秒</th><th>本人操作秒</th><th>在室秒</th><th>串行等待秒</th><th>完成</th></tr></thead><tbody id="people"></tbody></table></div></section>
<section><h2>2 / 3 / 4 / 5人及空间敏感性</h2><div class="scroll"><table><thead><tr><th>条件方案</th><th>本位 / 53</th><th>完成各班</th><th>实际峰值并发</th><th>条件分钟各班</th><th>首次阻塞</th></tr></thead><tbody id="compare"></tbody></table></div><p class="small">只表示确定性策略实际找到的分组，不是最优并发或最短时间证明。更大活动包络有时改变分组顺序和尾组数量，不能据此认定更大包络效率更高。等待本位不足是当前模板失败，不证明其他H5组织全部不可行。</p></section>
<section><h2>Owner来源与剩余输入</h2><pre id="binding"></pre><p>实际柜型与五层取物能力、人体穿脱/转身/弯腰范围、间隔柜列及避让规范、柜门和房门开向、完成面及净空、两次开柜取放顺序、动作时间/允许班次窗口、洁污及清洁维护流程仍需审阅。全过程保持INPUT_REQUIRED。</p><p><a href="cabinet-front-report.md">完整报告</a> · <a href="cabinet-front-results.json.gz">原始完整流程JSON</a> · <a href="comparison.json">全部方案对照</a> · <a href="project-binding.json">项目事实Scope</a> · <a href="source-manifest.json">来源Hash</a></p></section></main>
<script>
const $=id=>document.getElementById(id),esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');let cases,active,flow,events=[];
const labels={ENTER_AND_REACH_WAITING_POSITION:'进入并到实际本位',TO_PERSONAL_LOCKER:'到本人柜前',OPEN_FOR_RETRIEVE:'开柜取衣',RETRIEVE_CLOTHES:'取衣',CLOSE_AFTER_RETRIEVE:'关柜',PARALLEL_STANDING_CHANGE:'柜前并行更衣',OPEN_FOR_STORE:'再次开柜',STORE_CLOTHES:'存放衣物',CLOSE_AFTER_STORE:'关柜后准备离开',TO_PACKAGING_PORTAL:'到包装Portal',EXIT_PORTAL:'完整服务后离室'};
function box(b,c,t,stroke='#8d9da7'){return `<rect x="${b[0]}" y="${-b[3]}" width="${b[2]-b[0]}" height="${b[3]-b[1]}" fill="${c}" stroke="${stroke}" stroke-width="14"><title>${esc(t)}</title></rect>`}
function draw(p){let g=active.geometry,shift=$('shift').value,ref=g.waiting_snapshots[shift];let v='<svg xmlns="http://www.w3.org/2000/svg" viewBox="-600 -4100 27931 5100"><rect x="-600" y="-4100" width="27931" height="5100" fill="white"/>'+box(g.room.local_bounds_mm,'#f6f8fa','原H5','#283f50');ref.aisles.forEach(b=>v+=box(b,'#dcefe9','假设1200mm净通道'));g.inventory.cabinet_units.forEach(u=>v+=box(u.bounds_mm,'#7997af',u.id));g.inventory.vertical_columns.forEach(c=>{let [x,y,r,t]=c.bounds_mm;v+=box(c.bounds_mm,'none',c.id,'#36566e')+`<text x="${(x+r)/2}" y="${-y-140}" text-anchor="middle" font-size="100" fill="white">${esc(c.id.replace('-C','·'))}</text>`});(p.people_before||ref.people).forEach(o=>v+=box(o.bounds_mm,'#b5c1c8',o.id));(p.activity_volumes||[]).forEach(o=>v+=box(o.bounds_mm,'#dfb56b99',o.id+'活动范围','#b16c1f'));(p.swept_volumes_mm||[]).forEach(b=>v+=box([b[0],b[1],b[3],b[4]],'#cc444433','实际通行扫掠'));(p.doors||[]).forEach(d=>{if(d.kind!=='NO_PLAN_INTRUSION')v+=`<polygon points="${[d.hinge_mm,...d.arc_mm].map(q=>q[0]+','+(-q[1])).join(' ')}" fill="#e58d3c88"><title>${esc(d.id)} z=${d.z_interval_mm}mm</title></polygon>`});(p.conflicts||[]).forEach(c=>{let b=c.bounds_mm;if(c.volume_mm){let z=c.volume_mm;b=[z[0],z[1],z[3],z[4]]}if(b)v+=box(b,'none',c.code,'#c83436')});if(p.points_mm)v+=`<polyline points="${p.points_mm.map(q=>q[0]+','+(-q[1])).join(' ')}" fill="none" stroke="#c83436" stroke-width="28"/>`;g.room.portals.forEach(q=>{let [a,b]=q.segment_mm;v+=`<line x1="${a[0]}" y1="${-a[1]}" x2="${b[0]}" y2="${-b[1]}" stroke="#078371" stroke-width="65"/>`});v+='<text x="13165" y="-3650" text-anchor="middle" font-size="215">H5 26331 × 3250mm · 本人柜前站立 · 初始53人 · 22列110格</text><text x="25500" y="-2700" font-size="160">东入口1500</text><text x="13165" y="420" text-anchor="middle" font-size="175">南侧包装Portal1500mm</text><text x="0" y="850" font-size="170">位置工艺已确认；柜型、活动、并发、时间及洁污 INPUT_REQUIRED</text></svg>';$('plan').innerHTML=v}
function fallback(){let g=active.geometry,shift=+$('shift').value;let cs=[...g.waiting_evaluation.conflicts];g.schedule_diagnostics.filter(d=>d.shift===shift).forEach(d=>{if(d.rejected_groups.length)cs.push(...d.rejected_groups[0].conflicts)});return {people_before:g.waiting_snapshots[String(shift)].people,conflicts:cs,scope:'模板检查，完整流程未启动'}}
function show(){let e=events[+$('step').value],p=e?.proof||fallback();draw(p);let compact={...p};delete compact.people_before;$('proof').textContent=JSON.stringify(compact,null,2);$('caption').textContent=e?`${e.batch||'进入'} · ${labels[e.operation]} · 在室${e.inside_people} / 已离室${e.departed_people} / 尚未进入${e.not_entered_people} · ${p.status}`:'前置模板/分组未通过，未生成后续流程。';let group=active.geometry.snapshots.find(s=>s.id===e?.batch);$('group').textContent=JSON.stringify(group?.front_group_spaces||active.geometry.metrics,null,2);document.querySelectorAll('tr[data-i]').forEach(r=>r.classList.toggle('selected',r.dataset.i===$('step').value))}
function load(){let b=$('batch').value;events=flow.events.filter(e=>!b||e.batch===b);$('step').innerHTML=events.map((e,i)=>`<option value="${i}">${i+1} · ${e.batch||'进入'} · ${labels[e.operation]}</option>`).join('');$('timeline').innerHTML=events.map((e,i)=>`<tr data-i="${i}"><td>${i+1} / ${esc(e.batch||'进入')}</td><td>${labels[e.operation]}<br>${esc(e.active_people.join(', '))}</td><td>${e.start_seconds?.toFixed(2)??'未定'} → ${e.end_seconds?.toFixed(2)??'未完成'}</td><td>${esc(e.proof.status)}</td></tr>`).join('');document.querySelectorAll('tr[data-i]').forEach(r=>r.onclick=()=>{$('step').value=r.dataset.i;show()});$('step').selectedIndex=Math.max(0,events.findIndex(e=>e.operation==='PARALLEL_STANDING_CHANGE'));show()}
function refresh(){active=cases[$('case').value];flow=active.shifts[+$('shift').value-1];$('cards').innerHTML=[['本班设计人数',53],['完成服务离室',flow.completed_users],['请求 / 实际峰值',flow.requested_concurrency+' / '+flow.actual_peak_concurrency],['完整条件分钟',flow.full_shift_minutes?.toFixed(2)??'未建立'],['实际功能','INPUT_REQUIRED']].map(([l,v])=>`<div class="card"><b>${esc(v)}</b>${l}</div>`).join('');$('result').textContent=`${flow.status} · 实际批次${flow.completed_batches.length}/${flow.expected_batches} · 阻塞 ${flow.blocker?.operation||'无'}。不代表已批准吞吐能力。`;$('batch').innerHTML='<option value="">全部步骤</option>'+active.geometry.snapshots.filter(s=>s.shift===+$('shift').value).map(s=>`<option>${s.id}</option>`).join('');$('timing').textContent=JSON.stringify({hypothetical:active.timing,walk_seconds:flow.wall_walking_seconds,parallel_action_wall_seconds:flow.wall_parallel_action_seconds,max_completed_wait_seconds:flow.max_completed_person_waiting_seconds,phase_seconds:flow.duration_by_operation_seconds,concurrency_histogram:flow.concurrency_histogram,total_route_m:flow.total_route_m,space:active.geometry.metrics},null,2);$('people').innerHTML=Object.entries(flow.personnel_time_and_route).map(([k,p])=>`<tr><td>${k}</td><td>${p.route_mm} / ${p.walking_seconds?.toFixed(2)??'未定'}</td><td>${p.action_seconds??'未定'}</td><td>${p.residence_seconds?.toFixed(2)??'未完成'}</td><td>${p.serial_waiting_seconds?.toFixed(2)??'未完成'}</td><td>${p.completed}</td></tr>`).join('');$('binding').textContent=JSON.stringify(active.binding,null,2);load()}
(async()=>{let bytes=Uint8Array.from(atob('__DATA__'),c=>c.charCodeAt(0));cases=JSON.parse(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text());$('case').innerHTML=Object.keys(cases).map(k=>`<option>${esc(k)}</option>`).join('');$('case').selectedIndex=Math.min(6,Object.keys(cases).length-1);$('compare').innerHTML=Object.entries(cases).map(([k,c])=>`<tr><td>${esc(k)}</td><td>${c.geometry.metrics.home_count}/53</td><td>${c.shifts.map(s=>s.completed_users+'/53').join(' / ')}</td><td>${c.shifts.map(s=>s.actual_peak_concurrency).join(' / ')}</td><td>${c.shifts.map(s=>s.full_shift_minutes?.toFixed(2)??'未建立').join(' / ')}</td><td>${esc(c.shifts[0].blocker?.operation||'无')}</td></tr>`).join('');$('case').onchange=refresh;$('shift').onchange=refresh;$('batch').onchange=load;$('step').onchange=show;$('prev').onclick=()=>{$('step').selectedIndex=Math.max(0,$('step').selectedIndex-1);show()};$('next').onclick=()=>{$('step').selectedIndex=Math.min(events.length-1,$('step').selectedIndex+1);show()};$('detail').onclick=()=>$('plan').querySelector('svg')?.setAttribute('viewBox','0 -3300 11000 3700');$('overview').onclick=()=>$('plan').querySelector('svg')?.setAttribute('viewBox','-600 -4100 27931 5100');$('openDoor').onclick=()=>{let x=active.open_door_changing_sensitivity.find(x=>x.shift===+$('shift').value);if(x){draw(x.proof);$('caption').textContent='开门更衣独立负面对照，不是完整流程通过；'+x.batch;let p={...x.proof};delete p.people_before;$('proof').textContent=JSON.stringify(p,null,2)}};refresh()})().catch(e=>{$('result').textContent='加载失败：'+e.message});
</script></html>"""
