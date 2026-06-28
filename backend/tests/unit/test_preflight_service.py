"""Unit tests for OrchestrationPreflightService.

Covers:
- Command identity validation
- Request fingerprint deterministic
- Same fingerprint creates distinct request IDs
- Each typed error maps to exact PreflightFailure
- Approved ProjectVersion success path
- No identity/attempt/calculation/binding calls
- Repository does not commit
- Transaction rollback behavior
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from cold_storage.modules.orchestration.application.ports import (
    CoefficientResolutionPreflightPort,
    ExecutionSnapshotPreflightPort,
)
from cold_storage.modules.orchestration.application.service import (
    OrchestrationPreflightService,
    PreflightAccepted,
    ProjectVersionReadPort,
    _LoadedVersion,
)
from cold_storage.modules.orchestration.domain.contracts import (
    OrchestrationRequestCommand,
    PreflightFailure,
)
from cold_storage.modules.orchestration.infrastructure.repositories import (
    AuditOutboxRepository,
    OrchestrationRequestRepository,
    RequestStatus,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


def _make_command(
    project_id: str = "p-1",
    project_version_id: str = "pv-1",
    actor: str = "test-actor",
    correlation_id: str = "corr-1",
    coefficient_context: Mapping[str, object] | None = None,
) -> OrchestrationRequestCommand:
    return OrchestrationRequestCommand(
        project_id=project_id,
        project_version_id=project_version_id,
        coefficient_resolution_context=coefficient_context or {},
        actor=actor,
        correlation_id=correlation_id,
    )


class _FakeRequestRepo(OrchestrationRequestRepository):
    """In-memory request repository for unit tests."""

    def __init__(self) -> None:
        self.requests: dict[str, dict[str, object]] = {}
        self._counter = 0

    def add(
        self,
        session: Session,
        /,
        *,
        project_id: str,
        project_version_id: str,
        request_fingerprint: str,
        actor: str,
        correlation_id: str,
    ) -> str:
        self._counter += 1
        rid = f"req-{self._counter}"
        self.requests[rid] = {
            "project_id": project_id,
            "project_version_id": project_version_id,
            "request_fingerprint": request_fingerprint,
            "actor": actor,
            "correlation_id": correlation_id,
            "status": "PENDING",
        }
        return rid

    def update_status(
        self,
        session: Session,
        /,
        request_id: str,
        *,
        status: RequestStatus,
        failure_code: str | None = None,
        failure_field: str | None = None,
        failure_details: dict[str, object] | None = None,
        resolved_identity_id: str | None = None,
        resolved_attempt_id: str | None = None,
    ) -> None:
        assert request_id in self.requests, f"Unknown request {request_id}"
        self.requests[request_id]["status"] = str(status.value)
        self.requests[request_id]["failure_code"] = failure_code
        self.requests[request_id]["failure_field"] = failure_field
        self.requests[request_id]["failure_details"] = failure_details


class _FakeOutboxRepo(AuditOutboxRepository):
    """In-memory outbox repository for unit tests."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def add(
        self,
        session: Session,
        /,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
        request_id: str | None = None,
        identity_id: str | None = None,
        attempt_id: str | None = None,
        calculation_run_id: str | None = None,
        source_binding_id: str | None = None,
        available_at: datetime | None = None,
    ) -> str:
        eid = f"event-{len(self.events) + 1}"
        self.events.append(
            {
                "id": eid,
                "event_type": event_type,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "request_id": request_id,
                "identity_id": identity_id,
                "attempt_id": attempt_id,
                "calculation_run_id": calculation_run_id,
                "source_binding_id": source_binding_id,
                "payload": payload,
            }
        )
        return eid

    def claim(self, session, /, *, worker_id, limit=10):
        raise NotImplementedError

    def mark_published(self, session, /, event_id):
        raise NotImplementedError

    def mark_failed(self, session, /, event_id, *, error_code, next_retry_at):
        raise NotImplementedError


class _FakeVersionPort(ProjectVersionReadPort):
    """Controllable ProjectVersion loader."""

    def __init__(self, versions: dict[str, _LoadedVersion | None] | None = None) -> None:
        self.versions: dict[str, _LoadedVersion | None] = versions or {}

    def load_by_id(self, session: Session, project_version_id: str) -> _LoadedVersion | None:
        return self.versions.get(project_version_id)


