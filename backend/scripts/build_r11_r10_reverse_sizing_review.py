# ruff: noqa: E501 -- engineering review prose
"""Generate a finite, guarded functional sizing review; never a MAIN Runner."""

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.application.cabinet_front_review import SOURCE_PATH
from cold_storage.modules.layout.application.room_reverse_sizing_review import (
    TASK,
    evaluate_sizing_point,
    input_contract,
    preview_request,
    preview_room_sizing,
    select_designs,
)
from cold_storage.modules.layout.domain.functional_room_sizing_input import (
    RoomUseConditions,
    search_points,
)
from cold_storage.modules.layout.infrastructure.room_reverse_sizing_page import (
    comparison_svg,
    page,
    plan_svg,
    plot_record,
)

BASE = "6b47d04d5835ef6a6068a15ab33b371ff94baa2c"


def guarded_reexec(audit: Path) -> int | None:
    from ortools.sat.python import cp_model

    if (
        os.environ.get("R11_FUNCTIONAL_GUARD_ACTIVE") == "1"
        and cp_model.CpSolver.solve.__module__ == "sitecustomize"
        and cp_model.CpSolver.Solve.__module__ == "sitecustomize"
    ):
        return None
    backend = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["R11_FUNCTIONAL_GUARD_AUDIT"] = str(audit.resolve())
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(backend / "tests/functional_native_guard"),
            str(backend / "src"),
            str(backend / "scripts"),
        ]
    )
    return subprocess.run([sys.executable, *sys.argv], env=env, check=False).returncode


def sources(root: Path) -> tuple[dict[str, Any], bytes, bytes, list[Path]]:
    old = root / "docs/previews/v2.2.2/r11-r9-h5-space-relayout-r1"
    manifest = json.loads((old / "source-manifest.json").read_bytes())
    for name, sha in manifest["derived_files"].items():
        if hashlib.sha256((old / name).read_bytes()).hexdigest() != sha:
            raise ValueError("R9_ARCHIVE_MODIFIED:" + name)
    cat = (
        root
        / "docs/previews/v2.2.2/r11-r5-h5-practical-changing-review-r1/project-and-room-catalog.json"
    )
    cm = cat.parent / "source-manifest.json"
    if (
        hashlib.sha256(cat.read_bytes()).hexdigest()
        != json.loads(cm.read_bytes())["derived_files"][cat.name]
    ):
        raise ValueError("FROZEN_ROOM_CATALOG_MODIFIED")
    r7 = root / "docs/tasks/V2_2_2-r11-r7-reviewed-standing-project-facts.txt"
    r8 = root / SOURCE_PATH
    return (
        json.loads(cat.read_bytes()),
        r7.read_bytes(),
        r8.read_bytes(),
        [
            cat,
            cm,
            r7,
            r8,
            old / "source-manifest.json",
            old / "relayout-results.json.gz",
            old / "execution-boundary-exception.md",
            old / "interrupted-legacy-regression.xml",
        ],
    )


