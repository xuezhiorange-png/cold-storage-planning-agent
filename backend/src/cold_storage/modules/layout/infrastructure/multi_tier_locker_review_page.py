# ruff: noqa: E501 -- presentation markup, no browser-side engineering calculations
"""Local R4 review: display persisted results; parameter edits stay hypothetical."""

import html
import json
from dataclasses import fields
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from cold_storage.modules.layout.application.multi_tier_locker_review import (
    review_multi_tier_template,
)
from cold_storage.modules.layout.domain.multi_tier_locker_model import MultiTierHypothesis


def _rect(box: list[int], color: str, title: str = "", extra: str = "") -> str:
    x, y, r, t = box
    return f"<rect x='{x}' y='{-t}' width='{r - x}' height='{t - y}' fill='{color}' {extra}><title>{html.escape(title)}</title></rect>"


def plan_svg(result: dict[str, Any], snapshot: dict[str, Any] | None = None) -> str:
    room = result["room"]
    length, depth = room["local_bounds_mm"][2:]
    out = [
        f"<svg xmlns='http://www.w3.org/2000/svg' role='img' aria-label='历史房间真实比例与假设柜体布置' viewBox='-400 {-depth - 650} {length + 800} {depth + 1900}'>",
        _rect(room["local_bounds_mm"], "#f8fafc", extra="stroke='#334155' stroke-width='25'"),
    ]
    witness = snapshot["witness"] if snapshot else None
    conflicts = (
        {k for c in snapshot["evaluation"].get("conflicts", []) for k in c["components"]}
        if snapshot
        else set()
    )
    if witness:
        for a in witness["aisles"]:
            out.append(_rect(a, "#ccf3e4", "假设净通道"))
        for c in witness["operation_zones"]:
            out.append(_rect(c["bounds_mm"], "#ffedd5", c["id"]))
    for u in result["inventory"]["cabinet_units"]:
        if "bounds_mm" in u:
            out.append(
                _rect(
                    u["bounds_mm"],
                    "#93c5fd" if u["shift"] == 1 else "#c4b5fd",
                    u["id"] + "; 实体柜体；五层格口不重复占地",
                    "stroke='#475569' stroke-width='15'",
                )
            )
    if witness:
        for c in [*witness["benches"], *witness["people"], *witness["door_exclusions"]]:
            color = (
                "#f59e0b"
                if c.get("role") == "FRONT_OPERATOR"
                else "#64748b"
                if c.get("role") == "BENCH"
                else "#fcd34d"
                if "role" in c
                else "#fca5a5"
            )
            out.append(
                _rect(
                    c["bounds_mm"],
                    color,
                    c["id"],
                    f"stroke='{'#dc2626' if c['id'] in conflicts else '#92400e'}' stroke-width='12'",
                )
            )
        line = " ".join(f"{x},{-y}" for x, y in witness["route_points_mm"])
        out.append(
            f"<polyline points='{line}' fill='none' stroke='#047857' stroke-width='35'><title>假设内部中心线，按原P2全宽包络核查</title></polyline>"
        )
    for p in room["portals"]:
        a, b = p["segment_mm"]
        out.append(
            f"<line x1='{a[0]}' y1='{-a[1]}' x2='{b[0]}' y2='{-b[1]}' stroke='#be185d' stroke-width='70'><title>{html.escape(p['id'])}; 封存净宽{p['clear_width_mm']}mm</title></line>"
        )
    title = f"{result['group']} · {length} × {depth} mm · {result['geometry_status']}"
    out.append(
        f"<text x='0' y='{-depth - 200}' font-size='250'>{html.escape(title)}</text><text x='0' y='550' font-size='220'>HYPOTHETICAL_NOT_APPROVED · 实际项目 INPUT_REQUIRED · 门洞取自历史原件</text><line x1='0' y1='850' x2='1000' y2='850' stroke='#334155' stroke-width='25'/><text x='1100' y='925' font-size='220'>1m</text></svg>"
    )
    return "".join(out)