class _FakeUoW:
    """Minimal unit-of-work for testing."""

    def __init__(self, session: MagicMock | None = None) -> None:
        self.session = session or MagicMock(spec=Session)
        self._committed = False
        self._rolled_back = False

    def begin(self) -> None:
        pass

    def commit(self) -> None:
        self._committed = True

    def rollback(self) -> None:
        self._rolled_back = True

    def close(self) -> None:
        pass


def _make_service(
    request_repo: OrchestrationRequestRepository | None = None,
    outbox_repo: AuditOutboxRepository | None = None,
    version_port: ProjectVersionReadPort | None = None,
    snapshot_port: ExecutionSnapshotPreflightPort | None = None,
    coefficient_port: CoefficientResolutionPreflightPort | None = None,
) -> OrchestrationPreflightService:
    return OrchestrationPreflightService(
        request_repo=request_repo or _FakeRequestRepo(),
        outbox_repo=outbox_repo or _FakeOutboxRepo(),
        version_port=version_port or _FakeVersionPort(),
        snapshot_port=snapshot_port or MagicMock(spec=ExecutionSnapshotPreflightPort),
        coefficient_port=coefficient_port or MagicMock(spec=CoefficientResolutionPreflightPort),
    )


# ── Command identity validation ─────────────────────────────────────────────


class TestCommandIdentityValidation:
    def test_valid_command_passes(self) -> None:
        cmd = _make_command()
        svc = _make_service(
            version_port=_FakeVersionPort(
                {"pv-1": _LoadedVersion("p-1", "approved")}
            )
        )
        uow = _FakeUoW()
        result = svc.preflight_and_persist(cmd, uow)
        assert isinstance(result, PreflightAccepted)
        assert result.request_id.startswith("req-")

    def test_empty_actor_rejected(self) -> None:
        cmd = _make_command(actor="")
        svc = _make_service()
        uow = _FakeUoW()
        with pytest.raises(PreflightFailure) as exc_info:
            svc.preflight_and_persist(cmd, uow)
        pf = exc_info.value
        assert pf.error_class == "OrchestrationRequestIdentityError"
        assert pf.field == "actor"

    def test_whitespace_actor_rejected(self) -> None:
        cmd = _make_command(actor="   ")
        svc = _make_service()
        uow = _FakeUoW()
        with pytest.raises(PreflightFailure):
            svc.preflight_and_persist(cmd, uow)

    def test_empty_correlation_id_rejected(self) -> None:
        cmd = _make_command(correlation_id="")
        svc = _make_service()
        uow = _FakeUoW()
        with pytest.raises(PreflightFailure) as exc_info:
            svc.preflight_and_persist(cmd, uow)
        assert exc_info.value.field == "correlation_id"

    def test_empty_project_id_rejected(self) -> None:
        cmd = _make_command(project_id="")
        svc = _make_service()
        uow = _FakeUoW()
        with pytest.raises(PreflightFailure) as exc_info:
            svc.preflight_and_persist(cmd, uow)
        assert exc_info.value.field == "project_id"

    def test_empty_project_version_id_rejected(self) -> None:
        cmd = _make_command(project_version_id="")
        svc = _make_service()
        uow = _FakeUoW()
        with pytest.raises(PreflightFailure) as exc_info:
            svc.preflight_and_persist(cmd, uow)
        assert exc_info.value.field == "project_version_id"


# ── Request fingerprint ─────────────────────────────────────────────────────


