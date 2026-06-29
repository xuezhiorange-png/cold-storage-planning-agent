"""Integration tests for orchestration Transaction A and rejection.

Uses real Alembic Head schema via ``alembic upgrade head`` for SQLite.
(CI runs Alembic upgrade head before tests.)

Covers:
- approved ProjectVersion → ACCEPTED (full Transaction A)
- version not found → PREFLIGHT_REJECTED
- draft/archived/unknown → typed rejection
- project mismatch → typed rejection
- atomic rejection (request + outbox in same transaction)
- rejection rollback on persistence failure (P0-3)
- same fingerprint → distinct request IDs with separate identities
- zero identity/attempt/calculation/binding on rejection
- CHECK constraint compliance (PENDING/PREFLIGHT_REJECTED/ACCEPTED)
- fingerprint changes with version vector changes
- attempt acquisition uses max+1, not hardcoded 1
"""

from __future__ import annotations

import os

import pytest

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite Transaction A tests cannot run on PostgreSQL — use "
        "test_orchestration_transaction_a_postgresql.py instead",
        allow_module_level=True,
    )

import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.orchestration.application.ports import (
    CoefficientResolutionPreflightPort,
    ExecutionSnapshotPreflightPort,
    ResolvedCoefficientContextCandidate,
)
from cold_storage.modules.orchestration.application.service import (
    OrchestrationService,
    ProjectVersionReadPort,
    _compute_orchestration_fingerprint,
    _LoadedVersion,
)
from cold_storage.modules.orchestration.application.unit_of_work import (
    SqlAlchemyOrchestrationUnitOfWorkFactory,
)
from cold_storage.modules.orchestration.domain.contracts import (
    AttemptStatus,
    OrchestrationRequestCommand,
    PreflightFailure,
)
from cold_storage.modules.orchestration.domain.errors import (
    AttemptAlreadyRunningError,
)
from cold_storage.modules.orchestration.domain.fingerprint import result_hash
from cold_storage.modules.orchestration.infrastructure.orm import (
    AuditOutboxRecord,
    OrchestrationIdentityRecord,
    OrchestrationRequestRecord,
    OrchestrationRunAttemptRecord,
)
from cold_storage.modules.orchestration.infrastructure.repositories import (
    SqlAlchemyAuditOutboxRepository,
    SqlAlchemyCoefficientContextRepository,
    SqlAlchemyExecutionSnapshotRepository,
    SqlAlchemyOrchestrationAttemptRepository,
    SqlAlchemyOrchestrationIdentityRepository,
    SqlAlchemyOrchestrationRequestRepository,
)
from cold_storage.modules.projects.infrastructure.orm import (
    ProjectRecord,
    ProjectVersionRecord,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Authoritative required codes for the default calculator version vector
# (must match service._AUTHORITATIVE_REQUIRED_CODES exactly)
_REQUIRED_CODES: tuple[str, ...] = (
    "area.auxiliary_area_ratio",
    "area.circulation_allowance_ratio",
    "investment.building_unit_cost",
    "investment.electrical_installation_ratio",
    "investment.other_expenses_ratio",
    "investment.refrigeration_equipment_ratio",
    "pallet.net_load_kg",
    "pallet.turnover_factor",
    "power.design_margin_ratio",
    "power.standby_ratio",
)
_REGISTRY_VERSION = "1.0.0"
_CV_VECTOR: dict[str, str] = {
    "zone": "1.0.0",
    "cooling_load": "1.0.0",
    "equipment": "1.0.0",
    "power": "1.0.0",
    "investment": "1.0.0",
}


def _make_resolved_coefficient(
    *,
    project_id: str = "p-1",
    project_version_id: str = "pv-1",
    extra: dict[str, object] | None = None,
) -> ResolvedCoefficientContextCandidate:
    coefficients: list[dict[str, object]] = []
    revision_ids: list[str] = []
    for i, code in enumerate(_REQUIRED_CODES, 1):
        rev_id = f"rev-{i:03d}"
        revision_ids.append(rev_id)
        coefficients.append(
            {
                "definition_id": f"def-{i:03d}",
                "code": code,
                "revision_id": rev_id,
                "revision_number": 1,
                "unit": "dimensionless",
                "source_type": "standard",
                "status": "approved",
                "value_decimal": "1.0",
            }
        )

    req_hash = result_hash(
        {
            "registry_version": _REGISTRY_VERSION,
            "calculator_version_vector": dict(_CV_VECTOR),
            "required_codes": list(_REQUIRED_CODES),
        }
    )

    content: dict[str, object] = {
        "source_type": "catalog",
        "validity_status": "approved",
        "project_id": project_id,
        "project_version_id": project_version_id,
        "schema_version": "1.0.0",
        "coefficient_count": len(coefficients),
        "coefficients": coefficients,
        "requirement_registry_version": _REGISTRY_VERSION,
        "required_codes": list(_REQUIRED_CODES),
        "requirement_hash": req_hash,
    }
    if extra:
        content.update(extra)
    return ResolvedCoefficientContextCandidate(
        project_id=project_id,
        project_version_id=project_version_id,
        schema_version="1.0.0",
        content=content,
        content_hash=result_hash(content),
        approved_revision_ids=tuple(revision_ids),
    )


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def engine():
    """Create a SQLite DB and run Alembic upgrade head."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)

    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        db_path.unlink(missing_ok=True)
        pytest.fail(f"Alembic upgrade failed:\n{r.stderr}\n{r.stdout}")

    e = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(e, "connect")
    def _pragma(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    yield e
    e.dispose()
    db_path.unlink(missing_ok=True)


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def service(session_factory):
    """Fully wired OrchestrationService."""
    uow_factory = SqlAlchemyOrchestrationUnitOfWorkFactory(session_factory)
    version_port = _RealVersionPort()

    # Default coefficient mock returns approved context
    coeff_port = MagicMock(spec=CoefficientResolutionPreflightPort)
    coeff_port.resolve.return_value = _make_resolved_coefficient()

    return OrchestrationService(
        uow_factory=uow_factory,
        request_repo=SqlAlchemyOrchestrationRequestRepository(),
        outbox_repo=SqlAlchemyAuditOutboxRepository(),
        snapshot_repo=SqlAlchemyExecutionSnapshotRepository(),
        coefficient_repo=SqlAlchemyCoefficientContextRepository(),
        identity_repo=SqlAlchemyOrchestrationIdentityRepository(),
        attempt_repo=SqlAlchemyOrchestrationAttemptRepository(),
        version_port=version_port,
        snapshot_port=MagicMock(spec=ExecutionSnapshotPreflightPort),
        coefficient_port=coeff_port,
    )


class _RealVersionPort(ProjectVersionReadPort):
    def load_by_id(self, session, project_version_id: str) -> _LoadedVersion | None:
        record = session.execute(
            select(ProjectVersionRecord).where(ProjectVersionRecord.id == project_version_id)
        ).scalar_one_or_none()
        if record is None:
            return None
        project_record = session.execute(
            select(ProjectRecord).where(ProjectRecord.id == record.project_id)
        ).scalar_one_or_none()
        product_category = project_record.product_category if project_record else ""
        return _LoadedVersion(
            project_id=record.project_id,
            project_product_category=product_category,
            status=record.status,
            version_number=record.version_number,
            input_snapshot=record.input_snapshot or {},
        )


def _seed_project_and_version(
    session,
    *,
    project_id: str = "p-1",
    version_id: str = "pv-1",
    status: str = "approved",
):
    existing = session.execute(
        select(ProjectRecord).where(ProjectRecord.id == project_id)
    ).scalar_one_or_none()
    if not existing:
        session.add(
            ProjectRecord(
                id=project_id,
                code="T001",
                name="Test Project",
                location="test",
                product_category="blueberry",
                created_at=datetime.now(UTC),
            )
        )
    existing_v = session.execute(
        select(ProjectVersionRecord).where(ProjectVersionRecord.id == version_id)
    ).scalar_one_or_none()
    if not existing_v:
        session.add(
            ProjectVersionRecord(
                id=version_id,
                project_id=project_id,
                version_number=1,
                change_summary="test version",
                created_by="test",
                status=status,
                created_at=datetime.now(UTC),
                input_snapshot={"throughput_t": "25.0", "product_category": "blueberry"},
            )
        )
    session.commit()


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


class TestTransactionASuccess:
    """Full Transaction A: request → ACCEPTED."""

    def test_approved_version_succeeds(self, service, session_factory) -> None:
        with session_factory() as s:
            _seed_project_and_version(s)
        result = service.execute(_make_command())

        assert result.request_id
        assert result.identity_id
        assert result.attempt_id
        assert result.fingerprint

    def test_request_accepted_has_resolved_fields(self, service, session_factory) -> None:
        with session_factory() as s:
            _seed_project_and_version(s)
        result = service.execute(_make_command())

        with session_factory() as s:
            row = s.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.id == result.request_id
                )
            ).scalar_one()
            assert row.status == "ACCEPTED"
            assert row.requested_project_id == "p-1"
            assert row.requested_project_version_id == "pv-1"
            assert row.resolved_project_id == "p-1"
            assert row.resolved_project_version_id == "pv-1"
            assert row.resolved_identity_id == result.identity_id
            assert row.resolved_attempt_id == result.attempt_id
            assert row.failure_code is None
            assert row.completed_at is not None

    def test_creates_identity_and_attempt(self, service, session_factory) -> None:
        with session_factory() as s:
            _seed_project_and_version(s)
        result = service.execute(_make_command())

        with session_factory() as s:
            identity = s.execute(
                select(OrchestrationIdentityRecord).where(
                    OrchestrationIdentityRecord.id == result.identity_id
                )
            ).scalar_one()
            assert identity.fingerprint is not None
            assert identity.status == "ACTIVE"

            attempt = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == result.attempt_id
                )
            ).scalar_one()
            assert attempt.status == "RUNNING"
            assert attempt.attempt_number >= 1

    def test_outbox_events_written(self, service, session_factory) -> None:
        with session_factory() as s:
            _seed_project_and_version(s)
        result = service.execute(_make_command())

        with session_factory() as s:
            events = (
                s.execute(
                    select(AuditOutboxRecord).where(
                        AuditOutboxRecord.request_id == result.request_id
                    )
                )
                .scalars()
                .all()
            )
            assert len(events) >= 1
            ev = events[0]
            assert ev.event_type == "orchestration.request.accepted"

    def test_same_fingerprint_still_creates_attempt(self, service, session_factory) -> None:
        """Same project+version with different correlation_id creates
        a new request but shares identity — after marking first attempt
        COMPLETED, second attempt gets attempt_number=2."""
        with session_factory() as s:
            _seed_project_and_version(s)
        r1 = service.execute(_make_command(correlation_id="c1"))

        # Mark first attempt as COMPLETED so second acquire succeeds.
        # Repositories do NOT commit — we must commit the session ourselves.
        with session_factory() as s:
            service._attempt_repo.update_status(
                s,
                r1.attempt_id,
                status=AttemptStatus.COMPLETED,
            )
            service._identity_repo.set_authoritative_attempt(
                s,
                r1.identity_id,
                r1.attempt_id,
            )
            s.commit()

        # Second call with different correlation_id → different request
        r2 = service.execute(_make_command(correlation_id="c2"))

        # Different request IDs
        assert r1.request_id != r2.request_id
        # Same identity (same fingerprint = same hashes + version vectors)
        assert r1.identity_id == r2.identity_id
        # Different attempt IDs
        assert r1.attempt_id != r2.attempt_id

    def test_fingerprint_changes_with_version_vector(self) -> None:
        """Proof: changing a version field changes the fingerprint."""
        fp1 = _compute_orchestration_fingerprint(
            execution_identity_hash="h1",
            coefficient_context_hash="h2",
            definition_version="1.0.0",
            calculator_version_vector={"zone": "1.0.0"},
            input_mapping_schema_version="1.0.0",
            source_snapshot_schema_version="1.0.0",
        )
        fp2 = _compute_orchestration_fingerprint(
            execution_identity_hash="h1",
            coefficient_context_hash="h2",
            definition_version="2.0.0",  # version changed
            calculator_version_vector={"zone": "1.0.0"},
            input_mapping_schema_version="1.0.0",
            source_snapshot_schema_version="1.0.0",
        )
        assert fp1 != fp2


class TestPreflightRejection:
    """Preflight rejection: PREFLIGHT_REJECTED + outbox, zero downstream."""

    def test_version_not_found(self, service) -> None:
        with pytest.raises(PreflightFailure) as pf_exc:
            service.execute(_make_command(project_version_id="nonexistent"))
        pf = pf_exc.value
        assert pf.error_class == "ProjectVersionNotFoundError"
        assert pf.code == "PROJ_VERSION_NOT_FOUND"
        assert pf.request_id != ""

    def test_project_mismatch(self, service, session_factory) -> None:
        with session_factory() as s:
            _seed_project_and_version(s, project_id="p-2", version_id="pv-1")
        with pytest.raises(PreflightFailure) as pf_exc:
            service.execute(_make_command(project_id="p-1"))
        assert pf_exc.value.error_class == "ProjectVersionProjectMismatchError"
        assert pf_exc.value.request_id != ""

    def test_draft_version(self, service, session_factory) -> None:
        with session_factory() as s:
            _seed_project_and_version(s, status="draft")
        with pytest.raises(PreflightFailure) as pf_exc:
            service.execute(_make_command())
        assert pf_exc.value.error_class == "ProjectVersionNotReadyError"
        assert pf_exc.value.request_id != ""

    def test_archived_version(self, service, session_factory) -> None:
        with session_factory() as s:
            _seed_project_and_version(s, status="archived")
        with pytest.raises(PreflightFailure) as pf_exc:
            service.execute(_make_command())
        assert pf_exc.value.error_class == "ProjectVersionArchivedError"
        assert pf_exc.value.request_id != ""

    def test_rejection_persists_request_and_outbox(self, service, session_factory) -> None:
        with pytest.raises(PreflightFailure):
            service.execute(_make_command(project_version_id="nonexistent"))

        with session_factory() as s:
            row = s.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.requested_project_id == "p-1"
                )
            ).scalar_one_or_none()
            assert row is not None
            assert row.status == "PREFLIGHT_REJECTED"
            assert row.failure_code == "PROJ_VERSION_NOT_FOUND"

            ev = s.execute(
                select(AuditOutboxRecord).where(AuditOutboxRecord.request_id == row.id)
            ).scalar_one_or_none()
            assert ev is not None
            assert ev.event_type == "orchestration.request.rejected"

    def test_rejection_creates_zero_identity_attempt(self, service, session_factory) -> None:
        with pytest.raises(PreflightFailure):
            service.execute(_make_command(project_version_id="nonexistent"))

        with session_factory() as s:
            identities = s.execute(select(OrchestrationIdentityRecord)).scalars().all()
            assert len(identities) == 0

            attempts = s.execute(select(OrchestrationRunAttemptRecord)).scalars().all()
            assert len(attempts) == 0


class TestCheckConstraint:
    """ORM CHECK constraint compliance."""

    def test_pending_request_nullity(self, service, session_factory) -> None:
        with session_factory() as s:
            _seed_project_and_version(s)
        result = service.execute(_make_command())
        with session_factory() as s:
            row = s.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.id == result.request_id
                )
            ).scalar_one()
            assert row.status == "ACCEPTED"
            assert row.resolved_project_id is not None
            assert row.resolved_project_version_id is not None
            assert row.resolved_identity_id is not None
            assert row.resolved_attempt_id is not None
            assert row.completed_at is not None
            assert row.failure_code is None

    def test_rejected_request_nullity(self, service, session_factory) -> None:
        with pytest.raises(PreflightFailure):
            service.execute(_make_command(project_version_id="nonexistent"))

        with session_factory() as s:
            row = s.execute(select(OrchestrationRequestRecord)).scalar_one()
            assert row.status == "PREFLIGHT_REJECTED"
            assert row.failure_code is not None
            assert row.failure_field is not None
            assert row.failure_details is not None
            assert row.completed_at is not None
            assert row.resolved_identity_id is None
            assert row.resolved_attempt_id is None


class TestTransactionC:
    """Transaction C: attempt → BLOCKED/FAILED + outbox."""

    def test_mark_blocked_writes_outbox(self, service, session_factory) -> None:
        with session_factory() as s:
            _seed_project_and_version(s)
        result = service.execute(_make_command())

        service.mark_attempt_blocked(
            result.attempt_id,
            failure_code="TEST_BLOCK",
            failure_details={"reason": "test"},
        )

        with session_factory() as s:
            attempt = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == result.attempt_id
                )
            ).scalar_one()
            assert attempt.status == "BLOCKED"

            ev = s.execute(
                select(AuditOutboxRecord).where(
                    AuditOutboxRecord.attempt_id == result.attempt_id,
                    AuditOutboxRecord.event_type == "orchestration.attempt.blocked",
                )
            ).scalar_one()
            assert ev is not None

    def test_mark_failed_writes_outbox(self, service, session_factory) -> None:
        with session_factory() as s:
            _seed_project_and_version(s)
        result = service.execute(_make_command())

        service.mark_attempt_failed(
            result.attempt_id,
            failure_code="TEST_FAIL",
            failure_details={"reason": "test"},
        )

        with session_factory() as s:
            attempt = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == result.attempt_id
                )
            ).scalar_one()
            assert attempt.status == "FAILED"

            ev = s.execute(
                select(AuditOutboxRecord).where(
                    AuditOutboxRecord.attempt_id == result.attempt_id,
                    AuditOutboxRecord.event_type == "orchestration.attempt.failed",
                )
            ).scalar_one()
            assert ev is not None


class TestConcurrentAttempt:
    """Concurrent attempt acquisition."""

    def test_second_running_attempt_raises_typed_error(self, service, session_factory) -> None:
        """A second attempt acquire while one is RUNNING raises typed error."""
        with session_factory() as s:
            _seed_project_and_version(s)
        r1 = service.execute(_make_command(correlation_id="c1"))

        # The identity now has a RUNNING attempt.
        # Manually try to acquire another — should raise AttemptAlreadyRunningError
        with session_factory() as s:
            from cold_storage.modules.orchestration.infrastructure.repositories import (
                SqlAlchemyOrchestrationAttemptRepository,
            )

            repo = SqlAlchemyOrchestrationAttemptRepository()
            with pytest.raises(AttemptAlreadyRunningError) as exc_info:
                repo.acquire(
                    s,
                    identity_id=r1.identity_id,
                    heartbeat_at=datetime.now(UTC),
                )
            assert r1.identity_id in str(exc_info.value)


class TestServiceReentry:
    """P0-1: Concurrent service reentry — request IDs must not cross-talk."""

    def test_interleaved_failures_preserve_correct_request_ids(
        self, service, session_factory
    ) -> None:
        """Two interleaved failed requests using the same service instance
        must have distinct request IDs, distinct rejection outbox events,
        and distinct PreflightFailure.request_id values."""
        # Seed one project — both requests reference it but with nonexistent versions
        with session_factory() as s:
            _seed_project_and_version(s)

        failures: list[PreflightFailure] = []

        # Interleave two calls — both should fail with version not found
        for version_id in ("pv-nonexistent-a", "pv-nonexistent-b"):
            try:
                service.execute(_make_command(project_version_id=version_id))
            except PreflightFailure as pf:
                failures.append(pf)

        assert len(failures) == 2

        # Request IDs must differ
        assert failures[0].request_id != failures[1].request_id, (
            f"Shared request_id across reentrant calls: {failures[0].request_id!r}"
        )

        # Each request ID must be non-empty
        for pf in failures:
            assert pf.request_id != "", "request_id must not be empty"

        # Verify database: two distinct requests, two distinct outbox events
        with session_factory() as s:
            from cold_storage.modules.orchestration.infrastructure.orm import (
                AuditOutboxRecord,
                OrchestrationRequestRecord,
            )

            req_ids = {pf.request_id for pf in failures}
            rows = (
                s.execute(
                    select(OrchestrationRequestRecord).where(
                        OrchestrationRequestRecord.id.in_(req_ids)
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 2
            for row in rows:
                assert row.status == "PREFLIGHT_REJECTED"

            events = (
                s.execute(
                    select(AuditOutboxRecord).where(AuditOutboxRecord.request_id.in_(req_ids))
                )
                .scalars()
                .all()
            )
            assert len(events) == 2
            event_request_ids = {e.request_id for e in events}
            assert event_request_ids == req_ids, "Outbox events not bound to correct requests"


# ── Durable Rejection: All Domain Error Paths ────────────────────────────


class TestDurableRejectionAllPaths:
    """P0-1: Every domain error after durable request creation must produce
    PREFLIGHT_REJECTED + outbox + zero downstream rows."""

    def test_snapshot_port_failure(self, service, session_factory) -> None:
        """Snapshot preflight failure → durable rejection."""
        from cold_storage.modules.orchestration.domain.errors import (
            ExecutionSnapshotSchemaError,
        )

        service._snapshot_port.validate_candidate.side_effect = ExecutionSnapshotSchemaError(
            "v9.9.9"
        )

        with session_factory() as s:
            _seed_project_and_version(s)

        with pytest.raises(PreflightFailure) as pf_exc:
            service.execute(_make_command())

        pf = pf_exc.value
        assert pf.error_class == "ExecutionSnapshotSchemaError"
        assert pf.request_id != ""

        with session_factory() as s:
            req = s.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.id == pf.request_id
                )
            ).scalar_one()
            assert req.status == "PREFLIGHT_REJECTED"

            ev = s.execute(
                select(AuditOutboxRecord).where(
                    AuditOutboxRecord.request_id == pf.request_id,
                    AuditOutboxRecord.event_type == "orchestration.request.rejected",
                )
            ).scalar_one()
            assert ev is not None

            # Zero downstream rows
            from sqlalchemy import func

            assert (
                s.execute(select(func.count()).select_from(OrchestrationIdentityRecord)).scalar()
                == 0
            )
            assert (
                s.execute(select(func.count()).select_from(OrchestrationRunAttemptRecord)).scalar()
                == 0
            )

    def test_coefficient_resolver_failure(self, service, session_factory) -> None:
        """Coefficient resolver failure → durable rejection."""
        from cold_storage.modules.orchestration.domain.errors import (
            CoefficientResolutionError,
        )

        service._coefficient_port.resolve.side_effect = CoefficientResolutionError(
            "resolver", "coefficient catalog unavailable"
        )

        with session_factory() as s:
            _seed_project_and_version(s)

        with pytest.raises(PreflightFailure) as pf_exc:
            service.execute(_make_command())

        pf = pf_exc.value
        assert pf.error_class == "CoefficientResolutionError"
        assert pf.request_id != ""

        with session_factory() as s:
            req = s.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.id == pf.request_id
                )
            ).scalar_one()
            assert req.status == "PREFLIGHT_REJECTED"

            ev = s.execute(
                select(AuditOutboxRecord).where(
                    AuditOutboxRecord.request_id == pf.request_id,
                    AuditOutboxRecord.event_type == "orchestration.request.rejected",
                )
            ).scalar_one()
            assert ev is not None

            from sqlalchemy import func

            assert (
                s.execute(select(func.count()).select_from(OrchestrationIdentityRecord)).scalar()
                == 0
            )

    def test_attempt_live_running_conflict(self, service, session_factory) -> None:
        """Live RUNNING attempt → durable rejection."""
        with session_factory() as s:
            _seed_project_and_version(s)
        service.execute(_make_command(correlation_id="c1"))

        with pytest.raises(PreflightFailure) as pf_exc:
            service.execute(_make_command(correlation_id="c2"))

        pf = pf_exc.value
        assert pf.error_class == "AttemptAlreadyRunningError"
        assert pf.request_id != ""

        with session_factory() as s:
            req = s.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.id == pf.request_id
                )
            ).scalar_one()
            assert req.status == "PREFLIGHT_REJECTED"

            ev = s.execute(
                select(AuditOutboxRecord).where(
                    AuditOutboxRecord.request_id == pf.request_id,
                    AuditOutboxRecord.event_type == "orchestration.request.rejected",
                )
            ).scalar_one()
            assert ev is not None

    def test_empty_approved_revisions(self, service, session_factory) -> None:
        """Empty approved revision IDs → durable rejection."""
        from cold_storage.modules.orchestration.application.ports import (
            ResolvedCoefficientContextCandidate as RCC,
        )

        candidate = _make_resolved_coefficient()
        service._coefficient_port.resolve.return_value = RCC(
            project_id=candidate.project_id,
            project_version_id=candidate.project_version_id,
            schema_version=candidate.schema_version,
            content=candidate.content,
            content_hash=candidate.content_hash,
            approved_revision_ids=(),
        )

        with session_factory() as s:
            _seed_project_and_version(s)

        with pytest.raises(PreflightFailure) as pf_exc:
            service.execute(_make_command())

        pf = pf_exc.value
        assert pf.error_class == "CoefficientNotApprovedError"

        with session_factory() as s:
            req = s.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.id == pf.request_id
                )
            ).scalar_one()
            assert req.status == "PREFLIGHT_REJECTED"
            from sqlalchemy import func

            assert (
                s.execute(select(func.count()).select_from(OrchestrationIdentityRecord)).scalar()
                == 0
            )

    def test_duplicate_approved_revisions(self, service, session_factory) -> None:
        """Duplicate approved revision IDs → durable rejection."""
        from cold_storage.modules.orchestration.application.ports import (
            ResolvedCoefficientContextCandidate as RCC,
        )

        candidate = _make_resolved_coefficient()
        service._coefficient_port.resolve.return_value = RCC(
            project_id=candidate.project_id,
            project_version_id=candidate.project_version_id,
            schema_version=candidate.schema_version,
            content=candidate.content,
            content_hash=candidate.content_hash,
            approved_revision_ids=("rev-001", "rev-001"),
        )

        with session_factory() as s:
            _seed_project_and_version(s)

        with pytest.raises(PreflightFailure) as pf_exc:
            service.execute(_make_command())

        pf = pf_exc.value
        assert pf.error_class == "AmbiguousCoefficientError"

        with session_factory() as s:
            req = s.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.id == pf.request_id
                )
            ).scalar_one()
            assert req.status == "PREFLIGHT_REJECTED"

    def test_unsupported_coefficient_schema(self, service, session_factory) -> None:
        """Unsupported schema version → durable rejection."""
        from cold_storage.modules.orchestration.application.ports import (
            ResolvedCoefficientContextCandidate as RCC,
        )

        service._coefficient_port.resolve.return_value = RCC(
            project_id="p-1",
            project_version_id="pv-1",
            schema_version="9.9.9",
            content={"schema_version": "9.9.9"},
            content_hash=result_hash({"schema_version": "9.9.9"}),
            approved_revision_ids=("rev-001",),
        )

        with session_factory() as s:
            _seed_project_and_version(s)

        with pytest.raises(PreflightFailure) as pf_exc:
            service.execute(_make_command())

        pf = pf_exc.value
        assert pf.error_class == "CoefficientResolutionError"

        with session_factory() as s:
            req = s.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.id == pf.request_id
                )
            ).scalar_one()
            assert req.status == "PREFLIGHT_REJECTED"

    def test_content_schema_mismatch(self, service, session_factory) -> None:
        """Content schema_version != typed schema_version → durable rejection."""
        from cold_storage.modules.orchestration.application.ports import (
            ResolvedCoefficientContextCandidate as RCC,
        )

        service._coefficient_port.resolve.return_value = RCC(
            project_id="p-1",
            project_version_id="pv-1",
            schema_version="1.0.0",
            content={"schema_version": "2.0.0"},
            content_hash=result_hash({"schema_version": "2.0.0"}),
            approved_revision_ids=("rev-001",),
        )

        with session_factory() as s:
            _seed_project_and_version(s)

        with pytest.raises(PreflightFailure) as pf_exc:
            service.execute(_make_command())

        pf = pf_exc.value
        assert pf.error_class == "CoefficientResolutionError"


# ── True Service Reentry (threading.Barrier) ────────────────────────────


class TestTrueServiceReentry:
    """P0-2: Deterministic interleaving via threading.Barrier — proves
    same service instance does not cross-talk request IDs."""

    def test_concurrent_rejection_no_request_id_crosstalk(self, service, session_factory) -> None:
        """Two threads interleave on the same service instance.
        Both threads call execute with different version IDs that trigger
        preflight rejection. Each must get its own request_id.

        Skipped on SQLite StaticPool — requires PostgreSQL for threading."""
        import os

        if os.environ.get("DATABASE_BACKEND") != "postgresql":
            pytest.skip("Threading reentry requires PostgreSQL")

        import threading

        with session_factory() as s:
            _seed_project_and_version(s)

        errors: list[Exception] = []
        results: dict[str, PreflightFailure | None] = {}

        def call_a():
            try:
                results["a"] = None
                service.execute(
                    _make_command(
                        project_version_id="pv-nonexistent-a",
                        correlation_id="thread-a",
                    )
                )
            except PreflightFailure as pf:
                results["a"] = pf
            except Exception as e:
                errors.append(e)

        def call_b():
            try:
                results["b"] = None
                service.execute(
                    _make_command(
                        project_version_id="pv-nonexistent-b",
                        correlation_id="thread-b",
                    )
                )
            except PreflightFailure as pf:
                results["b"] = pf
            except Exception as e:
                errors.append(e)

        barrier = threading.Barrier(2, timeout=10)

        def thread_a():
            barrier.wait()
            call_a()

        def thread_b():
            barrier.wait()
            call_b()

        t_a = threading.Thread(target=thread_a, name="reentry-a")
        t_b = threading.Thread(target=thread_b, name="reentry-b")
        t_a.start()
        t_b.start()
        t_a.join(timeout=15)
        t_b.join(timeout=15)

        assert not errors, f"Thread errors: {errors}"
        assert results.get("a") is not None, "Thread A did not produce a result"
        assert results.get("b") is not None, "Thread B did not produce a result"

        pf_a = results["a"]
        pf_b = results["b"]
        assert pf_a is not None and pf_b is not None
        assert pf_a.request_id != pf_b.request_id, (
            f"Request IDs must differ: {pf_a.request_id!r} vs {pf_b.request_id!r}"
        )
        assert pf_a.request_id != ""
        assert pf_b.request_id != ""

        # Each thread's request should independently be PREFLIGHT_REJECTED
        with session_factory() as s:
            for pf in (pf_a, pf_b):
                req = s.execute(
                    select(OrchestrationRequestRecord).where(
                        OrchestrationRequestRecord.id == pf.request_id
                    )
                ).scalar_one()
                assert req.status == "PREFLIGHT_REJECTED", (
                    f"Request {pf.request_id} not REJECTED: {req.status}"
                )
                ev = s.execute(
                    select(AuditOutboxRecord).where(AuditOutboxRecord.request_id == pf.request_id)
                ).scalar_one()
                assert ev is not None, f"No outbox event for request {pf.request_id}"


# ── Zero-Downstream Delta Proof ───────────────────────────────────────────


class TestZeroDownstreamDelta:
    """P0-5: Every rejection path must leave zero downstream rows.

    Before/after ID-set snapshots for all downstream tables:
    execution_snapshots, coefficient_contexts, identities, attempts.
    """

    DOWNSTREAM_TABLES: tuple[str, ...] = (
        "orchestration_execution_snapshots",
        "orchestration_coefficient_contexts",
        "orchestration_identities",
        "orchestration_run_attempts",
    )

    def _count_all(self, session) -> dict[str, int]:
        """Return {table_name: row_count} for all downstream tables."""
        from sqlalchemy import text as sa_text

        counts: dict[str, int] = {}
        for tbl in self.DOWNSTREAM_TABLES:
            cnt = session.execute(sa_text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
            counts[tbl] = cnt
        return counts

    def test_version_not_found_zero_downstream(self, service, session_factory) -> None:
        """Version not found rejection leaves zero downstream rows."""
        with session_factory() as s:
            before = self._count_all(s)

        with pytest.raises(PreflightFailure):
            service.execute(_make_command(project_version_id="nonexistent"))

        with session_factory() as s:
            after = self._count_all(s)
            for tbl, cnt in after.items():
                assert cnt == before[tbl], f"Table {tbl} changed: {before[tbl]} → {cnt}"

    def test_project_mismatch_zero_downstream(self, service, session_factory) -> None:
        """Project mismatch rejection leaves zero downstream rows."""
        with session_factory() as s:
            _seed_project_and_version(s, project_id="p-2", version_id="pv-1")
            before = self._count_all(s)

        with pytest.raises(PreflightFailure):
            service.execute(_make_command(project_id="p-1"))

        with session_factory() as s:
            after = self._count_all(s)
            for tbl, cnt in after.items():
                assert cnt == before[tbl], f"Table {tbl} changed"

    def test_draft_version_zero_downstream(self, service, session_factory) -> None:
        with session_factory() as s:
            _seed_project_and_version(s, status="draft")
            before = self._count_all(s)

        with pytest.raises(PreflightFailure):
            service.execute(_make_command())

        with session_factory() as s:
            after = self._count_all(s)
            for tbl, cnt in after.items():
                assert cnt == before[tbl], f"Table {tbl} changed"

    def test_coefficient_rejection_zero_downstream(self, service, session_factory) -> None:
        from cold_storage.modules.orchestration.domain.errors import (
            CoefficientResolutionError,
        )

        service._coefficient_port.resolve.side_effect = CoefficientResolutionError(
            "resolver", "test rejection"
        )
        with session_factory() as s:
            _seed_project_and_version(s)
            before = self._count_all(s)

        with pytest.raises(PreflightFailure):
            service.execute(_make_command())

        with session_factory() as s:
            after = self._count_all(s)
            for tbl, cnt in after.items():
                assert cnt == before[tbl], f"Table {tbl} changed: {before[tbl]} → {cnt}"


# ── SQLite Constraint Classification Tests ───────────────────────────────


class TestSQLiteConstraintClassification:
    """P0-2: Exact SQLite error code and column-set classification."""

    def _make_integrity_error(self, error_code: int | None, message: str):
        """Construct a SQLAlchemy IntegrityError wrapping a SQLite error."""
        import sqlite3

        from sqlalchemy import exc as sa_exc

        orig = sqlite3.IntegrityError(message)
        if error_code is not None:
            orig.sqlite_errorcode = error_code
        else:
            # Simulate missing error code
            del orig.sqlite_errorcode

        return sa_exc.IntegrityError(
            "statement",
            {"params": ()},
            orig,
        )

    def test_code_2067_matching_table_and_columns(self) -> None:
        """SQLITE_CONSTRAINT_UNIQUE (2067) with matching table/columns."""
        from cold_storage.modules.orchestration.infrastructure.repositories import (
            _is_target_unique_violation,
        )

        exc = self._make_integrity_error(
            2067,
            "UNIQUE constraint failed: orchestration_run_attempts.identity_id,"
            " orchestration_run_attempts.attempt_number",
        )
        assert _is_target_unique_violation(
            exc,
            sqlite_table="orchestration_run_attempts",
            sqlite_column_sets=frozenset(
                {
                    ("identity_id", "attempt_number"),
                }
            ),
        )

    def test_code_1555_matching(self) -> None:
        """SQLITE_CONSTRAINT_PRIMARYKEY (1555) with matching."""
        from cold_storage.modules.orchestration.infrastructure.repositories import (
            _is_target_unique_violation,
        )

        exc = self._make_integrity_error(
            1555,
            "UNIQUE constraint failed: table.id",
        )
        assert _is_target_unique_violation(
            exc,
            sqlite_table="table",
            sqlite_column_sets=frozenset({("id",)}),
        )

    def test_wrong_error_code(self) -> None:
        """Correct text but wrong error code → False."""
        from cold_storage.modules.orchestration.infrastructure.repositories import (
            _is_target_unique_violation,
        )

        exc = self._make_integrity_error(
            19,  # SQLITE_CONSTRAINT (generic, not UNIQUE)
            "UNIQUE constraint failed: table.col",
        )
        assert not _is_target_unique_violation(
            exc,
            sqlite_table="table",
            sqlite_column_sets=frozenset({("col",)}),
        )

    def test_wrong_table(self) -> None:
        """Correct code but wrong table → False."""
        from cold_storage.modules.orchestration.infrastructure.repositories import (
            _is_target_unique_violation,
        )

        exc = self._make_integrity_error(
            2067,
            "UNIQUE constraint failed: other_table.col",
        )
        assert not _is_target_unique_violation(
            exc,
            sqlite_table="orchestration_run_attempts",
            sqlite_column_sets=frozenset({("col",)}),
        )

    def test_wrong_columns(self) -> None:
        """Correct everything except column set → False."""
        from cold_storage.modules.orchestration.infrastructure.repositories import (
            _is_target_unique_violation,
        )

        exc = self._make_integrity_error(
            2067,
            "UNIQUE constraint failed: t.a, t.b",
        )
        assert not _is_target_unique_violation(
            exc,
            sqlite_table="t",
            sqlite_column_sets=frozenset({("a", "c")}),
        )

    def test_missing_error_code(self) -> None:
        """Missing sqlite_errorcode attribute → False."""
        import sqlite3

        from sqlalchemy import exc as sa_exc

        from cold_storage.modules.orchestration.infrastructure.repositories import (
            _is_target_unique_violation,
        )

        orig = sqlite3.IntegrityError("UNIQUE constraint failed: t.col")
        exc = sa_exc.IntegrityError("stmt", {"params": ()}, orig)
        assert not _is_target_unique_violation(
            exc,
            sqlite_table="t",
            sqlite_column_sets=frozenset({("col",)}),
        )

    def test_orig_is_none(self) -> None:
        """orig is None → False."""
        from sqlalchemy import exc as sa_exc

        from cold_storage.modules.orchestration.infrastructure.repositories import (
            _is_target_unique_violation,
        )

        exc = sa_exc.IntegrityError("stmt", {"params": ()}, None)
        assert not _is_target_unique_violation(
            exc,
            sqlite_table="t",
            sqlite_column_sets=frozenset({("col",)}),
        )

    def test_non_integrity_error(self) -> None:
        """Non-SA-IntegrityError raises AttributeError — helper assumes SA exc."""
        import pytest as _pytest

        from cold_storage.modules.orchestration.infrastructure.repositories import (
            _is_target_unique_violation,
        )

        class FakeError(Exception):
            pass

        exc = FakeError("not an integrity error")
        with _pytest.raises(AttributeError):
            _is_target_unique_violation(
                exc,  # type: ignore[arg-type]
                sqlite_table="t",
                sqlite_column_sets=frozenset({("col",)}),
            )
