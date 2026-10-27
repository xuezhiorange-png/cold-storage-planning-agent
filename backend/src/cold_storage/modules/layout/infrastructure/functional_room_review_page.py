# ruff: noqa: E501 -- inline SVG, HTML and CSS literals
"""Local, self-contained R11 review of persisted Python facts. No JS formulas."""

from html import escape
from types import MappingProxyType
from typing import Any

NAMES = MappingProxyType(
    {
        "changing_room": "更衣室 Changing",
        "office": "办公室 Office",
        "coating_room": "覆膜间 Coating",
    }
)
FIELDS = MappingProxyType(
    {
        "finished_clear_bounds_mm": "装修完成面净边界",
        "clear_height_mm": "室内净高",
        "aisle_width_mm": "内部通道净宽",
        "door_operation_envelopes_mm": "已审阅门扇或推拉门操作包络",
        "door_operation": "门型、开启方向与操作包络",
        "cleaning_maintenance_basis": "清洁、维护作业依据",
        "simultaneous_users": "同时更衣人数",
        "shift_locker_counts": "两班独立柜数量",
        "shift_change_policy": "交接班是否重叠",
        "locker_model": "更衣柜型号与版本",
        "locker_internal_separation_available": "柜内衣物分隔能力",
        "locker_dimensions_mm": "柜体安装宽、深、高",
        "locker_arrangement": "单侧 / 双侧柜布置",
        "locker_front_clearance_mm": "柜门开启及柜前操作净距",
        "person_space_mm": "单人更衣操作空间",
        "bench_count": "座凳数量（无凳需明确）",
        "bench_dimensions_mm": "座凳实体尺寸",
        "bench_operation_mm": "座凳操作余量",
        "internal_clothing_separation": "工作服与个人衣物分隔要求",
        "clean_separation": "洁净 / 非洁净区分隔设计",
        "staff_count": "办公人数及选择依据",
        "desk_dimensions_mm": "桌体尺寸",
        "chair_movement_mm": "椅子移动与起身空间",
        "storage_count": "储物家具数量",
        "storage_dimensions_mm": "储物家具尺寸",
        "necessary_functions": "办公功能清单",
        "process_type": "覆膜工艺类型",
        "equipment_model": "已选覆膜设备型号",
        "equipment_count": "设备台数",
        "equipment_dimensions_mm": "设备安装尺寸",
        "operating_clearances_mm": "各侧操作净距",
        "maintenance_clearances_mm": "各侧维护净距",
        "infeed_space_mm": "进料作业区",
        "outfeed_space_mm": "出料作业区",
        "buffer_space_mm": "产品缓冲区",
        "effective_capacity_basis": "设备有效能力与运行依据",
        "logistics_direction_basis": "设备物流方向",
        "process_portal_roles": "真实进出料门洞对应关系",
        "equipment_flow_faces": "设备进出料侧向",
        "actual_room_portal": "本房间门洞与出入连接",
        "explicit_layout_witness": "具体柜体 / 家具 / 设备布置见证",
    }
)
STATUS = MappingProxyType(
    {
        "INPUT_REQUIRED": "待补设计输入",
        "CONDITIONAL_FIT": "给定布置条件可容纳",
        "CONFIGURATION_NOT_FIT": "指定布置存在冲突",
    }
)
COLORS = MappingProxyType(
    {
        "LOCKER": "#718fa5",
        "BENCH": "#b88f62",
        "DESK": "#718fa5",
        "STORAGE": "#94a892",
        "EQUIPMENT": "#718fa5",
        "PARTITION": "#333d45",
        "PERSON": "#dfb96f",
        "CHAIR": "#dfb96f",
        "OPERATION": "#ebe0c5",
        "MAINTENANCE": "#e3d7ca",
        "AISLE": "#cde6df",
        "DOOR_OPERATION": "#e0ad77",
        "INFEED": "#d3e5ec",
        "OUTFEED": "#d3e5ec",
        "BUFFER": "#d3e5ec",
    }
)


