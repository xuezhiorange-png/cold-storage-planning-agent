# ruff: noqa: E501 -- persisted engineering report text
"""New R7 report only. Frozen R5/R6 sources are read-only; both Native APIs blocked."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.standing_changing_review import (
    SOURCE_PATH,
    TASK,
    comparison_cases,
)
from cold_storage.modules.layout.infrastructure.standing_changing_page import page, plan_svg

BASE = "b1ca6be49e47d9e0c191205c7cee84ebcc269baf"


def forbidden(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("R11_R7_NATIVE_FORBIDDEN")


def write_review(root: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("NEW_R7_REVIEW_DIRECTORY_REQUIRED")
    cp_model.CpSolver.solve = forbidden
    cp_model.CpSolver.Solve = forbidden
    source_dir = root / "docs/previews/v2.2.2/r11-r5-h5-practical-changing-review-r1"
    cat_path = source_dir / "project-and-room-catalog.json"
    source_manifest = source_dir / "source-manifest.json"
    raw = cat_path.read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != json.loads(source_manifest.read_bytes())["derived_files"][cat_path.name]
    ):
        raise ValueError("FROZEN_R5_CATALOG_HASH_MISMATCH")
    owner_path = root / SOURCE_PATH
    cases = comparison_cases(json.loads(raw), owner_path.read_bytes())
    output.mkdir(parents=True, exist_ok=False)
    data_path = output / "standing-operation-results.json.gz"
    data_path.write_bytes(
        gzip.compress(
            json.dumps(cases, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0
        )
    )
    # Render only persisted deterministic results, no recalculation in HTML/report.
    cases = json.loads(gzip.decompress(data_path.read_bytes()))
    first = next(iter(cases.values()))
    (output / "project-binding.json").write_text(
        json.dumps(first["binding"], ensure_ascii=False, indent=2) + "\n"
    )
    comparisons = []
    for i, (label, c) in enumerate(cases.items(), 1):
        comparisons.append(
            dict(
                label=label,
                parameters=c["geometry"]["standing_parameters"],
                metrics=c["geometry"]["metrics"],
                shifts=[
                    {
                        k: s[k]
                        for k in (
                            "shift",
                            "status",
                            "initial_service_occupancy",
                            "completed_users",
                            "expected_batches",
                            "completed_batches",
                            "completed_batch_boundaries",
                            "full_shift_seconds",
                            "full_shift_minutes",
                            "duration_by_operation_seconds",
                            "total_route_m",
                            "personnel_route_mm",
                            "blocker",
                        )
                    }
                    for s in c["shifts"]
                ],
            )
        )
        for shift in (1, 2):
            (output / f"case-{i:02}-shift-{shift}.svg").write_text(plan_svg(c, shift))
    (output / "h5-no-bench-standing-plan.svg").write_text(plan_svg(first))
    (output / "comparison.json").write_text(
        json.dumps(comparisons, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "index.html").write_text(page(cases))
    rows = [
        "# H5 无坐凳站立更衣 R11 R7",
        "",
        "## 结论与输入边界",
        "",
        "Owner已确认本项目BENCH_COUNT=0、CHANGING_POSTURE=STANDING。通过原项目Scope、封存目录内容身份及本任务已审来源字节绑定为ReviewedProjectDatum，不接受普通JSON审批标签。不是新的Grant/Claim机制。",
        "两班各53名设计使用者、22列110格、H5 P01/P02同一26331×3250mm矩形及两处1500mm Portal不变。模拟先完成全53人进入，随后每人走完本人柜位、取放衣物、站立更衣、原南门离室。未完成者不会被提前移除。",
        "实际功能持续INPUT_REQUIRED。无坐凳的事实不批准任何具体更衣位置、人体动作尺度、柜型、通道或卫生工艺。R5/R6原报告及代码保留，旧必须坐凳流程不再用于R7。",
        "",
        "## 同条件方案结果",
        "",
        "|方案|完成各班人数|完整条件分钟 / 班|人员总行程m / 班|首个阻塞|",
        "|---|---|---|---|---|",
    ]
    for r in comparisons:
        rows.append(
            f"|{r['label']}|{[s['completed_users'] for s in r['shifts']]} / 53|{[None if s['full_shift_minutes'] is None else round(s['full_shift_minutes'], 2) for s in r['shifts']]}|{[round(s['total_route_m'], 3) for s in r['shifts']]}|{[None if s['blocker'] is None else s['blocker']['operation'] for s in r['shifts']]}|"
        )
    rows += (
        [
            "",
            "## 身体活动与并发的真正边界",
            "",
            "A条件模型：运输身体400×600mm、等候间隔20mm、站立更衣活动包络420×700mm、柜前4人。两班分别完成53人、15批及14个批次边界；无座位分配、无坐下起身或坐姿动作。分散活动位置来自本人等候位，沿通道分布，不再要求每人往返唯一800×900mm操作区。活动包络向净通道外侧展开，同时校核所有其他在室者及柜体，不移除等候人员。",
            "B柜前4人并行在420×700mm活动范围下发生邻列人员包络重叠；C改为1人可在相同假设内完成，但时间成本较大。H仅用400×600mm身体边界通过不是更衣可用性证明。不得为制造通过而把活动范围等同静态身体。",
            "F分散600×900mm包络碰到仍在室等候者，保留具体人员ID及冲突体积；G450×650mm人体加100mm间隙只排下47个本位，整班拒绝，不把设计人数降低为47。失败仅针对这些模板，不证明所有站立布置均不可行。",
            "柜门仍使用原三维扫掠与通道投影校核。取放衣物阶段并行开门，更衣和移动阶段均明确假设柜门关闭；真实房门开向、五层格口取物能力、穿脱/弯腰/转身动作及衣物体积仍待审。原Portal内侧连接保留；外部Access只作封存参考，本轮未重验外部人流能力。",
            "",
            "## 时间与路径",
            "",
            "示例时间：600mm/s步行、20s取放衣物并关门、90s站立更衣。source_type=demo、validity_status=unverified、requires_review=true。按批次同步操作计时：每个并发组20s及90s各计一次；进室、柜前换位、到分散位置和离室均按实际通行中心线及连续身体扫掠逐人计时。并发只覆盖已证明互不冲突的静止操作阶段，不假设通道并行通行。",
            "完整时长=全部成功移动路径长度/步速 + 各批取放衣物时长 + 各批站立更衣时长。每个人都保留相同组的实际开始/结束时间，未将并发人数除进步行耗时。失败后时长为空，只保留已执行前缀。没有时间输入也返回空时长，不宣称满足班次窗口。",
            "R6和R7功能程序已因Owner取消座凳而不同，条件时间不能作为同一程序的真实提速率。R7仍采用单人移动和同步批次，不能视为最优排队或现场实测。柜前并发增加并未减少同一路径的行走总距离。",
            "",
            "## 真实缺失输入",
            "",
        ]
        + ["- " + m for m in first["binding"]["missing_inputs"]]
        + [
            "",
            "## 可复核文件",
            "",
            "index.html可本地打开：切换方案、两班与全部动作，显示实时人员、柜门、活动范围、路径和失败位置。每个方案两张SVG来自实际条件计算，原始全部状态/路径/并发组/时间见standing-operation-results.json.gz。comparison.json记录8方案指标；project-binding.json保留Owner来源和Scope。",
            "无Native、MAIN、Grant/Claim、正式完整CI。P1、Stage B、九/十二指标、生产默认与历史记录不变。实际功能仍为INPUT_REQUIRED。",
        ]
    )
    (output / "standing-operation-report.md").write_text("\n".join(rows) + "\n")
    (output / "receipt.json").write_text(
        json.dumps(
            dict(
                task=TASK,
                base_head=BASE,
                bench_count=0,
                changing_posture="STANDING",
                owner_fact_binding="CONFIRMED_PROJECT_BASIS",
                full_service_users=[s["completed_users"] for s in first["shifts"]],
                full_shift_seconds=[s["full_shift_seconds"] for s in first["shifts"]],
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
    originals = [
        cat_path,
        source_manifest,
        owner_path,
        root / "docs/previews/v2.2.2/r11-r6-h5-full-operation-review-r1/receipt.json",
    ]
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
    args = parser.parse_args()
    write_review(Path(__file__).resolve().parents[2], args.output.resolve())
