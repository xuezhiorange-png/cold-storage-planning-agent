# ruff: noqa: E501 -- engineering presentation only; calculations remain in Python
"""Compact calibration editor and persisted witnesses; no in-browser fit formulas."""

import html
import json
import re
from typing import Any

from cold_storage.modules.layout.infrastructure.room_reverse_sizing_page import (
    plan_svg,
    plot_record,
)


def calibration_plan(case: dict[str, Any]) -> str:
    raw = case["witness"]["payload"]["case"]
    if raw is None:
        return empty_svg("INPUT_REQUIRED：没有足够实物几何参数，未套用默认柜型")
    svg = plan_svg(plot_record(raw))
    if not case["summary"]["full_flow_verified"]:
        probes = []
        for probe in raw["geometry"]["rejected_home_probes"][:8]:
            x, y, r, t = probe["bounds_mm"]
            title = html.escape(
                probe["code"] + " / " + probe["region"] + "；失败探针，不是实际本位"
            )
            probes.append(
                f'<rect x="{x}" y="{-t}" width="{r - x}" height="{t - y}" fill="#cd554322" stroke="#b6402e" stroke-width="18" stroke-dasharray="50 30"><title>{title}</title></rect>'
            )
        svg = svg.replace("</svg>", "".join(probes) + "</svg>")
    return svg


def empty_svg(text: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1800 250"><rect width="1800" height="250" fill="#f2f5f6"/><text x="40" y="120" font-size="32" fill="#4a6170">'
        + html.escape(text)
        + "</text></svg>"
    )


def comparison_plan(report: dict[str, Any]) -> str:
    """Identical mm viewport and pixel scale for the two fixed outer rectangles."""
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2200 620"><rect width="2200" height="620" fill="white"/>'
    ]
    for index, case in enumerate(report["cases"]):
        panel = calibration_plan(case)
        panel = re.sub(r'viewBox="[^"]+"', 'viewBox="-700 -5050 28631 6750"', panel, count=1)
        panel = panel.replace(
            "<svg ", f'<svg x="{index * 1100}" y="80" width="1100" height="440" ', 1
        )
        parts.append(panel)
        status = case["summary"]["full_flow_status"] if case["summary"] else "INPUT_REQUIRED"
        parts.append(
            f'<text x="{index * 1100 + 30}" y="45" font-size="24" fill="#284656">{html.escape(case["label"] + " · " + status)}</text>'
        )
    parts.append(
        '<text x="30" y="580" font-size="23" fill="#8b5b26">相同毫米视窗；未批准条件模拟。不是实物功能合格、工程批准或整厂适用。</text>'
    )
    return "".join(parts) + "</svg>"


def cabinet_elevation(case: dict[str, Any]) -> str:
    raw = case["witness"]["payload"]["case"]
    if raw is None:
        return empty_svg("实际柜型、净格尺寸和层位均待提供；不绘制伪实物立面")
    g = raw["geometry"]
    unit = g["inventory"]["cabinet_units"][0]
    width, _, height = unit["dimensions_mm"]
    cells = [c for c in g["inventory"]["compartments"] if c["unit_id"] == unit["id"]]
    v = case["witness"]["payload"]["physical_checks"]["storage"]["cells"]
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-100 {-height - 330} {width + 1400} {height + 600}"><rect x="-100" y="{-height - 330}" width="{width + 1400}" height="{height + 600}" fill="white"/><rect x="0" y="{-height}" width="{width}" height="{height}" fill="#edf2f5" stroke="#2c485a" stroke-width="6"/>'
    ]
    out.append(
        f'<text x="0" y="{-height - 220}" font-size="46">五层柜工作模型 · S1（另一班独立柜组同构）</text>'
    )
    for cell in cells:
        x, z, r, t = cell["elevation_bounds_mm"]
        color = "#cbdce8" if cell["assigned_person_id"] else "#efdfb4"
        out.append(
            f'<rect x="{x}" y="{-t}" width="{r - x}" height="{t - z}" fill="{color}" stroke="#4d6f83" stroke-width="3"/>'
        )
        label = cell["assigned_person_id"] or "SPARE"
        out.append(
            f'<text x="{x + 20}" y="{-t + 65}" font-size="32">{html.escape(label)}</text><text x="{x + 20}" y="{-t + 115}" font-size="28">T{cell["tier"]} · 高度参考{t - z}mm</text>'
        )
    for cell in v:
        tier = cell["tier"]
        match = next(c for c in cells if c["tier"] == tier)
        z, t = match["elevation_bounds_mm"][1::2]
        dims = cell["clear_dimensions_mm"]
        text = " × ".join("待确认" if n is None else str(n) for n in dims)
        out.append(
            f'<text x="{width + 70}" y="{-(z + t) // 2}" font-size="33">T{tier} 净宽×深×高：{html.escape(text)} mm</text>'
        )
    out.append(
        f'<text x="0" y="130" font-size="33">外形工作模型 {width}×{unit["dimensions_mm"][1]}×{height}mm · 非采购柜型</text>'
    )
    out.append(
        '<text x="0" y="195" font-size="30">外列宽不等于净格宽；衣物、隔断及可达性 INPUT_REQUIRED</text>'
    )
    return "".join(out) + "</svg>"