def svg_room(room: dict[str, Any], evaluation: dict[str, Any], state: str = "USE") -> str:
    x0, y0, x1, y1 = room["local_bounds_mm"]
    w = x1 - x0
    h = y1 - y0
    margin = max(w, h) * 0.035
    shapes = [
        f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#f5f3ed" stroke="#35434e" stroke-width="2" vector-effect="non-scaling-stroke"/>'
    ]
    components = evaluation.get("witness", {}).get("components", [])
    for c in components:
        if state not in c["states"]:
            continue
        a, b, r, t = c["bounds_mm"]
        title = escape(c["id"] + " · " + c["role"] + " · ENGINEERING_DERIVED")
        shapes.append(
            f'<rect x="{a}" y="{b}" width="{r - a}" height="{t - b}" fill="{COLORS.get(c["role"], "#dfd9d1")}" fill-opacity=".64" stroke="#64727d" stroke-width=".6" vector-effect="non-scaling-stroke"><title>{title}</title></rect>'
        )
    for c in (
        evaluation.get("state_results", {}).get(state, {}).get("operation_clearance_rectangles", [])
    ):
        a, b, r, t = c["bounds_mm"]
        shapes.append(
            f'<rect x="{a}" y="{b}" width="{r - a}" height="{t - b}" fill="none" stroke="#b28d4c" stroke-dasharray="4 3" stroke-width="1" vector-effect="non-scaling-stroke"/>'
        )
    for p in room["portals"]:
        (a, b), (r, t) = p["segment_mm"]
        shapes.append(
            f'<line x1="{a}" y1="{b}" x2="{r}" y2="{t}" stroke="#157e72" stroke-width="5" vector-effect="non-scaling-stroke"><title>{escape(p["id"])} · {p["clear_width_mm"]}mm · ENGINEERING_DERIVED</title></line>'
        )
    # Consistent Y-up physical frame, no room shape distortion or fake fixtures.
    return f'<svg viewBox="{-margin} {-margin} {w + 2 * margin} {h + 2 * margin}" role="img" aria-label="{escape(NAMES[room["room_code"]])}实际矩形"><g transform="translate(0,{h}) scale(1,-1)">{"".join(shapes)}</g></svg>'


def _panel(row: dict[str, Any], synthetic: bool = False) -> str:
    room, e = row["room"], row["evaluation"]
    code = room["room_code"]
    _, _, w, h = room["local_bounds_mm"]
    facts = e["physical_facts"]
    demand = escape(facts["required_area_m2"])
    area = escape(facts["area_m2"])
    aspect = escape(facts["aspect_ratio_display"])
    width_m = escape(facts["width_m"])
    depth_m = escape(facts["depth_m"])
    overallocation = escape(facts["overallocation_percent_display"])
    missing = "".join("<li>" + escape(FIELDS.get(k, k)) + "</li>" for k in e["missing_inputs"])
    conflicts = "".join(
        "<li>" + escape(c["code"] + " · " + ", ".join(c["components"])) + "</li>"
        for c in e["conflicts"][:30]
    )
    facts = "".join(
        '<div class="datum"><b>'
        + escape(FIELDS.get(k, k))
        + "</b><span>"
        + escape(str(v["value"]))
        + "</span><small>"
        + escape(v["source_label"] + " · " + v["reference"])
        + "</small></div>"
        for k, v in e["input_facts"].items()
    )
    diagrams = "".join(
        f'<div class="state-drawing" data-state="{s}"'
        + (" hidden" if s != "USE" else "")
        + ">"
        + svg_room(room, e, s)
        + "</div>"
        for s in ("USE", "SHIFT_CHANGE", "CLEANING", "MAINTENANCE")
    )
    origin = (
        "合成算例 · 不属于真实 MAIN"
        if synthetic
        else "封存 R10 R2 · "
        + room["record"]
        + " / H"
        + str(row["handoff"])
        + " · "
        + row["physical_group"]
    )
    return f'''<section class="room-panel" data-room="{code}"><div class="panel-heading"><div><p class="eyebrow">{escape(origin)}</p><h2>{NAMES[code]}</h2></div><span class="badge">{STATUS[e["functional_status"]]}</span></div>
    <div class="gates"><div><small>历史整套方案工程验收</small><strong>{"合成场景，未作原工程验收" if synthetic else "原 Stage B 有效，保留原 Access 范围"}</strong></div><div><small>P1 面积要求</small><strong>{"满足" if e.get("p1_area_status") == "AREA_SATISFIED" else "不足"} · {demand} m²</strong></div><div><small>功能可用性</small><strong>{STATUS[e["functional_status"]]}</strong></div></div>
    <div class="review-grid"><div class="geometry"><div class="drawing-head"><b>实体矩形与已有门洞</b><span>ENGINEERING_DERIVED · 整数毫米</span></div><div class="canvas">{diagrams}</div><div class="room-metrics"><span>宽 × 深 <b>{width_m} × {depth_m} m</b></span><span>实际面积 <b>{area} m²</b></span><span>长宽比 <b>{aspect}</b></span><span>超配 <b>{overallocation}%</b></span></div><p class="note">{"柜体、通道、座凳和操作包络来自显式合成输入，仅验证给定布置。数值不作为真实项目推荐尺寸。" if synthetic else "当前仅绘制封存房间和已验证 Portal。人员、柜型、设备及装修净尺寸不足，未生成内部设施。"}</p><div class="legend"><i class="portal"></i>原门洞 <i class="aisle"></i>显式通道 <i class="body"></i>设施实体 <i class="person"></i>人员 / 操作区</div></div>
    <aside><h3>{"给定布置校核" if synthetic else "功能依据尚未齐备"}</h3><p class="note">面积达标与外部 Access 通过，不替代实际柜体、家具或设备布置验证。</p><p class="source-tag">{e["source_label"]}</p>{'<ul class="missing">' + missing + "</ul>" if missing else "<p>所需输入已提供；结论仅适用于给定数据、布置和操作状态。</p>"}{'<h4>具体冲突</h4><ul class="conflicts">' + conflicts + "</ul>" if conflicts else ""}<details><summary>输入值与来源</summary>{facts or "<p>无本项目已确认的功能尺寸输入。</p>"}</details><details><summary>几何与 Authority 来源</summary><p class="mono">{escape(room.get("geometry_reference", room["scope_id"]))}</p><p class="note">来源标签说明数据出处，不签发工程批准或求解授权。</p></details></aside></div></section>'''