def elevation_svg(result: dict[str, Any], shift: int) -> str:
    """Equal x/z scale; elevation coordinates come from enumerated physical cells."""
    inv = result["inventory"]
    units = [u for u in inv["cabinet_units"] if u["shift"] == shift]
    height = max(u["dimensions_mm"][2] for u in units)
    width = sum(u["dimensions_mm"][0] + 100 for u in units)
    out = [
        f"<svg xmlns='http://www.w3.org/2000/svg' role='img' aria-label='五层格口真实比例假设立面' viewBox='-80 {-height - 500} {width + 160} {height + 1150}'>"
    ]
    offset = 0
    for u in units:
        w, _d, h = u["dimensions_mm"]
        out.append(
            _rect(
                [offset, 0, offset + w, h], "#e2e8f0", u["id"], "stroke='#334155' stroke-width='8'"
            )
        )
        for c in [c for c in inv["compartments"] if c["unit_id"] == u["id"]]:
            a, z, b, t = c["elevation_bounds_mm"]
            color = "#f1f5f9" if c["purpose"] == "SPARE" else "#bfdbfe" if shift == 1 else "#ddd6fe"
            out.append(
                _rect(
                    [offset + a, z, offset + b, t],
                    color,
                    c["id"] + " / " + str(c["assigned_person_id"]) + " / " + c["purpose"],
                    "stroke='#475569' stroke-width='5'",
                )
            )
            label = (
                "备用" if not c["assigned_person_id"] else c["assigned_person_id"].split("-")[-1]
            )
            label += (
                " 工"
                if c["purpose"] == "WORK_CLOTHES"
                else " 私"
                if c["purpose"] == "PRIVATE_CLOTHES"
                else ""
            )
            out.append(f"<text x='{offset + a + 15}' y='{-z - 120}' font-size='48'>{label}</text>")
            if result["demand"]["scenario"] == "INTERNAL_PARTITION" and c["assigned_person_id"]:
                mid = offset + (a + b) // 2
                out.append(
                    f"<line x1='{mid}' y1='{-z}' x2='{mid}' y2='{-t}' stroke='#b45309' stroke-width='6' stroke-dasharray='20 20'><title>仅分隔意向符号；厚度、两侧容积及卫生有效性INPUT_REQUIRED</title></line>"
                )
        out.append(f"<text x='{offset}' y='120' font-size='55'>{u['id']}</text>")
        offset += w + 100
    out.append(
        f"<text x='0' y='{-height - 200}' font-size='110'>班次{shift} · 五层五门工作模型 · 柜型及全部尺寸 HYPOTHETICAL_NOT_APPROVED</text><text x='0' y='350' font-size='95'>约300mm只是参考；内部隔断与双格方案均未获功能批准</text></svg>"
    )
    return "".join(out)


def presentation(result: dict[str, Any]) -> dict[str, Any]:
    return dict(
        result=result,
        plan_svg=plan_svg(result),
        shift_elevations={str(s): elevation_svg(result, s) for s in (1, 2)},
        snapshot_svgs={s["id"]: plan_svg(result, s) for s in result["snapshots"]},
    )


def preview_request(catalog: dict[str, Any], body: Any) -> dict[str, Any]:
    if (
        not isinstance(body, dict)
        or set(body) != {"group", "scenario", "parameters"}
        or not isinstance(body["parameters"], dict)
    ):
        raise ValueError("HYPOTHESES_ONLY_NO_PROJECT_FACT_OR_APPROVAL_IMPORT")
    allowed = {f.name for f in fields(MultiTierHypothesis)}
    if not set(body["parameters"]) <= allowed:
        raise ValueError("HYPOTHESES_ONLY_NO_PROJECT_FACT_OR_APPROVAL_IMPORT")
    return presentation(
        review_multi_tier_template(
            catalog, body["group"], body["scenario"], MultiTierHypothesis(**body["parameters"])
        )
    )


