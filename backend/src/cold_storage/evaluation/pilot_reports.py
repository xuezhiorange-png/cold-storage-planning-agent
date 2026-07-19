"""Multilingual report pilot verifier for the frozen TASK-011 Slice 1 contract."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import fitz
from docx import Document
from docx.oxml.ns import qn as _docx_qn

from cold_storage.evaluation.artifact_io import (
    assert_no_managed_artifacts,
    atomic_write_bytes,
    atomic_write_json,
)
from cold_storage.evaluation.errors import EvaluationRunnerError
from cold_storage.modules.reports.application.canonical_render_model_builder import (
    build_canonical_render_model,
)
from cold_storage.modules.reports.application.render_model_localizer import (
    localize_render_model,
)
from cold_storage.modules.reports.domain.enums import (
    ArtifactStatus,
    ExportFormat,
    ReportLocale,
    ReportType,
)
from cold_storage.modules.reports.domain.render_model import (
    CanonicalRenderMetric,
    CanonicalRenderTableCell,
    CanonicalReportRenderModel,
)
from cold_storage.modules.reports.localization.catalog import (
    compute_catalog_content_hash,
    get_catalog,
)

PILOT_RESULT_SCHEMA_VERSION = "task11-pilot-report.v1"
PILOT_CHECK_ID = "multilingual_report_same_revision"
_SHA256_LENGTH = 64
_RENDER_MATRIX: tuple[tuple[ReportLocale, ExportFormat], ...] = (
    (ReportLocale.ZH_CN, ExportFormat.DOCX),
    (ReportLocale.ZH_CN, ExportFormat.PDF),
    (ReportLocale.EN_US, ExportFormat.DOCX),
    (ReportLocale.EN_US, ExportFormat.PDF),
)
DownloadArtifact = Callable[[str, str, str], tuple[bytes, Mapping[str, str]]]


class PilotVerificationError(EvaluationRunnerError):
    """Typed fail-closed error for a pilot acceptance mismatch."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=dict(details or {}))
        self.code = code


def _fail(code: str, message: str, **details: Any) -> None:
    raise PilotVerificationError(code, message, details=details)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != _SHA256_LENGTH:
        return False
    return all(char in "0123456789abcdef" for char in value)


# ---------------------------------------------------------------------------
# P1-3: Structured artifact observation + field-bound verification
# ---------------------------------------------------------------------------
#
# The P1-3 fix removes the previous global substring search
# (metric.display_value in extracted_text) and replaces it with:
#
#   DOWNLOADED_ARTIFACT
#   → STRUCTURED_OBSERVATION  (_observe_docx / _observe_pdf)
#   → SECTION/FIELD/ROW_BINDING  (_find_metric_binding / _find_number_binding
#                                 / _find_table_cell_binding)
#   → OBSERVED_VALUE_AND_UNIT    (_ObservedNumericField)
#   → EXPECTED_LOCALIZED_VALUE_AND_UNIT_COMPARISON  (whitespace fold only)
#   → FAIL_CLOSED   (8 typed codes, no false PASS)
#
# The numeric comparison NEVER operates on a flattened global string. It
# only operates on the structured observation scoped to the target
# section/field/row/column, and the observed value/unit come from the
# downloaded artifact bytes, NOT from the localized expected model.


_BINDING_KIND_METRIC = "metric"
_BINDING_KIND_NUMBER = "number"
_BINDING_KIND_TABLE_CELL = "table_cell"

_BINDING_KINDS: tuple[str, ...] = (
    _BINDING_KIND_METRIC,
    _BINDING_KIND_NUMBER,
    _BINDING_KIND_TABLE_CELL,
)


@dataclass(frozen=True, slots=True)
class _ObservedNumericField:
    """Real artifact observation for a single canonical numeric field.

    The fields are populated from the downloaded artifact (DOCX/PDF
    bytes), NOT from the localized expected model. The
    ``binding_kind`` and ``section_key`` describe the structural
    position the observation was taken from.
    """

    field_path: str
    section_key: str
    binding_kind: str  # "metric" | "number" | "table_cell"
    display_value: str
    display_unit: str
    row_index: int | None = None
    column_index: int | None = None
    page_number: int | None = None


def _fold_whitespace(text: str) -> str:
    """Collapse runs of internal whitespace to a single space, strip ends.

    Permitted per the P1-3 contract:
        - remove leading/trailing whitespace
        - collapse pure-typographic runs of whitespace
    NOT permitted:
        - rewriting decimal/thousands separators
        - fuzzy numeric tolerance
        - dropping sign or unit
    """

    return " ".join(text.split())


def _strings_equal_folded(a: str, b: str) -> bool:
    """Compare two strings after whitespace folding only."""

    return _fold_whitespace(a) == _fold_whitespace(b)


# ── DOCX observation ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _DocxBlock:
    kind: str  # "paragraph" | "table"
    text: str
    paragraph_index: int | None
    table_index: int | None
    cells: tuple[tuple[str, ...], ...] | None  # only for tables
    heading_text: str | None  # for paragraphs that are headings
    heading_level: int | None  # 1..6 for heading paragraphs


@dataclass(frozen=True, slots=True)
class _DocxObservation:
    body_blocks: tuple[_DocxBlock, ...]
    # section_key -> (start_block_idx_inclusive, end_block_idx_exclusive)
    section_scopes: dict[str, tuple[int, int]]


