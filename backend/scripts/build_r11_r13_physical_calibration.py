"""Fresh R13 calibration output, using existing child Native guard; no approval."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from build_r11_r10_reverse_sizing_review import guarded_reexec

from cold_storage.modules.layout.application.physical_room_calibration_review import (
    BASE_HEAD,
    calibration_context,
    historical_hypothesis_packet,
    input_template,
    review_calibration,
)
from cold_storage.modules.layout.domain.physical_room_calibration import (
    FIELDS,
    IDENTITY,
    field_schema,
)
from cold_storage.modules.layout.infrastructure.physical_calibration_evidence import (
    read_calibration_evidence,
    read_proposed_documents,
)
from cold_storage.modules.layout.infrastructure.physical_calibration_page import (
    cabinet_door_plan,
    cabinet_elevation,
    calibration_plan,
    comparison_plan,
    review_page,
)


def packet_schema() -> dict[str, Any]:
    parameters = {}
    for name, spec in FIELDS.items():
        value = (
            {"type": ["integer", "null"], "minimum": spec.minimum, "maximum": 60000}
            if spec.unit in {"mm", "count", "degree"}
            else {"type": ["string", "null"], "minLength": 1, "maxLength": 256}
        )
        if spec.choices:
            value["enum"] = [*spec.choices, None]
        parameters[name] = dict(
            type="object",
            additionalProperties=False,
            required=["value", "unit", "document_id", "locator"],
            properties=dict(
                value=value,
                unit={"const": spec.unit},
                document_id={"type": ["string", "null"]},
                locator={"type": ["string", "null"]},
            ),
        )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": IDENTITY,
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "project_scope_id",
            "physical_room_id",
            "owner_template_sha256",
            "parameters",
            "source_documents",
        ],
        "properties": {
            "schema_version": {"const": IDENTITY},
            **{
                k: {"type": "string", "minLength": 1}
                for k in ("project_scope_id", "physical_room_id", "owner_template_sha256")
            },
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": list(parameters),
                "properties": parameters,
            },
            "source_documents": {
                "type": "object",
                "maxProperties": 32,
                "additionalProperties": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "source_type",
                        "file_name",
                        "sha256",
                        "document_date",
                        "project_scope_id",
                        "reference",
                    ],
                    "properties": {
                        "source_type": {
                            "enum": [
                                "SUPPLIER_UNREVIEWED",
                                "SITE_MEASUREMENT_UNREVIEWED",
                                "HYPOTHETICAL_NOT_APPROVED",
                            ]
                        },
                        "file_name": {"type": "string", "minLength": 1},
                        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "document_date": {"type": ["string", "null"], "format": "date"},
                        "project_scope_id": {"type": "string"},
                        "reference": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
        "description": (
            "Unreviewed input only. JSON cannot construct ReviewedProjectDatum "
            "or approve any field."
        ),
    }


def write_review(
    root: Path, output: Path, proposed: Path | None = None, source_dir: Path | None = None
) -> dict[str, Any]:
    output = output.resolve()
    preview_root = root / "docs/previews/v2.2.2"
    if (
        output.exists()
        or output.is_relative_to(root / "docs/evidence/v2.2.2/r11-r11-h5-sizing-sources")
        or output.is_relative_to(preview_root)
        and not output.is_relative_to(preview_root / "r11-r13-physical-input-calibration-r1")
    ):
        raise ValueError("FRESH_R13_OUTPUT_OUTSIDE_HISTORICAL_EVIDENCE_REQUIRED")
    files = read_calibration_evidence(root)
    ctx = calibration_context(files)
    template = input_template(ctx)
    packet = json.loads(proposed.read_bytes()) if proposed else template
    documents = read_proposed_documents(packet, source_dir or proposed.parent) if proposed else {}
    actual = review_calibration(ctx, packet, documents)
    results = {"actual": dict(label="实际参数（未齐全/未审阅）", review=actual)}
    packets = {"actual": packet}
    for key, name, label in (
        ("R10-L26331-W3550-M50-MIXED", "20-20", "20/20mm · 相同50mm填充（未批准）"),
        ("R10-L26331-W3850-M100-MIXED-SENSITIVITY", "30-40", "30/40mm · 相同100mm填充（未批准）"),
    ):
        p, source = historical_hypothesis_packet(ctx, key)
        results[name] = dict(label=label, review=review_calibration(ctx, p, source))
        packets[name] = p
        if any(n in documents and documents[n] != b for n, b in source.items()):
            raise ValueError("SOURCE_DOCUMENT_FILENAME_CONFLICT")
        documents.update(source)
    output.mkdir(parents=True, exist_ok=False)

    def write(name: str, value: Any) -> None:
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    write("physical-input-template.json", template)
    write("physical-input.schema.json", packet_schema())
    write("proposed-input.json", packet)
    for name, value in packets.items():
        write(name + "-input.json", value)
    (output / "source-documents").mkdir()
    for name, data in documents.items():
        path = output / "source-documents" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    summaries = {}
    for key, item in results.items():
        report = item["review"]
        (output / (key + "-comparison.svg")).write_text(comparison_plan(report))
        for case in report["cases"]:
            prefix = key + "-" + case["label"]
            (output / (prefix + "-plan.svg")).write_text(calibration_plan(case))
            (output / (prefix + "-elevation.svg")).write_text(cabinet_elevation(case))
            (output / (prefix + "-door.svg")).write_text(cabinet_door_plan(case))
        (output / (key + "-full-witnesses.json.gz")).write_bytes(
            gzip.compress(
                json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0
            )
        )
        summaries[key] = dict(
            label=item["label"],
            input_fingerprint=report["binding"]["input_fingerprint"],
            parameters=report["binding"]["parameters"],
            projection=report["projection"],
            missing=report["binding"]["missing"],
            unreviewed=report["binding"]["unreviewed"],
            cases=[
                {
                    k: c[k]
                    for k in (
                        "label",
                        "length_mm",
                        "width_mm",
                        "area_m2",
                        "summary",
                        "physical_checks",
                        "site",
                    )
                }
                | dict(new_witness_hash=c["witness"]["evidence_hash"])
                for c in report["cases"]
            ],
            actual_calibration=report["actual_calibration"],
            engineering_approval=report["engineering_approval"],
            factory_applicability=report["factory_applicability"],
        )
    data = dict(
        task=actual["task"],
        base_head=BASE_HEAD,
        reports=results,
        physical_room_count=1,
        owner_confirmed=actual["binding"]["owner_requirements"],
        confirmation_items=[
            v["item"] + "：INPUT_REQUIRED" for v in actual["owner_confirmation_checklist"]
        ],
        actual_calibration="INPUT_REQUIRED",
        engineering_approval="NOT_EVALUATED",
        factory_applicability="NOT_EVALUATED",
    )
    write(
        "calibration-summary.json",
        {k: v for k, v in data.items() if k != "reports"} | dict(reports=summaries),
    )
    (output / "index.html").write_text(review_page(data, packet, field_schema()))
    lines = [
        "# H5实物参数校准与同条件复核",
        "",
        f"TASK_ID={actual['task']}",
        f"BASE_HEAD={BASE_HEAD}",
        "",
        "当前没有实际设备/人体/现场完整资料。真实字段空值不填默认；供应商和现场资料仅验证来源字节，不自动审核其内容。既有ReviewedProjectDatum是唯一复用的审阅输入边界，没有新增审批体系。",
        "",
        "ACTUAL_CALIBRATION=INPUT_REQUIRED",
        "ENGINEERING_APPROVAL=NOT_EVALUATED",
        "FACTORY_APPLICABILITY=NOT_EVALUATED",
        "",
        "| 同条件组 | 房间 | 面积㎡ | 本位 | 两班完成 | 完整条件流程 | 最不利已定义余量 |",
        "|---|---|---:|---:|---|---|---|",
    ]
    for item in results.values():
        for case in item["review"]["cases"]:
            s = case["summary"]
            margin = (
                f"{s['minimum_margin_mm']}mm / {s['limiting_margin']['location']}"
                if s and s["limiting_margin"]
                else "NOT_EVALUATED"
            )
            if s and not s["full_flow_verified"]:
                margin += "（失败布置局部值，不是候选余量）"
            lines.append(
                f"| {item['label']} | {case['label']} | {case['area_m2']} | "
                f"{s['home_count'] if s else '未算'} | {s['completed_users'] if s else '未算'} | "
                f"{s['full_flow_status'] if s else 'INPUT_REQUIRED'} | {margin} |"
            )
    lines += [
        "",
        "20/20与30/40是分别明确的回归输入；每组C和3850mm使用同一组柜体、人体、通道、门扇和填充参数。"
        "没有以历史R10 PASS替代新流程。完整新事件、两班人员名单、门扇和局部余量保存在"
        "各组full-witnesses.json.gz中。",
        "",
        "三维柜门按原解析扇形逐批检查；取衣/存衣时开门，更衣时关门。实际五层净宽/净深、衣物尺寸、分隔与取放方式、操作可达性仍缺少资料；110个格口仅算容量，不构成106人储物功能合格。",
        "",
        "外矩形没有因内部参数改变：C和3850mm分别用两份原候选的12区/通道/Site几何重新叠加，已检查范围无新增正面积碰撞。外部Access、Truck、洁污工艺及最终整厂适用仍未验证。B仅保留原3.338㎡通道与0.982㎡禁建区冲突，不参与本轮校准。",
        "",
        "适配器边界明确列在projection中：不支持的门扇、非均匀层位、不同旋转包络或流程不被近似为旧模型。默认20mm框/15mm门厚/左铰链/参考可达范围等只属于R10受限模型，绝不是规范或Owner要求。实际更改需相应功能适配器。",
        "",
        "每侧不利施工公差预算加入完成面厚度并重新计算；不是未经审核的施工允许公差。所有参数、文件字节或审阅来源变化均改变input_fingerprint；旧见证不能继续用于新输入。Hash校验不等于审批。",
        "",
        "## Owner仍需提供/复核",
        "",
        *["- " + x for x in data["confirmation_items"]],
        "",
        "原53人同时在室、两班人数、无坐凳、本人柜前站立及五层形式不重新列为未知。"
        "P01/P02只计一个物理房间。未修改历史P1、Stage B、比较器、面积Authority、MCP、MAIN或默认。"
        "无Native、MAIN或真实Grant/Claim。",
    ]
    (output / "calibration-report.md").write_text("\n".join(lines) + "\n")
    write(
        "source-manifest.json",
        dict(
            base_head=BASE_HEAD,
            source_files=ctx["source_hashes"],
            proposed_document_hashes={
                n: hashlib.sha256(d).hexdigest() for n, d in documents.items()
            },
            derived_files={
                str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.rglob("*"))
                if p.is_file()
            },
            actual_calibration="INPUT_REQUIRED",
            native_solves=0,
            new_main=False,
            historical_records_changed=False,
        ),
    )
    return {k: v for k, v in data.items() if k != "reports"} | dict(reports=summaries)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--input", type=Path)
    p.add_argument("--source-dir", type=Path)
    args = p.parse_args()
    r = guarded_reexec(args.output.parent / (args.output.name + "-native-guard"))
    if r is not None:
        return r
    result = write_review(
        Path(__file__).resolve().parents[2], args.output, args.input, args.source_dir
    )
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "task",
                    "actual_calibration",
                    "engineering_approval",
                    "factory_applicability",
                )
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
