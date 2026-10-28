# ruff: noqa: E501 -- persisted engineering report text
"""R8 read-only sources, deterministic functional evidence, no Native APIs."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.cabinet_front_review import (
    SOURCE_PATH,
    TASK,
    comparison_cases,
)
from cold_storage.modules.layout.infrastructure.cabinet_front_page import page, plan_svg

BASE = "214bd1acabee79031823e6fc05ad3548a1c8b73c"


def forbidden(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("R11_R8_NATIVE_FORBIDDEN")


def write_review(root: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("NEW_R8_OUTPUT_DIRECTORY_REQUIRED")
    cp_model.CpSolver.solve = forbidden
    cp_model.CpSolver.Solve = forbidden
    source = root / "docs/previews/v2.2.2/r11-r5-h5-practical-changing-review-r1"
    cat = source / "project-and-room-catalog.json"
    manifest = source / "source-manifest.json"
    raw = cat.read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != json.loads(manifest.read_bytes())["derived_files"][cat.name]
    ):
        raise ValueError("FROZEN_CATALOG_SOURCE_MISMATCH")
    r7path = root / "docs/tasks/V2_2_2-r11-r7-reviewed-standing-project-facts.txt"
    r8path = root / SOURCE_PATH
    cases = comparison_cases(json.loads(raw), r7path.read_bytes(), r8path.read_bytes())
    output.mkdir(parents=True, exist_ok=False)
    packed = output / "cabinet-front-results.json.gz"
    packed.write_bytes(
        gzip.compress(
            json.dumps(cases, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0
        )
    )
    # Every presentation reads the persisted result, never re-evaluates the formulas.
    cases = json.loads(gzip.decompress(packed.read_bytes()))
    selected = list(cases.values())[6]
    (output / "project-binding.json").write_text(
        json.dumps(selected["binding"], ensure_ascii=False, indent=2) + "\n"
    )
    (output / "index.html").write_text(page(cases))
    comparison = []
    for i, (label, c) in enumerate(cases.items(), 1):
        comparison.append(
            dict(
                label=label,
                parameters=c["geometry"]["front_parameters"],
                metrics=c["geometry"]["metrics"],
                schedule_summary=[
                    dict(
                        shift=d["shift"],
                        status=d["status"],
                        checks=d["checks"],
                        remaining_users=d["remaining_users"],
                        rejected_group_count=len(d["rejected_groups"]),
                    )
                    for d in c["geometry"]["schedule_diagnostics"]
                ],
                shifts=[
                    {
                        k: s[k]
                        for k in (
                            "shift",
                            "status",
                            "completed_users",
                            "requested_concurrency",
                            "actual_peak_concurrency",
                            "concurrency_histogram",
                            "expected_batches",
                            "completed_batches",
                            "full_shift_seconds",
                            "full_shift_minutes",
                            "total_route_m",
                            "wall_walking_seconds",
                            "wall_parallel_action_seconds",
                            "max_completed_person_waiting_seconds",
                        )
                    }
                    | dict(
                        blocker=None
                        if s["blocker"] is None
                        else dict(
                            operation=s["blocker"]["operation"],
                            conflict_codes=sorted(
                                {q["code"] for q in s["blocker"].get("conflicts", [])}
                            ),
                            conflict_count=len(s["blocker"].get("conflicts", [])),
                        )
                    )
                    for s in c["shifts"]
                ],
            )
        )
        for shift in (1, 2):
            (output / f"case-{i:02}-shift-{shift}.svg").write_text(plan_svg(c, shift))
    (output / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "h5-cabinet-front-plan.svg").write_text(plan_svg(selected))
    (output / "h5-cabinet-front-detail.svg").write_text(plan_svg(selected, detail=True))
    rows = [
        "# R11 R8 H5 本人柜前站立更衣",
        "",
        "## 结论与Owner事实",
        "",
        "Owner已确认本人柜前直接站立更衣、无坐凳、无独立更衣操作区。使用原ReviewedProjectDatum模式，核对封存目录、原R7来源和本任务已审Owner来源及项目Scope后绑定；普通JSON标签不构成审批。R7分散更衣保留为历史对照，不再作为本项目主推荐。",
        "本轮在原H5矩形和两处1500mm Portal内，使用原柜组和1200mm假设通道，已实际找到420×700mm及600×900mm活动包络下2、3、4、5人的完整条件流程：两班各53人均完成进入、本人柜前开柜/取衣、关柜、更衣、再开柜存放、关柜和南门离室。设计基准没有减少，22列110格不变。",
        "这是对当前有限模板的条件见证，不是最大并发或最短时间证明，更不是实际功能合格。所有实际功能继续INPUT_REQUIRED。",
        "",
        "## 实际分组、完整流程与时间",
        "",
        "|方案|本位/53|完成各班|实际峰值并发|条件分钟各班|步行墙钟秒各班|并行动作墙钟秒各班|首个阻塞|",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in comparison:
        ss = c["shifts"]
        rows.append(
            f"|{c['label']}|{c['metrics']['home_count']}|{[s['completed_users'] for s in ss]}|{[s['actual_peak_concurrency'] for s in ss]}|{[None if s['full_shift_minutes'] is None else round(s['full_shift_minutes'], 2) for s in ss]}|{[None if s['wall_walking_seconds'] is None else round(s['wall_walking_seconds'], 2) for s in ss]}|{[s['wall_parallel_action_seconds'] for s in ss]}|{[None if s['blocker'] is None else s['blocker']['operation'] for s in ss]}|"
        )
    rows += (
        [
            "",
            "## 为什么间隔柜列有效",
            "",
            "以600×900mm、请求4人方案为默认评审视图。策略先按已服务次数和柜列实际x位置确定待用柜格，枚举与活动宽度相容的组合；完整原门扇、通道、Portal、53人和活动范围校核通过后才采纳。两人同列不允许同时操作；没有把连续柜列强行作为并发组，也没有用组图的无冲突代替完整实际流程。",
            "分组不改变柜体、房间或Portal。每个批次保留实际人员ID、柜格/列关联、列间距、活动体积及原验收结果。每名在室者有实际位置；活动组去柜前时其等候本位才变为空，不提前删除该人。其他人保持实际位置作为碰撞障碍，所有移动段按原通道中心线和连续身体扫掠检查。完成存放、关柜和离室后才扣减在室人数。",
            "同一柜组下，连续柜列负面对照保留全53人的入室和开柜取衣过程，在更衣包络重叠时停止。间隔组的成功与其采用同一物理几何，区别来自分组；没有靠缩小身体取得通过。",
            "原柜列相邻x间距存在400/420mm，600mm宽活动范围不能在这些相邻位置同时展开。间隔柜列的实际间距由每批front_group_spaces给出，选中组必须不少于所需活动宽度。本模板柜前关门可用深度实测980mm，900mm包络有80mm模板余量；这是当前假设柜型和站位的计算，不是获批净距。1100mm包络在同一位置侵入柜体，保留确切碰撞体积。",
            "策略是有限确定性组合与完整校核，不是全局最优调度。420与600mm活动宽度可能选到不同组序和尾组，不能因某次较大包络组数更少，就声称大包络提高效率。请求并发与实际峰值、每组人数直方图分别记录；尾组不足请求人数不会伪报满额并发。",
            "",
            "## 柜门与真实工艺边界",
            "",
            "每人两次开柜均校核原完整三维门扇扫掠、柜门投影净通道和实际其他在室者。每次开门、取/放、关门期间无人换位，故同一位置及门扇证明可复用；更衣后第二次开柜仍重新校核。主协议更衣时柜门关闭；若保持柜门打开，另存独立几何负面对照，600×900mm包络会与柜门扫掠冲突，不把其计作通过流程。两次开柜顺序、关门更衣操作规范和五层格口取物能力均待实际工艺确认。",
            "",
            "## 时间、通行与串行等待",
            "",
            "假设步速600mm/s；开门3s、取衣20s、关门3s、更衣90s、再开门3s、存放20s、关门3s。source_type=demo，validity_status=unverified，requires_review=true。每组共享同一操作时间窗口；实际行走仍逐人串行，不能把并发人数除入步行时间。",
            "完整条件墙钟时间=实际串行通行时间+各组并行动作时间。个人在室时长从本人开始穿越东入口至通过南门计算，另分本人行走、本人操作和串行等待；个人等待总和不能当作班次墙钟时间。外部到达队列与包装间后续消纳能力未重新验证。缺少时间输入时完整时长与个人等待为空，不能宣称吞吐满足。失败只保留已执行前缀，不用较短前缀路径冒充效率提升。",
            "R7旧报告使用不同的单次取放假设，不能把R8新增两次开柜程序与其时间直接作为同口径提速率。R8连续柜列对照与间隔柜列采用相同输入、尺寸和完整工序。",
            "",
            "## 空间不足及调整方向",
            "",
            "450×650mm运输身体与100mm等候间隔，在当前两排本位模板仅排下47人；单列实体柜加200mm柜间距拉长柜列、把等候起点推向东侧，只排下46人。两者均拒绝全班流程，不降低53人、不占用净通道，也不宣布H5所有替代组织均不可行。",
            "优先在现有柜组上审阅间隔柜列错峰，而非盲目增加所有柜间距。若批准的人体/等候空间使本模板不足，应重新设计柜组与等候本位、通道转折和门前缓冲的整体关系，复核53个实际位置及两Portal；必要时再由工程Authority决定建筑条件调整。本轮没有证明另一种重排能容纳放大后的全部53人，不能凭几何直觉宣称可行。",
            "",
            "## 尚缺真实输入",
            "",
        ]
        + ["- " + m for m in selected["binding"]["missing_inputs"]]
        + [
            "",
            "## 文件与验证边界",
            "",
            "index.html展示全部方案、两班、所有批次、柜门/活动冲突、人员路线与个人等待表；柜区放大只裁切相同真实比例几何。cabinet-front-results.json.gz保存全部原始轨迹、分组、每次校核与时间；comparison.json提供完整对照。未形成流程的图纸明确只是模板/冲突图，不冒充有效工程方案。",
            "R1-R7代码、报告和工程状态不改；P1、Stage B、九/十二指标及生产默认不改。两种Native API均禁止，无MAIN、Grant/Claim、正式完整CI、Ready、Merge或Deploy。实际功能仍为INPUT_REQUIRED。",
        ]
    )
    (output / "cabinet-front-report.md").write_text("\n".join(rows) + "\n")
    originals = [
        cat,
        manifest,
        r7path,
        r8path,
        root / "docs/previews/v2.2.2/r11-r7-h5-standing-changing-review-r1/receipt.json",
    ]
    (output / "receipt.json").write_text(
        json.dumps(
            dict(
                task=TASK,
                base_head=BASE,
                current_process="PERSONAL_CABINET_FRONT_STANDING",
                full_service_users=[s["completed_users"] for s in selected["shifts"]],
                functional_status="INPUT_REQUIRED",
                native_solves=0,
                main=False,
                grant=False,
                claim=False,
                full_ci="NOT_REQUESTED",
            ),
            indent=2,
        )
        + "\n"
    )
    m = dict(
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
    (output / "source-manifest.json").write_text(json.dumps(m, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_review(Path(__file__).resolve().parents[2], args.output.resolve())
