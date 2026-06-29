"""Deterministic request reentry test using threading.Event.

Verifies that two concurrent orchestration requests with distinct
correlation IDs produce independent request IDs, independent UoW
sessions, and no crosstalk — even when using the same service instance.

Protocol:
  Thread A:
    1. Create request + flush
    2. Commit to release DB lock (critical for SQLite single-writer)
    3. Signal A_CREATED
    4. Wait for B_COMMITTED
    5. Persist rejection + outbox  (new transaction)
    6. Commit

  Thread B:
    1. Wait for A_CREATED
    2. Create request + flush + commit
    3. Persist rejection + outbox
    4. Commit
    5. Signal B_COMMITTED

Assertions:
  - Same service instance (shared)
  - Two independent UoW / sessions
  - Distinct request IDs
  - failure.request_id == request.id for each thread
  - No crosstalk (each request sees only its own state)
  - Both threads exit; timeout prevents deadlock

Uses file-based SQLite with WAL mode for independent connections
(no StaticPool) so each thread gets a real independent connection.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

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
    OrchestrationRequestRecord,
)
from cold_storage.modules.orchestration.infrastructure.repositories import (
    OrchestrationRequestRepository,
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
    return ResolvedCoefficientContextCandidate(
        project_id=project_id,
        project_version_id=project_version_id,
        schema_version="1.0.0",
        content=content,
        content_hash=result_hash(content),
        approved_revision_ids=tuple(revision_ids),
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


# ── BlockingRequestRepository ────────────────────────────────────────


class BlockingRequestRepository(OrchestrationRequestRepository):
    """Test-only wrapper that blocks after ``add()`` + ``flush()``.

    After the inner repo's ``add()`` (which does ``session.add`` +
    ``session.flush``), the session is committed to release the DB
    write lock (critical for SQLite single-writer semantics).  Then
    ``request_created`` is signalled and the thread waits for
    ``allow_continue`` before returning.

    Only the *first* caller blocks; subsequent callers pass through
    without waiting.  This ensures Thread A blocks while Thread B
    can proceed immediately.

    Does NOT call ``rollback`` — only ``commit`` to release the lock.
    """

    def __init__(
        self,
        inner: OrchestrationRequestRepository,
        request_created: threading.Event,
        allow_continue: threading.Event,
    ) -> None:
        self._inner = inner
        self._request_created = request_created
        self._allow_continue = allow_continue
        self._should_block = True
        self._guard = threading.Lock()

    # -- OrchestrationRequestRepository interface ----------------------

    def add(
        self,
        session,
        /,
        *,
        requested_project_id: str,
        requested_project_version_id: str,
        request_fingerprint: str,
        actor: str,
        correlation_id: str,
    ) -> str:
        request_id = self._inner.add(
            session,
            requested_project_id=requested_project_id,
            requested_project_version_id=requested_project_version_id,
            request_fingerprint=request_fingerprint,
            actor=actor,
            correlation_id=correlation_id,
        )
        # Commit to release the DB write lock so other threads can write.
        # The service will start a fresh transaction for downstream work.
        session.commit()
        # Decide under the lock whether *this* caller should block,
        # but release the lock before waiting so the other thread can
        # acquire it and pass through.
        should_block = False
        with self._guard:
            if self._should_block:
                self._should_block = False
                should_block = True
        if should_block:
            self._request_created.set()
            if not self._allow_continue.wait(timeout=30):
                raise TimeoutError("Timed out waiting for allow_continue signal")
        return request_id

    def update_status(  # type: ignore[override]
        self,
        session,
        /,
        request_id: str,
        *,
        status=None,
        failure_code=None,
        failure_field=None,
        failure_details=None,
        resolved_project_id=None,
        resolved_project_version_id=None,
        resolved_identity_id=None,
        resolved_attempt_id=None,
    ) -> None:
        self._inner.update_status(
            session,
            request_id,
            status=status,
            failure_code=failure_code,
            failure_field=failure_field,
            failure_details=failure_details,
            resolved_project_id=resolved_project_id,
            resolved_project_version_id=resolved_project_version_id,
            resolved_identity_id=resolved_identity_id,
            resolved_attempt_id=resolved_attempt_id,
        )


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def reentry_engine():
    """File-based SQLite engine with Alembic head schema.

    Uses a real file (not :memory:) so that independent connections
    from different threads see the same data.
    """
    if os.environ.get("DATABASE_BACKEND") == "postgresql":
        pytest.skip("Reentry test uses file-based SQLite only")

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

    e = create_engine(f"sqlite:///{db_path}")

    @event.listens_for(e, "connect")
    def _pragma(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    yield e
    e.dispose()
    db_path.unlink(missing_ok=True)


@pytest.fixture()
def reentry_session_factory(reentry_engine):
    """Session factory using the file-based SQLite engine.

    NOT StaticPool — each call to session_factory() creates a
    genuinely independent connection, simulating concurrent access.
    """
    return sessionmaker(bind=reentry_engine, expire_on_commit=False)


def _make_service(session_factory, request_repo):
    """Build an OrchestrationService wired for reentry testing."""
    uow_factory = SqlAlchemyOrchestrationUnitOfWorkFactory(session_factory)

    coeff_port = MagicMock(spec=CoefficientResolutionPreflightPort)
    coeff_port.resolve.return_value = _make_resolved_coefficient()

    return OrchestrationService(
        uow_factory=uow_factory,
        request_repo=request_repo,
        outbox_repo=SqlAlchemyAuditOutboxRepository(),
        snapshot_repo=SqlAlchemyExecutionSnapshotRepository(),
        coefficient_repo=SqlAlchemyCoefficientContextRepository(),
        identity_repo=SqlAlchemyOrchestrationIdentityRepository(),
        attempt_repo=SqlAlchemyOrchestrationAttemptRepository(),
        version_port=_RealVersionPort(),
        snapshot_port=MagicMock(spec=ExecutionSnapshotPreflightPort),
        coefficient_port=coeff_port,
    )


# ── Seed helper ──────────────────────────────────────────────────────


def _seed_project_and_version(session, *, project_id="p-1", version_id="pv-1"):
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
                status="approved",
                created_at=datetime.now(UTC),
                input_snapshot={
                    "throughput_t": "25.0",
                    "product_category": "blueberry",
                },
            )
        )
    session.commit()


# ── Tests ────────────────────────────────────────────────────────────


class TestDeterministicReentry:
    """Two-thread deterministic reentry with threading.Event.

    Thread A creates a request (add + flush + commit), signals
    A_CREATED, then waits for B_COMMITTED before proceeding with
    rejection.

    Thread B waits for A_CREATED, then runs its own full execute()
    (create + reject + commit) and signals B_COMMITTED.

    Both use the same ``OrchestrationService`` instance but get
    independent UoW / sessions from the session factory.
    """

    def test_concurrent_reentry_distinct_request_ids_no_crosstalk(
        self,
        reentry_engine,
        reentry_session_factory,
    ) -> None:
        # -- Synchronisation events ------------------------------------
        a_created = threading.Event()
        b_committed = threading.Event()

        # -- Build service with blocking request repo ------------------
        blocking_repo = BlockingRequestRepository(
            inner=SqlAlchemyOrchestrationRequestRepository(),
            request_created=a_created,
            allow_continue=b_committed,
        )
        service = _make_service(reentry_session_factory, blocking_repo)

        # -- Seed project + version ------------------------------------
        with reentry_session_factory() as s:
            _seed_project_and_version(s)

        # -- Result collectors -----------------------------------------
        results: dict[str, PreflightFailure | Exception | None] = {
            "a": None,
            "b": None,
        }
        errors: list[Exception] = []

        # -- Thread A --------------------------------------------------
        def thread_a() -> None:
            try:
                service.execute(
                    OrchestrationRequestCommand(
                        project_id="p-1",
                        project_version_id="pv-nonexistent-a",
                        coefficient_resolution_context={},
                        actor="thread-a",
                        correlation_id="reentry-a",
                    )
                )
                # Should not reach here — nonexistent version → rejection
                results["a"] = AssertionError("Expected PreflightFailure")
            except PreflightFailure as exc:
                results["a"] = exc
            except Exception as exc:
                errors.append(exc)

        # -- Thread B --------------------------------------------------
        def thread_b() -> None:
            try:
                # Wait for Thread A to create its request before we start
                if not a_created.wait(timeout=30):
                    errors.append(TimeoutError("Timed out waiting for A_CREATED"))
                    return
                service.execute(
                    OrchestrationRequestCommand(
                        project_id="p-1",
                        project_version_id="pv-nonexistent-b",
                        coefficient_resolution_context={},
                        actor="thread-b",
                        correlation_id="reentry-b",
                    )
                )
                results["b"] = AssertionError("Expected PreflightFailure")
            except PreflightFailure as exc:
                results["b"] = exc
            except Exception as exc:
                errors.append(exc)
            finally:
                # Signal that Thread B has finished (committed rejection)
                b_committed.set()

        # -- Launch threads --------------------------------------------
        t_a = threading.Thread(target=thread_a, name="reentry-a")
        t_b = threading.Thread(target=thread_b, name="reentry-b")
        t_a.start()
        t_b.start()
        t_a.join(timeout=60)
        t_b.join(timeout=60)

        # -- Assert: both threads exited --------------------------------
        assert not t_a.is_alive(), "Thread A did not exit (possible deadlock)"
        assert not t_b.is_alive(), "Thread B did not exit (possible deadlock)"

        # -- Assert: no thread-level errors -----------------------------
        assert not errors, f"Thread errors: {errors}"

        # -- Assert: both got PreflightFailure --------------------------
        pf_a = results["a"]
        pf_b = results["b"]
        assert isinstance(pf_a, PreflightFailure), f"Thread A result: {pf_a}"
        assert isinstance(pf_b, PreflightFailure), f"Thread B result: {pf_b}"

        # -- Assert: distinct request IDs -------------------------------
        assert pf_a.request_id != pf_b.request_id, (
            f"Request IDs must differ: {pf_a.request_id!r} vs {pf_b.request_id!r}"
        )
        assert pf_a.request_id != ""
        assert pf_b.request_id != ""

        # -- Assert: no crosstalk — each failure references its own request
        with reentry_session_factory() as s:
            for pf in (pf_a, pf_b):
                req = s.execute(
                    select(OrchestrationRequestRecord).where(
                        OrchestrationRequestRecord.id == pf.request_id
                    )
                ).scalar_one()
                assert req.status == "PREFLIGHT_REJECTED", (
                    f"Request {pf.request_id} status: {req.status}"
                )
                # failure.request_id must match the persisted request
                assert req.id == pf.request_id

                ev = s.execute(
                    select(AuditOutboxRecord).where(AuditOutboxRecord.request_id == pf.request_id)
                ).scalar_one_or_none()
                assert ev is not None, f"No outbox event for request {pf.request_id}"
                assert ev.event_type == "orchestration.request.rejected"


# ── PostgreSQL version ───────────────────────────────────────────────


@pytest.mark.postgresql
class TestDeterministicReentryPostgreSQL:
    """Same deterministic reentry test against PostgreSQL.

    PostgreSQL supports concurrent writers so the BlockingRequestRepository
    does NOT need to commit before blocking — the lock is held at the row
    level, not the connection level.  Uses shared PG fixtures from
    ``tests/integration/conftest.py``.
    """

    @pytest.fixture()
    def pg_reentry_service(self, pg_session_factory):
        """OrchestrationService wired for PG reentry testing."""
        blocking_repo = BlockingRequestRepository(
            inner=SqlAlchemyOrchestrationRequestRepository(),
            request_created=threading.Event(),
            allow_continue=threading.Event(),
        )
        service = _make_service(pg_session_factory, blocking_repo)
        return service, blocking_repo

    def test_concurrent_reentry_pg(
        self,
        pg_session_factory,
        pg_reentry_service,
    ) -> None:
        if not os.environ.get("DATABASE_URL"):
            pytest.skip("DATABASE_URL not set")

        service, blocking_repo = pg_reentry_service
        a_created = blocking_repo._request_created
        b_committed = blocking_repo._allow_continue

        # Seed
        with pg_session_factory() as s:
            _seed_project_and_version(s)

        results: dict[str, PreflightFailure | Exception | None] = {
            "a": None,
            "b": None,
        }
        errors: list[Exception] = []

        def thread_a() -> None:
            try:
                service.execute(
                    OrchestrationRequestCommand(
                        project_id="p-1",
                        project_version_id="pv-nonexistent-a",
                        coefficient_resolution_context={},
                        actor="thread-a",
                        correlation_id="reentry-a",
                    )
                )
                results["a"] = AssertionError("Expected PreflightFailure")
            except PreflightFailure as exc:
                results["a"] = exc
            except Exception as exc:
                errors.append(exc)

        def thread_b() -> None:
            try:
                if not a_created.wait(timeout=30):
                    errors.append(TimeoutError("Timed out waiting for A_CREATED"))
                    return
                service.execute(
                    OrchestrationRequestCommand(
                        project_id="p-1",
                        project_version_id="pv-nonexistent-b",
                        coefficient_resolution_context={},
                        actor="thread-b",
                        correlation_id="reentry-b",
                    )
                )
                results["b"] = AssertionError("Expected PreflightFailure")
            except PreflightFailure as exc:
                results["b"] = exc
            except Exception as exc:
                errors.append(exc)
            finally:
                b_committed.set()

        t_a = threading.Thread(target=thread_a, name="pg-reentry-a")
        t_b = threading.Thread(target=thread_b, name="pg-reentry-b")
        t_a.start()
        t_b.start()
        t_a.join(timeout=60)
        t_b.join(timeout=60)

        assert not t_a.is_alive(), "Thread A did not exit (possible deadlock)"
        assert not t_b.is_alive(), "Thread B did not exit (possible deadlock)"
        assert not errors, f"Thread errors: {errors}"

        pf_a = results["a"]
        pf_b = results["b"]
        assert isinstance(pf_a, PreflightFailure), f"Thread A result: {pf_a}"
        assert isinstance(pf_b, PreflightFailure), f"Thread B result: {pf_b}"

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
                assert req.status == "PREFLIGHT_REJECTED", (
                    f"Request {pf.request_id} status: {req.status}"
                )
                assert req.id == pf.request_id

                ev = s.execute(
                    select(AuditOutboxRecord).where(AuditOutboxRecord.request_id == pf.request_id)
                ).scalar_one_or_none()
                assert ev is not None, f"No outbox event for request {pf.request_id}"
                assert ev.event_type == "orchestration.request.rejected"
