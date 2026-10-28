# ruff: noqa: E501 -- persisted bilingual report paragraphs
"""Read-only R3 historical locker review; optional loopback sensitivity preview."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.changing_locker_review import (
    build_r3_catalog,
    hypothetical_review,
)
from cold_storage.modules.layout.domain.changing_locker_screening import (
    HypotheticalLockerParameters,
)
from cold_storage.modules.layout.infrastructure.changing_locker_review_page import (
    render_page,
    response,
    serve_review,
)


def _read_checked(path: Path, sha: str) -> bytes:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError("SEALED_SOURCE_SHA256_MISMATCH:" + str(path))
    return raw


def _mm(value: str) -> int:
    number = Decimal(str(value)) * 1000
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError("EXACT_MM_SOURCE_REQUIRED")
    return int(number)


def load_sources(repo: Path, archive: Path) -> tuple[dict[str, Any], dict[str, str]]:
    frozen = repo / "docs/previews/v2.2.2/r11-functional-room-fit-r1"
    manifest = json.loads((frozen / "source-manifest.json").read_bytes())
    raw = _read_checked(frozen / "review-data.json", manifest["derived_files"]["review-data.json"])
    review = json.loads(raw)
    owner_path = (
        repo
        / "docs/previews/v2.2.2/owner-functional-input-contract-r2/owner-confirmed-business-rules-v2.json"
    )
    fact_path = repo / "docs/tasks/V2_2_2-r11-r3-reviewed-project-fact.txt"
    catalog = build_r3_catalog(review, owner_path.read_bytes(), fact_path.read_bytes())
    sources = {
        str(frozen / "review-data.json"): hashlib.sha256(raw).hexdigest(),
        str(owner_path): hashlib.sha256(owner_path.read_bytes()).hexdigest(),
        str(fact_path): hashlib.sha256(fact_path.read_bytes()).hexdigest(),
    }
    for group in catalog["groups"]:
        room = group["room"]
        group["record_access_readbacks"] = []
        for alias in group["aliases"]:
            relative = alias["geometry_reference"].removeprefix("sealed-r10:").split("#", 1)[0]
            path = (archive / relative).resolve()
            if not path.is_relative_to(archive.resolve()):
                raise ValueError("SEALED_CANDIDATE_PATH_REQUIRED")
            candidate = json.loads(_read_checked(path, alias["candidate_sha256"]))
            sources[str(path)] = alias["candidate_sha256"]
            routes = [
                r
                for r in candidate["engineering_validation"]["access_results"]
                if r.get("from_ref") == "changing_room" or r.get("to_ref") == "changing_room"
            ]
            if len(routes) != 2 or any(r["status"] != "PASS" for r in routes):
                raise ValueError("ORIGINAL_TWO_ACCESS_PASSES_REQUIRED")
            x, y = room["world_bounds_mm"][:2]
            actual_portals = {}
            for route in routes:
                for p in (route.get("portal_from"), route.get("portal_to")):
                    if p and p["access_ref"] == "changing_room":
                        if p["status"] != "VALID":
                            raise ValueError("ORIGINAL_CHANGING_PORTAL_NOT_VALID")
                        points = [p["segment"][key] for key in ("start", "end")]
                        actual_portals[p["identity"]] = (
                            sorted([[_mm(v["x"]) - x, _mm(v["y"]) - y] for v in points]),
                            _mm(p["clear_width_m"]),
                        )
            expected_portals = {
                p["id"]: (sorted(p["segment_mm"]), p["clear_width_mm"]) for p in room["portals"]
            }
            if actual_portals != expected_portals:
                raise ValueError("ARCHIVED_RECORD_PORTALS_DIFFER_FROM_R11_ROOM")
            group["record_access_readbacks"].append(
                dict(
                    record=alias["record"],
                    candidate_hash=alias["candidate_hash"],
                    source_sha256=alias["candidate_sha256"],
                    two_access_passes=True,
                    portal_geometry_matches=True,
                    access_results=routes,
                )
            )
            if alias != group["aliases"][0]:
                continue
            group["external_routes"] = [
                dict(
                    requirement=r["requirement_identity"],
                    status=r["status"],
                    source_reference=str(path) + "#/engineering_validation/access_results",
                    route_length_m=r["route_length_m"],
                    turn_count=r["turn_count"],
                    clear_width_m=r["clear_width_m"],
                    local_centerline_mm=[
                        [_mm(p["x"]) - x, _mm(p["y"]) - y] for p in r["centerline"]
                    ],
                )
                for r in routes
            ]
    return catalog, sources


def write_review(repo: Path, archive: Path, output: Path) -> tuple[dict[str, Any], str]:
    if output.exists() or output.resolve().is_relative_to(archive.resolve()):
        raise ValueError("NEW_OUTPUT_OUTSIDE_SEALED_ARCHIVE_REQUIRED")
    catalog, sources = load_sources(repo, archive)
    output.mkdir(parents=True, exist_ok=False)
    presets = {}
    for group in catalog["groups"]:
        for mode in ("SINGLE_SIDE", "DOUBLE_SIDE"):
            result = hypothetical_review(
                catalog, group["group"], HypotheticalLockerParameters(arrangement=mode)
            )
            presets[group["group"] + ":" + mode] = response(result)
    for name, data in (
        ("project-and-room-catalog.json", catalog),
        ("hypothetical-screening.json", presets),
    ):
        (output / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2 if name.startswith("project-") else None)
            + "\n"
        )
    # Read persisted calculations before producing report text, tables and SVGs.
    catalog = json.loads((output / "project-and-room-catalog.json").read_bytes())
    presets = json.loads((output / "hypothetical-screening.json").read_bytes())
    conditional = presets["G01:DOUBLE_SIDE"]["result"]["conditional_simulation"]
    (output / "h5-staggered-simulation.json").write_text(
        json.dumps(conditional, ensure_ascii=False) + "\n"
    )
    readbacks = [a for group in catalog["groups"] for a in group["record_access_readbacks"]]
    (output / "record-access-readbacks.json").write_text(
        json.dumps(readbacks, ensure_ascii=False, indent=2) + "\n"
    )
    unequal = []
    for first in (53, 90, 1):
        result = hypothetical_review(
            catalog, "G01", HypotheticalLockerParameters(first_row_count=first)
        )
        unequal.append(
            dict(
                first_row_count=first,
                second_row_count=catalog["design_counts"]["locker_count"] - first,
                required_length_mm=result["screening"]["required_length_mm"],
                status=result["screening"]["necessary_condition_status"],
                source_label="HYPOTHETICAL_NOT_APPROVED",
            )
        )
    (output / "unequal-row-checks.json").write_text(
        json.dumps(unequal, ensure_ascii=False, indent=2) + "\n"
    )
    page = render_page(catalog, presets)
    (output / "index.html").write_text(page)
    design = catalog["design_counts"]
    h5 = presets["G01:DOUBLE_SIDE"]["result"]["screening"]
    lines = [
        "# R11 R3 · 106柜功能布置评审",
        "",
        f"项目确认：包装成品{design['packaged_mass_kg_per_day']}kg/天；原Owner V2默认均分。各班质量{design['shift_mass_kg']}kg、设计人数{design['shift_workers']}；独立柜{design['locker_count']}、同时更衣{design['simultaneous_users']}人、包装台{design['packing_tables']}。全部为设计计算值，不是实际人员名册。",
        "",
        "8组真实物理矩形来自9份原记录。原门洞和外部路线只读回读；历史P1、工程有效性、九/十二指标与资源记录不变。",
        "",
        "所有真实房间功能结论仍为 INPUT_REQUIRED。柜型、完成面、内部通行、门扇、操作、座凳与清洁分隔均尚未审定。以下参数仅为 HYPOTHETICAL_NOT_APPROVED，不写入Authority；指定模板失败不代表其他模板不可行。",
        "",
        "假设：柜400×500×1800mm；通道1200mm；柜前操作600mm；人员空间400×600mm；无座凳、完成面内缩0（并非确认完成面）。",
        "",
        "|组|记录|Handoff|矩形mm|单侧理想上界|双侧剩余宽mm|双侧基本必要条件|真实功能结论|",
        "|---|---|---|---|---|---|---|---|",
    ]
    for group in catalog["groups"]:
        key = group["group"]
        single = presets[key + ":SINGLE_SIDE"]["result"]["screening"]
        double = presets[key + ":DOUBLE_SIDE"]["result"]["screening"]
        b = group["room"]["local_bounds_mm"]
        lines.append(
            f"|{key}|{'/'.join(group['records'])}|H{group['handoff']}|{b[2]}×{b[3]}|{single['ideal_single_side_capacity']}|{double['ideal_remaining_aisle_mm']}|{double['necessary_condition_status']}|INPUT_REQUIRED|"
        )
        for mode in ("SINGLE_SIDE", "DOUBLE_SIDE"):
            data = presets[key + ":" + mode]
            (output / (key + "-" + mode.lower() + ".svg")).write_text(data["svg"])
    lines += [
        "",
        "H6单侧理想上界99<106；实际扣除门洞缺口、端部或装修后更少。双侧两柜深1000mm后只剩8–15mm，低于假设净通道1200mm。",
        "",
        f"H5双侧基本所需{h5['required_length_mm']}×{h5['required_width_mm']}mm，外包矩形{h5['available_length_mm']}×{h5['available_width_mm']}mm，故仅通过必要条件。当前假设两侧独立柜前操作区加净通道所需宽{h5['operation_width_required_mm']}mm，超过现有宽度；这是指定模板失败，不是所有模板无解。实际两门的净通行、人员、座凳及四状态仍需完整已审见证。",
        "",
        "完整已审输入由可信应用提供BasisValue后，evaluate_reviewed_locker_witness调用原R11校核器。页面参数不是审阅入口；假设预览永远不产生正式CONDITIONAL_FIT。零Native、MAIN、Grant/Claim。",
    ]
    lines += [
        "",
        "## 两班独立证明与净通行修正",
        "",
        "R3要求分别提交shift_witnesses[1]与[2]，各班53人必须与本班53柜一一关联并位于对应柜体操作面。两班固定柜体/座凳位置一致。原R11四状态先校核，再由R3排除人员、门扇、其他功能占用及当前活动柜门操作区侵占净AISLE或路线包络；未知柜门运动或另一排关闭条件不得默认通过。",
        "",
        "经审阅的r3_shift_operation_plan须逐班、逐状态声明活动柜、未用柜关闭依据及柜门排除范围。人员可使用自己的操作区，但不能占用另一用户的活动操作区；缺少任一班或任一状态的完整证据不能CONDITIONAL_FIT。",
        "",
        "## H5错峰条件模拟（不是实际项目批准）",
        "",
        f"模拟状态：{conditional['simulation_status']}。仍假设无侵入式柜门、房门无门扇、净高4000mm、无座凳、无需洁污分隔及完成面零内缩；这些均未确认。",
    ]
    for shift, case in conditional.get("shifts", {}).items():
        proof = case["r3"]
        use = proof["state_results"].get("USE", {})
        lines.append(
            f"- 班次{shift}：原R11={case['original_r11']['functional_status']}，R3={proof['status']}，记录使用人位={use.get('people_count', 'NOT_EVALUATED')}，内部路线中心y={case['route_center_y_mm']}mm，门洞证明={use.get('proven_portal_ids', [])}。"
        )
        (output / f"G01-shift-{shift}-staggered.svg").write_text(
            presets["G01:DOUBLE_SIDE"]["shift_svgs"][shift]
        )
    lines += [
        "",
        "错峰时，仅当前班操作区保持活动，已明确假设关闭的另一班柜前地面可用于净通行。此条件下两班可以采用不同内部通道；并非要求106人同时使用，也不能把原3400mm同时双排操作模板的失败推广到所有安排。实际柜门机制、房门开启、净完成面、净宽、座凳和洁污条件仍缺失，8组真实房间均INPUT_REQUIRED。",
        "",
        "## 不均等柜排",
        "",
        "双侧理想必要长度=max(n1,N-n1)×柜宽；均分53/53只是特例。实际Portal分段容量另行检查，不能由总长公式替代。",
    ]
    lines += [
        f"- 假设柜排{r['first_row_count']}/{r['second_row_count']}：理想必要长度{r['required_length_mm']}mm，H5基础状态{r['status']}。"
        for r in unequal
    ]
    lines += ["", "## P01与P02分别回读", ""]
    lines += [
        f"- {r['record']}：源SHA={r['source_sha256']}；两条原Access均PASS={r['two_access_passes']}；原Portal坐标和净宽匹配={r['portal_geometry_matches']}。"
        for r in readbacks
        if r["record"] in {"P01", "P02"}
    ]
    (output / "results.md").write_text("\n".join(lines) + "\n")
    digests = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()
    }
    (output / "source-manifest.json").write_text(
        json.dumps(dict(source_files=sources, derived_files=digests), indent=2) + "\n"
    )
    return catalog, page


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=52987)
    args = parser.parse_args()

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("R11_R3_NATIVE_SOLVE_FORBIDDEN")

    for method in ("solve", "Solve"):
        setattr(cp_model.CpSolver, method, forbidden)
    repo = Path(__file__).resolve().parents[2]
    if args.serve and args.output.exists():
        manifest = json.loads((args.output / "source-manifest.json").read_bytes())
        for name, sha in manifest["derived_files"].items():
            _read_checked(args.output / name, sha)
        catalog = json.loads((args.output / "project-and-room-catalog.json").read_bytes())
        # Fresh application review of the frozen Owner fact; never approve cached labels.
        frozen = repo / "docs/previews/v2.2.2/r11-functional-room-fit-r1"
        frozen_manifest = json.loads((frozen / "source-manifest.json").read_bytes())
        review = json.loads(
            _read_checked(
                frozen / "review-data.json", frozen_manifest["derived_files"]["review-data.json"]
            )
        )
        current = build_r3_catalog(
            review,
            (
                repo
                / "docs/previews/v2.2.2/owner-functional-input-contract-r2/owner-confirmed-business-rules-v2.json"
            ).read_bytes(),
            (repo / "docs/tasks/V2_2_2-r11-r3-reviewed-project-fact.txt").read_bytes(),
        )
        if current["project_binding"] != catalog["project_binding"]:
            raise ValueError("CURRENT_REVIEWED_PROJECT_BASIS_REQUIRED")
        for expected, saved in zip(current["groups"], catalog["groups"], strict=True):
            if expected != {
                k: v
                for k, v in saved.items()
                if k not in {"external_routes", "record_access_readbacks"}
            }:
                raise ValueError("SEALED_ROOM_OR_PORTAL_CHANGED")
        page = (args.output / "index.html").read_text()
    else:
        if args.raw_archive is None:
            parser.error("--raw-archive required for new read-only report")
        catalog, page = write_review(repo, args.raw_archive, args.output)
    print(
        json.dumps(
            dict(records=9, physical_groups=8, design=catalog["design_counts"], native_solves=0)
        ),
        flush=True,
    )
    if args.serve:
        serve_review(catalog, page, args.port)


if __name__ == "__main__":
    main()