def cabinet_door_plan(case: dict[str, Any]) -> str:
    raw = case["witness"]["payload"]["case"]
    if raw is None or not raw["geometry"]["snapshots"]:
        return empty_svg("未取得合法柜前批次；不把静态失败升级为门扇或流程通过")
    g = raw["geometry"]
    s = g["snapshots"][0]
    door = s["doors"][0]
    col = next(c for c in g["inventory"]["vertical_columns"] if c["id"] == door["column_id"])
    x, y, r, t = col["bounds_mm"]
    vx = x - 150
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx} {-t - 2100} 2300 2650"><rect x="{vx}" y="{-t - 2100}" width="2300" height="2650" fill="white"/>'
    ]

    def box(b: list[int], color: str, label: str) -> None:
        a, c, d, e = b
        out.append(
            f'<rect x="{a}" y="{-e}" width="{d - a}" height="{e - c}" fill="{color}" stroke="#637d8a" stroke-width="4"><title>{html.escape(label)}</title></rect>'
        )

    for a in s["aisles"]:
        box(a, "#dcece5", "保留净通道")
    for u in g["inventory"]["cabinet_units"]:
        box(u["bounds_mm"], "#90abc0", u["id"])
    for p in s["people"]:
        box(p["bounds_mm"], "#d7bf8d" if p["role"] == "FRONT_OPERATOR" else "#bbcdd9", p["id"])
    points = [door["hinge_mm"], *door["arc_mm"], door["hinge_mm"]]
    coords = " ".join(f"{a},{-b}" for a, b in points)
    if door["kind"] != "NO_PLAN_INTRUSION":
        out.append(
            f'<polygon points="{coords}" fill="#cd5e4966" stroke="#a74133" stroke-width="7"/>'
        )
    out.append(
        f'<text x="{vx + 30}" y="{-t - 1900}" font-size="47">柜门与操作人员 · 原始毫米几何</text><text x="{vx + 30}" y="{-t - 1790}" font-size="35">扇形z={door["z_interval_mm"]}mm；人体0～{g["parameters"]["standing_height_mm"]}mm</text><text x="{vx + 30}" y="{-t - 1680}" font-size="32">门扇{door["radius_mm"]}mm / 厚{door["thickness_mm"]}mm / 90°</text>'
    )
    out.append(
        f'<text x="{vx + 30}" y="{-t - 1570}" font-size="30">解析四分之一圆盘检碰；折线仅展示 · {html.escape(case["physical_checks"]["door_status"])}</text>'
    )
    return "".join(out) + "</svg>"


def review_page(data: dict[str, Any], template: dict[str, Any], schema: dict[str, Any]) -> str:
    compact = {k: v for k, v in data.items() if k not in {"reports"}}
    compact["reports"] = {}
    for key, report in data["reports"].items():
        compact["reports"][key] = dict(
            label=report["label"],
            input_fingerprint=report["review"]["binding"]["input_fingerprint"],
            missing=report["review"]["binding"]["missing"],
            projection=report["review"]["projection"],
            parameters=report["review"]["binding"]["parameters"],
            cases=[],
        )
        for case in report["review"]["cases"]:
            compact["reports"][key]["cases"].append(
                {k: case[k] for k in ("label", "area_m2", "summary", "physical_checks", "site")}
                | dict(
                    evidence_hash=case["witness"]["evidence_hash"],
                    effective_geometry_parameters=(
                        case["witness"]["payload"]["case"]["geometry"]["parameters"]
                        if case["summary"]
                        else None
                    ),
                )
            )
    payload = json.dumps(
        dict(data=compact, template=template, catalog=schema), ensure_ascii=False
    ).replace("<", "\\u003c")
    return TEMPLATE.replace("__PAYLOAD__", payload)


