# ruff: noqa: E501 -- self-contained presentation; all engineering results come from Python
"""Render persisted exact overlay results. No engineering rules in HTML/JS."""

import html
import json
from decimal import Decimal
from typing import Any

ROOM_LABELS = (
    ("office", "办公室"),
    ("changing_room", "更衣 H5"),
    ("primary_precooling_room", "预冷1"),
    ("secondary_precooling_room", "预冷2"),
    ("raw_fruit_buffer", "原料暂存"),
    ("sorting_packaging_room", "分选包装"),
    ("coating_room", "涂膜"),
    ("finished_goods_room", "成品"),
    ("secondary_fruit_buffer", "次果"),
    ("frozen_fruit_room", "冻果"),
    ("packaging_material_storage", "包装库"),
    ("shipping_channel", "发货"),
)


def _points(points: list[list[int]]) -> str:
    return " ".join(f"{p[0]},{-p[1]}" for p in points)


def _box(bounds: list[int], attrs: str) -> str:
    x, y, r, t = bounds
    return f'<rect x="{x}" y="{-t}" width="{r - x}" height="{t - y}" {attrs}/>'


def overlay_svg(
    record: dict[str, Any], scheme: int, *, detail: bool = False, original_only: bool = False
) -> str:
    p = record["proposals"][scheme]
    boundary = p["site"]["boundaries"]["site_boundary"].get("polygon_mm")
    if not boundary:
        raise ValueError("ARCHIVED_SITE_REQUIRED_FOR_DRAWING")
    xs, ys = [v[0] for v in boundary], [v[1] for v in boundary]
    view = [min(xs) - 2000, -max(ys) - 4000, max(xs) - min(xs) + 4000, max(ys) - min(ys) + 6500]
    b = p["expanded_room_bounds_mm"]
    if detail:
        view = [b[0] - 4000, -b[3] - 5000, b[2] - b[0] + 9000, b[3] - b[1] + 9000]
    title = record["record"] + (" 原历史布局" if original_only else " · " + p["label"])
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{" ".join(map(str, view))}" role="img" aria-label="{html.escape(title)}">',
        f"<title>{html.escape(title)}；世界坐标毫米，等轴比例；叠加不是工程批准</title>",
        '<defs><pattern id="forbidden" patternUnits="userSpaceOnUse" width="650" height="650"><path d="M0 0L650 650" stroke="#9b9790" stroke-width="55"/></pattern><pattern id="collision" patternUnits="userSpaceOnUse" width="400" height="400"><path d="M0 0L400 400M400 0L0 400" stroke="#c62928" stroke-width="70"/></pattern></defs>',
        '<g font-family="sans-serif" fill="#233b47">',
        f'<polygon points="{_points(boundary)}" fill="#fff" stroke="#657780" stroke-width="100"/>',
    ]
    seen = set()
    for kind in ("no_build_zones", "hard_obstacles", "existing_buildings"):
        for obj in p["site"]["obstacles"][kind].get("archived_objects", []):
            footprint_key = tuple(tuple(v) for v in obj["polygon_mm"])
            if footprint_key in seen:
                continue
            seen.add(footprint_key)
            parts.append(
                f'<polygon data-object-id="{html.escape(obj["id"])}" points="{_points(obj["polygon_mm"])}" fill="url(#forbidden)" stroke="#8b8174" stroke-width="60"><title>{html.escape(obj["reference"])}</title></polygon>'
            )
    for z in record["zones"]:
        bounds = z["bounds_mm"]
        parts.append(
            _box(
                bounds,
                f'fill="{"#dbe7ec" if z["id"] != "changing_room" else "#bad4dc"}" stroke="#657c87" stroke-width="55" data-object-id="{z["id"]}"',
            )
        )
    for obj in record["corridors"] or []:
        parts.append(
            f'<polygon points="{_points(obj["polygon_mm"])}" fill="#36aa9b" fill-opacity="0.18" stroke="#148c7b" stroke-width="45"/>'
        )
    parts.append(
        f'<polygon points="{_points(p["footprint"]["archived"]["polygon_mm"])}" fill="none" stroke="#243e50" stroke-width="95" stroke-dasharray="450 180"/>'
    )
    if not original_only:
        for band in p["expansion_bands"]:
            parts.append(
                _box(
                    band["bounds_mm"],
                    'fill="#f3b74d" fill-opacity="0.52" stroke="#b87000" stroke-width="55"',
                )
            )
        for group in [
            p["zone_intersections"],
            p["corridor_intersections"],
            p["site"]["obstacles"]["no_build_zones"],
            p["site"]["obstacles"]["hard_obstacles"],
        ]:
            for c in group["contacts"]:
                for box in c["intersection_rectangles_mm"]:
                    parts.append(
                        _box(
                            box,
                            f'fill="url(#collision)" stroke="#bf2929" stroke-width="95" data-conflict="{html.escape(c["object_id"])}"',
                        )
                    )
        parts.append(
            _box(
                p["expanded_room_bounds_mm"],
                'fill="none" stroke="#c47b0f" stroke-width="100" stroke-dasharray="300 160"',
            )
        )
    for z in record["zones"]:
        x, y, r, t = z["bounds_mm"]
        cx, cy = (x + r) // 2, -(y + t) // 2
        rotation = f' transform="rotate(-90 {cx} {cy})"' if t - y > (r - x) * 2 else ""
        label = dict(ROOM_LABELS)[z["id"]]
        parts.append(
            f'<text x="{cx}" y="{cy}" font-size="700" text-anchor="middle"{rotation}>{label}</text>'
        )
    for portal in record["portal_geometries"]:
        parts.append(
            f'<polyline points="{_points(portal["segment_mm"])}" stroke="#8b3985" stroke-width="130" fill="none"><title>{html.escape(portal["id"])} · {portal["clear_width_mm"]}mm</title></polyline>'
        )
    for a in p["access"]:
        line = [
            [int(Decimal(v["x"]) * 1000), int(Decimal(v["y"]) * 1000)]
            for v in a["original_centerline"]
        ]
        parts.append(
            f'<polyline points="{_points(line)}" fill="none" stroke="#087d70" stroke-width="100" stroke-dasharray="180 120"/>'
        )
        for key, color in [
            ("original_portal_segment_mm", "#8b3985"),
            ("hypothetical_portal_segment_mm", "#e34b25"),
        ]:
            if key.startswith("hypothetical") and (original_only or not a["portal_mapped"]):
                continue
            points = a[key]
            parts.append(
                f'<polyline points="{_points(points)}" stroke="{color}" stroke-width="150" fill="none"><title>{html.escape(a["portal_identity"])} · {a["clear_width_mm"]}mm · {key}</title></polyline>'
            )
    if not detail:
        parts.append(
            f'<text x="{min(xs)}" y="{-max(ys) - 1600}" font-size="1050">{html.escape(title)} · 12区原始世界几何</text>'
        )
        parts.append(
            f'<text x="{min(xs)}" y="{-max(ys) - 500}" font-size="650">原候选{record["candidate_hash"][:26]}…；原状态保留；最终整厂适用 NOT_EVALUATED</text>'
        )
        parts.append(
            f'<path d="M{min(xs) + 200} {-min(ys) + 900}h5000" stroke="#263b44" stroke-width="90"/><text x="{min(xs) + 5500}" y="{-min(ys) + 1150}" font-size="650">5000mm · 北 ↑ · x向东，y向北</text>'
        )
    else:
        parts.append(
            f'<text x="{view[0] + 500}" y="{view[1] + 1000}" font-size="700">{html.escape(title)} · 更衣室邻域（原世界坐标）</text>'
        )
    parts.append("</g></svg>")
    return "".join(parts)


