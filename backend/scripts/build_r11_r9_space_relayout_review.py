# ruff: noqa: E501 -- engineering evidence report prose
"""Read-only archived inputs, finite spatial templates; both Native APIs disabled."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.cabinet_front_review import SOURCE_PATH
from cold_storage.modules.layout.application.h5_space_relayout_review import TASK, review_relayouts
from cold_storage.modules.layout.infrastructure.h5_space_relayout_page import page, space_svg

BASE = "9ab3851591b93c0bb0543ba2a96c16d49cfbc166"


def forbidden(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("R11_R9_NATIVE_FORBIDDEN")


def summarize(label: str, c: dict[str, Any]) -> dict[str, Any]:
    g = c["geometry"]
    complete = all(
        s["completed_users"] == 53 and s["status"] == "VERIFIED_UNDER_HYPOTHESES"
        for s in c["shifts"]
    )
    return dict(
        label=label,
        home_count=g["metrics"]["home_count"],
        rotated_home_count=g["metrics"].get("rotated_home_count", 0),
        metrics=g["metrics"],
        parameters=g["parameters"],
        portal_and_activity_result="BOTH_SHIFTS_VERIFIED_UNDER_HYPOTHESES"
        if complete
        else "NOT_ESTABLISHED_FOR_COMPLETE_SERVICE",
        limitation="仅10mm北带模板余量；人体/柜型/房门/洁污未批准"
        if complete
        else "本位不足，未降低53人；仅本模板失败",
        actual_functional_status="INPUT_REQUIRED",
        shifts=[
            dict(
                shift=s["shift"],
                status=s["status"],
                completed_users=s["completed_users"],
                initial_service_occupancy=s["initial_service_occupancy"],
                full_shift_minutes=s["full_shift_minutes"],
                total_route_m=s["total_route_m"],
                events=len(s["events"]),
                batches=len(s["completed_batches"]),
                completed_person_ids=s["completed_person_ids"],
                yaw_turns=sum(e["proof"].get("yaw_turn_count", 0) for e in s["events"]),
                blocker=s["blocker"],
            )
            for s in c["shifts"]
        ],
    )


def write_review(root: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("NEW_R9_OUTPUT_DIRECTORY_REQUIRED")
    cp_model.CpSolver.solve = forbidden
    cp_model.CpSolver.Solve = forbidden
    old = root / "docs/previews/v2.2.2/r11-r8-h5-cabinet-front-review-r1"
    for name, sha in json.loads((old / "source-manifest.json").read_bytes())[
        "derived_files"
    ].items():
        if hashlib.sha256((old / name).read_bytes()).hexdigest() != sha:
            raise ValueError("R8_ARCHIVE_HASH_MISMATCH: " + name)
    cat = (
        root
        / "docs/previews/v2.2.2/r11-r5-h5-practical-changing-review-r1/project-and-room-catalog.json"
    )
    cat_manifest = cat.parent / "source-manifest.json"
    if (
        hashlib.sha256(cat.read_bytes()).hexdigest()
        != json.loads(cat_manifest.read_bytes())["derived_files"][cat.name]
    ):
        raise ValueError("FROZEN_ROOM_CATALOG_HASH_MISMATCH")
    r7 = root / "docs/tasks/V2_2_2-r11-r7-reviewed-standing-project-facts.txt"
    r8 = root / SOURCE_PATH
    cases = review_relayouts(json.loads(cat.read_bytes()), r7.read_bytes(), r8.read_bytes())
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "relayout-results.json.gz"
    raw.write_bytes(
        gzip.compress(
            json.dumps(cases, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0
        )
    )
    # Presentation only reads these persisted engineering results.
    cases = json.loads(gzip.decompress(raw.read_bytes()))
    comparison = [summarize(k, v) for k, v in cases.items()]
    (output / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "index.html").write_text(page(cases, comparison))
    for i, c in enumerate(cases.values(), 1):
        for shift in (1, 2):
            stem = f"scheme-{i:02}-shift-{shift}"
            (output / (stem + "-waiting.svg")).write_text(space_svg(c, shift))
            s = c["shifts"][shift - 1]
            event = next(
                (e for e in s["events"] if e["operation"] == "PARALLEL_STANDING_CHANGE"), None
            )
            if event:
                (output / (stem + "-changing.svg")).write_text(space_svg(c, shift, event["proof"]))
        if i == 1:
            (output / "h5-relayout-plan.svg").write_text(space_svg(c))
            (output / "h5-relayout-detail.svg").write_text(space_svg(c, detail=True))
            for operation, name in [
                ("PARALLEL_STANDING_CHANGE", "h5-relayout-service.svg"),
                ("OPEN_FOR_RETRIEVE", "h5-locker-door-open.svg"),
            ]:
                witness = next(
                    e["proof"] for e in c["shifts"][0]["events"] if e["operation"] == operation
                )
                (output / name).write_text(space_svg(c, proof=witness, detail=True))
            turn = next(
                e["proof"] for e in c["shifts"][0]["events"] if e["proof"].get("yaw_turn_count")
            )
            yaw = next(p for p in turn["legs"] if p["operation"] == "YAW_90_IN_EXISTING_AISLE")
            (output / "h5-yaw-sweep.svg").write_text(space_svg(c, proof=yaw, detail=True))
    selected = next(iter(cases.values()))
    (output / "project-binding.json").write_text(
        json.dumps(selected["binding"], ensure_ascii=False, indent=2) + "\n"
    )
    dimension_chains = {label: c["geometry"].get("dimension_chains") for label, c in cases.items()}
    (output / "dimension-chains.json").write_text(
        json.dumps(dimension_chains, ensure_ascii=False, indent=2) + "\n"
    )
    report = [
        "# R11 R9 H5 实际空间重排与容量验证",
        "",
        "TASK_ID=" + TASK,
        "BASE_HEAD=" + BASE,
        "",
        "三种原H5组织均在450×650mm人体、100mm等候本位间隙、600×900mm柜前活动及1200mm假设通道下，取得两班各53人的完整条件流程。没有减少53人，没有修改原建筑矩形或1500mm Portal，也没有增加柜前并发算法。实际功能仍是 INPUT_REQUIRED。",
        "",
        "| 方案 | 本位 / 90°转向本位 | 第1/2班完成 | 第1/2班条件分钟 |",
        "|---|---:|---:|---:|",
    ]
    for row in comparison:
        mins = " / ".join(
            "未成立" if s["full_shift_minutes"] is None else f"{s['full_shift_minutes']:.2f}"
            for s in row["shifts"]
        )
        report.append(
            f"| {row['label']} | {row['home_count']} / {row['rotated_home_count']} | "
            + " / ".join(str(s["completed_users"]) for s in row["shifts"])
            + f" | {mins} |"
        )
    report += (
        [
            "",
            "## 空间变化与尺寸链",
            "",
            "A：原单侧柜组保留，东段47个常规本位与西北6个转向本位组合；北带身体只改变方向，从450×650变为650×450mm，面积、高度和人员身份都不变。B：34个北墙转向本位加19个东南常规本位；改变整体等候分区。C：两班柜组之间留1200mm分段间隙，仍为22列110格，34个北墙转向本位加19个东南常规本位。不是三张同一模板改名称。有限排布最多生成53位，不把53当作最大容量证明。",
            "沿柜区横向链：完成面20 + 安装20 + 柜深500 + 人距380 + 运输人体深650 + 净通道1200 + 转向等候深450 + 余量10 + 完成面20 = 3250mm。北带可用460mm，转向本位深450mm。三种方案的完整本位、柜体坐标与尺寸链保存于原始JSON、dimension-chains.json及同比例SVG。100mm是等候本位的轴向净间隙，不是未经确认的动态人体舒适距离。",
            "末柜600mm活动宽度以450mm人体中线定位，相对400mm柜列向右外伸125mm；原100mm回转退让会侵入25mm。新布置按包络计算125mm端部退让，保持原1200mm回转净区。原R8代码和47/46人历史结果均不改；该反例在独立回归中仍被原活动/通道校核拒绝。",
            "",
            "## 连续转向、柜门和人员完整流程",
            "",
            "没有把旋转后的静态矩形直接当成功。转向本位先以650×450mm姿态沿本位接入段移入实际通道，再在同一中心完成90°转向，之后恢复450×650mm运输姿态，调用原通道网络移动。入室顺序反向执行这一过程。整个90°转动用792×792mm保守对角方形连续包络覆盖所有中间角度；必须完整处于原1200mm通道并避开所有实际在室者和柜体。记录每段source/target、people_before、三维扫掠及冲突。该矩形模型仍不证明真实人体转身、弯腰和穿脱的人体工学。",
            "每班全部53人先经东Portal到达各自本位，再按原R8间隔柜列分组完成：到本人柜前→开柜→取衣→关柜→本人柜前站立更衣→再开柜→存放→关柜→连续走至南Portal→离室。两班各14批，每人一次完整服务；剩余等候者始终作为实际碰撞体。原三维门扇、层高、净通道、1500mm Portal、人员碰撞及原柜前活动校核均保留。柜门关闭后才更衣、移动期间柜门关闭、房门不侵入通道仍是未批准工艺/设备假设。P01/P02两份原Access记录分别只读附在结果中，不计为两套独立H5矩形；外部通道未重新求解。",
            "",
            "## 失败边界与反事实尺寸",
            "",
            "原R8在同样450×650mm及100mm间隙条件下仅47个本位，完整流程拒绝。R9完成面改为30mm的独立敏感性反例中，北带只剩440mm，转向450mm深本位也不成立；保留其实际本位数与拒绝，不靠缩小身体或删除用户通过。默认20mm完成面仅10mm余量，25mm完成面时理论余量为零，实际施工公差、墙面设备及衣物占用可能使方案失效。",
            "如坚持北带常规朝向650mm深本位，仅从同一柜区截面计算，20mm完成面需要建筑深3440mm，比原H5增加190mm；30mm完成面对应3460mm。这是未批准的截面必要条件，不是已证明的完整扩建方案，不能改写历史H5、P1或面积Authority。原H5下已找到条件重排，因此本轮不建议直接以有限模板失败要求扩建。其他未检查组织的可行性未知。",
            "",
            "## 时间仅作必要条件对照",
            "",
            "与R8相同的示例步速600mm/s、开/关各3s、取/放各20s、更衣90s；新增每次90°转向3s作为独立未批准参数。步行和转向串行，柜前动作按原分组并行，两班分别模拟。时间包含实际路线，不拿失败前缀作完整时长。未优化任何时间参数，不证明现场效率、舒适度、工间窗口或最大吞吐。",
            "",
            "## 工程评审建议与真实输入",
            "",
            "优先评审A：只补充6个西北转向本位，较少人员需要转向，原柜组保持连贯。B/C提供分区与柜组分段的对照，不因某班时间更短就宣布工程最优。必须现场确认北带完成面及安装公差，核实人穿工作服后的真实静态/活动/转向尺度、五层柜实际宽深高与顶层可达性、柜门和房门开向、站位方向可接受性、关柜更衣与两次开柜规程、洁污和清洁维护流程。",
            "",
        ]
        + ["- " + m for m in selected["binding"]["missing_inputs"]]
        + [
            "",
            "实际功能 INPUT_REQUIRED；未重新验收整厂工程。R9功能模板和报告生成不调用Native；没有20t求解、MAIN、Grant/Claim或正式完整CI。本地验证范围误扩张时执行了既有微型合成Native回归，已中断；见execution-boundary-exception.md，不宣称本任务整体Native次数为零。原P1、Stage B、历史有效状态、九/十二指标与生产默认均不变。",
            "",
        ]
    )
    (output / "relayout-report.md").write_text("\n".join(report))
    receipt = dict(
        task=TASK,
        base_head=BASE,
        original_h5_templates=3,
        both_shifts_completed_users=[r["shifts"] for r in comparison[:3]],
        actual_functional_status="INPUT_REQUIRED",
        r9_functional_native_solves=0,
        frozen_20t_native_solves=0,
        task_zero_native_boundary="NOT_MET_LEGACY_LOCAL_SYNTHETIC_REGRESSIONS_EXECUTED",
        legacy_local_native_call_count="NOT_INSTRUMENTED",
        main=False,
        grant=False,
        claim=False,
        full_ci="NOT_REQUESTED",
        historical_records_changed=False,
    )
    (output / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    originals = [
        cat,
        cat_manifest,
        r7,
        r8,
        old / "source-manifest.json",
        old / "comparison.json",
        old / "cabinet-front-results.json.gz",
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
    exception = output / "execution-boundary-exception.md"
    exception.write_text(
        "# Local validation boundary exception\n\n"
        "The agent mistakenly included the unchanged Stage B fast-regression modules in local validation. "
        "Their resource workers run in child Python processes; the parent-only Native API prohibition did not propagate. "
        "Existing tiny synthetic CP-SAT tests executed, including the R4 729-assignment enumeration and witness tests. "
        "The broad run was interrupted after 92 passing tests; this partial run is not counted as completed regression. "
        "Exact Native-call count was not instrumented and must not be stated as zero.\n\n"
        "No frozen 20t solve, MAIN, real Grant/Claim or formal full CI was executed. "
        "R9 spatial-template evaluation itself is deterministic and uses no Native API. "
        "Subsequent local tests are restricted to R11 functional, architecture and CI contracts. "
        "The inherited automatic fast-CI suite remains intact, including its original synthetic tests. "
        "This note records a scope deviation; it does not erase or approve it.\n"
    )
    manifest["derived_files"][exception.name] = hashlib.sha256(exception.read_bytes()).hexdigest()
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_review(Path(__file__).resolve().parents[2], args.output.resolve())