def _observe_docx(data: bytes) -> _DocxObservation:
    """Walk a downloaded DOCX in body-order to produce structured blocks.

    The walk visits ``w:body`` children in original XML order. A
    ``w:p`` (paragraph) is recorded with its text + heading style
    detection; a ``w:tbl`` (table) is recorded as a 2-D cell grid.
    ``w:sectPr`` (the trailing section properties) is ignored.

    Section scope is determined by Heading 1 paragraphs: a Heading 1
    starts a new section, and the section extends until the next
    Heading 1 or end-of-document.
    """
    document = Document(io.BytesIO(data))
    body = document.element.body

    # First pass: identify Heading 1 paragraphs in body-order to build
    # section boundaries. We use the localized title text the renderer
    # would emit (Heading 1, ``w:pStyle w:val="Heading 1"``).
    blocks: list[_DocxBlock] = []
    para_counter = 0
    table_counter = 0
    for child in body:
        tag = child.tag.split("}", 1)[-1] if "}" in child.tag else child.tag
        if tag == "p":
            p_elem = child
            # Detect pStyle
            heading_text: str | None = None
            heading_level: int | None = None
            pPr = p_elem.find(_docx_qn("w:pPr"))
            if pPr is not None:
                pStyle = pPr.find(_docx_qn("w:pStyle"))
                if pStyle is not None:
                    style_val = pStyle.get(_docx_qn("w:val"), "")
                    if style_val.startswith("Heading"):
                        # Accept ``Heading1``, ``Heading 1``, ``Heading 1.0``,
                        # ``heading1`` (case-insensitive). The numeric
                        # suffix may or may not be separated by a space.
                        suffix = style_val[len("Heading") :].strip()
                        try:
                            heading_level = int(suffix.split(".")[0])
                        except (ValueError, IndexError):
                            heading_level = None
                        # Pull all text from this paragraph.
                        text = "".join(t.text or "" for t in p_elem.iter(_docx_qn("w:t")))
                        heading_text = text
            # Normal paragraph text (always)
            text = "".join(t.text or "" for t in p_elem.iter(_docx_qn("w:t")))
            blocks.append(
                _DocxBlock(
                    kind="paragraph",
                    text=text,
                    paragraph_index=para_counter,
                    table_index=None,
                    cells=None,
                    heading_text=heading_text,
                    heading_level=heading_level,
                )
            )
            para_counter += 1
        elif tag == "tbl":
            tbl_elem = child
            rows: list[tuple[str, ...]] = []
            for tr in tbl_elem.findall(_docx_qn("w:tr")):
                cells: list[str] = []
                for tc in tr.findall(_docx_qn("w:tc")):
                    cell_text = "".join(t.text or "" for t in tc.iter(_docx_qn("w:t")))
                    cells.append(cell_text)
                rows.append(tuple(cells))
            # Combined text of the table (one row per line).
            combined = "\n".join("|".join(row) for row in rows)
            blocks.append(
                _DocxBlock(
                    kind="table",
                    text=combined,
                    paragraph_index=None,
                    table_index=table_counter,
                    cells=tuple(rows),
                    heading_text=None,
                    heading_level=None,
                )
            )
            table_counter += 1
        elif tag == "sectPr":
            # Trailing sectPr — skip.
            continue
        # Other elements (e.g. sdt) are ignored for binding purposes.

    # Second pass: build section scopes from Heading 1 paragraphs.
    # We don't have a heading→section_key map at this layer; the
    # caller (P1-3 _semantic_checks) supplies the heading→section_key
    # map from the localized model. We expose heading_text on each
    # paragraph and let the caller resolve.
    heading_indices: list[int] = []
    for idx, block in enumerate(blocks):
        if block.kind == "paragraph" and block.heading_level == 1 and block.heading_text:
            heading_indices.append(idx)
    section_scopes: dict[str, tuple[int, int]] = {}
    return _DocxObservation(
        body_blocks=tuple(blocks),
        section_scopes=section_scopes,
    )


# ── PDF observation ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _PdfLine:
    page_number: int
    block_index: int
    line_index: int
    text: str
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class _PdfTableGrid:
    """A 2-D grid reconstructed from PDF text lines (rows clustered by y).

    For real-renderer PDF tables, the renderer draws each cell as a
    separate text line positioned at a specific (x, y). This is a
    best-effort reconstruction: lines with overlapping y-coordinates
    form a row; within a row, lines are sorted by x to get column
    order. The unit row is identified as the row whose leftmost cell
    text matches one of the canonical unit codes.
    """

    page_number: int
    rows: tuple[tuple[_PdfLine, ...], ...]
    # unit_row_idx: index of the row that contains the unit labels.
    unit_row_idx: int | None


@dataclass(frozen=True, slots=True)
class _PdfObservation:
    all_lines: tuple[_PdfLine, ...]
    tables: tuple[_PdfTableGrid, ...]
    # section_key -> (start_line_index_in_global, end_line_index_exclusive)
    section_scopes: dict[str, tuple[int, int]]


_Y_TOLERANCE = 2.0  # pixels for clustering lines into rows


def _cluster_lines_into_rows(
    lines: tuple[_PdfLine, ...], *, y_tolerance: float = _Y_TOLERANCE
) -> tuple[tuple[_PdfLine, ...], ...]:
    """Group PDF lines into rows by y-coordinate, sorted top-to-bottom."""

    if not lines:
        return ()
    sorted_lines = sorted(lines, key=lambda ln: (ln.bbox[1], ln.bbox[0]))
    rows: list[list[_PdfLine]] = []
    current_row: list[_PdfLine] = [sorted_lines[0]]
    for line in sorted_lines[1:]:
        if abs(line.bbox[1] - current_row[0].bbox[1]) <= y_tolerance:
            current_row.append(line)
        else:
            rows.append(current_row)
            current_row = [line]
    rows.append(current_row)
    # Sort each row by x (left-to-right).
    return tuple(tuple(sorted(row, key=lambda ln: ln.bbox[0])) for row in rows)


def _observe_pdf(data: bytes) -> _PdfObservation:
    """Walk a downloaded PDF to produce structured lines + best-effort table grid.

    Uses ``page.get_text("dict")`` to extract blocks → lines → spans
    while preserving the spatial layout. Each line is recorded with
    its page number, block index, line index, text, and bounding box.
    The walker also reconstructs a 2-D table grid by y-coordinate
    clustering: lines that share an overlapping y-band form a row,
    and lines within a row are sorted by x to get column order.
    """

    all_lines: list[_PdfLine] = []
    with fitz.open(stream=data, filetype="pdf") as document:
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            d = page.get_text("dict")
            for block_index, block in enumerate(d.get("blocks", [])):
                for line_index, line in enumerate(block.get("lines", [])):
                    text = "".join(span.get("text", "") for span in line.get("spans", []))
                    if not text:
                        continue
                    bbox_tuple = line.get("bbox", (0.0, 0.0, 0.0, 0.0))
                    all_lines.append(
                        _PdfLine(
                            page_number=page_number,
                            block_index=block_index,
                            line_index=line_index,
                            text=text,
                            bbox=(
                                float(bbox_tuple[0]),
                                float(bbox_tuple[1]),
                                float(bbox_tuple[2]),
                                float(bbox_tuple[3]),
                            ),
                        )
                    )

    # Heuristic table-grid detection: a table is a cluster of lines on
    # a single page where 2+ rows share the same page and have
    # non-overlapping x-bands and the line count suggests a multi-row
    # structure (≥ 2 rows with ≥ 2 cells each).
    tables: list[_PdfTableGrid] = []
    by_page: dict[int, list[_PdfLine]] = {}
    for line in all_lines:
        by_page.setdefault(line.page_number, []).append(line)
    for page_number, page_lines in by_page.items():
        rows = _cluster_lines_into_rows(tuple(page_lines))
        # Filter to "table-like" clusters: ≥ 2 rows with ≥ 2 lines each
        # and a y-spacing pattern.
        table_rows: list[tuple[_PdfLine, ...]] = []
        for row in rows:
            if len(row) >= 2:
                table_rows.append(row)
        if len(table_rows) >= 2:
            tables.append(
                _PdfTableGrid(page_number=page_number, rows=tuple(table_rows), unit_row_idx=None)
            )

    return _PdfObservation(
        all_lines=tuple(all_lines),
        tables=tuple(tables),
        section_scopes={},
    )


