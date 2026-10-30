# ruff: noqa: E501 -- standalone presentation only, no engineering formulas
"""Compact review of persisted advice. No engineering formulas in the page."""

import html
import json
from typing import Any


def historical_room_svg(room: dict[str, Any]) -> str:
    length, width = room["length_mm"], room["width_mm"]
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-700 {-width - 1200} {length + 2300} {width + 2900}">',
        f'<rect x="0" y="{-width}" width="{length}" height="{width}" fill="#f0f3f5" stroke="#304e60" stroke-width="20"/>',
        f'<text x="0" y="{-width - 550}" font-size="230">原H5：{length}×{width}mm · {room["area_m2"]}m²</text>',
    ]
    for portal in room["portals"]:
        a, b = portal["segment_mm"]
        lines.append(
            f'<line x1="{a[0]}" y1="{-a[1]}" x2="{b[0]}" y2="{-b[1]}" stroke="#087c6a" stroke-width="65"/>'
        )
    lines.append(
        '<text x="0" y="650" font-size="170">P01/P02同一房间；原工程状态保留，功能可用性INPUT_REQUIRED</text>'
    )
    return "".join(lines) + "</svg>"


def review_page(preview: dict[str, Any]) -> str:
    data = json.dumps(preview, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return TEMPLATE.replace("__DATA__", data).replace(
        "__SCOPE__", html.escape(preview["project_scope_id"])
    )


# Presentation only: all dimensions, areas, margins and status values come from Python.
TEMPLATE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>H5 条件性尺寸建议｜R11 R11</title>
<style>body{margin:0;background:#edf1f3;color:#263e4d;font:14px system-ui,"PingFang SC",sans-serif}header{background:#233f50;color:white;padding:18px 24px}h1{font-size:23px;margin:0}h2{font-size:17px;margin:0 0 12px}p{line-height:1.7}main{padding:16px;max-width:1700px;margin:auto}section{padding:16px;background:white;border:1px solid #cad6dd;margin:0 0 14px}.boundary{background:#fff1d8;padding:12px;line-height:1.8}.small{font-size:12px;color:#536b7a}.scope{overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #d8e1e5;text-align:left;padding:9px;vertical-align:top}th{background:#eef3f5}a{color:#087b6a}.controls{display:flex;flex-wrap:wrap;gap:16px;margin-bottom:12px}.panels{display:flex;gap:12px;overflow-x:auto}.card{border:1px solid #ccd8df;flex:1 0 560px;min-width:560px;padding:12px}.card img{width:100%;display:block;background:white;border:1px solid #dce3e8}.facts{display:grid;grid-template-columns:1fr 1fr;gap:14px}ul{line-height:1.9;margin:8px 0;padding-left:22px}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:420px;overflow:auto;background:#f1f5f7;padding:12px}details{margin-top:12px}.tag{font-size:12px;background:#edf4f5;padding:4px 8px;display:inline-block}.warn{color:#9d542c}@media(max-width:800px){.facts{grid-template-columns:1fr}main{padding:8px}.card{flex-basis:520px;min-width:520px}table{font-size:12px}}</style>
<header><h1>H5 条件性尺寸建议 · 整厂只读预检查</h1><p>53人初始同时在室 · 两班各53人 · 五层柜22列110格 · 本人柜前站立 · 无坐凳</p></header><main>
<section><div class="boundary"><b>功能条件验证通过 ≠ 工程批准 ≠ 整厂可用。</b><br>这里只匹配已封存的项目、候选和功能见证。原P1面积、Stage B工程状态与原布局均不改变。不同参数组仅并列展示，没有全局最优、安全性排名或正式Pareto结论。</div><p class="small scope">项目Scope：__SCOPE__</p><p id="identity"></p></section>
<section><h2>原H5与条件候选</h2><div style="overflow:auto"><table><thead><tr><th>房间 / 参数组</th><th>长×宽mm</th><th>面积㎡ / 新增㎡</th><th>完成面 / 安装输入mm</th><th>最不利已定义余量</th><th>外部影响</th></tr></thead><tbody id="comparison"></tbody></table></div><p class="small">安装输入基值与实际柜到完成面距离不同。模板加量和实测余量分别列出，不把输入目标当作通过。局部余量不是规范限值或人体四周统一缓冲。</p></section>
<section><h2>同尺度并排平面</h2><div class="controls" id="selectors"></div><div class="panels" id="plans"></div><p class="small">各面板采用相同毫米视窗；可横向滚动或打开原比例详图。金色柜前活动是另一已校核使用时刻，不是在53人之外再增加人员。原H5只画真实矩形和Portal，不伪造已安装柜体。</p></section>
<div class="facts"><section><h2>已确认输入</h2><ul id="confirmed"></ul><p class="small">人员为设计人数，不是员工花名册；五层格高约300mm仅为参考，实际柜型和尺寸仍待确认。</p></section><section><h2>Owner / 工程师待确认</h2><ul id="checklist"></ul><p class="small">本清单只是评审事项，不能在此勾选生成审批或写入Authority。</p></section></div>
<section><h2>外部空间复核</h2><p>全部扩展方案均须重新检查Site、Footprint、外部Access、相邻功能房间和工艺关系。门洞坐标未移动也不代表原外部通道仍然适用；门洞映射更不代表取得新门洞批准。原历史H5的局部功能差异不等于整厂不合格。</p><table><thead><tr><th>候选</th><th>长度 / 宽度增量mm</th><th>门洞坐标映射</th><th>整厂容纳扩建</th></tr></thead><tbody id="external"></tbody></table></section>
<section><details><summary>尺寸建议合同、来源和失效条件</summary><pre id="contract"></pre></details><p><a href="advisories.json">全部建议JSON</a> · <a href="advisory-c.example.json">C建议示例</a> · <a href="functional-room-sizing-advisory-v1.schema.json">版本化Schema</a> · <a href="handoff-review.md">工程复核报告</a> · <a href="source-manifest.json">来源Hash</a></p></section>
<script type="application/json" id="data">__DATA__</script><script>
const data=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id),esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const schemes=[{key:'original',label:'原H5',room:data.original_room,svg:'original-h5-common.svg',detail:'original-h5.svg'},...data.advisories.map((a,i)=>({key:'advice-'+i,label:a.advised_room.label,room:a.advised_room,advice:a,svg:'advice-'+i+'-common.svg',detail:'advice-'+i+'.svg'}))];
$('identity').textContent='P01/P02已去重：'+data.physical_room_count+'个物理房间。原P1需求'+data.p1_required_area_m2+'㎡仅作为既有引用，不被候选面积替代。';
$('comparison').innerHTML=schemes.map(s=>{let a=s.advice,r=s.room,c=a?.conditions.parameters;return `<tr><td>${esc(s.label)}<br><span class="small">${a?'参数组 '+c.finish_mm+'/'+c.installation_gap_mm+'（假设）':'原工程状态保留'}</span></td><td>${r.length_mm}×${r.width_mm}</td><td>${esc(r.area_m2)} / ${esc(r.additional_area_m2??'0.000000')}</td><td>${c?c.finish_mm+' / '+c.installation_gap_mm:'NOT_EVALUATED'}</td><td>${a?esc(a.margins.minimum_mm)+'mm<br>'+esc(a.margins.minimum.family)+' · '+esc(a.margins.minimum.location):'不由原面积推断功能可用'}</td><td>${a?'全部外部复核待完成':'历史结论不改写'}</td></tr>`}).join('');
$('selectors').innerHTML=schemes.map((s,i)=>`<label><input type="checkbox" data-key="${s.key}" ${i<2?'checked':''}>${esc(s.label)}</label>`).join('');
function show(){let selected=[...$('selectors').querySelectorAll('input:checked')].map(x=>x.dataset.key);$('plans').innerHTML=schemes.filter(s=>selected.includes(s.key)).map(s=>{let a=s.advice,c=a?.conditions.parameters;return `<article class="card"><h2>${esc(s.label)}</h2><p>${c?'完成面'+c.finish_mm+'mm / 安装输入'+c.installation_gap_mm+'mm；实际柜到完成面'+a.margins.families.cabinet_wall_installation.actual_mm+'mm':'P01/P02同一实际矩形及原1500mm Portal'}</p><img src="${s.svg}" alt="${esc(s.label)}同尺度真实比例平面"><p><a href="${s.detail}" target="_blank" rel="noopener">打开原比例详图</a></p>${a?`<p>两班条件流程：53 / 53；最小余量${a.margins.minimum_mm}mm。<br>模板加量${a.conditions.template_padding_mm}mm：${a.margins.template_target_met?'目标达到（仍未批准）':'目标未达到'}。</p><p class="tag">实际功能 INPUT_REQUIRED · 工程批准 / 整厂适用 NOT_EVALUATED</p>`:'<p class="tag">原Stage B状态保留 · 功能输入仍待确认</p>'}</article>`}).join('')||'<p>请选择至少一套平面。</p>'}
$('selectors').querySelectorAll('input').forEach(x=>x.onchange=show);show();
const known=[['无坐凳','BENCH_COUNT'],['本人柜前站立','CHANGING_LOCATION'],['站立姿态','CHANGING_POSTURE'],['每班设计人数','USERS_PER_SHIFT'],['班次数','SHIFT_COUNT'],['同时在室设计人数','SIMULTANEOUS_USERS'],['五层柜形式','CABINET_STRUCTURE'],['柜列','CABINET_COLUMNS'],['独立格口','COMPARTMENT_CAPACITY']];
$('confirmed').innerHTML=known.map(([label,key])=>`<li><b>${label}</b>：${esc(data.owner_confirmed_inputs[key]?.value)} <span class="small">OWNER_CONFIRMED</span></li>`).join('');
$('checklist').innerHTML=data.owner_confirmation_checklist.map(x=>`<li>${esc(x.item)} <span class="warn">INPUT_REQUIRED</span></li>`).join('');
$('external').innerHTML=data.advisories.map(a=>`<tr><td>${esc(a.advised_room.label)}</td><td>+${a.external_impact.length_increase_mm} / +${a.external_impact.width_increase_mm}</td><td>${a.external_impact.any_portal_moved?'东Portal移动到新东边界；南Portal原位':'两处Portal坐标保持，外部关系仍须复核'}</td><td>NOT_EVALUATED</td></tr>`).join('');
$('contract').textContent=JSON.stringify(data.advisories,null,2);
</script></main></html>"""
