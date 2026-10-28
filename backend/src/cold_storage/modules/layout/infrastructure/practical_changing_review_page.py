# ruff: noqa: E501 -- engineering review markup and persisted-result presentation
"""Local R5 review UI. Geometry comes from deterministic persisted evaluations."""

import base64
import gzip
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from cold_storage.modules.layout.application.practical_changing_review import preview_request
from cold_storage.modules.layout.infrastructure.multi_tier_locker_review_page import elevation_svg


def _rect(b: list[int], fill: str, label: str, extra: str = "") -> str:
    x, y, r, t = b
    return f"<rect x='{x}' y='{-t}' width='{r - x}' height='{t - y}' fill='{fill}' {extra}><title>{html.escape(label)}</title></rect>"


def plan_svg(
    r: dict[str, Any], snapshot: dict[str, Any], move: dict[str, Any] | None = None
) -> str:
    room = r["room"]
    p = r["parameters"]
    m = r["model"]
    inv = r["inventory"]
    s = [
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='-600 -4350 27931 5550' role='img' aria-label='H5真实比例假设布置及原门洞'><defs><marker id='arrow' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='6' markerHeight='6' orient='auto-start-reverse'><path d='M0 0L10 5L0 10' fill='#126a64'/></marker></defs>"
    ]
    s.append("<rect x='-600' y='-4350' width='27931' height='5550' fill='white'/>")
    s.append(
        _rect(
            room["local_bounds_mm"],
            "#f7f8fa",
            "历史H5建筑矩形，P01/P02同一房间",
            "stroke='#243548' stroke-width='25'",
        )
    )
    for b in snapshot["aisles"]:
        s.append(_rect(b, "#cdece6", "预留净通道，不允许静态占人"))
    for b in inv["cabinet_units"]:
        s.append(
            _rect(
                b["bounds_mm"],
                "#6b98c1",
                b["id"] + " / " + str(len(b["column_ids"])) + "列组合柜",
                "stroke='#264c72' stroke-width='12'",
            )
        )
    for c in inv["vertical_columns"]:
        b = c["bounds_mm"]
        s.append(_rect(b, "none", c["id"] + " / 五层", "stroke='#264c72' stroke-width='5'"))
        s.append(
            f"<text x='{(b[0] + b[2]) // 2}' y='{-b[1] - 170}' text-anchor='middle' font-size='100' fill='#152c42'>{c['id'].split('-')[-1]}</text>"
        )
    for b in m["benches"]:
        s.append(
            _rect(
                b["bounds_mm"], "#bda9d3", b["id"] + " 座凳", "stroke='#73578f' stroke-width='12'"
            )
        )
    for d in [] if move else snapshot["doors"]:
        if d["kind"] == "NO_PLAN_INTRUSION":
            continue
        pts = [d["hinge_mm"], *d["arc_mm"]]
        points = " ".join(f"{x},{-y}" for x, y in pts)
        s.append(
            f"<polygon points='{points}' fill='#ef944d' fill-opacity='.45' stroke='#ba5c14' stroke-width='10'><title>{d['id']} 全角扫掠；高度{d['z_interval_mm']}mm</title></polygon>"
        )
    people = snapshot["people"] if move is None else move.get("people_before", snapshot["people"])
    s.append(
        _rect(
            m["changing_zone"],
            "none",
            "专用更衣操作包络（假设，非人体工学批准）",
            "stroke='#9d5398' stroke-width='15' stroke-dasharray='70 35'",
        )
    )
    for person in people:
        b = person["bounds_mm"]
        color = (
            "#e8ab43"
            if person["role"] == "FRONT_OPERATOR"
            else "#7f6b9a"
            if person["role"] == "BENCH_USER"
            else "#aeb9c4"
        )
        s.append(
            _rect(
                b, color, person["id"] + " " + person["role"], "stroke='#4c5b6c' stroke-width='6'"
            )
        )
        s.append(
            f"<text x='{(b[0] + b[2]) // 2}' y='{-b[1] - 240}' text-anchor='middle' font-size='115' fill='#152432'>{person['id'].split('-')[-1][1:]}</text>"
        )
    if move:
        for b in move.get("swept_volumes_mm", []):
            s.append(
                _rect([b[0], b[1], b[3], b[4]], "#d4574f", "完整连续人体扫掠", "fill-opacity='.15'")
            )
        points = " ".join(f"{x},{-y}" for x, y in move.get("points_mm", []))
        s.append(
            f"<polyline points='{points}' fill='none' stroke='#b8322e' stroke-width='28'><title>{move.get('person_id')}；其余52人固定，柜门关闭</title></polyline>"
        )
    caption = (
        f"换位 {move['person_id']} · 图示{len(people)}/要求53人 · 1人移动、52人固定 · 柜门关闭 · 净通道{p['aisle_mm']}mm（假设）"
        if move
        else f"{snapshot['id']} · 图示{snapshot['evaluation']['people_count']}/要求53人 · 柜前{snapshot['evaluation']['front_operators']}人 / 座凳{snapshot['evaluation']['bench_users']}人 / 更衣操作{snapshot['evaluation']['changing_operators']}人 / 等候{snapshot['evaluation']['other_users']}人 · 净通道{p['aisle_mm']}mm（假设）"
    )
    route = " ".join(f"{x},{-y}" for x, y in snapshot["main_route_mm"])
    s.append(
        f"<polyline points='{route}' fill='none' stroke='#126a64' stroke-width='22' stroke-dasharray='100 60' marker-end='url(#arrow)'/>"
    )
    for portal in room["portals"]:
        a, b = portal["segment_mm"]
        s.append(
            f"<line x1='{a[0]}' y1='{-a[1]}' x2='{b[0]}' y2='{-b[1]}' stroke='#0c8377' stroke-width='65'><title>{html.escape(portal['id'])} 原1500mm净门洞</title></line>"
        )
    s += [
        "<line x1='0' y1='-3650' x2='26331' y2='-3650' stroke='#526579' stroke-width='12'/>",
        "<text x='13165' y='-3800' font-size='230' text-anchor='middle'>H5 · 26,331 × 3,250 mm · P01/P02同一物理矩形</text>",
        "<text x='26080' y='-2700' font-size='170' text-anchor='end'>东侧人员入口 · 原净宽1500</text>",
        "<text x='13165' y='350' font-size='170' text-anchor='middle'>↓ 原分选包装门洞 x12415–13915 · 净宽1500</text>",
        f"<text x='0' y='850' font-size='185'>{caption}</text>",
        "<text x='0' y='1120' font-size='170' fill='#9b4717'>全部柜型及人体参数 HYPOTHETICAL_NOT_APPROVED；实际功能 INPUT_REQUIRED；非施工图</text></svg>",
    ]
    return "".join(s)