# ── Section-scope resolution ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _SectionScope:
    section_key: str
    heading_text: str


def _build_section_scopes(
    *,
    localized_sections: tuple[Any, ...],
) -> tuple[_SectionScope, ...]:
    """Build (section_key, localized_heading_text) tuples in document order."""

    return tuple(
        _SectionScope(section_key=section.section_key, heading_text=section.title)
        for section in localized_sections
    )


def _resolve_docx_section_scopes(
    *,
    observation: _DocxObservation,
    section_scopes: tuple[_SectionScope, ...],
) -> dict[str, tuple[int, int]]:
    """Map each section_key to (start_block_idx, end_block_idx) in DOCX order.

    A section's heading paragraph MUST match the localized section
    title exactly (after whitespace folding). If a section's heading
    cannot be found, the section is omitted from the scope map (the
    caller MUST treat the field as MISSING_FIELD_BINDING).
    """

    heading_to_key: dict[str, str] = {
        _fold_whitespace(s.heading_text): s.section_key for s in section_scopes
    }
    used: set[str] = set()
    resolved: dict[str, tuple[int, int]] = {}
    blocks = observation.body_blocks
    # Find the first block of each section (by heading match).
    starts: list[tuple[int, str]] = []  # (block_idx, section_key)
    for idx, block in enumerate(blocks):
        if block.kind == "paragraph" and block.heading_level == 1 and block.heading_text:
            folded = _fold_whitespace(block.heading_text)
            if folded in heading_to_key:
                section_key = heading_to_key[folded]
                if section_key not in used:
                    starts.append((idx, section_key))
                    used.add(section_key)
    for i, (start_idx, section_key) in enumerate(starts):
        end_idx = starts[i + 1][0] if i + 1 < len(starts) else len(blocks)
        resolved[section_key] = (start_idx, end_idx)
    return resolved


def _resolve_pdf_section_scopes(
    *,
    observation: _PdfObservation,
    section_scopes: tuple[_SectionScope, ...],
) -> dict[str, tuple[int, int]]:
    """Map each section_key to (start_line_idx, end_line_idx) in PDF order.

    Uses the y-coordinate of the heading line: a heading is a line
    whose text matches the localized section title (whitespace-folded)
    and whose y-coordinate is above a small threshold (i.e. it is a
    section divider, not a body line).
    """

    heading_to_key: dict[str, str] = {
        _fold_whitespace(s.heading_text): s.section_key for s in section_scopes
    }
    used: set[str] = set()
    starts: list[tuple[int, str]] = []
    for idx, line in enumerate(observation.all_lines):
        folded = _fold_whitespace(line.text)
        if folded in heading_to_key:
            section_key = heading_to_key[folded]
            if section_key not in used:
                starts.append((idx, section_key))
                used.add(section_key)
    resolved: dict[str, tuple[int, int]] = {}
    for i, (start_idx, section_key) in enumerate(starts):
        end_idx = starts[i + 1][0] if i + 1 < len(starts) else len(observation.all_lines)
        resolved[section_key] = (start_idx, end_idx)
    return resolved


# ── Field-level binding (structured) ──────────────────────────────────────


def _split_metric_paragraph(text: str) -> tuple[str, str, str] | None:
    """Parse a renderer-emitted metric line.

    The real DocxRenderer / PdfRenderer emits metrics as
    ``"{label}: {display_value} {display_unit}"`` (whitespace-folded).
    Returns (label, value, unit) or None if the line does not match
    the expected pattern.
    """

    folded = _fold_whitespace(text)
    if ":" not in folded:
        return None
    label_part, rest_part = folded.split(":", 1)
    label = label_part.strip()
    rest = rest_part.strip()
    if not label or not rest:
        return None
    # The value and unit are whitespace-separated tokens at the end.
    # The value can contain digits + . + , and an optional sign; the
    # unit is the last token.
    tokens = rest.split(" ")
    if len(tokens) < 1:
        return None
    unit = tokens[-1]
    value = " ".join(tokens[:-1]).strip()
    if not value:
        return None
    return (label, value, unit)


def _split_number_paragraph(text: str) -> tuple[str, str] | None:
    """Parse a renderer-emitted number line.

    The real renderer emits a number line as
    ``"{display_value} {display_unit}"`` (whitespace-folded). Returns
    (value, unit) or None if the line does not match.
    """

    folded = _fold_whitespace(text)
    tokens = folded.split(" ")
    if len(tokens) < 2:
        return None
    unit = tokens[-1]
    value = " ".join(tokens[:-1]).strip()
    if not value:
        return None
    return (value, unit)


def _find_metric_binding(
    *,
    docx_observation: _DocxObservation | None,
    pdf_observation: _PdfObservation | None,
    section_key: str,
    section_scopes: Mapping[str, tuple[int, int]],
    expected_label: str,
    expected_value: str,
    expected_unit: str,
) -> tuple[_ObservedNumericField, str | None] | tuple[None, str]:
    """Find the unique paragraph in the target section that binds the metric.

    Returns (observation, None) on success.
    Returns (None, failure_code) on MISSING/AMBIGUOUS binding.
    failure_code is one of:
        "MISSING_FIELD_BINDING" — no candidate paragraph found
        "AMBIGUOUS_FIELD_BINDING" — more than one candidate
    """

    if docx_observation is not None:
        if section_key not in section_scopes:
            return (None, "MISSING_SECTION")
        start, end = section_scopes[section_key]
        expected_label_folded = _fold_whitespace(expected_label)
        candidates: list[_ObservedNumericField] = []
        for idx in range(start, end):
            block = docx_observation.body_blocks[idx]
            if block.kind != "paragraph":
                continue
            # Heading paragraphs are skipped.
            if block.heading_level is not None:
                continue
            parsed = _split_metric_paragraph(block.text)
            if parsed is None:
                continue
            label, value, unit = parsed
            if _fold_whitespace(label) != expected_label_folded:
                continue
            candidates.append(
                _ObservedNumericField(
                    field_path="",  # populated by caller
                    section_key=section_key,
                    binding_kind=_BINDING_KIND_METRIC,
                    display_value=value,
                    display_unit=unit,
                    row_index=None,
                    column_index=None,
                )
            )
        if len(candidates) == 0:
            return (None, "MISSING_FIELD_BINDING")
        if len(candidates) > 1:
            return (None, "AMBIGUOUS_FIELD_BINDING")
        return (candidates[0], None)

    if pdf_observation is not None:
        if section_key not in section_scopes:
            return (None, "MISSING_SECTION")
        start, end = section_scopes[section_key]
        expected_label_folded = _fold_whitespace(expected_label)
        candidates = []
        for idx in range(start, end):
            line = pdf_observation.all_lines[idx]
            parsed = _split_metric_paragraph(line.text)
            if parsed is None:
                continue
            label, value, unit = parsed
            if _fold_whitespace(label) != expected_label_folded:
                continue
            candidates.append(
                _ObservedNumericField(
                    field_path="",
                    section_key=section_key,
                    binding_kind=_BINDING_KIND_METRIC,
                    display_value=value,
                    display_unit=unit,
                    row_index=None,
                    column_index=None,
                    page_number=line.page_number,
                )
            )
        if len(candidates) == 0:
            return (None, "MISSING_FIELD_BINDING")
        if len(candidates) > 1:
            return (None, "AMBIGUOUS_FIELD_BINDING")
        return (candidates[0], None)

    return (None, "MISSING_SECTION")


