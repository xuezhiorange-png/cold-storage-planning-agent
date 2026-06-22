"""Report application service — orchestrates creation, generation, review, approval.

No ORM access, no LLM calls.  Uses repository port and assembler.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cold_storage.modules.reports.application.assembler import (
    ReportAssembler,
)
from cold_storage.modules.reports.domain.enums import (
    ReportStatus,
    ReportType,
    ReviewAction,
)
from cold_storage.modules.reports.domain.errors import (
    IdempotencyClaimError,
    IdempotencyPayloadConflictError,
    InvalidStatusTransitionError,
    QualityBlockerError,
    ReportNotFoundError,
    SchemaValidationError,
)
from cold_storage.modules.reports.domain.models import (
    Report,
    ReportReviewAction,
    ReportRevision,
    ReportSourceReference,
)
from cold_storage.modules.reports.domain.quality import get_blockers, has_blockers
from cold_storage.modules.reports.domain.status_machine import apply_action


class ReportRepository:
    """Port: persistence for reports, revisions, source refs, review actions."""

    def save_report(self, report: Report) -> None:
        raise NotImplementedError

    def get_report(self, report_id: str) -> Report | None:
        raise NotImplementedError

    def list_reports(
        self, project_id: str | None = None, created_by: str | None = None
    ) -> list[Report]:
        raise NotImplementedError

    def update_report(self, report: Report, *, expected_version: int | None = None) -> None:
        raise NotImplementedError

    def save_revision(self, revision: ReportRevision) -> None:
        raise NotImplementedError

    def get_revision(self, report_id: str, revision_number: int) -> ReportRevision | None:
        raise NotImplementedError

    def list_revisions(self, report_id: str) -> list[ReportRevision]:
        raise NotImplementedError

    def save_source_references(self, refs: list[ReportSourceReference]) -> None:
        raise NotImplementedError

    def save_review_action(self, action: ReportReviewAction) -> None:
        raise NotImplementedError

    def get_latest_revision(self, report_id: str) -> ReportRevision | None:
        raise NotImplementedError

    def commit(self) -> None:
        raise NotImplementedError


class ReportService:
    """Application service for report lifecycle management."""

    def __init__(
        self,
        repository: ReportRepository,
        assembler: ReportAssembler,
        *,
        idempotency_store: Any | None = None,
    ) -> None:
        self._repo = repository
        self._assembler = assembler
        self._idempotency_store = idempotency_store

    # --- CRUD ---

    def create_report(
        self,
        *,
        project_id: str,
        project_version_id: str,
        report_type: ReportType,
        actor: str,
        idempotency_key: str | None = None,
    ) -> Report:
        # Idempotency check
        if idempotency_key:
            fp = self._make_fingerprint(
                "create", actor, project_id, project_version_id, report_type.value
            )
            existing = self._check_idempotency(idempotency_key, fp)
            if existing is not None:
                return existing
            self._claim_idempotency(idempotency_key)

        report = Report.create(
            project_id=project_id,
            project_version_id=project_version_id,
            report_type=report_type,
            created_by=actor,
        )
        self._repo.save_report(report)
        self._repo.commit()
        # Store result for idempotency
        if idempotency_key:
            self._complete_idempotency(idempotency_key, report)
        return report

    def get_report(self, report_id: str, actor: str) -> Report:
        report = self._repo.get_report(report_id)
        if report is None:
            raise ReportNotFoundError(report_id)
        if report.created_by != actor:
            raise ReportNotFoundError(report_id)  # Owner isolation — 404 for non-owners
        return report

    def list_reports(self, project_id: str | None = None, actor: str | None = None) -> list[Report]:
        return self._repo.list_reports(project_id=project_id, created_by=actor)

    # --- Generation ---

    def generate_revision(
        self,
        report_id: str,
        actor: str,
        *,
        idempotency_key: str | None = None,
    ) -> ReportRevision:
        report = self.get_report(report_id, actor)

        # Check status allows generation
        if report.status not in (ReportStatus.DRAFT, ReportStatus.GENERATED):
            raise InvalidStatusTransitionError(report.status.value, "generated")

        # Idempotency
        if idempotency_key:
            fp = self._make_fingerprint(
                "generate", actor, report_id, report.project_id
            )
            existing = self._check_idempotency_revision(idempotency_key, fp)
            if existing is not None:
                return existing
            self._claim_idempotency(idempotency_key)

        revision_number = report.current_revision_number + 1
        supersedes = None
        if report.current_revision_number > 0:
            prev = self._repo.get_latest_revision(report_id)
            if prev:
                supersedes = prev.id

        # Assemble
        assembled = self._assembler.assemble(
            report_id=report_id,
            project_id=report.project_id,
            project_version_id=report.project_version_id,
            report_type=report.report_type,
            revision_number=revision_number,
            generated_by=actor,
        )

        # JSON Schema validation — fail closed if content doesn't match schema
        _validate_schema(assembled.content, report.report_type, assembled.schema_version)

        # Quality status determines report status
        quality_status = assembled.quality_status

        # Save revision
        revision = ReportRevision.create(
            report_id=report_id,
            revision_number=revision_number,
            schema_version=assembled.schema_version,
            content_json=assembled.content,
            canonical_content_json=assembled.canonical_content,
            content_hash=assembled.content_hash,
            quality_status=quality_status,
            quality_findings_json=assembled.findings,
            generated_by=actor,
            supersedes_revision_id=supersedes,
        )
        self._repo.save_revision(revision)

        # Save source references
        source_refs = [
            ReportSourceReference.create(
                report_revision_id=revision.id,
                source_type=ref["source_type"],
                source_id=ref["source_id"],
                source_revision=ref.get("source_revision", ""),
                section_key=ref["section_key"],
                field_path=ref["field_path"],
                tool_name=ref.get("tool_name", ""),
                tool_version=ref.get("tool_version", ""),
                result_id=ref.get("result_id", ""),
                content_hash=ref.get("content_hash", ""),
            )
            for ref in assembled.source_refs
        ]
        self._repo.save_source_references(source_refs)

        # Update report
        from dataclasses import replace

        updated = replace(
            report,
            status=quality_status,
            current_revision_number=revision_number,
            updated_at=datetime.now(UTC),
            version=report.version + 1,
        )
        self._repo.update_report(updated, expected_version=report.version)
        self._repo.commit()

        # Store result for idempotency
        if idempotency_key:
            self._complete_idempotency(idempotency_key, revision)

        return revision

    # --- Review workflow ---

    def submit_review(
        self,
        report_id: str,
        actor: str,
        *,
        comment: str = "",
    ) -> Report:
        return self._apply_review_action(report_id, ReviewAction.SUBMIT_REVIEW, actor, comment)

    def request_changes(
        self,
        report_id: str,
        actor: str,
        *,
        comment: str = "",
    ) -> Report:
        return self._apply_review_action(report_id, ReviewAction.REQUEST_CHANGES, actor, comment)

    def mark_reviewed(
        self,
        report_id: str,
        actor: str,
        *,
        comment: str = "",
    ) -> Report:
        return self._apply_review_action(report_id, ReviewAction.MARK_REVIEWED, actor, comment)

    def approve(
        self,
        report_id: str,
        actor: str,
        *,
        comment: str = "",
    ) -> Report:
        return self._apply_review_action(report_id, ReviewAction.APPROVE, actor, comment)

    def archive(
        self,
        report_id: str,
        actor: str,
        *,
        comment: str = "",
    ) -> Report:
        return self._apply_review_action(report_id, ReviewAction.ARCHIVE, actor, comment)

    def _apply_review_action(
        self,
        report_id: str,
        action: ReviewAction,
        actor: str,
        comment: str,
    ) -> Report:
        from dataclasses import replace

        report = self.get_report(report_id, actor)  # owner isolation

        # Validate blockers for non-draft transitions
        new_status = apply_action(report.status, action)

        # Get latest revision for quality check and revision reference
        latest_rev = self._repo.get_latest_revision(report_id)

        # Check blockers when moving out of draft
        if (
            action == ReviewAction.SUBMIT_REVIEW
            and latest_rev
            and has_blockers(latest_rev.quality_findings_json)
        ):
            raise QualityBlockerError(get_blockers(latest_rev.quality_findings_json))

        # Validate revision exists when expected
        if report.current_revision_number > 0 and latest_rev is None:
            raise ReportNotFoundError(f"Revision not found for report {report_id}")

        # Record action with real revision UUID
        action_record = ReportReviewAction.create(
            report_id=report_id,
            report_revision_id=latest_rev.id if latest_rev else "",
            action=action,
            actor=actor,
            comment=comment,
            from_status=report.status,
            to_status=new_status,
        )
        self._repo.save_review_action(action_record)

        # Update report status
        updated = replace(
            report,
            status=new_status,
            updated_at=datetime.now(UTC),
            version=report.version + 1,
        )
        self._repo.update_report(updated, expected_version=report.version)
        self._repo.commit()

        return updated

    # --- Revision access ---

    def get_revision(
        self,
        report_id: str,
        revision_number: int,
        actor: str,
    ) -> ReportRevision:
        self.get_report(report_id, actor)  # access check
        rev = self._repo.get_revision(report_id, revision_number)
        if rev is None:
            raise ReportNotFoundError(f"{report_id}/rev/{revision_number}")
        return rev

    def list_revisions(self, report_id: str, actor: str) -> list[ReportRevision]:
        self.get_report(report_id, actor)  # access check
        return self._repo.list_revisions(report_id)

    # --- Export ---

    def export_json(
        self,
        report_id: str,
        revision_number: int,
        actor: str,
    ) -> dict[str, Any]:
        rev = self.get_revision(report_id, revision_number, actor)
        return {
            "schema_version": rev.schema_version,
            "content_hash": rev.content_hash,
            "content": rev.content_json,
        }

    # --- Comparison ---

    def compare_revisions(
        self,
        report_id: str,
        rev_a: int,
        rev_b: int,
        actor: str,
    ) -> list[dict[str, Any]]:
        from cold_storage.modules.reports.domain.revision_diff import diff_revisions

        ra = self.get_revision(report_id, rev_a, actor)
        rb = self.get_revision(report_id, rev_b, actor)
        return diff_revisions(ra.content_json, rb.content_json)

    # --- Idempotency ---

    def _check_idempotency(self, key: str, fingerprint: str) -> Report | None:
        """Check for a completed result matching key + fingerprint.

        Returns the original result if found, None otherwise.
        Raises IdempotencyPayloadConflictError if the key was used with
        different parameters.
        """
        if self._idempotency_store is None:
            return None
        result = self._idempotency_store.get(key)
        if result is None:
            return None
        if isinstance(result, Report):
            # Verify fingerprint matches
            stored_fp = getattr(result, "_idempotency_fingerprint", None)
            if stored_fp is not None and stored_fp != fingerprint:
                raise IdempotencyPayloadConflictError(key)
            return result
        return None

    def _check_idempotency_revision(
        self, key: str, fingerprint: str
    ) -> ReportRevision | None:
        """Check for a completed revision result matching key + fingerprint."""
        if self._idempotency_store is None:
            return None
        result = self._idempotency_store.get(key)
        if result is None:
            return None
        if isinstance(result, ReportRevision):
            stored_fp = getattr(result, "_idempotency_fingerprint", None)
            if stored_fp is not None and stored_fp != fingerprint:
                raise IdempotencyPayloadConflictError(key)
            return result
        return None

    def _claim_idempotency(self, key: str) -> None:
        """Claim an idempotency key to prevent concurrent duplicate execution.

        Raises IdempotencyClaimError if another request holds the key.
        """
        if self._idempotency_store is None:
            return
        if hasattr(self._idempotency_store, "claim"):
            claimed = self._idempotency_store.claim(key)
            if not claimed:
                raise IdempotencyClaimError(key)

    def _complete_idempotency(self, key: str, result: object) -> None:
        """Store the result for idempotency after successful execution."""
        if self._idempotency_store is None:
            return
        if hasattr(self._idempotency_store, "complete"):
            self._idempotency_store.complete(key, result)
        else:
            self._idempotency_store.set(key, result)

    @staticmethod
    def _make_fingerprint(*parts: str) -> str:
        """Create a fingerprint from request parameters for idempotency binding."""
        import hashlib
        h = hashlib.sha256()
        for p in parts:
            h.update(p.encode())
        return h.hexdigest()


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def _validate_schema(
    content: dict[str, Any],
    report_type: ReportType,
    schema_version: str,
) -> None:
    """Validate assembled content against the JSON Schema.

    Raises ``SchemaValidationError`` if the content is invalid.
    """
    import jsonschema

    from cold_storage.modules.reports.domain.schema import get_schema

    try:
        schema = get_schema(report_type.value, schema_version.split("@")[-1])
    except ValueError as exc:
        # Unknown schema version — treat as invalid
        raise SchemaValidationError(
            [f"Unknown schema: {schema_version}"]
        ) from exc

    try:
        jsonschema.validate(instance=content, schema=schema)
    except jsonschema.ValidationError as exc:
        raise SchemaValidationError(
            [f"{exc.json_path}: {exc.message}"]
        ) from exc
