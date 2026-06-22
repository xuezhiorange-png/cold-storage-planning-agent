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
    QualitySeverity,
    ReportStatus,
    ReportType,
    ReviewAction,
    SourceType,
)


def _uuid() -> str:
    return str(uuid4())


# ---------------------------------------------------------------------------
# Quality Finding
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
# Report
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
# ReportRevision — immutable snapshot
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
# ReportSourceReference
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
# ReportReviewAction
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
