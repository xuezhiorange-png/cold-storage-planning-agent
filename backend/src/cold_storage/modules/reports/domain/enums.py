"""Report domain enumerations."""

from __future__ import annotations

from enum import StrEnum


class ReportStatus(StrEnum):
    DRAFT = "draft"
    GENERATED = "generated"
    UNDER_REVIEW = "under_review"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    ARCHIVED = "archived"


class ReportType(StrEnum):
    COLD_STORAGE_CONCEPT_DESIGN = "cold_storage_concept_design"


class QualitySeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


class SourceType(StrEnum):
    PROJECT = "project"
    PROJECT_VERSION = "project_version"
    AGENT_SESSION = "agent_session"
    AGENT_TURN = "agent_turn"
    AGENT_TOOL_CALL = "agent_tool_call"
    CALCULATION_RESULT = "calculation_result"
    SCHEME_RESULT = "scheme_result"
    KNOWLEDGE_REVISION = "knowledge_revision"


class ReviewAction(StrEnum):
    SUBMIT_REVIEW = "submit_review"
    REQUEST_CHANGES = "request_changes"
    MARK_REVIEWED = "mark_reviewed"
    APPROVE = "approve"
    ARCHIVE = "archive"


class ExportFormat(StrEnum):
    DOCX = "docx"
    PDF = "pdf"


class TemplateStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class ArtifactStatus(StrEnum):
    PENDING = "pending"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class RenderMode(StrEnum):
    DRAFT = "draft"
    FORMAL = "formal"


class ReportLocale(StrEnum):
    ZH_CN = "zh-CN"
    EN_US = "en-US"


SUPPORTED_LOCALES: frozenset[ReportLocale] = frozenset(ReportLocale)


# Status transitions: from_status -> set of allowed to_status
STATUS_TRANSITIONS: dict[ReportStatus, set[ReportStatus]] = {
    ReportStatus.DRAFT: {ReportStatus.GENERATED},
    ReportStatus.GENERATED: {ReportStatus.UNDER_REVIEW},
    ReportStatus.UNDER_REVIEW: {ReportStatus.REVIEWED, ReportStatus.DRAFT},
    ReportStatus.REVIEWED: {ReportStatus.APPROVED},
    ReportStatus.APPROVED: {ReportStatus.ARCHIVED},
    ReportStatus.ARCHIVED: set(),
}

# Review action -> (from_status, to_status)
ACTION_TRANSITIONS: dict[ReviewAction, tuple[ReportStatus, ReportStatus]] = {
    ReviewAction.SUBMIT_REVIEW: (ReportStatus.GENERATED, ReportStatus.UNDER_REVIEW),
    ReviewAction.REQUEST_CHANGES: (ReportStatus.UNDER_REVIEW, ReportStatus.DRAFT),
    ReviewAction.MARK_REVIEWED: (ReportStatus.UNDER_REVIEW, ReportStatus.REVIEWED),
    ReviewAction.APPROVE: (ReportStatus.REVIEWED, ReportStatus.APPROVED),
    ReviewAction.ARCHIVE: (ReportStatus.APPROVED, ReportStatus.ARCHIVED),
}

# Draft export allowed statuses
DRAFT_EXPORT_STATUSES: frozenset[ReportStatus] = frozenset(
    {
        ReportStatus.DRAFT,
        ReportStatus.GENERATED,
        ReportStatus.UNDER_REVIEW,
        ReportStatus.REVIEWED,
    }
)

# Formal export allowed statuses
FORMAL_EXPORT_STATUSES: frozenset[ReportStatus] = frozenset(
    {
        ReportStatus.APPROVED,
        ReportStatus.ARCHIVED,
    }
)