def _find_number_binding(
    *,
    docx_observation: _DocxObservation | None,
    pdf_observation: _PdfObservation | None,
    section_key: str,
    section_scopes: Mapping[str, tuple[int, int]],
    expected_value: str,
    expected_unit: str,
) -> tuple[_ObservedNumericField, str | None] | tuple[None, str]:
    """Find the value+unit paragraph in the target section.

    Number binding is: the unique paragraph (or line) in the section
    that matches the (value, unit) pair exactly (whitespace-folded).
    """

    if docx_observation is not None:
        if section_key not in section_scopes:
            return (None, "MISSING_SECTION")
        start, end = section_scopes[section_key]
        expected_v_folded = _fold_whitespace(expected_value)
        expected_u_folded = _fold_whitespace(expected_unit)
        candidates: list[_ObservedNumericField] = []
        for idx in range(start, end):
            block = docx_observation.body_blocks[idx]
            if block.kind != "paragraph":
                continue
            if block.heading_level is not None:
                continue
            parsed = _split_number_paragraph(block.text)
            if parsed is None:
                continue
            value, unit = parsed
            if (
                _fold_whitespace(value) == expected_v_folded
                and _fold_whitespace(unit) == expected_u_folded
            ):
                candidates.append(
                    _ObservedNumericField(
                        field_path="",
                        section_key=section_key,
                        binding_kind=_BINDING_KIND_NUMBER,
                        display_value=value,
                        display_unit=unit,
                        row_index=None,
                        column_index=None,
                    )
                )
        if len(candidates) == 0:
            return (None, "MISSING_FIELD_BINDING")
        if len(candidates) > 1:
            return (None, "AMBIGUOUS_FIELD_BINDING")
        return (candidates[0], None)

    if pdf_observation is not None:
        if section_key not in section_scopes:
            return (None, "MISSING_SECTION")
        start, end = section_scopes[section_key]
        expected_v_folded = _fold_whitespace(expected_value)
        expected_u_folded = _fold_whitespace(expected_unit)
        candidates = []
        for idx in range(start, end):
            line = pdf_observation.all_lines[idx]
            parsed = _split_number_paragraph(line.text)
            if parsed is None:
                continue
            value, unit = parsed
            if (
                _fold_whitespace(value) == expected_v_folded
                and _fold_whitespace(unit) == expected_u_folded
            ):
                candidates.append(
                    _ObservedNumericField(
                        field_path="",
                        section_key=section_key,
                        binding_kind=_BINDING_KIND_NUMBER,
                        display_value=value,
                        display_unit=unit,
                        row_index=None,
                        column_index=None,
                        page_number=line.page_number,
                    )
                )
        if len(candidates) == 0:
            return (None, "MISSING_FIELD_BINDING")
        if len(candidates) > 1:
            return (None, "AMBIGUOUS_FIELD_BINDING")
        return (candidates[0], None)

    return (None, "MISSING_SECTION")


def _find_table_cell_binding(
    *,
    docx_observation: _DocxObservation | None,
    pdf_observation: _PdfObservation | None,
    section_key: str,
    section_scopes: Mapping[str, tuple[int, int]],
    table_section_key: str,
    row_index: int,
    column_index: int,
) -> tuple[_ObservedNumericField, str | None] | tuple[None, str]:
    """Find the (row, column) cell in the table located in the target section.

    For DOCX, the section's first table is used. For PDF, the first
    table grid on the section's page is used. The unit comes from the
    same table's unit row at the same column.

    ``row_index`` is the 0-based DATA row index (header and unit rows
    are excluded). ``column_index`` is the 0-based cell column.
    """

    if docx_observation is not None:
        if section_key not in section_scopes:
            return (None, "MISSING_SECTION")
        if section_key != table_section_key:
            return (None, "TABLE_COLUMN_MISMATCH")
        start, end = section_scopes[section_key]
        # Find the first table in the section.
        table_block: _DocxBlock | None = None
        for idx in range(start, end):
            block = docx_observation.body_blocks[idx]
            if block.kind == "table":
                table_block = block
                break
        if table_block is None or table_block.cells is None:
            return (None, "MISSING_FIELD_BINDING")
        cells = table_block.cells
        # The first row is the header. The second row, if all cells
        # are wrapped in parens (e.g. ``(kW(e))``) or match unit
        # patterns, is the unit row. Otherwise no unit row.
        unit_row_idx: int | None = None
        if len(cells) >= 2 and all(_is_unit_token(c) for c in cells[1]):
            unit_row_idx = 1
        data_row_idx = row_index + (2 if unit_row_idx is not None else 1)
        if data_row_idx < 0 or data_row_idx >= len(cells):
            return (None, "TABLE_ROW_MISMATCH")
        if column_index < 0 or column_index >= len(cells[data_row_idx]):
            return (None, "TABLE_COLUMN_MISMATCH")
        cell_value = cells[data_row_idx][column_index]
        unit_value = cells[unit_row_idx][column_index] if unit_row_idx is not None else ""
        # Strip parens for unit comparison (the renderer emits ``(kW(e))``)
        if unit_value.startswith("(") and unit_value.endswith(")"):
            unit_value = unit_value[1:-1]
        return (
            _ObservedNumericField(
                field_path="",
                section_key=section_key,
                binding_kind=_BINDING_KIND_TABLE_CELL,
                display_value=cell_value,
                display_unit=unit_value,
                row_index=row_index,
                column_index=column_index,
            ),
            None,
        )

    if pdf_observation is not None:
        if section_key not in section_scopes:
            return (None, "MISSING_SECTION")
        if section_key != table_section_key:
            return (None, "TABLE_COLUMN_MISMATCH")
        start, end = section_scopes[section_key]
        # Find the first table on the section's page.
        # ``start``/``end`` are indices into ``pdf_observation.all_lines``.
        section_lines = pdf_observation.all_lines[start:end]
        if not section_lines:
            return (None, "MISSING_FIELD_BINDING")
        section_page_numbers = {line.page_number for line in section_lines}
        candidate_table: _PdfTableGrid | None = None
        for table in pdf_observation.tables:
            if table.page_number in section_page_numbers:
                candidate_table = table
                break
        if candidate_table is None:
            return (None, "MISSING_FIELD_BINDING")
        rows = candidate_table.rows
        # The first row is the header. Identify the unit row by checking
        # if the second row's leftmost cell matches a unit-code pattern.
        pdf_unit_row_idx: int | None = None
        if len(rows) >= 2 and all(_is_unit_token(line.text) for line in rows[1]):
            pdf_unit_row_idx = 1
        data_row_idx = row_index + (2 if pdf_unit_row_idx is not None else 1)
        if data_row_idx < 0 or data_row_idx >= len(rows):
            return (None, "TABLE_ROW_MISMATCH")
        row = rows[data_row_idx]
        if column_index < 0 or column_index >= len(row):
            return (None, "TABLE_COLUMN_MISMATCH")
        cell_value = row[column_index].text
        if pdf_unit_row_idx is not None:
            unit_value = rows[pdf_unit_row_idx][column_index].text
        else:
            unit_value = ""
        return (
            _ObservedNumericField(
                field_path="",
                section_key=section_key,
                binding_kind=_BINDING_KIND_TABLE_CELL,
                display_value=cell_value,
                display_unit=unit_value,
                row_index=row_index,
                column_index=column_index,
                page_number=candidate_table.page_number,
            ),
            None,
        )

    return (None, "MISSING_SECTION")


