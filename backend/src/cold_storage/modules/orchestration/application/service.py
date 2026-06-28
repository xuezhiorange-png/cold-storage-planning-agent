"""Orchestration preflight application service.

Implements the request validation and preflight gate from approved
design §9.  This phase validates the incoming command, loads and
cross-checks the authoritative ProjectVersion, and maps every
rejection cause to a typed ``PreflightFailure``.

A rejected request is atomically persisted together with a
request-level audit outbox event.  No identity, attempt, calculation,
or source binding is created during preflight.

The service receives preflight port abstractions so that snapshot-schema
and coefficient-resolution validation can be injected by later sub-tasks
(and by test doubles in the current phase).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from cold_storage.modules.orchestration.application.ports import (
    CoefficientResolutionPreflightPort,
    ExecutionSnapshotPreflightPort,
)
from cold_storage.modules.orchestration.domain.contracts import (
    OrchestrationRequestCommand,
    PreflightFailure,
    RequestStatus,
)
from cold_storage.modules.orchestration.domain.errors import (
    OrchestrationDomainError,
    OrchestrationRequestIdentityError,
    ProjectVersionArchivedError,
    ProjectVersionNotFoundError,
    ProjectVersionNotReadyError,
    ProjectVersionProjectMismatchError,
    ProjectVersionStatusInvalidError,
)
from cold_storage.modules.orchestration.domain.fingerprint import result_hash
from cold_storage.modules.orchestration.infrastructure.repositories import (
    AuditOutboxRepository,
    OrchestrationRequestRepository,
)

# ── ProjectVersion loading port ─────────────────────────────────────────────


class ProjectVersionReadPort(Protocol):
    """Read-only port for loading ProjectVersion and its status."""

    def load_by_id(self, session: Session, project_version_id: str) -> _LoadedVersion | None:
        """Return the loaded record or None when not found."""
        ...


class _LoadedVersion:
    """Value object returned by ``ProjectVersionReadPort.load_by_id``."""

    __slots__ = ("project_id", "status")

    def __init__(self, project_id: str, status: str) -> None:
        self.project_id = project_id
        self.status = status


# ── Unit-of-Work boundary ───────────────────────────────────────────────────


class _UoWProtocol(Protocol):
    """Minimal unit-of-work protocol consumed by the preflight service."""

    session: Session

    def begin(self) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


# ── Preflight accepted result ───────────────────────────────────────────────


class PreflightAccepted:
    """Result returned when preflight validation passes."""

    __slots__ = ("request_id", "fingerprint")

    def __init__(self, request_id: str, fingerprint: str) -> None:
        self.request_id = request_id
        self.fingerprint = fingerprint


# ── Service ─────────────────────────────────────────────────────────────────


class OrchestrationPreflightService:
    """Validates an orchestration request before identity/attempt creation.

    Every invocation creates a new ``PENDING`` request record.  If any
    preflight check fails the request is atomically transitioned to
    ``PREFLIGHT_REJECTED`` together with a request-level outbox event.

    The service does NOT create identity, attempt, calculation, or binding
    records — those belong to later execution phases.

    Instance state:
        ``_current_request_id`` is set during ``_preflight()`` and read
        by the rejection path to avoid querying the session (which may
        be a mock in tests).
    """

    def __init__(
        self,
        *,
        request_repo: OrchestrationRequestRepository,
        outbox_repo: AuditOutboxRepository,
        version_port: ProjectVersionReadPort,
        snapshot_port: ExecutionSnapshotPreflightPort,
        coefficient_port: CoefficientResolutionPreflightPort,
    ) -> None:
        self._request_repo = request_repo
        self._outbox_repo = outbox_repo
        self._version_port = version_port
        self._snapshot_port = snapshot_port
        self._coefficient_port = coefficient_port
        self._current_request_id: str | None = None

    # ── Public entry point ──────────────────────────────────────────────

    def preflight_and_persist(
        self,
        command: OrchestrationRequestCommand,
        uow: _UoWProtocol,
    ) -> PreflightAccepted:
        """Run full preflight with transactional rejection support.

        On success returns ``PreflightAccepted``.
        On failure persists the rejection atomically and raises
        ``PreflightFailure`` — the caller MUST NOT catch it.
        """
        try:
            result = self._preflight(command, uow.session)
            uow.commit()
            return result
        except OrchestrationDomainError as exc:
            # Use the request_id captured during _preflight().
            # If no request was created (identity validation failed
            # before add()), create a fallback request now.
            request_id = self._current_request_id
            if not request_id:
                request_id = self._create_request(command, uow.session)
                self._current_request_id = request_id
            self._persist_rejection(uow.session, request_id, exc)
            uow.commit()
            raise PreflightFailure(
                request_id=request_id,
                project_id=command.project_id,
                project_version_id=command.project_version_id,
                error_class=type(exc).__name__,
                code=exc.code,
                field=exc.field,
                details=exc.details,
                occurred_at=datetime.now(UTC),
            ) from exc
        except Exception:
            uow.rollback()
            raise
        finally:
            self._current_request_id = None

    # ── Core preflight logic ────────────────────────────────────────────

    def _preflight(
        self,
        command: OrchestrationRequestCommand,
        session: Session,
    ) -> PreflightAccepted:
        # 1 – Validate request identity (fail-fast: no request created yet)
        _validate_command_identity(command)

        # 2 – Compute deterministic fingerprint
        fingerprint = _compute_request_fingerprint(command)

        # 3 – Create PENDING request
        request_id = self._request_repo.add(
            session,
            project_id=command.project_id,
            project_version_id=command.project_version_id,
            request_fingerprint=fingerprint,
            actor=command.actor,
            correlation_id=command.correlation_id,
        )
        self._current_request_id = request_id

        # 4 – Load authoritative ProjectVersion
        version = self._version_port.load_by_id(session, command.project_version_id)
        if version is None:
            raise ProjectVersionNotFoundError(command.project_version_id)
        if version.project_id != command.project_id:
            raise ProjectVersionProjectMismatchError(version.project_id, command.project_id)

        status = version.status
        if status == "approved":
            pass
        elif status == "draft":
            raise ProjectVersionNotReadyError(command.project_version_id, status)
        elif status == "archived":
            raise ProjectVersionArchivedError(command.project_version_id)
        else:
            raise ProjectVersionStatusInvalidError(command.project_version_id, status)

        # 5 – Preflight ports
        self._snapshot_port.validate_candidate(
            project_id=command.project_id,
            project_version_id=command.project_version_id,
            version_status=status,
        )
        self._coefficient_port.validate_resolution(
            project_id=command.project_id,
            project_version_id=command.project_version_id,
            coefficient_resolution_context=dict(command.coefficient_resolution_context),
        )

        return PreflightAccepted(request_id, fingerprint)

    # ── Rejection persistence ───────────────────────────────────────────

    def _persist_rejection(
        self,
        session: Session,
        request_id: str,
        exc: OrchestrationDomainError,
    ) -> None:
        self._request_repo.update_status(
            session,
            request_id,
            status=RequestStatus.PREFLIGHT_REJECTED,
            failure_code=exc.code,
            failure_field=exc.field,
            failure_details=dict(exc.details),
        )
        self._outbox_repo.add(
            session,
            event_type="orchestration.request.rejected",
            aggregate_type="OrchestrationRequest",
            aggregate_id=request_id,
            payload={
                "error_class": type(exc).__name__,
                "code": exc.code,
                "field": exc.field,
                "details": dict(exc.details),
            },
            request_id=request_id,
        )

    def _create_request(
        self,
        command: OrchestrationRequestCommand,
        session: Session,
    ) -> str:
        """Create a PENDING request even when identity fields are empty."""
        fingerprint = _compute_request_fingerprint(command)
        return self._request_repo.add(
            session,
            project_id=command.project_id or "__invalid__",
            project_version_id=command.project_version_id or "__invalid__",
            request_fingerprint=fingerprint,
            actor=command.actor or "__invalid__",
            correlation_id=command.correlation_id or "__invalid__",
        )


# ── Module-level helpers ────────────────────────────────────────────────────


def _validate_command_identity(command: OrchestrationRequestCommand) -> None:
    if not command.actor or not command.actor.strip():
        raise OrchestrationRequestIdentityError(field="actor", message="Actor is required")
    if not command.correlation_id or not command.correlation_id.strip():
        raise OrchestrationRequestIdentityError(
            field="correlation_id", message="Correlation ID is required"
        )
    if not command.project_id or not command.project_id.strip():
        raise OrchestrationRequestIdentityError(
            field="project_id", message="Project ID is required"
        )
    if not command.project_version_id or not command.project_version_id.strip():
        raise OrchestrationRequestIdentityError(
            field="project_version_id", message="Project version ID is required"
        )


def _compute_request_fingerprint(command: OrchestrationRequestCommand) -> str:
    return result_hash(
        {
            "project_id": command.project_id,
            "project_version_id": command.project_version_id,
            "coefficient_resolution_context": dict(command.coefficient_resolution_context),
            "actor": command.actor,
            "correlation_id": command.correlation_id,
        }
    )
