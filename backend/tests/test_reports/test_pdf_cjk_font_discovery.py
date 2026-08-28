"""PDF CJK font discovery: OS faces, env override, PyMuPDF builtin fallback."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from cold_storage.modules.reports.domain.render_model import (
    CanonicalRenderMetadata,
    LocalizedRenderMetadata,
    LocalizedRenderSection,
    LocalizedReportRenderModel,
    RenderManifest,
)
from cold_storage.modules.reports.renderers import cjk_font
from cold_storage.modules.reports.renderers.cjk_font import (
    CJK_FONT_PATH_ENV,
    find_cjk_font,
    reset_cjk_font_cache,
)
from cold_storage.modules.reports.renderers.pdf_renderer import PdfRenderer

_PROBE_GLYPH = "测"


@pytest.fixture()
def isolated_cjk_cache():
    reset_cjk_font_cache()
    yield
    reset_cjk_font_cache()


def _assert_font_file_has_cjk(path: str) -> None:
    font = fitz.Font(fontfile=path)
    assert font.has_glyph(ord(_PROBE_GLYPH)), path


def test_find_cjk_font_returns_readable_cjk_file(isolated_cjk_cache: None) -> None:
    path = find_cjk_font()
    assert Path(path).is_file()
    _assert_font_file_has_cjk(path)


def test_env_override_wins_over_system_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_cjk_cache: None,
) -> None:
    source = find_cjk_font()
    reset_cjk_font_cache()
    custom = tmp_path / "operator-cjk.ttf"
    custom.write_bytes(Path(source).read_bytes())
    monkeypatch.setenv(CJK_FONT_PATH_ENV, str(custom))
    assert find_cjk_font() == str(custom)


def test_candidates_include_macos_and_windows_system_fonts() -> None:
    joined = "\n".join(cjk_font._CJK_FONT_CANDIDATES)
    assert "PingFang.ttc" in joined
    assert "STHeiti" in joined
    windows = cjk_font._windows_font_candidates()
    assert any(name.endswith("msyh.ttc") for name in windows)
    assert any(name.endswith("simsun.ttc") for name in windows)


def test_builtin_fallback_when_no_system_font_file(
    monkeypatch: pytest.MonkeyPatch,
    isolated_cjk_cache: None,
) -> None:
    monkeypatch.delenv(CJK_FONT_PATH_ENV, raising=False)
    monkeypatch.setattr(cjk_font, "_CJK_FONT_CANDIDATES", ())
    monkeypatch.setattr(cjk_font, "_windows_font_candidates", lambda: [])
    monkeypatch.setattr(cjk_font, "_font_scan_roots", lambda: [])
    path = find_cjk_font()
    assert Path(path).is_file()
    assert "cold-storage-cjk-fonts" in path
    _assert_font_file_has_cjk(path)


def test_raises_when_no_file_and_builtin_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    isolated_cjk_cache: None,
) -> None:
    monkeypatch.delenv(CJK_FONT_PATH_ENV, raising=False)
    monkeypatch.setattr(cjk_font, "_CJK_FONT_CANDIDATES", ())
    monkeypatch.setattr(cjk_font, "_windows_font_candidates", lambda: [])
    monkeypatch.setattr(cjk_font, "_font_scan_roots", lambda: [])
    monkeypatch.setattr(cjk_font, "_materialize_pymupdf_cjk_font", lambda: None)
    with pytest.raises(RuntimeError, match="No CJK font found"):
        find_cjk_font()


def test_pdf_render_succeeds_with_builtin_cjk_only(
    monkeypatch: pytest.MonkeyPatch,
    isolated_cjk_cache: None,
) -> None:
    monkeypatch.delenv(CJK_FONT_PATH_ENV, raising=False)
    monkeypatch.setattr(cjk_font, "_CJK_FONT_CANDIDATES", ())
    monkeypatch.setattr(cjk_font, "_windows_font_candidates", lambda: [])
    monkeypatch.setattr(cjk_font, "_font_scan_roots", lambda: [])

    canonical_meta = CanonicalRenderMetadata(
        report_id="r-cjk-fallback",
        project_name="蓝莓冷库概念设计项目",
        report_type="概念设计报告",
        schema_version="cold_storage_concept_design@1.0.0",
        revision_number=1,
        content_hash="a" * 64,
        content_hash_short="a" * 8,
        generated_at="2025-01-01T00:00:00+00:00",
        generated_by="test-system",
        template_version="1.0.0",
        template_code="cold_storage_concept_design",
    )
    metadata = LocalizedRenderMetadata(
        canonical=canonical_meta,
        project_name=canonical_meta.project_name,
        report_type_label="概念设计报告",
        confidentiality_label="",
        disclaimer="本文件为概念设计草稿。",
        empty_section_placeholder="",
        cover_title="概念设计报告",
        cover_version_line="",
        control_info_title="",
        content_hash_label="",
        template_version_label="",
        generated_by_label="",
        generated_at_label="",
        revision_label="",
        watermark_text="",
    )
    section = LocalizedRenderSection(
        section_key="overview",
        title="项目概述",
        level=1,
        content_type="text",
        text="日入库用于规划预冷与储存。",
    )
    model = LocalizedReportRenderModel(
        metadata=metadata,
        sections=[section],
        manifest=RenderManifest(
            template_code="cold_storage_concept_design",
            template_version="1.0.0",
            schema_version="cold_storage_concept_design@1.0.0",
            source_content_hash="a" * 64,
            sections=["overview"],
            format="pdf",
            render_settings={},
        ),
    )
    pdf_bytes = PdfRenderer().render(model, is_draft=True)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    extracted = "".join(page.get_text() for page in doc)
    doc.close()
    assert "项目概述" in extracted
    assert "预冷" in extracted
    assert "储存" in extracted
