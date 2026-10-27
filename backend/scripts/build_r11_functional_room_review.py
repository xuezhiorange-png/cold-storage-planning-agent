# ruff: noqa: E501 -- persisted Markdown report paragraphs
"""Generate a local read-only R11 report. No Runner, Store, Native or P1 mutation."""

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

from cold_storage.modules.layout.application.functional_room_review import build_historical_review
from cold_storage.modules.layout.domain.functional_room_fit import evaluate_functional_room
from cold_storage.modules.layout.infrastructure.functional_room_fit_examples import scenario
from cold_storage.modules.layout.infrastructure.functional_room_review_page import render_review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--r9-archive", type=Path)
    parser.add_argument("--r9-preservation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    if args.output.resolve().is_relative_to(
        args.archive.resolve()
    ) or args.archive.resolve().is_relative_to(args.output.resolve()):
        raise ValueError("DERIVED_OUTPUT_MUST_BE_SEPARATE_FROM_HISTORICAL_ARCHIVE")
    owner_path = (
        repo
        / "docs/previews/v2.2.2/owner-functional-input-contract-r2/owner-confirmed-business-rules-v2.json"
    )
    relative = str(owner_path.relative_to(repo))
    if (
        subprocess.check_output(
            ["git", "show", "288a56b768baa859cbcfb41908fbbd5d6155094d:" + relative], cwd=repo
        )
        != owner_path.read_bytes()
    ):
        raise ValueError("LEGACY_OWNER_RULE_SOURCE_CHANGED")
    from ortools.sat.python import cp_model

    with (
        patch.object(
            cp_model.CpSolver, "solve", side_effect=AssertionError("R11_NATIVE_FORBIDDEN")
        ),
        patch.object(
            cp_model.CpSolver, "Solve", side_effect=AssertionError("R11_NATIVE_FORBIDDEN")
        ),
    ):
        data = build_historical_review(
            args.archive,
            args.manifest,
            owner_path,
            r9_archive=args.r9_archive,
            r9_preservation=args.r9_preservation,
        )
        examples = []
        for kind, title in [
            ("SINGLE_SIDE", "单侧柜 · 指定布置可容纳"),
            ("DOUBLE_SIDE", "双侧柜 · 指定布置可容纳"),
            ("NARROW", "同40㎡的窄条房间 · 指定布置冲突"),
            ("OFFICE", "办公家具与椅子操作区"),
            ("COATING", "覆膜设备、操作与维护空间"),
        ]:
            room, refs, witness, basis = scenario(kind)
            examples.append(
                dict(
                    title=title,
                    synthetic=True,
                    source_label="ENGINEERING_DERIVED",
                    room=room,
                    evaluation=evaluate_functional_room(room, refs, witness, reviewed_basis=basis),
                    field_refs=refs,
                    reviewed_basis={
                        k: dict(
                            value=v.value,
                            unit=v.unit,
                            source_label=v.source_label,
                            reference=v.reference,
                            scope_id=v.scope_id,
                            field_name=v.field_name,
                        )
                        for k, v in basis.items()
                    },
                )
            )
    args.output.mkdir(parents=True, exist_ok=True)

    def dump(name: str, value: Any) -> None:
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    dump("review-data.json", data)
    dump("synthetic-examples.json", examples)
    # Reports render the saved calculation results, never repeat their formulas.
    data = json.loads((args.output / "review-data.json").read_text())
    examples = json.loads((args.output / "synthetic-examples.json").read_text())
    (args.output / "index.html").write_text(render_review(data, examples), encoding="utf-8")
    rows = [
        "# R11 功能房间可用性报告",
        "",
        "任务：V2_2_2_R11_FUNCTIONAL_ROOM_FIT_R1。原源码参考HEAD 288a56b768baa859cbcfb41908fbbd5d6155094d。",
        "",
        "## 结论",
        "",
        "R10 R2唯一MAIN的9份记录对应8组实际房间矩形；27份房间记录的原工程状态与P1面积均保留，但功能可用性全部INPUT_REQUIRED。不能仅依据长宽比判断可用或不可用。原候选有效状态、九项和十二项比较完全未改。",
        "",
        "## 可信功能输入与适用性",
        "",
        "原Owner V2合同确认两班独立员工柜、柜数为两班人数之和、非重叠更衣以峰值人数计。Office的12/20/30人是按明确工厂规模选择的条件值。既有53人/106柜示例未绑定此封存20t的实际包装人数，未自动应用；20t进厂量不能直接替代已包装产品质量。",
        "",
        "实际同时更衣人数、两班柜数、柜型号/三维尺寸、柜前操作净距、内部通道、门扇操作包络、座凳、洁净分隔和装修净尺寸仍缺。Office缺实际办公人数、家具与通行设计；Coating缺已选覆膜设备、安装/操作/维护/进出料与有效能力依据。",
        "",
        "## 逐记录三类房间",
        "",
        "|记录|H|物理组|房间|实体宽×深m|实际面积m²|P1需求m²|原工程|P1面积|功能可用性|",
        "|---|---|---|---|---|---:|---:|---|---|---|",
    ]
    for r in data["room_evaluations"]:
        room = r["room"]
        e = r["evaluation"]
        facts = e["physical_facts"]
        rows.append(
            f"|{r['record']}|H{r['handoff']}|{r['physical_group']}|{room['room_code']}|{facts['width_m']}×{facts['depth_m']}|{facts['area_m2']}|{facts['required_area_m2']}|历史有效|{e['p1_area_status']}|{e['functional_status']}|"
        )
    rows += [
        "",
        "H5有2份、H6有7份记录。H5更衣室26.331×3.25m/85.57575㎡；H6为39.683×1.008m逐步调整至39.621×1.015m，面积40.000464至40.215315㎡。它们都有原Access见证，不能据此推定内部106柜或其他假设规模能用。P01/P02的等价尺寸/旋转编码归G01，实际房间矩形相同。",
        "",
        "## 独立历史参考R9 P04",
        "",
        "R9 P04只作独立历史参考：20×2m、40㎡的更衣室仍为INPUT_REQUIRED；不与R10跨实验合并正式Pareto。其原有效状态保持。",
        "",
        "## 模块的可解释结果",
        "",
        "四个操作状态：正常使用、交接班、清洁、维护。输入均为应用侧审阅、同scope的BasisValue引用；请求中的自称OWNER_CONFIRMED不能产生记录。只检验显式柜体/家具/设备、独立柜分配、同时操作容量、净高、实体/操作碰撞、全宽通道与真实Portal连接。允许单侧/双侧及旋转，不设3m宽度或比例上限。洁净分隔适用但缺完整专业分隔设计时继续INPUT_REQUIRED。",
        "",
        "CONDITIONAL_FIT只证明给定输入和指定布置的条件几何可容纳，既不认证来源，也不替代消防、卫生、无障碍及工程批准。CONFIGURATION_NOT_FIT只拒绝此布置，不证明所有布置均不可行。",
        "",
        "合成算例独立展示：只用于回归和演示柜体/通道/门洞/设备包络接口，不是真实工程验收，不属于封存20t候选。",
        "",
        "## 后续尺寸设计到P2的边界",
        "",
        "1. 先由Owner/工程方确认人数、型号、清洁分隔与完成面净尺寸；每个值保留单位、原文/型号版本、适用项目、审阅记录。来源Hash只证明字节，不代表批准。",
        "2. 对已确认的单侧/双侧模板，使用柜体行数×单元宽、柜深、开启/操作余量、内部净通道、座凳及端部余量计算条件包络；不同模板保持显式备选，不能把一个模板失败变成全局房间禁止。",
        "3. 长度要求向上取整至整数mm，可用净尺寸向下取整；完成面至P2实体边界还需墙体/饰面依据，不允许直接把名义边界当净宽。面积要求保持原P1 Authority。",
        "4. 只有新的尺寸条件经原工程Authority审批并版本化后，才可显式变成模板局部不等式、设备不重叠、Portal开启/通行包络与内部全宽连通约束。保留候选方案的析取与合法旋转；禁止隐含3m宽度、面积上限或比例阈值。",
        "5. 本轮没有将任何条件编译进P1或CP-SAT，没有调用Native，没有新增求解授权或修改生产默认。",
        "",
        "数据来源、各字段缺口、Portal局部坐标及原比较全文在review-data.json；完整条件算例在synthetic-examples.json。打开index.html可本地浏览，无网络依赖。",
    ]
    (args.output / "functional-room-report.md").write_text("\n".join(rows) + "\n")
    print(
        json.dumps(
            dict(
                records=9,
                physical_groups=8,
                rooms=len(data["room_evaluations"]),
                statuses={e["title"]: e["evaluation"]["functional_status"] for e in examples},
                native_solves=0,
                output=str(args.output),
            ),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