def door_svg(r: dict[str, Any]) -> str:
    p = r["parameters"]
    inv = r["inventory"]
    first = inv["vertical_columns"][0]
    cells = [c for c in inv["compartments"] if c["column_id"] == first["id"]]
    d = p["column_depth_mm"]
    st = p["operator_standoff_mm"]
    body = p["person_depth_mm"]
    radius = p["column_width_mm"] - 2 * p["frame_mm"]
    s = [
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='-150 -2150 2600 2650' role='img' aria-label='柜门逐层扫掠高度侧视'><rect x='-150' y='-2150' width='2600' height='2650' fill='white'/>"
    ]
    s.append(_rect([0, 0, d, p["cabinet_height_mm"]], "#87a9c8", "柜体侧面"))
    for c in cells:
        z = c["elevation_bounds_mm"]
        h = radius if p["door_kind"] == "OUTWARD_HINGED_90" else 0
        if h:
            s.append(
                _rect(
                    [d, z[1], d + h, z[3]],
                    "#edac71",
                    "门扇扫掠投影，实际碰撞采用三维扇形",
                    "fill-opacity='.7'",
                )
            )
        s.append(f"<text x='30' y='{-z[1] - 100}' font-size='75'>{z[1]}–{z[3]} mm</text>")
    s.append(
        _rect([d + st, 0, d + st + body, p["standing_height_mm"]], "#e8ab43", "柜前人体占用假设")
    )
    s.append(_rect([d + st + body, 0, d + st + body + p["aisle_mm"], 100], "#cdece6", "净通道投影"))
    s += [
        "<text x='0' y='-1920' font-size='100'>逐层门扇与人体 · 等比例侧视</text>",
        f"<text x='0' y='210' font-size='80'>柜深{d} / 前退让{st} / 人体{body} / 走道{p['aisle_mm']} mm</text>",
        "<text x='0' y='360' font-size='75'>仅占用与扫掠；弯腰、伸手、梯具和穿衣动作尚未验证</text></svg>",
    ]
    return "".join(s)


