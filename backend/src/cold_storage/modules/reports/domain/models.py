"""Report domain models — pure data types, no framework or DB dependencies.

All models use frozen dataclasses.  Numeric values use ``Decimal`` for
deterministic arithmetic.  Float is only permitted at the JSON serialisation
boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from cold_storage.modules.reports.domain.enums import (
    ArtifactStatus,
    ExportFormat,
    QualitySeverity,
    ReportStatus,
    ReportType,
    ReviewAction,
    SourceType,
    TemplateStatus,
)


def _uuid() -> str:
    return str(uuid4())


# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApprovalSnapshot:
    """Immutable snapshot of approval state for render model and manifest.

    Carries the exact approval fields at the moment of render, ensuring
    consistency between the citations/approval section and the artifact
    manifest.
    """

    revision_id: str
    content_hash: str
    approved_by: str
    approved_at: str
    revision_number: int = 0

    @classmethod
    def from_report(cls, report: Report) -> ApprovalSnapshot | None:
        """Build an ApprovalSnapshot from a Report's approval fields.

        Returns None if the report has not been approved (any field missing).
        """
        if not (
            report.approved_revision_id
            and report.approved_content_hash
            and report.approved_by
            and report.approved_at
        ):
            return None
        return cls(
            revision_id=report.approved_revision_id or "",
            content_hash=report.approved_content_hash or "",
            approved_by=report.approved_by or "",
            approved_at=report.approved_at or "",
        )

    @classmethod
    def from_report_and_revision(
        cls, report: Report, revision: ReportRevision
    ) -> ApprovalSnapshot | None:
        """Build an ApprovalSnapshot from Report approval fields and a revision.

        Returns None if the report has not been approved (any field missing).
        Includes the revision_number from the revision object.
        """
        if not (
            report.approved_revision_id
            and report.approved_content_hash
            and report.approved_by
            and report.approved_at
        ):
            return None
        return cls(
            revision_id=report.approved_revision_id or "",
            content_hash=report.approved_content_hash or "",
            approved_by=report.approved_by or "",
            approved_at=report.approved_at or "",
            revision_number=revision.revision_number,
        )


# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QualityFinding:
    """A single machine-readable quality finding."""

    code: str
    severity: QualitySeverity
    section_key: str
    field_path: str
    message: str
    source_ids: list[str] = field(default_factory=list)
    remediation: str = ""


# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Report:
    """Top-level report entity."""

    id: str
    project_id: str
    project_version_id: str
    report_type: ReportType
    status: ReportStatus
    current_revision_number: int
    created_by: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: int = 1  # optimistic lock
    # P0-8: Formal approval binding fields
    approved_revision_id: str | None = None
    approved_content_hash: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None  # ISO 8601

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        project_version_id: str,
        report_type: ReportType,
        created_by: str,
    ) -> Report:
        now = datetime.now(UTC)
        return cls(
            id=_uuid(),
            project_id=project_id,
            project_version_id=project_version_id,
            report_type=report_type,
            status=ReportStatus.DRAFT,
            current_revision_number=0,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            version=1,
        )


# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportRevision:
    """Immutable report revision.  Once created, never mutated."""

    id: str
    report_id: str
    revision_number: int
    schema_version: str
    content_json: dict[str, Any]
    canonical_content_json: dict[str, Any]
    content_hash: str  # SHA-256 hex
    quality_status: ReportStatus
    quality_findings_json: list[dict[str, Any]]
    generated_by: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    supersedes_revision_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        report_id: str,
        revision_number: int,
        schema_version: str,
        content_json: dict[str, Any],
        canonical_content_json: dict[str, Any],
        content_hash: str,
        quality_status: ReportStatus,
        quality_findings_json: list[dict[str, Any]],
        generated_by: str,
        supersedes_revision_id: str | None = None,
    ) -> ReportRevision:
        return cls(
            id=_uuid(),
            report_id=report_id,
            revision_number=revision_number,
            schema_version=schema_version,
            content_json=content_json,
            canonical_content_json=canonical_content_json,
            content_hash=content_hash,
            quality_status=quality_status,
            quality_findings_json=quality_findings_json,
            generated_by=generated_by,
            generated_at=datetime.now(UTC),
            supersedes_revision_id=supersedes_revision_id,
        )


# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportSourceReference:
    """Structured provenance for each field/chapter in a report revision."""

    id: str
    report_revision_id: str
    source_type: SourceType
    source_id: str
    source_revision: str
    section_key: str
    field_path: str
    tool_name: str
    tool_version: str
    result_id: str
    content_hash: str

    @classmethod
    def create(cls, **kwargs: Any) -> ReportSourceReference:
        return cls(id=_uuid(), **kwargs)


# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportReviewAction:
    """Append-only audit record for review workflow transitions."""

    id: str
    report_id: str
    report_revision_id: str
    action: ReviewAction
    actor: str
    comment: str
    from_status: ReportStatus
    to_status: ReportStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(cls, **kwargs: Any) -> ReportReviewAction:
        return cls(id=_uuid(), **kwargs)


# ===================================================================
# Template & Export Artifact models (Task 9B)
# ===================================================================


@dataclass(frozen=True)
class ReportTemplate:
    """Versioned report template.  Active templates are immutable."""

    id: str
    template_code: str
    report_type: ReportType
    format: ExportFormat
    version: str
    status: TemplateStatus
    schema_version: str
    locale: str
    manifest_json: dict[str, Any]
    template_content_hash: str
    created_by: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    activated_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        template_code: str,
        report_type: ReportType,
        format: ExportFormat,
        version: str,
        schema_version: str,
        locale: str = "zh-CN",
        manifest_json: dict[str, Any] | None = None,
        template_content_hash: str = "",
        created_by: str = "system",
    ) -> ReportTemplate:
        return cls(
            id=_uuid(),
            template_code=template_code,
            report_type=report_type,
            format=format,
            version=version,
            status=TemplateStatus.DRAFT,
            schema_version=schema_version,
            locale=locale,
            manifest_json=manifest_json or {},
            template_content_hash=template_content_hash,
            created_by=created_by,
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class ReportExportArtifact:
    """Immutable export artifact bound to a revision + template version."""

    id: str
    report_id: str
    report_revision_id: str
    revision_number: int
    format: ExportFormat
    template_id: str
    template_version: str
    schema_version: str
    status: ArtifactStatus
    storage_key: str
    file_name: str
    mime_type: str
    file_size_bytes: int
    file_sha256: str
    source_content_hash: str
    render_manifest_json: dict[str, Any]
    generated_by: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    failure_code: str = ""
    failure_message: str = ""

    @classmethod
    def create(
        cls,
        *,
        report_id: str,
        report_revision_id: str,
        revision_number: int,
        format: ExportFormat,
        template_id: str,
        template_version: str,
        schema_version: str,
        file_name: str,
        mime_type: str,
        source_content_hash: str,
        generated_by: str,
    ) -> ReportExportArtifact:
        return cls(
            id=_uuid(),
            report_id=report_id,
            report_revision_id=report_revision_id,
            revision_number=revision_number,
            format=format,
            template_id=template_id,
            template_version=template_version,
            schema_version=schema_version,
            status=ArtifactStatus.PENDING,
            storage_key="",
            file_name=file_name,
            mime_type=mime_type,
            file_size_bytes=0,
            file_sha256="",
            source_content_hash=source_content_hash,
            render_manifest_json={},
            generated_by=generated_by,
            generated_at=datetime.now(UTC),
        )