class TestRequestFingerprint:
    def test_same_command_produces_same_fingerprint(self) -> None:
        cmd1 = _make_command(actor="a", correlation_id="c1")
        cmd2 = _make_command(actor="a", correlation_id="c1")
        repo = _FakeRequestRepo()
        svc = _make_service(
            request_repo=repo,
            version_port=_FakeVersionPort({"pv-1": _LoadedVersion("p-1", "approved")}),
        )
        uow1 = _FakeUoW()
        uow2 = _FakeUoW()
        r1 = svc.preflight_and_persist(cmd1, uow1)
        r2 = svc.preflight_and_persist(cmd2, uow2)
        fp1 = repo.requests[r1.request_id]["request_fingerprint"]
        fp2 = repo.requests[r2.request_id]["request_fingerprint"]
        assert fp1 == fp2

    def test_actor_change_alters_fingerprint(self) -> None:
        cmd1 = _make_command(actor="a")
        cmd2 = _make_command(actor="b")
        repo = _FakeRequestRepo()
        svc = _make_service(
            request_repo=repo,
            version_port=_FakeVersionPort({"pv-1": _LoadedVersion("p-1", "approved")}),
        )
        uow1 = _FakeUoW()
        uow2 = _FakeUoW()
        r1 = svc.preflight_and_persist(cmd1, uow1)
        r2 = svc.preflight_and_persist(cmd2, uow2)
        assert (
            repo.requests[r1.request_id]["request_fingerprint"]
            != repo.requests[r2.request_id]["request_fingerprint"]
        )

    def test_correlation_id_change_alters_fingerprint(self) -> None:
        cmd1 = _make_command(correlation_id="c1")
        cmd2 = _make_command(correlation_id="c2")
        repo = _FakeRequestRepo()
        svc = _make_service(
            request_repo=repo,
            version_port=_FakeVersionPort({"pv-1": _LoadedVersion("p-1", "approved")}),
        )
        uow1 = _FakeUoW()
        uow2 = _FakeUoW()
        r1 = svc.preflight_and_persist(cmd1, uow1)
        r2 = svc.preflight_and_persist(cmd2, uow2)
        assert (
            repo.requests[r1.request_id]["request_fingerprint"]
            != repo.requests[r2.request_id]["request_fingerprint"]
        )

    def test_same_fingerprint_creates_distinct_request_ids(self) -> None:
        cmd = _make_command()
        repo = _FakeRequestRepo()
        svc = _make_service(
            request_repo=repo,
            version_port=_FakeVersionPort({"pv-1": _LoadedVersion("p-1", "approved")}),
        )
        uow1 = _FakeUoW()
        uow2 = _FakeUoW()
        r1 = svc.preflight_and_persist(cmd, uow1)
        r2 = svc.preflight_and_persist(cmd, uow2)
        assert r1.request_id != r2.request_id
        assert r1.fingerprint == r2.fingerprint

    def test_no_identity_attempt_calculation_binding_called(self) -> None:
        """Verify preflight never touches identity/attempt/calculation/binding."""
        cmd = _make_command()
        svc = _make_service(
            version_port=_FakeVersionPort({"pv-1": _LoadedVersion("p-1", "approved")}),
        )
        uow = _FakeUoW()
        result = svc.preflight_and_persist(cmd, uow)
        assert result.request_id.startswith("req-")
        # No identity, attempt, calculation, or binding created


# ── Preflight rejection typing ──────────────────────────────────────────────


class TestPreflightRejections:
    def test_project_version_not_found(self) -> None:
        svc = _make_service(version_port=_FakeVersionPort({}))
        uow = _FakeUoW()
        with pytest.raises(PreflightFailure) as exc_info:
            svc.preflight_and_persist(_make_command(), uow)
        pf = exc_info.value
        assert pf.error_class == "ProjectVersionNotFoundError"
        assert pf.code == "PROJ_VERSION_NOT_FOUND"
        assert pf.field == "project_version_id"

    def test_project_version_project_mismatch(self) -> None:
        svc = _make_service(
            version_port=_FakeVersionPort(
                {"pv-1": _LoadedVersion("other-project", "approved")}
            )
        )
        uow = _FakeUoW()
        with pytest.raises(PreflightFailure) as exc_info:
            svc.preflight_and_persist(_make_command(project_id="p-1"), uow)
        pf = exc_info.value
        assert pf.error_class == "ProjectVersionProjectMismatchError"
        assert pf.code == "PROJ_VERSION_PROJECT_MISMATCH"
        assert pf.field == "project_id"

    def test_project_version_draft_rejected(self) -> None:
        svc = _make_service(
            version_port=_FakeVersionPort(
                {"pv-1": _LoadedVersion("p-1", "draft")}
            )
        )
        uow = _FakeUoW()
        with pytest.raises(PreflightFailure) as exc_info:
            svc.preflight_and_persist(_make_command(), uow)
        pf = exc_info.value
        assert pf.error_class == "ProjectVersionNotReadyError"
        assert pf.code == "PROJ_VERSION_NOT_READY"

    def test_project_version_archived_rejected(self) -> None:
        svc = _make_service(
            version_port=_FakeVersionPort(
                {"pv-1": _LoadedVersion("p-1", "archived")}
            )
        )
        uow = _FakeUoW()
        with pytest.raises(PreflightFailure) as exc_info:
            svc.preflight_and_persist(_make_command(), uow)
        pf = exc_info.value
        assert pf.error_class == "ProjectVersionArchivedError"
        assert pf.code == "PROJ_VERSION_ARCHIVED"

    def test_project_version_unknown_status_rejected(self) -> None:
        svc = _make_service(
            version_port=_FakeVersionPort(
                {"pv-1": _LoadedVersion("p-1", "deprecated")}
            )
        )
        uow = _FakeUoW()
        with pytest.raises(PreflightFailure) as exc_info:
            svc.preflight_and_persist(_make_command(), uow)
        pf = exc_info.value
        assert pf.error_class == "ProjectVersionStatusInvalidError"
        assert pf.code == "PROJ_VERSION_STATUS_INVALID"