def review_page(result: dict[str, Any]) -> str:
    value = json.dumps(result, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return TEMPLATE.replace("__DATA__", value)


TEMPLATE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>H5扩展 · 整厂空间影响预检查</title>
<style>body{margin:0;color:#253d49;background:#eef2f4;font:14px system-ui,"PingFang SC",sans-serif}header{background:#294754;color:#fff;padding:18px 20px}h1{font-size:23px;margin:0}h2{font-size:18px;margin:0 0 12px}main{max-width:1600px;padding:14px;margin:auto}section{background:white;border:1px solid #cbd6dd;padding:14px;margin-bottom:12px}.notice{background:#fff1d7;padding:12px;line-height:1.8}p{line-height:1.65}.layout{display:grid;grid-template-columns:minmax(0,1fr) 350px;gap:12px}.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px}select,button{font:inherit;border:1px solid #a9bbc4;background:#fff;border-radius:3px;padding:8px}button{cursor:pointer}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:8px;text-align:left;border-bottom:1px solid #dce4e8;vertical-align:top}th{background:#edf3f6}.scroll{overflow:auto}.viewport{width:100%;max-height:72vh;overflow:auto;border:1px solid #cbd7df;background:white}.viewport img{display:block;width:100%;max-width:none}.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;margin:10px 0}.legend i{display:inline-block;width:16px;height:10px;margin-right:5px}a{color:#087d70}small,.small{font-size:12px;color:#526d7c;overflow-wrap:anywhere}.bad{color:#b32929;font-weight:600}.unknown{color:#8a5423}pre{font-size:11px;max-height:330px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f7;padding:10px}ul{padding-left:20px;line-height:1.9}.wrap{overflow-wrap:anywhere}@media(max-width:850px){.layout{display:block}main{padding:7px}header{padding:14px}h1{font-size:20px}.viewport{max-height:65vh}td,th{min-width:95px}.controls{gap:6px}select{max-width:100%}section{padding:10px}}</style>
<header><h1>H5尺寸扩展 · 整厂空间影响预检查</h1><p>P01/P02分别读取 · 一个物理更衣室 · 无布局搜索、无通道重规划</p></header><main>
<section><div class="notice"><b>没有检测到交集 ≠ 外部Access重新验收通过 ≠ 整厂适用。</b><br>本页只叠加封存几何。红色为实际正面积交集，普通边界接触不算占用冲突。缺失Truck或其他占用证据保留NOT_EVALUATED。原P1、历史候选、Stage B与正式比较结果不改变。</div><p class="small wrap" id="scope"></p></section>
<section><h2>C、3850mm、B空间影响矩阵</h2><div class="scroll"><table><thead><tr><th>记录 / 条件方案</th><th>房间新增㎡</th><th>其他房间交集㎡</th><th>原通道交集㎡</th><th>禁建/Hard交集㎡</th><th>归档可建边界</th><th>净Footprint增加㎡</th><th>原入口Access</th><th>最终整厂</th></tr></thead><tbody id="matrix"></tbody></table></div><p class="small">P01/P02是同一物理H5的两份历史记录，不合计扩建面积。Hard Obstacles与No-build同一覆盖不重复计面积。净Footprint为“保留原通道的叠加并集”，不是经过重新设计的建筑，也不表示B冲突区域可继续通行。</p></section>
<div class="layout"><section><h2>真实比例整厂叠加图</h2><div class="controls"><label>原记录 <select id="record"><option>P01</option><option>P02</option></select></label><label>条件方案 <select id="scheme"><option value="0">C · 20/20mm</option><option value="1">3850mm · 30/40mm</option><option value="2">B · 20/20mm</option></select></label><label><input id="detail" type="checkbox">更衣室邻域</label><button id="in">放大</button><button id="out">缩小</button><button id="fit">适配</button></div><div class="viewport"><img id="plan" alt="原整厂12区、人员通道与反事实更衣室扩展的等比例叠加"></div><div class="legend"><span><i style="background:#dbe7ec"></i>原12区</span><span><i style="background:#f3b74d"></i>新增占用</span><span><i style="background:#c62928"></i>正面积交集</span><span><i style="background:#36aa9b"></i>原2000mm通道</span><span>灰斜线：归档禁建/Hard</span><span>深色虚线：原Footprint</span><span>紫：原Portal；橙：条件映射</span></div><p><a id="full" target="_blank" rel="noopener">打开完整SVG</a> · <a id="original" target="_blank" rel="noopener">原历史整厂图</a></p><p class="small">全场采用统一毫米视窗；邻域图仅改变视窗，几何保持原坐标。手机可放大后滑动。门洞仍为原1500mm净宽。B显示的旧入口路线已发生占用冲突，不是新方案的有效路线。</p></section>
<section><h2 id="selected-title"></h2><p id="dimensions"></p><p id="condition"></p><div id="collision-summary"></div><p id="unknowns" class="unknown"></p><details><summary>交集坐标、源对象与Hash</summary><pre id="evidence"></pre></details><details><summary>原12区世界边界</summary><pre id="zones"></pre></details></section></div>
<section><h2>受影响的Portal及原Access</h2><div class="scroll"><table><thead><tr><th>原Access身份</th><th>原Portal世界坐标mm</th><th>条件Portal世界坐标mm</th><th>预检查状态</th></tr></thead><tbody id="access"></tbody></table></div><p class="small">这里只比较原门洞与条件映射，未生成任何替代通道，也未重新声明MUST、Access或P2D通过。</p></section>
<section><h2>已确认输入与Owner待确认</h2><p>已确认：两班各53人、53人同时在室、五层五门柜、本人柜前站立更衣、无坐凳。以下继续使用R11原清单，不产生审批记录。</p><ul id="checklist"></ul><p><a href="owner-input-template.json">未审参数模板（未知值为null，无默认批准值）</a> · <a href="site-impact.json">完整结构化JSON</a> · <a href="impact-matrix.json">矩阵JSON</a> · <a href="source-manifest.json">来源与证据Hash</a> · <a href="site-impact-report.md">工程报告</a></p></section>
<script type="application/json" id="data">__DATA__</script><script>
const data=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id),esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');let zoom=1;const names=['C','3850','B'];
$('scope').textContent='Scope '+data.project_scope_id+' · 原物理房间数 '+data.physical_room_count+' · 逐记录预检查 '+data.independently_checked_records;
$('matrix').innerHTML=data.impact_matrix.map(r=>`<tr><td>${esc(r.record+' / '+r.label)}</td><td>${esc(r.additional_room_area_m2)}</td><td>${esc(r.other_zone_overlap_m2)}</td><td>${esc(r.corridor_overlap_m2)}</td><td>${esc(r.prohibited_overlap_m2)}</td><td>${esc(r.effective_boundary==='WITHIN_ARCHIVED_BOUNDARY'?'归档边界内':r.effective_boundary)}</td><td>${esc(r.net_footprint_increase_m2)}</td><td class="${r.corridor_redesign_required?'bad':''}">${esc(r.entrance_access)}</td><td>NOT_EVALUATED</td></tr>`).join('');
function show(){let record=data.records.find(r=>r.record===$('record').value),i=Number($('scheme').value),p=record.proposals[i],file=record.record+'-'+names[i];$('plan').src=file+($('detail').checked?'-detail':'')+'.svg';$('plan').style.width=(zoom*100)+'%';$('plan').style.maxHeight=zoom===1?'60vh':'none';$('plan').style.objectFit='contain';$('full').href=file+'.svg';$('original').href=record.record+'-original.svg';$('selected-title').textContent=record.record+' · '+p.label;$('dimensions').textContent='原H5 '+JSON.stringify(p.original_room_bounds_mm)+'mm → 条件房间 '+JSON.stringify(p.expanded_room_bounds_mm)+'mm';let c=p.conditions.parameters;$('condition').textContent='未批准完成面 '+c.finish_mm+'mm / 安装输入 '+c.installation_gap_mm+'mm。R10/R11条件Hash与双班见证保持原样。';let contacts=[...p.corridor_intersections.contacts,...p.site.obstacles.no_build_zones.contacts,...p.zone_intersections.contacts];$('collision-summary').innerHTML=contacts.length?contacts.map(c=>`<p class="bad">${esc(c.intersection_area_m2)}㎡ · ${esc(JSON.stringify(c.intersection_rectangles_mm))}mm<br><small>${esc(c.object_id)}</small></p>`).join(''):p.checked_geometry_status==='NOT_EVALUATED'?'<p class="unknown">部分归档几何缺失：NOT_EVALUATED。</p>':'<p>已检查新增带内未检测到正面积交集；不能据此输出整厂PASS。</p>';$('unknowns').textContent='Truck Envelope、未归档占用、最终外部Access及整厂工程验收：NOT_EVALUATED。实际功能输入：INPUT_REQUIRED。';$('evidence').textContent=JSON.stringify({candidate_hash:record.candidate_hash,source_sha256:record.source_sha256,advisory_hash:p.advisory_hash,witness_sha256:p.witness_sha256,expansion_bands:p.expansion_bands,corridor:p.corridor_intersections,site:p.site,footprint:p.footprint},null,2);$('zones').textContent=JSON.stringify(record.zones.map(z=>({role:z.id,bounds_mm:z.bounds_mm,reference:z.reference,object_hash:z.object_hash})),null,2);$('access').innerHTML=p.access.map(a=>`<tr><td class="wrap">${esc(a.requirement_identity)}</td><td>${esc(JSON.stringify(a.original_portal_segment_mm))}</td><td>${esc(JSON.stringify(a.hypothetical_portal_segment_mm))}<br>${esc(a.clear_width_mm)}mm净宽</td><td>${esc(a.status)}<br>完整复验：NOT_EVALUATED</td></tr>`).join('')}
['record','scheme','detail'].forEach(id=>$(id).onchange=show);$('in').onclick=()=>{zoom=Math.min(4,zoom+.5);show()};$('out').onclick=()=>{zoom=Math.max(1,zoom-.5);show()};$('fit').onclick=()=>{zoom=1;show()};$('checklist').innerHTML=data.owner_confirmation_checklist.map(r=>`<li>${esc(r.item)}：INPUT_REQUIRED</li>`).join('');show();
</script></main></html>"""