def write_review(
    root: Path, output: Path, request: dict[str, Any], computed: Path | None = None
) -> None:
    if output.exists():
        raise ValueError("NEW_R10_OUTPUT_DIRECTORY_REQUIRED")
    catalog, r7, r8, originals = sources(root)
    c, search = preview_request(request)
    output.mkdir(parents=True, exist_ok=False)
    archive = output / "evaluation-grid.jsonl.gz"
    if computed:
        result = json.loads((computed / "sizing-preview.json").read_bytes())
        if result["conditions"] != asdict(c) or json.dumps(
            result["search"], sort_keys=True
        ) != json.dumps(asdict(search), sort_keys=True):
            raise ValueError("COMPUTED_REQUEST_MISMATCH")
        shutil.copyfile(computed / "evaluation-grid.jsonl.gz", archive)
    else:
        with gzip.GzipFile(filename=str(archive), mode="wb", mtime=0) as stream:

            def save(case: dict[str, Any]) -> None:
                stream.write(
                    json.dumps(case, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
                )

            result = preview_room_sizing(catalog, r7, r8, c, search, evidence_sink=save)
    expected = search_points(c, search)
    if [r["point"] for r in result["candidates"]] != expected:
        raise ValueError("FINITE_COLLECTION_MISMATCH")
    result["input_contract"] = input_contract(catalog, c)
    result["designs"] = select_designs(result["candidates"], search.change_review_target_mm)
    result["minimum_area_scope"] = (
        "Finite verified set only; smaller/unlisted dimensions not proven infeasible"
    )
    plots: dict[str, Any] = {}
    selected: dict[str, Any] = {}
    count = 0
    needed = {
        v
        for k, v in result["designs"].items()
        if k in {"A_MIN_VERIFIED_AREA", "B_LARGER_MARGIN", "C_MIN_BOUNDARY_CHANGE"} and v
    }
    with gzip.open(archive, "rt") as records:
        for raw in records:
            case = json.loads(raw)
            summary = case["summary"]
            payload = {k: case[k] for k in ("geometry", "shifts", "margins")}
            digest = hashlib.sha256(
                json.dumps(
                    payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            ).hexdigest()
            if digest != summary["witness_sha256"] or summary != result["candidates"][count]:
                raise ValueError("CALCULATION_EVIDENCE_CONTRADICTION")
            plots[summary["id"]] = plot_record(case)
            if summary["id"] in needed:
                selected[summary["id"]] = case
            count += 1
    if count != len(expected) or set(selected) != needed:
        raise ValueError("MISSING_CALCULATION_EVIDENCE")
    # Re-evaluate selected designs using current immutable inputs, never trust a cached PASS label.
    source = next(r for r in catalog["groups"] if r["group"] == "G01")
    for case in selected.values():
        checked = evaluate_sizing_point(
            source["room"], catalog["demands"]["INTERNAL_PARTITION"], c, case["summary"]["point"]
        )
        if checked["summary"]["witness_sha256"] != case["summary"]["witness_sha256"]:
            raise ValueError("SELECTED_WITNESS_NOT_REPRODUCED")
    sensitivities = []
    for case in selected.values():
        for label, conditions in (
            ("finish30", replace(c, finish_mm=30)),
            ("install40", replace(c, installation_gap_mm=40)),
            ("finish30_install40", replace(c, finish_mm=30, installation_gap_mm=40)),
        ):
            proof = evaluate_sizing_point(
                source["room"],
                catalog["demands"]["INTERNAL_PARTITION"],
                conditions,
                case["summary"]["point"],
            )
            sensitivities.append(dict(label=label, conditions=asdict(conditions), case=proof))
    # Find a width-only design robust to the declared combined finish/install sensitivity.
    robust = None
    robustness_trials = []
    choices = sorted(
        (
            r
            for r in result["candidates"]
            if r["full_flow_verified"]
            and r["minimum_margin_mm"] >= search.change_review_target_mm
            and r["length_delta_mm"] == 0
        ),
        key=lambda r: (r["area_mm2"], r["id"]),
    )
    for row in choices:
        proof = evaluate_sizing_point(
            source["room"],
            catalog["demands"]["INTERNAL_PARTITION"],
            replace(c, finish_mm=30, installation_gap_mm=40),
            row["point"],
        )
        robustness_trials.append(proof)
        if (
            proof["summary"]["full_flow_verified"]
            and proof["summary"]["minimum_margin_mm"] >= search.change_review_target_mm
        ):
            robust = proof
            break
    result["robust_width_only_review"] = robust["summary"] if robust else None
    result["robustness_review_target_mm"] = search.change_review_target_mm
    result["robustness_trial_summaries"] = [r["summary"] for r in robustness_trials]
    if robust:
        selected[robust["summary"]["id"] + "-SENSITIVITY"] = robust
        plots[robust["summary"]["id"] + "-SENSITIVITY"] = plot_record(robust)
    old = root / "docs/previews/v2.2.2/r11-r9-h5-space-relayout-r1"
    archived = json.loads(gzip.decompress((old / "relayout-results.json.gz").read_bytes()))
    references = [
        dict(
            label=label,
            north_margin_mm=case["geometry"]["metrics"].get("north_strip_margin_mm"),
            home_count=case["geometry"]["metrics"]["home_count"],
            completed_users=[s["completed_users"] for s in case["shifts"]],
            original_statuses=[s["status"] for s in case["shifts"]],
            source="ARCHIVED_R9_READ_ONLY",
        )
        for label, case in archived.items()
    ]
    r9a = next(iter(archived.values()))["geometry"]
    anew = selected[result["designs"]["A_MIN_VERIFIED_AREA"]]["geometry"]
    if (
        c == RoomUseConditions()
        and anew["point"]
        == dict(length_mm=26331, width_mm=3250, margin_mm=0, profile="MIXED", mode="A_FIXED_LENGTH")
        and (
            [h["bounds_mm"] for h in anew["model"]["homes"]]
            != [h["bounds_mm"] for h in r9a["model"]["homes"]]
            or anew["inventory"] != r9a["inventory"]
        )
    ):
        raise ValueError("R9_BASELINE_GEOMETRY_NOT_REPRODUCED")
    (output / "r9-reference-and-sensitivity.json").write_text(
        json.dumps(
            dict(
                r9_references=references,
                robustness_review_target_mm=search.change_review_target_mm,
                robustness_trials=[
                    dict(summary=r["summary"], margins=r["margins"]) for r in robustness_trials
                ],
                sensitivities=[
                    dict(
                        label=s["label"],
                        conditions=s["conditions"],
                        summary=s["case"]["summary"],
                        margins=s["case"]["margins"],
                    )
                    for s in sensitivities
                ],
                robust_width_only=robust["summary"] if robust else None,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    with gzip.GzipFile(
        filename=str(output / "sensitivity-evidence.jsonl.gz"), mode="wb", mtime=0
    ) as stream:
        for s in sensitivities:
            stream.write(json.dumps(s, ensure_ascii=False, separators=(",", ":")).encode() + b"\n")
    with gzip.GzipFile(
        filename=str(output / "robustness-evidence.jsonl.gz"), mode="wb", mtime=0
    ) as stream:
        for proof in robustness_trials:
            stream.write(
                json.dumps(proof, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
            )
    (output / "selected-evidence.json.gz").write_bytes(
        gzip.compress(
            json.dumps(selected, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0
        )
    )
    (output / "sizing-preview.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "plot-data.json.gz").write_bytes(
        gzip.compress(
            json.dumps(plots, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0
        )
    )
    # Extra sensitivity plot is not a member of the original grid; keep its page entry explicit.
    page_result = json.loads(json.dumps(result))
    if robust:
        page_result["candidates"].append(
            dict(robust["summary"], id=robust["summary"]["id"] + "-SENSITIVITY")
        )
    (output / "index.html").write_text(page(page_result, plots))
    panels = {}
    for key, name in (
        ("A_MIN_VERIFIED_AREA", "A_min_verified_area"),
        ("B_LARGER_MARGIN", "B_larger_margin"),
        ("C_MIN_BOUNDARY_CHANGE", "C_less_building_change"),
    ):
        cid = result["designs"][key]
        if cid:
            plot = plots[cid]
            (output / (name + ".svg")).write_text(plan_svg(plot))
            (output / (name + "-detail.svg")).write_text(plan_svg(plot, detail=True))
            panels[name] = plot
    (output / "design-comparison.svg").write_text(comparison_svg(panels))
    if robust:
        (output / "width-only-robust-sensitivity.svg").write_text(plan_svg(plot_record(robust)))
    report = [
        "# R11 R10 功能房间尺寸反推",
        "",
        "TASK_ID=" + TASK,
        "BASE_HEAD=" + BASE,
        "",
        "本次为有限功能预览，不写入P1/Stage B/Authority。R9三套原件、10mm北侧余量、30mm完成面失败和Native越界异常原件均保留。R10新增计算与本地白名单不执行Native；继承快速CI中原有的合成Native测试另行识别，不报告任务级总Native为零。",
        "",
        f"共检查{len(result['candidates'])}个有限组合；{sum(r['full_flow_verified'] for r in result['candidates'])}个取得两班各53人的完整条件流程，{sum(r['margin_target_met'] for r in result['candidates'])}个同时达到其假设余量目标。",
        "",
        "| 目标 | 长×宽mm | 面积㎡ | 新增㎡ | 最小已定义空间余量mm | 北侧余量mm | 完成各班 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key in ("A_MIN_VERIFIED_AREA", "B_LARGER_MARGIN", "C_MIN_BOUNDARY_CHANGE"):
        cid = result["designs"][key]
        if not cid:
            report.append(f"| {key} | 无完整见证 | | | | | |")
            continue
        r = next(r for r in result["candidates"] if r["id"] == cid)
        report.append(
            f"| {key} | {r['point']['length_mm']}×{r['point']['width_mm']} | {r['area_m2']} | {r['added_area_m2']} | {r['minimum_margin_mm']} | {r['north_wall_margin_mm']} | {r['completed_users']} |"
        )
    report += [
        "",
        "## 结论与范围",
        "",
        "A命中本次范围下边界，保留原H5完整条件见证；其0mm最小额外余量和10mm北带仅作面积对照，不作为舒适/稳健推荐。没有测试更小长宽，不能把85.575750㎡称为项目必要面积或全局最小面积。P01/P02只计一个物理房间。原40㎡P1需求及其来源不变。",
        "B按所声明空间余量族的最不利值择优，面积仅用于同余量时打破平局；C在达到可配置50mm假设评审目标的完整见证中，最小化|Δ长|+|Δ宽|。这些比较不改原九/十二指标，也不属于Stage B正式Pareto。",
        "",
        "## 尺寸链与真实局部余量",
        "",
        "每候选从实际柜体、人体、本位、通道、门洞和完整移动/门扇记录计算余量，不从总面积推断。分列安装退让、柜组间距、柜前活动到通道/柜体、本位墙距/净距/通道、通道净宽、门洞总宽余量、真实转身扫掠与其他对象的连续距离。完整位置和最不利bounds_mm均在evaluation-grid.jsonl.gz及结构化结果中。",
        "0/50/100/150mm是本轮未批准的设计余量目标。试算模板将目标分别加到安装/柜组间距、柜前站距、柜前到通道、实际通道宽度及本位间隙；每项实际余量重新测量，不能由输入目标自动判PASS。门洞宽度余量是总净宽差；单侧门框余量另列。转向使用原R9的完整对角方形扫掠。不同余量定义不能误读为人体四周统一缓冲或规范值。人体水平/竖向可达性仍沿用旧条件检查，单独显示，未获实际人体工学批准。",
        "",
        "## 长度、宽度与模板自由度",
        "",
        "固定长度模式覆盖3250、3300、3350、3400、3440、3460、3500、3600mm，并按尺寸链补充必要检查点；联合模式含27000、28000、30000mm。除R9式混合本位、北侧转向/南侧常规外，加入北侧常规/南侧转向模板，避免把旧单一布置当作全局硬约束。3440mm只有特定模板的截面意义；其完整流程与余量另行验收。只有长度变化的方案也实际进入检查，不预设只能加宽。",
        "",
        "| 边界调整类别 | 达到假设50mm目标的最少变化已验证方案 | 面积㎡ |",
        "|---|---|---:|",
    ]
    for label, accept in (
        ("仅加宽", lambda r: r["length_delta_mm"] == 0 and r["width_delta_mm"] > 0),
        ("仅加长", lambda r: r["length_delta_mm"] > 0 and r["width_delta_mm"] == 0),
        ("长宽联合", lambda r: r["length_delta_mm"] > 0 and r["width_delta_mm"] > 0),
    ):
        rows = [
            r
            for r in result["candidates"]
            if r["full_flow_verified"] and r["minimum_margin_mm"] >= 50 and accept(r)
        ]
        if rows:
            r = min(
                rows,
                key=lambda r: (r["length_delta_mm"] + r["width_delta_mm"], r["area_mm2"], r["id"]),
            )
            report.append(
                f"| {label} | {r['point']['length_mm']}×{r['point']['width_mm']} | {r['area_m2']} |"
            )
        else:
            report.append(f"| {label} | 本集合未取得目标见证，不代表全局不可行 | |")
    report += [
        "",
        "## 完成面/安装敏感性与评审建议",
        "",
        "选定A/B/C分别在完成面30mm、安装间隙40mm及二者同时变化时重新做完整功能检查。它们仍是未批准敏感性条件。达到原20mm完成面的目标，不意味着完成面变化后还达到相同余量；每一新结果独立记录，不改历史PASS。",
        "",
    ]
    if robust:
        r = robust["summary"]
        report.append(
            f"额外取得仅加宽方案 {r['point']['length_mm']}×{r['point']['width_mm']}mm，在完成面30mm、安装间隙40mm的组合假设下仍完成两班各53人，最小已定义空间余量{r['minimum_margin_mm']}mm，面积{r['area_m2']}㎡。可优先将该更稳健对照与C最小改动方案、B大余量方案一起评审；不把它直接批准为实际尺寸。"
        )
    report += (
        [
            "",
            "在默认组合敏感性中，3600mm宽方案仍有两班完整流程，但HOME-23到南Portal通道的实际间距40mm，低于50mm假设目标。它说明只增加横向面积不一定消除纵向本位/门前通道的局部瓶颈。3850mm宽、采用100mm模板加量的对照取得70mm最小实际余量：达到单独的50mm稳健评审目标，但没有达到其100mm模板目标。两类目标不混报。所有尝试均保存在robustness-evidence.jsonl.gz。",
            "",
            "## Portal与工程批准",
            "",
            "反事实对象与封存H5是不同对象；西/南边界固定，北/东按候选尺寸变化。仅加宽时两处Portal数值坐标不变；加长时东Portal保持y区间、映射到新东边界，原Portal完整来源另存。任何扩展的Site、Footprint及外部Access均NOT_EVALUATED_REVALIDATION_REQUIRED；房门不侵入通道仍是待批假设。不能把内部连续通行通过提升为外部Access或整厂工程批准。",
            "每班全部53人先到实际本位，再完整经过本人柜位开柜、取衣、关柜、更衣、再开柜存放、关柜及南Portal离室。原三维门扇/人员/柜体/通道校核保留，既有R8并发分组仅作提案，每组在R10实际通道上重新验证。没有Native、旧授权、Grant/Claim或生产求解接入。",
            "",
            "## 未确认输入与接口",
            "",
        ]
        + ["- " + m for m in result["binding"]["missing_inputs"]]
        + [
            "- 实际完成面、安装公差及各余量目标。",
            "- 反事实建筑扩展和门洞映射对应的外部Site/工艺/Access批准。",
            "",
            "结构化接口：application.room_reverse_sizing_review.preview_request()/preview_room_sizing()；只接受条件参数与有限搜索范围，拒绝审批标签或Owner事实覆盖。当前完整流程适配器为H5两班53人，其他功能房间可复用输入/有限搜索/余量结构，需另加经验证的功能适配器，不宣称已支持全部房型。",
            "index.html可切换全部已计算平面和阶段结果；本地服务支持Python预览接口，浏览器不复制工程公式。完整原始证据、选定见证、敏感性与来源Hash均随报告保存。实际结果始终INPUT_REQUIRED。",
            "",
        ]
    )
    (output / "reverse-sizing-report.md").write_text("\n".join(report))
    manifest = dict(
        base_head=BASE,
        source_files={
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in originals
        },
        derived_files={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in output.iterdir()
            if p.is_file()
        },
    )
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--computed", type=Path)
    args = parser.parse_args()
    exit_code = guarded_reexec(args.output.parent / (args.output.name + "-native-guard"))
    if exit_code is not None:
        raise SystemExit(exit_code)
    write_review(
        Path(__file__).resolve().parents[2],
        args.output.resolve(),
        json.loads(args.request.read_bytes()) if args.request else {},
        args.computed,
    )
