"""Report render service — orchestrates export rendering to DOCX/PDF.

No ORM access, no LLM calls.  Uses repository port, artifact storage,
and renderers.

P0-4: Real Revision Rendering — ISO 8601 dates, real manifest metadata
P0-5: Formal Export Rules — verify approved revision
P0-6: Real Idempotency — fingerprint-based deduplication
P0-7: Artifact State Machine — pending -> rendering -> completed/failed
P0-8: Download Safety — verify_download() with integrity checks
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from cold_storage.modules.reports.application.service import ReportRepository
from cold_storage.modules.reports.domain.enums import (
    DRAFT_EXPORT_STATUSES,
    FORMAL_EXPORT_STATUSES,
    ArtifactStatus,
    ExportFormat,
    RenderMode,
    ReportLocale,
    TemplateStatus,
)
from cold_storage.modules.reports.domain.errors import (
    ArtifactFileNotFoundError,
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactNotReadyError,
    ExportPermissionError,
    IdempotencyClaimError,
    IdempotencyPayloadConflictError,
    RenderError,
    ReportNotFoundError,
    TemplateNotFoundError,
)
from cold_storage.modules.reports.domain.models import (
    ApprovalSnapshot,
    Report,
    ReportExportArtifact,
    ReportRevision,
    ReportTemplate,
)
from cold_storage.modules.reports.domain.observer import NoopCanonicalObserver
from cold_storage.modules.reports.domain.reclaim_delete_result import ReclaimDeleteResult
from cold_storage.modules.reports.domain.render_model import JsonObject, LocalizedReportRenderModel


class IdempotencyWaiterPort(Protocol):
    """Port: wait for another render to complete on the same idempotency key.

    The ``notify_completed`` / ``notify_failed`` methods are called by the
    *winner* (the thread that successfully claimed the idempotency record)
    so that concurrent *loser* threads blocked in ``wait_for_completion``
    can be woken up and learn the outcome.

    ``wait_for_completion`` accepts an ``expected_fingerprint`` to validate
    that the completed record matches the caller's request parameters, and a
    monotonic-clock ``deadline`` for timeout.
    """

    def wait_for_completion(
        self,
        idempotency_key: str,
        expected_fingerprint: str,
        deadline: float,
        expected_report_id: str = "",
        expected_revision_number: int = 0,
    ) -> ReportExportArtifact | None:
        """Block until the render for *idempotency_key* finishes, or *deadline* elapses.

        Returns the completed artifact, or ``None`` if the outcome is unknown.
        Raises ``IdempotencyClaimError`` on timeout or if the winner's render failed.
        ``IdempotencyPayloadConflictError`` if the completed record's fingerprint
        does not match *expected_fingerprint*.
        """
        ...

    def notify_completed(self, idempotency_key: str, artifact_id: str) -> None:
        """Notify all waiters that the render succeeded."""
        ...

    def notify_failed(self, idempotency_key: str, error: Exception) -> None:
        """Notify all waiters that the render failed."""
        ...


class DatabaseIdempotencyWaiter:
    """Production waiter that polls the idempotency_records table.

    Uses fresh database connections per poll via ``session_factory`` to
    ensure it always observes the winner's commit.  Falls back to a shared
    ``repo`` if no factory is provided (backward-compat for simple setups).

    Validates on completion:
    - fingerprint matches ``expected_fingerprint``
    - ``result_payload`` is a dict containing ``artifact_id``
    - the artifact exists and is ``COMPLETED``
    - claim lineage (claim_token on artifact vs idempotency record)

    ``failed`` status propagates ``failure_code`` / ``failure_message``.
    """

    def __init__(
        self,
        repo: Any = None,
        artifact_repo: ReportArtifactRepositoryPort | None = None,
        *,
        session_factory: Callable[[], Any] | None = None,
        poll_interval: float = 0.5,
        expected_report_id: str = "",
        expected_revision_number: int = 0,
    ) -> None:
        self._repo = repo
        self._artifact_repo = artifact_repo
        self._session_factory = session_factory
        self._poll_interval = poll_interval
        self._expected_report_id = expected_report_id
        self._expected_revision_number = expected_revision_number

    def wait_for_completion(
        self,
        idempotency_key: str,
        expected_fingerprint: str,
        deadline: float,
        expected_report_id: str = "",
        expected_revision_number: int = 0,
    ) -> ReportExportArtifact | None:
        """Poll the idempotency_records table until completed/failed or deadline."""

        from cold_storage.modules.reports.infrastructure.repository import (
            SQLReportRepository,
        )

        # Use provided values, fall back to instance defaults
        effective_report_id = expected_report_id or self._expected_report_id
        effective_revision_number = expected_revision_number or self._expected_revision_number

        while time.monotonic() < deadline:
            # Open fresh connection when factory is provided
            repo = self._repo
            artifact_repo = self._artifact_repo
            fresh_session = None
            if self._session_factory:
                fresh_session = self._session_factory()
                repo = SQLReportRepository(fresh_session)
                artifact_repo = SQLReportRepository(fresh_session)

            try:
                record = repo.get_idempotency_record(idempotency_key)
            finally:
                if fresh_session is not None:
                    fresh_session.close()

            if record:
                if record["status"] == "completed":
                    return self._handle_completed(
                        record,
                        expected_fingerprint,
                        idempotency_key,
                        artifact_repo,
                        expected_report_id=effective_report_id,
                        expected_revision_number=effective_revision_number,
                    )

                if record["status"] == "failed":
                    payload = record.get("result_payload") or {}
                    failure_code = payload.get("failure_code", "UnknownError")
                    failure_message = payload.get("failure_message", "Idempotency render failed")
                    raise IdempotencyClaimError(
                        idempotency_key,
                        failure_code=failure_code,
                        failure_message=failure_message,
                    )

            time.sleep(self._poll_interval)

        raise IdempotencyClaimError(
            idempotency_key,
            failure_code="WaiterTimeout",
            failure_message=("Waiter timed out after waiting for idempotency key"),
        )

    def _handle_completed(
        self,
        record: dict[str, Any],
        expected_fingerprint: str,
        idempotency_key: str,
        artifact_repo: ReportArtifactRepositoryPort | None,
        *,
        expected_report_id: str = "",
        expected_revision_number: int = 0,
    ) -> ReportExportArtifact | None:
        """Validate a completed idempotency record and return the artifact."""
        # 1. Validate fingerprint
        if record.get("fingerprint") != expected_fingerprint:
            raise IdempotencyPayloadConflictError(idempotency_key)

        # 2. Validate result_payload is a dict
        payload = record.get("result_payload", {})
        if not isinstance(payload, dict):
            raise IdempotencyClaimError(
                idempotency_key,
                failure_code="InvalidPayload",
                failure_message="result_payload is not a dict",
            )

        # 3. Validate artifact_id exists
        artifact_id = payload.get("artifact_id")
        if not artifact_id:
            raise IdempotencyClaimError(
                idempotency_key,
                failure_code="MissingArtifactId",
                failure_message="result_payload missing artifact_id",
            )

        # 4. Validate artifact exists and is COMPLETED
        if artifact_repo is not None:
            artifact = artifact_repo.get_artifact(artifact_id)
            if artifact is None:
                raise IdempotencyClaimError(
                    idempotency_key,
                    failure_code="ArtifactNotFound",
                    failure_message=f"artifact {artifact_id} not found",
                )
            if artifact.status != ArtifactStatus.COMPLETED:
                raise IdempotencyClaimError(
                    idempotency_key,
                    failure_code="ArtifactNotCompleted",
                    failure_message=(f"artifact {artifact_id} status={artifact.status.value}"),
                )

            # 5. Validate claim lineage matches (claim_token)
            record_claim_token = record.get("claim_token", "")
            if artifact.claim_token != record_claim_token:
                raise IdempotencyClaimError(
                    idempotency_key,
                    failure_code="ClaimMismatch",
                    failure_message=(
                        f"artifact claim_token {artifact.claim_token} "
                        f"!= record claim_token {record_claim_token}"
                    ),
                )

            # 6. Validate claim_version matches
            record_claim_version = record.get("claim_version", 0)
            if artifact.claim_version != record_claim_version:
                raise IdempotencyClaimError(
                    idempotency_key,
                    failure_code="ClaimVersionMismatch",
                    failure_message=(
                        f"artifact claim_version {artifact.claim_version} "
                        f"!= record claim_version {record_claim_version}"
                    ),
                )

            # 7. Validate idempotency_key on artifact
            if artifact.idempotency_key != idempotency_key:
                raise IdempotencyClaimError(
                    idempotency_key,
                    failure_code="IdempotencyKeyMismatch",
                    failure_message=(
                        f"artifact idempotency_key {artifact.idempotency_key} "
                        f"!= expected {idempotency_key}"
                    ),
                )

            # 8. Validate report_id matches expected
            if expected_report_id and artifact.report_id != expected_report_id:
                raise IdempotencyClaimError(
                    idempotency_key,
                    failure_code="ReportIdMismatch",
                    failure_message=(
                        f"artifact report_id {artifact.report_id} != expected {expected_report_id}"
                    ),
                )

            # 9. Validate revision_number matches expected
            if expected_revision_number and artifact.revision_number != expected_revision_number:
                raise IdempotencyClaimError(
                    idempotency_key,
                    failure_code="RevisionNumberMismatch",
                    failure_message=(
                        f"artifact revision_number {artifact.revision_number} "
                        f"!= expected {expected_revision_number}"
                    ),
                )

            return artifact

        # No artifact_repo — can't validate further
        return None

    # -- Idempotency waiter port and implementations ------------------------------

    def notify_completed(self, idempotency_key: str, artifact_id: str) -> None:
        pass  # No-op for database polling

    def notify_failed(self, idempotency_key: str, error: Exception) -> None:
        pass  # No-op for database polling


class ArtifactStoragePort(Protocol):
    """Port: artifact file storage operations."""

    def put_temp(self, data: bytes, filename: str) -> tuple[str, str]: ...
    def cleanup_temp(self, path: str) -> None: ...
    def finalize_temp(
        self,
        path: str,
        artifact_id: str,
        filename: str,
        *,
        claim_token: str = "",
        claim_version: int = 0,
    ) -> str: ...
    def delete(self, key: str, *, claim_token: str = "", claim_version: int = 0) -> None: ...
    def reclaim_delete(
        self,
        key: str,
        *,
        stale_claim_token: str,
        stale_claim_version: int,
        reclaim_token: str = "",
        reclaim_version: int = 0,
        missing_is_success: bool = False,
        repository: Any = None,
    ) -> ReclaimDeleteResult:
        """Reclaim-delete an artifact.

        ``missing_is_success=True`` requires a valid ``repository``
        for DeletionReceipt verification.  Passing ``repository=None``
        with ``missing_is_success=True`` raises :class:`ValueError`.
        """
        ...

    def exists(self, key: str) -> bool: ...
    def get_path(self, key: str) -> str: ...
    def put(
        self,
        artifact_id: str,
        data: bytes,
        filename: str,
        *,
        claim_token: str = "",
        claim_version: int = 0,
    ) -> str: ...
    def get(self, key: str) -> bytes: ...
    def replace(
        self,
        key: str,
        data: bytes,
        *,
        claim_token: str = "",
        claim_version: int = 0,
    ) -> str: ...
    def delete_legacy_artifact(
        self,
        key: str,
        *,
        migration_actor: str,
        audit_reason: str,
        repository: Any,  # REQUIRED
    ) -> None: ...


class ReportTemplateRepositoryPort(Protocol):
    """Port: persistence for report templates."""

    def get_template(self, template_id: str) -> ReportTemplate | None: ...

    def get_active_template(
        self, template_code: str, format: ExportFormat, locale: ReportLocale | None = None
    ) -> ReportTemplate | None: ...

    def list_templates(
        self,
        template_code: str | None = None,
        format: ExportFormat | None = None,
        locale: ReportLocale | None = None,
    ) -> list[ReportTemplate]: ...

    def save_template(self, template: ReportTemplate) -> None: ...

    def update_template(self, template: ReportTemplate) -> None: ...

    # P0-7: Deactivate all active templates for the given code and format.
    def deactivate_templates(
        self, template_code: str, fmt: str, locale: ReportLocale | None = None
    ) -> int: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class ReportArtifactRepositoryPort(Protocol):
    """Port: persistence for export artifacts."""

    def save_artifact(self, artifact: ReportExportArtifact) -> None: ...
    def get_artifact(self, artifact_id: str) -> ReportExportArtifact | None: ...
    def list_artifacts(
        self,
        report_id: str,
        status: ArtifactStatus | None = None,
        locale: ReportLocale | None = None,
    ) -> list[ReportExportArtifact]: ...
    def find_artifact_by_idempotency(
        self, idempotency_key: str, report_id: str
    ) -> ReportExportArtifact | None: ...
    def update_artifact(self, artifact: ReportExportArtifact) -> None: ...
    def insert_artifact_with_claim(
        self,
        artifact: ReportExportArtifact,
        *,
        claim_token: str,
        claim_version: int,
    ) -> None: ...
    def fail_nonterminal_artifacts(
        self,
        report_id: str,
        *,
        idempotency_key: str,
        stale_claim_token: str,
        stale_claim_version: int,
    ) -> tuple[int, list[str]]: ...
    def transition_artifact(
        self,
        artifact: ReportExportArtifact,
        *,
        expected_status: ArtifactStatus,
        claim_token: str,
        claim_version: int,
    ) -> None: ...
    def fail_attempt_with_claim(
        self,
        artifact_id: str,
        idempotency_key: str,
        claim_token: str,
        claim_version: int,
        failure_code: str,
        failure_message: str,
    ) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


def _compute_fingerprint(
    *,
    actor: str,
    report_id: str,
    revision_number: int,
    source_content_hash: str,
    format: str,
    render_mode: str,
    template_id: str,
    template_version: str,
    template_content_hash: str,
    locale: str = "zh-CN",
    translation_catalog_version: str = "1.0.0",
    localized_template_content_hash: str = "",
) -> str:
    """Compute a deterministic fingerprint for idempotency checking."""
    payload = {
        "actor": actor,
        "report_id": report_id,
        "revision_number": revision_number,
        "source_content_hash": source_content_hash,
        "format": format,
        "render_mode": render_mode,
        "template_id": template_id,
        "template_version": template_version,
        "template_content_hash": template_content_hash,
        "locale": locale,
        "translation_catalog_version": translation_catalog_version,
        "localized_template_content_hash": localized_template_content_hash,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# P0-3: Unit of Work — atomic commit via single session
# ---------------------------------------------------------------------------


class ReportRenderUnitOfWork:
    """Atomic unit of work for report rendering.

    Wraps a single SQLAlchemy Session so that both the report repository and
    artifact repository share the same transaction.  ``commit()`` and
    ``rollback()`` operate on the underlying session exactly once.
    """

    def __init__(
        self,
        session: Any,  # sqlalchemy.orm.Session
        *,
        report_repo: ReportRepository | None = None,
        artifact_repo: ReportArtifactRepositoryPort | None = None,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._session = session
        self._session_factory: Callable[[], Any] | None = session_factory
        from cold_storage.modules.reports.infrastructure.repository import (
            SQLReportRepository,
        )

        # Validate that provided repos share the same session
        if report_repo is not None and getattr(report_repo, "_session", None) is not session:
            raise ValueError(
                "report_repo._session does not match the UOW session. "
                "Both repositories must share the same SQLAlchemy session."
            )
        if artifact_repo is not None and getattr(artifact_repo, "_session", None) is not session:
            raise ValueError(
                "artifact_repo._session does not match the UOW session. "
                "Both repositories must share the same SQLAlchemy session."
            )
        self._report_repo: ReportRepository = report_repo or SQLReportRepository(session)
        self._artifact_repo: ReportArtifactRepositoryPort | None = (
            artifact_repo or SQLReportRepository(session)
        )

    @property
    def report_repo(self) -> ReportRepository:
        return self._report_repo

    @property
    def artifact_repo(self) -> ReportArtifactRepositoryPort | None:
        return self._artifact_repo

    @property
    def session(self) -> Any:
        return self._session

    @property
    def session_factory(self) -> Callable[[], Any] | None:
        return self._session_factory

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


# ---------------------------------------------------------------------------


class ReportRenderService:
    """Application service for report export rendering.

    Parameters
    ----------
    uow:
        Unit of Work that provides report_repo and artifact_repo from a
        single shared session.
    storage:
        Artifact storage adapter (for saving rendered files).
    template_repo:
        Template repository port (for loading templates).
    """

    def __init__(
        self,
        *,
        uow: ReportRenderUnitOfWork,
        storage: ArtifactStoragePort | None = None,
        template_repo: ReportTemplateRepositoryPort | None = None,
        stale_claim_seconds: int = 300,
        clock: Callable[[], datetime] | None = None,
        idempotency_waiter: IdempotencyWaiterPort | None = None,
        canonical_observer: Any = None,
    ) -> None:
        """Initialize the render service.

        Parameters
        ----------
        uow:
            Required: a ``ReportRenderUnitOfWork`` that provides both
            report_repo and artifact_repo from a single session.
        storage:
            Artifact file storage adapter (required).
        template_repo:
            Template repository port.
        stale_claim_seconds:
            Seconds after which a 'claimed' idempotency record is
            considered stale and eligible for recovery.
        clock:
            Injectable clock for testing. Defaults to ``datetime.now(UTC)``.
        canonical_observer:
            Optional observer that receives the canonical render model
            after it is built but before localisation. Defaults to
            ``NoopCanonicalObserver``.
        """
        if uow is None:
            raise TypeError("ReportRenderService requires uow= parameter")

        self._uow: ReportRenderUnitOfWork = uow
        self._repo: ReportRepository = uow.report_repo
        self._artifact_repo: ReportArtifactRepositoryPort | None = uow.artifact_repo
        self._storage: ArtifactStoragePort = storage  # type: ignore[assignment]
        self._template_repo = template_repo
        self._stale_claim_seconds = stale_claim_seconds
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))
        self._waiter = idempotency_waiter or DatabaseIdempotencyWaiter(
            repo=self._repo,
            artifact_repo=self._artifact_repo,
            session_factory=uow.session_factory,
        )
        self._canonical_observer = canonical_observer or NoopCanonicalObserver()

    # ------------------------------------------------------------------
    # P0-9: Two-phase cleanup executor
    # ------------------------------------------------------------------

    def _execute_pending_cleanup(self) -> None:
        """Execute pending cleanup debts (Phase 2 of two-phase cleanup).

        Called after the DB transaction commits successfully.  If this
        method crashes, the pending debts remain in the database and will
        be processed on the next call (either via ``render()`` or an
        explicit ``run_cleanup_executor()`` call).

        Each debt is processed independently:
        1. CAS: pending/retryable -> processing (with locking)
        2. reclaim_delete the file using the reclaim_delete API
        3. Mark debt as completed or retryable

        The CAS ensures that if two executors run concurrently, only
        one processes each debt.
        """
        debts = self._repo.list_eligible_cleanup_debts()
        for debt in debts:
            debt_id: str = str(debt.get("id", ""))
            # Extract observed lease params for CAS
            locked_at: datetime | None = debt.get("locked_at")  # type: ignore[assignment]
            locked_by = str(debt.get("locked_by", ""))
            lock_expires_at: datetime | None = debt.get("lock_expires_at")  # type: ignore[assignment]
            status = str(debt.get("status", ""))
            # For pending/retryable debts, pass None/empty observed lease params.
            # For expired processing debts, pass actual values for CAS.
            if status in ("pending", "retryable"):
                claimed = self._repo.claim_cleanup_debt(
                    debt_id,
                    observed_locked_at=None,
                    observed_locked_by="",
                    observed_lock_expires_at=None,
                )
            else:
                claimed = self._repo.claim_cleanup_debt(
                    debt_id,
                    observed_locked_at=locked_at,
                    observed_locked_by=locked_by,
                    observed_lock_expires_at=lock_expires_at,
                )
            if not claimed:
                # Another executor already claimed it
                continue
            # Commit the claim so it's visible to other sessions
            self._repo.commit()
            try:
                sk: str = str(debt.get("storage_key", ""))
                stale_tok: str = str(debt.get("stale_claim_token", ""))
                stale_ver: int = int(str(debt.get("stale_claim_version", 0)))
                reclaim_tok: str = str(debt.get("reclaim_token", ""))
                reclaim_ver: int = int(str(debt.get("reclaim_version", 0)))
                claim_ver: int = int(str(debt.get("claim_version", 0)))
                self._storage.reclaim_delete(
                    sk,
                    stale_claim_token=stale_tok,
                    stale_claim_version=stale_ver,
                    reclaim_token=reclaim_tok,
                    reclaim_version=reclaim_ver,
                    missing_is_success=True,
                    repository=self._repo,
                )
                self._repo.mark_cleanup_completed(
                    debt_id,
                    observed_claim_version=claim_ver + 1,
                )
                self._repo.commit()
            except Exception as exc:
                error_msg = f"{type(exc).__name__}: {exc}"
                try:
                    self._repo.mark_cleanup_retryable(debt_id, error_msg)
                    self._repo.commit()
                except Exception:
                    import logging as _logging

                    _logging.getLogger(__name__).warning(
                        "Failed to mark cleanup debt %s as retryable",
                        debt_id,
                        exc_info=True,
                    )

    def run_cleanup_executor(self) -> int:
        """Explicitly run the cleanup executor on all pending debts.

        This is the public API for running cleanup outside of the
        render flow (e.g., on startup or via a background job).

        Returns the number of debts processed.
        """
        pending = self._repo.count_eligible_cleanup_debts()
        if pending:
            self._execute_pending_cleanup()
        return pending

    def render(
        self,
        *,
        report_id: str,
        revision_number: int,
        format: str,  # noqa: A002
        template_version: str | None,
        mode: str,  # noqa: A002
        actor: str,
        idempotency_key: str | None = None,
        locale: ReportLocale,
    ) -> ReportExportArtifact:
        """Render a report revision to DOCX or PDF.

        Parameters
        ----------
        report_id:
            Report identifier.
        revision_number:
            Revision number to render.
        format:
            Output format: "docx" or "pdf".
        template_version:
            Specific template version, or None for active.
        mode:
            Render mode: "draft" or "formal".
        actor:
            Actor performing the render (must be report owner).
        idempotency_key:
            Optional idempotency key for deduplication.

        Returns
        -------
        ReportExportArtifact
            The completed export artifact.

        Raises
        ------
        ReportNotFoundError
            If the report or revision is not found.
        ExportPermissionError
            If the report status is not valid for the requested mode.
        RenderError
            If rendering fails.
        """
        export_format = ExportFormat(format)
        render_mode = RenderMode(mode)

        # 1. Load the report (owner isolation check)
        report = self._repo.get_report(report_id)
        if report is None:
            raise ReportNotFoundError(report_id)
        if report.created_by != actor:
            raise ReportNotFoundError(report_id)

        # 2. Load the specific revision
        revision = self._repo.get_revision(report_id, revision_number)
        if revision is None:
            raise ReportNotFoundError(f"{report_id}/rev/{revision_number}")

        # 3. Validate draft/formal rules (P0-5)
        self._validate_export_mode(report, render_mode, revision)

        # 4. Find the active template (or specific version) for locale
        template = self._find_template(
            export_format,
            template_version,
            locale=locale,
            report_type=report.report_type.value,
            schema_version=revision.schema_version,
        )

        # P0-1: Build ApprovalSnapshot from Report fields for render model
        approval_snapshot = ApprovalSnapshot.from_report_and_revision(report, revision)

        # 5. Build render model: canonical → localized (two-stage pipeline)
        from cold_storage.modules.reports.application.canonical_render_model_builder import (
            build_canonical_render_model,
        )
        from cold_storage.modules.reports.application.render_model_localizer import (
            localize_render_model,
        )

        canonical_model = build_canonical_render_model(
            content=revision.content_json,
            report_id=revision.report_id,
            revision_number=revision.revision_number,
            content_hash=revision.content_hash,
            generated_by=revision.generated_by,
            generated_at=revision.generated_at.isoformat()
            if hasattr(revision.generated_at, "isoformat")
            else str(revision.generated_at),
            template_code=template.template_code,
            template_version=template.version,
            approval_snapshot=approval_snapshot,
        )

        # Notify canonical observer (used by tests to capture snapshots)
        self._canonical_observer.record(
            artifact_id="",  # filled in after artifact creation below
            locale=locale.value,
            format=export_format.value,
            canonical=canonical_model,
        )

        render_model = localize_render_model(
            canonical_model,
            locale=locale,
            template_manifest_json=template.manifest_json,
            format=export_format.value,
        )

        # 6. Idempotency check (P0-6) — atomic claim via idempotency_records
        template_id = template.id
        template_version_str = template.version
        template_content_hash = template.template_content_hash
        fingerprint = ""
        claim_token: str = ""
        claim_version: int = 0

        # Compute locale-aware fingerprint components (always, not just for idempotency)
        from cold_storage.modules.reports.localization.catalog import (
            compute_catalog_content_hash as _catalog_hash,
        )
        from cold_storage.modules.reports.localization.catalog import (
            get_catalog as _get_catalog,
        )

        report_locale = locale  # Already ReportLocale
        template_locale = (
            template.locale
            if isinstance(template.locale, ReportLocale)
            else ReportLocale(template.locale)
        )

        # Section I: Validate template locale matches requested locale
        if template_locale != report_locale:
            raise TemplateNotFoundError(
                f"Template locale {template_locale.value} does not match "
                f"requested locale {report_locale.value}"
            )

        catalog = _get_catalog(report_locale)
        translation_catalog_version = catalog.version
        translation_catalog_content_hash = _catalog_hash(report_locale)
        localized_content_str = (
            json.dumps(template.manifest_json, sort_keys=True, separators=(",", ":"))
            + ":"
            + report_locale.value
            + ":"
            + translation_catalog_version
            + ":"
            + translation_catalog_content_hash
        )
        localized_template_content_hash = hashlib.sha256(localized_content_str.encode()).hexdigest()

        if idempotency_key:
            fingerprint = _compute_fingerprint(
                actor=actor,
                report_id=report_id,
                revision_number=revision_number,
                source_content_hash=revision.content_hash,
                format=format,
                render_mode=mode,
                template_id=template_id,
                template_version=template_version_str,
                template_content_hash=template_content_hash,
                locale=report_locale.value,
                translation_catalog_version=translation_catalog_version,
                localized_template_content_hash=localized_template_content_hash,
            )

            # Attempt atomic claim via idempotency_records table
            try:
                claim_token, claim_version = self._repo.save_idempotency_record(
                    key=idempotency_key,
                    actor=actor,
                    action="render",
                    fingerprint=fingerprint,
                )
                self._uow.commit()
            except Exception:
                self._uow.rollback()
                # Record exists — verify same fingerprint
                existing = self._repo.get_idempotency_record(idempotency_key)
                if existing is None:
                    raise
                if existing["fingerprint"] != fingerprint:
                    raise IdempotencyPayloadConflictError(idempotency_key) from None
                # Same fingerprint — return existing completed artifact if available
                if existing["status"] == "completed" and existing.get("result_payload"):
                    payload = existing["result_payload"]
                    if (
                        isinstance(payload, dict)
                        and "artifact_id" in payload
                        and self._artifact_repo is not None
                    ):
                        completed = self._artifact_repo.get_artifact(payload["artifact_id"])
                        if completed and completed.status == ArtifactStatus.COMPLETED:
                            return completed
                # P0-2: Allow retry if previously failed — delete and re-claim
                if existing["status"] == "failed":
                    self._repo.reset_failed_idempotency(idempotency_key)
                    self._uow.commit()
                    claim_token, claim_version = self._repo.save_idempotency_record(
                        key=idempotency_key,
                        actor=actor,
                        action="render",
                        fingerprint=fingerprint,
                    )
                    self._uow.commit()
                    # Fall through — render will proceed
                elif existing["status"] in ("claimed", "running"):
                    # Stale-claim recovery: if the claim is older than
                    # the threshold, atomically CAS-reclaim it and
                    # cleanup orphaned non-terminal artifacts.
                    claimed_at = existing.get("claimed_at")
                    if claimed_at is not None:
                        cutoff = self._clock() - timedelta(seconds=self._stale_claim_seconds)
                        if hasattr(claimed_at, "replace"):
                            _claimed = claimed_at
                        else:
                            _claimed = datetime.fromisoformat(str(claimed_at))
                        # Normalize: strip tzinfo if claimed_at is naive
                        # (SQLite stores naive datetimes)
                        if _claimed.tzinfo is None and cutoff.tzinfo is not None:
                            cutoff = cutoff.replace(tzinfo=None)
                        if _claimed < cutoff:
                            # Pass naive cutoff for SQLite compatibility
                            sql_cutoff = (
                                cutoff.replace(tzinfo=None) if cutoff.tzinfo is not None else cutoff
                            )
                            stale_claim_token = str(existing.get("claim_token", ""))
                            stale_claim_version = existing.get("claim_version", 0)
                            reclaimed, new_token, new_version = (
                                self._repo.reclaim_stale_idempotency(
                                    idempotency_key,
                                    fingerprint,
                                    sql_cutoff,
                                    original_claimed_at=claimed_at,
                                    old_claim_token=stale_claim_token,
                                    old_claim_version=stale_claim_version,
                                )
                            )
                            if reclaimed:
                                assert new_token is not None
                                assert new_version is not None
                                claim_token = new_token
                                claim_version = new_version
                                # Cleanup orphaned non-terminal artifacts
                                if self._artifact_repo is not None:
                                    _, stale_storage_keys = (
                                        self._artifact_repo.fail_nonterminal_artifacts(
                                            report_id,
                                            idempotency_key=idempotency_key,
                                            stale_claim_token=stale_claim_token,
                                            stale_claim_version=stale_claim_version,
                                        )
                                    )
                                # Two-phase cleanup (P0-9):
                                # Phase 1: Record cleanup_debt in the same transaction.
                                # Phase 2: Execute file deletions after commit.
                                for sk in stale_storage_keys:
                                    self._repo.insert_cleanup_debt(
                                        idempotency_key=idempotency_key,
                                        storage_key=sk,
                                        stale_claim_token=stale_claim_token,
                                        stale_claim_version=stale_claim_version,
                                        reclaim_token=claim_token,
                                        reclaim_version=claim_version,
                                    )
                                self._uow.commit()
                                # Phase 2: Execute cleanup after commit succeeds.
                                # If this crashes, the cleanup_debt remains
                                # pending and will be processed on the next run.
                                self._execute_pending_cleanup()
                                # Fall through — render will proceed
                            else:
                                # CAS failed — re-read current state
                                existing = self._repo.get_idempotency_record(idempotency_key)
                                if (
                                    existing is not None
                                    and existing["status"] == "completed"
                                    and existing.get("result_payload")
                                ):
                                    payload = existing["result_payload"]
                                    if (
                                        isinstance(payload, dict)
                                        and "artifact_id" in payload
                                        and self._artifact_repo is not None
                                    ):
                                        c = self._artifact_repo.get_artifact(payload["artifact_id"])
                                        if c and c.status == ArtifactStatus.COMPLETED:
                                            return c
                                return self._resolve_idempotency_conflict(
                                    idempotency_key,
                                    fingerprint,
                                    report_id=report_id,
                                    revision_number=revision_number,
                                )
                        else:
                            # Not stale — another render in progress
                            return self._resolve_idempotency_conflict(
                                idempotency_key,
                                fingerprint,
                                report_id=report_id,
                                revision_number=revision_number,
                            )
                    else:
                        # No claimed_at — legacy record, treat as non-stale
                        return self._resolve_idempotency_conflict(
                            idempotency_key,
                            fingerprint,
                            report_id=report_id,
                            revision_number=revision_number,
                        )
                else:
                    # Unknown status
                    return self._resolve_idempotency_conflict(
                        idempotency_key,
                        fingerprint,
                        report_id=report_id,
                        revision_number=revision_number,
                    )

        # 7. Create pending artifact
        file_ext = "docx" if export_format == ExportFormat.DOCX else "pdf"
        mime_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if export_format == ExportFormat.DOCX
            else "application/pdf"
        )
        file_name = f"report_{report_id}_rev{revision_number}.{file_ext}"

        artifact = ReportExportArtifact.create(
            report_id=report_id,
            report_revision_id=revision.id,
            revision_number=revision_number,
            format=export_format,
            template_id=template_id,
            template_version=template_version_str,
            schema_version=revision.schema_version,
            file_name=file_name,
            mime_type=mime_type,
            source_content_hash=revision.content_hash,
            generated_by=actor,
            idempotency_key=idempotency_key,
            claim_token=claim_token if claim_token else None,
            claim_version=claim_version,
            locale=report_locale,
            template_locale=template_locale,
            translation_catalog_version=translation_catalog_version,
            translation_catalog_content_hash=translation_catalog_content_hash,
            localized_template_content_hash=localized_template_content_hash,
        )

        # P0-2: Unified failure handler for ALL artifact persistence stages.
        # Covers: insert pending → commit, update rendering → commit,
        #         render, finalize, update completed + complete idempotency.
        # If ANY stage fails → rollback, re-read, update to failed, fail
        # idempotency, commit, structured log.
        temp_path: str | None = None
        storage_key: str = ""
        current_stage = "init"
        try:
            # P0-2: INSERT artifact(pending) → commit
            current_stage = "insert_pending"
            if self._artifact_repo:
                if idempotency_key and claim_token:
                    self._artifact_repo.insert_artifact_with_claim(
                        artifact,
                        claim_token=claim_token,
                        claim_version=claim_version,
                    )
                else:
                    self._artifact_repo.save_artifact(artifact)
                self._uow.commit()

            # P0-2: UPDATE artifact(rendering) → commit
            current_stage = "update_rendering"
            if self._artifact_repo:
                # Atomic transition: pending → rendering with claim fencing
                artifact = replace(artifact, status=ArtifactStatus.RENDERING)
                if idempotency_key and claim_token:
                    self._artifact_repo.transition_artifact(
                        artifact,
                        expected_status=ArtifactStatus.PENDING,
                        claim_token=claim_token,
                        claim_version=claim_version,
                    )
                else:
                    self._artifact_repo.update_artifact(artifact)
                self._uow.commit()

            # 8. Render via DocxRenderer or PdfRenderer
            current_stage = "render"
            rendered_bytes = self._render_bytes(
                export_format,
                render_model,
                template,
                is_draft=(render_mode == RenderMode.DRAFT),
            )

            # 9. Compute file SHA-256
            file_sha256 = hashlib.sha256(rendered_bytes).hexdigest()

            # 10. Save to temp file first, then finalize (P0-7)
            current_stage = "finalize"
            temp_path, temp_sha256 = self._storage.put_temp(rendered_bytes, file_name)

            # Verify temp file hash matches
            if temp_sha256 != file_sha256:
                self._storage.cleanup_temp(temp_path)
                raise RenderError(f"SHA-256 mismatch: expected {file_sha256}, got {temp_sha256}")

            # Move to final location
            storage_key = self._storage.finalize_temp(
                temp_path,
                artifact.id,
                file_name,
                claim_token=claim_token,
                claim_version=claim_version,
            )
            temp_path = None  # Successfully finalized

            # Build real manifest metadata (P0-4) using same ApprovalSnapshot
            render_manifest = self._build_render_manifest(
                export_format=export_format,
                render_mode=render_mode,
                template_id=template_id,
                template_version=template_version_str,
                template_content_hash=template_content_hash,
                source_content_hash=revision.content_hash,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint if idempotency_key else "",
                render_settings=render_model.manifest.render_settings
                if hasattr(render_model.manifest, "render_settings")
                else {},
                approval_snapshot=approval_snapshot,
                locale=report_locale.value,
                translation_catalog_version=translation_catalog_version,
                translation_catalog_content_hash=translation_catalog_content_hash,
                localized_template_content_hash=localized_template_content_hash,
            )

            # 11. Update artifact with storage_key, file_size, file_sha256, status=completed
            current_stage = "update_completed"
            artifact = replace(
                artifact,
                status=ArtifactStatus.COMPLETED,
                storage_key=storage_key,
                file_size_bytes=len(rendered_bytes),
                file_sha256=file_sha256,
                render_manifest_json=render_manifest,
            )

            # P0-2: UPDATE artifact(completed) + complete idempotency → single commit
            if self._artifact_repo:
                if idempotency_key and claim_token:
                    self._artifact_repo.transition_artifact(
                        artifact,
                        expected_status=ArtifactStatus.RENDERING,
                        claim_token=claim_token,
                        claim_version=claim_version,
                    )
                else:
                    self._artifact_repo.update_artifact(artifact)
            if idempotency_key:
                self._repo.complete_idempotency_record(
                    key=idempotency_key,
                    result_payload={"artifact_id": artifact.id},
                    claim_token=claim_token,
                    claim_version=claim_version,
                )
            if self._artifact_repo:
                self._uow.commit()

            # Notify any waiter that the idempotent render completed
            if self._waiter is not None and idempotency_key:
                self._waiter.notify_completed(idempotency_key, artifact.id)

            return artifact

        except Exception as exc:
            logger = logging.getLogger(__name__)
            logger.error(
                "Artifact persistence failure",
                extra={
                    "artifact_id": artifact.id,
                    "idempotency_key": idempotency_key or "",
                    "stage": current_stage,
                    "exception": str(exc),
                },
                exc_info=True,
            )

            # Cleanup temp file if still present
            if temp_path is not None:
                try:
                    self._storage.cleanup_temp(temp_path)
                except Exception as cleanup_exc:
                    logger.warning(
                        "Failed to clean up temp file after artifact failure",
                        extra={
                            "artifact_id": artifact.id,
                            "storage_key": storage_key,
                            "idempotency_key": idempotency_key or "",
                            "stage": current_stage,
                            "exception": str(cleanup_exc),
                        },
                    )

            # Clean up finalized storage if it exists
            if storage_key:
                try:
                    self._storage.delete(
                        storage_key, claim_token=claim_token, claim_version=claim_version
                    )
                except Exception as cleanup_exc:
                    logger.warning(
                        "Failed to clean up storage after artifact failure",
                        extra={
                            "artifact_id": artifact.id,
                            "storage_key": storage_key,
                            "idempotency_key": idempotency_key or "",
                            "stage": current_stage,
                            "exception": str(cleanup_exc),
                        },
                    )

            # P0-2: Persist failure state — rollback, atomic fail attempt
            if self._artifact_repo:
                try:
                    self._uow.rollback()
                    if idempotency_key:
                        # Atomic: fail idempotency + fail artifact in one transaction
                        self._artifact_repo.fail_attempt_with_claim(
                            artifact_id=artifact.id,
                            idempotency_key=idempotency_key,
                            claim_token=claim_token,
                            claim_version=claim_version,
                            failure_code=type(exc).__name__,
                            failure_message=str(exc),
                        )
                    else:
                        # No idempotency — update artifact directly
                        failed_artifact = self._artifact_repo.get_artifact(artifact.id)
                        if failed_artifact is not None:
                            from dataclasses import is_dataclass as _is_dc

                            if _is_dc(failed_artifact):
                                failed_artifact = replace(
                                    failed_artifact,
                                    status=ArtifactStatus.FAILED,
                                    failure_code=type(exc).__name__,
                                    failure_message=str(exc),
                                )
                            self._artifact_repo.update_artifact(failed_artifact)
                    self._uow.commit()
                    # Notify any waiter that the idempotent render failed
                    if self._waiter is not None and idempotency_key:
                        self._waiter.notify_failed(idempotency_key, exc)
                except Exception:
                    import contextlib

                    with contextlib.suppress(Exception):
                        self._uow.rollback()
                    logger.error(
                        "Failed to persist failed artifact state",
                        extra={
                            "artifact_id": artifact.id,
                            "idempotency_key": idempotency_key or "",
                            "stage": current_stage,
                        },
                        exc_info=True,
                    )

            raise RenderError(f"Rendering failed: {exc}") from exc

    def _resolve_idempotency_conflict(
        self,
        key: str,
        expected_fingerprint: str = "",
        *,
        report_id: str = "",
        revision_number: int = 0,
    ) -> ReportExportArtifact:
        """Wait for a concurrent render on the same idempotency key to complete.

        Delegates to the configured ``IdempotencyWaiterPort`` with the
        stale-claim deadline and the caller's fingerprint for validation.
        """
        if self._waiter is not None:
            deadline = time.monotonic() + self._stale_claim_seconds
            result = self._waiter.wait_for_completion(
                key,
                expected_fingerprint,
                deadline,
                expected_report_id=report_id,
                expected_revision_number=revision_number,
            )
            if result is not None:
                return result
        raise IdempotencyClaimError(key)

    def _build_render_manifest(
        self,
        *,
        export_format: ExportFormat,
        render_mode: RenderMode,
        template_id: str,
        template_version: str,
        template_content_hash: str,
        source_content_hash: str,
        idempotency_key: str | None,
        fingerprint: str,
        render_settings: JsonObject,
        approval_snapshot: ApprovalSnapshot | None = None,
        locale: str = "zh-CN",
        translation_catalog_version: str = "",
        translation_catalog_content_hash: str = "",
        localized_template_content_hash: str = "",
    ) -> dict[str, Any]:
        """Build the render manifest with real metadata (P0-4).

        P0-1: Uses the same ApprovalSnapshot object that was passed to the
        render model, ensuring section content and manifest are consistent.
        """
        return {
            "export_format": export_format.value,
            "render_mode": render_mode.value,
            "template_id": template_id,
            "template_version": template_version,
            "template_content_hash": template_content_hash,
            "source_content_hash": source_content_hash,
            "renderer_name": "cold_storage_renderer",
            "renderer_version": "1.0.0",
            "render_settings": render_settings,
            "idempotency_key": idempotency_key or "",
            "fingerprint": fingerprint,
            "approved_revision_id": (approval_snapshot.revision_id if approval_snapshot else ""),
            "approved_content_hash": (approval_snapshot.content_hash if approval_snapshot else ""),
            "approved_by": (approval_snapshot.approved_by if approval_snapshot else ""),
            "approved_at": (approval_snapshot.approved_at if approval_snapshot else ""),
            "approved_revision_number": (
                approval_snapshot.revision_number if approval_snapshot else 0
            ),
            "locale": locale,
            "translation_catalog_version": translation_catalog_version,
            "translation_catalog_content_hash": translation_catalog_content_hash,
            "localized_template_content_hash": localized_template_content_hash,
        }

    def _validate_export_mode(
        self,
        report: Report,
        mode: RenderMode,
        revision: ReportRevision,
    ) -> None:
        """Validate that the report status allows the requested export mode.

        P0-4/P0-5: For formal mode, verify the revision being exported is the
        APPROVED revision (quality_status == APPROVED and latest revision).
        """
        allowed = (
            DRAFT_EXPORT_STATUSES
            if mode == RenderMode.DRAFT
            else FORMAL_EXPORT_STATUSES
            if mode == RenderMode.FORMAL
            else frozenset()
        )
        if report.status not in allowed:
            raise ExportPermissionError(report.id, mode.value, report.status.value)

        # P0-4/P0-5: Formal mode requires exporting the latest/approved revision
        if mode == RenderMode.FORMAL:
            # P0-8: Must have all approval fields for formal export
            missing = []
            if not report.approved_revision_id:
                missing.append("approved_revision_id")
            if not report.approved_content_hash:
                missing.append("approved_content_hash")
            if not report.approved_by:
                missing.append("approved_by")
            if not report.approved_at:
                missing.append("approved_at")
            if missing:
                raise ExportPermissionError(
                    report.id,
                    mode.value,
                    f"Missing approval fields: {', '.join(missing)}",
                )
            # Verify revision matches approval
            if revision.id != report.approved_revision_id:
                raise ExportPermissionError(
                    report.id,
                    mode.value,
                    "Approved revision mismatch",
                )
            if revision.content_hash != report.approved_content_hash:
                raise ExportPermissionError(
                    report.id,
                    mode.value,
                    "Approved content hash mismatch",
                )
            if revision.revision_number != report.current_revision_number:
                raise ExportPermissionError(
                    report.id,
                    mode.value,
                    f"Formal export requires latest revision ({report.current_revision_number}), "
                    f"got {revision.revision_number}",
                )
            # P0-8: Block formal export if blocking quality findings exist
            if revision.quality_findings_json:
                blockers = [
                    f
                    for f in revision.quality_findings_json
                    if isinstance(f, dict) and f.get("severity") == "blocking"
                ]
                if blockers:
                    raise ExportPermissionError(
                        report.id,
                        mode.value,
                        f"Revision has {len(blockers)} blocking findings",
                    )

    def _find_template(
        self,
        format: ExportFormat,
        template_version: str | None,  # noqa: A002
        *,
        locale: ReportLocale,
        report_type: str | None = None,
        schema_version: str | None = None,
    ) -> ReportTemplate:
        """Find the active template or specific version for a given locale.

        Section IV: Validates that the template matches:
        - template_code == cold_storage_concept_design
        - report_type matches (if provided)
        - schema_version matches (if provided)
        - format matches
        - locale matches
        - status == ACTIVE
        - version matches (if specified)

        Raises
        ------
        TemplateNotFoundError
            If no matching template is found.
        """
        if self._template_repo is None:
            raise TemplateNotFoundError("No template repository configured")

        if template_version:
            # Find by version — only ACTIVE templates with matching locale
            templates = self._template_repo.list_templates(format=format)
            for t in templates:
                if t.version != template_version:
                    continue
                if t.status != TemplateStatus.ACTIVE:
                    continue
                if t.locale != locale:
                    continue
                # Section IV: validate report_type and schema_version
                if report_type and t.report_type.value != report_type:
                    continue
                if schema_version and t.schema_version != schema_version:
                    continue
                return t
            raise TemplateNotFoundError(
                f"Template version {template_version} not found or not active "
                f"for format {format.value} / locale {locale.value}"
            )

        # Find active template for locale
        result = self._template_repo.get_active_template(
            template_code="cold_storage_concept_design",
            format=format,
            locale=locale,
        )
        if result is None:
            raise TemplateNotFoundError(
                f"No active template for cold_storage_concept_design / "
                f"{format.value} / {locale.value}"
            )

        # Section IV: validate report_type and schema_version
        if report_type and result.report_type.value != report_type:
            raise TemplateNotFoundError(
                f"Active template report_type {result.report_type.value} "
                f"does not match requested {report_type}"
            )
        if schema_version and result.schema_version != schema_version:
            raise TemplateNotFoundError(
                f"Active template schema_version {result.schema_version} "
                f"does not match requested {schema_version}"
            )
        return result

    def _render_bytes(
        self,
        format: ExportFormat,  # noqa: A002
        render_model: LocalizedReportRenderModel,
        template: ReportTemplate | None,
        *,
        is_draft: bool = False,
    ) -> bytes:
        """Render the model to bytes using the appropriate renderer.

        P0-4: Pass is_draft flag to renderer.
        """
        if format == ExportFormat.DOCX:
            from cold_storage.modules.reports.renderers.docx_renderer import (
                DocxRenderer,
            )

            docx_renderer = DocxRenderer()
            return docx_renderer.render(render_model, is_draft=is_draft)
        elif format == ExportFormat.PDF:
            from cold_storage.modules.reports.renderers.pdf_renderer import (
                PdfRenderer,
            )

            pdf_renderer = PdfRenderer()
            return pdf_renderer.render(render_model, is_draft=is_draft)
        else:
            raise RenderError(f"Unsupported format: {format}")

    # --- Query methods ---

    def get_artifact(self, report_id: str, artifact_id: str, actor: str) -> ReportExportArtifact:
        """Get an export artifact by ID."""
        # Owner isolation check
        report = self._repo.get_report(report_id)
        if report is None:
            raise ReportNotFoundError(report_id)
        if report.created_by != actor:
            raise ReportNotFoundError(report_id)

        if self._artifact_repo is None:
            raise ArtifactNotFoundError(artifact_id)

        artifact = self._artifact_repo.get_artifact(artifact_id)
        if artifact is None or artifact.report_id != report_id:
            raise ArtifactNotFoundError(artifact_id)

        return artifact

    def list_artifacts(
        self,
        report_id: str,
        actor: str,
        locale: ReportLocale | None = None,
    ) -> list[ReportExportArtifact]:
        """List all export artifacts for a report, optionally filtered by locale."""
        # Owner isolation check
        report = self._repo.get_report(report_id)
        if report is None:
            raise ReportNotFoundError(report_id)
        if report.created_by != actor:
            raise ReportNotFoundError(report_id)

        if self._artifact_repo is None:
            return []

        return self._artifact_repo.list_artifacts(report_id, locale=locale)

    def verify_download(
        self,
        report_id: str,
        artifact_id: str,
        actor: str,
    ) -> ReportExportArtifact:
        """Verify download safety (P0-8).

        Checks:
        1. Artifact belongs to the report
        2. Actor has permission
        3. Status is COMPLETED
        4. storage_key is non-empty
        5. File exists on disk
        6. File size matches database
        7. SHA-256 matches database

        Returns
        -------
        ReportExportArtifact
            The verified artifact.

        Raises
        ------
        ReportNotFoundError
            If the report is not found or actor has no access.
        ArtifactNotFoundError
            If the artifact is not found or doesn't belong to the report.
        ArtifactNotReadyError
            If the artifact is not in completed state.
        ArtifactFileNotFoundError
            If the artifact file does not exist on disk.
        ArtifactIntegrityError
            If file size or SHA-256 does not match database.
        PathTraversalError
            If the storage_key contains path traversal characters.
        """
        # 1 & 2: Get artifact with permission check
        artifact = self.get_artifact(report_id, artifact_id, actor)

        # 3: Status must be COMPLETED
        if artifact.status != ArtifactStatus.COMPLETED:
            raise ArtifactNotReadyError(artifact_id, artifact.status.value)

        # 4: storage_key must be non-empty
        if not artifact.storage_key:
            raise ArtifactFileNotFoundError(artifact_id, "<no storage key>")

        # 5: File exists on disk — let PathTraversalError pass through
        try:
            file_path = self._storage.get_path(artifact.storage_key)
        except FileNotFoundError:
            raise ArtifactFileNotFoundError(artifact_id, artifact.storage_key) from None

        path = Path(file_path)
        if not path.is_file():
            raise ArtifactFileNotFoundError(artifact_id, file_path)

        # 6: File size matches database
        actual_size = path.stat().st_size
        if actual_size != artifact.file_size_bytes:
            raise ArtifactIntegrityError(
                artifact_id,
                f"File size mismatch: expected {artifact.file_size_bytes}, got {actual_size}",
            )

        # 7: SHA-256 matches database
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        actual_hash = sha256.hexdigest()
        if actual_hash != artifact.file_sha256:
            raise ArtifactIntegrityError(
                artifact_id,
                f"SHA-256 mismatch: expected {artifact.file_sha256}, got {actual_hash}",
            )

        return artifact

    def get_artifact_path(self, storage_key: str) -> str:
        """Get the file path for an artifact download."""
        return str(self._storage.get_path(storage_key))
