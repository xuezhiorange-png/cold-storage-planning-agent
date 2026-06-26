"""Build a ReportRenderModel from assembled report content_json.

Maps ReportRevision.content_json (the assembled report content from
ReportAssembler) to a ReportRenderModel consumed by DOCXRenderer and
PDFRenderer.  No engineering computation, no ORM access.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from cold_storage.modules.reports.domain.models import ApprovalSnapshot
from cold_storage.modules.reports.domain.render_model import (
    RenderManifest,
    RenderMetadata,
    RenderMetric,
    RenderNumber,
    RenderSection,
    RenderTable,
    RenderTableCell,
    ReportRenderModel,
    TemplateManifest,
    format_number,
)

# ---------------------------------------------------------------------------
# Section mapping configuration
# ---------------------------------------------------------------------------

_SECTION_HEADINGS: dict[str, tuple[str, int]] = {
    "report_metadata": ("报告元数据", 1),
    "project_summary": ("项目概况", 1),
    "design_basis": ("设计依据", 1),
    "input_conditions": ("输入条件", 1),
    "assumptions": ("假设条件", 1),
    "capacity_and_throughput": ("产能与吞吐", 1),
    "inventory_and_storage": ("库存与储存", 1),
    "area_and_layout": ("面积与布局", 1),
    "cooling_load": ("冷负荷计算", 1),
    "equipment_selection": ("设备选型", 1),
    "electrical_and_energy": ("电气及能耗", 1),
    "scheme_comparison": ("方案比较", 1),
    "investment_estimate": ("投资估算", 1),
    "risks_and_quality": ("风险与质量", 1),
    "citations_and_approval": ("引用与审批", 1),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_measured_value(obj: Any) -> bool:
    """Return True if obj looks like a measured value dict (value + unit)."""
    return isinstance(obj, dict) and "value" in obj and "unit" in obj


def _make_render_number(field_path: str, mv: dict[str, Any]) -> RenderNumber:
    """Create a RenderNumber from a measured value dict."""
    return RenderNumber(
        raw=mv.get("value"),
        display=format_number(mv.get("value"), mv.get("unit", "")),
        unit=mv.get("unit", ""),
        field_path=field_path,
    )


def _make_number_section(
    section_key: str,
    data: dict[str, Any],
) -> RenderSection:
    """Build a RenderSection with ALL measured values as structured metrics."""
    title, level = _SECTION_HEADINGS.get(section_key, (section_key, 1))
    metrics: list[RenderMetric] = []

    def _extract(prefix: str, d: dict[str, Any]) -> None:
        for k, v in d.items():
            if _is_measured_value(v):
                unit = v.get("unit", "")
                metrics.append(
                    RenderMetric(
                        field_path=f"{prefix}.{k}",
                        label=k,
                        raw_value=v.get("value"),
                        display_value=format_number(v.get("value"), unit),
                        unit=unit,
                        source_id=v.get("source_result_id", ""),
                        source_tool=v.get("source_tool", ""),
                        source_tool_version=v.get("source_tool_version", ""),
                        source_content_hash=v.get("source_content_hash", ""),
                    )
                )
            elif isinstance(v, dict) and not _is_measured_value(v):
                _extract(f"{prefix}.{k}", v)

    _extract(section_key, data)

    if not metrics:
        return RenderSection(
            section_key=section_key,
            title=title,
            level=level,
            content_type="empty",
            is_empty=True,
            empty_reason="not_calculated",
        )

    primary = metrics[0]
    return RenderSection(
        section_key=section_key,
        title=title,
        level=level,
        content_type="metrics",
        metrics=metrics,
        number=RenderNumber(
            raw=primary.raw_value,
            display=primary.display_value,
            unit=primary.unit,
            field_path=primary.field_path,
        ),
    )


def _build_project_summary(data: dict[str, Any]) -> RenderSection:
    """Build the project_summary section with text fields."""
    title, level = _SECTION_HEADINGS["project_summary"]
    parts: list[str] = []
    label_map = {
        "project_name": "项目名称",
        "project_location": "项目地点",
        "description": "项目描述",
    }
    for key in ("project_name", "project_location", "description"):
        val = data.get(key, "")
        if val:
            parts.append(f"{label_map[key]}：{val}")

    text = "\n".join(parts)
    if not text.strip():
        return RenderSection(
            section_key="project_summary",
            title=title,
            level=level,
            content_type="empty",
            is_empty=True,
            empty_reason="not_provided",
        )
    return RenderSection(
        section_key="project_summary",
        title=title,
        level=level,
        content_type="text",
        text=text,
    )


def _build_report_metadata(data: dict[str, Any]) -> RenderSection:
    """Build the report_metadata section."""
    title, level = _SECTION_HEADINGS["report_metadata"]
    parts: list[str] = []
    label_map = {
        "project_id": "项目编号",
        "schema_version": "Schema版本",
        "report_type": "报告类型",
    }
    for key, label in label_map.items():
        val = data.get(key, "")
        if val:
            parts.append(f"{label}：{val}")
    text = "\n".join(parts)
    if not text.strip():
        return RenderSection(
            section_key="report_metadata",
            title=title,
            level=level,
            content_type="empty",
            is_empty=True,
            empty_reason="not_provided",
        )
    return RenderSection(
        section_key="report_metadata",
        title=title,
        level=level,
        content_type="text",
        text=text,
    )


def _build_design_basis(data: dict[str, Any]) -> RenderSection:
    """Build the design_basis section."""
    title, level = _SECTION_HEADINGS["design_basis"]
    parts: list[str] = []
    if isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, str) and val:
                parts.append(f"{key}：{val}")
            elif isinstance(val, dict):
                inner = val.get("value", val.get("description", ""))
                if inner:
                    parts.append(f"{key}：{inner}")
    text = "\n".join(parts)
    if not text.strip():
        return RenderSection(
            section_key="design_basis",
            title=title,
            level=level,
            content_type="empty",
            is_empty=True,
            empty_reason="not_provided",
        )
    return RenderSection(
        section_key="design_basis",
        title=title,
        level=level,
        content_type="text",
        text=text,
    )


def _build_input_conditions(data: dict[str, Any]) -> RenderSection:
    """Build the input_conditions section with text/metrics."""
    return _make_number_section("input_conditions", data)


def _build_assumptions(data: dict[str, Any]) -> RenderSection:
    """Build the assumptions section with text fields."""
    title, level = _SECTION_HEADINGS["assumptions"]
    parts: list[str] = []
    if isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, str) and val:
                parts.append(f"{key}：{val}")
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        parts.append(f"• {item}")
                    elif isinstance(item, dict):
                        desc = item.get("description", item.get("value", ""))
                        if desc:
                            parts.append(f"• {desc}")
    text = "\n".join(parts)
    if not text.strip():
        return RenderSection(
            section_key="assumptions",
            title=title,
            level=level,
            content_type="empty",
            is_empty=True,
            empty_reason="not_provided",
        )
    return RenderSection(
        section_key="assumptions",
        title=title,
        level=level,
        content_type="text",
        text=text,
    )


def _build_capacity_and_throughput(data: dict[str, Any]) -> RenderSection:
    """Build the capacity_and_throughput section with number fields."""
    return _make_number_section("capacity_and_throughput", data)


def _build_inventory_and_storage(data: dict[str, Any]) -> RenderSection:
    """Build the inventory_and_storage section with number fields."""
    return _make_number_section("inventory_and_storage", data)


def _build_area_and_layout(data: dict[str, Any]) -> RenderSection:
    """Build the area_and_layout section with number fields."""
    return _make_number_section("area_and_layout", data)


def _build_cooling_load(data: dict[str, Any]) -> RenderSection:
    """Build the cooling_load section with number fields."""
    return _make_number_section("cooling_load", data)


def _build_equipment_selection(data: dict[str, Any]) -> RenderSection:
    """Build the equipment_selection section with number fields."""
    return _make_number_section("equipment_selection", data)


def _build_electrical_and_energy(data: dict[str, Any]) -> RenderSection:
    """Build the electrical_and_energy section with number fields."""
    return _make_number_section("electrical_and_energy", data)


def _build_scheme_comparison(data: dict[str, Any]) -> RenderSection:
    """Build the scheme_comparison section as a RenderTable."""
    title, level = _SECTION_HEADINGS["scheme_comparison"]

    schemes = data.get("schemes", [])
    recommended = data.get("recommended_scheme", "")

    if not schemes:
        return RenderSection(
            section_key="scheme_comparison",
            title=title,
            level=level,
            content_type="empty",
            is_empty=True,
            empty_reason="not_calculated",
        )

    # Extract metric keys from the first scheme to build headers.
    metric_keys: list[str] = []
    for scheme in schemes:
        for k in scheme:
            if k not in metric_keys and k not in ("scheme_name", "scheme_id"):
                metric_keys.append(k)

    if not metric_keys:
        for k in schemes[0]:
            if k not in ("scheme_name", "scheme_id"):
                metric_keys.append(k)

    _HEADER_LABELS: dict[str, str] = {
        "total_capital_cost": "总投资",
        "annual_energy_cost": "年能耗费用",
        "total_cost_10yr": "10年总成本",
        "equipment_count": "设备台数",
        "total_power": "总功率",
        "cop_system": "系统COP",
        "payback_years": "回收期",
        "npv_10yr": "10年NPV",
        "co2_emissions": "CO₂排放",
    }

    headers = ["方案"]
    unit_row = [""]
    for mk in metric_keys:
        first_val = schemes[0].get(mk, {})
        unit = first_val.get("unit", "") if isinstance(first_val, dict) else ""
        label = _HEADER_LABELS.get(mk, mk)
        headers.append(f"{label} ({unit})" if unit else label)
        unit_row.append(unit)

    rows: list[list[RenderTableCell]] = []
    for scheme in schemes:
        scheme_name = scheme.get("scheme_name", scheme.get("scheme_id", ""))
        cells = [RenderTableCell(value=scheme_name, align="left")]
        for mk in metric_keys:
            val = scheme.get(mk, {})
            if isinstance(val, dict) and "value" in val:
                unit = val.get("unit", "")
                display = format_number(val.get("value"), unit)
                cells.append(RenderTableCell(value=display, unit=unit, align="right"))
            else:
                display = str(val) if val else "—"
                cells.append(RenderTableCell(value=display, align="right"))
        rows.append(cells)

    table = RenderTable(
        title="方案比较",
        headers=headers,
        rows=rows,
        unit_row=unit_row,
    )

    text = ""
    if recommended:
        text = f"推荐方案：{recommended}"

    return RenderSection(
        section_key="scheme_comparison",
        title=title,
        level=level,
        content_type="table",
        text=text,
        table=table,
    )


def _build_investment_estimate(data: dict[str, Any]) -> RenderSection:
    """Build the investment_estimate section with number fields (unit: CNY)."""
    title, level = _SECTION_HEADINGS["investment_estimate"]

    total = data.get("total_investment")
    if total is None:
        return RenderSection(
            section_key="investment_estimate",
            title=title,
            level=level,
            content_type="empty",
            is_empty=True,
            empty_reason="not_calculated",
        )

    number = RenderNumber(
        raw=total,
        display=format_number(total, "CNY"),
        unit="CNY",
        field_path="investment_estimate.total_investment",
    )

    text = ""
    breakdown = data.get("breakdown", {})
    if breakdown:
        parts: list[str] = []
        for k, v in breakdown.items():
            if isinstance(v, (int, float)):
                parts.append(f"{k}：{format_number(v, 'CNY')}")
        text = "\n".join(parts)

    return RenderSection(
        section_key="investment_estimate",
        title=title,
        level=level,
        content_type="number",
        number=number,
        text=text,
    )


def _build_risks_and_quality(data: dict[str, Any]) -> RenderSection:
    """Build the risks_and_quality section (risks + missing + quality findings)."""
    title, level = _SECTION_HEADINGS["risks_and_quality"]

    risks = data.get("risks", [])
    missing = data.get("missing_information", [])
    findings = data.get("findings", [])
    blocker_count = data.get("blocker_count", 0)
    warning_count = data.get("warning_count", 0)
    total = data.get("total_findings", 0)

    if not risks and not missing and not findings and total == 0:
        return RenderSection(
            section_key="risks_and_quality",
            title=title,
            level=level,
            content_type="empty",
            is_empty=True,
            empty_reason="not_provided",
        )

    parts: list[str] = []
    if risks:
        parts.append("风险项：")
        for i, risk in enumerate(risks, 1):
            desc = risk.get("description", "")
            sev = risk.get("severity", "")
            mitigation = risk.get("mitigation", "")
            line = f"  {i}. [{sev}] {desc}"
            if mitigation:
                line += f" — 缓解措施：{mitigation}"
            parts.append(line)

    if missing:
        parts.append("缺失信息：")
        for i, item in enumerate(missing, 1):
            desc = item.get("description", "")
            impact = item.get("impact", "")
            line = f"  {i}. {desc}"
            if impact:
                line += f" — 影响：{impact}"
            parts.append(line)

    if total > 0:
        info_count = data.get("info_count", 0)
        parts.append(
            f"质量摘要：共 {total} 项发现：{blocker_count} 个阻断项、"
            f"{warning_count} 个警告、{info_count} 个提示"
        )

    table: RenderTable | None = None
    if findings:
        headers = ["代码", "严重性", "消息", "来源"]
        rows_list: list[list[RenderTableCell]] = []
        for f in findings:
            rows_list.append(
                [
                    RenderTableCell(value=f.get("code", ""), align="left"),
                    RenderTableCell(value=f.get("severity", ""), align="center"),
                    RenderTableCell(value=f.get("message", ""), align="left"),
                    RenderTableCell(
                        value=f.get("section_key", "") or f.get("field_path", ""),
                        align="left",
                    ),
                ]
            )
        table = RenderTable(
            title="质量发现",
            headers=headers,
            rows=rows_list,
        )

    return RenderSection(
        section_key="risks_and_quality",
        title=title,
        level=level,
        content_type="finding",
        text="\n".join(parts),
        findings=findings,
        table=table,
    )


def _build_citations_and_approval(
    data: Any, *, approval_snapshot: ApprovalSnapshot | None = None
) -> RenderSection:
    """Build the citations_and_approval section with source references table."""
    title, level = _SECTION_HEADINGS["citations_and_approval"]

    # Accept both list (old format) and dict with "citations" + "approval" keys
    if isinstance(data, dict):
        citations = data.get("citations", [])
        approval = data.get("approval", {})
    elif isinstance(data, list):
        citations = data
        approval = {}
    else:
        citations = []
        approval = {}

    table: RenderTable | None = None
    if citations:
        headers = ["节", "来源类型", "来源ID", "工具", "内容哈希"]
        rows_list: list[list[RenderTableCell]] = []
        for c in citations:
            rows_list.append(
                [
                    RenderTableCell(value=c.get("section_key", ""), align="left"),
                    RenderTableCell(value=c.get("source_type", ""), align="left"),
                    RenderTableCell(value=c.get("source_id", ""), align="left"),
                    RenderTableCell(value=c.get("tool_name", ""), align="left"),
                    RenderTableCell(
                        value=(c.get("content_hash", "") or "")[:12],
                        align="left",
                    ),
                ]
            )
        table = RenderTable(
            title="引用来源",
            headers=headers,
            rows=rows_list,
        )

    # Build approval paragraphs
    # P0-1: If an ApprovalSnapshot is provided, use it as the canonical
    # approval source.  This ensures the render model section and the
    # artifact manifest use the exact same approval data.
    paragraphs: list[str] = []
    if approval_snapshot is not None:
        approval = {
            "approved_by": approval_snapshot.approved_by,
            "approved_at": approval_snapshot.approved_at,
            "approved_revision_id": approval_snapshot.revision_id,
            "approved_content_hash": approval_snapshot.content_hash,
        }
    if approval:
        paragraphs.append("审批信息：")
        if approval_snapshot is not None and approval_snapshot.revision_number:
            paragraphs.append(f"批准修订号：{approval_snapshot.revision_number}")
        if approval.get("approved_by"):
            paragraphs.append(f"批准人：{approval['approved_by']}")
        if approval.get("approved_at"):
            paragraphs.append(f"批准时间：{approval['approved_at']}")
        if approval.get("approved_revision_id"):
            rid = approval["approved_revision_id"]
            paragraphs.append(f"批准修订ID：{rid}")
        if approval.get("approved_content_hash"):
            h = approval["approved_content_hash"]
            paragraphs.append(f"批准内容哈希：{h}")

    if not citations and not approval:
        return RenderSection(
            section_key="citations_and_approval",
            title=title,
            level=level,
            content_type="empty",
            is_empty=True,
            empty_reason="not_provided",
        )

    content_type = "table" if table else "text"
    return RenderSection(
        section_key="citations_and_approval",
        title=title,
        level=level,
        content_type=content_type,
        table=table,
        paragraphs=paragraphs,
    )


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_render_model(
    *,
    content: dict[str, Any],
    report_id: str,
    revision_number: int,
    content_hash: str,
    generated_by: str,
    generated_at: str,
    template_code: str,
    template_version: str,
    locale: str = "zh-CN",
    template_manifest_json: dict[str, Any] | None = None,
    format: str = "docx",  # noqa: A002
    approval_snapshot: ApprovalSnapshot | None = None,
) -> ReportRenderModel:
    """Map assembled report content to a ReportRenderModel.

    Parameters
    ----------
    content:
        The ``ReportRevision.content_json`` dict produced by the assembler.
    report_id, revision_number, content_hash, generated_by, generated_at:
        Report identity and audit fields.
    template_code, template_version:
        Template provenance.
    locale:
        Locale string (default ``"zh-CN"``).

    Returns
    -------
    ReportRenderModel
        A fully populated render model ready for DOCX/PDF renderers.
    """
    meta_section = content.get("report_metadata", {})
    project_summary = content.get("project_summary", {})
    project_name = project_summary.get("project_name", "") or meta_section.get("project_id", "")

    schema_version = meta_section.get("schema_version", template_version)

    # Ensure generated_at is always an ISO 8601 string
    if isinstance(generated_at, datetime):
        generated_at_str = generated_at.isoformat()
    else:
        generated_at_str = str(generated_at) if generated_at else ""

    metadata = RenderMetadata(
        report_id=report_id,
        project_name=project_name,
        report_type="概念设计报告",
        schema_version=schema_version,
        revision_number=revision_number,
        content_hash=content_hash,
        content_hash_short=content_hash[:8] if content_hash else "",
        generated_at=generated_at_str,
        generated_by=generated_by,
        template_version=template_version,
        template_code=template_code,
        locale=locale,
    )

    # Build sections in defined order
    sections: list[RenderSection] = []

    section_builders: dict[str, Callable[..., RenderSection]] = {
        "report_metadata": _build_report_metadata,
        "project_summary": _build_project_summary,
        "design_basis": _build_design_basis,
        "input_conditions": _build_input_conditions,
        "assumptions": _build_assumptions,
        "capacity_and_throughput": _build_capacity_and_throughput,
        "inventory_and_storage": _build_inventory_and_storage,
        "area_and_layout": _build_area_and_layout,
        "cooling_load": _build_cooling_load,
        "equipment_selection": _build_equipment_selection,
        "electrical_and_energy": _build_electrical_and_energy,
        "scheme_comparison": _build_scheme_comparison,
        "investment_estimate": _build_investment_estimate,
        "risks_and_quality": _build_risks_and_quality,
        "citations_and_approval": _build_citations_and_approval,
    }

    for key, builder in section_builders.items():
        data = content.get(key)
        if data is None and not (key == "citations_and_approval" and approval_snapshot is not None):
            title, level = _SECTION_HEADINGS.get(key, (key, 1))
            sections.append(
                RenderSection(
                    section_key=key,
                    title=title,
                    level=level,
                    content_type="empty",
                    is_empty=True,
                    empty_reason="not_provided",
                )
            )
        else:
            if key == "citations_and_approval":
                sections.append(builder(data or {}, approval_snapshot=approval_snapshot))
            else:
                sections.append(builder(data))

    # Build manifest
    ALL_SECTION_KEYS = [
        "report_metadata",
        "project_summary",
        "design_basis",
        "input_conditions",
        "assumptions",
        "capacity_and_throughput",
        "inventory_and_storage",
        "area_and_layout",
        "cooling_load",
        "equipment_selection",
        "electrical_and_energy",
        "scheme_comparison",
        "investment_estimate",
        "risks_and_quality",
        "citations_and_approval",
    ]
    # P0-5: Normalize manifest_json through canonical TemplateManifest model
    template_manifest = TemplateManifest.from_manifest_json(template_manifest_json)
    render_settings = template_manifest.model_dump()
    manifest = RenderManifest(
        template_code=template_code,
        template_version=template_version,
        schema_version=schema_version,
        source_content_hash=content_hash,
        sections=ALL_SECTION_KEYS,
        format=format,
        render_settings=render_settings,
        manifest_hash="",
    )
    # Compute manifest hash in-place
    from dataclasses import replace as dc_replace

    manifest = dc_replace(manifest, manifest_hash=manifest.compute_hash())

    return ReportRenderModel(
        metadata=metadata,
        sections=sections,
        manifest=manifest,
    )
