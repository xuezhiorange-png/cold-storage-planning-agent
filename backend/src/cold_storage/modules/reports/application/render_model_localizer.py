"""Locale-specific render model localizer.

Converts a CanonicalReportRenderModel to a LocalizedReportRenderModel by performing
all translation and locale-specific formatting.

All display text MUST come from the TranslationCatalog via translate() or
translate_format().  No hardcoded Chinese/English strings.  No exception
suppression -- MissingTranslationError propagates on missing catalog keys
(fail-closed).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from cold_storage.modules.reports.domain.enums import ReportLocale
from cold_storage.modules.reports.domain.render_model import (
    CanonicalRenderMetadata,
    CanonicalRenderMetric,
    CanonicalRenderSection,
    CanonicalRenderTable,
    CanonicalRenderTableCell,
    CanonicalReportRenderModel,
    LocalizedCitation,
    LocalizedFinding,
    LocalizedMissingInformation,
    LocalizedRenderMetadata,
    LocalizedRenderMetric,
    LocalizedRenderNumber,
    LocalizedRenderSection,
    LocalizedRenderTable,
    LocalizedRenderTableCell,
    LocalizedReportRenderModel,
    LocalizedRisk,
    RenderManifest,
    TemplateManifest,
)
from cold_storage.modules.reports.localization.catalog import (
    TranslationCatalog,
    get_catalog,
    translate,
    translate_format,
)
from cold_storage.modules.reports.localization.formatter import (
    format_unit_label,
)


def _is_numeric(value: Any) -> bool:
    """Return True if value can be converted to a number."""
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            Decimal(value)
            return True
        except (ValueError, TypeError):
            return False
    return False


def _make_text_cell(text: str, align: str | None = None) -> LocalizedRenderTableCell:
    """Create a LocalizedRenderTableCell with a synthetic canonical cell."""
    canonical = CanonicalRenderTableCell(field_path="", field_key="", raw_value=text or "")
    return LocalizedRenderTableCell(canonical=canonical, display_value=text, align=align)


def _format_display_value(
    value: Decimal | int | None,
    unit: str,
    locale: ReportLocale,
    catalog: TranslationCatalog,
) -> str:
    """Format a numeric value for display using locale-aware formatting.

    Uses ``format_decimal`` for locale-aware number formatting.
    Returns ``\\u2014`` (em-dash) for None or empty values.

    The canonical model guarantees that raw_value is already ``Decimal`` or ``int``;
    this function does NOT accept ``float`` or ``str``.
    """
    from cold_storage.modules.reports.localization.formatter import (
        format_decimal,
    )

    if value is None:
        return "\u2014"  # em-dash
    return format_decimal(value, locale)


def _localize_section(
    section: CanonicalRenderSection,
    locale: ReportLocale,
    catalog: TranslationCatalog,
) -> LocalizedRenderSection:
    """Localize a canonical section for a specific locale.

    All translations go through the catalog.  MissingTranslationError
    propagates on missing keys (fail-closed).
    """
    title = translate(locale, f"section.{section.section_key}")

    # Empty-reason text
    empty_reason_text = ""
    if section.content_type_code == "empty" and section.empty_reason_code:
        empty_reason_text = translate(locale, f"empty.{section.empty_reason_code}")

    # -- Localize metrics ---------------------------------------------------
    localized_metrics: list[LocalizedRenderMetric] = []
    for m in section.metrics:
        label = translate(locale, m.field_key) if m.field_key else ""
        display_value = _format_display_value(m.raw_value, m.unit_code, locale, catalog)
        display_unit = format_unit_label(m.unit_code, locale) if m.unit_code else ""
        localized_metrics.append(
            LocalizedRenderMetric(
                canonical=m,
                label=label,
                display_value=display_value,
                display_unit=display_unit,
            )
        )

    # -- Localize number (single metric) ------------------------------------
    localized_number: LocalizedRenderNumber | None = None
    if section.number is not None:
        num: CanonicalRenderMetric = section.number
        display = _format_display_value(num.raw_value, num.unit_code, locale, catalog)
        unit = format_unit_label(num.unit_code, locale) if num.unit_code else ""
        localized_number = LocalizedRenderNumber(
            canonical=num,
            display_value=display,
            display_unit=unit,
        )

    # -- Assemble display text from text_fields -----------------------------
    display_text = ""
    if section.text_fields:
        parts: list[str] = []
        for key, val in section.text_fields.items():
            # Translate label via catalog; MissingTranslationError propagates (fail-closed)
            label = translate(locale, f"field.{key}")
            parts.append(f"{label}: {val}")
        display_text = "\n".join(parts)

    # Append recommended_scheme_code as a dedicated display line
    if section.recommended_scheme_code:
        label = translate(locale, "field.recommended_scheme")
        rec_line = f"{label}: {section.recommended_scheme_code}"
        if display_text:
            display_text += "\n" + rec_line
        else:
            display_text = rec_line

    # -- Build paragraphs from approval_snapshot ----------------------------
    # -- Localize findings (CanonicalFinding → LocalizedFinding) ------------
    localized_findings: list[LocalizedFinding] = []
    for f in section.findings:
        severity_label = translate(locale, f"severity.{f.severity_code}") if f.severity_code else ""
        section_label = translate(locale, f"section.{f.section_key}") if f.section_key else ""
        localized_findings.append(
            LocalizedFinding(
                canonical=f,
                severity_label=severity_label,
                section_label=section_label,
            )
        )

    # -- Localize risks (CanonicalRisk → LocalizedRisk) --------------------
    localized_risks: list[LocalizedRisk] = []
    for r in section.risks:
        severity_label = translate(locale, f"severity.{r.severity_code}") if r.severity_code else ""
        localized_risks.append(
            LocalizedRisk(
                canonical=r,
                severity_label=severity_label,
                mitigation_label=r.mitigation or "",
            )
        )

    # -- Localize citations (CanonicalCitation → LocalizedCitation) --------
    localized_citations: list[LocalizedCitation] = []
    for c in section.citations:
        section_label = translate(locale, f"section.{c.section_key}") if c.section_key else ""
        src_type = c.source_type_code
        source_type_label = translate(locale, f"source_type.{src_type}") if src_type else ""
        localized_citations.append(
            LocalizedCitation(
                canonical=c,
                section_label=section_label,
                source_type_label=source_type_label,
            )
        )

    # -- Localize missing_information → LocalizedMissingInformation ----------
    localized_missing: list[LocalizedMissingInformation] = []
    for mi in section.missing_information:
        impact_label = translate(locale, f"impact.{mi.impact_code}") if mi.impact_code else ""
        localized_missing.append(
            LocalizedMissingInformation(
                canonical=mi,
                impact_label=impact_label,
            )
        )

    # -- Build text from missing_information if no text ---------------------
    if not display_text and localized_missing:
        mi_parts: list[str] = [translate(locale, "label.missing_information")]
        for i, mi_entry in enumerate(localized_missing, 1):
            line = f"  {i}. {mi_entry.canonical.description}"
            if mi_entry.impact_label:
                line += f" \u2014 {translate(locale, 'label.impact')}{mi_entry.impact_label}"
            mi_parts.append(line)
        display_text = "\n".join(mi_parts)

    # -- Build paragraphs from section ----------------------------------------
    localized_paragraphs: list[str] = list(section.paragraphs)

    # -- Initialize localized_table -----------------------------------------
    localized_table: LocalizedRenderTable | None = None

    # -- Build table from findings if no canonical table --------------------
    if localized_table is None and localized_findings:
        code_hdr = translate(locale, "header.code")
        severity_hdr = translate(locale, "header.severity")
        message_hdr = translate(locale, "header.message")
        section_hdr = translate(locale, "header.section")
        table_title = translate(locale, "header.quality_findings")
        findings_rows: list[tuple[LocalizedRenderTableCell, ...]] = []
        for fd in localized_findings:
            findings_rows.append(
                (
                    _make_text_cell(fd.canonical.code),
                    _make_text_cell(fd.severity_label),
                    _make_text_cell(fd.canonical.message),
                    _make_text_cell(fd.section_label),
                )
            )
        localized_table = LocalizedRenderTable(
            canonical=CanonicalRenderTable(table_key="quality_findings"),
            title=table_title,
            headers=(code_hdr, severity_hdr, message_hdr, section_hdr),
            rows=tuple(findings_rows),
        )

    # -- Localize canonical table → LocalizedRenderTable (if not already built)
    if localized_table is None and section.table is not None:
        from cold_storage.modules.reports.domain.render_model import (
            CanonicalRenderTable as _CRT,
        )

        ct: _CRT = section.table
        # Translate table title
        table_title = translate(locale, ct.title_key) if ct.title_key else ""
        # Translate column headers
        scheme_hdr = translate(locale, "header.scheme")
        table_headers: list[str] = []
        for col in ct.column_keys:
            if col == "scheme_name":
                table_headers.append(scheme_hdr)
            elif ct.table_key == "investment_breakdown":
                table_headers.append(translate(locale, f"investment.{col}"))
            else:
                table_headers.append(translate(locale, f"header.{col}"))
        # Build unit row
        table_unit_row: list[str] = [
            format_unit_label(code, locale) if code else "" for code in ct.unit_codes
        ]
        # Build rows
        table_rows: list[tuple[LocalizedRenderTableCell, ...]] = []
        for row in ct.rows:
            cells: list[LocalizedRenderTableCell] = []
            for cell in row:
                raw = cell.raw_value
                # Determine if this is a scheme_name cell (first column) or a metric
                if cell.field_key == "header.scheme" or cell.field_path.endswith("scheme_name"):
                    display_val = str(raw) if raw else "\u2014"
                    cells.append(
                        LocalizedRenderTableCell(
                            canonical=cell, display_value=display_val, align="left"
                        )
                    )
                elif cell.unit_code and _is_numeric(raw):
                    # Numeric metric cell — canonical model guarantees Decimal | int
                    num_val = raw if isinstance(raw, (Decimal, int)) else Decimal(str(raw))
                    display_val = _format_display_value(num_val, cell.unit_code, locale, catalog)
                    localized_unit = (
                        format_unit_label(cell.unit_code, locale) if cell.unit_code else ""
                    )
                    cells.append(
                        LocalizedRenderTableCell(
                            canonical=cell,
                            display_value=display_val,
                            display_unit=localized_unit,
                            align="right",
                        )
                    )
                else:
                    # Text cell (citations, etc.)
                    display_val = str(raw) if raw else "\u2014"
                    cells.append(
                        LocalizedRenderTableCell(
                            canonical=cell, display_value=display_val, align="left"
                        )
                    )
            table_rows.append(tuple(cells))
        localized_table = LocalizedRenderTable(
            canonical=ct,
            title=table_title,
            headers=tuple(table_headers),
            rows=tuple(table_rows),
            unit_row=tuple(table_unit_row),
        )

    return LocalizedRenderSection(
        section_key=section.section_key,
        title=title,
        level=section.level,
        content_type=section.content_type_code,
        text=display_text,
        number=localized_number,
        table=localized_table,
        findings=tuple(localized_findings),
        is_empty=section.content_type_code == "empty",
        metrics=tuple(localized_metrics),
        paragraphs=tuple(localized_paragraphs),
        citations=tuple(localized_citations),
        empty_reason_text=empty_reason_text,
        risks=tuple(localized_risks),
        missing_information=tuple(localized_missing),
        canonical=section,
    )


def localize_render_model(
    canonical: CanonicalReportRenderModel,
    *,
    locale: ReportLocale,
    template_manifest_json: dict[str, Any] | None = None,
    format: str = "docx",  # noqa: A002
) -> LocalizedReportRenderModel:
    """Localize a canonical render model for a specific locale.

    This function performs ALL translation and locale-specific formatting.
    It does NOT call build_canonical_render_model -- it takes an already-built
    canonical model as input.

    All display text is sourced from the TranslationCatalog.  No hardcoded
    Chinese/English strings.  MissingTranslationError propagates on missing
    catalog keys (fail-closed).
    """
    catalog = get_catalog(locale)

    report_type_label = translate(locale, "report_type.cold_storage_concept_design")
    confidentiality = translate(locale, "header.confidentiality")
    disclaimer_text = translate(locale, "disclaimer.standard")
    watermark_text = translate(locale, "watermark.draft")

    # Cover page / document control — ALL from catalog, no hardcoded strings
    date_display = canonical.metadata.generated_at[:10] if canonical.metadata.generated_at else ""
    cover_version_line = translate_format(
        locale,
        "cover.version_line",
        number=str(canonical.metadata.revision_number),
        date=date_display,
    )
    control_info_title = translate(locale, "document_control.title")
    content_hash_label = translate(locale, "document_control.content_hash")
    template_version_label = translate(locale, "document_control.template_version")
    generated_by_label = translate(locale, "document_control.generated_by")
    generated_at_label = translate(locale, "document_control.generated_at")
    revision_label = translate(locale, "document_control.revision")

    localized_meta = LocalizedRenderMetadata(
        canonical=CanonicalRenderMetadata(
            report_id=canonical.metadata.report_id,
            report_type=canonical.metadata.report_type,
            schema_version=canonical.metadata.schema_version,
            revision_number=canonical.metadata.revision_number,
            content_hash=canonical.metadata.content_hash,
            content_hash_short=canonical.metadata.content_hash_short,
            generated_at=canonical.metadata.generated_at,
            generated_by=canonical.metadata.generated_by,
            template_version=canonical.metadata.template_version,
            template_code=canonical.metadata.template_code,
            project_name=canonical.metadata.project_name,
        ),
        project_name=canonical.metadata.project_name,
        report_type_label=report_type_label,
        confidentiality_label=confidentiality,
        disclaimer=disclaimer_text,
        empty_section_placeholder="",
        cover_title=canonical.metadata.project_name or "",
        cover_version_line=cover_version_line,
        control_info_title=control_info_title,
        content_hash_label=content_hash_label,
        template_version_label=template_version_label,
        generated_by_label=generated_by_label,
        generated_at_label=generated_at_label,
        revision_label=revision_label,
        watermark_text=watermark_text,
    )

    # Localize sections
    localized_sections: tuple[LocalizedRenderSection, ...] = tuple(
        _localize_section(section, locale, catalog) for section in canonical.sections
    )

    # Update manifest
    template_manifest = TemplateManifest.from_manifest_json(template_manifest_json)
    render_settings = template_manifest.model_dump()
    manifest = RenderManifest(
        template_code=canonical.manifest.template_code,
        template_version=canonical.manifest.template_version,
        schema_version=canonical.manifest.schema_version,
        source_content_hash=canonical.manifest.source_content_hash,
        sections=canonical.manifest.sections,
        format=format,
        render_settings=render_settings,
    )
    from dataclasses import replace as dc_replace

    manifest = dc_replace(manifest, manifest_hash=manifest.compute_hash())

    return LocalizedReportRenderModel(
        metadata=localized_meta,
        sections=localized_sections,
        manifest=manifest,
        disclaimer=disclaimer_text,
        watermark_text=watermark_text,
        cover_version_line=cover_version_line,
        control_info_title=control_info_title,
        content_hash_label=content_hash_label,
        template_version_label=template_version_label,
        generated_by_label=generated_by_label,
        generated_at_label=generated_at_label,
        revision_label=revision_label,
    )
