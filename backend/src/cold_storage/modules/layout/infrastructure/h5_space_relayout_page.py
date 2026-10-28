# ruff: noqa: E501 -- standalone evidence viewer, all engineering results are persisted
"""R9 scale plans and a local viewer; no layout or time calculations in the UI."""

import base64
import gzip
import html
import json
from typing import Any


def space_svg(
    case: dict[str, Any],
    shift: int = 1,
    proof: dict[str, Any] | None = None,
    *,
    detail: bool = False,
) -> str:
    g = case["geometry"]
    ref = g["waiting_snapshots"][str(shift)]
    current = proof or dict(
        people_before=ref["people"], conflicts=g["waiting_evaluation"]["conflicts"]
    )
    if proof is None and g["metrics"]["home_count"] < 53:
        attempted = [
            q for q in g.get("rejected_home_probes", []) if q["reason"] == "OUTSIDE_FINISHED_ROOM"
        ]
        current = dict(
            current,
            conflicts=[
                *current["conflicts"],
                *[
                    dict(code="REJECTED_WAITING_POSITION_NOT_AN_OCCUPANT", bounds_mm=q["bounds_mm"])
                    for q in attempted[:3]
                ],
            ],
        )
    view = "-700 -4350 13500 6050" if detail else "-700 -4350 28500 6050"
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}"><rect x="-700" y="-4350" width="28500" height="6050" fill="white"/>'
    ]

    def text(x: int, y: int, label: str, size: int = 150, anchor: str = "start") -> None:
        out.append(
            f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="#284251">{html.escape(label)}</text>'
        )

    def rect(
        b: list[int], fill: str, label: str, stroke: str = "#7e939f", dash: bool = False
    ) -> None:
        x, y, r, t = b
        out.append(
            f'<rect x="{x}" y="{-t}" width="{r - x}" height="{t - y}" fill="{fill}" stroke="{stroke}" stroke-width="12"'
            + (' stroke-dasharray="45 30"' if dash else "")
            + f"><title>{html.escape(label)}</title></rect>"
        )

    rect(g["room"]["local_bounds_mm"], "#f6f8fa", "历史H5建筑矩形", "#233e50")
    for b in ref["aisles"]:
        rect(b, "#e0eee7", "1200mm假设连续净通道")
    for u in g["inventory"]["cabinet_units"]:
        rect(u["bounds_mm"], "#7897ae" if u["shift"] == 1 else "#586e95", u["id"] + " 多列组合柜体")
    for c in g["inventory"]["vertical_columns"]:
        rect(c["bounds_mm"], "none", c["id"], "#3b586c")
    for i, h in enumerate(g["model"]["homes"], 1):
        rect(h["bounds_mm"], "none", f"本位{i:02}; {h.get('region', 'R8参考')}", "#488b9e", True)
    for person in current.get("people_before", ref["people"]):
        b = person["bounds_mm"]
        rotated = b[2] - b[0] == 650
        rect(
            b,
            "#eab963"
            if person["role"] == "FRONT_OPERATOR"
            else "#88b9b6"
            if rotated
            else "#bbc9d2",
            person["id"] + f" {b[2] - b[0]}×{b[3] - b[1]}mm",
        )
        text(
            (b[0] + b[2]) // 2, -(b[1] + b[3]) // 2 + 45, person["id"].split("P")[-1], 135, "middle"
        )
    for a in current.get("activity_volumes", []):
        rect(a["bounds_mm"], "#efbe6580", a["id"] + " 600×900mm活动范围", "#ac6d19")
    for v in current.get("swept_volumes_mm", []):
        rect([v[0], v[1], v[3], v[4]], "#db684433", "连续人体扫掠", "#c14b36")
    for d in current.get("doors", []):
        if d["kind"] != "NO_PLAN_INTRUSION":
            pts = " ".join(f"{q[0]},{-q[1]}" for q in [d["hinge_mm"], *d["arc_mm"]])
            out.append(
                f'<polygon points="{pts}" fill="#e18a3a80"><title>{html.escape(d["id"])} z={d["z_interval_mm"]}mm</title></polygon>'
            )
    for e in current.get("conflicts", []):
        b = e.get("bounds_mm")
        if "volume_mm" in e:
            v = e["volume_mm"]
            b = [v[0], v[1], v[3], v[4]]
        if b:
            rect(b, "#c3363622", e["code"], "#c33636")
    if current.get("points_mm"):
        pts = " ".join(f"{q[0]},{-q[1]}" for q in current["points_mm"])
        out.append(f'<polyline points="{pts}" fill="none" stroke="#bd4c38" stroke-width="28"/>')
    for q in g["room"]["portals"]:
        a, b = q["segment_mm"]
        out.append(
            f'<line x1="{a[0]}" y1="{-a[1]}" x2="{b[0]}" y2="{-b[1]}" stroke="#087b6b" stroke-width="65"/>'
        )
    out.append(
        '<path d="M0,-3560 H26331 M0,-3410 V-3710 M26331,-3410 V-3710 M-400,0 V-3250 M-550,0 H-250 M-550,-3250 H-250" stroke="#38586b" stroke-width="16" fill="none"/>'
    )
    text(13165, -3750, "26331mm · 历史H5矩形不变", 205, "middle")
    text(-600, -1700, "3250", 130)
    text(13165, 350, "南Portal x=12415–13915mm / 净宽1500", 170, "middle")
    text(22000, -4100, "东入口 y=875–2375 / 1500mm", 145)
    text(600, -4100, "北带转向本位：650×450，同一450×650人体", 140)
    text(600, -2500, "柜区净通道1200 · 90°转向需792×792连续扫掠", 140)
    text(600, -1850, "本人柜前站立600×900；更衣期间柜门关闭（未批准假设）", 140)
    text(0, 600, "柜体：400mm列宽 / 500mm深；22列×5层=110格", 145)
    text(0, 800, "虚线＝53个本位；实心＝当前真实在室者；红＝扫掠/冲突；不增设座凳或独立更衣区", 160)
    text(
        0,
        1200,
        "HYPOTHETICAL_NOT_APPROVED · 人体/柜型/完成面/门扇/洁污待审 · 实际功能 INPUT_REQUIRED · 非施工图",
        155,
    )
    return "".join(out) + "</svg>"


