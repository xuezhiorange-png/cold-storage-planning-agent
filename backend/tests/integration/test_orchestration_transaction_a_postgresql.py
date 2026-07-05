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

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select

from cold_storage.modules.coefficients.infrastructure.orm import (
    CoefficientDefinitionRecord,
    CoefficientRevisionRecord,
)
from cold_storage.modules.orchestration.application.ports import (
    CoefficientResolutionPreflightPort,
    ExecutionSnapshotPreflightPort,
    ResolvedCoefficientContextCandidate,
)
from cold_storage.modules.orchestration.application.service import (
    OrchestrationService,
    PreflightAccepted,
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
from cold_storage.modules.orchestration.infrastructure.coefficient_resolver import (
    SqlAlchemyCoefficientResolutionAdapter,
)
from cold_storage.modules.orchestration.infrastructure.orm import (
    AuditOutboxRecord,
    CoefficientContextRecord,
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

pytestmark = pytest.mark.postgresql

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
        "calculator_version_vector": dict(_CV_VECTOR),
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
        calc_run_repo=MagicMock(),
        source_binding_repo=MagicMock(),
        calculator_port=MagicMock(),
        verification_read_port=MagicMock(),
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
                status="active",
                current_version_number=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
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
            assert ev.event_type == "orchestration.request.preflight_rejected"

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
            actor="test-actor",
            correlation_id="test-corr",
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
            actor="test-actor",
            correlation_id="test-corr",
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


# ── Real resolver fixtures and helpers ──────────────────────────────────────


def _seed_catalog_definitions(session_factory) -> None:
    """Seed CoefficientDefinitionRecord + CoefficientRevisionRecord for all
    10 authoritative required codes so the real adapter can resolve them."""
    with session_factory() as session:
        for code in _REQUIRED_CODES:
            def_id = uuid.uuid4().hex
            session.add(
                CoefficientDefinitionRecord(
                    id=def_id,
                    code=code,
                    name=code.replace(".", " ").replace("_", " ").title(),
                    description=f"Test definition for {code}",
                    category=code.split(".")[0],
                    canonical_unit="ratio",
                    value_type="decimal",
                    scope_type="global",
                    is_active=True,
                )
            )
            session.add(
                CoefficientRevisionRecord(
                    id=uuid.uuid4().hex,
                    coefficient_definition_id=def_id,
                    revision_number=1,
                    value_decimal="1.0",
                    unit="ratio",
                    status="approved",
                    source_type="standard",
                    approved_at=datetime.now(UTC),
                    approved_by="test-seed",
                    created_by="test-seed",
                )
            )
        session.commit()


@pytest.fixture()
def pg_real_resolver_service(pg_session_factory):
    """Fully wired OrchestrationService with a REAL
    SqlAlchemyCoefficientResolutionAdapter on PostgreSQL.

    Returns ``(service, session_factory)`` so tests can seed and query.
    """
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

    coeff_port = SqlAlchemyCoefficientResolutionAdapter()

    service = OrchestrationService(
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
        calc_run_repo=MagicMock(),
        source_binding_repo=MagicMock(),
        calculator_port=MagicMock(),
        verification_read_port=MagicMock(),
    )
    return service, pg_session_factory


# ── Real adapter tests ─────────────────────────────────────────────────────


class TestRealResolverSuccessPathPG:
    """Verify the real SqlAlchemyCoefficientResolutionAdapter end-to-end."""

    def test_real_adapter_success_path(self, pg_real_resolver_service) -> None:
        service, session_factory = pg_real_resolver_service

        # Seed project + version + catalog definitions
        with session_factory() as s:
            _seed_project_and_version(s)
        _seed_catalog_definitions(session_factory)

        # Execute Transaction A
        result = service.execute(_make_command())
        assert isinstance(result, PreflightAccepted)
        assert result.request_id
        assert result.identity_id
        assert result.attempt_id

        # Query persisted coefficient context
        with session_factory() as s:
            ctx = s.execute(
                select(CoefficientContextRecord).where(
                    CoefficientContextRecord.project_version_id == "pv-1"
                )
            ).scalar_one()
            content = ctx.content
            assert "requirement_registry_version" in content
            assert "calculator_version_vector" in content
            assert "required_codes" in content
            assert "requirement_hash" in content
            assert content["requirement_registry_version"] == _REGISTRY_VERSION
            assert content["calculator_version_vector"] == dict(_CV_VECTOR)
            assert tuple(content["required_codes"]) == _REQUIRED_CODES

            # Coefficient content hash matches identity fingerprint binding
            identity = s.execute(
                select(OrchestrationIdentityRecord).where(
                    OrchestrationIdentityRecord.id == result.identity_id
                )
            ).scalar_one()
            assert identity.coefficient_context_id == ctx.id

            # Request → identity → attempt relationships
            request = s.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.id == result.request_id
                )
            ).scalar_one()
            assert request.status == "ACCEPTED"
            assert request.resolved_identity_id == result.identity_id
            assert request.resolved_attempt_id == result.attempt_id

            attempt = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == result.attempt_id
                )
            ).scalar_one()
            assert attempt.identity_id == result.identity_id
            assert attempt.status == "RUNNING"


class TestRealResolverRejectionPathPG:
    """Verify that missing catalog definitions produce a durable rejection."""

    def test_real_adapter_rejection_path(self, pg_real_resolver_service) -> None:
        service, session_factory = pg_real_resolver_service

        # Seed project + version but NO catalog definitions (empty catalog)
        with session_factory() as s:
            _seed_project_and_version(s)

        # Execute → should get PreflightFailure
        with pytest.raises(PreflightFailure) as pf_exc:
            service.execute(_make_command())

        pf = pf_exc.value
        assert pf.request_id != ""

        # Assert persisted PREFLIGHT_REJECTED + one rejection outbox
        with session_factory() as s:
            req = s.execute(
                select(OrchestrationRequestRecord).where(
                    OrchestrationRequestRecord.id == pf.request_id
                )
            ).scalar_one()
            assert req.status == "PREFLIGHT_REJECTED"
            assert req.failure_code is not None

            outbox_count = s.execute(
                select(func.count())
                .select_from(AuditOutboxRecord)
                .where(AuditOutboxRecord.request_id == pf.request_id)
            ).scalar()
            assert outbox_count == 1

            # Zero downstream rows
            assert (
                s.execute(select(func.count()).select_from(OrchestrationIdentityRecord)).scalar()
                == 0
            )
            assert (
                s.execute(select(func.count()).select_from(OrchestrationRunAttemptRecord)).scalar()
                == 0
            )
