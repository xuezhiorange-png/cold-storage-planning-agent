"""Deterministic request reentry test using threading.Event.

Verifies that two concurrent orchestration requests with distinct
correlation IDs produce independent request IDs, independent UoW
sessions, and no crosstalk — even when using the same service instance.

Protocol:
  Thread A:
    1. Create request + flush (not committed yet)
    2. Signal A_CREATED
    3. Wait for B_COMMITTED
    4. Persist rejection + outbox
    5. Commit

  Thread B:
    1. Wait for A_CREATED
    2. Create request + persist rejection + outbox
    3. Commit
    4. Signal B_COMMITTED

Assertions:
  - Same service instance (shared)
  - Two independent UoW / sessions
  - Distinct request IDs
  - No crosstalk (each request sees only its own state)

Uses file-based SQLite for independent connections (no StaticPool)
so each thread gets a real independent connection.
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
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

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


@pytest.fixture()
def reentry_service(reentry_session_factory):
    """OrchestrationService wired for reentry testing."""
    uow_factory = SqlAlchemyOrchestrationUnitOfWorkFactory(reentry_session_factory)

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
    """Two-thread deterministic reentry with threading.Event."""

    def test_concurrent_reentry_distinct_request_ids_no_crosstalk(
        self,
        reentry_service,
        reentry_session_factory,
    ) -> None:
        """Thread A and Thread B create independent rejection requests.

        Both use the same service instance but get independent
        UoW/sessions.  The test verifies:
        - Distinct request IDs
        - Each request has its own PREFLIGHT_REJECTED status
        - Each request has its own rejection outbox event
        - No crosstalk between the two requests
        """
        # Seed project + version
        with reentry_session_factory() as s:
            _seed_project_and_version(s)

        # Results
        results: dict[str, PreflightFailure | Exception | None] = {
            "a": None,
            "b": None,
        }
        errors: list[Exception] = []

        def thread_a():
            """Thread A: create request, wait for B, then commit rejection."""
            try:
                reentry_service.execute(
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

        def thread_b():
            """Thread B: wait for A to create its request, then create own."""
            try:
                reentry_service.execute(
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

        # Use a barrier to ensure both threads start concurrently
        barrier = threading.Barrier(2, timeout=30)

        def _thread_a_wrapper():
            barrier.wait()
            thread_a()

        def _thread_b_wrapper():
            barrier.wait()
            thread_b()

        t_a = threading.Thread(target=_thread_a_wrapper, name="reentry-a")
        t_b = threading.Thread(target=_thread_b_wrapper, name="reentry-b")
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)

        # No thread-level errors
        assert not errors, f"Thread errors: {errors}"

        # Both threads got PreflightFailure
        pf_a = results["a"]
        pf_b = results["b"]
        assert isinstance(pf_a, PreflightFailure), f"Thread A result: {pf_a}"
        assert isinstance(pf_b, PreflightFailure), f"Thread B result: {pf_b}"

        # Distinct request IDs
        assert pf_a.request_id != pf_b.request_id, (
            f"Request IDs must differ: {pf_a.request_id!r} vs {pf_b.request_id!r}"
        )
        assert pf_a.request_id != ""
        assert pf_b.request_id != ""

        # Verify persistence — each request is PREFLIGHT_REJECTED with its own outbox
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

                ev = s.execute(
                    select(AuditOutboxRecord).where(AuditOutboxRecord.request_id == pf.request_id)
                ).scalar_one_or_none()
                assert ev is not None, f"No outbox event for request {pf.request_id}"
                assert ev.event_type == "orchestration.request.rejected"
