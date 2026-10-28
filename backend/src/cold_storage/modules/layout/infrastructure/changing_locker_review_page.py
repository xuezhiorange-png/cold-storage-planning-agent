# ruff: noqa: E501 -- static report/UI markup; no engineering calculations in JavaScript
"""Local review presentation; engineering results and SVG dimensions come from Python."""

import html
import json
from dataclasses import asdict, fields
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from cold_storage.modules.layout.application.changing_locker_review import hypothetical_review
from cold_storage.modules.layout.domain.changing_locker_screening import (
    HypotheticalLockerParameters,
)
from cold_storage.modules.layout.infrastructure.changing_staggered_simulation import (
    simulate_staggered_h5,
)


def room_svg(result: dict[str, Any], *, external: bool = False) -> str:
    room = result["room"]
    bounds = room["world_bounds_mm"] if external else room["local_bounds_mm"]
    components = [] if external else result["screening"]["components"]
    x0, y0, x1, y1 = bounds
    rectangles = [bounds, *(c["bounds_mm"] for c in components)]
    routes = result.get("external_routes", []) if external else []
    points = [p for route in routes for p in route["local_centerline_mm"]]
    # Routes use room-local coordinates; shift once for the world overview.
    points = [[p[0] + x0, p[1] + y0] for p in points]
    minx = min([r[0] for r in rectangles] + [p[0] for p in points])
    maxx = max([r[2] for r in rectangles] + [p[0] for p in points])
    miny = min([r[1] for r in rectangles] + [p[1] for p in points])
    maxy = max([r[3] for r in rectangles] + [p[1] for p in points])
    pad = 1000

    def rect(r: list[int], fill: str, extra: str = "") -> str:
        return f"<rect x='{r[0]}' y='{-r[3]}' width='{r[2] - r[0]}' height='{r[3] - r[1]}' fill='{fill}' {extra}/>"

    out = [
        f"<svg xmlns='http://www.w3.org/2000/svg' role='img' aria-label='真实比例房间与已封存门洞' viewBox='{minx - pad} {-maxy - pad} {maxx - minx + 2 * pad} {maxy - miny + 2 * pad}'>",
        rect(bounds, "#f8fafc", "stroke='#334155' stroke-width='35'"),
    ]
    colors = {
        "LOCKER": "#93c5fd",
        "PERSON": "#fbbf24",
        "BENCH": "#94a3b8",
        "AISLE": "#d1fae5",
        "BENCH_OPERATION": "#e2e8f0",
    }
    conflict_ids = {v for c in result["screening"]["conflicts"] for v in c["components"]}
    for c in sorted(components, key=lambda c: c["role"] != "AISLE"):
        color = "#c4b5fd" if c["role"] == "LOCKER" and c["shift"] == 2 else colors[c["role"]]
        out.append(
            f"<g data-states='{' '.join(c['states'])}'><title>{html.escape(c['id'])}</title>"
            + rect(
                c["bounds_mm"],
                color,
                f"stroke='{'#dc2626' if c['id'] in conflict_ids else '#64748b'}' stroke-width='18'",
            )
            + "</g>"
        )
    if not external:
        for p in result["screening"]["portal_envelopes"]:
            out.append(
                rect(
                    p["bounds_mm"],
                    "none",
                    "stroke='#a855f7' stroke-width='25' stroke-dasharray='80 60'",
                )
            )
    for p in room["portals"]:
        a, b = p["segment_mm"]
        dx, dy = (x0, y0) if external else (0, 0)
        out.append(
            f"<line x1='{a[0] + dx}' y1='{-a[1] - dy}' x2='{b[0] + dx}' y2='{-b[1] - dy}' stroke='#059669' stroke-width='65'><title>{html.escape(p['id'])}; {p['clear_width_mm']}mm</title></line>"
        )
    for r in routes:
        line = " ".join(f"{p[0] + x0},{-p[1] - y0}" for p in r["local_centerline_mm"])
        out.append(
            f"<polyline points='{line}' fill='none' stroke='#0d9488' stroke-width='90'><title>原始外部路线 {r['route_length_m']}m</title></polyline>"
        )
    for route in result.get("simulated_internal_routes", []) if not external else []:
        line = " ".join(f"{p[0]},{-p[1]}" for p in route["points_mm"])
        out.append(
            f"<polyline points='{line}' data-states='{' '.join(route['states'])}' fill='none' stroke='#2563eb' stroke-width='70'><title>假设内部净通行中心线</title></polyline>"
        )
    out.append(
        f"<text x='{x0}' y='{-y1 - 300}' font-size='250' fill='#334155'>{x1 - x0} × {y1 - y0} mm</text></svg>"
    )
    stamp = (
        "仅封存外部通道 · 内部功能未验证"
        if external
        else "HYPOTHETICAL_NOT_APPROVED · 项目功能 INPUT_REQUIRED"
    )
    out[-1] = out[-1].replace(
        "</svg>",
        f"<text x='{minx}' y='{-miny + 700}' font-size='500' fill='#92400e'>{stamp}</text></svg>",
    )
    return "".join(out)


