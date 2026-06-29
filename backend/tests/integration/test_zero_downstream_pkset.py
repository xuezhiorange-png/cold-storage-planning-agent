"""Zero-downstream PK-set proof for ALL rejection paths.

For every rejection path, this test:
  1. Captures PK sets for downstream tables BEFORE the rejection.
  2. Triggers the rejection.
  3. Captures PK sets AFTER the rejection.
  4. Asserts after == before (no new downstream rows).
  5. Asserts exactly one new rejected request.
  6. Asserts exactly one new rejection outbox event.

Downstream tables monitored:
  - orchestration_execution_snapshots
  - orchestration_coefficient_contexts
  - orchestration_identities
  - orchestration_run_attempts
  - orchestration_audit_outbox

Rejection paths covered:
  - version missing (ProjectVersionNotFoundError)
  - version status mismatch (draft → ProjectVersionNotReadyError)
  - version status mismatch (archived → ProjectVersionArchivedError)
  - snapshot preflight failure (ExecutionSnapshotSchemaError)
  - coefficient resolver failure (CoefficientResolutionError)
  - required set failure (CoefficientNotApprovedError → missing codes)

Uses PostgreSQL fixtures from conftest.py for real constraint enforcement.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

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
from cold_storage.modules.orchestration.domain.errors import (
    CoefficientNotApprovedError,
    CoefficientResolutionError,
    ExecutionSnapshotSchemaError,
)
from cold_storage.modules.orchestration.domain.fingerprint import result_hash
from cold_storage.modules.orchestration.infrastructure.orm import (
    AuditOutboxRecord,
    CoefficientContextRecord,
    OrchestrationIdentityRecord,
    OrchestrationRequestRecord,
    OrchestrationRunAttemptRecord,
    ProjectVersionExecutionSnapshotRecord,
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


# ── PK-set snapshot helper ────────────────────────────────────────────


def _snapshot_pk_sets(session: Session) -> dict[str, set[str]]:
    """Capture PK sets for all downstream tables."""
    return {
        "execution_snapshots": set(
            session.execute(select(ProjectVersionExecutionSnapshotRecord.id)).scalars().all()
        ),
        "coefficient_contexts": set(
            session.execute(select(CoefficientContextRecord.id)).scalars().all()
        ),
        "identities": set(session.execute(select(OrchestrationIdentityRecord.id)).scalars().all()),
        "attempts": set(session.execute(select(OrchestrationRunAttemptRecord.id)).scalars().all()),
        "outbox": set(session.execute(select(AuditOutboxRecord.id)).scalars().all()),
        "requests": set(session.execute(select(OrchestrationRequestRecord.id)).scalars().all()),
    }


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def pg_zd_service(pg_session_factory):
    """OrchestrationService with default passing mocks."""
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
                input_snapshot={
                    "throughput_t": "25.0",
                    "product_category": "blueberry",
                },
            )
        )
    session.commit()


def _make_command(
    project_id: str = "p-1",
    project_version_id: str = "pv-1",
) -> OrchestrationRequestCommand:
    return OrchestrationRequestCommand(
        project_id=project_id,
        project_version_id=project_version_id,
        coefficient_resolution_context={},
        actor="test-actor",
        correlation_id="corr-1",
    )


def _assert_zero_downstream_and_one_rejection(
    *,
    pg_session_factory,
    before: dict[str, set[str]],
    pf: PreflightFailure,
) -> None:
    """Assert that after == before for all downstream tables,
    exactly one new rejected request, and one new rejection outbox."""
    with pg_session_factory() as s:
        after = _snapshot_pk_sets(s)

        # Zero new downstream rows
        for table in (
            "execution_snapshots",
            "coefficient_contexts",
            "identities",
            "attempts",
        ):
            assert after[table] == before[table], (
                f"Table {table}: new rows detected: {after[table] - before[table]}"
            )

        # Exactly one new request (the rejected one)
        new_requests = after["requests"] - before["requests"]
        assert len(new_requests) == 1, (
            f"Expected 1 new request, got {len(new_requests)}: {new_requests}"
        )
        new_request_id = new_requests.pop()
        assert new_request_id == pf.request_id

        req = s.execute(
            select(OrchestrationRequestRecord).where(
                OrchestrationRequestRecord.id == new_request_id
            )
        ).scalar_one()
        assert req.status == "PREFLIGHT_REJECTED"
        assert req.failure_code is not None

        # Exactly one new outbox event (the rejection event)
        new_outbox = after["outbox"] - before["outbox"]
        assert len(new_outbox) == 1, f"Expected 1 new outbox, got {len(new_outbox)}: {new_outbox}"
        new_outbox_id = new_outbox.pop()
        ev = s.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == new_outbox_id)
        ).scalar_one()
        assert ev.event_type == "orchestration.request.rejected"
        assert ev.request_id == new_request_id


# ── Tests ────────────────────────────────────────────────────────────


class TestZeroDownstreamVersionMissing:
    """Version not found → zero downstream + rejection."""

    def test_version_not_found(self, pg_zd_service, pg_session_factory) -> None:
        with pg_session_factory() as s:
            before = _snapshot_pk_sets(s)

        with pytest.raises(PreflightFailure) as pf_exc:
            pg_zd_service.execute(_make_command(project_version_id="nonexistent"))

        _assert_zero_downstream_and_one_rejection(
            pg_session_factory=pg_session_factory,
            before=before,
            pf=pf_exc.value,
        )


class TestZeroDownstreamVersionStatus:
    """Version status mismatch → zero downstream + rejection."""

    def test_draft_version(self, pg_zd_service, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _seed_project_and_version(s, status="draft")
            before = _snapshot_pk_sets(s)

        with pytest.raises(PreflightFailure) as pf_exc:
            pg_zd_service.execute(_make_command())

        _assert_zero_downstream_and_one_rejection(
            pg_session_factory=pg_session_factory,
            before=before,
            pf=pf_exc.value,
        )

    def test_archived_version(self, pg_zd_service, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _seed_project_and_version(s, status="archived")
            before = _snapshot_pk_sets(s)

        with pytest.raises(PreflightFailure) as pf_exc:
            pg_zd_service.execute(_make_command())

        _assert_zero_downstream_and_one_rejection(
            pg_session_factory=pg_session_factory,
            before=before,
            pf=pf_exc.value,
        )


class TestZeroDownstreamSnapshotFailure:
    """Snapshot preflight failure → zero downstream + rejection."""

    def test_snapshot_schema_error(self, pg_zd_service, pg_session_factory) -> None:
        pg_zd_service._snapshot_port.validate_candidate.side_effect = ExecutionSnapshotSchemaError(
            "v9.9.9"
        )
        with pg_session_factory() as s:
            _seed_project_and_version(s)
            before = _snapshot_pk_sets(s)

        with pytest.raises(PreflightFailure) as pf_exc:
            pg_zd_service.execute(_make_command())

        _assert_zero_downstream_and_one_rejection(
            pg_session_factory=pg_session_factory,
            before=before,
            pf=pf_exc.value,
        )


class TestZeroDownstreamResolverFailure:
    """Coefficient resolver failure → zero downstream + rejection."""

    def test_coefficient_resolution_error(self, pg_zd_service, pg_session_factory) -> None:
        pg_zd_service._coefficient_port.resolve.side_effect = CoefficientResolutionError(
            "resolver", "catalog down"
        )
        with pg_session_factory() as s:
            _seed_project_and_version(s)
            before = _snapshot_pk_sets(s)

        with pytest.raises(PreflightFailure) as pf_exc:
            pg_zd_service.execute(_make_command())

        _assert_zero_downstream_and_one_rejection(
            pg_session_factory=pg_session_factory,
            before=before,
            pf=pf_exc.value,
        )

    def test_coefficient_not_approved_error(self, pg_zd_service, pg_session_factory) -> None:
        pg_zd_service._coefficient_port.resolve.side_effect = CoefficientNotApprovedError(
            "missing.code"
        )
        with pg_session_factory() as s:
            _seed_project_and_version(s)
            before = _snapshot_pk_sets(s)

        with pytest.raises(PreflightFailure) as pf_exc:
            pg_zd_service.execute(_make_command())

        _assert_zero_downstream_and_one_rejection(
            pg_session_factory=pg_session_factory,
            before=before,
            pf=pf_exc.value,
        )


class TestZeroDownstreamRequiredSetFailure:
    """Required set failures → zero downstream + rejection.

    These are triggered by _validate_coefficient_candidate after
    the resolver returns a candidate with structural issues.
    """

    def test_project_mismatch(self, pg_zd_service, pg_session_factory) -> None:
        """Version belongs to a different project → rejection."""
        with pg_session_factory() as s:
            _seed_project_and_version(s, project_id="p-2", version_id="pv-1")
            before = _snapshot_pk_sets(s)

        with pytest.raises(PreflightFailure) as pf_exc:
            pg_zd_service.execute(_make_command(project_id="p-1"))

        _assert_zero_downstream_and_one_rejection(
            pg_session_factory=pg_session_factory,
            before=before,
            pf=pf_exc.value,
        )