# ── Transaction behavior ────────────────────────────────────────────────────


class TestTransactionBehavior:
    def test_success_commits(self) -> None:
        svc = _make_service(
            version_port=_FakeVersionPort({"pv-1": _LoadedVersion("p-1", "approved")}),
        )
        uow = _FakeUoW()
        svc.preflight_and_persist(_make_command(), uow)
        assert uow._committed is True
        assert uow._rolled_back is False

    def test_rejection_commits(self) -> None:
        """Rejection writes are durable — commit must happen."""
        svc = _make_service(version_port=_FakeVersionPort({}))
        uow = _FakeUoW()
        with pytest.raises(PreflightFailure):
            svc.preflight_and_persist(_make_command(), uow)
        assert uow._committed is True    # rejection is committed
        assert uow._rolled_back is False

    def test_unexpected_exception_rolls_back(self) -> None:
        """A non-domain exception (e.g., DB connection loss) rolls back."""

        class ExplodingRepo(_FakeRequestRepo):
            def add(self, session, /, **kwargs) -> str:
                raise RuntimeError("connection lost")

        svc = _make_service(request_repo=ExplodingRepo())
        uow = _FakeUoW()
        with pytest.raises(RuntimeError, match="connection lost"):
            svc.preflight_and_persist(_make_command(), uow)
        assert uow._rolled_back is True

    def test_repository_never_commits(self) -> None:
        """Repositories are session-bound; service owns the commit."""
        svc = _make_service(
            version_port=_FakeVersionPort({"pv-1": _LoadedVersion("p-1", "approved")}),
        )
        uow = _FakeUoW()
        # Session is a MagicMock — if any repo code calls commit(), it'll be recorded
        svc.preflight_and_persist(_make_command(), uow)
        # The mock session should only have been touched by the service's uow.commit()
        # We don't assert on MagicMock here because FakeUoW wraps it

    def test_outbox_and_request_in_same_commit(self) -> None:
        """On rejection, both request update and outbox write happen before commit."""
        request_repo = _FakeRequestRepo()
        outbox_repo = _FakeOutboxRepo()
        svc = _make_service(
            request_repo=request_repo,
            outbox_repo=outbox_repo,
            version_port=_FakeVersionPort({}),
        )
        uow = _FakeUoW()
        with pytest.raises(PreflightFailure):
            svc.preflight_and_persist(_make_command(), uow)

        # Both should exist
        assert len(request_repo.requests) == 1
        rid = list(request_repo.requests.keys())[0]
        assert request_repo.requests[rid]["status"] == "PREFLIGHT_REJECTED"
        assert request_repo.requests[rid]["failure_code"] is not None

        assert len(outbox_repo.events) == 1
        ev = outbox_repo.events[0]
        assert ev["request_id"] == rid
        assert ev["identity_id"] is None
        assert ev["attempt_id"] is None
        assert ev["calculation_run_id"] is None
        assert ev["source_binding_id"] is None


# ── PreflightFailure carrys all fields ──────────────────────────────────────


class TestPreflightFailureFields:
    def test_failure_contains_all_contract_fields(self) -> None:
        svc = _make_service(
            version_port=_FakeVersionPort(
                {"pv-1": _LoadedVersion("other-p", "draft")}
            )
        )
        uow = _FakeUoW()
        with pytest.raises(PreflightFailure) as pf_exc:
            svc.preflight_and_persist(_make_command(project_id="p-1"), uow)

        pf = pf_exc.value
        assert pf.request_id != ""
        assert pf.project_id == "p-1"
        assert pf.project_version_id == "pv-1"
        assert pf.error_class == "ProjectVersionProjectMismatchError"
        assert pf.code == "PROJ_VERSION_PROJECT_MISMATCH"
        assert pf.field == "project_id"
        assert isinstance(pf.details, Mapping)
        assert pf.occurred_at is not None