def render_page(catalog: dict[str, Any], presets: dict[str, Any]) -> str:
    data = json.dumps(dict(catalog=catalog, presets=presets), ensure_ascii=False).replace(
        "<", "\\u003c"
    )
    return """<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>R11 R4 · 五层格口工程评审</title>
<style>*{box-sizing:border-box}body{margin:0;background:#edf1f4;color:#172a3a;font:14px/1.65 system-ui}header{background:#182c3b;color:white;padding:26px 4vw}header h1{margin:4px 0;font-size:27px}.tag{font:12px monospace;color:#93c5fd}main{max-width:1500px;margin:auto;padding:22px}.facts{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.card,section{background:white;border:1px solid #ccd6df;border-radius:6px;padding:18px;margin-bottom:15px}.big{font-size:24px;font-weight:650}.note{background:#fffbeb;border-left:4px solid #d97706;padding:12px}.grid{display:grid;grid-template-columns:315px minmax(0,1fr);gap:18px}label{display:block;margin:7px 0}select,input,button{font:inherit;padding:7px;width:100%;border:1px solid #bccad5;border-radius:4px}button{background:#173f59;color:white;cursor:pointer;margin-top:12px}.fields{display:grid;grid-template-columns:1fr 1fr;gap:5px 12px}.fields label{font-size:12px}svg{width:100%;display:block}#plan{overflow:auto}#plan svg{min-width:0}pre{white-space:pre-wrap;max-height:250px;overflow:auto;font-size:12px}h2{font-size:18px;margin:0 0 12px}h3{font-size:15px}small{color:#526576}.legend span{display:inline-block;margin-right:18px}summary{cursor:pointer}.grid>section{overflow-wrap:anywhere}.grid>div{min-width:0}.status{color:#92400e;font-weight:650}.elevation{overflow:auto}.elevation svg{min-width:700px}@media(max-width:900px){.grid{grid-template-columns:1fr}.facts{grid-template-columns:1fr 1fr}}</style>
<header><div class="tag">R11 R4 / 只读历史几何 · 零 Native</div><h1>五层格口，更衣空间逐项核查</h1><div>106 是独立储物格口需求。柜列、落地柜体、同时在室人数和柜前并发人数分别建模。</div></header>
<main><div class="facts"><div class="card"><small>OWNER_CONFIRMED · 形式</small><div class="big">五层 / 五门</div>每人独立格口；实际柜型未选</div><div class="card"><small>ENGINEERING_DERIVED · 基本方案</small><div class="big">22 列 / 110 格</div>每班 11 列、53 格需求、2 格备用</div><div class="card"><small>原项目设计基准</small><div class="big">53 人同时在室</div>柜前并发人数仍 INPUT_REQUIRED</div><div class="card"><small>真实功能结论</small><div class="big status">INPUT_REQUIRED</div>8 组矩形 / 9 份原记录</div></div>
<div class="note">所有尺寸、柜前并发、门扇、人员空间、座凳及完成面参数均为 <b>HYPOTHETICAL_NOT_APPROVED</b>。约300mm是参考，不是已审柜高。快照通过不代表已验证动态换位、吞吐、疏散、五层操作人体工学或洁污分隔，不产生 CONDITIONAL_FIT。</div>
<div class="grid" style="margin-top:18px"><section><h2>条件演示</h2><label>真实房间 <select id="group"></select></label><label>分隔工作模型 <select id="scenario"><option value="INTERNAL_PARTITION">每人1格，格内隔断待审</option><option value="TWO_COMPARTMENTS">每人2格，工衣/私衣分格待审</option></select></label><label>柜列方案 <select id="arrangement"><option value="OPPOSED">两侧独立班次柜列</option><option value="SINGLE_SIDE">单侧两班柜列</option></select></label><p id="capacity"></p><details><summary>调整假设参数（需本地服务）</summary><div id="fields" class="fields"></div><button id="apply">计算假设快照</button><small>0mm门扇侵入是假设无内侵/滑门，并非已确认。人员、座凳和门扇冲突会保留；修改参数不会批准项目输入。</small></details><p id="message" class="status"></p><h3>待确认设计输入</h3><ul id="missing"></ul></section>
<div><section><h2>原房间比例与两班使用</h2><div class="legend"><span>🟦 班1实体柜</span><span>🟪 班2实体柜</span><span>🟨 在室人员</span><span>🟩 净通道</span><span>🟥 原Portal/冲突</span></div><label>班次 / 运行状态 / 操作批次 <select id="snapshot"></select></label><div id="summary"></div><div id="plan"></div><details><summary>当前快照冲突与未验证项</summary><pre id="conflicts"></pre></details></section><section><h2>实际比例立面 · 格口及人员分配</h2><p>一列五格竖向堆叠，仅柜体在平面占地。每格独立门；编号是设计人员槽，不是花名册。虚线是未批准的内部分隔意向，不能证明衣物分隔效果。</p><div class="elevation" id="e1"></div><div class="elevation" id="e2"></div></section><section><h2>原始门洞与证据</h2><pre id="source"></pre><p>两份P01/P02记录分别回读Access，但同一G01矩形仅算一组。原工程有效状态、P1、九/十二指标、历史账本不变。旧106个落地柜结论不适用于本柜型。</p></section></div></div></main>
<script type="application/json" id="data">DATA</script><script>
const D=JSON.parse(document.getElementById('data').textContent), $=id=>document.getElementById(id);let current;
for(const g of D.catalog.groups){const o=new Option(g.group+' / H'+g.handoff+' / '+g.records.join('/'),g.group);$('group').add(o)}
const missingLabels={selected_cabinet_model_and_column_grouping:'实际柜型，以及每个实体柜包含几列',cabinet_column_and_compartment_clear_dimensions:'柜体、列及格口的净宽深高',shelves_plinth_structure_and_finished_clear_height:'层板、底座构造及室内完成面净高',compartment_door_sweep_and_simultaneous_operation_rules:'柜门开启范围和同时操作规则',cabinet_front_concurrent_users_and_staggered_service_plan:'柜前并发人数与分批操作安排', '53_person_changing_spaces_and_transition_paths':'53人的更衣动作空间与换位路径',approved_reach_and_operating_clearance_for_all_five_tiers:'五层格口可达高度与操作余量',internal_divider_or_two_compartment_hygiene_approval:'格内隔断或双格分隔的卫生确认',finished_room_dimensions_and_internal_aisle_width:'完成面净尺寸和内部净通道',actual_room_door_leaf_motion_and_landing_clearance:'两处真实房门的门扇及落脚区',benches_dimensions_quantity_and_operation_spaces:'座凳数量、尺寸和操作区',clean_unclean_separation_and_cleaning_maintenance_plan:'洁污分隔与清洁维护流程',both_shift_complete_reviewed_four_state_witnesses:'两班分别通过的完整四状态见证'};
const labels={column_width_mm:'列宽mm',column_depth_mm:'柜深mm',cabinet_height_mm:'柜总高mm',compartment_clear_height_mm:'格口净高mm',plinth_mm:'底座mm',shelf_mm:'层板mm',columns_per_unit:'每实体柜列数',aisle_mm:'净通道mm',front_clearance_mm:'柜前操作mm',person_width_mm:'人员宽mm',person_depth_mm:'人员深mm',front_concurrent_users:'柜前并发人数',cabinet_door_sweep_mm:'柜门侵入mm',room_door_sweep_mm:'房门侵入mm',bench_count:'座凳数量',bench_width_mm:'座凳宽mm',bench_depth_mm:'座凳深mm',bench_operation_mm:'座凳操作mm',finish_inset_mm:'完成面内缩mm',clear_height_mm:'室内净高mm',reach_low_mm:'可达下界mm',reach_high_mm:'可达上界mm'};
for(const [k,v] of Object.entries(labels)){const l=document.createElement('label');l.textContent=v;const i=document.createElement('input');i.type='number';i.id=k;l.append(i);$('fields').append(l)}
function show(data){current=data;const r=data.result;for(const k of Object.keys(labels))$(k).value=r.parameters[k]??'';$('capacity').textContent='本方案：'+r.demand.total_columns+'列 / '+r.demand.total_capacity+'格；假设实体柜 '+r.inventory.hypothetical_floor_unit_count+' 个。真实柜体数量待选型。';$('missing').replaceChildren(...D.catalog.missing_inputs.map(v=>{const li=document.createElement('li');li.textContent=missingLabels[v]||v;return li}));$('e1').innerHTML=data.shift_elevations['1'];$('e2').innerHTML=data.shift_elevations['2'];$('source').textContent=JSON.stringify({records:r.records,room:r.room,access:r.original_access_readbacks.map(v=>({record:v.record,two_access_passes:v.two_access_passes,portal_geometry_matches:v.portal_geometry_matches,source_sha256:v.source_sha256}))},null,2);$('snapshot').replaceChildren(new Option('柜体与原门洞（不含使用快照）',''));for(const s of r.snapshots)$('snapshot').add(new Option(s.id+' · 班'+s.witness.shift+' · '+s.witness.states.join('/'),s.id));if(r.snapshots.length)$('snapshot').value=r.snapshots[0].id;draw();}
function draw(){const r=current.result,s=r.snapshots.find(s=>s.id===$('snapshot').value);$('plan').innerHTML=s?current.snapshot_svgs[s.id]:current.plan_svg;$('summary').textContent='模板：'+r.geometry_status+'；项目：INPUT_REQUIRED'+(s?'；本快照在室 '+s.evaluation.people_count+' 人 / 柜前 '+s.evaluation.active_operator_count+' 人 / 其余 '+s.evaluation.other_room_users+' 人':'');$('conflicts').textContent=JSON.stringify({template_failures:r.template_failures,missing:r.missing_hypothetical_inputs,evaluation:s?.evaluation,transitions:r.transition_paths,separation:r.separation_satisfied},null,2)}
function load(){show(D.presets[$('group').value+':'+$('scenario').value+':'+$('arrangement').value]);$('message').textContent='已载入持久化假设计算'}
for(const k of ['group','scenario','arrangement'])$(k).onchange=load;$('snapshot').onchange=draw;
$('apply').onclick=async()=>{if(location.protocol==='file:'){$('message').textContent='静态报告可切换已保存方案；自定义参数需启动说明中的本地服务。';return}const parameters={arrangement:$('arrangement').value};for(const k of Object.keys(labels))parameters[k]=$(k).value===''?null:Number($(k).value);$('message').textContent='正在验证假设快照…';try{const resp=await fetch('/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({group:$('group').value,scenario:$('scenario').value,parameters})});const data=await resp.json();if(!resp.ok)throw Error(data.error);show(data);$('message').textContent='假设计算完成，真实项目仍 INPUT_REQUIRED'}catch(e){$('message').textContent=e.message}};load();</script></html>""".replace(
        "DATA</script>", data + "</script>"
    )


def serve_review(catalog: dict[str, Any], page: str, port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def send(self, code: int, content: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:
            self.send(
                200 if self.path == "/" else 404,
                page.encode() if self.path == "/" else b"not found",
                "text/html; charset=utf-8",
            )

        def do_POST(self) -> None:
            origin = self.headers.get("Origin")
            if self.path != "/preview" or origin not in {
                None,
                f"http://127.0.0.1:{port}",
                f"http://localhost:{port}",
            }:
                self.send(403, b'{"error":"LOCAL_HYPOTHESIS_PREVIEW_ONLY"}', "application/json")
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8192:
                    raise ValueError("BOUNDED_REQUEST_REQUIRED")
                result = preview_request(catalog, json.loads(self.rfile.read(size)))
                self.send(
                    200,
                    json.dumps(result, ensure_ascii=False).encode(),
                    "application/json; charset=utf-8",
                )
            except (ValueError, TypeError, KeyError) as exc:
                self.send(400, json.dumps(dict(error=str(exc))).encode(), "application/json")

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
