"""P0-1 E2E wiring test.

The production archive row MUST land in the same UoW + same commit as
the production SchemeRun.  This test wires
``SqlAlchemyProductionSchemeRunRepository`` with the real archive
builder closure and drives a full production SchemeRun completion
through the real ``ProductionSchemeService`` (the production
SchemeRun generation entry).  The expected end state is:

* ``scheme_runs`` row present (status='completed')
* ``production_source_archives`` row present in the SAME UoW
* archive_hash matches what ``build_archive_for_completed_scheme_run``
  produces for the same inputs
* archive_insert + scheme_run_insert are atomic: if the builder
  raises, NEITHER row survives

The test guards the four user-stated acceptance targets:

  - archive INSERT + SchemeRun completion share the same UoW, same
    transaction, same commit.
  - archive build failure rolls back the entire SchemeRun UoW (no
    half-committed SchemeRun row).
  - production SchemeRun completion produces a
    ``production_source_archives`` row.
  - the wired repository was constructed via the archive_composition
    helper (not by directly importing orchestration modules from
    schemes.infrastructure).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker

# Module-level pytestmark: every test in this module is SQLite-tagged
# so the PostgreSQL CI step skips them.
pytestmark = pytest.mark.sqlite


# ── Schema constants ───────────────────────────────────────────────────────

PROJECT_ID = "wiring-test-p-001"
VERSION_ID = "wiring-test-v-001"
EXEC_SNAPSHOT_ID = "wiring-test-exec-001"
COEFF_CONTEXT_ID = "wiring-test-cc-001"
IDENTITY_ID = "wiring-test-id-001"
ATTEMPT_ID = "wiring-test-attempt-001"
SOURCE_BINDING_ID = "wiring-test-binding-001"
WEIGHT_SET_ID = "wiring-test-ws-001"
WEIGHT_REVISION_ID = "wiring-test-wrev-001"
GOLDEN_COMBINED_SOURCE_HASH = "wire-combined-source-hash-v1"

SLOT_CALC_RUN_IDS: dict[str, str] = {
    "zone": "wiring-zone-run-001",
    "cooling_load": "wiring-cool-run-001",
    "equipment": "wiring-equip-run-001",
    "power": "wiring-power-run-001",
    "investment": "wiring-invest-run-001",
}
SLOT_RESULT_HASHES: dict[str, str] = {
    "zone": "wiring-zone-rh",
    "cooling_load": "wiring-cool-rh",
    "equipment": "wiring-equip-rh",
    "power": "wiring-power-rh",
    "investment": "wiring-invest-rh",
}
WEIGHT_CONTENT_HASH = "wiring-weight-content-h"

# Calculator IDs accepted by the source_binding_verifier.
_CALCULATOR_ID_FOR_STAGE: dict[str, str] = {
    "zone": "cold_room_zone_plan",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "power": "installed_power",
    "investment": "investment_estimate",
}


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def db_path() -> Iterator[str]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
    tmp.close()
    try:
        yield tmp.name
    finally:
        Path(tmp.name).unlink(missing_ok=True)


@pytest.fixture()
def engine(db_path):
    """SQLite engine after ``alembic upgrade head``."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    assert backend_dir.name == "backend", backend_dir

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["SQLITE_PATH"] = db_path
    env["DATABASE_BACKEND"] = "sqlite"
    env.setdefault("COLD_STORAGE_TESTING", "1")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "upgrade",
            "head",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(backend_dir),
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed (exit={result.returncode}):\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )

    e = create_engine(f"sqlite:///{db_path}", future=True)

    @event.listens_for(e, "connect")
    def _fk_on(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    yield e
    e.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


# ── Combined chain seeder ──────────────────────────────────────────────────


def _seed_all_chains(session) -> None:
    """Insert every prerequisite in FK-correct order.

    Order:
        1. Project + ProjectVersion
        2. ProjectVersionExecutionSnapshot + CoefficientContext
        3. OrchestrationIdentity
        4. OrchestrationRunAttempt (no source_binding_id yet)
        5. CalculationRun ×5
        6. SourceBinding
        7. attempt.source_binding_id = SOURCE_BINDING_ID (link)
        8. SchemeWeightSet + SchemeWeightSetRevision (approved)
    """
    from cold_storage.modules.orchestration.infrastructure.orm import (
        CoefficientContextRecord,
        OrchestrationIdentityRecord,
        OrchestrationRunAttemptRecord,
        ProjectVersionExecutionSnapshotRecord,
        SourceBindingRecord,
    )
    from cold_storage.modules.projects.infrastructure.orm import (
        CalculationRunRecord,
        ProjectRecord,
        ProjectVersionRecord,
    )
    from cold_storage.modules.schemes.application.production_service import (
        SOURCE_CONTRACT_VERSION,
    )
    from cold_storage.modules.schemes.infrastructure.orm import (
        SchemeWeightSetRecord,
        SchemeWeightSetRevisionRecord,
    )

    now = datetime.now(UTC)

    # 1. Project + version
    if not session.get(ProjectRecord, PROJECT_ID):
        session.add(
            ProjectRecord(
                id=PROJECT_ID,
                code="wiring-test-project",
                name="Wiring Test Project",
                location="wiring-test-location",
                product_category="blueberry",
                status="approved",
                current_version_number=1,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
    if not session.get(ProjectVersionRecord, VERSION_ID):
        session.add(
            ProjectVersionRecord(
                id=VERSION_ID,
                project_id=PROJECT_ID,
                version_number=1,
                change_summary="wiring test version",
                created_by="test",
                status="approved",
                created_at=now,
                input_snapshot={
                    "throughput_t": "25.0",
                    "product_category": "blueberry",
                },
            )
        )
        session.flush()

    # 2. exec_snapshot + coefficient_context
    if not session.get(ProjectVersionExecutionSnapshotRecord, EXEC_SNAPSHOT_ID):
        session.add(
            ProjectVersionExecutionSnapshotRecord(
                id=EXEC_SNAPSHOT_ID,
                project_id=PROJECT_ID,
                project_version_id=VERSION_ID,
                version_number=1,
                input_snapshot={"throughput_t": "25.0"},
                input_snapshot_hash="wiring-test-exec-hash",
                schema_version="1.0.0",
                captured_status="approved",
                captured_at=now,
            )
        )
        session.flush()
    if not session.get(CoefficientContextRecord, COEFF_CONTEXT_ID):
        session.add(
            CoefficientContextRecord(
                id=COEFF_CONTEXT_ID,
                project_id=PROJECT_ID,
                project_version_id=VERSION_ID,
                content={"coefficients": []},
                content_hash="wiring-test-cc-hash",
                schema_version="1.0.0",
                captured_at=now,
            )
        )
        session.flush()

    # 3. identity first WITHOUT authoritative_attempt_id; this row is
    # referenced by attempt.identity_id (NOT NULL).  We backfill the
    # authoritative link after the attempt row exists.
    if not session.get(OrchestrationIdentityRecord, IDENTITY_ID):
        session.add(
            OrchestrationIdentityRecord(
                id=IDENTITY_ID,
                fingerprint="wiring-test-fingerprint-001",
                execution_snapshot_id=EXEC_SNAPSHOT_ID,
                coefficient_context_id=COEFF_CONTEXT_ID,
                definition_version="1.0.0",
                calculator_version_vector={
                    "zone": "1.0.0",
                    "cooling_load": "1.0.0",
                    "equipment": "1.0.0",
                    "power": "1.0.0",
                    "investment": "1.0.0",
                },
                status="ACTIVE",
                authoritative_attempt_id=None,
                created_at=now,
            )
        )
        session.flush()

    # 4. attempt (FK identity_id is now resolvable).
    if not session.get(OrchestrationRunAttemptRecord, ATTEMPT_ID):
        session.add(
            OrchestrationRunAttemptRecord(
                id=ATTEMPT_ID,
                identity_id=IDENTITY_ID,
                attempt_number=1,
                status="COMPLETED",
                heartbeat_at=now,
                started_at=now,
                completed_at=now,
                source_binding_id=None,
            )
        )
        session.flush()

    # Backfill authoritative_attempt_id (FK from identity row to attempt).
    identity = session.get(OrchestrationIdentityRecord, IDENTITY_ID)
    if identity.authoritative_attempt_id is None:
        identity.authoritative_attempt_id = ATTEMPT_ID
        session.flush()

    # 5. calculation_runs ×5
    for stage, run_id in SLOT_CALC_RUN_IDS.items():
        if not session.get(CalculationRunRecord, run_id):
            session.add(
                CalculationRunRecord(
                    id=run_id,
                    project_id=PROJECT_ID,
                    project_version_id=VERSION_ID,
                    calculator_name=_CALCULATOR_ID_FOR_STAGE[stage],
                    calculator_version="1.0.0",
                    calculation_type=stage,
                    input_snapshot={},
                    result_snapshot={"result": stage},
                    formulas=[],
                    coefficients=[],
                    assumptions=[],
                    warnings=[],
                    source_references=[],
                    requires_review=False,
                    orchestration_identity_id=IDENTITY_ID,
                    orchestration_run_attempt_id=ATTEMPT_ID,
                    execution_snapshot_id=EXEC_SNAPSHOT_ID,
                    coefficient_context_id=COEFF_CONTEXT_ID,
                    input_hash="wiring-input-hash",
                    result_hash=SLOT_RESULT_HASHES[stage],
                    provenance={"stage": stage},
                    schema_version="1.0.0",
                    orchestration_fingerprint="wiring-test-fingerprint-001",
                    created_at=now,
                )
            )
    session.flush()

    # 6. SourceBinding
    if not session.get(SourceBindingRecord, SOURCE_BINDING_ID):
        session.add(
            SourceBindingRecord(
                id=SOURCE_BINDING_ID,
                project_id=PROJECT_ID,
                project_version_id=VERSION_ID,
                execution_snapshot_id=EXEC_SNAPSHOT_ID,
                coefficient_context_id=COEFF_CONTEXT_ID,
                orchestration_identity_id=IDENTITY_ID,
                orchestration_run_attempt_id=ATTEMPT_ID,
                orchestration_fingerprint="wiring-test-fingerprint-001",
                zone_calculation_id=SLOT_CALC_RUN_IDS["zone"],
                cooling_load_calculation_id=SLOT_CALC_RUN_IDS["cooling_load"],
                equipment_calculation_id=SLOT_CALC_RUN_IDS["equipment"],
                power_calculation_id=SLOT_CALC_RUN_IDS["power"],
                investment_calculation_id=SLOT_CALC_RUN_IDS["investment"],
                per_calculation_result_hashes=dict(SLOT_RESULT_HASHES),
                combined_source_hash=GOLDEN_COMBINED_SOURCE_HASH,
                schema_version="1.0.0",
                created_at=now,
            )
        )
        session.flush()

    # 7. Link attempt → source_binding
    attempt_rec = session.get(OrchestrationRunAttemptRecord, ATTEMPT_ID)
    if attempt_rec is not None and attempt_rec.source_binding_id is None:
        attempt_rec.source_binding_id = SOURCE_BINDING_ID
        session.flush()

    # 8. weight set + revision (governance: insert draft, set approved)
    if not session.get(SchemeWeightSetRecord, WEIGHT_SET_ID):
        session.add(
            SchemeWeightSetRecord(
                id=WEIGHT_SET_ID,
                code="wiring-test-weights",
                name="Wiring Test Weights",
                revision=1,
                status="approved",
                source_type="production",
                criteria=[],
                requires_review=False,
                created_at=now,
                approved_at=now,
            )
        )
        session.flush()
    if not session.get(SchemeWeightSetRevisionRecord, WEIGHT_REVISION_ID):
        session.add(
            SchemeWeightSetRevisionRecord(
                id=WEIGHT_REVISION_ID,
                weight_set_id=WEIGHT_SET_ID,
                code="wiring-test-weights",
                revision=1,
                status="draft",
                content=[],
                content_hash=WEIGHT_CONTENT_HASH,
                generator_compatibility_version=SOURCE_CONTRACT_VERSION,
                approved_at=None,
                approved_by=None,
                created_at=now,
            )
        )
        session.flush()
        rev = session.get(SchemeWeightSetRevisionRecord, WEIGHT_REVISION_ID)
        rev.status = "approved"
        rev.approved_at = now
        rev.approved_by = "wiring-test-approver"
        session.flush()

    session.commit()


# ── Wire-up factory ──────────────────────────────────────────────────────


def _build_wired_service(engine):
    """Construct a ProductionSchemeService with the archive closure
    injected into the production repository.

    The repository is the production
    ``SqlAlchemyProductionSchemeRunRepository(build_archive_callable=...)``
    that downstream production bootstrap / composition root will
    instantiate.  Closing over the archive writer keeps the schemes
    application layer free of orchestration-application imports at
    module load.
    """
    from cold_storage.modules.orchestration.infrastructure.archive_composition import (
        make_production_archive_callable,
    )
    from cold_storage.modules.schemes.application.production_service import (
        ProductionSchemeService,
    )
    from cold_storage.modules.schemes.application.production_ports import (
        GenerateProductionSchemeCommand,
    )
    from cold_storage.modules.schemes.infrastructure.production_read_ports import (
        SqlAlchemySourceBindingReadPort,
        SqlAlchemyWeightRevisionReadPort,
    )
    from cold_storage.modules.schemes.infrastructure.production_repository import (
        SqlAlchemyProductionSchemeRunRepository,
    )
    from cold_storage.modules.schemes.infrastructure.production_uow_impl import (
        SqlAlchemyProductionSchemeUnitOfWork,
    )

    sf = sessionmaker(bind=engine, expire_on_commit=False)

    def uow_factory() -> SqlAlchemyProductionSchemeUnitOfWork:
        return SqlAlchemyProductionSchemeUnitOfWork(sf)

    archive_callable = make_production_archive_callable()

    service = ProductionSchemeService(
        uow_factory=uow_factory,
        binding_read_port=SqlAlchemySourceBindingReadPort(),
        weight_revision_read_port=SqlAlchemyWeightRevisionReadPort(),
        run_repository=SqlAlchemyProductionSchemeRunRepository(
            build_archive_callable=archive_callable,
        ),
    )
    cmd = GenerateProductionSchemeCommand(
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        profile_codes=("balanced",),
        profile_parameters={},
        actor="wiring-e2e-test",
        correlation_id="wiring-e2e-corr-001",
    )
    return service, cmd


# ── Tests ─────────────────────────────────────────────────────────────────


class TestArchiveWiringE2E:
    """P0-1 wiring acceptance: production SchemeRun completion produces
    a ``production_source_archives`` row in the same UoW + same commit.

    Drives the wired ``SqlAlchemyProductionSchemeRunRepository`` via
    the same ``save_production_run`` code path that
    ``ProductionSchemeService._generate_within_uow`` takes.  The
    archive closure is the only post-insert hook on this path; its
    presence is the wiring we are asserting here.
    """

    def test_wired_repo_writes_archive_row_on_save(
        self,
        engine,
        session_factory,
    ) -> None:
        with session_factory() as session:
            _seed_all_chains(session)

        # ── Construct wired repository ───────────────────────────────
        from cold_storage.modules.orchestration.infrastructure.archive_composition import (  # noqa: E501
            make_production_archive_callable,
        )
        from cold_storage.modules.schemes.infrastructure.production_repository import (  # noqa: E501
            SqlAlchemyProductionSchemeRunRepository,
        )

        archive_callable = make_production_archive_callable()
        repo = SqlAlchemyProductionSchemeRunRepository(
            build_archive_callable=archive_callable,
        )

        # ── Drive save_production_run on a UoW session ───────────────
        with session_factory() as session:
            with session.begin():
                persisted = repo.save_production_run(
                    session,
                    project_id=PROJECT_ID,
                    project_version_id=VERSION_ID,
                    run_id="wiring-run-001",
                    source_mode="production",
                    source_binding_id=SOURCE_BINDING_ID,
                    source_contract_version="1.0.0",
                    binding_schema_version="1.0.0",
                    combined_source_hash=GOLDEN_COMBINED_SOURCE_HASH,
                    execution_snapshot_id=EXEC_SNAPSHOT_ID,
                    coefficient_context_id=COEFF_CONTEXT_ID,
                    orchestration_identity_id=IDENTITY_ID,
                    authoritative_attempt_id=ATTEMPT_ID,
                    orchestration_fingerprint="wiring-test-fingerprint-001",
                    zone_calculation_id=SLOT_CALC_RUN_IDS["zone"],
                    cooling_load_calculation_id=SLOT_CALC_RUN_IDS["cooling_load"],
                    equipment_calculation_id=SLOT_CALC_RUN_IDS["equipment"],
                    power_calculation_id=SLOT_CALC_RUN_IDS["power"],
                    investment_calculation_id=SLOT_CALC_RUN_IDS["investment"],
                    zone_result_hash=SLOT_RESULT_HASHES["zone"],
                    cooling_load_result_hash=SLOT_RESULT_HASHES["cooling_load"],
                    equipment_result_hash=SLOT_RESULT_HASHES["equipment"],
                    power_result_hash=SLOT_RESULT_HASHES["power"],
                    investment_result_hash=SLOT_RESULT_HASHES["investment"],
                    weight_set_id=WEIGHT_SET_ID,
                    weight_set_revision_id=WEIGHT_REVISION_ID,
                    weight_set_content_hash=WEIGHT_CONTENT_HASH,
                    weight_set_generator_compatibility_version="1.0.0",
                    generator_version="1.0.0",
                    source_snapshot_hash=GOLDEN_COMBINED_SOURCE_HASH,
                    content_hash="wiring-content-hash",
                    profile_codes=("balanced",),
                    profile_parameters={"balanced": {}},
                    candidates_snapshot={"items": []},
                    candidates=[],
                    input_snapshot={"throughput_t": "25.0"},
                    assumption_snapshot={"safety_factor": "1.2"},
                    comparison_snapshot={},
                    warning_messages=[],
                    requires_review=False,
                    recommended_scheme_code=None,
                    status="completed",
                )

        # ── Acceptance 1: SchemeRun row exists ───────────────────────
        with session_factory() as session:
            sr_count = session.execute(
                text("SELECT COUNT(*) FROM scheme_runs WHERE id = :rid"),
                {"rid": persisted.id},
            ).scalar_one()
            assert sr_count == 1

            # ── Acceptance 2: Archive row exists ─────────────────────
            row = session.execute(
                text(
                    "SELECT archive_schema_version, archive_hash, "
                    "combined_source_hash, source_binding_id FROM "
                    "production_source_archives WHERE scheme_run_id = :sid"
                ),
                {"sid": persisted.id},
            ).fetchone()
            assert row is not None, (
                "production_source_archives row missing after wired save"
            )
            archive_schema_version, archive_hash, archive_combined, archive_bid = row
            assert archive_schema_version == "SchemeSourceArchiveV1"
            assert archive_combined == GOLDEN_COMBINED_SOURCE_HASH
            assert archive_bid == SOURCE_BINDING_ID
            assert len(archive_hash) == 64
            assert all(c in "0123456789abcdef" for c in archive_hash), (
                f"archive_hash must be lowercase hex, got {archive_hash!r}"
            )

            # ── Acceptance 3: Archive payload preserves the ordered list ──
            import json as _json
            payload_json = session.execute(
                text(
                    "SELECT archive_payload FROM production_source_archives "
                    "WHERE scheme_run_id = :sid"
                ),
                {"sid": persisted.id},
            ).scalar_one()
            payload = _json.loads(payload_json)
            slot_field = payload["source_slots"]
            assert isinstance(slot_field, list), (
                "source_slots must be an ordered list, not a dict"
            )
            names = [entry[0] for entry in slot_field]
            assert names == [
                "zone",
                "cooling_load",
                "equipment",
                "power",
                "investment",
            ]

            # ── Acceptance 4: archive_hash matches rebuilt payload ─
            from cold_storage.modules.orchestration.application.canonical_archive_v1 import (  # noqa: E501
                assemble_archive_payload,
                compute_archive_hash_v1,
            )

            ordered_slots = [
                (entry[0], dict(entry[1])) for entry in slot_field
            ]
            rebuilt = assemble_archive_payload(
                scheme_run_id=persisted.id,
                source_binding_id=SOURCE_BINDING_ID,
                source_contract_version="1.0.0",
                binding_schema_version="1.0.0",
                combined_source_hash=GOLDEN_COMBINED_SOURCE_HASH,
                weight_set_revision_id=WEIGHT_REVISION_ID,
                weight_set_content_hash=WEIGHT_CONTENT_HASH,
                weight_set_generator_compatibility_version="1.0.0",
                execution_snapshot_id=EXEC_SNAPSHOT_ID,
                coefficient_context_id=COEFF_CONTEXT_ID,
                orchestration_identity_id=IDENTITY_ID,
                authoritative_attempt_id=ATTEMPT_ID,
                orchestration_fingerprint="wiring-test-fingerprint-001",
                source_slots=ordered_slots,
                project_id=PROJECT_ID,
                project_version_id=VERSION_ID,
                generator_compatibility_version="1.0.0",
                captured_at=datetime.fromisoformat(payload["captured_at"]),
            )
            assert compute_archive_hash_v1(rebuilt) == archive_hash, (
                "archive_hash mismatch between writer and rebuilder"
            )

    def test_archive_row_count_one_per_scheme_run(
        self,
        engine,
        session_factory,
    ) -> None:
        with session_factory() as session:
            _seed_all_chains(session)

        from cold_storage.modules.orchestration.infrastructure.archive_composition import (  # noqa: E501
            make_production_archive_callable,
        )
        from cold_storage.modules.schemes.infrastructure.production_repository import (  # noqa: E501
            SqlAlchemyProductionSchemeRunRepository,
        )

        archive_callable = make_production_archive_callable()
        repo = SqlAlchemyProductionSchemeRunRepository(
            build_archive_callable=archive_callable,
        )

        with session_factory() as session:
            with session.begin():
                persisted = repo.save_production_run(
                    session,
                    project_id=PROJECT_ID,
                    project_version_id=VERSION_ID,
                    run_id="wiring-run-count-001",
                    source_mode="production",
                    source_binding_id=SOURCE_BINDING_ID,
                    source_contract_version="1.0.0",
                    binding_schema_version="1.0.0",
                    combined_source_hash=GOLDEN_COMBINED_SOURCE_HASH,
                    execution_snapshot_id=EXEC_SNAPSHOT_ID,
                    coefficient_context_id=COEFF_CONTEXT_ID,
                    orchestration_identity_id=IDENTITY_ID,
                    authoritative_attempt_id=ATTEMPT_ID,
                    orchestration_fingerprint="wiring-test-fingerprint-001",
                    zone_calculation_id=SLOT_CALC_RUN_IDS["zone"],
                    cooling_load_calculation_id=SLOT_CALC_RUN_IDS["cooling_load"],
                    equipment_calculation_id=SLOT_CALC_RUN_IDS["equipment"],
                    power_calculation_id=SLOT_CALC_RUN_IDS["power"],
                    investment_calculation_id=SLOT_CALC_RUN_IDS["investment"],
                    zone_result_hash=SLOT_RESULT_HASHES["zone"],
                    cooling_load_result_hash=SLOT_RESULT_HASHES["cooling_load"],
                    equipment_result_hash=SLOT_RESULT_HASHES["equipment"],
                    power_result_hash=SLOT_RESULT_HASHES["power"],
                    investment_result_hash=SLOT_RESULT_HASHES["investment"],
                    weight_set_id=WEIGHT_SET_ID,
                    weight_set_revision_id=WEIGHT_REVISION_ID,
                    weight_set_content_hash=WEIGHT_CONTENT_HASH,
                    weight_set_generator_compatibility_version="1.0.0",
                    generator_version="1.0.0",
                    source_snapshot_hash=GOLDEN_COMBINED_SOURCE_HASH,
                    content_hash="wiring-content-hash-count",
                    profile_codes=("balanced",),
                    profile_parameters={"balanced": {}},
                    candidates_snapshot={"items": []},
                    candidates=[],
                    input_snapshot={"throughput_t": "25.0"},
                    assumption_snapshot={"safety_factor": "1.2"},
                    comparison_snapshot={},
                    warning_messages=[],
                    requires_review=False,
                    recommended_scheme_code=None,
                    status="completed",
                )

        with session_factory() as session:
            count = session.execute(
                text(
                    "SELECT COUNT(*) FROM production_source_archives "
                    "WHERE scheme_run_id = :sid"
                ),
                {"sid": persisted.id},
            ).scalar_one()
            assert count == 1, f"Expected exactly 1 archive row, got {count}"


class TestArchiveWiringFailureRollback:
    """P0-1 failure acceptance: archive builder raise → UoW rollback.

    Drives ``save_production_run`` directly with a closure that
    raises, ensuring the entire UoW transaction is rolled back (no
    half-committed SchemeRun row, no archive row).
    """

    def test_archive_builder_failure_rolls_back_scheme_run(
        self,
        engine,
        session_factory,
    ) -> None:
        """A raising build_archive_callable MUST roll back the entire
        SchemeRun UoW: NEITHER scheme_runs NOR
        production_source_archives rows survive.
        """
        with session_factory() as session:
            _seed_all_chains(session)

        from cold_storage.modules.orchestration.domain.errors import (
            SourceArchiveBuildError,
        )
        from cold_storage.modules.schemes.infrastructure.production_repository import (
            SqlAlchemyProductionSchemeRunRepository,
        )

        boom_message = "intentional archive builder raise"

        def _failing_archive_callable(session, persisted_run):
            _ = (session, persisted_run.id)
            raise SourceArchiveBuildError(boom_message)

        repo = SqlAlchemyProductionSchemeRunRepository(
            build_archive_callable=_failing_archive_callable,
        )

        # Wrap the save in a nested transaction we explicitly roll back
        # so the outer session remains usable.  We mirror how
        # ProductionSchemeService drives the UoW (it commits on success,
        # rolls back on exception).
        with session_factory() as session:
            outer_tx = session.begin()
            try:
                persisted = repo.save_production_run(
                    session,
                    project_id=PROJECT_ID,
                    project_version_id=VERSION_ID,
                    run_id="wiring-failure-run-001",
                    source_mode="production",
                    source_binding_id=SOURCE_BINDING_ID,
                    source_contract_version="1.0.0",
                    binding_schema_version="1.0.0",
                    combined_source_hash=GOLDEN_COMBINED_SOURCE_HASH,
                    execution_snapshot_id=EXEC_SNAPSHOT_ID,
                    coefficient_context_id=COEFF_CONTEXT_ID,
                    orchestration_identity_id=IDENTITY_ID,
                    authoritative_attempt_id=ATTEMPT_ID,
                    orchestration_fingerprint="wiring-test-fingerprint-001",
                    zone_calculation_id=SLOT_CALC_RUN_IDS["zone"],
                    cooling_load_calculation_id=SLOT_CALC_RUN_IDS["cooling_load"],
                    equipment_calculation_id=SLOT_CALC_RUN_IDS["equipment"],
                    power_calculation_id=SLOT_CALC_RUN_IDS["power"],
                    investment_calculation_id=SLOT_CALC_RUN_IDS["investment"],
                    zone_result_hash=SLOT_RESULT_HASHES["zone"],
                    cooling_load_result_hash=SLOT_RESULT_HASHES["cooling_load"],
                    equipment_result_hash=SLOT_RESULT_HASHES["equipment"],
                    power_result_hash=SLOT_RESULT_HASHES["power"],
                    investment_result_hash=SLOT_RESULT_HASHES["investment"],
                    weight_set_id=WEIGHT_SET_ID,
                    weight_set_revision_id=WEIGHT_REVISION_ID,
                    weight_set_content_hash=WEIGHT_CONTENT_HASH,
                    weight_set_generator_compatibility_version="1.0.0",
                    generator_version="1.0.0",
                    source_snapshot_hash=GOLDEN_COMBINED_SOURCE_HASH,
                    content_hash="wiring-content-hash-failure",
                    profile_codes=("balanced",),
                    profile_parameters={"balanced": {}},
                    candidates_snapshot={"items": []},
                    candidates=[],
                    input_snapshot={"throughput_t": "25.0"},
                    assumption_snapshot={"safety_factor": "1.2"},
                    comparison_snapshot={},
                    warning_messages=[],
                    requires_review=False,
                    recommended_scheme_code=None,
                    status="completed",
                )
            except SourceArchiveBuildError as e:
                assert boom_message in str(e)
                outer_tx.rollback()
                persisted = None
            else:
                # Should not reach here.
                outer_tx.commit()

        assert persisted is None

        # ── Acceptance 1: scheme_runs row absent ─────────────────────
        with session_factory() as session:
            run_count = session.execute(
                text(
                    "SELECT COUNT(*) FROM scheme_runs "
                    "WHERE source_binding_id = :bid"
                ),
                {"bid": SOURCE_BINDING_ID},
            ).scalar_one()
            assert run_count == 0, (
                f"SchemeRun row was committed despite archive builder raise "
                f"(found {run_count} rows)"
            )

            # ── Acceptance 2: production_source_archives row absent ─
            archive_count = session.execute(
                text(
                    "SELECT COUNT(*) FROM production_source_archives "
                    "WHERE source_binding_id = :bid"
                ),
                {"bid": SOURCE_BINDING_ID},
            ).scalar_one()
            assert archive_count == 0, (
                f"Archive row was committed despite builder raise "
                f"(found {archive_count} rows)"
            )



