"""Build a ReportRenderModel from assembled report content_json.

Maps ReportRevision.content_json (the assembled report content from
ReportAssembler) to a ReportRenderModel consumed by DOCXRenderer and
PDFRenderer.  No engineering computation, no ORM access.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from cold_storage.modules.reports.domain.render_model import (
    RenderManifest,
    RenderMetadata,
    RenderNumber,
    RenderSection,
    RenderTable,
    RenderTableCell,
    ReportRenderModel,
    format_number,
)

# ---------------------------------------------------------------------------
# Section mapping configuration
# ---------------------------------------------------------------------------

_SECTION_HEADINGS: dict[str, tuple[str, int]] = {
    "project_summary": ("项目概况", 1),
    "cooling_load": ("冷负荷计算", 1),
    "equipment_selection": ("设备选型", 1),
    "electrical_and_energy": ("电气及能耗", 1),
    "scheme_comparison": ("方案比较", 1),
    "investment_estimate": ("投资估算", 1),
    "risks_and_missing_information": ("风险与待补充信息", 1),
    "quality_summary": ("质量摘要", 1),
    "citations": ("引用来源", 1),
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
    *,
    unit_override: str | None = None,
) -> RenderSection:
    """Build a RenderSection of content_type='number' from measured value fields."""
    title, level = _SECTION_HEADINGS.get(section_key, (section_key, 1))

    # Collect the first meaningful measured value as the primary number.
    primary: RenderNumber | None = None
    for k, v in data.items():
        if _is_measured_value(v):
            u = unit_override or v.get("unit", "")
            primary = RenderNumber(
                raw=v.get("value"),
                display=format_number(v.get("value"), u),
                unit=u,
                field_path=f"{section_key}.{k}",
            )
            break

    if primary is None:
        return RenderSection(
            section_key=section_key,
            title=title,
            level=level,
            content_type="empty",
            is_empty=True,
            empty_reason="not_calculated",
        )

    return RenderSection(
        section_key=section_key,
        title=title,
        level=level,
        content_type="number",
        number=primary,
    )


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


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


def _build_cooling_load(data: dict[str, Any]) -> RenderSection:
    """Build the cooling_load section with number fields (unit: kW(r))."""
    return _make_number_section("cooling_load", data, unit_override="kW(r)")


def _build_equipment_selection(data: dict[str, Any]) -> RenderSection:
    """Build the equipment_selection section with number fields."""
    return _make_number_section("equipment_selection", data)


def _build_electrical_and_energy(data: dict[str, Any]) -> RenderSection:
    """Build the electrical_and_energy section with number fields (unit: kW(e))."""
    return _make_number_section("electrical_and_energy", data, unit_override="kW(e)")


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


def _build_risks_and_missing(data: dict[str, Any]) -> RenderSection:
    """Build the risks_and_missing_information section."""
    title, level = _SECTION_HEADINGS["risks_and_missing_information"]

    risks = data.get("risks", [])
    missing = data.get("missing_information", [])

    if not risks and not missing:
        return RenderSection(
            section_key="risks_and_missing_information",
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

    return RenderSection(
        section_key="risks_and_missing_information",
        title=title,
        level=level,
        content_type="text",
        text="\n".join(parts),
    )


def _build_quality_summary(data: dict[str, Any]) -> RenderSection:
    """Build the quality_summary section with findings table."""
    title, level = _SECTION_HEADINGS["quality_summary"]

    total = data.get("total_findings", 0)
    if total == 0 and not data.get("findings"):
        return RenderSection(
            section_key="quality_summary",
            title=title,
            level=level,
            content_type="empty",
            is_empty=True,
            empty_reason="not_provided",
        )

    findings = data.get("findings", [])

    blocker_count = data.get("blocker_count", 0)
    warning_count = data.get("warning_count", 0)
    info_count = data.get("info_count", 0)

    summary = (
        f"共 {total} 项发现：{blocker_count} 个阻断项、{warning_count} 个警告、{info_count} 个提示"
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
        section_key="quality_summary",
        title=title,
        level=level,
        content_type="finding",
        text=summary,
        findings=findings,
        table=table,
    )


def _build_citations(data: Any) -> RenderSection:
    """Build the citations section with source references table."""
    title, level = _SECTION_HEADINGS["citations"]

    citations = data if isinstance(data, list) else []
    if not citations:
        return RenderSection(
            section_key="citations",
            title=title,
            level=level,
            content_type="empty",
            is_empty=True,
            empty_reason="not_provided",
        )

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

    return RenderSection(
        section_key="citations",
        title=title,
        level=level,
        content_type="table",
        table=table,
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

    section_builders: dict[str, Any] = {
        "project_summary": _build_project_summary,
        "cooling_load": _build_cooling_load,
        "equipment_selection": _build_equipment_selection,
        "electrical_and_energy": _build_electrical_and_energy,
        "scheme_comparison": _build_scheme_comparison,
        "investment_estimate": _build_investment_estimate,
        "risks_and_missing_information": _build_risks_and_missing,
        "quality_summary": _build_quality_summary,
        "citations": _build_citations,
    }

    for key, builder in section_builders.items():
        data = content.get(key)
        if data is None:
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
            sections.append(builder(data))

    # Build manifest
    section_keys = [s.section_key for s in sections if not s.is_empty]
    render_settings = dict(template_manifest_json) if template_manifest_json else {"locale": locale}
    manifest = RenderManifest(
        template_code=template_code,
        template_version=template_version,
        schema_version=schema_version,
        source_content_hash=content_hash,
        sections=section_keys,
        format="docx/pdf",
        render_settings=render_settings,
    )
    manifest = RenderManifest(
        template_code=manifest.template_code,
        template_version=manifest.template_version,
        schema_version=manifest.schema_version,
        source_content_hash=manifest.source_content_hash,
        sections=manifest.sections,
        format=manifest.format,
        render_settings=manifest.render_settings,
        manifest_hash=manifest.compute_hash(),
    )

    return ReportRenderModel(
        metadata=metadata,
        sections=sections,
        manifest=manifest,
    )
