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
    ArtifactStatus,
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
    ReportExportArtifact,
    ReportReviewAction,
    ReportRevision,
    ReportSourceReference,
)
from cold_storage.modules.reports.domain.quality import get_blockers, has_blockers
from cold_storage.modules.reports.domain.status_machine import apply_action


def _parse_dt(val: Any) -> datetime | Any:
    """Parse an ISO datetime string back to a datetime object.

    Used during idempotency replay where ``_serialize_result`` converts
    datetimes to ISO strings via ``.isoformat()``.
    """
    if isinstance(val, str):
        return datetime.fromisoformat(val)
    return val


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

    def save_idempotency_record(
        self, key: str, actor: str, action: str, fingerprint: str
    ) -> tuple[str, int]:
        raise NotImplementedError

    def get_idempotency_record(self, key: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def complete_idempotency_record(
        self,
        key: str,
        result_payload: Any,
        *,
        claim_token: str,
        claim_version: int,
    ) -> None:
        raise NotImplementedError

    def fail_idempotency_record(
        self,
        key: str,
        failure_code: str,
        failure_message: str,
        *,
        claim_token: str,
        claim_version: int,
    ) -> None:
        raise NotImplementedError

    def reset_failed_idempotency(self, key: str) -> None:
        raise NotImplementedError

    def reclaim_stale_idempotency(
        self,
        key: str,
        fingerprint: str,
        cutoff: datetime,
        original_claimed_at: datetime,
        *,
        old_claim_token: str,
        old_claim_version: int,
    ) -> tuple[bool, str | None, int | None]:
        raise NotImplementedError

    def fail_nonterminal_artifacts(
        self,
        report_id: str,
        *,
        idempotency_key: str,
        stale_claim_token: str,
        stale_claim_version: int,
    ) -> int:
        raise NotImplementedError

    def transition_artifact(
        self,
        artifact: ReportExportArtifact,
        *,
        expected_status: ArtifactStatus,
        claim_token: str,
        claim_version: int,
    ) -> None:
        raise NotImplementedError

    def commit(self) -> None:
        raise NotImplementedError

    def rollback(self) -> None:
        raise NotImplementedError


class ReportService:
    """Application service for report lifecycle management."""

    def __init__(
        self,
        repository: ReportRepository,
        assembler: ReportAssembler,
    ) -> None:
        self._repo = repository
        self._assembler = assembler

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
            ct, cv = self._claim_idempotency(idempotency_key, actor, "create", fp)

        report = Report.create(
            project_id=project_id,
            project_version_id=project_version_id,
            report_type=report_type,
            created_by=actor,
        )
        self._repo.save_report(report)
        # Complete idempotency BEFORE commit so both are in the same transaction.
        # If either fails, rollback the entire transaction.
        try:
            if idempotency_key:
                self._complete_idempotency(
                    idempotency_key,
                    report,
                    claim_token=ct,
                    claim_version=cv,
                )
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise
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
            fp = self._make_fingerprint("generate", actor, report_id, report.project_id)
            existing = self._check_idempotency_revision(idempotency_key, fp)
            if existing is not None:
                return existing
            ct, cv = self._claim_idempotency(idempotency_key, actor, "generate", fp)

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
            # Clear approval fields when new revision is generated
            approved_revision_id=None,
            approved_content_hash=None,
            approved_by=None,
            approved_at=None,
        )
        self._repo.update_report(updated, expected_version=report.version)
        # Complete idempotency BEFORE commit so both are in the same transaction.
        # If either fails, rollback the entire transaction.
        try:
            if idempotency_key:
                self._complete_idempotency(
                    idempotency_key,
                    revision,
                    claim_token=ct,
                    claim_version=cv,
                )
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise

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

        # P0-8: Compute approval fields
        approval_fields: dict[str, Any] = {}
        if action == ReviewAction.APPROVE:
            if latest_rev is None:
                raise ReportNotFoundError(f"No revision to approve for report {report_id}")
            # Check blockers
            if has_blockers(latest_rev.quality_findings_json):
                raise QualityBlockerError(get_blockers(latest_rev.quality_findings_json))
            from datetime import datetime as _dt

            approval_fields = {
                "approved_revision_id": latest_rev.id,
                "approved_content_hash": latest_rev.content_hash,
                "approved_by": actor,
                "approved_at": _dt.now(UTC).isoformat(),
            }
        elif action in (ReviewAction.REQUEST_CHANGES,):
            # Clear approval on request changes
            approval_fields = {
                "approved_revision_id": None,
                "approved_content_hash": None,
                "approved_by": None,
                "approved_at": None,
            }

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
            **approval_fields,
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
        different parameters (fingerprint mismatch).
        """
        record = self._repo.get_idempotency_record(key)
        if record is None:
            return None
        # Fingerprint mismatch means different params → conflict
        if record["fingerprint"] != fingerprint:
            raise IdempotencyPayloadConflictError(key)
        # Only return result if completed
        if record["status"] == "completed" and record["result_payload"] is not None:
            payload = record["result_payload"]
            # Reconstruct Report from payload (serialized as dict)
            if isinstance(payload, dict) and "id" in payload:
                from cold_storage.modules.reports.domain.enums import ReportType

                return Report(
                    id=payload["id"],
                    project_id=payload["project_id"],
                    project_version_id=payload["project_version_id"],
                    report_type=ReportType(payload["report_type"]),
                    status=ReportStatus(payload["status"]),
                    current_revision_number=payload["current_revision_number"],
                    created_by=payload["created_by"],
                    created_at=_parse_dt(payload["created_at"]),
                    updated_at=_parse_dt(payload["updated_at"]),
                    version=payload["version"],
                )
        return None

    def _check_idempotency_revision(self, key: str, fingerprint: str) -> ReportRevision | None:
        """Check for a completed revision result matching key + fingerprint."""
        record = self._repo.get_idempotency_record(key)
        if record is None:
            return None
        if record["fingerprint"] != fingerprint:
            raise IdempotencyPayloadConflictError(key)
        if record["status"] == "completed" and record["result_payload"] is not None:
            payload = record["result_payload"]
            if isinstance(payload, dict) and "id" in payload:
                from cold_storage.modules.reports.domain.enums import ReportStatus as RS

                return ReportRevision(
                    id=payload["id"],
                    report_id=payload["report_id"],
                    revision_number=payload["revision_number"],
                    schema_version=payload["schema_version"],
                    content_json=payload["content_json"],
                    canonical_content_json=payload["canonical_content_json"],
                    content_hash=payload["content_hash"],
                    quality_status=RS(payload["quality_status"]),
                    quality_findings_json=payload["quality_findings_json"],
                    generated_by=payload["generated_by"],
                    generated_at=_parse_dt(payload["generated_at"]),
                    supersedes_revision_id=payload.get("supersedes_revision_id"),
                )
        return None

    def _claim_idempotency(
        self, key: str, actor: str, action: str, fingerprint: str
    ) -> tuple[str, int]:
        """Claim an idempotency key via INSERT.

        Returns (claim_token, claim_version).
        Raises IdempotencyClaimError if another request holds the key.
        """
        try:
            return self._repo.save_idempotency_record(
                key=key, actor=actor, action=action, fingerprint=fingerprint
            )
        except Exception as exc:
            # Duplicate key → already claimed
            raise IdempotencyClaimError(key) from exc

    def _complete_idempotency(
        self,
        key: str,
        result: object,
        *,
        claim_token: str,
        claim_version: int,
    ) -> None:
        """Mark idempotency key as completed with the result payload."""
        payload = self._serialize_result(result)
        self._repo.complete_idempotency_record(
            key, payload, claim_token=claim_token, claim_version=claim_version
        )

    @staticmethod
    def _serialize_result(result: object) -> dict[str, Any]:
        """Serialize a Report or ReportRevision to a JSON-safe dict."""
        from dataclasses import fields, is_dataclass

        if not is_dataclass(result) or isinstance(result, type):
            return {"error": "non-serializable result"}
        d: dict[str, Any] = {}
        for f in fields(result):
            val = getattr(result, f.name)
            if hasattr(val, "value"):
                d[f.name] = val.value
            elif hasattr(val, "isoformat"):
                d[f.name] = val.isoformat()
            else:
                d[f.name] = val
        return d

    @staticmethod
    def _make_fingerprint(*parts: str) -> str:
        """Create a fingerprint from request parameters for idempotency binding.

        Uses null-byte separators to prevent deterministic collisions
        between ("ab", "c") and ("a", "bc").
        """
        import hashlib

        h = hashlib.sha256()
        for p in parts:
            h.update(b"\x00")
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
        raise SchemaValidationError([f"Unknown schema: {schema_version}"]) from exc

    try:
        jsonschema.validate(instance=content, schema=schema)
    except jsonschema.ValidationError as exc:
        raise SchemaValidationError([f"{exc.json_path}: {exc.message}"]) from exc