TEMPLATE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>H5实物参数校准 · R11 R13</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f0f3f4;color:#243f50;font:14px system-ui,"PingFang SC",sans-serif}header{padding:20px max(16px,calc((100vw - 1440px)/2));background:#244453;color:white}h1{font-size:24px;margin:0 0 8px}main{max-width:1472px;padding:16px;margin:auto}section{background:white;border:1px solid #cad7de;padding:16px;margin-bottom:14px;min-width:0}h2{font-size:18px;margin:0 0 12px}h3{font-size:15px}p{line-height:1.7;overflow-wrap:anywhere}li{overflow-wrap:anywhere}button,input,select{font:inherit;color:inherit;border:1px solid #9bb0bc;padding:8px;background:white;max-width:100%}button{cursor:pointer}input[type=number]{width:130px}.controls label>*{min-width:0;width:100%}.notice{padding:12px;background:#fff1d8;border-left:4px solid #b77e30;line-height:1.8}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.scroll{overflow:auto;max-width:100%}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:8px;border-bottom:1px solid #d8e1e6;vertical-align:top;text-align:left;overflow-wrap:anywhere}th{background:#eef3f5}details{border-top:1px solid #d5e0e6;padding:10px 0}summary{cursor:pointer;font-weight:600}label{display:grid;gap:5px;min-width:0}.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin:14px 0}.small{font-size:12px;color:#5b7180;line-height:1.7}.bad{color:#a53d2c}#dirty{display:none;padding:12px;background:#fff0d1}.canvas{overflow:auto;border:1px solid #d2dce1;touch-action:pan-x pan-y}.canvas img{display:block;width:100%;max-height:65vh;object-fit:contain;object-position:left top;min-width:0}.elevation img{min-width:0;max-height:620px}a{color:#08786c}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:#f1f5f6;padding:10px;max-height:300px;overflow:auto}fieldset{border:0;padding:0;min-width:0}#sources td{min-width:130px}#inputGroups td:first-child{min-width:150px}#inputGroups td{min-width:130px}#sourceStatus{overflow-wrap:anywhere}@media(max-width:800px){.grid{grid-template-columns:1fr}main{padding:8px}section{padding:12px}.canvas img{min-width:0}header{padding:18px 12px}h1{font-size:21px}.elevation img{min-width:0}.controls label{flex:1 1 160px}}</style>
<header><h1>H5 · 实物参数校准</h1><div>R11 R13｜真实资料录入与同条件复核｜实际校准 INPUT_REQUIRED</div></header><main>
<section><div class="notice"><b>条件流程通过 ≠ 实物功能合格 ≠ 工程批准 ≠ 整厂适用。</b><br>尚无实际设备、衣物和人体/现场完整资料。本页回归仅使用原R10明确未批准假设；实际数据缺失保持null。上传供应商资料、文件Hash或普通JSON标签都不构成Owner确认。</div><h2 style="margin-top:16px">已确认项目要求</h2><p>20000kg/天包装成品；两班各53人；53人同时在室；106个独立储物格需求；五层五门柜22列110格；本人柜前站立更衣；无坐凳、无独立更衣区。P01/P02只计一个H5物理房间。</p><p class="small" id="scope"></p></section>
<section><h2>实际设备和现场输入 · 未审阅草稿</h2><p>选择本地资料后计算文件SHA256；字段需填写具体图号/页码/测点。此页不会从PDF自动推断尺寸，也不会签发审批。导出JSON后须用随附Python命令重新校核；资料原件需一并放入source-dir。</p><div class="controls"><label>资料原件<input type="file" id="docFile"></label><label>来源类型<select id="docKind"><option value="SUPPLIER_UNREVIEWED">供应商提供，未审核</option><option value="SITE_MEASUREMENT_UNREVIEWED">现场测量，未复核</option><option value="HYPOTHETICAL_NOT_APPROVED">明确未批准模拟假设</option></select></label><label>资料/测量日期（已知时）<input type="date" id="docDate"></label><label>图纸/测量引用<input id="docRef" placeholder="图号、版本或测量记录"></label><button id="addDoc">登记未审资料</button><button id="export">导出待审输入JSON</button></div><p class="small" id="sourceStatus">实际资料尚未提供，参数全部INPUT_REQUIRED。</p><div class="scroll"><table id="sources"><thead><tr><th>资料</th><th>类型</th><th>SHA256</th><th>日期/引用</th></tr></thead><tbody></tbody></table></div><div id="dirty">输入已变更：下方结果属于先前冻结参数，不能继续作为当前草稿的见证。导出后重新运行Python校核可获得新Hash；旧见证不再适用。</div><div id="inputGroups"></div><p class="small">字段审核只接受既有应用边界ReviewedProjectDatum；页面/CLI不把JSON转换为审批。柜型、门扇、转身或流程不受现有适配器支持时，明确返回UNSUPPORTED_PHYSICAL_CONFIGURATION，不静默替代。</p></section>
<section><h2>C与3850mm · 同参数条件复核</h2><p class="small">每一行使用对应完整几何参数集，均重新调用原R10功能适配器与两班流程。20/20采用相同50mm布置填充，30/40采用相同100mm填充；这些是回归假设，不是现场参数或规范。跨参数组不做安全性/全局最优排名。</p><div class="scroll"><table><thead><tr><th>参数组</th><th>方案/面积㎡</th><th>本位</th><th>两班完成</th><th>完整条件流程</th><th>最不利已定义余量</th><th>实物结论</th></tr></thead><tbody id="matrix"></tbody></table></div></section>
<section><div class="controls"><label>冻结结果参数组<select id="bundle"></select></label><label>房间<select id="scheme"><option value="0">C · 26331×3550mm</option><option value="1">3850mm · 26331×3850mm</option></select></label><button id="zoomIn">放大图纸</button><button id="fit">适配</button></div><p id="caseStatus"></p><div class="canvas" id="planCanvas"><img id="plan" alt="同条件重新校核的H5真实比例平面、柜组、53个本位或失败位置、活动区和原Portal"></div><p class="small">与原历史H5分开建模，不覆盖原矩形或Portal。两班错峰、53人初始在室；金色活动是另一时刻，不是额外人员。失败布置不得当作可用方案。</p><p id="margins"></p><details><summary>冻结参数、实际布置间隙及适配器边界</summary><pre id="parameterDetails"></pre></details><p id="fingerprint" class="small"></p><div class="grid"><div><h3>五层柜立面及净格尺寸</h3><div class="canvas elevation"><img id="elevation" alt="五层柜按毫米绘制的立面、所属班次与格口尺寸未确认项"></div></div><div><h3>柜门扫掠与人体活动</h3><div class="canvas elevation"><img id="door" alt="实际条件模型中的柜门扇形、人员、净通道和高度区间"></div><p class="small">以原解析扇形和三维高度区间检碰；不能将高层柜门默认当作无人体影响。</p></div></div></section>
<div class="grid"><section><h2>功能检查与明确缺口</h2><div id="checks"></div><details><summary>逐层储物、取放与可达性</summary><pre id="storage"></pre></details></section><section><h2>原整厂空间影响 · 分记录只读复核</h2><div id="site"></div><p class="small">每份原候选独立复算；面积不重复相加。内部参数不改变外矩形，不能以功能重算代替外部Access复验。Truck、未归档占用及最终整厂适用NOT_EVALUATED。</p><p>B仅保留历史：入口通道交集3.338㎡、禁建区0.982㎡；不参与本轮优先校准。</p></section></div>
<section><h2>现场还需确认</h2><ul id="missing"></ul><p>已确认的人数、无坐凳、本人柜前站立和五层形式不重新列为未知。实际校准INPUT_REQUIRED；工程批准及整厂适用NOT_EVALUATED。</p><p><a href="physical-input-template.json">空值输入合同示例</a> · <a href="physical-input.schema.json">JSON Schema</a> · <a href="calibration-report.md">复核报告</a> · <a href="calibration-summary.json">结构化结果</a> · <a href="source-manifest.json">来源和见证Hash</a></p><pre>cd backend
PYTHONPATH=src:scripts uv run python scripts/build_r11_r13_physical_calibration.py \
  --input /path/h5-physical-input.json --source-dir /path/original-documents \
  --output ../artifacts/r13-new-review