def response(result: dict[str, Any]) -> dict[str, Any]:
    result = dict(result)
    result["conditional_simulation"] = (
        simulate_staggered_h5(
            result["room"],
            result["design_counts"],
            HypotheticalLockerParameters(**result["screening"]["parameters"]),
        )
        if result["handoff"] == 5
        else None
    )
    drawings = {}
    for shift, case in (result["conditional_simulation"] or {}).get("shifts", {}).items():
        rendered = dict(
            result,
            screening=dict(
                result["screening"],
                components=case["witness"]["components"],
                conflicts=case["r3"]["conflicts"] + case["original_r11"]["conflicts"],
            ),
            simulated_internal_routes=case["witness"]["routes"],
        )
        drawings[shift] = room_svg(rendered)
    return dict(
        result=result,
        svg=room_svg(result),
        external_svg=room_svg(result, external=True),
        shift_svgs=drawings,
    )


def preview_request(catalog: dict[str, Any], body: Any) -> dict[str, Any]:
    """Untrusted web input can change hypotheses only, never reviewed design facts."""
    if (
        not isinstance(body, dict)
        or set(body) != {"group", "parameters"}
        or not isinstance(body["parameters"], dict)
    ):
        raise ValueError("HYPOTHETICAL_FIELDS_ONLY_NO_REVIEW_IMPORT")
    allowed = {f.name for f in fields(HypotheticalLockerParameters)}
    if not set(body["parameters"]) <= allowed:
        raise ValueError("HYPOTHETICAL_PARAMETERS_ONLY")
    return response(
        hypothetical_review(
            catalog, body["group"], HypotheticalLockerParameters(**body["parameters"])
        )
    )


