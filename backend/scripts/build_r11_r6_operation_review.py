# ruff: noqa: E501 -- persisted engineering report prose
"""Read-only frozen H5 source; deterministic R6 review. Both Native APIs blocked."""

import argparse
import gzip
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.full_changing_operation_review import (
    TASK,
    comparison_cases,
)
from cold_storage.modules.layout.domain.full_changing_operation import (
    TimingHypothesis,
    timing_bounds,
)
from cold_storage.modules.layout.infrastructure.full_changing_operation_page import (
    overview_svg,
    page,
)
from cold_storage.modules.layout.infrastructure.practical_changing_review_page import plan_svg


def forbidden(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("R11_R6_NATIVE_FORBIDDEN")


def write_review(root: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("NEW_REVIEW_OUTPUT_REQUIRED")
    source = root / "docs/previews/v2.2.2/r11-r5-h5-practical-changing-review-r1"
    paths = [source / "project-and-room-catalog.json", source / "source-manifest.json"]
    catalog_raw = paths[0].read_bytes()
    manifest = json.loads(paths[1].read_bytes())
    if (
        hashlib.sha256(catalog_raw).hexdigest()
        != manifest["derived_files"]["project-and-room-catalog.json"]
    ):
        raise ValueError("FROZEN_R5_CATALOG_HASH_MISMATCH")
    catalog = json.loads(catalog_raw)
    cases = comparison_cases(catalog)
    output.mkdir(parents=True, exist_ok=False)
    packed = gzip.compress(
        json.dumps(cases, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0
    )
    (output / "full-operation-results.json.gz").write_bytes(packed)
    # Reports and drawings consume persisted deterministic calculation output.
    cases = json.loads(gzip.decompress((output / "full-operation-results.json.gz").read_bytes()))
    baseline = next(iter(cases.values()))
    comparison = []
    for label, case in cases.items():
        g, a = case["geometry"], case["operation"]
        comparison.append(
            dict(
                label=label,
                parameters=g["parameters"],
                metrics=g["metrics"],
                transitions_checked=a["expected_transitions"],
                transitions_verified=a["verified_transitions"],
                complete_users_by_shift=[
                    s["complete_service_users"] for s in a["departing_shifts"]
                ],
                retained_protocol_users=[s["complete_service_users"] for s in a["full_shifts"]],
                blockers=[s["blocker"] for s in a["departing_shifts"]],
                full_shift_seconds=[s["full_shift_seconds"] for s in a["departing_shifts"]],
                timing=a["timing"],
                project_functional_status="INPUT_REQUIRED",
            )
        )
    (output / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "index.html").write_text(page(cases))
    (output / "h5-full-operation-plan.svg").write_text(overview_svg(baseline))
    g, a = baseline["geometry"], baseline["operation"]
    for t in a["transitions"]:
        before = next(s for s in g["snapshots"] if s["id"] == t["from_batch"])
        svg = plan_svg(g, before)
        overlays = []
        for i, m in enumerate(t["moves"], 1):
            points = " ".join(f"{x},{-y}" for x, y in m["points_mm"])
            overlays.append(
                f'<polyline points="{points}" fill="none" stroke="{"#b73e32" if i % 2 else "#2c728c"}" stroke-width="18"><title>顺序{i} {m["person_id"]} {m["status"]}</title></polyline>'
            )
        svg = svg.replace("</svg>", "".join(overlays) + "</svg>")
        (output / f"{t['from_batch']}-to-{t['to_batch']}.svg").write_text(svg)
    timings = {}
    for key, times in {
        "fast_demo": replace(TimingHypothesis(), changing_seconds=60, seated_seconds=30),
        "base_demo": TimingHypothesis(),
        "slow_demo": replace(TimingHypothesis(), changing_seconds=180, seated_seconds=90),
    }.items():
        timings[key] = dict(
            input=asdict(times),
            source_type="demo",
            validity_status="unverified",
            requires_review=True,
            source_label="HYPOTHETICAL_NOT_APPROVED",
            result=timing_bounds(g, times),
        )
    (output / "timing-hypotheses.json").write_text(
        json.dumps(timings, ensure_ascii=False, indent=2) + "\n"
    )
    rows = [
        "# H5 两班完整更衣流程 R11 R6",
        "",
        "## 结论",
        "",
        "两种协议对照：完成本人服务即离室的条件模型走通两班各53人；统一离室协议每班仅3人后阻塞。实际功能仍为 INPUT_REQUIRED，不得升级为 CONDITIONAL_FIT。",
        "原两班各53人、22列110格、P01/P02同一H5矩形和两处真实1500mm Portal不变。未进行Native、MAIN或任何授权槽操作。",
        "",
        "## 28次批次转换与完整流程不是同一件事",
        "",
        f"原4柜前/6座方案：30个原静态批次；独立核验全部28次相邻转换，通过{a['verified_transitions']}次。每次保持53人身份，逐人移动；坐姿起身/坐下采用三维上身联合包络与前伸腿部，座凳始终参加碰撞检查。",
        "两班各53人的独立进室、独立离室路径通过条件几何检查。外部Access仍为原档参考，未重新证明外部人流能力。",
        "两种协议均先从东入口逐人入室到本位，53人全部到齐后才开始服务。负面参考保持53人在室直到全员完成再统一离室，每班完成3人后因服务区让位受阻，不能得到完整班次时间。主协议每人依次完成本人柜前操作、更衣、座凳使用、起身，经原南Portal离室；退出只发生在完整服务链和路径均通过后，所有剩余人员按实际位置参加校核，班次身份始终核对53人。",
        "完成即离室协议两班分别走通15批次、14个批次边界及53人全部服务/退出。成功依据是同一连续状态轨迹，不是拼接独立Portal或换位证明。初始峰值53人保持；离室后记录实际在室人数，不把已离室者算作静态障碍，也不提前删除未完成者。统一离室失败不是证明H5其他调度不可行。",
        "",
        "## 可审阅的人员活动假设",
        "",
        "原400×600mm身体、20mm相邻间隙保留为对照。固定全部坐标后，对身体周边外扩0/10/25/50/100mm：10mm即出现侵入净通道或坐姿支撑模型边界等冲突，25mm出现相邻人员活动包络重叠。静态不重叠不能证明穿脱衣、弯腰取物或转身可用。",
        "坐起的保守模型：上身从座面高度起覆盖原坐姿至前方站姿的联合空间，腿部始终在座凳前缘外；额外50mm侧向/前向余量仅为假设。不能视为生物力学、平衡或个体适配证明。",
        "",
        "## 方案比较",
        "",
        "|条件方案|静态批次|相邻转换|服务完成/每班|完整班次时间|",
        "|---|---|---|---|---|",
    ]
    for r in comparison:
        m = r["metrics"]
        rows.append(
            f"|{r['label']}|{m['static_pass_count']}/{m['snapshots']}|{r['transitions_verified']}/{r['transitions_checked']}|{r['complete_users_by_shift']} / 53|{[None if v is None else round(v / 60, 2) for v in r['full_shift_seconds']]} 分钟（条件）|"
        )
    rows += [
        "",
        "统一离室参考协议在并发2/4/6人时分别完成1/3/5人后堵塞。完成本人服务即离室后会释放实际空间，不能再把该参考协议堵塞解释为房间必然不可用。3/6/9座和扩大更衣区的完整结果分别列出；本轮仍是单人移动、串行更衣，不推定多座就能同比提速。450×650或500×700身体加100mm间隙、以及400×600加100mm间隙，现有单侧模板不能容纳完整53个本位，保留失败，没有减少人数。不是禁止其他布置。",
        "",
        "## 时间与吞吐边界",
        "",
        "示例：步行600mm/s；柜前20s；更衣90s；座凳45s；坐下4s、起身4s。均未经批准。记录逐项路径长度/速度和动作时长的累计已完成前缀。失败步骤没有完成时间；主协议成功时按完整进室、使用、离室轨迹求和，默认两班为13796.765s与12998.232s（约229.95/216.64分钟）。这些是条件串行计划，不是现场实测或吞吐合格证明。",
        "一个更衣操作位、53人、每人90s，仅此资源的理想工作量下界已为4770s（79.5分钟）。这还没有计入步行、排队或冲突，不能代替已经逐项累计的完整条件时长。60/90/180s敏感性保存在timing-hypotheses.json。没有认可的时间输入时，模块返回INPUT_REQUIRED与空时长。",
        "柜前15批来自各柜列与层位分配，不能用简单人数相除替代实际动作序列。资源下界只作下界，完整时长只允许从所有进入、使用、离开步骤均通过的连续轨迹计算。",
        "",
        "## 工程建议及缺失输入",
        "",
        "优先审阅服务区/等候本位的轮换协议与更衣操作位数量，再确定座凳和柜前并发人数；不能把座位占用者固定在公共服务设施上，又假定其随时能让位。单更衣操作位与保守单人移动协议是明显时间瓶颈，新增座位不能自动解除。完整条件时间远大于理想下界，需评审服务时间、动作包络和可批准的并发流程。",
        "真实人体活动尺度、衣物与五层格口可达性、坐起包络、实际柜型与房门开向、净通道/装修完成面、批准的洁污流线、清洁维护空间、全班允许时窗及经审阅的操作时间均待确认。",
        "全部结论限于假设模型。R1–R5代码及历史工程有效状态、P1、Stage B与九/十二指标未改。",
        "",
        "## 复核文件",
        "",
        "index.html可本地直接打开，切换两班、全部相邻批次、完整失败前缀及独立Portal路径。full-operation-results.json.gz保存所有真实计算状态、路径、三维包络、冲突、人数及时间。28张SVG忠实显示既有几何和逐条路径，叠加路径是依次使用，不是同时通行。",
    ]
    rows += ["", "## 主协议完整条件时间分解", "", "|操作|第1班秒|第2班秒|", "|---|---:|---:|"]
    time_rows = [s["duration_by_operation_seconds"] for s in a["departing_shifts"]]
    for operation in sorted(set(time_rows[0]) | set(time_rows[1])):
        rows.append(
            f"|{operation}|{time_rows[0].get(operation, 0):.3f}|{time_rows[1].get(operation, 0):.3f}|"
        )
    rows += [
        "",
        "路线由西侧柜列去东端更衣区，再返回南侧座凳和包装门，来回行走成本真实计入。串行计划仅作为可复核条件模拟，不代表最优排程。",
    ]
    (output / "operation-time-breakdown.json").write_text(json.dumps(time_rows, indent=2) + "\n")
    (output / "operation-report.md").write_text("\n".join(rows) + "\n")
    (output / "receipt.json").write_text(
        json.dumps(
            dict(
                task=TASK,
                base_head="73e5ab0a12f8851298da9b8222321327e46edabb",
                project_functional_status="INPUT_REQUIRED",
                all_adjacent_pairs_checked=28,
                pairs_verified=a["verified_transitions"],
                full_service_users=[s["complete_service_users"] for s in a["departing_shifts"]],
                retained_protocol_service_users=[
                    s["complete_service_users"] for s in a["full_shifts"]
                ],
                full_shift_verified_under_hypotheses=all(
                    s["full_shift_seconds"] is not None for s in a["departing_shifts"]
                ),
                actual_functional_fit="INPUT_REQUIRED",
                native_solves=0,
                new_main=False,
                new_grant=False,
                new_claim=False,
                full_ci="NOT_REQUESTED",
            ),
            indent=2,
        )
        + "\n"
    )
    sources = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for p in (root / "backend/src/cold_storage/modules/layout").rglob("*changing_operation*.py"):
        sources[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    derived = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}
    (output / "source-manifest.json").write_text(
        json.dumps(dict(sources=sources, derived=derived), indent=2) + "\n"
    )


def main() -> None:
    cp_model.CpSolver.solve = forbidden
    cp_model.CpSolver.Solve = forbidden
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_review(Path(__file__).resolve().parents[2], args.output)
    print(json.dumps(dict(output=str(args.output.resolve()), native_solves=0)))


if __name__ == "__main__":
    main()