def render_review(data: dict[str, Any], examples: list[dict[str, Any]]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in data["room_evaluations"]:
        grouped.setdefault(row["physical_group"], []).append(row)
    templates = []
    options = []
    for group, rows in grouped.items():
        alias = " / ".join(data["physical_groups"][group])
        representative = next(r for r in rows if r["record"] == data["physical_groups"][group][0])
        options.append(
            f'<option value="{group}">{escape(alias)} · H{representative["handoff"]} · {group}</option>'
        )
        templates.append(
            f'<template id="hist-{group}">'
            + "".join(_panel(r) for r in rows if r["record"] == representative["record"])
            + "</template>"
        )
    example_templates = "".join(
        f'<template id="example-{i}">{_panel(r, True)}</template>' for i, r in enumerate(examples)
    )
    example_options = "".join(
        f'<option value="{i}">{escape(r["title"])}</option>' for i, r in enumerate(examples)
    )
    rules = "".join(
        "<tr><td>"
        + escape(f["FIELD_NAME"])
        + "</td><td>"
        + escape(str(f["VALUE"]))
        + "</td><td>"
        + escape(f["APPLICABILITY"])
        + "</td><td>OWNER_CONFIRMED</td></tr>"
        for f in data["owner_business_rules"]["facts"]
    )
    return (
        """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>R11 功能房间评审</title><style>
:root{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;color:#23303b;background:#eaece9}*{box-sizing:border-box}body{margin:0}header{background:#202b34;color:#f5f6f2;padding:30px 4vw 27px;border-bottom:4px solid #88a99d}header .eyebrow{color:#a9c1ba}h1{margin:6px 0 10px;font-size:29px;letter-spacing:1px}h2{font-size:22px;margin:6px 0}h3{font-size:17px;margin:0 0 12px}.eyebrow{font-size:11px;letter-spacing:1px;color:#657681;margin:0}.intro{font-size:14px;color:#c8d3d6;max-width:900px;line-height:1.7}.meta{display:flex;gap:24px;flex-wrap:wrap;font-size:12px;color:#c8d3d6;margin-top:20px}.meta b{font-size:24px;color:#fff;padding-right:6px}main{max-width:1520px;margin:auto;padding:22px 3vw 40px}.toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:18px}.seg{display:flex;background:#dce2df;border-radius:5px;padding:3px}.seg button{border:0;background:transparent;padding:9px 17px;cursor:pointer;color:#485e66;font-size:13px}.seg button.active{background:#fff;box-shadow:0 1px 3px #0001;color:#1b514b}select{font-size:13px;padding:10px 14px;border:1px solid #b8c6c2;border-radius:5px;background:#fafbf9;min-width:260px}.links{margin-left:auto;display:flex;gap:15px;font-size:12px}.links a{color:#416b63}.panel-heading{display:flex;justify-content:space-between;align-items:center;padding:20px 22px;background:#fafbf8;border-bottom:1px solid #d6ded9}.badge,.source-tag{font-size:12px;color:#8c5c21;background:#f3e6d0;border:1px solid #decba7;padding:7px 10px;border-radius:4px}.room-panel{background:#fff;border:1px solid #cbd5d0;border-radius:7px;overflow:hidden}.gates{display:grid;grid-template-columns:repeat(3,1fr);background:#f1f5f2;padding:17px 22px;gap:14px;border-bottom:1px solid #dce3de}.gates small{display:block;color:#64746e;margin-bottom:6px;font-size:11px}.gates strong{font-size:13px}.review-grid{display:grid;grid-template-columns:minmax(0,1.75fr) minmax(310px,1fr)}.geometry{padding:20px 22px}.drawing-head{display:flex;justify-content:space-between;gap:10px;font-size:12px}.drawing-head span{font-size:10px;color:#64796f}.canvas{height:320px;display:flex;align-items:center;border:1px solid #e1e5de;margin-top:14px;background:repeating-linear-gradient(0deg,transparent,transparent 19px,#87988c10 20px),repeating-linear-gradient(90deg,#fdfcf8,#fdfcf8 19px,#87988c10 20px)}.state-drawing{width:100%;height:100%;padding:24px}.state-drawing svg{width:100%;height:100%}[hidden]{display:none!important}.room-metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:17px;font-size:12px;color:#68766d}.room-metrics b{display:block;color:#263d37;font-size:17px;margin-top:5px;font-variant-numeric:tabular-nums}.note{font-size:12px;line-height:1.8;color:#66756e}.legend{font-size:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}.legend i{width:12px;height:9px;display:inline-block}.portal{background:#157e72}.aisle{background:#cde6df}.body{background:#718fa5}.person{background:#dfb96f}aside{padding:22px;border-left:1px solid #e0e6e1;background:#fafbf9}.source-tag{display:inline-block;font-size:10px;margin:0 0 8px}.missing{list-style:none;padding:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;font-size:12px;margin-top:5px}.missing li:before{content:'□';color:#9f855c;margin-right:7px}.conflicts{font-size:11px;line-height:1.7;color:#9c4a32;padding-left:18px;overflow-wrap:anywhere}details{border-top:1px solid #dce3de;padding-top:12px;margin-top:16px;font-size:12px}summary{cursor:pointer;font-weight:600}.datum{padding:9px 0;border-bottom:1px solid #e5e9e4}.datum span,.datum small{display:block;margin-top:5px;overflow-wrap:anywhere}.datum small{font-size:10px;color:#7e8b84}.mono{font:11px ui-monospace,monospace;overflow-wrap:anywhere;line-height:1.7}.state-controls{display:flex;gap:10px;align-items:center;margin-top:15px;font-size:12px}.state-controls select{min-width:0}.source-section{margin-top:22px;border:1px solid #d3dbd6;border-radius:6px;background:#f9faf7;padding:20px}table{border-collapse:collapse;width:100%;font-size:11px}td,th{text-align:left;padding:9px;border-bottom:1px solid #e1e6df;line-height:1.6}td:first-child{font-family:ui-monospace,monospace;overflow-wrap:anywhere}.table-wrap{overflow-x:auto}.banner{padding:12px 16px;background:#faebd3;border:1px solid #e1c795;font-size:12px;line-height:1.7;margin-bottom:14px}.footer{font-size:11px;color:#7c8981;margin:20px 0;line-height:1.8}@media(max-width:900px){.review-grid{grid-template-columns:1fr}aside{border-left:0;border-top:1px solid #e0e6e1}.canvas{height:300px}.links{margin-left:0}}@media(max-width:560px){header{padding:22px}h1{font-size:24px}main{padding:14px}.gates{grid-template-columns:1fr;padding:14px 18px;gap:12px}.panel-heading{padding:17px;align-items:flex-start;gap:8px}h2{font-size:19px}.badge{font-size:10px;white-space:nowrap}.geometry,aside{padding:17px}.missing{grid-template-columns:1fr}.drawing-head{display:block}.drawing-head span{display:block;margin-top:6px}.canvas{height:240px}.meta{gap:17px}.seg button{padding:9px 12px}select{min-width:0;max-width:100%}.toolbar{gap:9px}.room-metrics b{font-size:15px}.links{flex-wrap:wrap}}
</style></head><body><header><p class="eyebrow">COLD STORAGE PLANNING / ENGINEERING REVIEW</p><h1>R11 功能房间可用性复核</h1><p class="intro">原工程与面积已通过。功能资料待补齐。<br>查看真实房间、已验证门洞，以及柜体、人员、设备布置所需的设计依据。</p><div class="meta"><span><b>9</b>历史记录</span><span><b>8</b>实际矩形组</span><span><b>27</b>房间功能待确认</span><span>Native Solve <b>0</b></span></div></header><main>
<div class="toolbar"><div class="seg" id="mode"><button class="active" data-mode="hist">真实历史布局</button><button data-mode="example">合成校核示例</button></div><select id="record" aria-label="选择历史布局">"""
        + "".join(options)
        + """</select><select id="example" aria-label="选择合成案例" hidden>"""
        + example_options
        + """</select><div class="links"><a href="review-data.json">完整事实 JSON</a><a href="functional-room-report.md">功能适用性报告</a></div></div><div class="banner" id="synthetic-banner" hidden>以下是输入齐全的合成校核，所有尺寸为 ENGINEERING_DERIVED 示例值，不是本项目已选柜体、家具或设备，不进入真实候选或工程验收。</div><div class="toolbar"><div class="seg" id="rooms"><button class="active" data-room="changing_room">Changing 更衣室</button><button data-room="office">Office 办公室</button><button data-room="coating_room">Coating 覆膜间</button></div></div><div id="content"></div><div class="state-controls"><label for="state">查看操作状态</label><select id="state"><option value="USE">正常使用</option><option value="SHIFT_CHANGE">交接班</option><option value="CLEANING">清洁</option><option value="MAINTENANCE">维护</option></select><span class="note">不假定不同状态可以无条件共用空间。</span></div><section class="source-section"><h3>已有 Owner 业务规则及适用边界</h3><p class="note">两班独立柜与人员计算规则已有确认；本次封存20t输入未建立实际包装人员与柜型绑定。53人 / 106柜属于条件示例，不能直接作为历史布局确定值。Office的12 / 20 / 30人也需要明确的工厂规模选择。</p><div class="table-wrap"><table><thead><tr><th>字段</th><th>值</th><th>适用条件</th><th>来源</th></tr></thead><tbody>"""
        + rules
        + """</tbody></table></div><p class="mono">Owner 来源文件 SHA256: """
        + escape(str(data["owner_business_rules"]["sha256"]))
        + """</p></section><p class="footer">ENGINEERING_DERIVED：从封存几何或显式输入确定性计算。OWNER_CONFIRMED：原确认文件中的条件规则。INPUT_REQUIRED：本房间缺少可适用的设计资料。<br>本页面不改变P1、原Stage B有效状态、九项/十二项Pareto结果，不签发工程批准，也不触发布局搜索。</p>"""
        + "".join(templates)
        + example_templates
        + """</main><script>
const $=s=>document.querySelector(s);let mode='hist',room='changing_room';
function draw(){const id=mode==='hist'?'hist-'+$('#record').value:'example-'+$('#example').value;$('#content').replaceChildren(document.getElementById(id).content.cloneNode(true));document.querySelectorAll('.room-panel').forEach(p=>p.hidden=mode==='hist'&&p.dataset.room!==room);document.querySelectorAll('.state-drawing').forEach(p=>p.hidden=p.dataset.state!==$('#state').value);$('#record').hidden=mode!=='hist';$('#example').hidden=mode!=='example';$('#rooms').hidden=mode!=='hist';$('#synthetic-banner').hidden=mode!=='example';}
$('#mode').addEventListener('click',e=>{if(!e.target.dataset.mode)return;mode=e.target.dataset.mode;$('#mode').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));draw()});$('#rooms').addEventListener('click',e=>{if(!e.target.dataset.room)return;room=e.target.dataset.room;$('#rooms').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.room===room));draw()});['#record','#example','#state'].forEach(s=>$(s).addEventListener('change',draw));draw();
</script></body></html>"""
    )