# 只读条件复核，无Native；输出目录必须新建。没有JSON审批入口。</pre></section></main>
<script>const P=__PAYLOAD__;const $=id=>document.getElementById(id);let packet=structuredClone(P.template),dirty=false,zoom=1;const labels={SUPPLIER_UNREVIEWED:'供应商提供，未审核',SITE_MEASUREMENT_UNREVIEWED:'现场测量，未复核',HYPOTHETICAL_NOT_APPROVED:'未批准模拟假设'};const add=(parent,tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;parent.append(e);return e};function markDirty(){dirty=true;$('dirty').style.display='block'}function sourceOptions(select,value){select.replaceChildren();const a=add(select,'option','未绑定资料');a.value='';for(const [id,d] of Object.entries(packet.source_documents)){const o=add(select,'option',d.file_name);o.value=id}select.value=value||''}
function sourceRow(d){const row=add($('sources').tBodies[0],'tr');for(const text of [d.file_name,labels[d.source_type],d.sha256,(d.document_date||'日期未提供')+' / '+d.reference])add(row,'td',text)}for(const d of Object.values(packet.source_documents))sourceRow(d);if(Object.keys(packet.source_documents).length)$('sourceStatus').textContent='以下资料字节已经Python核对，参数仍需既有项目审阅，不自动成为Owner确认。';$('scope').textContent='Scope '+packet.project_scope_id+' · H5 '+packet.physical_room_id;const groups={};for(const [name,spec] of Object.entries(P.catalog)){(groups[spec.group]??=[]).push([name,spec])}for(const [group,fields] of Object.entries(groups)){const d=add($('inputGroups'),'details');add(d,'summary',group+' · 未确认实际值');const scroll=add(d,'div');scroll.className='scroll';const table=add(scroll,'table');const tr=add(add(table,'thead'),'tr');for(const s of ['参数','值 / 单位','资料','具体位置'])add(tr,'th',s);const body=add(table,'tbody');for(const [name,spec] of fields){const row=add(body,'tr');const label=add(add(row,'td'),'label',spec.label);label.htmlFor='v-'+name;const td=add(row,'td');let input;if(spec.choices.length){input=add(td,'select');const empty=add(input,'option','INPUT_REQUIRED');empty.value='';for(const c of spec.choices){const o=add(input,'option',c);o.value=c}}else{input=add(td,'input');input.type=['mm','count','degree'].includes(spec.unit)?'number':'text';if(input.type==='number'){input.step='1';input.min=spec.minimum;input.max=60000}}input.id='v-'+name;const raw=packet.parameters[name];input.value=raw.value===null?'':String(raw.value);add(td,'small',' '+spec.unit);const source=add(add(row,'td'),'select');source.dataset.sourceFor=name;source.setAttribute('aria-label',spec.label+'资料');sourceOptions(source,raw.document_id);const loc=add(add(row,'td'),'input');loc.value=raw.locator||'';loc.placeholder='图号/页码/测点';loc.setAttribute('aria-label',spec.label+'来源位置');const updateValue=()=>{packet.parameters[name].value=input.value===''?null:input.type==='number'?Number(input.value):input.value;if(input.value===''){packet.parameters[name].document_id=null;packet.parameters[name].locator=null;source.value='';loc.value=''}markDirty()};input.addEventListener('input',updateValue);input.addEventListener('change',updateValue);source.addEventListener('change',()=>{packet.parameters[name].document_id=source.value||null;markDirty()});const updateLocator=()=>{packet.parameters[name].locator=loc.value||null;markDirty()};loc.addEventListener('input',updateLocator);loc.addEventListener('change',updateLocator)}}
$('addDoc').onclick=async()=>{const file=$('docFile').files[0];if(!file||!$('docRef').value.trim()){$('sourceStatus').textContent='请选择原资料并填写引用；不能凭状态文字审批。';return}const digest=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());const sha=[...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');const id='document_'+(Object.keys(packet.source_documents).length+1);packet.source_documents[id]={source_type:$('docKind').value,file_name:file.name,sha256:sha,document_date:$('docDate').value||null,project_scope_id:packet.project_scope_id,reference:$('docRef').value.trim()};sourceRow(packet.source_documents[id]);for(const select of document.querySelectorAll('select[data-source-for]'))sourceOptions(select,select.value);$('sourceStatus').textContent='Hash已核对本地所选字节；数据及适用性仍未审阅，原件需随JSON提交。';markDirty()};$('export').onclick=()=>{for(const name of Object.keys(P.catalog)){const control=$('v-'+name),source=document.querySelector('select[data-source-for="'+name+'"]'),location=source.closest('tr').querySelector('td:last-child input');const value=control.value===''?null:control.type==='number'?Number(control.value):control.value;packet.parameters[name].value=value;packet.parameters[name].document_id=value===null?null:source.value||null;packet.parameters[name].locator=value===null?null:location.value||null}const blob=new Blob([JSON.stringify(packet,null,2)+'\n'],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='h5-physical-input-unreviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),0)};
for(const [key,r] of Object.entries(P.data.reports)){const o=add($('bundle'),'option',r.label);o.value=key;for(const c of r.cases){const row=add($('matrix'),'tr');const s=c.summary;const completed=s&&s.completed_users.length?s.completed_users.join(' / '):'未执行';for(const text of [r.label,c.label+' / '+c.area_m2,s?s.home_count+'/53':'INPUT_REQUIRED',completed,s?s.full_flow_status:'未运行：参数缺失',s&&s.limiting_margin?s.minimum_margin_mm+'mm / '+s.limiting_margin.location+(s.full_flow_verified?'':'（失败布置局部值）'):'NOT_EVALUATED','INPUT_REQUIRED'])add(row,'td',text)}}
$('bundle').value='20-20';function render(){const key=$('bundle').value,index=Number($('scheme').value),r=P.data.reports[key],c=r.cases[index],s=c.summary;for(const [id,suffix] of [['plan','plan'],['elevation','elevation'],['door','door']])$(id).src=key+'-'+c.label+'-'+suffix+'.svg';$('caseStatus').textContent=r.label+' · '+c.label+' · '+(s?s.full_flow_status:r.projection.status+'；'+(r.projection.unsupported||[]).join(' / '))+(s&&!s.full_flow_verified?'；当前MIXED模板本位'+s.home_count+'/53；红虚线为失败探针，非完整可用方案':'');$('caseStatus').className=s&&!s.full_flow_verified?'bad':'';$('fingerprint').textContent='输入 '+r.input_fingerprint+' · 新见证 '+c.evidence_hash;$('margins').textContent=s&&s.limiting_margin?'最不利已定义余量：'+s.minimum_margin_mm+'mm / '+s.limiting_margin.family+' / '+s.limiting_margin.location+'；填充目标是否达到：'+s.margin_target_met:'缺少实物参数，未计算局部余量';$('parameterDetails').textContent=JSON.stringify({base_parameters:r.projection.conditions,padding_target_mm:r.projection.margin_target_mm,effective_placement:c.effective_geometry_parameters,unsupported:r.projection.unsupported,missing:r.projection.missing},null,2);$('storage').textContent=JSON.stringify(c.physical_checks.storage,null,2);$('checks').replaceChildren();const entries=[['106格需求',c.physical_checks.storage.capacity_status],['格口净尺寸/衣物/分隔','INPUT_REQUIRED；见逐层记录'],['五层操作可达性','INPUT_REQUIRED；参考包络不等于人体工学校核'],['柜门与人员',c.physical_checks.door_status],['53人本位、换位与两班流程',s?s.full_flow_status:'INPUT_REQUIRED'],['安装固定/门前空间',c.physical_checks.fixing_and_landing?JSON.stringify(c.physical_checks.fixing_and_landing):'INPUT_REQUIRED'],['实际功能','INPUT_REQUIRED']];for(const [label,state] of entries)add($('checks'),'p',label+'：'+state);$('site').replaceChildren();for(const site of c.site)add($('site'),'p',site.record+'：'+site.status+'；其他房间交集 '+site.zone_intersections.unique_intersection_area_m2+'㎡；通道 '+site.corridor_intersections.unique_intersection_area_m2+'㎡；Hard/禁建 '+site.site.unique_hard_and_no_build_intersection_area_m2+'㎡；整厂 NOT_EVALUATED');$('plan').style.width=(100*zoom)+'%';$('plan').style.maxHeight=zoom===1?'65vh':'none'}$('bundle').onchange=render;$('scheme').onchange=render;$('zoomIn').onclick=()=>{zoom=Math.min(8,zoom+.5);render()};$('fit').onclick=()=>{zoom=1;render()};for(const text of P.data.confirmation_items)add($('missing'),'li',text);render();</script></html>"""
