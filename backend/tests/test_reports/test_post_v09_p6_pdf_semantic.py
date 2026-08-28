"""POST-V0.9 P6 leftovers: zh-CN PDF heading NFKC and compact-table binding."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cold_storage.evaluation import pilot_reports as ppr
from cold_storage.modules.reports.application.canonical_render_model_builder import (
    build_canonical_render_model,
)
from cold_storage.modules.reports.application.render_model_localizer import localize_render_model
from cold_storage.modules.reports.domain.enums import ExportFormat, ReportLocale
from cold_storage.modules.reports.renderers.pdf_renderer import PdfRenderer

_PDF_MANIFEST = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "src/cold_storage/modules/reports/templates/"
        / "cold_storage_concept_design/1.0.0/pdf/manifest.json"
    ).read_text(encoding="utf-8")
)

_P14_LIKE_CONTENT = {
    "report_metadata": {
        "schema_version": "cold_storage_concept_design@1.0.0",
        "project_id": "p1",
    },
    "project_summary": {"project_name": "Demo"},
    "input_conditions": {
        "daily_inbound_mass_kg": 20000,
        "finished_storage_days": 7,
        "frozen_storage_days": 10,
        "main_packaging_storage_days": 4,
        "auxiliary_packaging_storage_days": 12,
    },
    "assumptions": {},
    "throughput_inventory_area": {
        "daily_inbound_mass_kg": 20000,
        "total_area_m2": 350.5,
        "zone_details": [
            {
                "zone_name": "成品库A",
                "temperature_band": "0~4C",
                "required_area_m2": 200.0,
                "position_count": 30,
            }
        ],
    },
    "calculation_logic": {"stages": []},
    "cooling_load": {
        "total_design_refrigeration_load": {
            "value": 25.0,
            "unit": "kW(r)",
            "source_tool": "cooling_load",
            "source_tool_version": "1.0.0",
        }
    },
    "equipment_selection": {
        "total_compressor_capacity": {
            "value": 25.0,
            "unit": "kW(r)",
            "source_tool": "equipment",
            "source_tool_version": "1.0.0",
        },
        "condenser_heat_rejection": {
            "value": 30.0,
            "unit": "kW(th)",
            "source_tool": "equipment",
            "source_tool_version": "1.0.0",
        },
    },
    "electrical_and_energy": {
        "total_installed_power": {
            "value": 200.0,
            "unit": "kW(e)",
            "source_tool": "installed_power",
            "source_tool_version": "1.0.0",
        }
    },
    "scheme_comparison": {
        "run_id": "scheme-run-1",
        "generator_version": "scheme_generator@1.0.0",
        "scheme_evaluator": "scheme_evaluator",
        "persisted_content_hash": "ea4ab8cd7f73b50cabcdef1234567890abcdef12",
        "recommended_scheme": "scheme_a",
        "schemes": [
            {
                "scheme_id": "scheme_a",
                "name": "方案A",
                "rank": 1,
                "total_score": {
                    "value": "100.000",
                    "unit": "",
                    "source_tool_version": "1.0.0",
                    "source_content_hash": "ea4ab8cd7f73b50cabcdef1234567890abcdef12",
                },
            }
        ],
    },
    "investment_estimate": {"total_investment": 1000},
    "risks_and_missing_information": {"risks": [], "missing_information": []},
    "quality_summary": {
        "total_findings": 0,
        "blocker_count": 0,
        "warning_count": 0,
        "info_count": 0,
        "findings": [],
    },
    "citations": [],
    "provenance": {},
}


def _pdf_line(page: int, text: str, size: float, idx: int = 0) -> ppr._PdfLine:
    return ppr._PdfLine(
        page_number=page,
        block_index=idx,
        line_index=idx,
        text=text,
        bbox=(50.0, 80.0, 200.0, 96.0),
        max_font_size=size,
    )


def test_section_page_filter_ignores_watermark_and_drops_next_section() -> None:
    """Draft watermarks are large; only catalog titles bound section pages."""

    cooling = _pdf_line(2, "冷却负荷", 16.0, 0)
    watermark_p2 = _pdf_line(2, "草稿", 72.0, 1)
    row_p2 = _pdf_line(2, "项目", 9.5, 2)
    watermark_p3 = _pdf_line(3, "草稿", 72.0, 0)
    row_p3 = _pdf_line(3, "25.0", 9.0, 1)
    equipment = _pdf_line(4, "设备选型", 16.0, 0)
    watermark_p4 = _pdf_line(4, "草稿", 72.0, 1)
    leaked_header = _pdf_line(4, "项目", 9.5, 2)
    all_lines = (
        cooling,
        watermark_p2,
        row_p2,
        watermark_p3,
        row_p3,
        equipment,
        watermark_p4,
        leaked_header,
    )
    observation = ppr._PdfObservation(all_lines=all_lines, section_scopes={})
    kept = ppr._section_lines_without_next_section_pages(
        pdf_observation=observation,
        section_lines=all_lines,
        known_section_headings=frozenset({"冷却负荷", "设备选型"}),
        current_heading_text="冷却负荷",
    )
    assert {line.page_number for line in kept} == {2, 3}


def test_section_page_filter_noop_without_heading_catalog() -> None:
    """Direct reconstruction callers must keep continuation pages as-is."""

    heading = _pdf_line(1, "Investment Estimate", 16.0)
    watermark = _pdf_line(1, "DRAFT", 72.0, 1)
    continuation_wm = _pdf_line(2, "DRAFT", 72.0, 0)
    row = _pdf_line(2, "50.0", 9.0, 1)
    section_lines = (heading, watermark, continuation_wm, row)
    observation = ppr._PdfObservation(all_lines=section_lines, section_scopes={})
    kept = ppr._section_lines_without_next_section_pages(
        pdf_observation=observation,
        section_lines=section_lines,
    )
    assert kept == section_lines


def test_fold_whitespace_maps_cjk_compatibility_ideographs_for_quantity() -> None:
    """PDF CJK fonts often round-trip 量 to U+F97E; headings must still match."""
    catalog = "质量摘要"
    extracted = "质\uf97e摘要"
    assert ppr._fold_whitespace(extracted) == ppr._fold_whitespace(catalog)
    assert ppr._fold_whitespace("Ａ１") == "A1"


def test_pdf_section_scopes_match_quality_summary_with_compatibility_glyph() -> None:
    observation = ppr._PdfObservation(
        all_lines=(
            ppr._PdfLine(
                page_number=1,
                block_index=0,
                line_index=0,
                text="质\uf97e摘要",
                bbox=(50.0, 80.0, 200.0, 96.0),
                max_font_size=16.0,
            ),
        ),
        section_scopes={},
    )
    resolved = ppr._resolve_pdf_section_scopes(
        observation=observation,
        section_scopes=(ppr._SectionScope(section_key="quality_summary", heading_text="质量摘要"),),
    )
    assert "quality_summary" in resolved


def test_zh_cn_pdf_semantic_passes_for_compact_tables_and_quality_summary() -> None:
    """Living leftover from P6: consecutive Item/Value/Unit tables plus 质量摘要."""
    pytest.importorskip("fitz")
    canonical = build_canonical_render_model(
        content=_P14_LIKE_CONTENT,
        report_id="r1",
        revision_number=1,
        content_hash="hash",
        generated_by="tester",
        generated_at="2026-08-28T00:00:00Z",
        template_code="cold_storage_concept_design",
        template_version="1.0.0",
    )
    localized = localize_render_model(
        canonical,
        locale=ReportLocale.ZH_CN,
        template_manifest_json=_PDF_MANIFEST,
        format="pdf",
    )
    pdf_bytes = PdfRenderer().render(localized)
    checks = ppr._semantic_checks(
        canonical_model=canonical,
        template=SimpleNamespace(manifest_json=_PDF_MANIFEST),
        locale=ReportLocale.ZH_CN,
        fmt=ExportFormat.PDF,
        artifact_bytes=pdf_bytes,
    )
    assert checks["missing_sections"] == []
    assert "质量摘要" in checks["observed_localized_headings"]
    assert checks["numeric_mismatches"] == []
    assert checks["semantic_result"] == "PASS"
    compact_paths = {
        "cooling_load.total_design_refrigeration_load.value",
        "equipment_selection.total_compressor_capacity.value",
        "equipment_selection.condenser_heat_rejection.value",
        "electrical_and_energy.total_installed_power.value",
    }
    observed = {row["field_path"]: row for row in checks["observed_numeric_fields"]}
    for path in compact_paths:
        assert observed[path]["binding_status"] == "BOUND", path
