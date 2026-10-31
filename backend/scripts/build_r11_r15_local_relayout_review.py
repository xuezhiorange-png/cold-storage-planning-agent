# ruff: noqa: E501 -- engineering report prose
"""Fresh R15 source/clearance/local review. Original photo is never published."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from build_r11_r10_reverse_sizing_review import guarded_reexec

from cold_storage.modules.layout.application.physical_room_calibration_review import (
    calibration_context,
)
from cold_storage.modules.layout.application.ten_door_locker_review import SOURCE_PATH as R14_SOURCE
from cold_storage.modules.layout.application.ten_door_relayout_review import (
    BASE_HEAD,
    PHOTO_FILENAME,
    SOURCE_PATH,
    TASK,
    review_local_relayout,
)
from cold_storage.modules.layout.infrastructure.physical_calibration_evidence import (
    read_calibration_evidence,
)
from cold_storage.modules.layout.infrastructure.ten_door_relayout_evidence import (
    R14,
    read_r14_archive,
)
from cold_storage.modules.layout.infrastructure.ten_door_relayout_page import (
    case_plan,
    clearance_svg,
    comparison_plan,
    review_page,
)


def summarize(raw: dict[str, Any]) -> dict[str, Any]:
    result = {k: v for k, v in raw.items() if k not in {"reports", "archived_baseline"}}
    result["reports"] = [
        dict(
            id=r["id"],
            organization=r["organization"],
            home_count=r["home_count"],
            static_status=r["geometry"]["static_status"],
            static_conflicts=(
                r["geometry"]["waiting_evaluation"]["conflicts"]
                + r["geometry"]["waiting_clearance_conflicts"]
                + r["geometry"]["hierarchy_failures"]
            ),
            completed_users=[f["completed_users"] for f in r["closed_door_flows"]],
            initial_people=[f["initial_service_occupancy"] for f in r["closed_door_flows"]],
            blockers=[f["blocker"] for f in r["closed_door_flows"]],
            profiles=[
                dict(
                    hinges=p["hinges"],
                    combined=p["combined"],
                    checked_open_events=p["doors"]["checked_open_events"],
                    complete_106_person_coverage=p["doors"]["complete_106_person_coverage"],
                    minimum_door_clearance=p["doors"]["minimum_door_clearance_lower_bound"],
                )
                for p in r["profiles"]
            ],
            closed_margin=r["margins"]["minimum_declared_spatial_margin"],
            coordinate_diff=r["coordinate_diff"],
            witness_hash=r["witness_hash"],
        )
        for r in raw["reports"]
    ]
    return result


def engineering_report(s: dict[str, Any]) -> str:
    lines = [
        "# R11 R15 · 11台十门柜有限重排和柜门距离复核",
        "",
        f"TASK_ID={TASK}",
        f"BASE_HEAD={BASE_HEAD}",
        "",
        "## 结论",
        "",
        f"有限检查{s['actual_candidates']}组（硬上限{s['candidate_limit']}，不超过36）；完成两班各53人联合条件流程的组合：{s['complete_candidate_ids']}。选作坐标变化较少的评审对象：{s['selected_candidate_id']}。",
        "静态本位、闭门运动、逐门开启与100mm目标分别报告。新完成组的柜门条件下界为65mm，仍小于100mm目标；没有降低目标、人体尺寸、53人设计基准或1300mm有效通道。不能宣称全部严格空间余量满足或实际功能获批。",
        "",
        "## 照片来源",
        "",
        f"Owner提供文件名 IMG_0875.jpeg 及期望SHA256 `{s['photo_source_supplement']['owner_reported_sha256']}`；原始字节独立核对状态：`{s['photo_source_supplement']['photo_file_evidence']}`，实际字节Hash=`{s['photo_source_supplement']['actual_photo_sha256']}`。",
        "原件未取得时保持照片INPUT_REQUIRED，不把文字Hash写成原图已验证。不公开、嵌入或复制原照片。独立补充记录关联R14选型来源，不覆盖R14。图片标称400×360×320mm不是内部净格尺寸；照片即使核对成功也不证明铰链、门厚、开启角度或储物卫生。",
        "",
        "## 有限几何与真实流程",
        "",
        "只检查南侧网格相位（旧网格/按南门通道边对齐/额外目标退让）、北侧本位行（旧位置/对齐东侧等待行间隔）、两种行填充顺序的3×2×2组合。柜体、柜列、格口分配、原两处Portal、全部参数及建筑边界保持不变。53静态本位成立的每组都重新调用原连续运动与完整两班流程，不因动态失败跳过或重写结果。",
        "北侧行的对齐由实际东侧本位上边界加200mm等待间隔得到，不使用历史人员坐标作为强制解。所有本位和路由都由本次候选生成。不同填充顺序会改变真实人员对应本位；3个NORTH_FIRST组合静态53通过却在进入/旋转接近路径碰到仍在场的人员，原错误及具体扫掠体积保留。",
        "",
        "|组合|本位|两班完成|联合条件流程|最低下界/目标|",
        "|---|---:|---|---|---|",
    ]
    for r in s["reports"]:
        p = r["profiles"][0]
        lines.append(
            f"|{r['id']}|{r['home_count']}|{r['completed_users']}|{p['combined']['status']}|{p['combined']['minimum_declared_margin_lower_bound_mm']}/100mm；满足={p['combined']['margin_target_met']}|"
        )
    lines += [
        "",
        "每个完成方案均保留11台完整850×390×1800mm柜、22列110格、每班55格（53人+2备用），U06左右列分配不同班次且柜体不拆。两班分别初始53人、完成53人；每人取放各一次，共212个人开门事件；ALL_LEFT与MIRRORED分别新算。使用原始人员连续路径/全高旋转方形包络、净通道、柜体与其他剩余人员碰撞、Portal及独立三维柜门校核。柜门关闭后才移动，更衣600×900活动与开柜450×650运输人体是不同工序，不能声称任意动作/同时开柜均成立。",
        "",
        "## 15mm独立解析审查",
        "",
        "R14最不利：第一班E110、S1-B01、OPEN_FOR_RETRIEVE，U01-L-T1-DOOR（第一层z100..420mm），对应S1-P001（人体[795,910,0,1245,1560,1800]mm），假设左铰链[807,480]mm、叶宽400mm、保守厚度15mm、90°。同期开门还包括U02/U03/U04的左列第一层；实际通道和其他人员在原事件中逐项保留。",
        "新距离函数不改原碰撞器。原模型是四分之一圆盘与[-厚度,+厚度]方形的Minkowski和；把厚度方形移到目标矩形后，求目标至两条半径线段和圆弧的最小距离。整数平方根提供0.001mm包络，绘图折线不参与证明。在最不利事件中，原15mm包围盒下界与这个保守厚度模型的解析距离恰好相等（[15000,15000]×0.001mm），原解析碰撞为false；因此不能借更紧算法把它提升到50mm。该距离也不等于真实五金或真实人体动作的可用净距。50mm仍是未批准敏感性目标，不是规范。",
        "完整事件、门层/铰链/扫掠、人体体积、更衣阶段、保留通道及同时打开门在clearance-analysis.json和局部比例图中提供。实际铰链、厚度、角度与人体活动未批准，真实柜门功能保持INPUT_REQUIRED。",
        "",
        "## 保留历史与外部边界",
        "",
        "R14原20/20目标50的C、3850均53人条件流程完成、柜门15mm下界；30/40目标100的C38本位、385052本位原样保留。新R15见证及Hash独立保存。有限12组不是全局搜索，不能由模板失败推出房间全局不可行。",
        "本任务不扩大原反事实3850mm房间、不改原封存H5、R3～R14、P01/P02、P1、Stage B、九/十二比较器、MCP或生产默认。外部工程不从本次室内功能模拟升级为PASS。",
        "",
        "## 待确认输入",
        "",
        *["- " + m for m in s["missing_inputs"]],
        "",
        "ACTUAL_CALIBRATION=INPUT_REQUIRED",
        "ENGINEERING_APPROVAL=NOT_EVALUATED",
        "FACTORY_APPLICABILITY=NOT_EVALUATED",
        "",
        "本地显式白名单与生成器使用父子Python启动级Native禁用。自动快速CI保留原合成Native，不能声称整个继承CI零Native。没有新增20t Native、MAIN、真实Grant/Claim或正式完整CI，不Ready/Merge/Deploy。",
    ]
    return "\n".join(lines) + "\n"


def write_review(root: Path, output: Path, photo: Path | None = None) -> dict[str, Any]:
    root, output = root.resolve(), output.resolve()
    previews = root / "docs/previews/v2.2.2"
    allowed = previews / "r11-r15-ten-door-local-relayout-r1"
    if (
        output.exists()
        or output.is_relative_to(root / "docs/evidence")
        or output.is_relative_to(previews)
        and output != allowed
    ):
        raise ValueError("FRESH_R15_OUTPUT_OUTSIDE_HISTORICAL_EVIDENCE_REQUIRED")
    if photo is not None and photo.name != PHOTO_FILENAME:
        raise ValueError("EXPLICIT_ORIGINAL_PHOTO_FILENAME_REQUIRED")
    ctx = calibration_context(read_calibration_evidence(root))
    archived = read_r14_archive(root)
    raw = review_local_relayout(
        ctx,
        archived,
        (root / R14_SOURCE).read_bytes(),
        (root / SOURCE_PATH).read_bytes(),
        photo.read_bytes() if photo else None,
    )
    summary = summarize(raw)
    output.mkdir(parents=True)

    def save(name: str, value: Any) -> None:
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    save("review-summary.json", summary)
    save("photo-source-supplement.json", raw["photo_source_supplement"])
    save("clearance-analysis.json", raw["clearance_traces"])
    save("coordinate-difference.json", {r["id"]: r["coordinate_diff"] for r in raw["reports"]})
    (output / "full-new-witnesses.json.gz").write_bytes(
        gzip.compress(
            json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(),
            mtime=0,
        )
    )
    base = raw["archived_baseline"]
    (output / "original-52-plan.svg").write_text(case_plan(base))
    (output / "r14-worst-clearance.svg").write_text(clearance_svg(raw["clearance_traces"][0]))
    for r in raw["reports"]:
        (output / f"{r['id']}-plan.svg").write_text(case_plan(r))
        (output / f"{r['id']}-doors.svg").write_text(case_plan(r, doors=True))
        (output / f"{r['id']}-difference.svg").write_text(comparison_plan(base, r))
    (output / "index.html").write_text(review_page(summary))
    (output / "engineering-report.md").write_text(engineering_report(summary))
    source = {
        **ctx["source_hashes"],
        SOURCE_PATH: raw["photo_source_supplement"]["supplement_source_sha256"],
        R14_SOURCE: raw["photo_source_supplement"]["r14_selection_source_sha256"],
    }
    producers = [
        *sorted(root.glob("backend/src/cold_storage/modules/layout/*/ten_door_*relayout*.py")),
        root / "backend/src/cold_storage/modules/layout/domain/ten_door_sweep_clearance.py",
        Path(__file__).resolve(),
        root / R14 / "source-manifest.json",
        root / R14 / "full-new-witnesses.json.gz",
    ]
    source.update(
        {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in producers}
    )
    save(
        "source-manifest.json",
        dict(
            base_head=BASE_HEAD,
            source_files=source,
            derived_files={
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.iterdir())
                if p.is_file()
            },
            original_photo_published=False,
            native_solves=0,
            historical_records_changed=False,
        ),
    )
    return summary


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--photo", type=Path, help="Private original bytes; never copied to output")
    a = p.parse_args()
    code = guarded_reexec(a.output.parent / (a.output.name + "-native-guard"))
    if code is not None:
        return code
    s = write_review(Path(__file__).resolve().parents[2], a.output, a.photo)
    print(
        json.dumps(
            dict(
                output=str(a.output.resolve()),
                candidates=s["actual_candidates"],
                complete=s["complete_candidate_ids"],
                selected=s["selected_candidate_id"],
                photo=s["photo_source_supplement"]["photo_file_evidence"],
                actual_calibration=s["actual_calibration"],
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
