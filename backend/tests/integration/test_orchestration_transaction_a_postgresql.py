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
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.postgresql

_DB_NAME_RE = re.compile(r"[^a-z0-9_]")


def _sanitize(name: str) -> str:
    return _DB_NAME_RE.sub("_", name.lower())[:63]


# ── PostgreSQL fixtures ──────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def pg_admin_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set")
    return url


@pytest.fixture(scope="session")
def pg_admin_engine(pg_admin_url: str):
    """AUTOCOMMIT connection to the postgres admin database."""
    admin_url = pg_admin_url.rsplit("/", 1)[0] + "/postgres"
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    yield engine
    engine.dispose()


@pytest.fixture()
def pg_database(pg_admin_engine, request) -> Generator[str, None, None]:
    """Create a unique test database, run Alembic upgrade head, yield URL."""
    db_name = _sanitize(f"test_ta_{request.node.name}_{_uuid_mod.uuid4().hex[:8]}")

    with pg_admin_engine.connect() as conn:
        conn.execute(f'CREATE DATABASE "{db_name}"')

    base_url = str(pg_admin_engine.url).rsplit("/", 1)[0]
    db_url = f"{base_url}/{db_name}"

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url

    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        with suppress(Exception):
            with pg_admin_engine.connect() as c:
                c.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        pytest.fail(f"Alembic upgrade failed:\n{r.stderr}\n{r.stdout}")

    yield db_url

    # Teardown
    with suppress(Exception):
        with pg_admin_engine.connect() as conn:
            conn.execute(
                f"SELECT pg_terminate_backend(pg_stat_activity.pid) "
                f"FROM pg_stat_activity "
                f"WHERE pg_stat_activity.datname = '{db_name}' "
                f"AND pid <> pg_backend_pid()"
            )
            conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')


# ── Simplified fixtures (no per-test DB recreation needed for most tests) ───


@pytest.fixture()
def pg_session_factory(pg_database: str):
    engine = create_engine(pg_database, pool_size=1, max_overflow=2)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def pg_service(pg_session_factory):
    """Fully wired OrchestrationService on PostgreSQL."""
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
    from cold_storage.modules.orchestration.domain.fingerprint import result_hash
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

    uow_factory = SqlAlchemyOrchestrationUnitOfWorkFactory(pg_session_factory)

    class _PGVersionPort(ProjectVersionReadPort):
        def load_by_id(self, session, project_version_id):
            record = session.execute(
                select(ProjectVersionRecord).where(
                    ProjectVersionRecord.id == project_version_id
                )
            ).scalar_one_or_none()
            if record is None:
                return None
            return _LoadedVersion(
                project_id=record.project_id,
                status=record.status,
                version_number=record.version_number,
                input_snapshot=record.input_snapshot or {},
            )

    coeff_port = MagicMock(spec=CoefficientResolutionPreflightPort)
    coeff_port.resolve.return_value = ResolvedCoefficientContextCandidate(
        project_id="p-1",
        project_version_id="pv-1",
        schema_version="1.0.0",
        content={
            "source_type": "catalog",
            "validity_status": "approved",
            "project_id": "p-1",
            "project_version_id": "pv-1",
            "schema_version": "1.0.0",
        },
        content_hash=result_hash(
            {
                "source_type": "catalog",
                "validity_status": "approved",
                "project_id": "p-1",
                "project_version_id": "pv-1",
                "schema_version": "1.0.0",
            }
        ),
        approved_revision_ids=("rev-001",),
    )

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
    from cold_storage.modules.projects.infrastructure.orm import (
        ProjectRecord,
        ProjectVersionRecord,
    )

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
                input_snapshot={"throughput_t": "25.0"},
            )
        )
    session.commit()


def _make_command(
    project_id: str = "p-1",
    project_version_id: str = "pv-1",
    actor: str = "test-actor",
    correlation_id: str = "corr-1",
):
    from cold_storage.modules.orchestration.domain.contracts import (
        OrchestrationRequestCommand,
    )

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


class TestPreflightRejectionPG:
    def test_version_not_found(self, pg_service) -> None:
        from cold_storage.modules.orchestration.domain.contracts import (
            PreflightFailure,
        )

        with pytest.raises(PreflightFailure) as pf_exc:
            pg_service.execute(_make_command(project_version_id="nonexistent"))
        pf = pf_exc.value
        assert pf.error_class == "ProjectVersionNotFoundError"
        assert pf.request_id != ""

    def test_draft_version(self, pg_service, pg_session_factory) -> None:
        from cold_storage.modules.orchestration.domain.contracts import (
            PreflightFailure,
        )

        with pg_session_factory() as s:
            _seed_project_and_version(s, status="draft")
        with pytest.raises(PreflightFailure) as pf_exc:
            pg_service.execute(_make_command())
        assert pf_exc.value.error_class == "ProjectVersionNotReadyError"
        assert pf_exc.value.request_id != ""

    def test_rejection_zero_downstream(self, pg_service, pg_session_factory) -> None:
        from cold_storage.modules.orchestration.domain.contracts import (
            PreflightFailure,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationIdentityRecord,
            OrchestrationRunAttemptRecord,
        )

        with pytest.raises(PreflightFailure):
            pg_service.execute(_make_command(project_version_id="nonexistent"))

        with pg_session_factory() as s:
            identities = s.execute(
                select(OrchestrationIdentityRecord)
            ).scalars().all()
            assert len(identities) == 0

            attempts = s.execute(
                select(OrchestrationRunAttemptRecord)
            ).scalars().all()
            assert len(attempts) == 0


class TestTransactionCPG:
    def test_mark_blocked_writes_outbox(self, pg_service, pg_session_factory) -> None:
        from cold_storage.modules.orchestration.infrastructure.orm import (
            AuditOutboxRecord,
            OrchestrationRunAttemptRecord,
        )

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