def _is_unit_token(text: str) -> bool:
    """Heuristic: does this text look like a unit label?

    Used to identify the unit row in a DOCX/PDF table. Recognizes
    tokens like ``(kW(e))``, ``kW(r)``, ``kg``, ``元``, ``CNY``.
    """

    folded = _fold_whitespace(text)
    if folded.startswith("(") and folded.endswith(")"):
        folded = folded[1:-1]
    if not folded:
        return False
    # Common unit patterns: contains parens or is short alphanumeric
    # with non-ASCII allowed.
    if "(" in folded or ")" in folded:
        return True
    if any(ch.isdigit() for ch in folded):
        return False
    return len(folded) <= 12


def _compare_field(
    *,
    observed: _ObservedNumericField,
    expected_value: str,
    expected_unit: str,
) -> str | None:
    """Compare an observed field against the localized expected.

    Returns a failure code (one of "VALUE_MISMATCH", "UNIT_MISSING",
    "UNIT_MISMATCH") or None on success. Whitespace folding is the
    ONLY allowed transformation; no fuzzy numeric tolerance.
    """

    # Unit presence: if the canonical has a unit, the observation
    # MUST also have a unit. If the canonical has no unit, the
    # observation is allowed to have no unit too.
    expected_u_folded = _fold_whitespace(expected_unit)
    observed_u_folded = _fold_whitespace(observed.display_unit)
    if expected_u_folded:
        if not observed_u_folded:
            return "UNIT_MISSING"
        if observed_u_folded != expected_u_folded:
            return "UNIT_MISMATCH"
    # Value comparison (whitespace-folded).
    if not _strings_equal_folded(observed.display_value, expected_value):
        return "VALUE_MISMATCH"
    return None


def _extract_text(fmt: ExportFormat, data: bytes) -> str:  # noqa: ARG001
    """Retained for backward compatibility with P1-1/P1-2 contracts.

    The P1-3 round replaces the global-text verifier with a
    structured observation + binding layer. This function is kept
    for any test/utility that still needs a flattened text view
    (e.g. heading-presence checks, or legacy helpers). Numeric
    semantic verification MUST go through ``_semantic_checks`` and
    the structured binding functions, not through this helper.
    """

    if fmt is ExportFormat.DOCX:
        document = Document(io.BytesIO(data))
        parts: list[str] = [paragraph.text for paragraph in document.paragraphs if paragraph.text]
        for table in document.tables:
            for row in table.rows:
                parts.extend(cell.text for cell in row.cells if cell.text)
        return "\n".join(parts)
    if fmt is ExportFormat.PDF:
        with fitz.open(stream=data, filetype="pdf") as document:
            return "\n".join(page.get_text("text") for page in document)
    _fail("UNSUPPORTED_FORMAT", f"Unsupported report format: {fmt.value}")
    raise AssertionError("unreachable")


def _canonical_metrics(
    model: CanonicalReportRenderModel,
) -> tuple[CanonicalRenderMetric | CanonicalRenderTableCell, ...]:
    values: list[CanonicalRenderMetric | CanonicalRenderTableCell] = []
    for section in model.sections:
        if section.number is not None:
            values.append(section.number)
        values.extend(section.metrics)
        if section.table is not None:
            for row in section.table.rows:
                values.extend(
                    cell
                    for cell in row
                    if isinstance(cell.raw_value, int) or hasattr(cell.raw_value, "as_tuple")
                )
    return tuple(values)


def _managed_paths() -> tuple[Path, ...]:
    paths: list[Path] = [Path("pilot-run.json"), Path("pilot-summary.json")]
    for locale, fmt in _RENDER_MATRIX:
        base = Path("artifacts") / locale.value / fmt.value
        paths.extend(
            (
                base / f"report.{fmt.value}",
                base / "artifact-metadata.json",
                base / "semantic-checks.json",
            )
        )
    return tuple(paths)


def _verify_artifact_binding(
    *,
    artifact: Any,
    report_id: str,
    revision: Any,
    locale: ReportLocale,
    fmt: ExportFormat,
    template: Any,
) -> None:
    if artifact.status is not ArtifactStatus.COMPLETED:
        _fail(
            "ARTIFACT_NOT_COMPLETED",
            "Rendered artifact is not completed.",
            artifact_id=artifact.id,
            status=artifact.status.value,
        )
    if (
        artifact.report_id != report_id
        or artifact.report_revision_id != revision.id
        or artifact.revision_number != revision.revision_number
    ):
        _fail(
            "REPORT_REVISION_MISMATCH",
            "Artifact does not bind to the one pilot report revision.",
            artifact_id=artifact.id,
        )
    if artifact.format is not fmt:
        _fail("ARTIFACT_METADATA_MISMATCH", "Artifact format mismatch.")
    if artifact.locale is not locale:
        _fail("LOCALE_BINDING_MISMATCH", "Artifact locale mismatch.")
    if artifact.template_locale is not locale:
        _fail("TEMPLATE_LOCALE_MISMATCH", "Template locale mismatch.")
    if artifact.source_content_hash != revision.content_hash:
        _fail("SOURCE_CONTENT_HASH_MISMATCH", "Artifact source hash mismatch.")
    manifest = artifact.render_manifest_json
    if manifest.get("render_mode") != "draft":
        _fail("UNSUPPORTED_RENDER_MODE", "Pilot artifact is not a draft render.")
    if manifest.get("template_content_hash") != template.template_content_hash:
        _fail("TEMPLATE_PROVENANCE_MISMATCH", "Template content hash mismatch.")
    catalog = get_catalog(locale)
    catalog_hash = compute_catalog_content_hash(locale)
    if not artifact.translation_catalog_version:
        _fail(
            "TRANSLATION_CATALOG_IDENTITY_MISSING",
            "Translation catalog version is empty.",
        )
    if (
        artifact.translation_catalog_version != catalog.version
        or artifact.translation_catalog_content_hash != catalog_hash
    ):
        _fail(
            "TRANSLATION_CATALOG_IDENTITY_MISMATCH",
            "Translation catalog identity mismatch.",
        )
    if not _is_sha256(artifact.localized_template_content_hash):
        _fail(
            "LOCALIZED_TEMPLATE_HASH_MISSING",
            "Localized template content hash is missing or malformed.",
        )


