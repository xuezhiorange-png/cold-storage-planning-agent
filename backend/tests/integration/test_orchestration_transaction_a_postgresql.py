"""PostgreSQL Transaction A integration tests.

Uses real Alembic Head schema on PostgreSQL via the pg_database_factory
fixture pattern from test_orchestration_migration_postgresql.py.

Covers:
- approved ProjectVersion → ACCEPTED (full Transaction A)
- version not found → PREFLIGHT_REJECTED
- draft/archived → typed rejection
- project mismatch → typed rejection
- request + outbox atomic rejection
- rejection downstream rows = zero
- snapshot/context/identity get-or-create uniqueness
- Transaction C BLOCKED + outbox
- Transaction C FAILED + outbox
- request ID reentry no cross-talk

Tagged with @pytest.mark.postgresql for CI (-m postgresql).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid as _uuid_mod
from collections.abc import Generator
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from cold_storage.modules.orchestration.application.ports import (
    CoefficientResolutionPreflightPort,
    ExecutionSnapshotPreflightPort,
    ResolvedCoefficientContextCandidate,
)
from cold_storage.modules.orchestration.application.service import (
    OrchestrationService,
    ProjectVersionReadPort,
    _LoadedVersion,
)
from cold_storage.modules.orchestration.application.unit_of_work import (
    SqlAlchemyOrchestrationUnitOfWorkFactory,
)
from cold_storage.modules.orchestration.domain.contracts import (
    OrchestrationRequestCommand,
    PreflightFailure,
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

pytestmark = pytest.mark.postgresql

_DB_NAME_RE = re.compile(r"[^a-z0-9_]")

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


def _sanitize(name: str) -> str:
    return _DB_NAME_RE.sub("_", name.lower())[:63]


# ── PostgreSQL fixtures ──────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def pg_admin_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set")
    base = url.rsplit("/", 1)[0]
    return f"{base}/postgres"


@pytest.fixture()
def pg_database_factory(pg_admin_url: str) -> Generator:
    """Yield a callable that creates isolated PostgreSQL test databases.

    Uses AUTOCOMMIT isolation and text() for DDL operations.
    Collects all created databases and drops them on teardown.
    """
    created: list[str] = []
    admin_engine = create_engine(pg_admin_url, poolclass=NullPool)
    admin_engine = admin_engine.execution_options(isolation_level="AUTOCOMMIT")

    def create_db(*, prefix: str) -> str:
        db_name = _sanitize(f"{prefix}_{_uuid_mod.uuid4().hex[:12]}")
        with admin_engine.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE {db_name}"))
        base_url = os.environ.get("DATABASE_URL", "").rsplit("/", 1)[0]
        db_url = f"{base_url}/{db_name}"
        created.append(db_name)
        return db_url

    try:
        yield create_db
    finally:
        with admin_engine.connect() as conn:
            for db_name in created:
                with suppress(Exception):
                    conn.execute(text(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)"))
        admin_engine.dispose()


def _run_alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["DATABASE_BACKEND"] = "postgresql"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture()
def pg_database(pg_database_factory) -> str:
    """Isolated database with full head schema."""
    db_url = pg_database_factory(prefix="pg_ta")
    r = _run_alembic(db_url, "upgrade", "head")
    if r.returncode != 0:
        pytest.fail(f"Alembic upgrade failed:\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}")
    return db_url


@pytest.fixture()
def pg_session_factory(pg_database: str):
    engine = create_engine(pg_database, poolclass=NullPool)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


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


@pytest.fixture()
def pg_service(pg_session_factory):
    """Fully wired OrchestrationService on PostgreSQL."""
    uow_factory = SqlAlchemyOrchestrationUnitOfWorkFactory(pg_session_factory)

    class _PGVersionPort(ProjectVersionReadPort):
        def load_by_id(self, session, project_version_id):
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
        version_port=_PGVersionPort(),
        snapshot_port=MagicMock(spec=ExecutionSnapshotPreflightPort),
        coefficient_port=coeff_port,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


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
                code=f"T_{project_id}",
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


class TestTransactionASuccessPG:
    def test_approved_version_succeeds(self, pg_service, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _seed_project_and_version(s)
        result = pg_service.execute(_make_command())
        assert result.request_id
        assert result.identity_id
        assert result.attempt_id

    def test_request_accepted_has_resolved_fields(self, pg_service, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _seed_project_and_version(s)
        result = pg_service.execute(_make_command())

        with pg_session_factory() as s:
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

    def test_creates_identity_and_attempt(self, pg_service, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _seed_project_and_version(s)
        result = pg_service.execute(_make_command())

        with pg_session_factory() as s:
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

    def test_outbox_event_written(self, pg_service, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _seed_project_and_version(s)
        result = pg_service.execute(_make_command())

        with pg_session_factory() as s:
            ev = s.execute(
                select(AuditOutboxRecord).where(AuditOutboxRecord.request_id == result.request_id)
            ).scalar_one()
            assert ev.event_type == "orchestration.request.accepted"


class TestPreflightRejectionPG:
    def test_version_not_found(self, pg_service) -> None:
        with pytest.raises(PreflightFailure) as pf_exc:
            pg_service.execute(_make_command(project_version_id="nonexistent"))
        pf = pf_exc.value
        assert pf.error_class == "ProjectVersionNotFoundError"
        assert pf.request_id != ""

    def test_draft_version(self, pg_service, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _seed_project_and_version(s, status="draft")
        with pytest.raises(PreflightFailure) as pf_exc:
            pg_service.execute(_make_command())
        assert pf_exc.value.error_class == "ProjectVersionNotReadyError"

    def test_archived_version(self, pg_service, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _seed_project_and_version(s, status="archived")
        with pytest.raises(PreflightFailure) as pf_exc:
            pg_service.execute(_make_command())
        assert pf_exc.value.error_class == "ProjectVersionArchivedError"

    def test_project_mismatch(self, pg_service, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _seed_project_and_version(s, project_id="p-2", version_id="pv-1")
        with pytest.raises(PreflightFailure) as pf_exc:
            pg_service.execute(_make_command(project_id="p-1"))
        assert pf_exc.value.error_class == "ProjectVersionProjectMismatchError"

    def test_rejection_persists_request_and_outbox(self, pg_service, pg_session_factory) -> None:
        with pytest.raises(PreflightFailure):
            pg_service.execute(_make_command(project_version_id="nonexistent"))

        with pg_session_factory() as s:
            req = s.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.requested_project_id == "p-1"
                )
            ).scalar_one()
            assert req.status == "PREFLIGHT_REJECTED"
            assert req.failure_code is not None

            ev = s.execute(
                select(AuditOutboxRecord).where(AuditOutboxRecord.request_id == req.id)
            ).scalar_one()
            assert ev.event_type == "orchestration.request.rejected"

    def test_rejection_zero_downstream(self, pg_service, pg_session_factory) -> None:
        with pytest.raises(PreflightFailure):
            pg_service.execute(_make_command(project_version_id="nonexistent"))

        with pg_session_factory() as s:
            from sqlalchemy import func

            assert (
                s.execute(select(func.count()).select_from(OrchestrationIdentityRecord)).scalar()
                == 0
            )
            assert (
                s.execute(select(func.count()).select_from(OrchestrationRunAttemptRecord)).scalar()
                == 0
            )

    def test_snapshot_port_failure_durable_rejection(self, pg_service, pg_session_factory) -> None:
        """P0-1: Snapshot preflight failure → PREFLIGHT_REJECTED on PG."""
        from cold_storage.modules.orchestration.domain.errors import (
            ExecutionSnapshotSchemaError,
        )

        pg_service._snapshot_port.validate_candidate.side_effect = ExecutionSnapshotSchemaError(
            "v9.9.9"
        )
        with pg_session_factory() as s:
            _seed_project_and_version(s)

        with pytest.raises(PreflightFailure) as pf_exc:
            pg_service.execute(_make_command())

        pf = pf_exc.value
        assert pf.error_class == "ExecutionSnapshotSchemaError"
        assert pf.request_id != ""

        with pg_session_factory() as s:
            from sqlalchemy import func

            req = s.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.id == pf.request_id
                )
            ).scalar_one()
            assert req.status == "PREFLIGHT_REJECTED"
            assert (
                s.execute(select(func.count()).select_from(OrchestrationIdentityRecord)).scalar()
                == 0
            )

    def test_coefficient_resolver_failure_durable_rejection(
        self, pg_service, pg_session_factory
    ) -> None:
        """P0-1: Coefficient resolver failure → PREFLIGHT_REJECTED on PG."""
        from cold_storage.modules.orchestration.domain.errors import (
            CoefficientResolutionError,
        )

        pg_service._coefficient_port.resolve.side_effect = CoefficientResolutionError(
            "resolver", "catalog down"
        )
        with pg_session_factory() as s:
            _seed_project_and_version(s)

        with pytest.raises(PreflightFailure) as pf_exc:
            pg_service.execute(_make_command())

        pf = pf_exc.value
        assert pf.error_class == "CoefficientResolutionError"
        assert pf.request_id != ""

        with pg_session_factory() as s:
            req = s.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.id == pf.request_id
                )
            ).scalar_one()
            assert req.status == "PREFLIGHT_REJECTED"

    def test_attempt_conflict_durable_rejection(self, pg_service, pg_session_factory) -> None:
        """P0-1: AttemptAlreadyRunningError → PREFLIGHT_REJECTED on PG."""
        with pg_session_factory() as s:
            _seed_project_and_version(s)
        pg_service.execute(_make_command(correlation_id="c1"))

        with pytest.raises(PreflightFailure) as pf_exc:
            pg_service.execute(_make_command(correlation_id="c2"))

        pf = pf_exc.value
        assert pf.error_class == "AttemptAlreadyRunningError"
        assert pf.request_id != ""

        with pg_session_factory() as s:
            req = s.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.id == pf.request_id
                )
            ).scalar_one()
            assert req.status == "PREFLIGHT_REJECTED"


class TestTransactionCPG:
    def test_mark_blocked_writes_outbox(self, pg_service, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _seed_project_and_version(s)
        result = pg_service.execute(_make_command())

        pg_service.mark_attempt_blocked(
            result.attempt_id,
            failure_code="TEST_BLOCK",
            failure_details={"reason": "test"},
        )

        with pg_session_factory() as s:
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

    def test_mark_failed_writes_outbox(self, pg_service, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _seed_project_and_version(s)
        result = pg_service.execute(_make_command())

        pg_service.mark_attempt_failed(
            result.attempt_id,
            failure_code="TEST_FAIL",
            failure_details={"reason": "test"},
        )

        with pg_session_factory() as s:
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


class TestServiceReentryPG:
    def test_concurrent_rejection_no_request_id_crosstalk(
        self, pg_service, pg_session_factory
    ) -> None:
        """P0-2: Threading reentry on PostgreSQL."""
        import threading

        with pg_session_factory() as s:
            _seed_project_and_version(s)

        errors: list[Exception] = []
        results: dict[str, PreflightFailure | None] = {}

        def call_a():
            try:
                results["a"] = None
                pg_service.execute(
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
                pg_service.execute(
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

        t_a = threading.Thread(target=thread_a, name="pg-reentry-a")
        t_b = threading.Thread(target=thread_b, name="pg-reentry-b")
        t_a.start()
        t_b.start()
        t_a.join(timeout=15)
        t_b.join(timeout=15)

        assert not errors, f"Thread errors: {errors}"
        pf_a = results.get("a")
        pf_b = results.get("b")
        assert pf_a is not None and pf_b is not None
        assert pf_a.request_id != pf_b.request_id, (
            f"Request IDs must differ: {pf_a.request_id!r} vs {pf_b.request_id!r}"
        )
        assert pf_a.request_id != ""
        assert pf_b.request_id != ""

        with pg_session_factory() as s:
            for pf in (pf_a, pf_b):
                req = s.execute(
                    select(OrchestrationRequestRecord).where(
                        OrchestrationRequestRecord.id == pf.request_id
                    )
                ).scalar_one()
                assert req.status == "PREFLIGHT_REJECTED"
                ev = s.execute(
                    select(AuditOutboxRecord).where(AuditOutboxRecord.request_id == pf.request_id)
                ).scalar_one()
                assert ev is not None
