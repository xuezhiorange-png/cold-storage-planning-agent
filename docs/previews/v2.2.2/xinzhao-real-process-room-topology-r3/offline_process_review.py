"""Private four-layer source-aligned review, reusing R2 SVG/background renderer."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from offline_process_topology import HERE, analyze, dependencies, encode

LAYERS = (
    "source-room-boundaries",
    "physical-room-portals",
    "logical-zone-mapping",
    "process-connectivity",
)
SCRIPT = """const data=JSON.parse(document.getElementById('data').textContent);
const frames=new Map([...document.querySelectorAll('svg')].map(s=>[s,s.getAttribute('viewBox')]));
document.addEventListener('click',e=>{const x=e.target.closest('[data-object]');if(!x)return;
const [kind,id]=x.dataset.object.split(':');const value=data[kind].find(v=>(v.physical_room_id||v.portal_id)===id);
document.getElementById('details').textContent=JSON.stringify(value,null,2);
if(kind==='rooms'&&value){const [a,b,c,d]=value.source_roi;x.closest('svg').setAttribute('viewBox',[a-30,b-30,c-a+60,d-b+60].join(' '));}});
document.getElementById('reset').addEventListener('click',()=>{for(const [s,f]of frames)s.setAttribute('viewBox',f);});
document.getElementById('zone').addEventListener('change',e=>{const z=e.target.value;
for(const n of document.querySelectorAll('[data-room]')){const r=data.rooms.find(v=>v.physical_room_id===n.dataset.room);n.style.display=!z||r.logical_zone_candidates.includes(z)?'':'none';}});
for(const c of document.querySelectorAll('[data-layer]'))c.addEventListener('change',()=>{for(const n of document.getElementsByClassName(c.dataset.layer))n.style.display=c.checked?'':'none';});
"""


def safe_json(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def views(
    pdf: Path, source: dict[str, Any], result: dict[str, Any]
) -> dict[str, bytes]:
    core, renderer = dependencies()
    records = [
        {**r, "points": r["source_points"], "kind": "BOUNDARY_CONTINUATION"}
        for room in result["rooms"]
        for r in room["boundary_source_segments"]
    ]
    dummy = {
        "room_id": "R3 REFERENCE TOPOLOGY ONLY - NOT CONSTRUCTION / NOT ROUTES",
        "source_roi": [560, 535, 2850, 1840],
        "source_page": 1,
        "boundary_segments": records,
        "door_openings": [],
        "boundary_closed": False,
        "reference_topology": {"unbound_endpoints": []},
    }
    base = (
        renderer.svg(pdf, source, dummy)
        .decode()
        .replace("<image ", '<image class="SOURCE_BACKGROUND" ', 1)
    )
    base = base.replace('class="source-vector"', 'class="SOURCE_VECTOR"')
    nodes = {r["physical_room_id"]: r for r in result["rooms"]}
    positions = {
        k: (
            (r["source_roi"][0] + r["source_roi"][2]) / 2,
            (r["source_roi"][1] + r["source_roi"][3]) / 2,
        )
        for k, r in nodes.items()
    }
    output = {}
    for layer in LAYERS:
        fragments = []
        for room in result["rooms"]:
            rid = html.escape(room["physical_room_id"], quote=True)
            x, y = positions[room["physical_room_id"]]
            label = html.escape(room["source_room_name"] or "NAME UNAVAILABLE")
            fragments.append(
                f'<g data-room="{rid}" data-object="rooms:{rid}" class="LOGICAL_GROUP"><circle cx="{x}" cy="{y}" r="6" fill="#fff7d8" stroke="#6745a3"/><text x="{x + 8}" y="{y}" font-size="12" fill="#44226c">{rid}</text><title>{label} | reference_closed={room["boundary_reference_closed"]}; NOT ENGINEERING PASS</title></g>'
            )
            ring = room["outer_ring_topology"]
            if (
                layer in {"source-room-boundaries", "logical-zone-mapping"}
                and ring["closed"]
            ):
                points = " ".join(
                    f"{float(core.rational(a))},{float(core.rational(b))}"
                    for a, b in ring["vertices"]
                )
                fragments.append(
                    f'<g data-room="{rid}" data-object="rooms:{rid}" class="REFERENCE_BOUNDARY"><polygon points="{points}" fill="none" stroke="#923698" stroke-width="2" stroke-dasharray="6 4"><title>OUTER REFERENCE ONLY; CHECK INTERNAL RINGS / PARTIAL STATUS</title></polygon></g>'
                )
            if layer == "source-room-boundaries":
                for a, b in ring["unbound_endpoints"]:
                    fragments.append(
                        f'<g class="UNKNOWN_GAP"><circle cx="{float(core.rational(a))}" cy="{float(core.rational(b))}" r="2" fill="#c70000"><title>UNBOUND SOURCE END; NO SNAP</title></circle></g>'
                    )
                for inner in room["internal_ring_topology"]:
                    if inner["closed"]:
                        points = " ".join(
                            f"{float(core.rational(a))},{float(core.rational(b))}"
                            for a, b in inner["vertices"]
                        )
                        fragments.append(
                            f'<g class="UNKNOWN_GAP"><polygon points="{points}" fill="none" stroke="#c70000" stroke-width="2"><title>INTERNAL COLUMN/WELL RING RETAINED; AREA BLOCKED</title></polygon></g>'
                        )
        if layer in {"physical-room-portals", "process-connectivity"}:
            for portal in result["portals"]:
                pid = html.escape(portal["portal_id"], quote=True)
                kind = (
                    "DOOR_OPENING"
                    if portal["connection_status"] == "TWO_SIDE_SOURCE_BOUND_REFERENCE"
                    else "UNVERIFIED_CONNECTION"
                )
                for edge in portal["reference_opening_geometry"]:
                    (x0, y0), (x1, y1) = [
                        [float(core.rational(v)) for v in p] for p in edge
                    ]
                    fragments.append(
                        f'<g class="{kind}" data-object="portals:{pid}"><path d="M {x0} {y0} L {x1} {y1}" stroke="#d17800" stroke-width="4" stroke-dasharray="3 2"/><circle cx="{(x0 + x1) / 2}" cy="{(y0 + y1) / 2}" r="6" fill="transparent" stroke="#d17800"/><title>{pid} | {portal["connection_status"]}; NET WIDTH UNAVAILABLE; NOT ROUTE PASS</title></g>'
                    )
        if layer == "process-connectivity":
            for edge in result["graph"]["edges"]:
                if edge["type"] != "SOURCE_BOUND_PORTAL":
                    continue
                (a, b), (c, d) = positions[edge["from"]], positions[edge["to"]]
                fragments.append(
                    f'<g class="UNVERIFIED_CONNECTION"><path d="M {a} {b} L {c} {d}" fill="none" stroke="#996c11" stroke-width="1.2" stroke-dasharray="2 5"><title>{html.escape(edge["portal_id"])} | GRAPH EDGE, NOT PATH GEOMETRY OR PROCESS DIRECTION</title></path></g>'
                )
        title = f'<text x="575" y="525" font-size="13" fill="#762300">{layer} | SOURCE REVIEW ONLY | PROCESS DIRECTION UNVERIFIED</text>'
        output[layer] = base.replace(
            "</svg>", title + "".join(fragments) + "</svg>"
        ).encode()
    return output


def review_html(result: dict[str, Any], svgs: dict[str, bytes]) -> bytes:
    digest = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    csp = f"default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'sha256-{digest}'"
    options = '<option value="">全部功能区</option>' + "".join(
        f"<option>{html.escape(m['logical_zone_id'])}</option>"
        for m in result["mapping"]["mappings"]
    )
    controls = "".join(
        f'<label><input type="checkbox" checked data-layer="{c}">{c}</label> '
        for c in [
            "SOURCE_BACKGROUND",
            "SOURCE_VECTOR",
            "REFERENCE_BOUNDARY",
            "DOOR_OPENING",
            "UNKNOWN_GAP",
            "LOGICAL_GROUP",
            "UNVERIFIED_CONNECTION",
        ]
    )
    body = "".join(
        f"<details open><summary>{name}</summary>{content.decode()}</details>"
        for name, content in svgs.items()
    )
    text = (
        '<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="'
        + html.escape(csp, quote=True)
        + '"><title>R3 新哨工艺房间私有审图</title><style>body{font-family:sans-serif;margin:24px;background:#faf8f1}svg{width:100%;height:auto;background:white}summary{cursor:pointer;font-weight:600;padding:12px}label{display:inline-block;padding:5px}pre{white-space:pre-wrap;overflow-wrap:anywhere;border:1px solid #ccc;padding:14px;max-height:500px;overflow:auto}[data-object]{cursor:pointer}</style><h1>R3 源绑定工艺房间与门洞拓扑</h1><p>PRIVATE / ENGINEERING REVIEW REQUIRED。紫色外环不等于完整房间几何通过；红色保留缺口及内部环。门洞净宽未核实。图中点线连接仅是有门洞依据的拓扑边，不是人员、物料或工艺路线。点击房间或门洞查看来源。</p><select id="zone">'
        + options
        + '</select><button id="reset">恢复全部视图</button>'
        + controls
        + '<pre id="details">请选择房间或门洞；源path_id、闭合状态、未知端点、参考面积及逻辑候选均可查看。</pre>'
        + body
        + '<script type="application/json" id="data">'
        + safe_json(result)
        + "</script><script>"
        + SCRIPT
        + "</script>"
    )
    return text.encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("private_review", type=Path)
    parser.add_argument("private_output", type=Path)
    args = parser.parse_args()
    if args.private_output.resolve().is_relative_to(HERE.parents[3]):
        raise ValueError("PRIVATE_COORDINATES_MUST_NOT_BE_WRITTEN_IN_PUBLIC_WORKTREE")
    source, result = analyze(args.pdf, json.loads(args.private_review.read_bytes()))
    args.private_output.mkdir(parents=True, exist_ok=False)
    with (args.private_output / "result.json").open("xb") as stream:
        stream.write(encode(result))
    svgs = views(args.pdf, source, result)
    for name, content in svgs.items():
        with (args.private_output / (name + ".svg")).open("xb") as stream:
            stream.write(content)
    with (args.private_output / "review-index.html").open("xb") as stream:
        stream.write(review_html(result, svgs))


if __name__ == "__main__":
    main()