def page(cases: dict[str, Any], comparison: list[dict[str, Any]]) -> str:
    # Persisted Python views are the initial fallback; JS only draws saved coordinates.
    drawings = {label: {str(s): space_svg(c, s) for s in (1, 2)} for label, c in cases.items()}
    data = dict(cases=cases, comparison=comparison, drawings=drawings)
    packed = base64.b64encode(
        gzip.compress(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0)
    ).decode()
    return TEMPLATE.replace("__DATA__", packed)


TEMPLATE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>H5 空间重排与53人容量 · R11 R9</title>
<style>body{margin:0;background:#eef2f4;color:#243c4d;font:14px system-ui,"PingFang SC",sans-serif}header{background:#223b4e;color:#fff;padding:24px}h1{font-size:26px;margin:0}main{max-width:1720px;margin:auto;padding:18px}section{background:white;padding:18px;border:1px solid #cedae0;margin-bottom:16px}h2{font-size:18px;margin-top:0}.notice{background:#fff1d8;padding:14px;line-height:1.8}.controls{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:16px 0}label{display:grid;gap:6px}select,button{padding:9px;border:1px solid #abc0cc;background:white;color:#243c4d}.drawing{overflow:auto;border:1px solid #c6d5de}.drawing svg{display:block;min-width:1700px;width:100%}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #d7e1e5;padding:10px;text-align:left;vertical-align:top}th{background:#eaf1f4}pre{white-space:pre-wrap;word-break:break-word;max-height:440px;overflow:auto;background:#f4f7f8;padding:12px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.small{line-height:1.8;color:#526e7f}.bad{color:#aa462e}@media(max-width:850px){.grid{grid-template-columns:1fr}main{padding:8px}}</style>
<header><h1>H5 · 空间重排 / 53人实际本位</h1><p>R11 R9 · 原26331×3250mm · 两班各53人 · 22列110格 · 本人柜前站立</p></header><main>
<section><div class="notice"><b>已确认：</b>本人柜前直接站立更衣、无座凳、无独立更衣区、53人初始同时在室。<br><b>本轮条件：</b>450×650mm人体、100mm本位间隙、600×900mm更衣包络、1200mm净通道；北侧部分本位采用650×450mm，只改变同一人体朝向。进入和离开本位必须通过实际通道内的连续90°扫掠，不用静态矩形冒充运动通过。<br><b>实际功能仍为 INPUT_REQUIRED：</b>设备、人体、完成面、门扇、卫生及操作规范未批准。北带仅10mm模板余量，30mm完成面负对照保留失败。</div><div class="controls"><label>空间组织<select id="case"></select></label><label>班次<select id="shift"><option value="1">第1班53人</option><option value="2">第2班53人</option></select></label><label>步骤<select id="event"></select></label><label>连续运动分段<select id="leg"><option value="-1">整个动作</option></select></label><button id="all">全图</button><button id="detail">柜区与北带放大</button></div><p id="status" class="bad"></p><div id="plan" class="drawing"></div><p class="small">虚线是本位，不代表额外人员。实心是当前实际在室者；蓝绿为等候、黄为柜前操作者；红为实际扫掠/冲突。放大视图只裁切同一坐标。柜门阴影保留对应层高；移动时柜门关闭。</p></section>
<section><h2>三种原H5重排与失败对照</h2><div style="overflow:auto"><table><thead><tr><th>方案</th><th>本位 / 转向</th><th>各班完成</th><th>两Portal / 600×900活动</th><th>条件分钟</th><th>失败位置或敏感性</th></tr></thead><tbody id="compare"></tbody></table></div></section>
<div class="grid"><section><h2>尺寸链与所需空间</h2><pre id="dimensions"></pre><p class="small">100mm间隙只限定等候本位，不是获批的动态人体余量。柜前分组沿用R8；这次没有增加并发算法。纵向末柜活动外伸125mm，转角退让由100改为125mm。原R8和开发初测失败不覆盖。3440mm等反事实宽度仅是未批准截面必要尺寸，不是完整建筑改造建议或新增Authority。</p></section><section><h2>当前检查及冲突</h2><pre id="proof"></pre><h2>必要条件性时间对照</h2><pre id="time"></pre></section></div>
<section><h2>项目来源与未确认输入</h2><pre id="binding"></pre><p>45×65cm是有方向的矩形人体条件模型，不证明真实穿脱、转身或取顶层格口的人体工学。原外部Access只读引用，未重新求解；房门保持不侵入通道的未批准假设。两次开柜、关柜更衣及错峰流程仍需审核。</p><p><a href="relayout-report.md">工程报告</a> · <a href="comparison.json">方案对照JSON</a> · <a href="relayout-results.json.gz">全部位置、门扇与连续流程原始记录</a> · <a href="source-manifest.json">来源与衍生Hash</a></p></section></main>
<script>
const $=x=>document.getElementById(x),esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');let data,c,flow;
function box(b,fill,title){return `<rect x="${b[0]}" y="${-b[3]}" width="${b[2]-b[0]}" height="${b[3]-b[1]}" fill="${fill}" stroke="#748b9c" stroke-width="12"><title>${esc(title)}</title></rect>`}
function show(){let i=+$('event').value,e=flow.events[i],p=e?.proof,li=+$('leg').value;if(li>=0)p=p?.legs?.[li]||p;$('plan').innerHTML=data.drawings[$('case').value][$('shift').value];if(p){const svg=$('plan').querySelector('svg');svg.querySelectorAll('rect').forEach(r=>{if(r.querySelector('title')?.textContent?.match(/^S[12]-P/))r.remove()});svg.querySelectorAll('text').forEach(t=>{if(/^\d{3}$/.test(t.textContent||''))t.remove()});let v='';(p.people_before||[]).forEach(o=>v+=box(o.bounds_mm,o.role==='FRONT_OPERATOR'?'#eab963':'#9dbbc8',o.id));(p.activity_volumes||[]).forEach(o=>v+=box(o.bounds_mm,'#edb85d80',o.id+' 600×900活动'));(p.swept_volumes_mm||[]).forEach(b=>v+=box([b[0],b[1],b[3],b[4]],'#cf5f3d50','连续扫掠'));(p.doors||[]).forEach(d=>{if(d.kind!=='NO_PLAN_INTRUSION')v+=`<polygon points="${[d.hinge_mm,...d.arc_mm].map(q=>q[0]+','+(-q[1])).join(' ')}" fill="#e48c3980"><title>${esc(d.id)} z=${d.z_interval_mm}</title></polygon>`});(p.conflicts||[]).forEach(e=>{let b=e.bounds_mm;if(e.volume_mm){let z=e.volume_mm;b=[z[0],z[1],z[3],z[4]]}if(b)v+=box(b,'#ce222288',e.code)});if(p.points_mm)v+=`<polyline points="${p.points_mm.map(q=>q[0]+','+(-q[1])).join(' ')}" fill="none" stroke="#b84730" stroke-width="28"/>`;svg.insertAdjacentHTML('beforeend',v)}let compact={...(p||c.geometry.waiting_evaluation)};delete compact.people_before;delete compact.legs;$('proof').textContent=JSON.stringify(compact,null,2);$('status').textContent=`${flow.status} · 初始${flow.initial_service_occupancy}人 / 完成${flow.completed_users}/53 · 实际功能 INPUT_REQUIRED`}
function choose(){let e=flow.events[+$('event').value];$('leg').innerHTML='<option value="-1">整个动作</option>'+(e?.proof?.legs||[]).map((l,i)=>`<option value="${i}">${esc(l.operation)}</option>`).join('');show()}
function refresh(){c=data.cases[$('case').value];flow=c.shifts[+$('shift').value-1];$('event').innerHTML='<option value="-1">初始53个本位 / 前置失败</option>'+flow.events.map((e,i)=>`<option value="${i}">${i} ${e.batch||''} ${esc(e.operation)} ${esc(e.proof.person_id||e.active_people?.join(','))}</option>`).join('');$('dimensions').textContent=JSON.stringify(c.geometry.dimension_chains||c.geometry.metrics,null,2);$('time').textContent=JSON.stringify({full_shift_minutes:flow.full_shift_minutes,total_route_m:flow.total_route_m,durations:flow.duration_by_operation_seconds,timing:c.timing,approval:'INPUT_REQUIRED'},null,2);$('binding').textContent=JSON.stringify(c.binding,null,2);choose()}
(async()=>{const bytes=Uint8Array.from(atob('__DATA__'),c=>c.charCodeAt(0));data=JSON.parse(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text());$('case').innerHTML=Object.keys(data.cases).map(k=>`<option>${esc(k)}</option>`).join('');$('compare').innerHTML=data.comparison.map(x=>`<tr><td>${esc(x.label)}</td><td>${x.home_count}/53 · ${x.rotated_home_count??0}个转向</td><td>${x.shifts.map(s=>s.completed_users+'/53').join(' / ')}</td><td>${esc(x.portal_and_activity_result)}</td><td>${x.shifts.map(s=>s.full_shift_minutes?.toFixed(2)??'未验证').join(' / ')}</td><td>${esc(x.limitation)}</td></tr>`).join('');$('case').onchange=refresh;$('shift').onchange=refresh;$('event').onchange=choose;$('leg').onchange=show;$('detail').onclick=()=>$('plan').querySelector('svg')?.setAttribute('viewBox','-700 -4350 13500 6050');$('all').onclick=()=>$('plan').querySelector('svg')?.setAttribute('viewBox','-700 -4350 28500 6050');refresh()})().catch(e=>{$('status').textContent='证据加载失败：'+e.message});
</script></html>"""