def presentation(r: dict[str, Any]) -> dict[str, Any]:
    return dict(
        result=r,
        plans={s["id"]: plan_svg(r, s) for s in r["snapshots"]},
        transitions={
            str(t["shift"]): [
                plan_svg(r, next(s for s in r["snapshots"] if s["id"] == t["from_snapshot"]), m)
                for m in t["moves"]
            ]
            for t in r["transitions"]
            if "shift" in t and t["moves"]
        },
        elevations={str(i): elevation_svg(r, i) for i in (1, 2)},
        door_svg=door_svg(r),
    )


def render_page(shown: dict[str, Any]) -> str:
    data = base64.b64encode(
        gzip.compress(json.dumps(shown, ensure_ascii=False).encode(), mtime=0)
    ).decode()
    return """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>H5 更衣室｜工程深化 R11 R5</title><style>
:root{color-scheme:light;font:15px/1.65 system-ui;color:#203447;background:#eef1f3}body{margin:0}header,main{max-width:1480px;margin:auto;padding:22px 30px}header{border-bottom:1px solid #c7d2da}h1{font-size:28px;margin:0}h2{font-size:18px;margin:0 0 10px}p{margin:8px 0}.muted{color:#52697b}label{display:inline-flex;flex-direction:column;font-size:13px;margin-right:15px}select,input,button{font:inherit;padding:7px;border:1px solid #aebdc8;border-radius:4px;background:white}button{cursor:pointer;background:#203f52;color:white}.status{background:#fff1dc;border-left:4px solid #bd6e18;padding:14px 18px;margin:16px 0}.card{background:white;border:1px solid #ced9e0;padding:18px;margin:16px 0}.plan{overflow:auto}.plan svg{width:100%;min-width:1200px;display:block}.zoom svg{min-width:2200px}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}.two svg{width:100%}.facts{display:flex;gap:30px;flex-wrap:wrap}.facts b{font-size:24px}.pill{display:inline-block;padding:2px 8px;background:#e5edef;font-size:12px}details{margin:14px 0}pre{white-space:pre-wrap;font-size:12px;max-height:400px;overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}td,th{border-bottom:1px solid #dde4e8;padding:8px;text-align:left}#params{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}#params input{width:95%}.legend span{margin-right:18px}.legend i{display:inline-block;width:12px;height:12px}a{color:#156776}@media(max-width:800px){header,main{padding:16px}.two{grid-template-columns:1fr}#params{grid-template-columns:repeat(2,1fr)}}
</style><header><span class="pill">R11 R5 · H5 / P01 + P02</span><h1>更衣室：安装、操作与换位</h1><p class="muted">真实建筑矩形与原门洞 × 五层格口条件方案 · 规划辅助评审，非施工图</p><div class="status"><b>实际功能结论：INPUT_REQUIRED</b><br>53人在室、两班各53独立格为项目设计基准。柜型、门扇、人体操作、座凳、完成面、洁污工艺尚待审阅。下方通过项仅属于明确假设，不能升级为 CONDITIONAL_FIT。</div></header><main>
<div class="card"><label>条件方案<select id="preset"></select></label><label>班次 / 操作批次<select id="state"></select></label><label>平面倍率<select id="zoom"><option value="">全室</option><option value="zoom">放大，可横向滚动</option></select></label><div class="facts" id="facts"></div><p id="status" class="muted"></p></div>
<div class="card"><h2>01 · 实际比例平面</h2><div class="legend"><span><i style="background:#6b98c1"></i>组合柜体</span><span><i style="background:#e8ab43"></i>柜前人员</span><span><i style="background:#aeb9c4"></i>更衣/等候占位</span><span><i style="background:#bda9d3"></i>座凳及坐姿</span><span><i style="background:#cdece6"></i>净通道</span><span><i style="background:#ef944d"></i>柜门扫掠</span></div><div id="plan" class="plan"></div><p>东侧入口至南侧包装门洞的虚线是预留通行中心线；不是洁污分隔证明。悬停可查看组件ID及具体尺寸。</p><details><summary>当前快照冲突 / 原Portal核验</summary><pre id="conflicts"></pre></details></div>
<div class="two"><div class="card"><h2>02 · 柜门高度与操作空间</h2><div id="door"></div><p>每层独立计算扫掠高度。高层门与座凳的平面重叠不必然是三维碰撞，但门扇投影仍不得侵入预留通道。未将五层门自动当作零占地。</p></div><div class="card"><h2>03 · 相邻批次换位</h2><label>班次<select id="shift"><option>1</option><option>2</option></select></label><label>移动步骤<select id="move"></select></label><p id="motionStatus"></p><p>一次仅1人移动，其余52人保持当前位置；先关柜门、前批返回空出的本位、后批再进入柜前。红线及淡红区域为连续路径和全段人体包络。</p><p><b>尚未验证：</b>座凳起坐、其余相邻批次、队列耗时、同时穿行、穿脱衣动作、交接班重叠、清洁维护及疏散。</p><button id="showMove">在上方显示这一步</button></div></div>
<div class="card"><h2>04 · 五层柜立面与两班分配</h2><p>列与采购柜不等同：本例每2列组合，奇数末列独立成柜。格号为设计人员编号，不是花名册；虚线为内隔断意向，不代表卫生批准。</p><div class="two"><div id="e1"></div><div id="e2"></div></div></div>
<div class="card"><h2>05 · 方案对照与条件复算</h2><div id="comparison"></div><details><summary>调整假设参数（需本机预览服务）</summary><p>参数只进入本页条件计算，不修改项目事实、历史布局或Authority。完整失败方案保留。</p><div id="params"></div><button id="recalc">复算假设</button><span id="message"></span></details><details><summary>原始参数、证据与待确认项</summary><pre id="raw"></pre></details></div>
<p>打开同目录 review-report.md、hypothetical-results.json 和 source-manifest.json 可复核。所有真实项目功能状态均为 INPUT_REQUIRED。</p></main><script type="module">
const packed=Uint8Array.from(atob("__DATA__"),c=>c.charCodeAt(0));const saved=JSON.parse(await new Response(new Blob([packed]).stream().pipeThrough(new DecompressionStream("gzip"))).text());let current;const el=id=>document.getElementById(id);const names={SINGLE_SIDE:'单侧分区',OPPOSED:'相对双侧',SEGMENTED:'分段柜列'};for(const [k,v] of Object.entries(saved)){let o=new Option(k,k);el('preset').add(o)}
const labels={column_width_mm:'列宽 mm',column_depth_mm:'柜深 mm',cabinet_height_mm:'总高 mm',cell_height_mm:'格口净高 mm',plinth_mm:'底座 mm',finish_mm:'完成面内缩 mm',front_concurrency:'柜前并发人数',aisle_mm:'净通道 mm',person_width_mm:'人体占位宽 mm',person_depth_mm:'人体占位深 mm',bench_length_mm:'座凳长 mm',bench_depth_mm:'座凳深 mm',bench_count:'座凳数量',changing_operation_width_mm:'更衣操作宽 mm',changing_operation_depth_mm:'更衣操作深 mm',segment_gap_mm:'分段间距 mm',operator_standoff_mm:'柜前退让 mm'};
function table(){let h='<table><tr><th>条件</th><th>列 / 格</th><th>柜占地</th><th>静态批次</th><th>相邻换位</th><th>结论</th></tr>';for(const [k,v] of Object.entries(saved)){const r=v.result,m=r.metrics;h+=`<tr><td>${k}</td><td>${m.columns} / ${m.compartments}</td><td>${m.cabinet_footprint_mm2} mm²</td><td>${m.static_pass_count}/${m.snapshots}</td><td>${m.adjacent_batch_pass_count}/2</td><td>${r.template_status==='TEMPLATE_AND_ADJACENT_TRANSITIONS_VERIFIED_UNDER_HYPOTHESES'?'条件快照与首组换位通过':'含冲突或未验证'}</td></tr>`}el('comparison').innerHTML=h+'</table>'}
function pick(v){current=v;const r=v.result,m=r.metrics;el('state').replaceChildren();for(const s of r.snapshots)el('state').add(new Option(s.id,s.id));el('facts').innerHTML=`<p><b>${m.columns}</b> 柜列 / ${m.compartments}格</p><p><b>${m.hypothetical_procurement_units}</b> 假设组合柜</p><p><b>${m.distinct_home_positions}/53</b> 本位/要求人数</p><p><b>${m.bench_count}</b> 座凳 / ${m.bench_seat_capacity}座</p>`;el('status').textContent=r.template_status==='TEMPLATE_AND_ADJACENT_TRANSITIONS_VERIFIED_UNDER_HYPOTHESES'?'指定假设下：静态批次与首组相邻换位通过；实际功能待审':'指定假设下：存在冲突或未验证项；见下方详情';el('door').innerHTML=v.door_svg;el('e1').innerHTML=v.elevations['1'];el('e2').innerHTML=v.elevations['2'];el('raw').textContent=JSON.stringify({parameters:r.parameters,missing:r.missing_inputs,unverified:r.unverified,portal_records:r.record_access_readbacks,hygiene:r.hygiene},null,2);el('params').replaceChildren();for(const [k,label] of Object.entries(labels)){let l=document.createElement('label');l.textContent=label;let i=document.createElement('input');i.type='number';i.value=r.parameters[k];i.dataset.key=k;l.append(i);el('params').append(l)}renderState();motion()}
function renderState(){let id=el('state').value,s=current.result.snapshots.find(x=>x.id===id);el('plan').innerHTML=current.plans[id];el('conflicts').textContent=JSON.stringify(s.evaluation,null,2)}
function motion(){let sh=el('shift').value,t=current.result.transitions.find(x=>String(x.shift)===sh);el('move').replaceChildren();for(const [i,m] of (t?.moves||[]).entries())el('move').add(new Option(`${i+1} · ${m.person_id}`,i));el('motionStatus').textContent=t?`${t.status==='ADJACENT_BATCH_TRANSITION_VERIFIED_UNDER_HYPOTHESES'?'首组换位路径通过（条件假设）':'换位未完全验证'} · 仅首组相邻批次`:'未验证';}
el('preset').onchange=()=>pick(saved[el('preset').value]);el('state').onchange=renderState;el('shift').onchange=motion;el('zoom').onchange=()=>el('plan').className='plan '+el('zoom').value;el('showMove').onclick=()=>{let sv=current.transitions[el('shift').value]?.[Number(el('move').value)];if(sv)el('plan').innerHTML=sv;};el('recalc').onclick=async()=>{const p={...current.result.parameters};for(const i of el('params').querySelectorAll('input'))p[i.dataset.key]=Number(i.value);el('message').textContent='计算中…';try{const res=await fetch('/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenario:current.result.demand.scenario,parameters:p})});const out=await res.json();if(!res.ok)throw Error(out.error);pick(out);el('message').textContent='仅假设结果，未批准项目';}catch(e){el('message').textContent='未完成：'+e.message+'。直接打开HTML时仅可查看保存方案。';}};table();pick(saved[Object.keys(saved)[0]]);
</script></html>""".replace("__DATA__", data)


def serve_review(catalog: dict[str, Any], page: str, port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/":
                self.send_error(404)
                return
            data = page.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            try:
                if self.path != "/preview" or self.headers.get("Origin") not in {
                    None,
                    f"http://127.0.0.1:{port}",
                    f"http://localhost:{port}",
                }:
                    raise ValueError("LOCAL_HYPOTHESIS_PREVIEW_ONLY")
                n = int(self.headers.get("Content-Length", "0"))
                if not 0 < n <= 10000:
                    raise ValueError("BOUNDED_HYPOTHESIS_PAYLOAD_REQUIRED")
                value = presentation(preview_request(catalog, json.loads(self.rfile.read(n))))
                code = 200
            except (ValueError, KeyError, TypeError, StopIteration) as exc:
                value = dict(error=str(exc))
                code = 400
            data = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
