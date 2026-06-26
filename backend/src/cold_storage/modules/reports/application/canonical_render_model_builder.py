"""Locale-free canonical render model builder.

Builds a CanonicalReportRenderModel from report content_json.
No translation, no localization, no display text formatting.

This module MUST NOT import:
- domain.enums.ReportLocale
- localization.*
- localization.catalog.*
- localization.formatter.*
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from cold_storage.modules.reports.domain.models import ApprovalSnapshot
from cold_storage.modules.reports.domain.render_model import (
    CanonicalCitation,
    CanonicalFinding,
    CanonicalMissingInformation,
    CanonicalRenderMetadata,
    CanonicalRenderMetric,
    CanonicalRenderSection,
    CanonicalRenderTable,
    CanonicalRenderTableCell,
    CanonicalReportRenderModel,
    CanonicalRisk,
    RenderManifest,
)

# ---------------------------------------------------------------------------
# Section mapping -- locale-free
# ---------------------------------------------------------------------------

_SECTION_KEYS: tuple[str, ...] = (
    "report_metadata",
    "project_summary",
    "input_conditions",
    "assumptions",
    "throughput_inventory_area",
    "cooling_load",
    "equipment_selection",
    "electrical_and_energy",
    "scheme_comparison",
    "investment_estimate",
    "risks_and_missing_information",
    "quality_summary",
    "citations",
)

# Properties defined in COLD_STORAGE_CONCEPT_DESIGN_V1 JSON schema
_REPORT_SCHEMA_PROPERTIES: frozenset[str] = frozenset(
    {
        "report_metadata",
        "project_summary",
        "input_conditions",
        "assumptions",
        "throughput_inventory_area",
        "cooling_load",
        "equipment_selection",
        "electrical_and_energy",
        "scheme_comparison",
        "investment_estimate",
        "risks_and_missing_information",
        "quality_summary",
        "citations",
        "provenance",
    }
)

# Sections whose dict data should be preserved as text fields (not just metrics)
_TEXT_SECTIONS: frozenset[str] = frozenset(
    {
        "report_metadata",
        "project_summary",
        "assumptions",
    }
)


def _section_level(section_key: str) -> int:
    """All top-level sections use level 1."""
    return 1


def _is_measured_value(obj: Any) -> bool:
    """Return True if obj looks like a measured value dict (value + unit)."""
    return isinstance(obj, dict) and "value" in obj and "unit" in obj


def _canonicalize_numeric(value: object) -> Decimal | int:
    """Convert a raw value to Decimal or int for storage in canonical models.

    Decimal → return as-is
    int → return as-is
    float → Decimal(str(value))
    str → Decimal(value)
    bool → raise TypeError (bool is subclass of int)
    Anything else → raise TypeError
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TypeError(f"bool is not allowed as canonical raw_value: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value)
    raise TypeError(f"Cannot convert {type(value).__name__} to canonical numeric value: {value!r}")


def _extract_text_fields(data: dict[str, Any]) -> dict[str, str]:
    """Extract key-value pairs from a dict as text fields.

    Only extracts simple string/int/float values, not nested dicts or lists.
    """
    fields: dict[str, str] = {}
    for k, v in data.items():
        if isinstance(v, str) and v:
            fields[k] = v
        elif isinstance(v, (int, float, Decimal)):
            fields[k] = str(v)
        elif isinstance(v, dict) and "value" in v:
            # measured-value dict: {"value": 123.45, "unit_code": "CNY", ...}
            num_val = Decimal(str(v["value"]))
            unit_code = v.get("unit_code", "")
            fields[k] = f"{num_val} {unit_code}".strip() if unit_code else str(num_val)
    return fields


def _extract_canonical_metrics(prefix: str, d: dict[str, Any]) -> list[CanonicalRenderMetric]:
    """Extract canonical metrics from nested dict."""
    metrics: list[CanonicalRenderMetric] = []
    for k, v in d.items():
        if _is_measured_value(v):
            unit = v.get("unit", "")
            metrics.append(
                CanonicalRenderMetric(
                    field_path=f"{prefix}.{k}",
                    field_key=f"field.{k}",
                    raw_value=_canonicalize_numeric(v.get("value")),
                    unit_code=unit,
                    source_id=v.get("source_result_id", ""),
                    source_tool=v.get("source_tool", ""),
                    source_tool_version=v.get("source_tool_version", ""),
                    source_content_hash=v.get("source_content_hash", ""),
                )
            )
        elif isinstance(v, dict) and not _is_measured_value(v):
            metrics.extend(_extract_canonical_metrics(f"{prefix}.{k}", v))
    return metrics


def _build_text_section(
    section_key: str,
    data: dict[str, Any],
) -> CanonicalRenderSection:
    """Build a section that preserves text fields from dict data."""
    level = _section_level(section_key)
    text_fields = _extract_text_fields(data)
    if text_fields:
        return CanonicalRenderSection(
            section_key=section_key,
            title=section_key,
            level=level,
            content_type_code="text",
            text_fields=text_fields,
        )
    return CanonicalRenderSection(
        section_key=section_key,
        title=section_key,
        level=level,
        content_type_code="empty",
        empty_reason_code="not_provided",
    )


def _build_risks_and_missing_information_section(
    data: dict[str, Any],
) -> CanonicalRenderSection:
    """Build the risks_and_missing_information section with canonical risks and missing info.

    Findings are in the quality_summary section, not here.
    """
    section_key = "risks_and_missing_information"
    level = _section_level(section_key)

    risks_raw = data.get("risks", [])
    missing = data.get("missing_information", [])

    if not risks_raw and not missing:
        return CanonicalRenderSection(
            section_key=section_key,
            title=section_key,
            level=level,
            content_type_code="empty",
            empty_reason_code="not_provided",
        )

    # Convert raw risk dicts to canonical CanonicalRisk objects
    canonical_risks = tuple(
        CanonicalRisk(
            description=r.get("description", ""),
            severity_code=r.get("severity", r.get("severity_code", "")),
            mitigation=r.get("mitigation", ""),
        )
        for r in risks_raw
    )

    # Convert raw missing_information dicts to canonical CanonicalMissingInformation objects
    canonical_missing = tuple(
        CanonicalMissingInformation(
            description=item.get("description", ""),
            impact_code=item.get("impact", item.get("impact_code", "")),
            field_path=item.get("field_path", ""),
        )
        for item in missing
    )

    return CanonicalRenderSection(
        section_key=section_key,
        title=section_key,
        level=level,
        content_type_code="finding",
        risks=canonical_risks,
        missing_information=canonical_missing,
    )


def _build_investment_estimate_section(
    data: dict[str, Any],
) -> CanonicalRenderSection:
    """Build the investment_estimate section with a canonical number metric and breakdown table."""
    section_key = "investment_estimate"
    level = _section_level(section_key)

    total = data.get("total_investment")
    if total is None:
        return CanonicalRenderSection(
            section_key=section_key,
            title=section_key,
            level=level,
            content_type_code="empty",
            empty_reason_code="not_calculated",
        )

    number_metric = CanonicalRenderMetric(
        field_path="investment_estimate.total_investment",
        field_key="field.total_investment",
        raw_value=_canonicalize_numeric(total),
        unit_code="CNY",
    )

    # Build breakdown table from breakdown dict
    breakdown = data.get("breakdown", {})
    table: CanonicalRenderTable | None = None
    if breakdown:
        column_keys: list[str] = []
        for k in breakdown:
            if isinstance(breakdown[k], (int, float, Decimal)):
                column_keys.append(k)
            elif isinstance(breakdown[k], dict) and "value" in breakdown[k]:
                # measured-value dict: {"value": 123.45, "unit_code": "CNY", ...}
                column_keys.append(k)

        if column_keys:
            # Single-row table: each column is a breakdown item
            cells = tuple(
                CanonicalRenderTableCell(
                    field_path=f"investment_estimate.breakdown.{k}",
                    field_key=f"investment.{k}",
                    raw_value=(
                        _canonicalize_numeric(breakdown[k]["value"])
                        if isinstance(breakdown[k], dict) and "value" in breakdown[k]
                        else _canonicalize_numeric(breakdown[k])
                    ),
                    unit_code=(
                        breakdown[k].get("unit_code", breakdown[k].get("unit", "CNY"))
                        if isinstance(breakdown[k], dict) and "value" in breakdown[k]
                        else "CNY"
                    ),
                    align_code="right",
                    source_id=(
                        breakdown[k].get("source_result_id", breakdown[k].get("source_id", ""))
                        if isinstance(breakdown[k], dict)
                        else ""
                    ),
                    source_tool=(
                        breakdown[k].get("source_tool", "")
                        if isinstance(breakdown[k], dict)
                        else ""
                    ),
                    source_tool_version=(
                        breakdown[k].get("source_tool_version", "")
                        if isinstance(breakdown[k], dict)
                        else ""
                    ),
                    source_content_hash=(
                        breakdown[k].get("source_content_hash", "")
                        if isinstance(breakdown[k], dict)
                        else ""
                    ),
                )
                for k in column_keys
            )
            table = CanonicalRenderTable(
                table_key="investment_breakdown",
                title_key="section.investment_estimate",
                column_keys=tuple(column_keys),
                rows=(cells,),
                unit_codes=("CNY",) * len(column_keys),
            )

    return CanonicalRenderSection(
        section_key=section_key,
        title=section_key,
        level=level,
        content_type_code="number",
        number=number_metric,
        table=table,
    )


def resolve_scheme_provenance(
    *,
    metric: Mapping[str, Any] | None,
    scheme: Mapping[str, Any],
    run_id: str,
    run_scheme_evaluator: str,
    run_generator_version: str,
    run_persisted_content_hash: str,
) -> dict[str, str]:
    """Resolve provenance for a scheme cell following precedence rules.

    Precedence chain: metric-level > scheme-level > run-level.

    Rules:
    - source_id:      metric > scheme > run_id
    - source_tool:    metric > scheme > evaluator > "scheme_evaluator"
    - source_tool_version:  metric > scheme > generator_version
    - source_content_hash:  metric > scheme > persisted_hash

    Returns a dict with 4 source_* keys.
    """
    # source_id: metric.source_id > scheme.source_id > run_id
    if metric is not None and metric.get("source_id"):
        source_id = metric["source_id"]
    elif scheme.get("source_id"):
        source_id = scheme["source_id"]
    else:
        source_id = run_id

    # source_tool: metric > scheme > evaluator > "scheme_evaluator"
    if metric is not None and metric.get("source_tool"):
        source_tool = metric["source_tool"]
    elif scheme.get("source_tool"):
        source_tool = scheme["source_tool"]
    elif run_scheme_evaluator:
        source_tool = run_scheme_evaluator
    else:
        source_tool = "scheme_evaluator"

    # source_tool_version: metric > scheme > generator_version
    if metric is not None and metric.get("source_tool_version"):
        source_tool_version = metric["source_tool_version"]
    elif scheme.get("source_tool_version"):
        source_tool_version = scheme["source_tool_version"]
    else:
        source_tool_version = run_generator_version

    # source_content_hash: metric > scheme > persisted_hash
    if metric is not None and metric.get("source_content_hash"):
        source_content_hash = metric["source_content_hash"]
    elif scheme.get("source_content_hash"):
        source_content_hash = scheme["source_content_hash"]
    else:
        source_content_hash = run_persisted_content_hash

    return {
        "source_id": source_id,
        "source_tool": source_tool,
        "source_tool_version": source_tool_version,
        "source_content_hash": source_content_hash,
    }


def _build_scheme_comparison_section(
    data: dict[str, Any],
) -> CanonicalRenderSection:
    """Build the scheme_comparison section with a canonical table.

    Uses data.get("name", "") for scheme name (not "scheme_name").
    total_score is converted to Decimal deterministically.
    Metric order is deterministic (sorted keys).
    Provenance fields are added to scheme table cells.
    recommended_scheme is a code preserved across locales.
    """
    section_key = "scheme_comparison"
    level = _section_level(section_key)

    schemes = data.get("schemes", [])
    recommended = data.get("recommended_scheme", "")

    # Run-level provenance from section data (lowest fallback for cell provenance)
    run_generator_version = data.get("generator_version", "")
    run_scheme_evaluator = data.get("scheme_evaluator", "")
    run_persisted_content_hash = data.get("persisted_content_hash", "")

    if not schemes:
        return CanonicalRenderSection(
            section_key=section_key,
            title=section_key,
            level=level,
            content_type_code="empty",
            empty_reason_code="not_calculated",
        )

    # Identify known non-metric keys to exclude
    _NON_METRIC_KEYS: frozenset[str] = frozenset(
        {
            "scheme_id",
            "name",
            "rank",
            "source_id",
            "source_tool",
            "source_tool_version",
            "source_content_hash",
            "generator_version",
            "scheme_evaluator",
            "persisted_content_hash",
        }
    )

    # Known scheme metric keys — any key not in this registry or _NON_METRIC_KEYS
    # will be rejected with ValueError to fail closed on unrecognized fields.
    _SCHEME_METRIC_REGISTRY: tuple[str, ...] = (
        "total_score",
        "total_investment_cny",
        "total_area_m2",
        "operating_cost_per_year",
        "design_cooling_load_kw_r",
        "installed_power_kw_e",
        "compressor_operating_capacity_kw_r",
        "compressor_installed_capacity_kw_r",
        "compressor_standby_capacity_kw_r",
        "condenser_heat_rejection_kw",
        "investment_cny",
        "area_m2",
        "total_position_count",
        "room_module_count",
        "door_count",
        "partition_length_proxy_m",
        "energy_consumption",
        "annual_operating_cost",
        "net_present_value",
        "payback_period_years",
    )

    # Collect metric keys from ALL schemes, preserving registry order
    metric_keys_set: set[str] = set()
    for scheme in schemes:
        for k in scheme:
            if k not in _NON_METRIC_KEYS:
                if k not in _SCHEME_METRIC_REGISTRY:
                    raise ValueError(
                        f"Unknown scheme metric key {k!r} — not in _SCHEME_METRIC_REGISTRY. "
                        f"Allowed metrics: {sorted(_SCHEME_METRIC_REGISTRY)}"
                    )
                metric_keys_set.add(k)
    # Preserve the order from _SCHEME_METRIC_REGISTRY (not alphabet sorted)
    metric_keys = [mk for mk in _SCHEME_METRIC_REGISTRY if mk in metric_keys_set]

    # Build canonical table rows
    col_keys = ("scheme_id", "scheme_name", "rank") + tuple(metric_keys)
    rows: list[tuple[CanonicalRenderTableCell, ...]] = []
    run_id_val = data.get("run_id", "")
    for scheme in schemes:
        scheme_id_val = scheme.get("scheme_id", "")
        # Resolve scheme-level provenance for non-metric cells (metric=None → scheme > run)
        _scheme_prov = resolve_scheme_provenance(
            metric=None,
            scheme=scheme,
            run_id=run_id_val,
            run_scheme_evaluator=run_scheme_evaluator,
            run_generator_version=run_generator_version,
            run_persisted_content_hash=run_persisted_content_hash,
        )
        # Section-level provenance fields: scheme > run fallback for non-metric cells
        _scheme_gen_version = scheme.get("generator_version", run_generator_version)
        _scheme_scheme_evaluator = scheme.get("scheme_evaluator", run_scheme_evaluator)
        _scheme_persisted_hash = scheme.get("persisted_content_hash", run_persisted_content_hash)

        scheme_id_cell = CanonicalRenderTableCell(
            field_path="scheme_comparison.scheme_id",
            field_key="header.scheme_id",
            raw_value=scheme_id_val,
            align_code="left",
            **_scheme_prov,
            run_id=run_id_val,
            generator_version=_scheme_gen_version,
            scheme_evaluator=_scheme_scheme_evaluator,
            persisted_content_hash=_scheme_persisted_hash,
        )
        scheme_name = scheme.get("name", scheme.get("scheme_id", ""))
        name_cell = CanonicalRenderTableCell(
            field_path="scheme_comparison.scheme_name",
            field_key="header.scheme",
            raw_value=scheme_name,
            align_code="left",
            **_scheme_prov,
            run_id=run_id_val,
            generator_version=_scheme_gen_version,
            scheme_evaluator=_scheme_scheme_evaluator,
            persisted_content_hash=_scheme_persisted_hash,
        )

        rank_raw = scheme.get("rank")
        rank_cell = CanonicalRenderTableCell(
            field_path="scheme_comparison.rank",
            field_key="header.rank",
            raw_value=rank_raw if rank_raw is not None else None,
            align_code="right",
            **_scheme_prov,
            run_id=run_id_val,
            generator_version=_scheme_gen_version,
            scheme_evaluator=_scheme_scheme_evaluator,
            persisted_content_hash=_scheme_persisted_hash,
        )

        metric_cells = tuple(
            CanonicalRenderTableCell(
                field_path=f"scheme_comparison.{mk}",
                field_key=f"header.{mk}",
                raw_value=(
                    _canonicalize_numeric(scheme.get(mk, {}).get("value"))
                    if isinstance(scheme.get(mk), dict) and "value" in scheme.get(mk, {})
                    else (
                        _canonicalize_numeric(scheme.get(mk))
                        if mk in scheme and scheme.get(mk) is not None
                        else None
                    )
                ),
                unit_code=(
                    scheme.get(mk, {}).get("unit_code", scheme.get(mk, {}).get("unit", ""))
                    if isinstance(scheme.get(mk), dict)
                    else ""
                ),
                align_code="right",
                **resolve_scheme_provenance(
                    metric=(
                        metric_val if isinstance((metric_val := scheme.get(mk)), dict) else None
                    ),
                    scheme=scheme,
                    run_id=run_id_val,
                    run_scheme_evaluator=run_scheme_evaluator,
                    run_generator_version=run_generator_version,
                    run_persisted_content_hash=run_persisted_content_hash,
                ),
                run_id=run_id_val,
                # Per-metric provenance fallback: metric > scheme > run
                generator_version=(
                    metric_val.get(
                        "generator_version", scheme.get("generator_version", run_generator_version)
                    )
                    if isinstance(metric_val, dict) and "generator_version" in metric_val
                    else scheme.get("generator_version", run_generator_version)
                ),
                scheme_evaluator=(
                    metric_val.get(
                        "scheme_evaluator", scheme.get("scheme_evaluator", run_scheme_evaluator)
                    )
                    if isinstance(metric_val, dict) and "scheme_evaluator" in metric_val
                    else scheme.get("scheme_evaluator", run_scheme_evaluator)
                ),
                persisted_content_hash=(
                    metric_val.get(
                        "persisted_content_hash",
                        scheme.get("persisted_content_hash", run_persisted_content_hash),
                    )
                    if isinstance(metric_val, dict) and "persisted_content_hash" in metric_val
                    else scheme.get("persisted_content_hash", run_persisted_content_hash)
                ),
            )
            for mk in metric_keys
        )
        rows.append((scheme_id_cell, name_cell, rank_cell, *metric_cells))

    # Determine unit codes for each column (sorted metric keys for determinism)
    first_scheme = schemes[0] if schemes else {}
    unit_codes: list[str] = ["", "", ""]  # scheme_id, scheme_name and rank have no unit
    for mk in metric_keys:
        val = first_scheme.get(mk, {})
        if isinstance(val, dict):
            unit_codes.append(str(val.get("unit_code", val.get("unit", ""))))
        else:
            unit_codes.append("")

    table = CanonicalRenderTable(
        table_key="scheme_comparison",
        title_key="section.scheme_comparison",
        column_keys=col_keys,
        rows=tuple(rows),
        unit_codes=tuple(unit_codes),
    )

    text_fields: dict[str, str] = {}
    # Preserve run-level provenance fields on the section (except run_id which is on cells)
    for prov_key in ("generator_version", "scheme_evaluator", "persisted_content_hash"):
        prov_val = data.get(prov_key)
        if prov_val is not None:
            text_fields[prov_key] = str(prov_val)

    return CanonicalRenderSection(
        section_key=section_key,
        title=section_key,
        level=level,
        content_type_code="table",
        table=table,
        text_fields=text_fields,
        recommended_scheme_code=recommended,
    )


def _build_quality_summary_section(
    data: dict[str, Any],
) -> CanonicalRenderSection:
    """Build the quality_summary section from top-level content["quality_summary"].

    Reads findings from the quality_summary dict and converts them
    to CanonicalFinding objects.
    """
    section_key = "quality_summary"
    level = _section_level(section_key)

    findings_raw = data.get("findings", [])
    total = data.get("total_findings", 0)

    if not findings_raw and total == 0:
        return CanonicalRenderSection(
            section_key=section_key,
            title=section_key,
            level=level,
            content_type_code="empty",
            empty_reason_code="not_provided",
        )

    canonical_findings = tuple(
        CanonicalFinding(
            code=f.get("code", ""),
            severity_code=f.get("severity", f.get("severity_code", "")),
            message=f.get("message", ""),
            section_key=f.get("section_key", ""),
            field_path=f.get("field_path", ""),
        )
        for f in findings_raw
    )

    text_fields: dict[str, str] = {}
    if total:
        text_fields["total_findings"] = str(total)
    blocker_count = data.get("blocker_count", 0)
    if blocker_count:
        text_fields["blocker_count"] = str(blocker_count)
    warning_count = data.get("warning_count", 0)
    if warning_count:
        text_fields["warning_count"] = str(warning_count)
    info_count = data.get("info_count", 0)
    if info_count:
        text_fields["info_count"] = str(info_count)

    return CanonicalRenderSection(
        section_key=section_key,
        title=section_key,
        level=level,
        content_type_code="finding",
        findings=canonical_findings,
        text_fields=text_fields,
    )


def _build_citations_section(
    data: list[dict[str, Any]] | Any,
) -> CanonicalRenderSection:
    """Build the citations section from top-level content["citations"]."""
    section_key = "citations"
    level = _section_level(section_key)

    if not isinstance(data, (list, tuple)) or not data:
        return CanonicalRenderSection(
            section_key=section_key,
            title=section_key,
            level=level,
            content_type_code="empty",
            empty_reason_code="not_provided",
        )

    canonical_citations = tuple(
        CanonicalCitation(
            section_key=c.get("section_key", ""),
            source_type_code=c.get("source_type", c.get("source_type_code", "")),
            source_id=c.get("source_id", ""),
            tool_name=c.get("tool_name", ""),
            content_hash=c.get("content_hash", ""),
        )
        for c in data
    )

    # Build citations table
    col_keys = ("section", "source_type", "source_id", "tool", "content_hash")
    _ATTR_MAP = {
        "section": "section_key",
        "source_type": "source_type_code",
        "source_id": "source_id",
        "tool": "tool_name",
        "content_hash": "content_hash",
    }
    rows: list[tuple[CanonicalRenderTableCell, ...]] = []
    for c in canonical_citations:
        row = tuple(
            CanonicalRenderTableCell(
                field_path=f"citations.{_ATTR_MAP[col]}",
                field_key=f"header.{col}",
                raw_value=getattr(c, _ATTR_MAP[col], ""),
            )
            for col in col_keys
        )
        rows.append(row)

    table = CanonicalRenderTable(
        table_key="citation_sources",
        title_key="header.citation_sources",
        column_keys=col_keys,
        rows=tuple(rows),
    )

    return CanonicalRenderSection(
        section_key=section_key,
        title=section_key,
        level=level,
        content_type_code="table",
        citations=canonical_citations,
        table=table,
    )


def _build_provenance_section(
    data: dict[str, Any],
) -> CanonicalRenderSection:
    """Build a provenance section from report content provenance data.

    Extracts provenance fields (content_hash, canonical_hash, etc.)
    and preserves them as text_fields on the section.
    """
    section_key = "provenance"
    level = _section_level(section_key)

    if not data:
        return CanonicalRenderSection(
            section_key=section_key,
            title=section_key,
            level=level,
            content_type_code="empty",
            empty_reason_code="not_provided",
        )

    text_fields = _extract_text_fields(data)
    return CanonicalRenderSection(
        section_key=section_key,
        title=section_key,
        level=level,
        content_type_code="text",
        text_fields=text_fields,
    )


def _build_throughput_inventory_area_section(
    data: dict[str, Any],
) -> CanonicalRenderSection:
    """Build the throughput_inventory_area section with numeric values, units, and provenance."""
    section_key = "throughput_inventory_area"
    level = _section_level(section_key)

    if not data:
        return CanonicalRenderSection(
            section_key=section_key,
            title=section_key,
            level=level,
            content_type_code="empty",
            empty_reason_code="not_provided",
        )

    metrics = _extract_canonical_metrics(section_key, data)
    if metrics:
        return CanonicalRenderSection(
            section_key=section_key,
            title=section_key,
            level=level,
            content_type_code="metrics",
            metrics=tuple(metrics),
        )

    # Fallback: text fields if no measured values
    text_fields = _extract_text_fields(data)
    if text_fields:
        return CanonicalRenderSection(
            section_key=section_key,
            title=section_key,
            level=level,
            content_type_code="text",
            text_fields=text_fields,
        )

    return CanonicalRenderSection(
        section_key=section_key,
        title=section_key,
        level=level,
        content_type_code="empty",
        empty_reason_code="not_provided",
    )


def _build_canonical_section(
    section_key: str,
    data: dict[str, Any] | Any,
) -> CanonicalRenderSection:
    """Build a section with only canonical (non-localized) data."""
    level = _section_level(section_key)

    # Handle special sections with explicit data structures
    if section_key == "risks_and_missing_information" and isinstance(data, dict):
        return _build_risks_and_missing_information_section(data)

    if section_key == "investment_estimate" and isinstance(data, dict):
        return _build_investment_estimate_section(data)

    if section_key == "scheme_comparison" and isinstance(data, dict):
        return _build_scheme_comparison_section(data)

    if section_key == "throughput_inventory_area" and isinstance(data, dict):
        return _build_throughput_inventory_area_section(data)

    if section_key == "quality_summary" and isinstance(data, dict):
        return _build_quality_summary_section(data)

    if section_key == "citations" and isinstance(data, (list, tuple)):
        return _build_citations_section(data)

    if section_key == "provenance" and isinstance(data, dict):
        return _build_provenance_section(data)

    # For text sections, preserve key-value pairs
    if section_key in _TEXT_SECTIONS and isinstance(data, dict):
        return _build_text_section(section_key, data)

    # For dict data, try to extract metrics
    if isinstance(data, dict):
        metrics = _extract_canonical_metrics(section_key, data)
        if metrics:
            return CanonicalRenderSection(
                section_key=section_key,
                title=section_key,
                level=level,
                content_type_code="metrics",
                metrics=tuple(metrics),
            )

    # Reject unrecognized non-dict data — fail-closed
    if data is not None and not isinstance(data, dict):
        raise ValueError(
            f"Unrecognized section {section_key!r} has non-dict data type "
            f"{type(data).__name__}; cannot build canonical section."
        )
    return CanonicalRenderSection(
        section_key=section_key,
        title=section_key,
        level=level,
        content_type_code="empty",
        empty_reason_code="not_provided" if not data else "",
    )


def build_canonical_render_model(
    *,
    content: dict[str, Any],
    report_id: str,
    revision_number: int,
    content_hash: str,
    generated_by: str,
    generated_at: str,
    template_code: str,
    template_version: str,
    approval_snapshot: ApprovalSnapshot | None = None,
) -> CanonicalReportRenderModel:
    """Build a locale-free canonical render model.

    This function does NOT accept a locale parameter and does NOT
    import or use any translation/localization functions.
    All display text is absent from the canonical model.
    """
    meta_section = content.get("report_metadata", {})
    project_summary = content.get("project_summary", {})
    project_name = project_summary.get("project_name", "") or meta_section.get("project_id", "")

    schema_version = meta_section.get("schema_version", template_version)

    if isinstance(generated_at, datetime):
        generated_at_str = generated_at.isoformat()
    else:
        generated_at_str = str(generated_at) if generated_at else ""

    metadata = CanonicalRenderMetadata(
        report_id=report_id,
        project_name=project_name,
        report_type=meta_section.get("report_type", template_code),
        schema_version=schema_version,
        revision_number=revision_number,
        content_hash=content_hash,
        content_hash_short=content_hash[:8] if content_hash else "",
        generated_at=generated_at_str,
        generated_by=generated_by,
        template_version=template_version,
        template_code=template_code,
    )

    # Validate all content keys against the schema registry — fail closed on unknown keys
    for content_key in content:
        if content_key not in _REPORT_SCHEMA_PROPERTIES:
            raise ValueError(
                f"Unrecognized section key {content_key!r} in content — not in "
                f"_REPORT_SCHEMA_PROPERTIES ({sorted(_REPORT_SCHEMA_PROPERTIES)}). "
                "Unknown sections are not allowed."
            )

    # Build sections with canonical data
    sections: list[CanonicalRenderSection] = []
    # Process all known schema properties in order, plus provenance and render-only sections
    _SECTION_BUILD_ORDER: tuple[str, ...] = (
        "report_metadata",
        "project_summary",
        "input_conditions",
        "assumptions",
        "throughput_inventory_area",
        "cooling_load",
        "equipment_selection",
        "electrical_and_energy",
        "scheme_comparison",
        "investment_estimate",
        "risks_and_missing_information",
        "quality_summary",
        "citations",
        "provenance",
    )

    for key in _SECTION_BUILD_ORDER:
        data = content.get(key)
        if data is None:
            sections.append(
                CanonicalRenderSection(
                    section_key=key,
                    title=key,
                    level=_section_level(key),
                    content_type_code="empty",
                    empty_reason_code="not_provided",
                )
            )
        else:
            sections.append(_build_canonical_section(key, data))

    manifest = RenderManifest(
        template_code=template_code,
        template_version=template_version,
        schema_version=schema_version,
        source_content_hash=content_hash,
        sections=list(_SECTION_KEYS),
        format="docx",
    )
    from dataclasses import replace as dc_replace

    manifest = dc_replace(manifest, manifest_hash=manifest.compute_hash())

    return CanonicalReportRenderModel(
        metadata=metadata,
        sections=tuple(sections),
        manifest=manifest,
        approval_snapshot=approval_snapshot,
    )
