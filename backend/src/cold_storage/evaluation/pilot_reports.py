"""Multilingual report pilot verifier for the frozen TASK-011 Slice 1 contract."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fitz
from docx import Document

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


def _extract_docx_text(data: bytes) -> str:
    document = Document(io.BytesIO(data))
    parts: list[str] = [paragraph.text for paragraph in document.paragraphs if paragraph.text]
    for table in document.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells if cell.text)
    return "\n".join(parts)


def _extract_pdf_text(data: bytes) -> str:
    with fitz.open(stream=data, filetype="pdf") as document:
        return "\n".join(page.get_text("text") for page in document)


def _extract_text(fmt: ExportFormat, data: bytes) -> str:
    if fmt is ExportFormat.DOCX:
        return _extract_docx_text(data)
    if fmt is ExportFormat.PDF:
        return _extract_pdf_text(data)
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
    extracted_text: str,
) -> dict[str, Any]:
    localized = localize_render_model(
        canonical_model,
        locale=locale,
        template_manifest_json=template.manifest_json,
        format=fmt.value,
    )
    expected_headings = [section.title for section in localized.sections]
    missing_sections = [heading for heading in expected_headings if heading not in extracted_text]

    canonical_fields: list[dict[str, str]] = []
    observed_fields: list[dict[str, str]] = []
    missing_units: list[str] = []
    numeric_mismatches: list[str] = []

    def inspect_metric(metric: Any) -> None:
        canonical_fields.append(
            {
                "field_path": metric.canonical.field_path,
                "raw_value": str(metric.canonical.raw_value),
                "unit_code": metric.canonical.unit_code,
            }
        )
        observed_fields.append(
            {
                "field_path": metric.canonical.field_path,
                "display_value": metric.display_value,
                "display_unit": metric.display_unit,
            }
        )
        if metric.display_value and metric.display_value not in extracted_text:
            numeric_mismatches.append(metric.canonical.field_path)
        if metric.display_unit and metric.display_unit not in extracted_text:
            missing_units.append(metric.canonical.field_path)

    for section in localized.sections:
        for metric in section.metrics:
            inspect_metric(metric)
        if section.number is not None:
            inspect_metric(section.number)
        if section.table is not None:
            for row in section.table.rows:
                for cell in row:
                    raw = cell.canonical.raw_value
                    if isinstance(raw, int) or hasattr(raw, "as_tuple"):
                        inspect_metric(cell)

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
            heading for heading in expected_headings if heading in extracted_text
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

        extracted_text = _extract_text(fmt, downloaded)
        checks = _semantic_checks(
            canonical_model=canonical_model,
            template=template,
            locale=locale,
            fmt=fmt,
            extracted_text=extracted_text,
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