def render_page(catalog: dict[str, Any], presets: dict[str, Any]) -> str:
    default = asdict(HypotheticalLockerParameters())
    labels = {
        "locker_width_mm": "柜宽",
        "locker_depth_mm": "柜深",
        "locker_height_mm": "柜高",
        "aisle_mm": "净通道",
        "front_clearance_mm": "柜前操作净距",
        "end_space_mm": "端部留空",
        "first_row_count": "双侧第一排柜数",
        "person_width_mm": "人员操作宽",
        "person_depth_mm": "人员操作深",
        "bench_count": "座凳数量",
        "bench_width_mm": "座凳宽",
        "bench_depth_mm": "座凳深",
        "bench_height_mm": "座凳高",
        "bench_operation_mm": "座凳操作间距",
        "finish_inset_mm": "完成面单侧内缩",
        "active_shift": "当前班次",
    }
    controls = "".join(
        f"<label>{html.escape(label)}<input type='number' name='{key}' value='{default[key]}' min='0' max='60000' step='1'></label>"
        for key, label in labels.items()
    )
    groups = "".join(
        f"<option value='{g['group']}'>{g['group']} · H{g['handoff']} · {'/'.join(g['records'])}</option>"
        for g in catalog["groups"]
    )
    rows = "".join(
        f"<tr><td>{g['group']}</td><td>H{g['handoff']}</td><td>{g['room']['local_bounds_mm'][2]} × {g['room']['local_bounds_mm'][3]}</td><td>{presets[g['group'] + ':SINGLE_SIDE']['result']['screening']['ideal_single_side_capacity']}</td><td>{presets[g['group'] + ':DOUBLE_SIDE']['result']['screening']['ideal_remaining_aisle_mm']}</td><td>INPUT_REQUIRED</td></tr>"
        for g in catalog["groups"]
    )
    # Full component records remain in the evidence JSON; SVG already carries their geometry.
    page_presets = {
        key: dict(
            value,
            result=dict(
                value["result"],
                screening={
                    k: v for k, v in value["result"]["screening"].items() if k != "components"
                },
            ),
        )
        for key, value in presets.items()
    }
    for value in page_presets.values():
        conditional = value["result"].get("conditional_simulation")
        if conditional:
            value["result"]["conditional_simulation"] = dict(
                conditional,
                shifts={
                    shift: {k: v for k, v in case.items() if k not in {"witness", "original_r11"}}
                    for shift, case in conditional["shifts"].items()
                },
            )
    data = json.dumps(page_presets, ensure_ascii=False).replace("<", "\\u003c")
    page = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>R11 R3 · 106柜功能评审</title>
