"""Fresh, guarded, read-only H5 complete ten-door cabinet report."""

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from build_r11_r10_reverse_sizing_review import guarded_reexec

from cold_storage.modules.layout.application.physical_room_calibration_review import (
    calibration_context,
)
from cold_storage.modules.layout.application.ten_door_locker_review import (
    BASE_HEAD,
    SOURCE_PATH,
    TASK,
    review_ten_door_selection,
)
from cold_storage.modules.layout.infrastructure.physical_calibration_evidence import (
    read_calibration_evidence,
)
from cold_storage.modules.layout.infrastructure.ten_door_locker_page import (
    complete_elevation,
    complete_plan,
    review_page,
)


def allocation_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(
            unit_id=c["unit_id"],
            column_id=c["column_id"],
            tier=c["tier"],
            shift=c["shift"],
            person_id=c["assigned_person_id"],
            compartment_id=c["id"],
            door_id=c["independent_door_id"],
            purpose=c["purpose"],
            net_dimensions_status=c["net_dimensions_status"],
        )
        for c in report["inventory"]["compartments"]
    ]


def summary_report(report: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for c in report["reports"]:
        g = c["geometry"]
        u = g["inventory"]["cabinet_units"]
        closed = (
            all(f["completed_users"] == 53 for f in c["closed_door_flows"])
            and len(c["closed_door_flows"]) == 2
        )
        rows.append(
            dict(
                **{
                    k: c[k]
                    for k in (
                        "id",
                        "label",
                        "conditions",
                        "margin_target_mm",
                        "room_dimensions_mm",
                        "area_mm2",
                        "home_count",
                        "missing_home_count",
                        "completed_users",
                        "closed_door_evidence_hash",
                        "actual_functional_status",
                    )
                },
                installed_cabinet_run_mm=max(x["bounds_mm"][2] for x in u)
                - min(x["bounds_mm"][0] for x in u),
                cabinet_footprint_mm2=g["metrics"]["cabinet_footprint_mm2"],
                effective_installation_mm=g["parameters"]["installation_gap_mm"],
                effective_unit_gap_mm=g["parameters"]["unit_gap_mm"],
                effective_aisle_mm=g["parameters"]["aisle_mm"],
                conditional_reach_mm=g["conditional_reach_mm"],
                door_faces_height_scope=(
                    "100..1780mm CONDITIONAL_NOMINAL_FACE_PLACEMENT_NOT_NET_HEIGHT"
                ),
                closed_status="CLOSED_DOOR_MOVEMENT_PASS_ONLY"
                if closed
                else "NOT_EVALUATED_STATIC_REJECTED"
                if not c["closed_door_flows"]
                else "CLOSED_DOOR_MOVEMENT_BLOCKED",
                closed_door_minimum_observed_margin_mm=c["minimum_observed_margin_mm"],
                closed_door_limiting_location=c["margins"]["minimum_declared_spatial_margin"],
                static_conflicts=g["waiting_evaluation"]["conflicts"]
                + g["waiting_clearance_conflicts"]
                + g["hierarchy_failures"],
                portal_readbacks=g["waiting_evaluation"]["portal_results"],
                door_profiles=[
                    dict(
                        hinges=p["hypothesis"]["hinges"],
                        hypothesis=p["hypothesis"],
                        **p["combined"],
                        witness_hash=p["witness_hash"],
                        checked_open_events=p["doors"]["checked_open_events"],
                        served_compartments=p["doors"]["served_compartments"],
                    )
                    for p in c["door_profiles"]
                ],
            )
        )
    return dict(
        task=TASK,
        base_head=BASE_HEAD,
        owner_selection=report["owner_selection"],
        reports=rows,
        allocation=allocation_rows(report),
        difference=report["difference_from_400_500_reference"],
        storage_function_checks=report["storage_function_checks"],
        actual_door_records=report["actual_door_records"],
        missing_inputs=report["missing_inputs"],
        physical_room_count=1,
        historical_records=["P01", "P02"],
        actual_calibration="INPUT_REQUIRED",
        engineering_approval="NOT_EVALUATED",
        factory_applicability="NOT_EVALUATED",
        native_solves=0,
        main_executed=False,
        real_grant_claim=False,
    )


def report_markdown(s: dict[str, Any]) -> str:
    lines = [
        "# H5 · Owner选定五层十门柜实物建模",
        "",
        f"TASK_ID={TASK}",
        f"BASE_HEAD={BASE_HEAD}",
        "",
        "Owner选择850×390×1800mm标称整柜。原照片文件不可获取，照片Hash=null，照片证据INPUT_REQUIRED。选型不等于供应商技术审核/采购验收。400×360×320mm只是Owner转述图片中的标称标签，不是内部净尺寸。",
        "",
        "11台完整双列五层柜，22列110格；两班各55格，其中各53人分配独立格口、各2格备用。U06两列分属两班，但整柜只有一个实体身份。无单列半柜，无跨班共享格口，未引入12台方案。",
        "",
        "所有以下尺寸与流程均为条件模拟：425mm均分前缘非净宽；450×650mm人员、600×900mm活动、1200mm基准通道与余量、柜门400×320mm叶片/15mm厚、100mm底部/20mm层间隙、左铰链或镜像90°均未技术确认。层位100..1780mm，条件参考取放范围100..1800mm及水平600mm不是已批准人体可达性。不能借此认定储物或人体工学满足。",
        "",
        "| 同条件案例 | 本位/缺口 | 两班已完成 | 闭门子校核 | 左开/镜像联合流程 | "
        "联合最小余量下界 / 目标 |",
        "|---|---|---|---|---|---|",
    ]
    for c in s["reports"]:
        p = c["door_profiles"][0]
        lines.append(
            f"| {c['id']} | {c['home_count']}/53；缺{c['missing_home_count']} | "
            f"{c['completed_users']} | {c['closed_status']} | "
            + " / ".join(x["status"] for x in c["door_profiles"])
            + f" | {p['minimum_declared_margin_lower_bound_mm']}mm / "
            f"{c['margin_target_mm']}mm；达到目标={p['margin_target_met']} |"
        )
    lines += [
        "",
        "每组C/3850mm使用相同柜体与人体/完成面/安装输入，全部新算；没有套用R10/R13的旧PASS。新Hash绑定Owner来源、原历史源Hash、当前几何/全部两班事件/逐门开柜子校核。",
        "",
        "闭门状态复用原R10柜体/人员/Portal/连续通行子校核；它不是开门通过依据。R14单独检查110个门的独立身份，并在两班106人每人取放两次、共212个人-开柜事件中检查完整三维扇形与真实剩余人员/固定柜体/通道/其他同时打开门的冲突。只有两个子校核均通过才形成指定假设下的联合流程PASS。实际未知门型、内部净格和工艺仍INPUT_REQUIRED。",
        "",
        "柜门额外余量采用原解析四分之一圆盘+厚度检查，并单列包围盒间隙下界。联合最小余量包含该新增门扇项，不能用闭门50mm余量掩盖开柜后更小余量。该下界不是人体工学净距或规范限值。",
        "",
        "30/40mm组失败保留：C/3850未形成53个本位，因此未进入完整流程；没有减少人数、缩小人体或删除净通道。仅此有限模板失败，不是全局不可行。",
        "",
        "## 标称柜体与旧模型的差异",
        "",
        "旧22列400×500mm合计外包络面积4.400000㎡、累计列宽8800mm；新11台850×390mm合计3.646500㎡、累计柜宽9350mm。面积减少0.753500㎡、累计宽度增加550mm、外深减少110mm。实际安装排长还包括柜间隙，不能只用面积下降宣称功能改善。",
        "",
        "| 案例 | 有效安装间隙 | 有效柜间隙 | 保留通道 | 实际柜排长度 |",
        "|---|---:|---:|---:|---:|",
    ]
    for c in s["reports"]:
        lines.append(
            f"| {c['id']} | {c['effective_installation_mm']}mm | "
            f"{c['effective_unit_gap_mm']}mm | {c['effective_aisle_mm']}mm | "
            f"{c['installed_cabinet_run_mm']}mm |"
        )
    lines += [
        "",
        "## 储物与外部工程边界",
        "",
        "110>=106仅是容量算术。各层真实净宽/净深/净高尚无证据，不能把360mm或320mm标签当净值。无衣杆/额外层板0为图片转述，不自动增加隔板。工作服/私人衣物分隔、折叠衣物规格与取出空间、最高最低格口可达、固定与维护条件均待确认。",
        "",
        "原P01/P02对应一个H5物理房间，面积不重复计算。C=93.475050㎡、3850=101.374350㎡均为独立反事实尺寸，不改原85.575750㎡历史H5。R12原始叠加在构造上下文时独立复核；未重新验证的外部Access、Site/Footprint最终适用及洁污流程不作PASS。B历史3.338㎡通道与0.982㎡禁建区冲突原样保留。",
        "",
        "## 待补资料",
        "",
        *["- " + m for m in s["missing_inputs"]],
        "",
        "ACTUAL_CALIBRATION=INPUT_REQUIRED",
        "ENGINEERING_APPROVAL=NOT_EVALUATED",
        "FACTORY_APPLICABILITY=NOT_EVALUATED",
        "",
        "本轮无Native/MAIN/真实Grant/Claim/正式完整CI。既有自动快速CI保留原合成Native测试，"
        "不能将继承CI虚报为全程零Native。原R3～R13源码、证据、P1、Stage B、九/十二指标、"
        "MCP与生产默认未改。",
    ]
    return "\n".join(lines) + "\n"


def write_review(root: Path, output: Path) -> dict[str, Any]:
    root = root.resolve()
    output = output.resolve()
    previews = root / "docs/previews/v2.2.2"
    if (
        output.exists()
        or output.is_relative_to(root / "docs/evidence")
        or output.is_relative_to(previews)
        and not output.is_relative_to(previews / "r11-r14-ten-door-locker-r1")
    ):
        raise ValueError("FRESH_R14_OUTPUT_OUTSIDE_HISTORICAL_EVIDENCE_REQUIRED")
    ctx = calibration_context(read_calibration_evidence(root))
    raw = review_ten_door_selection(ctx, (root / SOURCE_PATH).read_bytes())
    summary = summary_report(raw)
    output.mkdir(parents=True)

    def write(name: str, obj: Any) -> None:
        (output / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")

    write("owner-selection.json", raw["owner_selection"])
    write("review-summary.json", summary)
    write(
        "actual-missing-physical-inputs.json",
        dict(
            actual_doors=raw["actual_door_records"],
            checks=raw["storage_function_checks"],
            missing=raw["missing_inputs"],
        ),
    )
    (output / "full-new-witnesses.json.gz").write_bytes(
        gzip.compress(
            json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(),
            mtime=0,
        )
    )
    with (output / "compartment-allocation.csv").open("w", newline="") as stream:
        rows = allocation_rows(raw)
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    for case in raw["reports"]:
        for suffix, svg in (
            ("plan", complete_plan(case)),
            ("doors", complete_plan(case, doors=True)),
            ("elevation", complete_elevation(case)),
        ):
            (output / f"{case['id']}-{suffix}.svg").write_text(svg)
    (output / "index.html").write_text(review_page(summary))
    (output / "engineering-report.md").write_text(report_markdown(summary))
    source = {**ctx["source_hashes"], SOURCE_PATH: raw["owner_selection"]["source_sha256"]}
    producer = [
        *sorted(root.glob("backend/src/cold_storage/modules/layout/*/ten_door_locker*.py")),
        Path(__file__).resolve(),
    ]
    source.update(
        {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in producer}
    )
    derived = {
        str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in output.rglob("*")
        if p.is_file()
    }
    write(
        "source-manifest.json",
        dict(
            base_head=BASE_HEAD,
            source_files=source,
            derived_files=derived,
            physical_room_count=1,
            actual_calibration="INPUT_REQUIRED",
            native_solves=0,
            historical_records_changed=False,
        ),
    )
    return summary


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    code = guarded_reexec(a.output.parent / (a.output.name + "-native-guard"))
    if code is not None:
        return code
    result = write_review(Path(__file__).resolve().parents[2], a.output)
    print(
        json.dumps(
            dict(
                output=str(a.output.resolve()),
                cases=[
                    dict(
                        id=r["id"], home_count=r["home_count"], completed_users=r["completed_users"]
                    )
                    for r in result["reports"]
                ],
                actual_calibration=result["actual_calibration"],
            ),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