def _semantic_checks(
    *,
    canonical_model: CanonicalReportRenderModel,
    template: Any,
    locale: ReportLocale,
    fmt: ExportFormat,
    artifact_bytes: bytes,
) -> dict[str, Any]:
    """Run structured, field-bound semantic verification on a downloaded artifact.

    The P1-3 fix replaces the previous global substring search
    (metric.display_value in extracted_text) with a structured
    observation + binding layer. The function:

      1. Localizes the canonical model via ``localize_render_model``.
      2. Observes the downloaded artifact (DOCX/PDF bytes) into
         structured blocks/lines + section scopes.
      3. For each canonical numeric field (metric, number, table
         cell), finds the unique structural binding at the
         section/field/row/column position.
      4. Compares the observed value/unit against the localized
         expected value/unit (whitespace-folded only).
      5. Records any mismatch in ``numeric_mismatches`` (value/unit
         error), ``missing_units`` (unit absent/mismatched), and
         sets ``semantic_result`` to ``FAIL`` on any failure.

    The function NEVER falls back to global substring search. The
    observed value/unit come from the downloaded artifact bytes,
    not from the localized model.
    """

    template_manifest_json = template.manifest_json if hasattr(template, "manifest_json") else None

    localized = localize_render_model(
        canonical_model,
        locale=locale,
        template_manifest_json=template_manifest_json,
        format=fmt.value,
    )

    # Heading-presence check (auxiliary diagnostic, NOT a numeric
    # semantic check). The P1-3 contract explicitly allows keeping
    # text-based heading presence as auxiliary diagnostic.
    flattened_text = _extract_text(fmt, artifact_bytes)
    expected_headings = [section.title for section in localized.sections]
    missing_sections = [heading for heading in expected_headings if heading not in flattened_text]

    # Section scopes from the localized model.
    section_scopes_spec = _build_section_scopes(localized_sections=localized.sections)

    # Structured observation.
    docx_observation: _DocxObservation | None = None
    pdf_observation: _PdfObservation | None = None
    if fmt is ExportFormat.DOCX:
        docx_observation = _observe_docx(artifact_bytes)
        resolved_scopes = _resolve_docx_section_scopes(
            observation=docx_observation, section_scopes=section_scopes_spec
        )
    elif fmt is ExportFormat.PDF:
        pdf_observation = _observe_pdf(artifact_bytes)
        resolved_scopes = _resolve_pdf_section_scopes(
            observation=pdf_observation, section_scopes=section_scopes_spec
        )
    else:
        _fail("UNSUPPORTED_FORMAT", f"Unsupported report format: {fmt.value}")
        raise AssertionError("unreachable")

    canonical_fields: list[dict[str, str]] = []
    observed_fields: list[dict[str, Any]] = []
    missing_units: list[str] = []
    numeric_mismatches: list[str] = []

    def _inspect_metric(
        metric: Any,
        *,
        section_key: str,
        binding_label: str,
    ) -> None:
        canonical_fields.append(
            {
                "field_path": metric.canonical.field_path,
                "raw_value": str(metric.canonical.raw_value),
                "unit_code": metric.canonical.unit_code,
            }
        )
        # Try to bind the metric in the section scope.
        result = _find_metric_binding(
            docx_observation=docx_observation,
            pdf_observation=pdf_observation,
            section_key=section_key,
            section_scopes=resolved_scopes,
            expected_label=binding_label,
            expected_value=metric.display_value,
            expected_unit=metric.display_unit,
        )
        if result[1] is not None:
            # Binding failure: report the failure code with field_path.
            # We still record the observed record (with the expected
            # values) so audit consumers can see what we tried to bind.
            observed_fields.append(
                {
                    "field_path": metric.canonical.field_path,
                    "section_key": section_key,
                    "binding_kind": _BINDING_KIND_METRIC,
                    "display_value": metric.display_value,
                    "display_unit": metric.display_unit,
                    "row_index": None,
                    "column_index": None,
                    "page_number": None,
                    "binding_status": result[1],
                }
            )
            if result[1] in ("UNIT_MISSING", "UNIT_MISMATCH"):
                missing_units.append(metric.canonical.field_path)
            else:
                numeric_mismatches.append(metric.canonical.field_path)
            return
        observed = result[0]
        if observed is None:  # pragma: no cover
            numeric_mismatches.append(metric.canonical.field_path)
            return
        observed_fields.append(
            {
                "field_path": metric.canonical.field_path,
                "section_key": section_key,
                "binding_kind": _BINDING_KIND_METRIC,
                "display_value": observed.display_value,
                "display_unit": observed.display_unit,
                "row_index": observed.row_index,
                "column_index": observed.column_index,
                "page_number": observed.page_number,
                "binding_status": "BOUND",
            }
        )
        cmp = _compare_field(
            observed=observed,
            expected_value=metric.display_value,
            expected_unit=metric.display_unit,
        )
        if cmp == "UNIT_MISSING" or cmp == "UNIT_MISMATCH":
            missing_units.append(metric.canonical.field_path)
        elif cmp is not None:
            numeric_mismatches.append(metric.canonical.field_path)

    def _inspect_number(
        number_metric: Any,
        *,
        section_key: str,
    ) -> None:
        canonical_fields.append(
            {
                "field_path": number_metric.canonical.field_path,
                "raw_value": str(number_metric.canonical.raw_value),
                "unit_code": number_metric.canonical.unit_code,
            }
        )
        result = _find_number_binding(
            docx_observation=docx_observation,
            pdf_observation=pdf_observation,
            section_key=section_key,
            section_scopes=resolved_scopes,
            expected_value=number_metric.display_value,
            expected_unit=number_metric.display_unit,
        )
        if result[1] is not None:
            observed_fields.append(
                {
                    "field_path": number_metric.canonical.field_path,
                    "section_key": section_key,
                    "binding_kind": _BINDING_KIND_NUMBER,
                    "display_value": number_metric.display_value,
                    "display_unit": number_metric.display_unit,
                    "row_index": None,
                    "column_index": None,
                    "page_number": None,
                    "binding_status": result[1],
                }
            )
            if result[1] in ("UNIT_MISSING", "UNIT_MISMATCH"):
                missing_units.append(number_metric.canonical.field_path)
            else:
                numeric_mismatches.append(number_metric.canonical.field_path)
            return
        observed = result[0]
        if observed is None:  # pragma: no cover
            numeric_mismatches.append(number_metric.canonical.field_path)
            return
        observed_fields.append(
            {
                "field_path": number_metric.canonical.field_path,
                "section_key": section_key,
                "binding_kind": _BINDING_KIND_NUMBER,
                "display_value": observed.display_value,
                "display_unit": observed.display_unit,
                "row_index": observed.row_index,
                "column_index": observed.column_index,
                "page_number": observed.page_number,
                "binding_status": "BOUND",
            }
        )
        cmp = _compare_field(
            observed=observed,
            expected_value=number_metric.display_value,
            expected_unit=number_metric.display_unit,
        )
        if cmp == "UNIT_MISSING" or cmp == "UNIT_MISMATCH":
            missing_units.append(number_metric.canonical.field_path)
        elif cmp is not None:
            numeric_mismatches.append(number_metric.canonical.field_path)

    def _inspect_table_cell(
        cell: CanonicalRenderTableCell,
        *,
        section_key: str,
        table_section_key: str,
        row_index: int,
        column_index: int,
    ) -> None:
        canonical_fields.append(
            {
                "field_path": cell.field_path,
                "raw_value": str(cell.raw_value),
                "unit_code": cell.unit_code,
            }
        )
        result = _find_table_cell_binding(
            docx_observation=docx_observation,
            pdf_observation=pdf_observation,
            section_key=section_key,
            section_scopes=resolved_scopes,
            table_section_key=table_section_key,
            row_index=row_index,
            column_index=column_index,
        )
        if result[1] is not None:
            observed_fields.append(
                {
                    "field_path": cell.field_path,
                    "section_key": section_key,
                    "binding_kind": _BINDING_KIND_TABLE_CELL,
                    "display_value": str(cell.raw_value),
                    "display_unit": cell.unit_code,
                    "row_index": row_index,
                    "column_index": column_index,
                    "page_number": None,
                    "binding_status": result[1],
                }
            )
            if result[1] in ("UNIT_MISSING", "UNIT_MISMATCH"):
                missing_units.append(cell.field_path)
            else:
                numeric_mismatches.append(cell.field_path)
            return
        observed = result[0]
        if observed is None:  # pragma: no cover
            numeric_mismatches.append(cell.field_path)
            return
        # Format the expected display value from the canonical.
        from cold_storage.modules.reports.localization.formatter import (
            format_decimal,
            format_unit_label,
        )

        if isinstance(cell.raw_value, (int, Decimal)):
            expected_dv = format_decimal(cell.raw_value, locale)
        else:
            expected_dv = str(cell.raw_value) if cell.raw_value is not None else "\u2014"
        expected_du = format_unit_label(cell.unit_code, locale) if cell.unit_code else ""
        observed_fields.append(
            {
                "field_path": cell.field_path,
                "section_key": section_key,
                "binding_kind": _BINDING_KIND_TABLE_CELL,
                "display_value": observed.display_value,
                "display_unit": observed.display_unit,
                "row_index": observed.row_index,
                "column_index": observed.column_index,
                "page_number": observed.page_number,
                "binding_status": "BOUND",
            }
        )
        cmp = _compare_field(
            observed=observed,
            expected_value=expected_dv,
            expected_unit=expected_du,
        )
        if cmp == "UNIT_MISSING" or cmp == "UNIT_MISMATCH":
            missing_units.append(cell.field_path)
        elif cmp is not None:
            numeric_mismatches.append(cell.field_path)

    for section in localized.sections:
        for metric in section.metrics:
            _inspect_metric(metric, section_key=section.section_key, binding_label=metric.label)
        if section.number is not None:
            _inspect_number(section.number, section_key=section.section_key)
        if section.table is not None:
            for row_idx, row in enumerate(section.table.rows):
                for col_idx, cell in enumerate(row):
                    raw = cell.canonical.raw_value
                    if isinstance(raw, (int, Decimal)) or hasattr(raw, "as_tuple"):
                        _inspect_table_cell(
                            cell.canonical,
                            section_key=section.section_key,
                            table_section_key=section.section_key,
                            row_index=row_idx,
                            column_index=col_idx,
                        )

    result = (
        "PASS" if not missing_sections and not missing_units and not numeric_mismatches else "FAIL"
    )
    return {
        "schema_version": PILOT_RESULT_SCHEMA_VERSION,
        "locale": locale.value,
        "format": fmt.value,
        "canonical_section_keys": [section.section_key for section in canonical_model.sections],
        "required_heading_keys": [
            f"section.{section.section_key}" for section in canonical_model.sections
        ],
        "observed_localized_headings": [
            heading for heading in expected_headings if heading in flattened_text
        ],
        "canonical_numeric_fields": canonical_fields,
        "observed_numeric_fields": observed_fields,
        "missing_sections": missing_sections,
        "missing_units": sorted(set(missing_units)),
        "numeric_mismatches": sorted(set(numeric_mismatches)),
        "semantic_result": result,
    }


