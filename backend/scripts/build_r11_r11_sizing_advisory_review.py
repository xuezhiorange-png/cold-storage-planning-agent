"""Export a new, read-only advisory review from preserved evidence; no solving."""

import argparse
import hashlib
import io
import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from build_r11_r10_reverse_sizing_review import guarded_reexec

from cold_storage.modules.layout.application.functional_sizing_handoff import (
    CASE_KEYS,
    preview_functional_sizing_handoff,
)
from cold_storage.modules.layout.application.functional_sizing_sources import (
    BASE_HEAD,
    HISTORICAL,
    HISTORICAL_FILES,
    R10,
)
from cold_storage.modules.layout.domain.functional_sizing_advisory import advisory_json_schema
from cold_storage.modules.layout.infrastructure.functional_sizing_advisory_page import (
    historical_room_svg,
    review_page,
)
from cold_storage.modules.layout.infrastructure.functional_sizing_evidence import (
    read_functional_sizing_evidence,
)

SVG_FILES = (
    "C_less_building_change.svg",
    "width-only-robust-sensitivity.svg",
    "B_larger_margin.svg",
)


def write_review(root: Path, output: Path) -> dict[str, Any]:
    if output.exists() or any(output.resolve().is_relative_to(root / p) for p in (R10, HISTORICAL)):
        raise ValueError("NEW_INDEPENDENT_ADVISORY_OUTPUT_REQUIRED")
    files = read_functional_sizing_evidence(root)
    candidates = [json.loads(files[f"{HISTORICAL}/{name}"]) for name in HISTORICAL_FILES[2:]]
    scope = candidates[0]["source_zone_plan_hash"] + ":" + candidates[0]["source_p1_handoff_hash"]
    preview = preview_functional_sizing_handoff(
        files, project_scope_id=scope, layout_candidates=candidates
    )
    ci_path = f"{HISTORICAL}/r10-remote-ci/"
    ci = json.loads(files[ci_path + "verified-r10-results.json"])
    with zipfile.ZipFile(io.BytesIO(files[ci_path + "backend-regression.zip"])) as z:
        if (
            z.namelist() != ["backend-regression.xml"]
            or z.read("backend-regression.xml") != files[ci_path + "backend-regression.xml"]
        ):
            raise ValueError("ORIGINAL_R10_REMOTE_JUNIT_MISMATCH")
    cases = ET.fromstring(files[ci_path + "backend-regression.xml"]).findall(".//testcase")
    selected = [
        c
        for c in cases
        if c.get("classname", "").split(".")[-1] == "test_v222_r11_r10_reverse_sizing"
    ]
    if len(selected) != 41 or any(
        c.find(t) is not None for c in selected for t in ("failure", "error", "skipped")
    ):
        raise ValueError("ORIGINAL_R10_REMOTE_JUNIT_MISMATCH")
    if ci["HEAD"] != BASE_HEAD or ci["CI_RUN_ID"] != 40803856287:
        raise ValueError("ORIGINAL_R10_REMOTE_CI_IDENTITY_MISMATCH")
    output.mkdir(parents=True)

    def json_file(name: str, data: Any) -> None:
        (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    json_file("preview.json", preview)
    json_file("advisories.json", preview["advisories"])
    json_file("advisory-c.example.json", preview["advisories"][0])
    json_file("functional-room-sizing-advisory-v1.schema.json", advisory_json_schema())
    json_file("owner-confirmation-checklist.json", preview["owner_confirmation_checklist"])
    original_svg = historical_room_svg(preview["original_room"])
    (output / "original-h5.svg").write_text(original_svg)
    drawings = [("original-h5", original_svg)]
    for i, name in enumerate(SVG_FILES):
        source = files[f"{R10}/{name}"]
        (output / f"advice-{i}.svg").write_bytes(source)
        drawings.append((f"advice-{i}", source.decode()))
    # Equal mm viewports; all source geometry elements stay byte-for-byte intact.
    boxes = [list(map(int, ET.fromstring(svg).attrib["viewBox"].split())) for _, svg in drawings]
    left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
    right, bottom = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
    common = f"{left} {top} {right - left} {bottom - top}"
    for key, svg in drawings:
        e = ET.fromstring(svg)
        old_box = e.attrib["viewBox"]
        (output / f"{key}-common.svg").write_text(
            svg.replace(f'viewBox="{old_box}"', f'viewBox="{common}"', 1)
        )
    (output / "index.html").write_text(review_page(preview))
    lines = [
        "# H5功能尺寸建议与整厂只读预检查",
        "",
        f"BASE_HEAD={BASE_HEAD}",
        "",
        "本报告只匹配已审阅H5与封存功能见证。条件流程通过不等于工程批准，也不证明原整厂可容纳扩建。",
        "",
        f"P01/P02按真实矩形与Portal、项目/P1/Site/Composition去重为{preview['physical_room_count']}个物理房间。原P1需求{preview['p1_required_area_m2']}㎡不变；引用现有DimensionAuthorityReferenceV1及原Authority行，不创建新面积Authority。",
        "",
        "| 方案 | 长×宽mm | 面积㎡ | 新增㎡ | 完成面/安装输入mm | 最小余量mm | 最不利位置 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    o = preview["original_room"]
    lines.append(
        f"| 原H5 | {o['length_mm']}×{o['width_mm']} | {o['area_m2']}"
        " | 0.000000 | 未确认 | 不推断 | 原工程状态保留 |"
    )
    for a in preview["advisories"]:
        r, c, m = a["advised_room"], a["conditions"]["parameters"], a["margins"]
        lines.append(
            f"| {r['label']} | {r['length_mm']}×{r['width_mm']} | {r['area_m2']}"
            f" | {r['additional_area_m2']} | {c['finish_mm']}/{c['installation_gap_mm']}"
            f" | {m['minimum_mm']} | {m['minimum']['family']} / {m['minimum']['location']} |"
        )
    lines += [
        "",
        "C/B为20/20mm基础假设，3850mm为30/40mm组合敏感性。三者各自保留柜体/人体/排布条件、模板加量及实际余量；不归一化即不作全局最优或安全性排名。3850mm的70mm低于其100mm模板目标，不能标为目标通过。所有实际功能仍INPUT_REQUIRED。",
        "",
        "## 来源与架构衔接",
        "",
        "P1原始快照→现有尺寸Authority引用→已验收候选/P01-P02房间身份→R10原完整双班条件见证→只读建议合同。原composition_candidate_validation通过来源Hash校核候选的原则保留；本预检查只读取已封存候选，不调用重放、候选枚举或Native。不向dimension_handoff、整厂求解器、数据库或MCP注册建议。",
        "",
        "输入文件须匹配固定内容摘要。改写JSON标签、重算建议自身Hash或替换候选不能获得适用性。其他房型返回FUNCTIONAL_ADAPTER_REQUIRED，错项目/源候选/证据缺失直接拒绝。",
        "",
        "## 外部复核",
        "",
        "全部扩建的Site、Footprint、外部Access、相邻功能房间及工艺关系保持NOT_EVALUATED。C/3850mm仅扩北边、Portal数值不变；B向北/东扩展，东Portal映射到新东边界。原门洞、原几何及其工程结论不被覆盖。",
        "",
        "## Owner与工程师待确认",
        "",
    ]
    lines += [
        "- " + row["item"] + "：INPUT_REQUIRED" for row in preview["owner_confirmation_checklist"]
    ]
    lines += [
        "",
        "已确认的无坐凳、本人柜前站立、两班各53人、53人同时在室及五层柜形式不再列为未知。清单不生成审批记录。",
        "",
        "## 软件证据与执行边界",
        "",
        "R10原远端CI #40803856287的41项JUnit、原ZIP与验证记录均按原字节保留，"
        "属于软件测试证据，不是工程批准。R9 Native异常、R10所有文件与来源Hash均保持原样。"
        "本轮只读已有功能见证，无新布局求解、20t Native、MAIN、真实Grant/Claim或正式完整CI。"
        "自动快速CI中的既有合成Native单独识别，不能据此声称任务级所有环境Native为零。",
        "",
    ]
    (output / "handoff-review.md").write_text("\n".join(lines))
    json_file(
        "source-manifest.json",
        dict(
            base_head=BASE_HEAD,
            source_files={k: hashlib.sha256(v).hexdigest() for k, v in sorted(files.items())},
            derived_files={
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.iterdir())
                if p.is_file()
            },
            old_files_modified=False,
            original_r10_remote_tests_verified=41,
            native_solves=0,
        ),
    )
    return preview


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    status = guarded_reexec(args.output.parent / (args.output.name + "-native-guard"))
    if status is not None:
        raise SystemExit(status)
    result = write_review(Path(__file__).resolve().parents[2], args.output.resolve())
    print(
        json.dumps(
            dict(
                physical_rooms=result["physical_room_count"],
                advisories=len(CASE_KEYS),
                actual_status="INPUT_REQUIRED",
            )
        )
    )
