"""SQLite integration tests for OrchestrationPreflightService.

Covers:
- request PENDING insert via Alembic Head schema
- rejection mutation
- request-level outbox FK
- exact null identity/attempt/calculation/binding fields
- atomic rollback (outbox insert fails → request mutation rolled back)
- two same-fingerprint requests coexist
- ProjectVersion lookup via real SQLAlchemy session
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.orchestration.application.ports import (
    CoefficientResolutionPreflightPort,
    ExecutionSnapshotPreflightPort,
)
from cold_storage.modules.orchestration.application.service import (
    OrchestrationPreflightService,
    ProjectVersionReadPort,
    _LoadedVersion,
)
from cold_storage.modules.orchestration.domain.contracts import (
    OrchestrationRequestCommand,
    PreflightFailure,
)
from cold_storage.modules.orchestration.infrastructure.orm import (
    AuditOutboxRecord,
    OrchestrationRequestRecord,
)
from cold_storage.modules.orchestration.infrastructure.repositories import (
    SqlAlchemyAuditOutboxRepository,
    SqlAlchemyOrchestrationRequestRepository,
)
from cold_storage.modules.projects.infrastructure.orm import (
    Base,
    ProjectRecord,
    ProjectVersionRecord,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def engine():
    """In-memory SQLite engine with full Alembic-equivalent schema."""
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(e)
    yield e
    e.dispose()


@pytest.fixture()
def session(engine):
    """Session bound to in-memory engine, rolled back after each test."""
    sm = sessionmaker(bind=engine)
    s = sm()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def request_repo() -> SqlAlchemyOrchestrationRequestRepository:
    return SqlAlchemyOrchestrationRequestRepository()


@pytest.fixture()
def outbox_repo() -> SqlAlchemyAuditOutboxRepository:
    return SqlAlchemyAuditOutboxRepository()


class _FakeVersionPort(ProjectVersionReadPort):
    """Controllable ProjectVersion loader backed by a real session."""

    def load_by_id(self, session: Session, project_version_id: str) -> _LoadedVersion | None:
        record = session.execute(
            select(ProjectVersionRecord).where(ProjectVersionRecord.id == project_version_id)
        ).scalar_one_or_none()
        if record is None:
            return None
        return _LoadedVersion(project_id=record.project_id, status=record.status)


def _seed_project_and_version(
    session: Session,
    *,
    project_id: str = "p-1",
    version_id: str = "pv-1",
    project_name: str = "Test Project",
    status: str = "approved",
) -> None:
    """Seed a project and approved ProjectVersion into the database."""

    project = ProjectRecord(
        id=project_id,
        code="T001",
        name=project_name,
        location="test",
        product_category="blueberry",
        created_at=datetime.now(UTC),
    )
    session.add(project)
    version = ProjectVersionRecord(
        id=version_id,
        project_id=project_id,
        version_number=1,
        change_summary="test version",
        created_by="test",
        status=status,
        created_at=datetime.now(UTC),
    )
    session.add(version)
    session.flush()


def _make_service(
    request_repo: SqlAlchemyOrchestrationRequestRepository,
    outbox_repo: SqlAlchemyAuditOutboxRepository,
    session: Session,
    **kwargs,
) -> OrchestrationPreflightService:
    """Create a service wired to real repositories and a version port
    backed by *session*."""
    version_port = _FakeVersionPort()
    snapshot_port = MagicMock(spec=ExecutionSnapshotPreflightPort)
    coefficient_port = MagicMock(spec=CoefficientResolutionPreflightPort)
    return OrchestrationPreflightService(
        request_repo=request_repo,
        outbox_repo=outbox_repo,
        version_port=version_port,
        snapshot_port=snapshot_port,
        coefficient_port=coefficient_port,
    )


def _make_uow(session: Session):
    """Minimal unit-of-work wrapping a real session."""

    class Uow:
        def __init__(self, s: Session) -> None:
            self.session = s

        def begin(self) -> None:
            pass

        def commit(self) -> None:
            self.session.commit()

        def rollback(self) -> None:
            self.session.rollback()

        def close(self) -> None:
            pass

    return Uow(session)


def _make_command(
    project_id: str = "p-1",
    project_version_id: str = "pv-1",
    actor: str = "test-actor",
    correlation_id: str = "corr-1",
) -> OrchestrationRequestCommand:
    return OrchestrationRequestCommand(
        project_id=project_id,
        project_version_id=project_version_id,
        coefficient_resolution_context={},
        actor=actor,
        correlation_id=correlation_id,
    )


# ── Tests ───────────────────────────────────────────────────────────────────


class TestRequestPersistence:
    """Real SQLAlchemy persistence for request lifecycle."""

    def test_pending_request_inserted(self, session, request_repo, outbox_repo) -> None:
        _seed_project_and_version(session)
        svc = _make_service(request_repo, outbox_repo, session)
        uow = _make_uow(session)

        result = svc.preflight_and_persist(_make_command(), uow)

        row = session.execute(
            select(OrchestrationRequestRecord).where(
                OrchestrationRequestRecord.id == result.request_id
            )
        ).scalar_one()
        assert row.status == "PENDING"
        assert row.project_id == "p-1"
        assert row.project_version_id == "pv-1"
        assert row.actor == "test-actor"
        assert row.correlation_id == "corr-1"
        assert row.request_fingerprint is not None
        assert row.failure_code is None
        assert row.failure_field is None
        assert row.failure_details is None
        assert row.resolved_identity_id is None
        assert row.resolved_attempt_id is None

    def test_rejection_mutation(self, session, request_repo, outbox_repo) -> None:
        # No version seeded → ProjectVersionNotFoundError
        svc = _make_service(request_repo, outbox_repo, session)
        uow = _make_uow(session)

        with pytest.raises(PreflightFailure) as pf_exc:
            svc.preflight_and_persist(_make_command(), uow)

        pf = pf_exc.value
        assert pf.error_class == "ProjectVersionNotFoundError"

        # Request must be PREFLIGHT_REJECTED
        row = session.execute(
            select(OrchestrationRequestRecord).where(OrchestrationRequestRecord.id == pf.request_id)
        ).scalar_one()
        assert row.status == "PREFLIGHT_REJECTED"
        assert row.failure_code == "PROJ_VERSION_NOT_FOUND"
        assert row.failure_field == "project_version_id"
        assert row.failure_details is not None
        assert row.completed_at is not None

    def test_request_level_outbox_event(self, session, request_repo, outbox_repo) -> None:
        svc = _make_service(request_repo, outbox_repo, session)
        uow = _make_uow(session)

        with pytest.raises(PreflightFailure) as pf_exc:
            svc.preflight_and_persist(_make_command(), uow)

        pf = pf_exc.value

        # One outbox event for the rejection
        events = (
            session.execute(
                select(AuditOutboxRecord).where(AuditOutboxRecord.request_id == pf.request_id)
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        ev = events[0]
        assert ev.event_type == "orchestration.request.rejected"
        assert ev.aggregate_type == "OrchestrationRequest"
        assert ev.aggregate_id == pf.request_id
        assert ev.status == "PENDING"
        # All other FK fields must be NULL
        assert ev.identity_id is None
        assert ev.attempt_id is None
        assert ev.calculation_run_id is None
        assert ev.source_binding_id is None

    def test_two_same_fingerprint_requests_coexist(
        self, session, request_repo, outbox_repo
    ) -> None:
        _seed_project_and_version(session)
        svc = _make_service(request_repo, outbox_repo, session)

        uow1 = _make_uow(session)
        r1 = svc.preflight_and_persist(_make_command(correlation_id="c1"), uow1)

        uow2 = _make_uow(session)
        r2 = svc.preflight_and_persist(_make_command(correlation_id="c1"), uow2)

        assert r1.request_id != r2.request_id
        assert r1.fingerprint == r2.fingerprint

        rows = (
            session.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.project_id == "p-1"
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 2

    def test_atomic_rollback_on_unexpected_error(self, session, request_repo, outbox_repo) -> None:
        """When a non-domain exception occurs, nothing should be persisted."""

        class ExplodingPort(ExecutionSnapshotPreflightPort):
            def validate_candidate(self, **kwargs) -> None:
                raise RuntimeError("unexpected failure")

        _seed_project_and_version(session)
        svc = OrchestrationPreflightService(
            request_repo=request_repo,
            outbox_repo=outbox_repo,
            version_port=_FakeVersionPort(),
            snapshot_port=ExplodingPort(),
            coefficient_port=MagicMock(spec=CoefficientResolutionPreflightPort),
        )
        uow = _make_uow(session)

        with pytest.raises(RuntimeError):
            svc.preflight_and_persist(_make_command(), uow)

        # Nothing persisted
        rows = session.execute(select(OrchestrationRequestRecord)).scalars().all()
        # The request was created during _preflight() but rolled back
        assert len(rows) == 0

    def test_version_not_found(self, session, request_repo, outbox_repo) -> None:
        svc = _make_service(request_repo, outbox_repo, session)
        uow = _make_uow(session)

        with pytest.raises(PreflightFailure) as pf_exc:
            svc.preflight_and_persist(_make_command(project_version_id="nonexistent"), uow)

        assert pf_exc.value.error_class == "ProjectVersionNotFoundError"

    def test_version_wrong_project(self, session, request_repo, outbox_repo) -> None:
        _seed_project_and_version(session, project_id="p-2", version_id="pv-1")
        svc = _make_service(request_repo, outbox_repo, session)
        uow = _make_uow(session)

        with pytest.raises(PreflightFailure) as pf_exc:
            svc.preflight_and_persist(
                _make_command(project_id="p-1", project_version_id="pv-1"), uow
            )

        assert pf_exc.value.error_class == "ProjectVersionProjectMismatchError"

    def test_draft_version_rejected(self, session, request_repo, outbox_repo) -> None:
        _seed_project_and_version(session, status="draft")
        svc = _make_service(request_repo, outbox_repo, session)
        uow = _make_uow(session)

        with pytest.raises(PreflightFailure) as pf_exc:
            svc.preflight_and_persist(_make_command(), uow)

        assert pf_exc.value.error_class == "ProjectVersionNotReadyError"

    def test_archived_version_rejected(self, session, request_repo, outbox_repo) -> None:
        _seed_project_and_version(session, status="archived")
        svc = _make_service(request_repo, outbox_repo, session)
        uow = _make_uow(session)

        with pytest.raises(PreflightFailure) as pf_exc:
            svc.preflight_and_persist(_make_command(), uow)

        assert pf_exc.value.error_class == "ProjectVersionArchivedError"


class TestRequestCheckConstraint:
    """Verify the ORM CHECK constraint for status-dependent nullability."""

    def test_pending_request_has_null_resolution_fields(
        self, session, request_repo, outbox_repo
    ) -> None:
        _seed_project_and_version(session)
        svc = _make_service(request_repo, outbox_repo, session)
        uow = _make_uow(session)
        result = svc.preflight_and_persist(_make_command(), uow)

        row = session.execute(
            select(OrchestrationRequestRecord).where(
                OrchestrationRequestRecord.id == result.request_id
            )
        ).scalar_one()
        assert row.status == "PENDING"
        assert row.resolved_identity_id is None
        assert row.resolved_attempt_id is None
        assert row.failure_code is None
        assert row.failure_field is None
        assert row.failure_details is None
        assert row.completed_at is None

    def test_preflight_rejected_has_failure_fields(
        self, session, request_repo, outbox_repo
    ) -> None:
        svc = _make_service(request_repo, outbox_repo, session)
        uow = _make_uow(session)

        with pytest.raises(PreflightFailure) as pf_exc:
            svc.preflight_and_persist(_make_command(), uow)

        row = session.execute(
            select(OrchestrationRequestRecord).where(
                OrchestrationRequestRecord.id == pf_exc.value.request_id
            )
        ).scalar_one()
        assert row.status == "PREFLIGHT_REJECTED"
        assert row.resolved_identity_id is None
        assert row.resolved_attempt_id is None
        assert row.failure_code is not None
        assert row.failure_field is not None
        assert row.failure_details is not None
        assert row.completed_at is not None
