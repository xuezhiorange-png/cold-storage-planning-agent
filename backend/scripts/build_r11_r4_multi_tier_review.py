# ruff: noqa: E501 -- persisted bilingual engineering review prose
"""Build a new R4 report without changing any historical evidence or running Native."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from build_r11_r3_locker_review import load_sources
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.multi_tier_locker_review import (
    bind_multi_tier_review,
    review_multi_tier_template,
)
from cold_storage.modules.layout.domain.multi_tier_locker_model import MultiTierHypothesis
from cold_storage.modules.layout.infrastructure.multi_tier_locker_review_page import (
    presentation,
    render_page,
    serve_review,
)


def forbidden_native(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("R11_R4_NATIVE_FORBIDDEN")


def write_review(repo: Path, archive: Path, output: Path) -> tuple[dict[str, Any], str]:
    if output.exists() or output.resolve().is_relative_to(archive.resolve()):
        raise ValueError("NEW_OUTPUT_OUTSIDE_HISTORICAL_ARCHIVE_REQUIRED")
    r3, sources = load_sources(repo, archive)
    fact = repo / "docs/tasks/V2_2_2-r11-r4-reviewed-locker-form.txt"
    catalog = bind_multi_tier_review(r3, fact.read_bytes())
    sources[str(fact)] = hashlib.sha256(fact.read_bytes()).hexdigest()
    presets = {}
    for row in catalog["groups"]:
        for scenario in catalog["demands"]:
            for arrangement in ("OPPOSED", "SINGLE_SIDE"):
                p = MultiTierHypothesis(
                    arrangement=arrangement,
                    front_concurrent_users=11,
                    cabinet_door_sweep_mm=0,
                    room_door_sweep_mm=0,
                )
                key = row["group"] + ":" + scenario + ":" + arrangement
                presets[key] = review_multi_tier_template(catalog, row["group"], scenario, p)
    output.mkdir(parents=True, exist_ok=False)
    (output / "project-and-room-catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "hypothetical-results.json").write_text(
        json.dumps(presets, ensure_ascii=False) + "\n"
    )
    # All report tables and drawings consume the persisted deterministic results.
    catalog = json.loads((output / "project-and-room-catalog.json").read_bytes())
    presets = json.loads((output / "hypothetical-results.json").read_bytes())
    shown = {key: presentation(value) for key, value in presets.items()}
    page = render_page(catalog, shown)
    (output / "index.html").write_text(page)
    rows = [
        "# R11 R4 · 五层格口模型与真实更衣室评审",
        "",
        "## 实际项目结论",
        "",
        "8组房间全部 INPUT_REQUIRED。实际五层五门、每人独立格口已由本轮Owner确认；约300mm格高只是参考，实际柜型、宽深总高、隔断、并发操作人数、门扇和内部通行均未审定。快照通过仅说明指定假设下的静态占用与通道条件成立，不是 CONDITIONAL_FIT。",
        "",
        "原20t成品/天的R3项目审阅绑定原样复用，未改Owner V2通用规则。默认两班设计人数各53，106是独立储物格口需求，不是106个落地柜体；仍保留53人同时在室。",
        "",
        "## 分层实体与分隔方案",
        "",
        "物理柜体单元 → 竖向柜列 → 5个独立门格口 → 设计人员分配。厂家可将多列组合成一个实体柜，因此22列不能自动等同于22个实际柜体。每班独立列，不借用另一班备用格口；设计编号不是人员名册。",
        "",
        "|方案|每人格口|各班需求|各班列数|总列|容量|各班备用|洁污满足|",
        "|---|---:|---|---|---:|---:|---|---|",
    ]
    for d in catalog["demands"].values():
        rows.append(
            f"|{d['scenario']}|{d['compartments_per_person']}|{d['required_compartments_per_shift']}|{d['columns_per_shift']}|{d['total_columns']}|{d['total_capacity']}|{d['spare_per_shift']}|INPUT_REQUIRED|"
        )
    rows += [
        "",
        "单格内部分隔方案只保留分隔需求，虚线不代表隔板厚度、两侧有效容积或卫生效果已证明。两格/人方案将工衣、私衣分别分配独立门格口，但交叉污染控制、操作顺序及洁污分区仍需工程确认。",
        "",
        "## 仅用于敏感性演示的参数",
        "",
        "列宽400mm、深500mm、总高1800mm；格口参考净高300mm、底座100mm、层板20mm；每实体柜1列；净通道1200mm；柜前操作深600mm；人员占位400×600mm；柜前最多11人并发；其余人仍在室并有独立占位。无座凳、完成面内缩0、净高3000mm、操作可达高度100–1700mm、柜门与房门无内侵均是 HYPOTHETICAL_NOT_APPROVED。不能把这些数值写入真实设计Authority。",
        "",
        "每列同一时刻最多一人操作，不因五层格口叠放就同时在同一地面安排五人。各班逐批覆盖全部已分配格口，USE/SHIFT_CHANGE每批始终保留53人；清洁/维护另用一名假设工作人员，生产人员离室也是待审假设。清洁/维护按列核对全部五层的假设可达高度与操作占位，但实际维护方式、梯具及转移路径尚未评估。",
        "",
        "## 8组真实矩形，原门洞逐记录复核",
        "",
        "|组|记录/Handoff|实际mm|分隔方案|排布|必要柜排长mm|柜深+净通道必要宽mm|假设模板状态|失败快照|实际功能|",
        "|---|---|---|---|---|---:|---:|---|---:|---|",
    ]
    for key, r in presets.items():
        b = r["room"]["local_bounds_mm"]
        rows.append(
            f"|{r['group']}|{'/'.join(r['records'])}/H{r['handoff']}|{b[2]}×{b[3]}|{r['demand']['scenario']}|{r['parameters']['arrangement']}|{r['column_row_length_mm']}|{r['required_width_mm']}|{r['geometry_status']}|{r['failed_snapshot_count']}|INPUT_REQUIRED|"
        )
        slug = key.replace(":", "-").lower()
        (output / (slug + "-plan.svg")).write_text(shown[key]["plan_svg"])
        if r["group"] == "G01":
            for shift in (1, 2):
                (output / (slug + f"-shift-{shift}-elevation.svg")).write_text(
                    shown[key]["shift_elevations"][str(shift)]
                )
                selected = next(
                    (
                        s
                        for s in r["snapshots"]
                        if s["witness"]["shift"] == shift and "USE" in s["witness"]["states"]
                    ),
                    None,
                )
                if selected:
                    (output / (slug + f"-shift-{shift}-use.svg")).write_text(
                        shown[key]["snapshot_svgs"][selected["id"]]
                    )
    rows += [
        "",
        "## H5/H6的新柜型结论",
        "",
        "H5 G01（P01/P02，同一26.331×3.250m矩形）必须分别保留两份原Access读数。五层柜大幅改变了地面占用模型；表中通过的假设快照需要两班错峰、当前活动柜列之外格门关闭、零门扇内侵等条件。并未证明完整人员换位路径、排队吞吐、53人更衣动作、竖向操作人体工学、维护梯具或洁污隔断，不能批准功能适用。",
        "",
        "H6七组矩形短边1008–1015mm。示例单侧500mm柜深+1200mm净通道需1700mm，双侧需2200mm，均超出短边；且柜前/人员操作会另需空间。新柜型不能再使用旧“长度最多99柜<106”的拒绝理由：格口竖向叠放后，短边与实际净通道成为本次指定模板的明确冲突。未审柜型不能由这些假设推导所有布局均不可行。",
        "",
        "## 边界及后续设计输入",
        "",
        "全部柜门、人员、操作区、座凳和两处原Portal通行包络分别检查；人员不得占据净通道。每个操作人员必须关联其本班格口与所属柜列。任何失败保留具体组件ID。通过快照仍不证明动态换位、疏散或四状态的完整运行能力；真实数据未齐时从不返回CONDITIONAL_FIT。",
        "",
        *["- " + v for v in catalog["missing_inputs"]],
        "",
        "## 浏览和复算",
        "",
        "直接打开 index.html 可切换全部保存方案、两班及各批次。自定义参数请使用下列命令启动仅本机的假设预览；该接口不接受项目事实、source_label或批准状态。",
        "",
        "```bash",
        "cd backend",
        "PYTHONPATH=src:scripts uv run python scripts/build_r11_r4_multi_tier_review.py --serve-existing ../docs/previews/v2.2.2/r11-r4-multi-tier-locker-review-r1 --port 52990",
        "```",
        "",
        "源码和评审不调用原MAIN/Store，不执行Native；原R3实现、历史9记录/8矩形、P1、工程验收、九/十二指标及原始资源账本不变。未来任何已审功能尺寸转为P2约束须另经工程确认及显式版本化接线，本轮无此行为。",
    ]
    (output / "review-report.md").write_text("\n".join(rows) + "\n")
    receipt = dict(
        task=catalog["task"],
        project_functional_status="INPUT_REQUIRED",
        source_records=9,
        physical_groups=8,
        base_columns=22,
        base_capacity=110,
        two_compartment_columns=44,
        two_compartment_capacity=220,
        simultaneous_room_users=53,
        cabinet_front_concurrency="INPUT_REQUIRED",
        native_solves=0,
        source_approval="OWNER_CONFIRMED_FORM_ONLY",
        all_geometry_parameters="HYPOTHETICAL_NOT_APPROVED",
        new_main=False,
        new_grant=False,
        new_claim=False,
        full_ci="NOT_REQUESTED",
        historical_changed=False,
    )
    (output / "final-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    )
    derived = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()
    }
    (output / "source-manifest.json").write_text(
        json.dumps(dict(source_files=sources, derived_files=derived), ensure_ascii=False, indent=2)
        + "\n"
    )
    return catalog, page


def main() -> None:
    cp_model.CpSolver.solve = forbidden_native
    cp_model.CpSolver.Solve = forbidden_native
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--serve-existing", type=Path)
    parser.add_argument("--port", type=int, default=52990)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    if args.serve_existing:
        catalog = json.loads((args.serve_existing / "project-and-room-catalog.json").read_bytes())
        serve_review(catalog, (args.serve_existing / "index.html").read_text(), args.port)
    elif args.archive and args.output:
        catalog, _page = write_review(repo, args.archive, args.output)
        print(
            json.dumps(
                dict(
                    output=str(args.output.resolve()),
                    native_solves=0,
                    groups=len(catalog["groups"]),
                )
            )
        )
    else:
        parser.error("provide --archive and --output, or --serve-existing")


if __name__ == "__main__":
    main()
