# ruff: noqa: E501 -- persisted engineering report text
"""Read raw archived Access records; produce a new R5 hypothesis-only review."""

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from build_r11_r3_locker_review import load_sources
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.multi_tier_locker_review import bind_multi_tier_review
from cold_storage.modules.layout.application.practical_changing_review import (
    TASK,
    review_h5,
    verify_catalog,
)
from cold_storage.modules.layout.domain.practical_changing_layout import H5Hypothesis
from cold_storage.modules.layout.infrastructure.practical_changing_review_page import (
    presentation,
    render_page,
    serve_review,
)


def forbidden_native(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("R11_R5_NATIVE_FORBIDDEN")


def write_review(repo: Path, archive: Path, output: Path) -> dict[str, Any]:
    if output.exists() or output.resolve().is_relative_to(archive.resolve()):
        raise ValueError("NEW_INDEPENDENT_OUTPUT_REQUIRED")
    r3, sources = load_sources(repo, archive)
    fact = repo / "docs/tasks/V2_2_2-r11-r4-reviewed-locker-form.txt"
    catalog = bind_multi_tier_review(r3, fact.read_bytes())
    sources[str(fact)] = hashlib.sha256(fact.read_bytes()).hexdigest()
    p = H5Hypothesis()
    choices = {
        "A 单侧分区 · 22列 · 铰链门": ("INTERNAL_PARTITION", p),
        "B 相对双侧 · 22列 · 铰链门": ("INTERNAL_PARTITION", replace(p, arrangement="OPPOSED")),
        "C 分段1200 · 22列 · 铰链门": ("INTERNAL_PARTITION", replace(p, arrangement="SEGMENTED")),
        "D 分段600 · 22列 · 铰链门": (
            "INTERNAL_PARTITION",
            replace(p, arrangement="SEGMENTED", segment_gap_mm=600),
        ),
        "E 单侧分区 · 44列双格 · 铰链门": ("TWO_COMPARTMENTS", p),
        "F 单侧分区 · 22列 · 无平面侵入门假设": (
            "INTERNAL_PARTITION",
            replace(p, door_kind="NO_PLAN_INTRUSION"),
        ),
        "G 柜深600敏感性 · 22列": ("INTERNAL_PARTITION", replace(p, column_depth_mm=600)),
        "H 格高350敏感性 · 22列": (
            "INTERNAL_PARTITION",
            replace(p, cell_height_mm=350, cabinet_height_mm=2000),
        ),
    }
    results = {k: review_h5(catalog, mode, h) for k, (mode, h) in choices.items()}
    output.mkdir(parents=True, exist_ok=False)
    (output / "project-and-room-catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "hypothetical-results.json").write_text(
        json.dumps(results, ensure_ascii=False) + "\n"
    )
    results = json.loads((output / "hypothetical-results.json").read_bytes())
    shown = {k: presentation(v) for k, v in results.items()}
    (output / "index.html").write_text(render_page(shown))
    rows = [
        "# R11 R5 · H5更衣室工程深化",
        "",
        "## 结论与实际批准边界",
        "",
        "推荐进一步深化A：西段单侧组合柜，东段更衣/等候与座凳，保留真实东入口和南侧分选包装Portal。它是有明确参数的条件空间见证，实际功能仍为 INPUT_REQUIRED，不能成为 CONDITIONAL_FIT 或施工图。",
        "",
        "项目事实：成品20000kg/日；设计两班各53人；每班53人同时在室。五层格口基本方案每班11列，共22列110格；双格方案每班22列，共44列220格。设计编号不是花名册。R4原审批来源和R3项目级审阅机制原样复用。",
        "",
        "P01/P02共用同一26331×3250mm物理矩形；分别从原档回读其Access。东Portal x26331,y875–2375；南Portal y0,x12415–13915，两处1500mm净宽。外部Access未重新规划，原工程通过状态和历史九/十二指标未变。",
        "",
        "## 明示假设",
        "",
        "每列宽400、深500、总高1800mm；格净高300、底座100、层板20mm；每2列组合成一实体柜，末列独立，因此22列为12个假设采购单元。完成面四边内缩20mm，柜后安装间隙20mm，单元间20mm。真实厂家、结构、锚固/安装运输净空和装修尺寸尚未确认。",
        "",
        "柜门为左铰链外开0–90°，柜框20、门厚15、扫掠半径360mm；各层按真实模型的z高度独立检查。柜前退让380mm，人体/操作占位400×600×1800mm，柜前每批最多4人；并未将53人在室减少为4人。此占位只证明指定包络，不证明人体弯腰、穿脱衣、提取衣物和动作工学。",
        "",
        "两张1800×400×450mm座凳，各3个600mm节距座位。坐姿上身从450至1300mm、腿部从凳前缘至600mm占位前缘。两班均有53处独立本位；操作人员离开自己的本位后，该处保持空置供返回。静态快照通常4名柜前、6名座凳、1名独立更衣操作、42名等候人员。东端北侧另留800×900mm的假设更衣操作包络，人员始终计入53人；该包络仅为待审动作空间模型，并非人体工学验证。53人完整更衣动作能力尚未证明。",
        "",
        "净通道1200mm；真实房门暂按打开后不侵入室内的条件假设，实际门型/开向未确认。实际柜门闭合后人员才换位，其他未操作格门保持关闭。无平面侵入柜门只是独立敏感性选项，不作为真实柜型结论。",
        "",
        "## 参数方案核验",
        "",
        "|方案|列/容量|组合柜|柜长mm/占地mm²|净通道mm|静态通过|相邻批次通过|具体失败|",
        "|---|---|---:|---|---:|---|---|---|",
    ]
    for i, (key, r) in enumerate(results.items(), 1):
        m = r["metrics"]
        errors = Counter(v["code"] for s in r["snapshots"] for v in s["evaluation"]["conflicts"])
        errors.update(r["hierarchy_failures"])
        rows.append(
            f"|{key}|{m['columns']}/{m['compartments']}|{m['hypothetical_procurement_units']}|{m['occupied_cabinet_length_mm']}/{m['cabinet_footprint_mm2']}|{m['reserved_aisle_mm']}|{m['static_pass_count']}/{m['snapshots']}|{m['adjacent_batch_pass_count']}/2|{dict(errors)}|"
        )
        shown_r = shown[key]
        first = r["snapshots"][0]["id"]
        (output / f"variant-{i}-plan.svg").write_text(shown_r["plans"][first])
        if i == 1:
            (output / "h5-best-conditional-plan.svg").write_text(shown_r["plans"][first])
            (output / "h5-door-height-review.svg").write_text(shown_r["door_svg"])
            for shift in (1, 2):
                (output / f"h5-shift-{shift}-elevation.svg").write_text(
                    shown_r["elevations"][str(shift)]
                )
                for n, svg in enumerate(shown_r["transitions"].get(str(shift), []), 1):
                    (output / f"h5-shift-{shift}-transition-{n}.svg").write_text(svg)
    rows += [
        "",
        "## 真实碰撞与动作证据",
        "",
        "门扇校核采用完整90°扇形加保守门厚膨胀，与各物体三维体积逐项相交；SVG弧线采样只用于显示，不参与判定。高层扫掠与矮凳的同平面投影单独记录，不能把所有门扫掠视为地面占用，也不能忽略高层门风险。预留通道无论高度均不得被开门投影侵入。",
        "",
        "首组相邻批次按两班分别核验：前4人逐一返回各自本位，后4人逐一进入自己的柜列。每步完整轴向扫掠盒与52名固定人员、柜体、座凳、完成面和预留通道/端部接近区逐项核验；包含转角与端部的完整人体包络，不用端点或直线距离替代路径。所有端部站位在换位完成后与下一快照吻合。",
        "",
        "仅两班首组相邻批次，共16条人员移动见证。没有把其他28组快照自动升级成动态能力；座凳起坐、持续取衣更衣、全部53人的整轮转换、同时穿行、交接班重叠、清洁维护及疏散未验证。不能由本例估计吞吐时间或证明53人能完成全部更衣流程。",
        "",
        "安装评估仅含外形、完成面、假设安装间隙和打开包络；未证明设备可搬入、锚固、调平、维修拆卸。清洁/维护作业流程缺少真实工具和净空，标记 NOT_EVALUATED。",
        "",
        "## 洁污分隔",
        "",
        "A每人一格内部隔断：保留分隔要求，隔板厚度、有效容积、衣物尺度和卫生效果 INPUT_REQUIRED。B每人两格：独立分配工衣/私衣，仍不证明两条洁污人流完全隔离。东入口至南包装门的示意方向只来自真实Portal，不代表已批准卫生流程。44列方案若空间冲突，保留失败，不减少53人、座凳或校核功能换取通过。",
        "",
        "## 待确认输入",
        "",
        *["- " + x for x in catalog["missing_inputs"]],
        "",
        "另需：柜门铰链位置/角度/厚度、门把及锁具突出、完成面净高、锚固及搬运要求、实际人体和穿衣操作包络、每批人数与时间、座凳起坐和维护清洁工具、房门开向及内外候门空间、洁污工艺审批。",
        "",
        "## 本地查看与参数复算",
        "",
        "直接打开 index.html 可查看所有保存方案和批次。启动仅本机服务可复算假设，不写入Authority：",
        "",
        "```bash",
        "cd backend",
        "PYTHONPATH=src:scripts uv run --frozen python scripts/build_r11_r5_h5_review.py --serve-existing ../docs/previews/v2.2.2/r11-r5-h5-practical-changing-review-r1 --port 52992",
        "```",
        "",
        "函数版本、单位、公式、输入、冲突组件、每次移动的52人位置和门扇状态均在 hypothetical-results.json；来源及衍生哈希在 source-manifest.json。无Native、MAIN、Grant/Claim、正式CI或生产默认改变。",
    ]
    (output / "review-report.md").write_text("\n".join(rows) + "\n")
    (output / "final-receipt.json").write_text(
        json.dumps(
            dict(
                task=TASK,
                base_head="bc031b50edda3a8e142eb2f0a89b850fc2e2811e",
                project_functional_status="INPUT_REQUIRED",
                hypothetical_template=next(iter(results.values()))["template_status"],
                source_records=["P01", "P02"],
                physical_rooms=1,
                room_users=53,
                native_solves=0,
                new_main=False,
                new_grant=False,
                new_claim=False,
                full_ci="NOT_REQUESTED",
                historical_changed=False,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    derived = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()
    }
    (output / "source-manifest.json").write_text(
        json.dumps(dict(source_files=sources, derived_files=derived), ensure_ascii=False, indent=2)
        + "\n"
    )
    return catalog


def main() -> None:
    cp_model.CpSolver.solve = forbidden_native
    cp_model.CpSolver.Solve = forbidden_native
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--serve-existing", type=Path)
    parser.add_argument("--port", type=int, default=52992)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    if args.serve_existing:
        catalog = json.loads((args.serve_existing / "project-and-room-catalog.json").read_bytes())
        verify_catalog(catalog)
        serve_review(catalog, (args.serve_existing / "index.html").read_text(), args.port)
    elif args.archive and args.output:
        write_review(repo, args.archive, args.output)
        print(json.dumps(dict(output=str(args.output.resolve()), native_solves=0)))
    else:
        parser.error("use --archive/--output or --serve-existing")


if __name__ == "__main__":
    main()
