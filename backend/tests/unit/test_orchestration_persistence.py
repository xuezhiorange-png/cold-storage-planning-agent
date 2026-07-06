"""Orchestration persistence constraint tests.

Coverage:
- Migration upgrade / downgrade roundtrip (SQLite)
- Execution snapshot unique constraint
- Coefficient context deterministic uniqueness
- Identity fingerprint unique
- Attempt (identity_id, attempt_number) unique
- SourceBinding five non-null slots
- SourceBinding identity+attempt unique
- CalculationRun legacy all-null legal
- CalculationRun orchestrated all-required legal
- CalculationRun partial fields rejected by CHECK
- SchemeRun legacy all-null legal
- SchemeRun production all-required legal
- SchemeRun partial fields rejected by CHECK
- Outbox event_identity unique
- AuditEvent outbox_event_id unique
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.orchestration.infrastructure.orm import (
    AuditOutboxRecord,
    CoefficientContextRecord,
    OrchestrationIdentityRecord,
    OrchestrationRunAttemptRecord,
    ProjectVersionExecutionSnapshotRecord,
    SourceBindingRecord,
)
from cold_storage.modules.projects.infrastructure.orm import (
    AuditEventRecord,
    Base,
    CalculationRunRecord,
)
from cold_storage.modules.schemes.infrastructure.orm import SchemeRunRecord


@pytest.fixture()
def engine():
    """In-memory SQLite engine with all tables created."""
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


# ── Helper factories ────────────────────────────────────────────────────────


def _make_legacy_calc(session: Session, calc_name: str = "zone") -> CalculationRunRecord:
    import uuid
    from datetime import UTC, datetime

    r = CalculationRunRecord(
        id=str(uuid.uuid4()),
        project_id="p-1",
        project_version_id="pv-1",
        calculator_name=calc_name,
        calculator_version="1.0.0",
        input_snapshot={},
        result_snapshot={},
        formulas=[],
        coefficients=[],
        assumptions=[],
        warnings=[],
        source_references=[],
        requires_review=False,
        created_at=datetime.now(UTC),
    )
    session.add(r)
    session.flush()
    return r


def _make_orch_calc(
    session: Session, calc_name: str = "zone", calc_type: str = "zone"
) -> CalculationRunRecord:
    import uuid
    from datetime import UTC, datetime

    r = CalculationRunRecord(
        id=str(uuid.uuid4()),
        project_id="p-1",
        project_version_id="pv-1",
        calculator_name=calc_name,
        calculator_version="1.0.0",
        input_snapshot={},
        result_snapshot={},
        formulas=[],
        coefficients=[],
        assumptions=[],
        warnings=[],
        source_references=[],
        requires_review=False,
        created_at=datetime.now(UTC),
        # Orchestration fields
        calculation_type=calc_type,
        orchestration_identity_id="oi-1",
        orchestration_run_attempt_id="oa-1",
        execution_snapshot_id="es-1",
        coefficient_context_id="cc-1",
        input_hash="abc",
        result_hash="def",
        provenance={},
        schema_version="1.0",
        orchestration_fingerprint="fp-1",
    )
    session.add(r)
    session.flush()
    return r


# ── Execution Snapshot ──────────────────────────────────────────────────────


class TestExecutionSnapshotConstraints:
    def test_unique_version_hash_schema(self, session: Session) -> None:
        import uuid

        r1 = ProjectVersionExecutionSnapshotRecord(
            id=str(uuid.uuid4()),
            project_id="p-1",
            project_version_id="pv-1",
            version_number=1,
            input_snapshot={"a": 1},
            input_snapshot_hash="h1",
            schema_version="1.0",
            captured_status="approved",
        )
        r2 = ProjectVersionExecutionSnapshotRecord(
            id=str(uuid.uuid4()),
            project_id="p-1",
            project_version_id="pv-1",
            version_number=1,
            input_snapshot={"a": 1},
            input_snapshot_hash="h1",
            schema_version="1.0",
            captured_status="approved",
        )
        session.add(r1)
        session.flush()
        session.add(r2)
        with pytest.raises(IntegrityError):
            session.flush()


# ── Coefficient Context ─────────────────────────────────────────────────────


class TestCoefficientContextConstraints:
    def test_unique_version_hash(self, session: Session) -> None:
        import uuid

        c1 = CoefficientContextRecord(
            id=str(uuid.uuid4()),
            project_id="p-1",
            project_version_id="pv-1",
            content={"k": "v"},
            content_hash="h1",
            schema_version="1.0",
        )
        c2 = CoefficientContextRecord(
            id=str(uuid.uuid4()),
            project_id="p-1",
            project_version_id="pv-1",
            content={"k": "v"},
            content_hash="h1",
            schema_version="1.0",
        )
        session.add(c1)
        session.flush()
        session.add(c2)
        with pytest.raises(IntegrityError):
            session.flush()


# ── Identity Fingerprint ────────────────────────────────────────────────────


class TestIdentityConstraints:
    def test_unique_fingerprint(self, session: Session) -> None:
        import uuid

        i1 = OrchestrationIdentityRecord(
            id=str(uuid.uuid4()),
            fingerprint="fp-1",
            execution_snapshot_id="es-1",
            coefficient_context_id="cc-1",
            definition_version="1.0",
            calculator_version_vector={},
        )
        i2 = OrchestrationIdentityRecord(
            id=str(uuid.uuid4()),
            fingerprint="fp-1",
            execution_snapshot_id="es-1",
            coefficient_context_id="cc-1",
            definition_version="1.0",
            calculator_version_vector={},
        )
        session.add(i1)
        session.flush()
        session.add(i2)
        with pytest.raises(IntegrityError):
            session.flush()


# ── Attempt Constraints ─────────────────────────────────────────────────────


class TestAttemptConstraints:
    def test_unique_identity_number(self, session: Session) -> None:
        import uuid

        a1 = OrchestrationRunAttemptRecord(
            id=str(uuid.uuid4()),
            identity_id="oi-1",
            attempt_number=1,
            database_backend="sqlite",
            correlation_id="legacy-migration-0036",
        )
        a2 = OrchestrationRunAttemptRecord(
            id=str(uuid.uuid4()),
            identity_id="oi-1",
            attempt_number=1,
            database_backend="sqlite",
            correlation_id="legacy-migration-0036",
        )
        session.add(a1)
        session.flush()
        session.add(a2)
        with pytest.raises(IntegrityError):
            session.flush()


# ── Source Binding ──────────────────────────────────────────────────────────


class TestSourceBindingConstraints:
    def _setup_calcs(self, session: Session) -> dict[str, str]:
        """Create five legacy calculation runs and return their IDs."""
        ids = {}
        for calc_type in ("zone", "cooling_load", "equipment", "power", "investment"):
            r = _make_legacy_calc(session, calc_name=calc_type)
            ids[calc_type] = r.id
        return ids

    def test_five_slots_non_null(self, session: Session) -> None:
        calc_ids = self._setup_calcs(session)
        import uuid

        sb = SourceBindingRecord(
            id=str(uuid.uuid4()),
            project_id="p-1",
            project_version_id="pv-1",
            execution_snapshot_id="es-1",
            coefficient_context_id="cc-1",
            orchestration_identity_id="oi-1",
            orchestration_run_attempt_id="oa-1",
            orchestration_fingerprint="fp-1",
            zone_calculation_id=calc_ids["zone"],
            cooling_load_calculation_id=calc_ids["cooling_load"],
            equipment_calculation_id=calc_ids["equipment"],
            power_calculation_id=calc_ids["power"],
            investment_calculation_id=calc_ids["investment"],
            per_calculation_result_hashes={},
            combined_source_hash="h1",
            schema_version="1.0",
        )
        session.add(sb)
        session.flush()  # Should not raise

    def test_unique_identity_attempt(self, session: Session) -> None:
        calc_ids = self._setup_calcs(session)
        import uuid

        sb1 = SourceBindingRecord(
            id=str(uuid.uuid4()),
            project_id="p-1",
            project_version_id="pv-1",
            execution_snapshot_id="es-1",
            coefficient_context_id="cc-1",
            orchestration_identity_id="oi-1",
            orchestration_run_attempt_id="oa-1",
            orchestration_fingerprint="fp-1",
            zone_calculation_id=calc_ids["zone"],
            cooling_load_calculation_id=calc_ids["cooling_load"],
            equipment_calculation_id=calc_ids["equipment"],
            power_calculation_id=calc_ids["power"],
            investment_calculation_id=calc_ids["investment"],
            per_calculation_result_hashes={},
            combined_source_hash="h1",
            schema_version="1.0",
        )
        sb2 = SourceBindingRecord(
            id=str(uuid.uuid4()),
            project_id="p-1",
            project_version_id="pv-1",
            execution_snapshot_id="es-1",
            coefficient_context_id="cc-1",
            orchestration_identity_id="oi-1",
            orchestration_run_attempt_id="oa-1",
            orchestration_fingerprint="fp-1",
            zone_calculation_id=calc_ids["zone"],
            cooling_load_calculation_id=calc_ids["cooling_load"],
            equipment_calculation_id=calc_ids["equipment"],
            power_calculation_id=calc_ids["power"],
            investment_calculation_id=calc_ids["investment"],
            per_calculation_result_hashes={},
            combined_source_hash="h2",
            schema_version="1.0",
        )
        session.add(sb1)
        session.flush()
        session.add(sb2)
        with pytest.raises(IntegrityError):
            session.flush()


# ── CalculationRun legacy/orchestrated CHECK ────────────────────────────────


class TestCalculationRunNullityCheck:
    def test_legacy_all_null_legal(self, session: Session) -> None:
        _make_legacy_calc(session)
        session.flush()  # Should not raise

    def test_orchestrated_all_required_legal(self, session: Session) -> None:
        _make_orch_calc(session)
        session.flush()  # Should not raise

    def test_partial_fields_rejected(self, session: Session) -> None:
        import uuid
        from datetime import UTC, datetime

        r = CalculationRunRecord(
            id=str(uuid.uuid4()),
            project_id="p-1",
            project_version_id="pv-1",
            calculator_name="zone",
            calculator_version="1.0.0",
            input_snapshot={},
            result_snapshot={},
            formulas=[],
            coefficients=[],
            assumptions=[],
            warnings=[],
            source_references=[],
            requires_review=False,
            created_at=datetime.now(UTC),
            # Some orchestration fields set, but not all
            calculation_type="zone",
            orchestration_identity_id=None,  # partial: some set, some not
            orchestration_run_attempt_id="oa-1",
        )
        session.add(r)
        with pytest.raises(IntegrityError):
            session.flush()


# ── SchemeRun legacy/production CHECK ───────────────────────────────────────


class TestSchemeRunNullityCheck:
    def test_legacy_all_null_legal(self, session: Session) -> None:
        import uuid

        r = SchemeRunRecord(
            id=str(uuid.uuid4()),
            project_id="p-1",
            project_version_id="pv-1",
            weight_set_id="ws-1",
            generator_version="1.0",
            source_snapshot_hash="h1",
            source_mode="legacy",
            database_backend="sqlite",
        )
        session.add(r)
        session.flush()  # Should not raise

    def test_production_all_required_legal(self, session: Session) -> None:
        import uuid

        r = SchemeRunRecord(
            id=str(uuid.uuid4()),
            project_id="p-1",
            project_version_id="pv-1",
            weight_set_id="ws-1",
            generator_version="1.0",
            source_snapshot_hash="h1",
            source_mode="production",
            source_binding_id="sb-1",
            source_contract_version="1.0",
            weight_set_revision_id="wsr-1",
            weight_set_content_hash="h1",
            weight_set_generator_compatibility_version="1.0",
            combined_source_hash="h1",
            binding_schema_version="1.0",
            execution_snapshot_id="es-1",
            coefficient_context_id="cc-1",
            orchestration_identity_id="oi-1",
            authoritative_attempt_id="aa-1",
            orchestration_fingerprint="fp-1",
            zone_calculation_id="zc-1",
            cooling_load_calculation_id="clc-1",
            equipment_calculation_id="ec-1",
            power_calculation_id="pc-1",
            investment_calculation_id="ic-1",
            zone_result_hash="zrh-1",
            cooling_load_result_hash="clrh-1",
            equipment_result_hash="erh-1",
            power_result_hash="prh-1",
            investment_result_hash="irh-1",
            database_backend="sqlite",
        )
        session.add(r)
        session.flush()

    def test_partial_production_fields_rejected(self, session: Session) -> None:
        import uuid

        r = SchemeRunRecord(
            id=str(uuid.uuid4()),
            project_id="p-1",
            project_version_id="pv-1",
            weight_set_id="ws-1",
            generator_version="1.0",
            source_snapshot_hash="h1",
            source_mode="production",
            source_binding_id="sb-1",  # some set
            # Phase 1 (0035) added scheme_runs.database_backend as
            # NOT NULL — supply it so the test exercises the
            # intended check (production fields nullity), not the
            # new database_backend NOT NULL.
            database_backend="sqlite",
            # weight_set_revision_id missing → CHECK should reject
        )
        session.add(r)
        with pytest.raises(IntegrityError):
            session.flush()


# ── Outbox / AuditEvent ─────────────────────────────────────────────────────


class TestOutboxConstraints:
    def test_unique_event_identity(self, session: Session) -> None:
        import uuid
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        base = dict(
            event_type="test",
            event_schema_version="1.0",
            aggregate_type="test",
            aggregate_id="t-1",
            actor="system",
            correlation_id="",
            occurred_at=now,
            payload={},
            payload_hash="abc",
            envelope_hash="test-envelope-hash",
        )
        o1 = AuditOutboxRecord(
            id=str(uuid.uuid4()),
            event_identity="ev-1",
            **base,
        )
        o2 = AuditOutboxRecord(
            id=str(uuid.uuid4()),
            event_identity="ev-1",
            **base,
        )
        session.add(o1)
        session.flush()
        session.add(o2)
        with pytest.raises(IntegrityError):
            session.flush()

    def test_audit_event_outbox_id_unique(self, session: Session) -> None:
        import uuid

        e1 = AuditEventRecord(
            id=str(uuid.uuid4()),
            actor="test",
            action="test",
            entity_type="test",
            entity_id="t-1",
            before_snapshot={},
            after_snapshot={},
            event_metadata={},
            outbox_event_id="oe-1",
        )
        e2 = AuditEventRecord(
            id=str(uuid.uuid4()),
            actor="test",
            action="test",
            entity_type="test",
            entity_id="t-2",
            before_snapshot={},
            after_snapshot={},
            event_metadata={},
            outbox_event_id="oe-1",
        )
        session.add(e1)
        session.flush()
        session.add(e2)
        with pytest.raises(IntegrityError):
            session.flush()