def verify_multilingual_report_pilot(
    *,
    report_service: Any,
    render_service: Any,
    template_repository: Any,
    project_id: str,
    project_version_id: str,
    source_commit_sha: str,
    source_manifest_sha: str,
    output_root: Path,
    repeat_index: int,
    run_identity: Mapping[str, Any],
    download_artifact: DownloadArtifact,
    actor: str = "task011-pilot",
) -> dict[str, Any]:
    """Run and verify the frozen four-render pilot from one report revision."""
    if not output_root.is_absolute():
        _fail("UNSAFE_OUTPUT_ROOT", "Pilot output root must be absolute.")
    if repeat_index not in (1, 2):
        _fail("INFRASTRUCTURE_ERROR", "repeat_index must be 1 or 2.")
    if not _is_sha256(source_manifest_sha):
        _fail("SOURCE_BINDING_MISMATCH", "Manifest SHA-256 is malformed.")
    assert_no_managed_artifacts(root=output_root, managed_paths=_managed_paths())

    report = report_service.create_report(
        project_id=project_id,
        project_version_id=project_version_id,
        report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
        actor=actor,
    )
    revision = report_service.generate_revision(report.id, actor)
    if revision.report_id != report.id:
        _fail("REPORT_REVISION_MISMATCH", "Generated revision report ID mismatch.")

    canonical_model = build_canonical_render_model(
        content=revision.content_json,
        report_id=report.id,
        revision_number=revision.revision_number,
        content_hash=revision.content_hash,
        generated_by=revision.generated_by,
        generated_at=revision.generated_at.isoformat(),
        template_code="cold_storage_concept_design",
        template_version="1.0.0",
        approval_snapshot=None,
    )
    section_keys = [section.section_key for section in canonical_model.sections]
    metrics = _canonical_metrics(canonical_model)

    started_at = datetime.now(UTC).isoformat()
    pilot_run = {
        "schema_version": PILOT_RESULT_SCHEMA_VERSION,
        "pilot_check_id": PILOT_CHECK_ID,
        "source_commit_sha": source_commit_sha,
        "source_manifest_sha": source_manifest_sha,
        **dict(run_identity),
        "repeat_index": repeat_index,
        "project_id": project_id,
        "project_version_id": project_version_id,
        "report_id": report.id,
        "report_revision_id": revision.id,
        "revision_number": revision.revision_number,
        "report_revision_content_hash": revision.content_hash,
        "report_type": report.report_type.value,
        "report_schema_version": revision.schema_version,
        "started_at": started_at,
    }
    atomic_write_json(path=output_root / "pilot-run.json", data=pilot_run)

    artifact_rows: list[dict[str, Any]] = []
    semantic_results: list[str] = []
    for locale, fmt in _RENDER_MATRIX:
        artifact = render_service.render(
            report_id=report.id,
            revision_number=revision.revision_number,
            format=fmt.value,
            template_version=None,
            mode="draft",
            actor=actor,
            locale=locale,
        )
        template = template_repository.get_template(artifact.template_id)
        if template is None:
            _fail(
                "TEMPLATE_PROVENANCE_MISMATCH",
                "Persisted template for artifact is missing.",
                template_id=artifact.template_id,
            )
        _verify_artifact_binding(
            artifact=artifact,
            report_id=report.id,
            revision=revision,
            locale=locale,
            fmt=fmt,
            template=template,
        )
        downloaded, download_headers = download_artifact(report.id, artifact.id, actor)
        downloaded_hash = _sha256(downloaded)
        if downloaded_hash != artifact.file_sha256 or len(downloaded) != artifact.file_size_bytes:
            _fail(
                "DOWNLOAD_INTEGRITY_MISMATCH",
                "Downloaded artifact bytes do not match persisted metadata.",
                artifact_id=artifact.id,
            )
        expected_headers = {
            "X-Content-SHA256": downloaded_hash,
            "X-Source-Content-Hash": revision.content_hash,
            "X-Report-Locale": locale.value,
            "X-Template-Locale": locale.value,
            "X-Translation-Catalog-Version": artifact.translation_catalog_version,
            "X-Translation-Catalog-Content-Hash": artifact.translation_catalog_content_hash,
            "X-Localized-Template-Content-Hash": artifact.localized_template_content_hash,
        }
        if any(download_headers.get(key) != value for key, value in expected_headers.items()):
            _fail(
                "DOWNLOAD_INTEGRITY_MISMATCH",
                "Download response header binding mismatch.",
                artifact_id=artifact.id,
            )

        checks = _semantic_checks(
            canonical_model=canonical_model,
            template=template,
            locale=locale,
            fmt=fmt,
            artifact_bytes=downloaded,
        )
        if checks["semantic_result"] != "PASS":
            _fail(
                "NUMERIC_SEMANTIC_MISMATCH",
                "Downloaded report failed section or numeric semantic verification.",
                locale=locale.value,
                format=fmt.value,
                checks=checks,
            )
        semantic_results.append(str(checks["semantic_result"]))

        artifact_dir = output_root / "artifacts" / locale.value / fmt.value
        metadata = {
            "schema_version": PILOT_RESULT_SCHEMA_VERSION,
            "artifact_id": artifact.id,
            "report_id": artifact.report_id,
            "report_revision_id": artifact.report_revision_id,
            "revision_number": artifact.revision_number,
            "format": artifact.format.value,
            "locale": artifact.locale.value,
            "template_locale": artifact.template_locale.value,
            "render_mode": artifact.render_manifest_json.get("render_mode"),
            "template_version": artifact.template_version,
            "template_content_hash": template.template_content_hash,
            "template_schema_version": template.schema_version,
            "source_content_hash": artifact.source_content_hash,
            "translation_catalog_version": artifact.translation_catalog_version,
            "translation_catalog_content_hash": artifact.translation_catalog_content_hash,
            "localized_template_content_hash": artifact.localized_template_content_hash,
            "artifact_status": artifact.status.value,
            "file_name": artifact.file_name,
            "file_size_bytes": artifact.file_size_bytes,
            "file_sha256": artifact.file_sha256,
            "download_headers": dict(download_headers),
            "integrity_result": "PASS",
        }
        atomic_write_bytes(path=artifact_dir / f"report.{fmt.value}", data=downloaded)
        atomic_write_json(path=artifact_dir / "artifact-metadata.json", data=metadata)
        atomic_write_json(path=artifact_dir / "semantic-checks.json", data=checks)
        artifact_rows.append(metadata)

    identities = {
        (
            item["report_id"],
            item["report_revision_id"],
            item["revision_number"],
            item["source_content_hash"],
        )
        for item in artifact_rows
    }
    if len(identities) != 1:
        _fail("REPORT_REVISION_MISMATCH", "Four renders do not share one revision.")
    if any(item["source_content_hash"] != revision.content_hash for item in artifact_rows):
        _fail("SOURCE_BINDING_MISMATCH", "Four renders do not share source content.")
    if not section_keys or not metrics:
        _fail(
            "REQUIRED_SECTION_MISSING",
            "Canonical report has no sections or numeric fields to verify.",
        )

    managed_hashes = {
        str(path.relative_to(output_root)): _sha256(path.read_bytes())
        for path in sorted(output_root.rglob("*"))
        if path.is_file() and path.name != "pilot-summary.json"
    }
    summary = {
        "schema_version": PILOT_RESULT_SCHEMA_VERSION,
        "pilot_check_id": PILOT_CHECK_ID,
        "source_commit_sha": source_commit_sha,
        "source_manifest_sha": source_manifest_sha,
        **dict(run_identity),
        "repeat_index": repeat_index,
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "render_matrix": [
            {"locale": locale.value, "format": fmt.value, "mode": "draft"}
            for locale, fmt in _RENDER_MATRIX
        ],
        "source_binding_result": "PASS",
        "artifact_integrity_result": "PASS",
        "semantic_result": (
            "PASS" if all(result == "PASS" for result in semantic_results) else "FAIL"
        ),
        "overall_result": "PASS",
        "managed_file_sha256": managed_hashes,
    }
    atomic_write_json(path=output_root / "pilot-summary.json", data=summary)
    return summary


__all__ = [
    "PILOT_CHECK_ID",
    "PILOT_RESULT_SCHEMA_VERSION",
    "PilotVerificationError",
    "verify_multilingual_report_pilot",
]
