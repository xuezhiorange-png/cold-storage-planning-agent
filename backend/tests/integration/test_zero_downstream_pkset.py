"""Zero-downstream PK-set proof for ALL rejection paths.

For every rejection path, this test:
  1. Captures PK sets for downstream tables BEFORE the rejection.
  2. Triggers the rejection.
  3. Captures PK sets AFTER the rejection.
  4. Asserts after == before (no new downstream rows).
  5. Asserts exactly one new rejected request.
  6. Asserts exactly one new rejection outbox event.
  7. Asserts no new accepted outbox events.

Downstream tables monitored:
  - orchestration_execution_snapshots
  - orchestration_coefficient_contexts
  - orchestration_identities
  - orchestration_run_attempts
  - calculation_runs
  - orchestration_source_bindings
  - orchestration_audit_outbox (accepted subset)

Rejection paths covered:
  - version missing (ProjectVersionNotFoundError)
  - version status mismatch (draft → ProjectVersionNotReadyError)
  - version status mismatch (archived → ProjectVersionArchivedError)
  - snapshot preflight failure (ExecutionSnapshotSchemaError)
  - coefficient resolver failure (CoefficientResolutionError)
  - required set failure (CoefficientNotApprovedError → missing codes)
  - candidate project_id mismatch (CoefficientResolutionError)
  - candidate project_version_id mismatch (CoefficientResolutionError)
  - candidate content_hash mismatch (CoefficientResolutionError)
  - candidate content schema mismatch (CoefficientResolutionError)
  - duplicate revision IDs (AmbiguousCoefficientError)
  - empty revision IDs (CoefficientNotApprovedError)
  - unsupported coefficient schema (CoefficientResolutionError)
  - live attempt conflict (AttemptAlreadyRunningError)

Uses PostgreSQL fixtures from conftest.py for real constraint enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    SourceBindingRecord,
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
    CalculationRunRecord,
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


# ── Bad-candidate helpers ─────────────────────────────────────────────


def _make_resolved_coefficient_bad_project_id() -> ResolvedCoefficientContextCandidate:
    """Candidate with mismatched project_id."""
    return _make_resolved_coefficient(project_id="wrong-project-id")


def _make_resolved_coefficient_bad_version_id() -> ResolvedCoefficientContextCandidate:
    """Candidate with mismatched project_version_id."""
    return _make_resolved_coefficient(project_version_id="wrong-version-id")


def _make_resolved_coefficient_bad_hash() -> ResolvedCoefficientContextCandidate:
    """Candidate with mismatched content_hash."""
    candidate = _make_resolved_coefficient()
    return ResolvedCoefficientContextCandidate(
        project_id=candidate.project_id,
        project_version_id=candidate.project_version_id,
        schema_version=candidate.schema_version,
        content=candidate.content,
        content_hash="wrong-hash-value",
        approved_revision_ids=candidate.approved_revision_ids,
    )


def _make_resolved_coefficient_content_schema_mismatch() -> ResolvedCoefficientContextCandidate:
    """Candidate where content schema_version != candidate schema_version."""
    candidate = _make_resolved_coefficient()
    new_content = dict(candidate.content)
    new_content["schema_version"] = "2.0.0"
    return ResolvedCoefficientContextCandidate(
        project_id=candidate.project_id,
        project_version_id=candidate.project_version_id,
        schema_version="1.0.0",
        content=new_content,
        content_hash=result_hash(new_content),
        approved_revision_ids=candidate.approved_revision_ids,
    )


def _make_resolved_coefficient_unsupported_schema() -> ResolvedCoefficientContextCandidate:
    """Candidate with unsupported coefficient schema version."""
    candidate = _make_resolved_coefficient()
    new_content = dict(candidate.content)
    new_content["schema_version"] = "99.0.0"
    return ResolvedCoefficientContextCandidate(
        project_id=candidate.project_id,
        project_version_id=candidate.project_version_id,
        schema_version="99.0.0",
        content=new_content,
        content_hash=result_hash(new_content),
        approved_revision_ids=candidate.approved_revision_ids,
    )


def _make_resolved_coefficient_duplicate_revisions() -> ResolvedCoefficientContextCandidate:
    """Candidate with duplicate approved_revision_ids."""
    candidate = _make_resolved_coefficient()
    rev_ids = candidate.approved_revision_ids
    duped = rev_ids + (rev_ids[0],)
    return ResolvedCoefficientContextCandidate(
        project_id=candidate.project_id,
        project_version_id=candidate.project_version_id,
        schema_version=candidate.schema_version,
        content=candidate.content,
        content_hash=candidate.content_hash,
        approved_revision_ids=duped,
    )


def _make_resolved_coefficient_empty_revisions() -> ResolvedCoefficientContextCandidate:
    """Candidate with empty approved_revision_ids."""
    candidate = _make_resolved_coefficient()
    return ResolvedCoefficientContextCandidate(
        project_id=candidate.project_id,
        project_version_id=candidate.project_version_id,
        schema_version=candidate.schema_version,
        content=candidate.content,
        content_hash=candidate.content_hash,
        approved_revision_ids=(),
    )


# ── PK-set snapshot dataclass ────────────────────────────────────────


@dataclass
class DownstreamPkSnapshot:
    """Snapshot of PK sets for all monitored downstream tables."""

    execution_snapshots: set[str]
    coefficient_contexts: set[str]
    identities: set[str]
    attempts: set[str]
    outbox: set[str]
    requests: set[str]
    calculation_runs: set[str]
    source_bindings: set[str]
    accepted_outbox: set[str]


def _snapshot_pk_sets(session: Session) -> DownstreamPkSnapshot:
    """Capture PK sets for all downstream tables."""
    return DownstreamPkSnapshot(
        execution_snapshots=set(
            session.execute(select(ProjectVersionExecutionSnapshotRecord.id)).scalars().all()
        ),
        coefficient_contexts=set(
            session.execute(select(CoefficientContextRecord.id)).scalars().all()
        ),
        identities=set(session.execute(select(OrchestrationIdentityRecord.id)).scalars().all()),
        attempts=set(session.execute(select(OrchestrationRunAttemptRecord.id)).scalars().all()),
        outbox=set(session.execute(select(AuditOutboxRecord.id)).scalars().all()),
        requests=set(session.execute(select(OrchestrationRequestRecord.id)).scalars().all()),
        calculation_runs=set(session.execute(select(CalculationRunRecord.id)).scalars().all()),
        source_bindings=set(session.execute(select(SourceBindingRecord.id)).scalars().all()),
        accepted_outbox=set(
            session.execute(
                select(AuditOutboxRecord.id).where(
                    AuditOutboxRecord.event_type == "orchestration.request.accepted"
                )
            )
            .scalars()
            .all()
        ),
    )


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
    before: DownstreamPkSnapshot,
    pf: PreflightFailure,
) -> None:
    """Assert that after == before for all downstream tables,
    exactly one new rejected request, one new rejection outbox,
    and no new accepted outbox events."""
    with pg_session_factory() as s:
        after = _snapshot_pk_sets(s)

        # Zero new downstream rows
        for table_name in (
            "execution_snapshots",
            "coefficient_contexts",
            "identities",
            "attempts",
            "calculation_runs",
            "source_bindings",
        ):
            before_set = getattr(before, table_name)
            after_set = getattr(after, table_name)
            assert after_set == before_set, (
                f"Table {table_name}: new rows detected: {after_set - before_set}"
            )

        # No new accepted outbox events
        assert after.accepted_outbox == before.accepted_outbox, (
            f"New accepted outbox events detected: {after.accepted_outbox - before.accepted_outbox}"
        )

        # Exactly one new request (the rejected one)
        new_requests = after.requests - before.requests
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
        new_outbox = after.outbox - before.outbox
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


class TestZeroDownstreamCandidateMismatch:
    """Candidate identity/hash/schema mismatches → zero downstream + rejection."""

    def test_candidate_project_id_mismatch(self, pg_zd_service, pg_session_factory) -> None:
        """Candidate project_id != command project_id → rejection."""
        pg_zd_service._coefficient_port.resolve.return_value = (
            _make_resolved_coefficient_bad_project_id()
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

    def test_candidate_project_version_id_mismatch(self, pg_zd_service, pg_session_factory) -> None:
        """Candidate project_version_id != command project_version_id → rejection."""
        pg_zd_service._coefficient_port.resolve.return_value = (
            _make_resolved_coefficient_bad_version_id()
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

    def test_candidate_content_hash_mismatch(self, pg_zd_service, pg_session_factory) -> None:
        """Candidate content_hash != result_hash(content) → rejection."""
        pg_zd_service._coefficient_port.resolve.return_value = _make_resolved_coefficient_bad_hash()
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

    def test_candidate_content_schema_mismatch(self, pg_zd_service, pg_session_factory) -> None:
        """Content schema_version != candidate schema_version → rejection."""
        pg_zd_service._coefficient_port.resolve.return_value = (
            _make_resolved_coefficient_content_schema_mismatch()
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


class TestZeroDownstreamRevisionIdValidation:
    """Revision ID validation failures → zero downstream + rejection."""

    def test_duplicate_revision_ids(self, pg_zd_service, pg_session_factory) -> None:
        """Duplicate approved_revision_ids → AmbiguousCoefficientError → rejection."""
        pg_zd_service._coefficient_port.resolve.return_value = (
            _make_resolved_coefficient_duplicate_revisions()
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

    def test_empty_revision_ids(self, pg_zd_service, pg_session_factory) -> None:
        """Empty approved_revision_ids → CoefficientNotApprovedError → rejection."""
        pg_zd_service._coefficient_port.resolve.return_value = (
            _make_resolved_coefficient_empty_revisions()
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


class TestZeroDownstreamUnsupportedScope:
    """Unsupported coefficient schema → zero downstream + rejection."""

    def test_unsupported_coefficient_schema(self, pg_zd_service, pg_session_factory) -> None:
        """Unsupported coefficient schema version → CoefficientResolutionError → rejection."""
        pg_zd_service._coefficient_port.resolve.return_value = (
            _make_resolved_coefficient_unsupported_schema()
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


class TestZeroDownstreamLiveAttemptConflict:
    """Live RUNNING attempt → AttemptAlreadyRunningError → zero downstream + rejection."""

    def test_live_attempt_conflict(self, pg_zd_service, pg_session_factory) -> None:
        """Second request with same identity while first attempt is RUNNING."""
        with pg_session_factory() as s:
            _seed_project_and_version(s)

        # First request succeeds — creates identity + RUNNING attempt
        result = pg_zd_service.execute(_make_command())
        assert isinstance(result, PreflightAccepted)

        # Capture state after the successful request
        with pg_session_factory() as s:
            before = _snapshot_pk_sets(s)

        # Second request should fail — live attempt blocks acquisition
        with pytest.raises(PreflightFailure) as pf_exc:
            pg_zd_service.execute(_make_command())

        _assert_zero_downstream_and_one_rejection(
            pg_session_factory=pg_session_factory,
            before=before,
            pf=pf_exc.value,
        )