<style>*{box-sizing:border-box}body{margin:0;background:#eef1f4;color:#253346;font:14px system-ui,sans-serif;line-height:1.6}header{background:#172839;color:white;padding:24px 32px}header h1{font-size:24px;margin:4px 0}header p{color:#c8d4df;margin:8px 0}.pill{display:inline-block;padding:2px 8px;border:1px solid #90a5b7;border-radius:4px;font-size:11px}main{max-width:1580px;margin:20px auto;padding:0 24px}.summary{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}.card,.panel{background:white;border:1px solid #dbe2e8;border-radius:6px;padding:16px;margin-bottom:16px}.number{font-size:26px;font-weight:650}.muted{color:#64748b;font-size:12px}.workspace{display:grid;grid-template-columns:300px minmax(0,1fr);gap:18px}.controls{display:grid;grid-template-columns:1fr 1fr;gap:10px}label{font-size:12px;display:block}input,select{display:block;width:100%;border:1px solid #bac6d1;border-radius:4px;padding:7px;background:white;color:#243447}select{margin-bottom:12px}h2{font-size:17px;margin:0 0 10px}h3{font-size:14px}.notice{padding:12px;background:#fff7dd;border-left:3px solid #c19024;margin:12px 0}.drawing{overflow:auto;min-height:180px}svg{display:block;width:100%;min-width:760px;max-height:500px}.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px}.legend span:before{content:'■';color:var(--c);padding-right:5px}.status{font-weight:650;color:#92400e}.ok{color:#166534}.fail{color:#b91c1c}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:9px;border-bottom:1px solid #e2e8f0;text-align:left}code{font-size:11px;overflow-wrap:anywhere}#errors{color:#b91c1c}li{margin:4px 0}@media(max-width:900px){.workspace{grid-template-columns:1fr}.summary{grid-template-columns:repeat(2,1fr)}main{padding:0 12px}header{padding:18px}.controls{grid-template-columns:repeat(3,1fr)}}</style>
<header><span class="pill">R11 R3 · 工程功能评审 / 不执行布局搜索</span><h1>106 个独立柜，能否落进现有更衣室？</h1><p>真实房间与门洞 + 已确认项目基数 + 明确标注的假设排布。三个来源分层展示。</p></header>
<main><section class="summary"><div class="card"><div class="muted">已确认成品日质量 · kg</div><div class="number">20,000</div><span class="pill">CONFIRMED_PROJECT_BASIS</span></div><div class="card"><div class="muted">设计包装人员 / 班</div><div class="number">53</div><span class="muted">10,000kg / 192，向上取整</span></div><div class="card"><div class="muted">两班独立柜</div><div class="number">106</div><span class="muted">53 + 53，禁止跨班共柜</span></div><div class="card"><div class="muted">同时更衣 / 包装台</div><div class="number">53 / 18</div><span class="muted">设计计算值，不是实际花名册</span></div><div class="card"><div class="muted">真实物理房间组</div><div class="number">8</div><span class="muted">9份记录；P01/P02合并为G01</span></div></section>
<section class="workspace"><aside class="panel"><h2>假设敏感性参数</h2><span class="pill">HYPOTHETICAL_NOT_APPROVED</span><p class="muted">全部尺寸为mm；第一排柜数及座凳数为数量。参数只影响此指定模板，不写入Authority。</p><label>实际房间组<select id="group">GROUP_OPTIONS</select></label><label>柜体布置<select id="arrangement"><option value="DOUBLE_SIDE">相对双侧</option><option value="SINGLE_SIDE">单侧长墙</option></select></label><div class="controls">CONTROLS</div><label>显示状态<select id="state"><option value="USE">正常使用</option><option value="SHIFT_CHANGE">交接班</option><option value="CLEANING">清洁</option><option value="MAINTENANCE">维护</option></select></label><p class="muted">状态切换为图层展示；完整四状态功能校核仍待已审设计输入。虚线为假设内向通行净区，不是门扇开启范围。</p><p id="errors" role="status"></p></aside>
<article><section class="panel"><h2 id="room-title"></h2><div id="formal" class="notice">项目功能结论：INPUT_REQUIRED</div><div id="screen-summary"></div><div class="legend"><span style="--c:#93c5fd">一班柜</span><span style="--c:#c4b5fd">二班柜</span><span style="--c:#fbbf24">假设人员空间</span><span style="--c:#94a3b8">假设座凳</span><span style="--c:#059669">真实门洞</span><span style="--c:#dc2626">指定模板冲突</span></div><h3 id="template-title">保守对照：同时预留两排操作区</h3><div id="drawing" class="drawing"></div><div id="counts"></div><details><summary>指定模板冲突明细（不代表其他模板不可行）</summary><div id="conflicts"></div></details></section>
<section class="panel"><h2>H5 两班错峰条件模拟（未经批准）</h2><p>仅假设当前班柜排操作、未用柜排关闭；房门暂按无门扇Portal、柜门按不侵入地面的机制。净高4000mm、净通道1200mm、柜体与人员尺寸、无座凳及无需洁污隔断均未批准。蓝线为新构造的假设内部路线，不是原历史外部路线。</p><p id="shift-summary"></p><h3>一班：独立柜位、关联人位与净通行</h3><div id="shift-one" class="drawing"></div><h3>二班：独立柜位、关联人位与净通行</h3><div id="shift-two" class="drawing"></div><p>任何模拟结果均不改变实际房间 INPUT_REQUIRED。</p></section><section class="panel"><h2>原始外部通道与门洞来源</h2><div id="external" class="drawing"></div><p class="muted">仅回读历史通道中心线。外部Stage B通过不能替代内部柜体、人员、门扇与维护校核。</p><div id="portals"></div></section><section class="panel"><h2>正式功能输入缺口</h2><ul id="missing"></ul><p class="muted">本页不提供将普通JSON、勾选框或假设参数转为已审输入的接口。后续完整设计通过应用侧审阅后，调用原R11功能校核器；CONDITIONAL_FIT仍不等于专业工程批准。</p></section></article></section>
<section class="panel"><h2>八组必要条件对照 · 柜宽400 / 深500 / 净通道1200</h2><p class="muted">单侧容量为未扣门洞和端部的理想上界；双侧剩余宽度还未扣人员操作及座凳。H5通过基本尺寸必要条件，不代表功能合格。</p><table><thead><tr><th>组</th><th>Handoff</th><th>实际矩形 mm</th><th>单侧理想柜数</th><th>双侧柜间剩余 mm</th><th>项目功能状态</th></tr></thead><tbody>OVERVIEW_ROWS</tbody></table></section>
<section class="panel"><h2>当前来源与评审边界</h2><p>项目成品20000kg/天来自Owner任务 V2_2_2_R11_R3_106_LOCKER_LAYOUT_REVIEW_R1；默认均分、192kg/人班和独立柜规则来自原Owner V2合同。人数、柜数、包装台为ENGINEERING_DERIVED设计值。原历史进厂量、P1、Stage B、九/十二指标及资源账本全部保持不变。</p><p>柜型、净完成面、门扇、柜门操作、人员空间、座凳、清洁分隔、内部通道与维护资料仍为INPUT_REQUIRED。此处任何假设均为HYPOTHETICAL_NOT_APPROVED；指定模板失败为CONFIGURATION_NOT_FIT，不能推广为所有布局不可行。</p></section></main>
<script type="application/json" id="presets">PRESET_DATA</script><script>
const presets=JSON.parse(document.getElementById('presets').textContent);let ticket=0;
function state(){document.querySelectorAll('[data-states]').forEach(e=>e.style.display=e.dataset.states.split(' ').includes(document.getElementById('state').value)?'':'none')}
function show(data){const r=data.result,s=r.screening;const cs=r.conditional_simulation;document.getElementById('shift-summary').textContent=cs?cs.simulation_status+' · '+(cs.not_evaluated_reason||'')+'；'+Object.entries(cs.shifts).map(([k,v])=>'第'+k+'班：'+v.r3.status+'，使用人位 '+(v.r3.state_results.USE?.people_count??'未验证')+'，交接人位 '+(v.r3.state_results.SHIFT_CHANGE?.people_count??'未验证')+'，路线中心y='+v.route_center_y_mm+'mm').join('；'):'本模板未评估该H5条件模拟';document.getElementById('shift-one').innerHTML=(data.shift_svgs||{})['1']||'';document.getElementById('shift-two').innerHTML=(data.shift_svgs||{})['2']||'';document.getElementById('room-title').textContent=r.group+' · H'+r.handoff+' · '+r.records.join('/')+' · '+r.project_evaluation.physical_facts.width_m+' × '+r.project_evaluation.physical_facts.depth_m+'m';document.getElementById('template-title').textContent=s.parameters.arrangement==='DOUBLE_SIDE'?'保守对照：同时预留两排操作区':'单侧连续/分段指定模板';document.getElementById('drawing').innerHTML=data.svg;document.getElementById('external').innerHTML=data.external_svg;document.getElementById('formal').textContent='项目功能结论：INPUT_REQUIRED — 柜型、完成面、内部通行与完整见证尚未确认';document.getElementById('screen-summary').textContent='必要条件：'+s.necessary_condition_status+'；理想所需长度 '+s.required_length_mm+'mm / 宽度 '+s.required_width_mm+'mm；含操作区所需宽度 '+s.operation_width_required_mm+'mm；指定模板：'+s.specified_template_status;document.getElementById('counts').textContent='已画柜位 '+s.placed_lockers+' / '+r.design_counts.locker_count+'；未安置 '+s.unplaced_lockers+'；各排 '+s.actual_row_counts.join(' / ')+'；人员空间 '+s.placed_person_spaces+' / '+r.design_counts.simultaneous_users+'；座凳 '+s.placed_benches;document.getElementById('conflicts').textContent=JSON.stringify({原因:s.reasons,空间冲突:s.conflicts},null,2);const m=document.getElementById('missing');m.replaceChildren();r.project_evaluation.missing_inputs.forEach(t=>{let li=document.createElement('li');li.textContent=t;m.append(li)});const p=document.getElementById('portals');p.replaceChildren();r.room.portals.forEach(t=>{let el=document.createElement('p');el.textContent=t.id+' · 净宽 '+t.clear_width_mm+'mm · 原坐标 '+JSON.stringify(t.segment_mm);p.append(el)});r.record_access_readbacks.forEach(v=>{let el=document.createElement('p');el.textContent=v.record+' 原记录：两条Access均PASS，真实Portal坐标与净宽分别核对一致';p.append(el)});state()}
async function refresh(){const n=++ticket,params={arrangement:document.getElementById('arrangement').value};document.querySelectorAll('input[name]').forEach(e=>params[e.name]=Number(e.value));const group=document.getElementById('group').value;try{let data;if(location.protocol==='file:'){data=presets[group+':'+params.arrangement];if(JSON.stringify(data.result.screening.parameters)!==JSON.stringify(params)){const same=Object.keys(params).every(k=>params[k]===data.result.screening.parameters[k]);if(!same)throw Error('自定义参数需要运行本地Python评审服务；当前图未按新参数计算。')}}else{const res=await fetch('/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({group,parameters:params})});data=await res.json();if(!res.ok)throw Error(data.error)}if(n===ticket){document.getElementById('errors').textContent='';show(data)}}catch(e){document.getElementById('errors').textContent=e.message+'；图形保留上一份结果，尚未按当前参数更新。'}}
document.querySelectorAll('input,#group,#arrangement').forEach(e=>e.addEventListener('change',refresh));document.getElementById('state').addEventListener('change',state);show(presets['G01:DOUBLE_SIDE']);
</script></html>"""
    design = catalog["design_counts"]
    page = page.replace(
        '<div class="number">20,000</div>',
        f'<div class="number">{design["packaged_mass_kg_per_day"]:,}</div>',
    )
    page = page.replace(
        '<div class="number">53</div>', f'<div class="number">{design["shift_workers"][0]}</div>'
    )
    page = page.replace(
        '<div class="number">106</div>', f'<div class="number">{design["locker_count"]}</div>'
    )
    page = page.replace(
        '<div class="number">53 / 18</div>',
        f'<div class="number">{design["simultaneous_users"]} / {design["packing_tables"]}</div>',
    )
    return (
        page.replace("GROUP_OPTIONS", groups)
        .replace("CONTROLS", controls)
        .replace("OVERVIEW_ROWS", rows)
        .replace("PRESET_DATA", data)
    )


def serve_review(catalog: dict[str, Any], page: str, port: int) -> None:
    """Loopback-only hypothetical preview. No approval, upload, file-write or solver endpoint."""

    class Handler(BaseHTTPRequestHandler):
        def send(self, status: int, content: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:
            if self.path != "/":
                self.send(404, b"Not found", "text/plain")
                return
            self.send(200, page.encode(), "text/html; charset=utf-8")

        def do_POST(self) -> None:
            try:
                if self.path != "/preview" or self.headers.get_content_type() != "application/json":
                    raise ValueError("HYPOTHETICAL_PREVIEW_ONLY")
                if self.headers.get("Host") != f"127.0.0.1:{port}" or self.headers.get(
                    "Origin"
                ) not in (None, f"http://127.0.0.1:{port}"):
                    raise ValueError("LOCAL_ORIGIN_REQUIRED")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16000:
                    raise ValueError("BOUNDED_PREVIEW_REQUEST_REQUIRED")
                body = json.loads(self.rfile.read(size))
                self.send(
                    200,
                    json.dumps(preview_request(catalog, body), ensure_ascii=False).encode(),
                    "application/json; charset=utf-8",
                )
            except (ValueError, TypeError, KeyError) as exc:
                self.send(400, json.dumps({"error": str(exc)}).encode(), "application/json")

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        print(f"Local hypothetical review: http://127.0.0.1:{port}/", flush=True)
        server.serve_forever()
