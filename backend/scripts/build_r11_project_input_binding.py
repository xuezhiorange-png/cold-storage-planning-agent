# ruff: noqa: E501 -- persisted Chinese report paragraphs
"""Read-only R11 R2 project-input gap report; never consumes unreviewed JSON as approval."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.application.functional_project_input_binding import (
    bind_project_functional_inputs,
    project_candidate_room_inputs,
)

PREVIEW = "docs/previews/v2.2.2/r11-functional-room-fit-r1"
OWNER = "docs/previews/v2.2.2/owner-functional-input-contract-r2"


def report_lines(binding: dict[str, Any], rooms: list[dict[str, Any]]) -> list[str]:
    staff = binding["workforce"]
    office = binding["office"]
    lines = [
        "# R11 R2｜封存20t功能设计输入绑定与缺口",
        "",
        "当前结论：**INPUT_REQUIRED**。未收到经应用侧资料/适用性审阅的项目专属输入。",
        "",
        "本项目为 FROZEN_20T_REGRESSION_FIXTURE_NOT_XINZHAO；20t 是进厂量，",
        "不能当作已包装产品质量推导包装人数或柜数量。",
        "",
        "## 已确认、但不等于项目设计批准的通用规则",
        "",
        "- 两班独立更衣柜，一人一柜，不能跨班共用。",
        "- 两班错峰更衣，同时人数按实际两班较大人数计算。",
        "- 产能按已包装产品质量：15件/人时×1.6kg/件×8小时=192kg/人班。",
        "- 包装人员默认两班均分，仅当已包装产品日质量经项目审阅后启用；显式班次覆盖须同时提供两班人数。",
        "- 显式两班人数不会自动分配50/50工作量；合计产能充足只证明总量容量，逐班满足须有各班已审包装质量并分别校核。",
        "- 办公人员按经确认的项目工厂规模选 SMALL=12/MEDIUM=20/LARGE=30。",
        "- 覆膜设计比率为100%，但设备型号、独立运行时数、有效产能均未确认。",
        "",
        "## 项目专属输入现状",
        "",
        "- 已包装产品日质量："
        + str(
            binding["project_reviewed_facts"]
            .get("PACKAGED_PRODUCT_MASS_KG_PER_DAY", {})
            .get("value", "INPUT_REQUIRED")
        )
        + "。",
        f"- 办公厂型：{office['factory_size'] or 'INPUT_REQUIRED'}；"
        f"办公人数：{office['staff_count'] if office['staff_count'] is not None else 'INPUT_REQUIRED'}。",
        "- 两班包装人数：" + str(staff["separate_personal_lockers"] or "INPUT_REQUIRED") + "。",
        "- 同时更衣人数：" + str(staff["simultaneous_changing_users"] or "INPUT_REQUIRED") + "。",
        f"- 已审核人数依据状态：{staff['status']}；逐班产能校核：{staff['capacity_validation']}。",
        f"- 合计容量校核：{staff['aggregate_capacity_validation']}；班次工作量依据：{staff['shift_workload_allocation_basis'] or 'INPUT_REQUIRED_SHIFT_WORKLOAD_ALLOCATION'}。",
        "- 显式人数已知但各班工作量未知时，保留人数及柜数需求，产能仍为待验证。",
        "- 更衣柜规格、内部净尺寸、门操作包络、人员空间及内部通道：INPUT_REQUIRED。",
        "- 办公家具及合法办公出入口：INPUT_REQUIRED。",
        "- 覆膜设备型号、台数、运行工时、进出料与维护包络：INPUT_REQUIRED。",
        "",
        "## 历史27份房间记录（只读投影）",
        "",
        "|候选|Handoff|物理组|房间|已绑定项目字段|功能结论|",
        "|---|---|---|---|---|---|",
    ]
    for room in rooms:
        fields = ", ".join(room["project_fields_bound"]) or "—"
        lines.append(
            f"|{room['record']}|H{room['handoff']}|{room['physical_group']}|"
            f"{room['room_code']}|{fields}|{room['functional_status']}|"
        )
    lines += [
        "",
        "## 下一步设计输入的办理方式",
        "",
        "填写 `project-input-request.json` 的候选值及可验证来源；这只是待审资料清单，",
        "不具备 OWNER_CONFIRMED 或工程批准效力。应用侧逐项核对项目范围、原始文件、",
        "班制、人员、设备版本并生成可信 ReviewedProjectDatum，方可用于真实绑定。",
        "不允许通过修改 JSON 的 status/label 自行授权。",
        "",
        "本模块只减少可追溯的输入缺口，绝不修改原 P1、Stage B 验收、九/十二指标、",
        "历史账本、Grant/Claim 或生产默认；Native=0。",
    ]
    return lines


def render_html(binding: dict[str, Any], rooms: list[dict[str, Any]]) -> str:
    def safe(value: Any) -> str:
        return html.escape(str(value))

    names = {"changing_room": "更衣室", "office": "办公室", "coating_room": "覆膜间"}
    rows = "".join(
        "<tr><td>"
        + "</td><td>".join(
            safe(v)
            for v in (
                item["record"],
                "H" + str(item["handoff"]),
                item["physical_group"],
                names[item["room_code"]],
                ", ".join(item["project_fields_bound"]) or "未绑定",
                item["functional_status"],
            )
        )
        + "</td></tr>"
        for item in rooms
    )
    return (
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>R11 R2｜项目功能输入</title>"
        "<style>body{font:14px system-ui,sans-serif;background:#f5f6f7;color:#1f2937;"
        "max-width:1000px;margin:36px auto;padding:0 16px;line-height:1.65}"
        "h1{font-size:23px}h2{font-size:17px;margin-top:28px}"
        ".panel{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:18px 20px}"
        "table{border-collapse:collapse;width:100%;background:#fff}td,th{padding:9px 10px;"
        "border-bottom:1px solid #e5e7eb;text-align:left}th{font-size:12px;color:#64748b}"
        ".muted{color:#64748b}code{background:#edf2f7;padding:2px 4px;border-radius:4px}"
        "</style><h1>R11 R2｜20t 功能设计输入</h1>"
        "<p class='muted'>封存回归输入，不是实际项目工程批准</p>"
        "<section class='panel'><h2>当前绑定：INPUT_REQUIRED</h2>"
        "<p>规则已有来源，但项目包装产量、工厂规模及真实柜型／设备资料不足。"
        "不从20t进厂质量推算两班人数，不自动采用53人／106柜示例。</p>"
        "<p><strong>已核对：</strong>两班独立柜、192kg/人班、错峰更衣、覆膜设计100%。"
        "</p><p><strong>仍需：</strong>已包装产品日质量、工厂规模、柜体及装修净尺寸、"
        "实际办公室入口、覆膜设备运行及维护资料。</p></section>"
        "<section class='panel'><h2>包装班次产能边界</h2>"
        "<p>显式两班人数不能自动套用50/50包装工作量。合计容量足够，也不等于各班产能满足；"
        "须审阅各班包装质量、核对合计与日总量，再分别校核。已审人数保留，产能状态单列。</p>"
        "<p>逐班校核："
        + safe(binding["workforce"]["capacity_validation"])
        + "；工作量依据："
        + safe(
            binding["workforce"]["shift_workload_allocation_basis"]
            or "INPUT_REQUIRED_SHIFT_WORKLOAD_ALLOCATION"
        )
        + "。</p></section>"
        "<h2>27份历史房间记录</h2><table><thead><tr><th>候选</th><th>Handoff</th>"
        "<th>矩形组</th><th>房间</th><th>已绑定字段</th><th>功能状态</th></tr></thead>"
        "<tbody>" + rows + "</tbody></table>"
        "<p class='muted'>功能状态与原工程/P1面积分离；未审项目输入不能转为 CONDITIONAL_FIT。"
        "不执行 Native 或重写历史证据。</p>"
        "</html>"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    original = repo / PREVIEW / "review-data.json"
    owner_path = repo / OWNER / "owner-confirmed-business-rules-v2.json"
    manifest = json.loads((repo / PREVIEW / "source-manifest.json").read_bytes())
    original_bytes = original.read_bytes()
    if hashlib.sha256(original_bytes).hexdigest() != manifest["derived_files"]["review-data.json"]:
        raise ValueError("SEALED_R11_SOURCE_DIGEST_CHANGED")
    review = json.loads(original_bytes)
    binding = bind_project_functional_inputs(review, owner_path.read_bytes())
    rows = project_candidate_room_inputs(review, binding)
    output = args.output.resolve()
    if output.is_relative_to((repo / PREVIEW).resolve()) or output == repo.resolve():
        raise ValueError("DO_NOT_OVERWRITE_R11_ARCHIVED_REVIEW")
    output.mkdir(parents=True, exist_ok=False)

    def write_json(name: str, obj: Any) -> None:
        (output / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")

    write_json("project-binding.json", binding)
    write_json("room-input-projection.json", rows)
    write_json(
        "project-input-request.json",
        dict(
            project_scope_id=binding["project_scope_id"],
            status="UNREVIEWED_PROPOSAL_NOT_APPROVED",
            note="Entries need actual project evidence and external application review.",
            values={
                name: dict(value=None, unit=unit, original_document_reference=None)
                for name, unit in {
                    "PACKAGED_PRODUCT_MASS_KG_PER_DAY": "kg/day",
                    "SHIFT_1_WORKERS": "people (optional explicit pair)",
                    "SHIFT_2_WORKERS": "people (optional explicit pair)",
                    "SHIFT_1_PACKAGED_PRODUCT_MASS_KG": "kg/shift (reviewed allocation pair)",
                    "SHIFT_2_PACKAGED_PRODUCT_MASS_KG": "kg/shift (reviewed allocation pair)",
                    "FACTORY_SIZE": "SMALL|MEDIUM|LARGE",
                    "LOCKER_MODEL_AND_DIMENSIONS": "manufacturer mm specification",
                    "CHANGING_FINISHED_CLEAR_BOUNDS": "mm",
                    "OFFICE_FURNITURE_AND_DOOR": "reviewed design",
                    "COATING_EQUIPMENT_AND_RUNTIME": "reviewed manufacturer data",
                }.items()
            },
        ),
    )
    # Reports consume the persisted calculation results, as required by AGENTS.md.
    saved_binding = json.loads((output / "project-binding.json").read_bytes())
    saved_rows = json.loads((output / "room-input-projection.json").read_bytes())
    (output / "readiness-report.md").write_text(
        "\n".join(report_lines(saved_binding, saved_rows)) + "\n"
    )
    (output / "index.html").write_text(render_html(saved_binding, saved_rows))
    print(json.dumps(dict(records=len(rows), native_solves=0, status=binding["binding_status"])))


if __name__ == "__main__":
    main()
