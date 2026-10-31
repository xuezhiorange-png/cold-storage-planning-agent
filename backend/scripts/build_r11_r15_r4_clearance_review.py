# ruff: noqa: E501 -- engineering report prose
"""Export at most six local checks with original non-Native full-flow evidence."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from build_r11_r10_reverse_sizing_review import guarded_reexec

from cold_storage.modules.layout.application.ten_door_clearance_review import (
    BASE_HEAD,
    TASK,
    review_local_clearance,
)
from cold_storage.modules.layout.infrastructure.ten_door_clearance_evidence import (
    R15,
    read_r15_archive,
)
from cold_storage.modules.layout.infrastructure.ten_door_clearance_page import (
    coordinate_comparison,
    plan_svg,
    review_page,
    section_svg,
)

DIRECTORY = "r11-r15-r4-local-clearance"


def summarize(raw: dict[str, Any]) -> dict[str, Any]:
    result = {k: v for k, v in raw.items() if k not in {"source_geometry", "reports"}}
    result["reports"] = []
    for c in raw["reports"]:
        result["reports"].append(
            dict(
                id=c["id"],
                choice=c["choice"],
                section=c["section"],
                has_geometry=c["geometry"] is not None,
                static_status=c["static_status"],
                completed_users=[f["completed_users"] for f in c["closed_door_flows"]],
                initial_people=[f["initial_service_occupancy"] for f in c["closed_door_flows"]],
                completed_batches=[len(f["completed_batches"]) for f in c["closed_door_flows"]],
                event_counts=[len(f["events"]) for f in c["closed_door_flows"]],
                blockers=[f["blocker"] for f in c["closed_door_flows"]],
                full_flow_status=c["full_flow_status"],
                all_100_met=c["all_100_met"],
                exact_min_mm=[
                    p["analytic_distances"]["minimum"]["distance"]["model_distance_lower_um"] / 1000
                    if p["analytic_distances"]["minimum"] is not None
                    else None
                    for p in c["profiles"]
                ]
                or None,
                own_door_min_mm=[
                    min(
                        o["distance"]["model_distance_lower_um"]
                        for o in p["analytic_distances"]["own_person_openings"]
                    )
                    / 1000
                    if p["analytic_distances"]["own_person_openings"]
                    else None
                    for p in c["profiles"]
                ]
                or None,
                closed_min_mm=c["margins"]["minimum_declared_spatial_margin"]["extra_mm"]
                if c.get("margins", {}).get("minimum_declared_spatial_margin") is not None
                else None,
                margin_families=c.get("margins", {}).get("families", {}),
                profiles=[
                    dict(
                        hinges=p["hinges"],
                        combined=p["combined"],
                        checked_open_events=p["doors"]["checked_open_events"],
                        exact_minimum=p["analytic_distances"]["minimum"],
                        all_object_volume_checks=p["analytic_distances"][
                            "all_object_volume_checks"
                        ],
                    )
                    for p in c["profiles"]
                ],
                coordinate_diff=c.get("coordinate_diff"),
                witness_hash=c.get("witness_hash"),
            )
        )
    return result


def engineering_report(summary: dict[str, Any]) -> str:
    selected = summary["selected_candidate_id"]
    lines = [
        "# R11 R15 R4｜3850mm房间的柜前站位与支廊协调",
        "",
        f"TASK_ID={TASK}",
        f"BASE_HEAD={BASE_HEAD}",
        "",
        "## 结论与范围",
        "",
        f"六项预声明检查中，满足原完整条件流程和所有已声明100mm余量家族的最小位移方案为 **{selected}**。这是测试集合内最小站距位移，不是全局最优，也不是现场工程批准。",
        "R4-02：柜前站距480→515mm，柜前支廊中心线2440→2475mm；房间26331×3850mm、11台完整850×390×1800mm十门柜、22列110格、两班各53人、53人初始同时在室、450×650×1800行走人体、600×900×1800更衣体积、1300mm通道、200mm等待间隔、原两处1500mm Portal与所有53本位均不动。没有新增建筑面积。",
        "两班分别重新完成全部53人进入—到本人柜位—开柜取衣—关柜—站立更衣—开柜存物—关柜—离室。两种原90°门扇假设分别检查212次人员开柜，原碰撞校核全部保留。",
        "**条件距离100mm不是实测操作净距。100mm为未批准敏感性目标，不是规范下限。** 实际铰链/厚度/把手、弯腰伸手携衣、格口净尺寸、五层取放与卫生分隔仍INPUT_REQUIRED；外部Site/Access和扩大后3850mm房间的整厂适用性没有因本轮室内改进升级。",
        "",
        "## 局部尺寸链",
        "",
        "基准S1/E110/OPEN_FOR_RETRIEVE，U01-L-T1-DOOR与S1-P001。柜前缘y560mm，条件门扇最北边560+400+15=975mm；原人体y1040..1690mm，原关柜更衣体积y790..1690mm。",
        "只退人35mm：人体y1075..1725mm，门距1075−975=100mm；支廊南缘不变1790mm，更衣/静态人体至支廊只剩1790−1725=65mm。该项是必要断面负对照，未生成完整布局或成功见证；不把未达100目标称为碰撞或全局不可行。",
        "同步移支廊35mm：支廊y1825..3125mm，更衣至廊1825−1725=100mm；北侧本位下缘3225mm，本位至廊3225−3125=100mm；北侧本位上缘3675mm至完成面3820mm仍145mm。",
        "在保持原北侧本位的这个截面中，门距要求给出人员位移≥35，活动至廊要求支廊位移≥人员位移，北侧本位至廊要求支廊位移≤35；因此该截面下35/35是同时满足目标的边界值。它不替代完整路径和事件校核。",
        "",
        "## 六项对照（含原基线及一个断面负对照）",
        "",
        "|编号|人员/支廊/北侧本位位移mm|本人门距 / 全对象最小解析距离mm|更衣至廊 / 北侧本位至廊mm|两班完成|完整流程与全部已声明100mm目标|",
        "|---|---|---|---|---|---|",
    ]
    for c in summary["reports"]:
        s = c["section"]
        lines.append(
            f"|{c['id']}|{c['choice']['operator_delta_mm']} / {c['choice']['branch_delta_mm']} / {s['north_home_delta_mm']}|{c['own_door_min_mm']} / {c['exact_min_mm']}|{s['gaps']['standing_activity_to_branch_mm']} / {s['gaps']['north_home_to_branch_mm']}|{c['completed_users']}|{c['full_flow_status']}；100目标={c['all_100_met']}|"
        )
    lines += [
        "",
        "R4-03实际两班流程仍完成，但北侧至廊仅85mm，不能以门距115mm宣称全部达标。R4-04将北侧行按新支廊边界+100mm并与东侧行保持200mm间隔的公式生成，北移15mm；R4-05北移45mm。它们没有修改既有成功事件坐标，而是先改变候选输入和布局，再重新生成快照、路径、动作与证明。",
        "R4-05本人门距145mm，但所有对象的真正保守模型最小解析距离是117mm（邻柜限制），不能把145mm写成全局最小。较大位移还减少了未批准的600mm水平可达参考差值，且消耗北侧余量；因此不作为最小调整推荐。",
        "",
        "## 原有流程、通道与距离复核",
        "",
        "五套实际几何（含零位移控制）均通过原validate_use与activity_proof静态检查，并调用原closed_door_flow/simulate_sizing_shift、relayout_transfer、portal_crossing。_schedule保留原完整柜列/人员绑定及交错排序，快照由原sizing_snapshot按新站距生成，支廊由相同参数自动联动。没有修改上述历史代码或工程判据。",
        "所有未完成人员在连续运动证明里始终作为碰撞对象保留。每班初始53人；完成/服务身份集合均为53，全部进入、两次取存开柜、更衣、离室记录保留。关门后才移动或更衣；没有将静态不重叠升级为真实人体动作验证。",
        "每种门假设、每套实际几何对原事件重新执行check_flow_doors：110个独立门身份、106个独立人员格口、212次必要开柜；另对每次开门的现场人员与其他柜体逐体积运行原certified_sweep_distance，共8148次距离核对/配置。距离是原保守四分之一圆盘加厚度模型的解析值，不依赖简化扫掠盒对任意位置都准确。原door_hits_box碰撞器没有替换。",
        "原闭门余量、人员至通道、更衣至通道、转身方形至通道、等待间距和门扇距离分别保存。R4-02最小已声明空间余量100mm；人员运动时进入通道是预期通行，不声称每种运动都具有统一100mm人体膨胀缓冲。原Portal宽减通道宽为200mm，左右各100mm。",
        "",
        "## 证据和复现",
        "",
        "- review-summary.json：六项状态、两班人数、余量家族、逐门最小值和见证Hash。",
        "- full-witnesses.json.gz：所有新几何、完整事件、连续路径扫掠、原校核输出、目标未达记录。",
        "- coordinate-difference.json：房间/柜体/Portal、本位、站位、支廊、路线和活动区变化。",
        "- R4-02-plan.svg / R4-02-difference.svg / R4-02-section.svg：完整平面、柜区叠加和最不利事件断面，均取实际输出坐标。",
        "- source-manifest.json：原157个来源/衍生文件与新增计算代码Hash；R15-03原见证单独绑定。",
        "- ../r11-r15-ten-door-local-relayout-r1/：原12组及失败轨迹原样保留，不重跑原生成器。",
        "",
        "复现（输出目录必须不存在）：",
        "",
        "```bash",
        "cd backend",
        "PYTHONPATH=src:scripts uv run python scripts/build_r11_r15_r4_clearance_review.py --output ../artifacts/r15-r4-fresh-review",
        "```",
        "",
        "生成器在运行前通过既有启动级保护重新执行，父子Python均禁用两种Native API；只接受固定六项目录，无照片参数、无MAIN、Store或Claim入口。定向测试见docs/evidence/v2.2.2/r11-r15-r4-local-clearance-validation/。自动快速CI继续包含原有合成Native测试，不能把整条继承CI虚报为零Native。",
        "",
        "## 待确认条件与执行状态",
        "",
        "实际柜门铰链/角度/厚度/把手、内净格口与衣物分隔、人体取放和穿脱动作、员工适配、固定维护和施工公差、洁污流程、实际房门与外部Access均待工程确认。站距515mm仅在既有600mm参考以内，不等于真实伸入柜内可达。",
        "照片R15 R2暂停NOT_EVALUATED；不搜索或验证图片，不改变旧不匹配记录。原P1、Stage B、九/十二比较器、生产默认、历史MAIN与R9边界异常均不改。",
        "",
        "ACTUAL_CALIBRATION=INPUT_REQUIRED",
        "ENGINEERING_APPROVAL=NOT_EVALUATED",
        "FACTORY_APPLICABILITY=NOT_EVALUATED",
        "NEW_NATIVE_SOLVES=0",
        "NEW_MAIN=false",
        "NEW_REAL_GRANT_CLAIM=false",
        "FULL_CI=NOT_REQUESTED",
        "READY=false",
        "MERGE=false",
        "DEPLOY=false",
        "",
    ]
    return "\n".join(lines)


def write_review(root: Path, output: Path) -> dict[str, Any]:
    root, output = root.resolve(), output.resolve()
    previews = root / "docs/previews/v2.2.2"
    if (
        output.exists()
        or output.is_relative_to(root / "docs/evidence")
        or output.is_relative_to(previews)
        and output != previews / DIRECTORY
    ):
        raise ValueError("FRESH_R15_R4_OUTPUT_REQUIRED_OUTSIDE_HISTORICAL_EVIDENCE")
    raw = review_local_clearance(read_r15_archive(root))
    summary = summarize(raw)
    output.mkdir(parents=True, exist_ok=False)

    def save(name: str, value: Any) -> None:
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    save("review-summary.json", summary)
    (output / "full-witnesses.json.gz").write_bytes(
        gzip.compress(
            json.dumps(raw, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(),
            mtime=0,
        )
    )
    baseline = raw["reports"][0]
    differences = {}
    for case in raw["reports"]:
        if case["geometry"] is None:
            continue
        old, new = raw["source_geometry"]["snapshots"][0], case["geometry"]["snapshots"][0]
        differences[case["id"]] = dict(
            case["coordinate_diff"],
            source_operator_mm=next(p["bounds_mm"] for p in old["people"] if p["id"] == "S1-P001"),
            new_operator_mm=next(p["bounds_mm"] for p in new["people"] if p["id"] == "S1-P001"),
            source_activity=old["front_activity_evaluation"]["activity_volumes"],
            new_activity=new["front_activity_evaluation"]["activity_volumes"],
            source_branch=old["branch_centerline_mm"],
            new_branch=new["branch_centerline_mm"],
            source_aisles=old["aisles"],
            new_aisles=new["aisles"],
            portals_unchanged=True,
        )
        (output / f"{case['id']}-plan.svg").write_text(plan_svg(case))
        (output / f"{case['id']}-difference.svg").write_text(coordinate_comparison(baseline, case))
        (output / f"{case['id']}-section.svg").write_text(section_svg(baseline, case))
    save("coordinate-difference.json", differences)
    (output / "engineering-report.md").write_text(engineering_report(summary))
    (output / "index.html").write_text(review_page(summary))
    source = json.loads((root / R15 / "source-manifest.json").read_bytes())
    files = {
        **source["source_files"],
        **{f"{R15}/{n}": d for n, d in source["derived_files"].items()},
    }
    producers = [
        root / R15 / "source-manifest.json",
        Path(__file__).resolve(),
        *sorted(
            (root / "backend/src/cold_storage/modules/layout").glob("*/ten_door_*clearance*.py")
        ),
    ]
    files.update(
        {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in producers}
    )
    save(
        "source-manifest.json",
        dict(
            task=TASK,
            base_head=BASE_HEAD,
            source_witness=raw["source_witness"],
            source_files=files,
            derived_files={
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.iterdir())
                if p.is_file()
            },
            original_photo_searched=False,
            photo_r2="PAUSED_NOT_EVALUATED",
            original_photo_published=False,
        ),
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    code = guarded_reexec(args.output.resolve().parent / (args.output.name + "-native-guard"))
    if code is not None:
        return code
    summary = write_review(Path(__file__).resolve().parents[2], args.output)
    print(
        json.dumps(
            dict(
                task=TASK,
                selected=summary["selected_candidate_id"],
                declared_checks=summary["declared_candidates"],
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
