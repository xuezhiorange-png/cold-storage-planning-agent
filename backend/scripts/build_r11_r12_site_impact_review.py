"""Read archived evidence and export deterministic overlays; no layout or route search."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from build_r11_r10_reverse_sizing_review import guarded_reexec

from cold_storage.modules.layout.application.functional_site_impact_review import (
    BASE_HEAD,
    R11_PATH,
    review_functional_site_impact,
)
from cold_storage.modules.layout.application.functional_sizing_sources import (
    HISTORICAL,
    HISTORICAL_FILES,
    R10,
)
from cold_storage.modules.layout.infrastructure.functional_site_impact_evidence import (
    read_site_impact_evidence,
)
from cold_storage.modules.layout.infrastructure.functional_site_impact_page import (
    overlay_svg,
    review_page,
)

SCHEMES = ("C", "3850", "B")
R11_CI = "docs/evidence/v2.2.2/r11-r12-source-preservation/r11-remote-ci"
R11_CI_SOURCES = (
    ("backend-regression.zip", "5148ccc2de597b3de70ee6c4e2b3ad9532bc5cbef43e1a57511ae1de002d192f"),
    ("backend-regression.xml", "da5a1408d1ff860b4912bd0bb7ee0e04bc81c72dda60f074c5cfa0dab1aa1b13"),
    ("verified-results.json", "3f007e1cb04299ccf9484a5f6b8ea3222175dc5382088c59dc620cf2744d2874"),
)


def write_review(root: Path, output: Path) -> dict[str, Any]:
    output = output.resolve()
    if output.exists() or any(output.is_relative_to(root / p) for p in (R11_PATH, R10, HISTORICAL)):
        raise ValueError("NEW_INDEPENDENT_SITE_IMPACT_OUTPUT_REQUIRED")
    files = read_site_impact_evidence(root)
    for name, sha in R11_CI_SOURCES:
        data = (root / R11_CI / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError("ORIGINAL_R11_REMOTE_EVIDENCE_MISMATCH")
        files[f"{R11_CI}/{name}"] = data
    candidates = {
        record: json.loads(files[f"{HISTORICAL}/{p}"])
        for record, p in zip(("P01", "P02"), HISTORICAL_FILES[2:], strict=True)
    }
    c = candidates["P01"]
    scope = c["source_zone_plan_hash"] + ":" + c["source_p1_handoff_hash"]
    result = review_functional_site_impact(
        files, project_scope_id=scope, candidate_records=candidates
    )
    output.mkdir(parents=True, exist_ok=False)

    def save(name: str, obj: Any) -> None:
        (output / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")

    save("site-impact.json", result)
    save("impact-matrix.json", result["impact_matrix"])
    save("owner-input-template.json", result["owner_parameter_template"])
    for r in result["records"]:
        (output / f"{r['record']}-original.svg").write_text(overlay_svg(r, 0, original_only=True))
        for i, name in enumerate(SCHEMES):
            (output / f"{r['record']}-{name}.svg").write_text(overlay_svg(r, i))
            (output / f"{r['record']}-{name}-detail.svg").write_text(overlay_svg(r, i, detail=True))
    # Each comparative SVG contains both independently sourced records at equal scale.
    for name in SCHEMES:
        panels = [(output / f"{r['record']}-{name}.svg").read_text() for r in result["records"]]
        parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 650">']
        for i, panel in enumerate(panels):
            panel = panel.replace("<svg ", f'<svg x="{i * 800}" y="0" width="800" height="650" ', 1)
            for identifier in ("forbidden", "collision"):
                panel = panel.replace(f'id="{identifier}"', f'id="{identifier}-{i}"').replace(
                    f"url(#{identifier})", f"url(#{identifier}-{i})"
                )
            parts.append(panel)
        (output / f"comparison-{name}.svg").write_text("".join(parts) + "</svg>")
    (output / "index.html").write_text(review_page(result))
    lines = [
        "# H5尺寸扩展的整厂空间影响预验证",
        "",
        f"TASK_ID={result['task']}",
        f"BASE_HEAD={BASE_HEAD}",
        "",
        "只读使用原20t回归输入、P01/P02的12区、原Site与原通道，不求解、不重规划、不改变原工程状态。两份候选分别读取和验证，但扩建面积按一个物理更衣室计算。",
        "",
        "| 原记录 | 方案 | 房间新增㎡ | 其他房间交集㎡ | 原通道交集㎡ | "
        "禁建/Hard去重交集㎡ | 净Footprint新增㎡ |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in result["impact_matrix"]:
        lines.append(
            f"| {r['record']} | {r['label']} | {r['additional_room_area_m2']} | "
            f"{r['other_zone_overlap_m2']} | {r['corridor_overlap_m2']} | "
            f"{r['prohibited_overlap_m2']} | {r['net_footprint_increase_m2']} |"
        )
    lines += ["", "## B的实际交集及影响", ""]
    for r in result["records"]:
        b = r["proposals"][2]
        for kind, report in [
            ("入口通道", b["corridor_intersections"]),
            ("禁建区（亦为Hard Obstacle）", b["site"]["obstacles"]["no_build_zones"]),
        ]:
            for hit in report["contacts"]:
                lines.append(
                    f"- {r['record']} {kind}：源边界{hit['object_bounds_mm']}mm；"
                    f"交集{hit['intersection_rectangles_mm']}mm；"
                    f"面积{hit['intersection_area_mm2']}mm² / {hit['intersection_area_m2']}㎡。"
                    f"来源{hit['reference']}；对象Hash {hit['object_hash']}。"
                )
    lines += [
        "",
        "受影响的是access:main_entrance->changing_room@1.0.0。B原入口通道需重新设计/验证，"
        "标记ARCHIVED_CORRIDOR_INTERSECTION_DETECTED。旧更衣室东Portal位于原墙线，"
        "条件Portal移到新东墙，旧通道末端已不在映射门洞上。"
        "南侧更衣室→分选包装间的原1500mm Portal及共享边几何保持；这不是完整Access复验通过。",
        "",
        "B还占用归档No-build Zone。该区域同时列在Hard Obstacles与No-build Zones中，"
        "按空间并集去重。结论只针对本次固定原通道、原禁建区的叠加；"
        "不宣布B全局不可行，不生成替代通道，不调整禁建Authority。",
        "",
        "## C及3850mm与边界",
        "",
        "两种向北扩展带分别计算，均未检测到与已归档其他房间、通道、"
        "Hard Obstacles和No-build Zones的正面积交集；三种条件房间均位于原Site/可建边界内。"
        "门洞坐标未变化不代表外部工程适用。所有方案最终整厂适用仍NOT_EVALUATED。",
        "",
        "## Footprint与原工艺",
        "",
        "先由每份候选的12区及原通道包络重现原Footprint，再求纯几何叠加并集。原建筑面积、周长、转折与凹角及新并集指标保存在JSON；正式九/十二指标比较器未调用或修改。B房间新增面积与净Footprint新增面积不同，是因为其中一部分覆盖原通道。即使并集周长减少，也不能称为工程质量改善。拓扑并集单连通/零孔洞仅是几何诊断，不能替代Site、通道和独立验收。七条原MUST共享边均按原图复查，不创建新工艺关系。",
        "",
        "## 缺失与未验证",
        "",
        "Truck Envelope在两份原候选中均为空且原Truck状态"
        "BLOCKED_PROJECT_MANEUVER_INPUT_REQUIRED，不把空数组当作Truck空间清晰证据，"
        "保留NOT_EVALUATED。未归档设备/其他占用不推断为空。"
        "未运行外部Access重规划或整厂工程复验。缺少某项几何时返回NOT_EVALUATED，"
        "篡改或跨项目来源则拒绝。",
        "",
        "## 条件与Owner输入",
        "",
        "C/B使用20mm完成面、20mm安装输入；3850mm使用30/40mm。三者保留原R10/R11建议Hash、条件与完整双班见证Hash，不作跨参数安全性或全局最优排序。实际功能保持INPUT_REQUIRED。复用R11原确认清单；参数模板的未知值为null，不创建Owner审批记录。已确认的两班各53人、53人同时在室、五层柜、柜前站立、无坐凳继续保留。",
        "",
    ]
    lines += ["- " + r["item"] + "：INPUT_REQUIRED" for r in result["owner_confirmation_checklist"]]
    lines += [
        "",
        "本轮新增功能不调用Native、MAIN、Grant/Claim或正式完整CI。继承自动快速CI的既有合成Native测试单独记录，不宣称所有CI测试都无Native。原R9异常、R10及R11来源和远端JUnit证据保留。",
        "",
    ]
    (output / "site-impact-report.md").write_text("\n".join(lines))
    save(
        "source-manifest.json",
        dict(
            base_head=BASE_HEAD,
            source_files={k: hashlib.sha256(v).hexdigest() for k, v in sorted(files.items())},
            derived_files={
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.iterdir())
                if p.is_file()
            },
            historical_files_modified=False,
            new_native_solves=0,
            new_main=False,
        ),
    )
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    guard = guarded_reexec(args.output.parent / (args.output.name + "-native-guard"))
    if guard is not None:
        raise SystemExit(guard)
    review = write_review(Path(__file__).resolve().parents[2], args.output)
    print(
        json.dumps(
            dict(
                records=review["independently_checked_records"],
                physical_rooms=review["physical_room_count"],
                factory_status=review["final_factory_applicability"],
            )
        )
    )
