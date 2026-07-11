"""Test-side pre-existing-context seed helpers for A1/A2 live-database tests.

Scope and authority
===================

This module is **strictly test-side** and exists solely to support the
Path A / Task 11B Implementation Slice A1 (SQLite) and A2
(PostgreSQL) live-database happy-path tests in
``backend/tests/evaluation/test_path_a_adapter.py``.  It is **not**
part of the evaluation production surface.

**Authority boundary (A1 follow-up slice + A2 closure):**

* This file is the **only** location in ``backend/tests/evaluation/``
  that is allowed to write pre-existing production rows for the A1/A2
  live-database happy-path tests, per the narrow architecture-test
  carve-out documented in
  ``backend/tests/architecture/test_phase1_identity_foundation_boundary.py``.

* It is **not** imported by production code, the evaluation adapter, or
  the evaluation runner.  The architecture boundary tests enforce this
  import-direction discipline (raw-ORM fabrication ban).

* It does **not** implement a full pipeline.  It only seeds the minimum
  pre-existing production context required for the A1-2a adapter to
  call ``ProductionSchemeService.generate_production_scheme_run``
  end-to-end on a real SQLite database.

* It does **not** restore or substitute for
  ``backend/src/cold_storage/evaluation/production_seeding.py`` — that
  file must remain absent (per A1 design contract §6 explicit
  exclusions).

Helper naming
=============

Every helper in this module is named with a leading underscore and the
``seed_a1_`` prefix to make the test-only intent unambiguous.

Helpers
=======

* :func:`engine` (pytest fixture) — temp SQLite file with Alembic head
  schema.
* :func:`session_factory` (pytest fixture) — ``sessionmaker`` bound to
  the engine.
* :func:`seed_a1_all_prereqs` — public entry point that seeds the full
  pre-existing context chain.

The seed chain (in dependency order):

1. ``ProjectRecord`` + ``ProjectVersionRecord``
2. ``ProjectVersionExecutionSnapshotRecord``
3. ``CoefficientContextRecord``
4. ``OrchestrationIdentityRecord`` (with status=ACTIVE)
5. ``OrchestrationRunAttemptRecord`` (with status=COMPLETED)
6. 5 × ``CalculationRunRecord`` (zone / cooling_load / equipment /
   power / investment)
7. ``SourceBindingRecord`` (with per-calc hashes + combined source
   hash matching production ``SourceBindingVerifier``)
8. ``SchemeWeightSetRecord`` (status=approved) + draft
   ``SchemeWeightSetRevisionRecord`` (then UPDATE to approved because
   the production INSERT trigger blocks direct approved status).

See :mod:`backend.tests.integration.test_production_scheme_sqlite` for
the integration-test sibling that this helper was distilled from.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

# A1 + A2 — backend-aware seed helpers. Each fixture decides its own
# backend:
#   * ``a1_engine`` / ``a1_session_factory`` — SQLite in-process
#     (StaticPool, temp file, ``PRAGMA foreign_keys=ON``). Used by
#     A1 SQLite live tests.
#   * ``a2_pg_engine`` / ``a2_pg_session_factory`` — PostgreSQL
#     isolated database (NullPool, Alembic-upgraded head schema).
#     Used by A2 PostgreSQL live tests.
#
# Both fixture sets reuse the **same** ``seed_a1_*`` functions
# (which are dialect-agnostic — they only use SQLAlchemy session
# APIs) to seed the pre-existing production context.

BACKEND_DIR = Path(__file__).resolve().parents[2]

# ── Deterministic IDs (A1/A2 test-only) ──────────────────────────────────

PROJECT_ID = "a1-test-p-001"
VERSION_ID = "a1-test-v-001"
EXEC_SNAPSHOT_ID = "a1-test-exec-001"
COEFF_CONTEXT_ID = "a1-test-cc-001"
IDENTITY_ID = "a1-test-id-001"
ATTEMPT_ID = "a1-test-attempt-001"

ZONE_RUN_ID = "a1-test-run-zone-001"
COOL_RUN_ID = "a1-test-run-cool-001"
EQUIP_RUN_ID = "a1-test-run-equip-001"
POWER_RUN_ID = "a1-test-run-power-001"
INVEST_RUN_ID = "a1-test-run-invest-001"

SOURCE_BINDING_ID = "a1-test-binding-001"
WEIGHT_SET_ID = "a1-test-ws-001"
WEIGHT_REVISION_ID = "a1-test-wrev-001"

FINGERPRINT = "a1-test-fingerprint-001"

# ── Stage result snapshots (A1 test-only, minimum-viable) ─────────────────
#
# These snapshots match the shape that the production
# ``SourceBindingVerifier`` and downstream ``SchemeRun`` post-conditions
# expect, distilled from the integration test
# ``tests/integration/test_production_scheme_sqlite.py``.  All numeric
# values are JSON-safe strings (per the domain
# ``canonical_json_bytes`` rule that rejects binary ``float``).

ZONE_RESULT_SNAPSHOT: dict[str, Any] = {
    "daily_inbound_mass_kg": 10000,
    "design_daily_mass_kg": 10000,
    "total_required_area_m2": "200.0",
    "total_area_m2": "200.0",
    "planning_parameters": {
        "pallet_weight_kg": 500,
        "working_hours_per_day": 8,
    },
    "zones": [
        {
            "zone_code": "Z1",
            "zone_name": "a1-zone-001",
            "daily_throughput_kg_day": 10000,
            "required_area_m2": "200.0",
            "design_storage_mass_kg": "15000.0",
            "position_count": 30,
            "temperature_band": "0~4C",
            "function": "storage",
            "process_compatibility": "blueberry",
            "hygiene_zone": "food_grade",
        }
    ],
}

COOLING_RESULT_SNAPSHOT: dict[str, Any] = {
    "total_cooling_load_kw": "25.0",
    "safety_margin_load_kw": "2.5",
    "envelope_heat_transfer_load_kw": "3.0",
    "product_sensible_heat_load_kw": "18.0",
    "packaging_load_kw": "1.0",
    "infiltration_load_kw": "3.0",
    "personnel_load_kw": "0.5",
    "lighting_load_kw": "0.3",
    "evaporator_fan_load_kw": "1.2",
    "defrost_additional_load_kw": "0.4",
    "other_configuration_load_kw": "0.1",
    "latent_load_kw": "0.0",
}

EQUIPMENT_RESULT_SNAPSHOT: dict[str, Any] = {
    "evaporator_total_cooling_capacity_kw": "30.0",
    "evaporator_quantity": 2,
    "single_evaporator_capacity_kw": "15.0",
    "compressor_operating_capacity_kw": "22.0",
    "compressor_installed_capacity_kw": "25.0",
    "standby_capacity_kw": "8.0",
    "condenser_heat_rejection_capacity_kw": "30.0",
    "evaporation_temperature_c": "-5.0",
    "condensing_temperature_c": "40.0",
    "defrost_method": "electric",
    "review_requirement": "",
}

POWER_RESULT_SNAPSHOT: dict[str, Any] = {
    "total_installed_power_kw_e": "200.0",
    "total_estimated_demand_kw": "160.0",
    "equipment_rows": [],
    "summary_rows": [],
    "items": [],
    "assumptions": [],
}

INVESTMENT_RESULT_SNAPSHOT: dict[str, Any] = {
    "total_investment_cny": "6000000.0",
    "items": [
        {"item_name": "building", "amount_cny": "3000000.0"},
        {"item_name": "equipment", "amount_cny": "2000000.0"},
        {"item_name": "other", "amount_cny": "1000000.0"},
    ],
}

# ── Weight revision content (A1 test-only) ────────────────────────────────

_WEIGHT_CRITERIA_RAW: list[dict[str, Any]] = [
    {
        "criterion_code": "total_area_m2",
        "weight": "0.20",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "investment_cny",
        "weight": "0.30",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "total_position_count",
        "weight": "0.15",
        "direction": "higher_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "room_module_count",
        "weight": "0.10",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "door_count",
        "weight": "0.05",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "partition_length_proxy_m",
        "weight": "0.05",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "installed_power_kw_e",
        "weight": "0.15",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
]

WEIGHT_REVISION_CONTENT: dict[str, Any] = {"criteria": _WEIGHT_CRITERIA_RAW}

# ── Calculator name / type maps (A1 test-only) ────────────────────────────

_SLOT_CALCULATOR_NAMES: dict[str, str] = {
    "zone": "cold_room_zone_plan",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "power": "installed_power",
    "investment": "investment_estimate",
}

_SLOT_CALCULATION_TYPES: dict[str, str] = {
    "zone": "zone",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "power": "power",
    "investment": "investment",
}

_SLOT_STAGE_ORDER: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)

_SLOT_UPSTREAM_IDS: dict[str, dict[str, str]] = {
    "zone": {},
    "cooling_load": {"zone": ZONE_RUN_ID},
    "equipment": {"cooling_load": COOL_RUN_ID},
    "power": {"equipment": EQUIP_RUN_ID},
    "investment": {"zone": ZONE_RUN_ID, "power": POWER_RUN_ID},
}

_SLOT_RESULTS: dict[str, dict[str, Any]] = {
    "zone": ZONE_RESULT_SNAPSHOT,
    "cooling_load": COOLING_RESULT_SNAPSHOT,
    "equipment": EQUIPMENT_RESULT_SNAPSHOT,
    "power": POWER_RESULT_SNAPSHOT,
    "investment": INVESTMENT_RESULT_SNAPSHOT,
}


# ── Canonical hash helpers (test-only) ────────────────────────────────────


def _compute_domain_hash(*, stage: str, result_snapshot: dict[str, Any], run_id: str) -> str:
    """Compute the production domain-layer canonical hash for a stage.

    Uses the same ``build_source_snapshot_content_v1`` builder that the
    production ``SourceBindingVerifier`` and Transaction B executor
    use, ensuring identical SHA-256 hashes.

    The fields populated here (schema_version, project_id, etc.) must
    match the values used when the production verifier recomputes the
    hash in ``verify_source_binding``. The A1 test pre-seeds all of
    them on the ``CalculationRunRecord`` row; the verifier reads them
    back via the same read port.
    """
    from cold_storage.modules.orchestration.domain.fingerprint import (
        result_hash,
    )
    from cold_storage.modules.orchestration.domain.snapshots import (
        build_source_snapshot_content_v1,
    )

    content = build_source_snapshot_content_v1(
        schema_version="1.0.0",
        calculation_type=_SLOT_CALCULATION_TYPES[stage],
        calculator_name=_SLOT_CALCULATOR_NAMES[stage],
        calculator_version="1.0.0",
        project_id=PROJECT_ID,
        project_version_id=VERSION_ID,
        execution_snapshot_id=EXEC_SNAPSHOT_ID,
        coefficient_context_id=COEFF_CONTEXT_ID,
        orchestration_identity_id=IDENTITY_ID,
        orchestration_run_attempt_id=ATTEMPT_ID,
        input_hash="a1-input-hash-001",
        requires_review=False,
        payload=result_snapshot,
        upstream_calculation_ids=_SLOT_UPSTREAM_IDS.get(stage, {}),
    )
    return result_hash(content)


def _compute_weight_content_hash(content: dict[str, Any]) -> str:
    """Compute the canonical SHA-256 of weight-set revision content."""
    from cold_storage.modules.orchestration.domain.fingerprint import (
        canonical_json_bytes,
    )

    return hashlib.sha256(canonical_json_bytes(content)).hexdigest()


# ── Fixtures (A1 test-only) ───────────────────────────────────────────────


@pytest.fixture()
def a1_engine() -> Engine:
    """Temp SQLite file with Alembic head schema for A1 live-DB tests.

    The engine is disposed and the temp file removed after the test.
    Foreign-key enforcement is enabled via ``PRAGMA foreign_keys=ON``
    so that the production schema constraints are exercised.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    env["DATABASE_BACKEND"] = "sqlite"
    env.pop("DATABASE_URL", None)
    # pytest adds ``src`` to sys.path via pyproject.toml's
    # ``pythonpath = ["src"]`` config; the alembic subprocess must
    # see the same sys.path so that ``cold_storage.*`` imports
    # resolve in alembic's env.py.
    src_path = (BACKEND_DIR / "src").resolve()
    existing_pp = env.get("PYTHONPATH", "")
    pp_parts = [str(src_path)] + ([existing_pp] if existing_pp else [])
    env["PYTHONPATH"] = os.pathsep.join(pp_parts)
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
        pytest.fail(f"Alembic failed: {r.stderr}")
    e = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(e, "connect")
    def _pragma(dbapi_conn, _rec):  # pragma: no cover (PRAGMA hook)
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    yield e
    e.dispose()
    db_path.unlink(missing_ok=True)


@pytest.fixture()
def a1_session_factory(a1_engine: Engine) -> Callable[[], Session]:
    """``sessionmaker`` bound to the A1 test engine (``expire_on_commit=False``)."""
    return sessionmaker(bind=a1_engine, expire_on_commit=False)


# ── A2 PostgreSQL fixtures (A2 closure) ───────────────────────────────────
#
# The A2 PostgreSQL live happy-path tests reuse the dialect-agnostic
# ``seed_a1_*`` functions above and supply them with an isolated
# PostgreSQL database via the ``a2_pg_engine`` / ``a2_pg_session_factory``
# fixtures. The isolated database is created by:
#
#   1. Spinning up a unique database name derived from a UUID
#      (mirroring the integration-test ``pg_database_factory`` pattern
#      in ``tests/integration/conftest.py`` — without the cross-test
#      import).
#   2. Running ``alembic upgrade head`` against it as a subprocess
#      (the same way the SQLite ``a1_engine`` fixture does it).
#   3. Returning a SQLAlchemy engine + sessionmaker bound to the
#      isolated database.
#
# The fixture requires ``DATABASE_URL`` to be set (CI sets it via
# the ``backend-postgresql`` service container; local PG runs set it
# to the same ``postgresql+psycopg2://cold_storage:cold_storage@localhost:5432/...``
# URL that CI uses). When ``DATABASE_URL`` is missing the fixture
# skips the test (consistent with the integration-test pattern).

_PG_DB_NAME_RE = re.compile(r"[^a-z0-9_]")


def _sanitize_pg_db_name(name: str) -> str:
    """Return a valid PostgreSQL database name."""
    return _PG_DB_NAME_RE.sub("_", name.lower())[:63]


@pytest.fixture()
def a2_pg_admin_url() -> str:
    """PostgreSQL admin URL (points at the ``postgres`` system DB).

    Required for CREATE / DROP DATABASE — DDL operations need
    AUTOCOMMIT isolation and a connection to a database that is NOT
    the one being created / dropped.
    """
    original = os.environ.get("DATABASE_URL", "")
    if not original:
        pytest.skip("DATABASE_URL not set; A2 PG live tests require a PG service")
    base = original.rsplit("/", 1)[0]
    return f"{base}/postgres"


@pytest.fixture()
def a2_pg_database(a2_pg_admin_url: str):
    """Isolated PostgreSQL database with Alembic head schema applied.

    Yields the database URL. Cleans up via ``DROP DATABASE … WITH
    (FORCE)`` on teardown to terminate any lingering connections.
    """
    base_url = os.environ.get("DATABASE_URL", "")
    if not base_url:
        pytest.skip("DATABASE_URL not set")

    db_name = _sanitize_pg_db_name(f"a2_eval_{uuid.uuid4().hex[:12]}")
    admin_engine = create_engine(a2_pg_admin_url, poolclass=NullPool)
    admin_engine = admin_engine.execution_options(isolation_level="AUTOCOMMIT")
    db_url = f"{base_url.rsplit('/', 1)[0]}/{db_name}"

    try:
        with admin_engine.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE {db_name}"))
    finally:
        admin_engine.dispose()

    # Run alembic upgrade head against the new database.
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    env["DATABASE_BACKEND"] = "postgresql"
    # pytest adds ``src`` to sys.path via pyproject.toml; the
    # alembic subprocess must see the same path so cold_storage.*
    # imports resolve in alembic's env.py.
    src_path = (BACKEND_DIR / "src").resolve()
    existing_pp = env.get("PYTHONPATH", "")
    pp_parts = [str(src_path)] + ([existing_pp] if existing_pp else [])
    env["PYTHONPATH"] = os.pathsep.join(pp_parts)
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        # Cleanup the database we created even on upgrade failure.
        admin_engine = create_engine(a2_pg_admin_url, poolclass=NullPool)
        admin_engine = admin_engine.execution_options(isolation_level="AUTOCOMMIT")
        try:
            with admin_engine.connect() as conn:
                conn.execute(text(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)"))
        finally:
            admin_engine.dispose()
        pytest.fail(
            f"Alembic upgrade to head failed for A2 PG test database:\n"
            f"STDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}"
        )

    try:
        yield db_url
    finally:
        admin_engine = create_engine(a2_pg_admin_url, poolclass=NullPool)
        admin_engine = admin_engine.execution_options(isolation_level="AUTOCOMMIT")
        try:
            with admin_engine.connect() as conn, suppress(Exception):
                conn.execute(text(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)"))
        finally:
            admin_engine.dispose()


@pytest.fixture()
def a2_pg_engine(a2_pg_database: str):
    """SQLAlchemy engine for the A2 isolated PG test database (NullPool)."""
    engine = create_engine(a2_pg_database, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def a2_pg_session_factory(
    a2_pg_engine: Engine,
) -> Callable[[], Session]:
    """``sessionmaker`` bound to the A2 test engine (``expire_on_commit=False``)."""
    return sessionmaker(bind=a2_pg_engine, expire_on_commit=False)


# ── Pre-seed chain (A1 test-only) ─────────────────────────────────────────


def _compute_a1_combined_source_hash() -> str:
    """Compute the combined source hash matching the production verifier."""
    from cold_storage.modules.schemes.application.source_binding_verifier import (
        _compute_combined_source_hash,
    )

    slot_ids = {
        "zone": ZONE_RUN_ID,
        "cooling_load": COOL_RUN_ID,
        "equipment": EQUIP_RUN_ID,
        "power": POWER_RUN_ID,
        "investment": INVEST_RUN_ID,
    }
    per_calc_hashes: dict[str, str] = {
        stage: _compute_domain_hash(
            stage=stage,
            result_snapshot=_SLOT_RESULTS[stage],
            run_id=slot_ids[stage],
        )
        for stage in _SLOT_STAGE_ORDER
    }
    return _compute_combined_source_hash(
        binding_schema_version="1.0.0",
        project_id=PROJECT_ID,
        project_version_id=VERSION_ID,
        execution_snapshot_id=EXEC_SNAPSHOT_ID,
        coefficient_context_id=COEFF_CONTEXT_ID,
        orchestration_identity_id=IDENTITY_ID,
        orchestration_attempt_id=ATTEMPT_ID,
        orchestration_fingerprint=FINGERPRINT,
        slot_ids=slot_ids,
        result_hashes=per_calc_hashes,
        requires_reviews={stage: False for stage in _SLOT_STAGE_ORDER},
    )


def seed_a1_project_and_version(session: Session) -> None:
    """Create the A1 test project + version (idempotent)."""
    from cold_storage.modules.projects.infrastructure.orm import (
        ProjectRecord,
        ProjectVersionRecord,
    )

    existing = session.execute(
        select(ProjectRecord).where(ProjectRecord.id == PROJECT_ID)
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            ProjectRecord(
                id=PROJECT_ID,
                code="A1_TEST_001",
                name="A1 Test Project",
                location="test",
                product_category="blueberry",
                status="active",
                current_version_number=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
    existing_v = session.execute(
        select(ProjectVersionRecord).where(ProjectVersionRecord.id == VERSION_ID)
    ).scalar_one_or_none()
    if existing_v is None:
        session.add(
            ProjectVersionRecord(
                id=VERSION_ID,
                project_id=PROJECT_ID,
                version_number=1,
                change_summary="a1 test version",
                created_by="a1-test",
                status="approved",
                created_at=datetime.now(UTC),
                input_snapshot={
                    "throughput_t": "25.0",
                    "product_category": "blueberry",
                },
            )
        )
    session.commit()


def seed_a1_orchestration_prereqs(session: Session) -> None:
    """Create snapshot / coefficient-context / identity / attempt for A1."""
    from cold_storage.modules.orchestration.infrastructure.orm import (
        CoefficientContextRecord,
        OrchestrationIdentityRecord,
        OrchestrationRunAttemptRecord,
        ProjectVersionExecutionSnapshotRecord,
    )

    existing = session.execute(
        select(ProjectVersionExecutionSnapshotRecord).where(
            ProjectVersionExecutionSnapshotRecord.id == EXEC_SNAPSHOT_ID
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            ProjectVersionExecutionSnapshotRecord(
                id=EXEC_SNAPSHOT_ID,
                project_id=PROJECT_ID,
                project_version_id=VERSION_ID,
                version_number=1,
                input_snapshot={"throughput_t": "25.0"},
                input_snapshot_hash="a1-snap-hash-001",
                schema_version="1.0.0",
                captured_status="approved",
                captured_at=datetime.now(UTC),
            )
        )

    existing_cc = session.execute(
        select(CoefficientContextRecord).where(CoefficientContextRecord.id == COEFF_CONTEXT_ID)
    ).scalar_one_or_none()
    if existing_cc is None:
        session.add(
            CoefficientContextRecord(
                id=COEFF_CONTEXT_ID,
                project_id=PROJECT_ID,
                project_version_id=VERSION_ID,
                content={"coefficients": []},
                content_hash="a1-cc-hash-001",
                schema_version="1.0.0",
                captured_at=datetime.now(UTC),
            )
        )
    session.commit()

    existing_i = session.execute(
        select(OrchestrationIdentityRecord).where(OrchestrationIdentityRecord.id == IDENTITY_ID)
    ).scalar_one_or_none()
    if existing_i is None:
        session.add(
            OrchestrationIdentityRecord(
                id=IDENTITY_ID,
                fingerprint=FINGERPRINT,
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
                created_at=datetime.now(UTC),
            )
        )

    existing_a = session.execute(
        select(OrchestrationRunAttemptRecord).where(OrchestrationRunAttemptRecord.id == ATTEMPT_ID)
    ).scalar_one_or_none()
    if existing_a is None:
        session.add(
            OrchestrationRunAttemptRecord(
                id=ATTEMPT_ID,
                identity_id=IDENTITY_ID,
                attempt_number=1,
                status="COMPLETED",
                heartbeat_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                database_backend="sqlite",
                correlation_id="a1-test-corr-001",
            )
        )
        session.commit()

        identity_rec = session.execute(
            select(OrchestrationIdentityRecord).where(OrchestrationIdentityRecord.id == IDENTITY_ID)
        ).scalar_one()
        identity_rec.authoritative_attempt_id = ATTEMPT_ID
        session.commit()


def seed_a1_calculation_runs(session: Session) -> dict[str, str]:
    """Create the 5 ``CalculationRunRecord`` rows for the A1 test. Returns per-calc hash map."""
    from cold_storage.modules.projects.infrastructure.orm import (
        CalculationRunRecord,
    )

    slot_ids = {
        "zone": ZONE_RUN_ID,
        "cooling_load": COOL_RUN_ID,
        "equipment": EQUIP_RUN_ID,
        "power": POWER_RUN_ID,
        "investment": INVEST_RUN_ID,
    }
    per_calc: dict[str, str] = {}
    for stage in _SLOT_STAGE_ORDER:
        run_id = slot_ids[stage]
        snap = _SLOT_RESULTS[stage]
        computed_hash = _compute_domain_hash(stage=stage, result_snapshot=snap, run_id=run_id)
        per_calc[stage] = computed_hash
        existing = session.execute(
            select(CalculationRunRecord).where(CalculationRunRecord.id == run_id)
        ).scalar_one_or_none()
        if existing is not None:
            continue
        provenance: dict[str, Any] = {
            "stage": stage,
            "upstream_calculation_ids": _SLOT_UPSTREAM_IDS.get(stage, {}),
        }
        session.add(
            CalculationRunRecord(
                id=run_id,
                project_id=PROJECT_ID,
                project_version_id=VERSION_ID,
                calculator_name=_SLOT_CALCULATOR_NAMES[stage],
                calculator_version="1.0.0",
                input_snapshot={},
                result_snapshot=snap,
                formulas=[],
                coefficients=[],
                assumptions=[],
                warnings=[],
                source_references=[],
                requires_review=False,
                calculation_type=_SLOT_CALCULATION_TYPES[stage],
                orchestration_identity_id=IDENTITY_ID,
                orchestration_run_attempt_id=ATTEMPT_ID,
                execution_snapshot_id=EXEC_SNAPSHOT_ID,
                coefficient_context_id=COEFF_CONTEXT_ID,
                input_hash="a1-input-hash-001",
                result_hash=computed_hash,
                provenance=provenance,
                schema_version="1.0.0",
                orchestration_fingerprint=FINGERPRINT,
                created_at=datetime.now(UTC),
            )
        )
    session.commit()
    return per_calc


def seed_a1_source_binding(session: Session, *, per_calc: dict[str, str] | None = None) -> None:
    """Create the A1 ``SourceBindingRecord`` (idempotent)."""
    from cold_storage.modules.orchestration.infrastructure.orm import (
        OrchestrationRunAttemptRecord,
        SourceBindingRecord,
    )

    per_calc = per_calc or {
        stage: _compute_domain_hash(
            stage=stage, result_snapshot=_SLOT_RESULTS[stage], run_id=slot_id
        )
        for stage, slot_id in (
            ("zone", ZONE_RUN_ID),
            ("cooling_load", COOL_RUN_ID),
            ("equipment", EQUIP_RUN_ID),
            ("power", POWER_RUN_ID),
            ("investment", INVEST_RUN_ID),
        )
    }

    existing = session.execute(
        select(SourceBindingRecord).where(SourceBindingRecord.id == SOURCE_BINDING_ID)
    ).scalar_one_or_none()
    if existing is not None:
        return

    combined = _compute_a1_combined_source_hash()
    session.add(
        SourceBindingRecord(
            id=SOURCE_BINDING_ID,
            project_id=PROJECT_ID,
            project_version_id=VERSION_ID,
            execution_snapshot_id=EXEC_SNAPSHOT_ID,
            coefficient_context_id=COEFF_CONTEXT_ID,
            orchestration_identity_id=IDENTITY_ID,
            orchestration_run_attempt_id=ATTEMPT_ID,
            orchestration_fingerprint=FINGERPRINT,
            zone_calculation_id=ZONE_RUN_ID,
            cooling_load_calculation_id=COOL_RUN_ID,
            equipment_calculation_id=EQUIP_RUN_ID,
            power_calculation_id=POWER_RUN_ID,
            investment_calculation_id=INVEST_RUN_ID,
            per_calculation_result_hashes=per_calc,
            combined_source_hash=combined,
            schema_version="1.0.0",
            created_at=datetime.now(UTC),
        )
    )
    session.commit()

    # P0-2: attempt.source_binding_id must be non-NULL.
    attempt_rec = session.execute(
        select(OrchestrationRunAttemptRecord).where(OrchestrationRunAttemptRecord.id == ATTEMPT_ID)
    ).scalar_one_or_none()
    if attempt_rec is not None and attempt_rec.source_binding_id is None:
        attempt_rec.source_binding_id = SOURCE_BINDING_ID
        session.commit()


def seed_a1_weight_set_and_revision(session: Session) -> None:
    """Create the A1 ``SchemeWeightSetRecord`` + approved revision."""
    from cold_storage.modules.schemes.infrastructure.orm import (
        SchemeWeightSetRecord,
        SchemeWeightSetRevisionRecord,
    )

    content_hash = _compute_weight_content_hash(WEIGHT_REVISION_CONTENT)
    approved_at = datetime.now(UTC)
    approved_by = "a1-test-approver"

    existing_ws = session.execute(
        select(SchemeWeightSetRecord).where(SchemeWeightSetRecord.id == WEIGHT_SET_ID)
    ).scalar_one_or_none()
    if existing_ws is None:
        session.add(
            SchemeWeightSetRecord(
                id=WEIGHT_SET_ID,
                code="a1-standard-weights",
                name="A1 Standard Weights",
                revision=1,
                status="approved",
                source_type="production",
                criteria=_WEIGHT_CRITERIA_RAW,
                requires_review=False,
                created_at=datetime.now(UTC),
                approved_at=approved_at,
            )
        )

    existing_rev = session.execute(
        select(SchemeWeightSetRevisionRecord).where(
            SchemeWeightSetRevisionRecord.id == WEIGHT_REVISION_ID
        )
    ).scalar_one_or_none()
    if existing_rev is None:
        # Production INSERT trigger blocks direct approved status, so
        # insert as draft first then UPDATE to approved.
        session.add(
            SchemeWeightSetRevisionRecord(
                id=WEIGHT_REVISION_ID,
                weight_set_id=WEIGHT_SET_ID,
                code="a1-standard-weights",
                revision=1,
                status="draft",
                content=WEIGHT_REVISION_CONTENT,
                content_hash=content_hash,
                generator_compatibility_version="1.0.0",
                approved_at=None,
                approved_by=None,
                sealed_at=None,
                created_at=datetime.now(UTC),
            )
        )
        session.flush()
        session.execute(
            text(
                "UPDATE scheme_weight_set_revisions "
                "SET status = 'approved', "
                "approved_at = :approved_at, "
                "approved_by = :approved_by "
                "WHERE id = :rev_id"
            ),
            {
                "approved_at": approved_at,
                "approved_by": approved_by,
                "rev_id": WEIGHT_REVISION_ID,
            },
        )
    session.commit()


def seed_a1_all_prereqs(session: Session) -> None:
    """Seed the full pre-existing production context chain for the A1 live-DB tests.

    Public entry point.  Calls the per-stage helpers in dependency order.
    """
    seed_a1_project_and_version(session)
    seed_a1_orchestration_prereqs(session)
    per_calc = seed_a1_calculation_runs(session)
    seed_a1_source_binding(session, per_calc=per_calc)
    seed_a1_weight_set_and_revision(session)


# ── Test-side helpers for TASK-011B Path A baseline golden (Commit C) ──
#
# These helpers are PURE test-side expected-output construction and
# comparison. They MUST NOT:
#   - Modify any seed data, semantic IDs, fixture behavior, or production state.
#   - Call production private hash helpers.
#   - Re-derive a content_hash from test-defined payloads.
#
# The golden file (data/expected/baseline_feasible.v1.json) is the
# frozen expected output; the helpers below construct the canonical
# actual from the real persisted SchemeRunRecord + input_snapshot +
# assumption_snapshot and ScenarioOutcome, then compare.

# Canonical stage ledger frozen by §12.4 / §15.3
BASELINE_STAGE_LEDGER: list[str] = [
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
]

# Field name constants (raw SchemeRunRecord columns)
_F_PROD_RUN_COLUMNS = [
    "zone_calculation_id",
    "cooling_load_calculation_id",
    "equipment_calculation_id",
    "power_calculation_id",
    "investment_calculation_id",
]
_F_PROD_HASH_COLUMNS = [
    "zone_result_hash",
    "cooling_load_result_hash",
    "equipment_result_hash",
    "power_result_hash",
    "investment_result_hash",
]


def _str_or_none(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def build_baseline_expected_output_actual(
    *,
    scenario_outcome: Any,
    scheme_run_record: Any,
    input_snapshot: dict[str, Any],
    assumption_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Build the canonical expected-output shape for the baseline
    scenario directly from the live production-path values.

    NO test-side recomputation of ``content_hash``. The actual
    canonical ``content_hash`` is the production-side
    ``scheme_run_record.content_hash`` value, which has been proven
    byte-equal across SQLite and PostgreSQL backends.

    The raw `SchemeRunRecord` (production-side ORM) provides:
      - ``status`` (string)
      - ``combined_source_hash`` (string)
      - ``requires_review`` (bool)
      - ``warning_messages`` (list[str]) — RAW, which is then
        canonicalized into ``review_reasons``.
      - ``content_hash`` (string, frozen per §15.3 + auth §4)
      - semantic IDs (source_binding_id, weight_set_revision_id,
        project_id, project_version_id)
      - source_calculation_ids (per stage)
      - source_snapshot_hashes (per stage)
      - candidates_snapshot (with constraint_results)
      - comparison_snapshot
      - assumption_snapshot (JSON column)
      - input_snapshot (JSON column)

    ``scenario_outcome`` is the runner-side
    :class:`cold_storage.evaluation.execute.ScenarioOutcome`. Its
    `phase_b_blocked` and `database_backend` fields are runtime-only
    and are NOT present in the expected JSON; they are documented
    in the ``_comparison_policy.excluded_runtime_fields`` set.
    """
    p = scheme_run_record
    # §4: expected_outcome is derived from the live ScenarioOutcome,
    # NOT hard-coded. The golden records what the runner actually
    # produced for this scenario at the time the capture was taken.
    actual_outcome = (
        str(getattr(scenario_outcome, "outcome", None)) if scenario_outcome is not None else None
    )
    out: dict[str, Any] = {
        "schema_version": "task11b-expected-output.v1",
        "scenario_id": "baseline_feasible",
        "expected_outcome": actual_outcome,
        "scheme_status": str(p.status),
        "combined_source_hash": str(p.combined_source_hash),
        "review_required": bool(p.requires_review),
        # Canonical mapping: raw warning_messages → review_reasons
        "review_reasons": list(p.warning_messages or []),
        "source_binding_proxy": str(p.source_binding_id),
        "weight_set_revision_proxy": str(p.weight_set_revision_id),
        "project_id": str(p.project_id),
        "project_version_id": str(p.project_version_id),
        "stage_ledger": list(BASELINE_STAGE_LEDGER),
        "production_outputs": {
            "generator_version": str(p.generator_version),
            "source_mode": str(p.source_mode),
            "binding_schema_version": str(p.binding_schema_version),
            "weight_set_generator_compatibility_version": str(
                p.weight_set_generator_compatibility_version
            ),
            "weight_set_content_hash": str(p.weight_set_content_hash),
            "source_calculation_ids": {
                stage: str(getattr(p, col))
                for stage, col in zip(BASELINE_STAGE_LEDGER, _F_PROD_RUN_COLUMNS, strict=True)
            },
            "source_snapshot_hashes": {
                stage: str(getattr(p, col))
                for stage, col in zip(BASELINE_STAGE_LEDGER, _F_PROD_HASH_COLUMNS, strict=True)
            },
            "candidates_snapshot": p.candidates_snapshot,
            "comparison_snapshot": p.comparison_snapshot,
            "assumption_snapshot": dict(assumption_snapshot or {}),
            "cooling_load_result": input_snapshot.get("cooling_load_result"),
            "equipment_result": input_snapshot.get("equipment_result"),
            "investment_result": input_snapshot.get("investment_result"),
            "power_result": input_snapshot.get("power_result"),
            "zone_results": input_snapshot.get("zone_results"),
            "profile_codes": input_snapshot.get("profile_codes"),
            "profile_parameters": input_snapshot.get("profile_parameters"),
            "total_daily_throughput_kg_day": input_snapshot.get("total_daily_throughput_kg_day"),
            "total_position_count": input_snapshot.get("total_position_count"),
            "total_storage_capacity_kg": input_snapshot.get("total_storage_capacity_kg"),
            "weight_set_id": input_snapshot.get("weight_set_id"),
        },
        "content_hash": str(p.content_hash),  # PRODUCTION VALUE, not test-recomputed
    }

    # constraint_check_summary derived from candidates_snapshot[0]
    c0 = p.candidates_snapshot[0]
    cr = c0["constraint_results"]
    n_pass = sum(1 for c in cr if c["passed"])
    n_fail = sum(1 for c in cr if not c["passed"])
    failed_codes = [c["constraint_code"] for c in cr if not c["passed"]]
    out["constraint_check_summary"] = {
        "expected_passed_count": n_pass,
        "expected_failed_count": n_fail,
        "expected_failed_code": (failed_codes[0] if failed_codes else None),
    }
    return out


# Sentinel set of canonical expected JSON top-level field names.
EXPECTED_OUTPUT_TOP_LEVEL_FIELDS: frozenset[str] = frozenset(
    {
        "schema_version",
        "scenario_id",
        "expected_outcome",
        "scheme_status",
        "combined_source_hash",
        "review_required",
        "review_reasons",
        "source_binding_proxy",
        "weight_set_revision_proxy",
        "project_id",
        "project_version_id",
        "stage_ledger",
        "production_outputs",
        "content_hash",
        "constraint_check_summary",
        "_comparison_policy",
    }
)


def _walk(obj: Any, path: str, out: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _walk(v, f"{path}.{k}" if path else f"$.{k}", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk(v, f"{path}[{i}]", out)
    else:
        out.append(path)


def collect_golden_leaf_paths(golden: dict[str, Any]) -> list[str]:
    """Return all golden leaf JSON paths EXCLUDING the
    ``_comparison_policy`` subtree (which is meta-documentation)."""
    g = dict(golden)
    g.pop("_comparison_policy", None)
    leaves: list[str] = []
    _walk(g, "", leaves)
    return leaves


def _collect_ancestor_paths(leaf: str) -> list[str]:
    """Return all ancestor paths of ``leaf``.

    For leaf ``$.production_outputs.zone_results[0].area_m2``,
    ancestors are:
      - ``$.production_outputs.zone_results[0]``
      - ``$.production_outputs.zone_results``
      - ``$.production_outputs``
      - ``$``
    For leaf ``$.stage_ledger[0]``, ancestors are:
      - ``$.stage_ledger``
      - ``$``
    List indices ``[N]`` are stripped when computing the parent path.
    """
    ancestors: list[str] = []
    cur = leaf
    while True:
        # Strip a trailing ``[N]`` if present (in-place before finding the dot)
        bracket = cur.rfind("[")
        if bracket > 0:
            cur = cur[:bracket]
        # Find the LAST dot separator (which splits off the last key segment)
        idx = cur.rfind(".")
        if idx < 0:
            break
        # cur itself (with the trailing [N] already stripped) is an
        # ancestor path. Append it.
        ancestors.append(cur)
        # Now strip the trailing ``.key`` segment for the next iteration.
        cur = cur[:idx]
    return ancestors


def validate_expected_output_comparison_policy(
    golden: dict[str, Any],
    *,
    backend: str,
) -> None:
    """Validate the comparison_policy is self-consistent and covers
    every golden leaf path.

    Validation rules (per auth §5 + §6, pairwise-disjoint classes):
      1. ``_comparison_policy`` exists and is an object.
      2. Required policy keys present.
      3. ``exact_match_fields`` has no duplicates.
      4. ``excluded_runtime_fields`` has no duplicates.
      5. ``normalized_proxy_fields`` has no duplicates.
      6. exact ∩ excluded = ∅  → POLICY_EXACT_EXCLUDED_OVERLAP
      7. exact ∩ proxy    = ∅  → POLICY_EXACT_PROXY_OVERLAP
      8. proxy  ∩ excluded = ∅ → POLICY_PROXY_EXCLUDED_OVERLAP
      9. ``content_hash``, ``schema_version``, ``scenario_id`` are
         EXACT_MATCH only (NOT in excluded).
     10. Every golden non-policy leaf classifies into EXACTLY ONE
         comparison class (EXACT_MATCH or NORMALIZED_PROXY).
         - class_count == 0 → POLICY_LEAF_UNCOVERED
         - class_count >  1 → POLICY_LEAF_MULTI_CLASSIFIED
         NO "exact-first continue" shortcut is permitted: any leaf
         matched by both exact and proxy is rejected.
     11. Parent recursive exact subtrees count toward EXACT_MATCH
         coverage (so a leaf like ``$.production_outputs`` covers all
         descendant leaves).
     12. No fuzzy global tolerance.
     13. No string truncation.
     14. No "ignore all numerical" escape.
    """
    if "_comparison_policy" not in golden:
        raise AssertionError(f"POLICY_MISSING: _comparison_policy not present (backend={backend})")
    policy = golden["_comparison_policy"]
    if not isinstance(policy, dict):
        raise AssertionError(
            f"POLICY_TYPE: _comparison_policy must be object, got "
            f"{type(policy).__name__} (backend={backend})"
        )
    required_keys = {
        "exact_match_fields",
        "excluded_runtime_fields",
        "normalized_proxy_fields",
        "forbidden_comparison_methods",
    }
    missing = required_keys - set(policy.keys())
    if missing:
        raise AssertionError(f"POLICY_KEYS_MISSING: {sorted(missing)} (backend={backend})")

    exact = list(policy["exact_match_fields"])
    excluded = list(policy["excluded_runtime_fields"])
    proxy = list(policy["normalized_proxy_fields"])

    exact_set = set(exact)
    excluded_set = set(excluded)
    proxy_set = set(proxy)

    if len(exact) != len(exact_set):
        dups = sorted([x for x in exact if exact.count(x) > 1])
        raise AssertionError(f"POLICY_DUP_EXACT: {dups} (backend={backend})")
    if len(excluded) != len(excluded_set):
        dups = sorted([x for x in excluded if excluded.count(x) > 1])
        raise AssertionError(f"POLICY_DUP_EXCLUDED: {dups} (backend={backend})")
    if len(proxy) != len(proxy_set):
        dups = sorted([x for x in proxy if proxy.count(x) > 1])
        raise AssertionError(f"POLICY_DUP_PROXY: {dups} (backend={backend})")

    # Pairwise-disjoint comparison classes
    overlap_e_x = sorted(exact_set & excluded_set)
    if overlap_e_x:
        raise AssertionError(f"POLICY_EXACT_EXCLUDED_OVERLAP: {overlap_e_x} (backend={backend})")
    overlap_e_p = sorted(exact_set & proxy_set)
    if overlap_e_p:
        raise AssertionError(f"POLICY_EXACT_PROXY_OVERLAP: {overlap_e_p} (backend={backend})")
    overlap_p_x = sorted(proxy_set & excluded_set)
    if overlap_p_x:
        raise AssertionError(f"POLICY_PROXY_EXCLUDED_OVERLAP: {overlap_p_x} (backend={backend})")

    # content_hash / schema_version / scenario_id must NOT be in excluded
    forbidden_in_excluded = {
        "$.content_hash",
        "$.schema_version",
        "$.scenario_id",
    }
    bad_in_excluded = sorted(forbidden_in_excluded & excluded_set)
    if bad_in_excluded:
        raise AssertionError(f"POLICY_FORBIDDEN_IN_EXCLUDED: {bad_in_excluded} (backend={backend})")
    # ... and MUST be in exact_match_fields (exact canonical values,
    # not proxy normalized comparisons)
    must_be_exact = {
        "$.content_hash",
        "$.schema_version",
        "$.scenario_id",
    }
    missing_exact = sorted(must_be_exact - exact_set)
    if missing_exact:
        raise AssertionError(
            f"POLICY_MUST_BE_EXACT: {missing_exact} must appear in "
            f"exact_match_fields (backend={backend})"
        )

    # forbidden_comparison_methods
    forbidden = list(policy["forbidden_comparison_methods"])
    must_have_forbidden = [
        "fuzzy_global_tolerance",
        "string_truncation",
        "ignore_all_numerical_fields",
    ]
    missing_forbidden = sorted(set(must_have_forbidden) - set(forbidden))
    if missing_forbidden:
        raise AssertionError(f"POLICY_FORBIDDEN_MISSING: {missing_forbidden} (backend={backend})")

    # ── Commit F §3.1: leaf_coverage_summary self-consistency ───────────
    # Per Charles's Commit F spec, the leaf_coverage_summary
    # documents the executable comparison classes. Drift between the
    # summary and the executable arrays creates a second opinion on
    # classification and is therefore rejected with stable error
    # codes. Per §4 "Deterministic overlap order", these checks run
    # BEFORE leaf traversal so any overlap raises
    # POLICY_EXACT_PROXY_OVERLAP (never POLICY_LEAF_MULTI_CLASSIFIED).
    summary = policy.get("leaf_coverage_summary")
    if not isinstance(summary, dict):
        raise AssertionError(
            f"POLICY_SUMMARY_TYPE: leaf_coverage_summary must be object, "
            f"got {type(summary).__name__} (backend={backend})"
        )
    required_summary_keys = {
        "exact_match_leaf_examples",
        "normalized_proxy_leaf_examples",
        "no_excluded_canonical_field",
    }
    missing_summary = required_summary_keys - set(summary.keys())
    if missing_summary:
        raise AssertionError(
            f"POLICY_SUMMARY_TYPE: leaf_coverage_summary missing keys "
            f"{sorted(missing_summary)} (backend={backend})"
        )
    exact_examples = summary["exact_match_leaf_examples"]
    proxy_examples = summary["normalized_proxy_leaf_examples"]
    if not isinstance(exact_examples, list) or not all(isinstance(x, str) for x in exact_examples):
        raise AssertionError(
            f"POLICY_SUMMARY_TYPE: exact_match_leaf_examples must be list[str] (backend={backend})"
        )
    if not isinstance(proxy_examples, list) or not all(isinstance(x, str) for x in proxy_examples):
        raise AssertionError(
            f"POLICY_SUMMARY_TYPE: normalized_proxy_leaf_examples must be "
            f"list[str] (backend={backend})"
        )
    if len(exact_examples) != len(set(exact_examples)):
        dups = sorted({x for x in exact_examples if exact_examples.count(x) > 1})
        raise AssertionError(f"POLICY_SUMMARY_DUP_EXACT: {dups} (backend={backend})")
    if len(proxy_examples) != len(set(proxy_examples)):
        dups = sorted({x for x in proxy_examples if proxy_examples.count(x) > 1})
        raise AssertionError(f"POLICY_SUMMARY_DUP_PROXY: {dups} (backend={backend})")
    if set(proxy_examples) != proxy_set:
        raise AssertionError(
            f"POLICY_PROXY_SUMMARY_MISMATCH: "
            f"normalized_proxy_leaf_examples={sorted(set(proxy_examples))} "
            f"must exactly equal normalized_proxy_fields={sorted(proxy_set)} "
            f"(backend={backend})"
        )
    exact_examples_set = set(exact_examples)
    bad_exact = sorted(exact_examples_set - exact_set)
    if bad_exact:
        raise AssertionError(
            f"POLICY_EXACT_SUMMARY_CLASS_MISMATCH: {bad_exact} are not in "
            f"exact_match_fields (backend={backend})"
        )
    if exact_examples_set & proxy_set:
        overlap = sorted(exact_examples_set & proxy_set)
        raise AssertionError(
            f"POLICY_SUMMARY_CLASS_OVERLAP: exact_match_leaf_examples ∩ "
            f"normalized_proxy_fields = {overlap} (backend={backend})"
        )
    if summary["no_excluded_canonical_field"] is not True:
        raise AssertionError(
            f"POLICY_SUMMARY_EXCLUDED_FLAG_INVALID: "
            f"no_excluded_canonical_field must be True, "
            f"got {summary['no_excluded_canonical_field']!r} "
            f"(backend={backend})"
        )

    # ── Commit F §3.2: evidence object self-consistency ─────────────────
    exact_evidence = policy.get("exact_field_evidence")
    if not isinstance(exact_evidence, dict):
        raise AssertionError(
            f"POLICY_EXACT_EVIDENCE_CLASS_MISMATCH: exact_field_evidence "
            f"must be object, got {type(exact_evidence).__name__} "
            f"(backend={backend})"
        )
    proxy_evidence = policy.get("normalized_proxy_evidence")
    if not isinstance(proxy_evidence, dict):
        raise AssertionError(
            f"POLICY_PROXY_EVIDENCE_MISMATCH: normalized_proxy_evidence "
            f"must be object, got {type(proxy_evidence).__name__} "
            f"(backend={backend})"
        )
    for k, v in exact_evidence.items():
        if not isinstance(k, str) or not k or not isinstance(v, str) or not v:
            raise AssertionError(
                f"POLICY_EXACT_EVIDENCE_CLASS_MISMATCH: exact_field_evidence "
                f"keys and values must be non-empty strings "
                f"(backend={backend})"
            )
    for k, v in proxy_evidence.items():
        if not isinstance(k, str) or not k or not isinstance(v, str) or not v:
            raise AssertionError(
                f"POLICY_PROXY_EVIDENCE_MISMATCH: normalized_proxy_evidence "
                f"keys and values must be non-empty strings "
                f"(backend={backend})"
            )
    if not set(exact_evidence.keys()) <= exact_set:
        bad = sorted(set(exact_evidence.keys()) - exact_set)
        raise AssertionError(
            f"POLICY_EXACT_EVIDENCE_CLASS_MISMATCH: {bad} are not in "
            f"exact_match_fields (backend={backend})"
        )
    if set(proxy_evidence.keys()) != proxy_set:
        raise AssertionError(
            f"POLICY_PROXY_EVIDENCE_MISMATCH: "
            f"normalized_proxy_evidence.keys()={sorted(set(proxy_evidence.keys()))} "
            f"must exactly equal normalized_proxy_fields={sorted(proxy_set)} "
            f"(backend={backend})"
        )
    if set(exact_evidence.keys()) & set(proxy_evidence.keys()):
        overlap = sorted(set(exact_evidence.keys()) & set(proxy_evidence.keys()))
        raise AssertionError(
            f"POLICY_EVIDENCE_CLASS_OVERLAP: exact_field_evidence ∩ "
            f"normalized_proxy_evidence = {overlap} (backend={backend})"
        )

    # ── Commit F §3.3: warning_messages mapping exactly validated ───────
    expected_warning_value = (
        "review_reasons (canonical form: ordered list[str], same content as raw)"
    )
    mapping = policy.get("field_normalization_mapping", {})
    actual_warning_value = mapping.get("scheme_run.warning_messages")
    if actual_warning_value != expected_warning_value:
        raise AssertionError(
            f"POLICY_WARNING_MAPPING_MISMATCH: "
            f"field_normalization_mapping['scheme_run.warning_messages']="
            f"{actual_warning_value!r} must equal {expected_warning_value!r} "
            f"(backend={backend})"
        )
    review_reasons_path = "$.review_reasons"
    if review_reasons_path not in exact_set:
        raise AssertionError(
            f"POLICY_WARNING_TARGET_NOT_EXACT: {review_reasons_path} must be "
            f"in exact_match_fields (backend={backend})"
        )
    if review_reasons_path in proxy_set:
        raise AssertionError(
            f"POLICY_WARNING_TARGET_PROXY_OVERLAP: {review_reasons_path} "
            f"must NOT be in normalized_proxy_fields (backend={backend})"
        )
    if review_reasons_path in excluded_set:
        raise AssertionError(
            f"POLICY_WARNING_TARGET_EXCLUDED: {review_reasons_path} "
            f"must NOT be in excluded_runtime_fields (backend={backend})"
        )

    # Every golden non-policy leaf must classify into EXACTLY ONE
    # comparison class (no double-counting, no fallback).
    leaves = collect_golden_leaf_paths(golden)
    for leaf in leaves:
        classes: list[str] = []
        # Class A: exact match — leaf itself OR any ancestor in exact
        if leaf in exact_set:
            classes.append("EXACT_MATCH")
        else:
            ancestors = _collect_ancestor_paths(leaf)
            if any(a in exact_set for a in ancestors):
                classes.append("EXACT_MATCH")
        # Class B: normalized proxy — leaf itself OR any ancestor in proxy
        ancestors_for_proxy = _collect_ancestor_paths(leaf)
        if leaf in proxy_set or any(a in proxy_set for a in ancestors_for_proxy):
            classes.append("NORMALIZED_PROXY")
        # Excluded runtime fields are RAW fields, not canonical leaves.
        # A golden leaf matching an excluded entry is a mis-mapping
        # (excluded should never be reached for canonical JSON).
        ancestors_for_excluded = _collect_ancestor_paths(leaf)
        if leaf in excluded_set or any(a in excluded_set for a in ancestors_for_excluded):
            raise AssertionError(
                f"POLICY_LEAF_IN_EXCLUDED: golden leaf {leaf} matched an "
                f"excluded_runtime_fields entry (backend={backend})"
            )
        if len(classes) == 0:
            raise AssertionError(f"POLICY_LEAF_UNCOVERED: {leaf} has no rule (backend={backend})")
        if len(classes) > 1:
            raise AssertionError(
                f"POLICY_LEAF_MULTI_CLASSIFIED: {leaf} matched {classes} (backend={backend})"
            )


def assert_expected_output_matches(
    *,
    actual: dict[str, Any],
    expected_golden: dict[str, Any],
    backend: str,
) -> None:
    """Strict field-by-field comparison between the canonical actual
    (built by ``build_baseline_expected_output_actual``) and the
    frozen golden file.

    ``_comparison_policy`` is itself an expected JSON field — it is
    validated by ``validate_expected_output_comparison_policy`` and
    is NOT field-by-field compared here.

    On mismatch, prints ``JSON path / expected / actual / backend`` and
    raises ``AssertionError``.
    """
    expected = dict(expected_golden)
    expected.pop("_comparison_policy", None)

    def _walk(a: Any, e: Any, path: str) -> None:
        if type(a) is not type(e):
            raise AssertionError(
                f"TYPE_MISMATCH {path}: expected={type(e).__name__} {e!r}, "
                f"actual={type(a).__name__} {a!r} (backend={backend})"
            )
        if isinstance(a, dict):
            for k in sorted(set(a.keys()) | set(e.keys())):
                if k not in a:
                    raise AssertionError(
                        f"MISSING_ACTUAL {path}.{k}: expected={e[k]!r} (backend={backend})"
                    )
                if k not in e:
                    raise AssertionError(
                        f"EXTRA_ACTUAL {path}.{k}: actual={a[k]!r} (backend={backend})"
                    )
                _walk(a[k], e[k], f"{path}.{k}")
        elif isinstance(a, list):
            if len(a) != len(e):
                raise AssertionError(
                    f"LIST_LEN {path}: actual={len(a)}, expected={len(e)} (backend={backend})"
                )
            for i, (av, ev) in enumerate(zip(a, e, strict=True)):
                _walk(av, ev, f"{path}[{i}]")
        else:
            if a != e:
                raise AssertionError(
                    f"VALUE_MISMATCH {path}: expected={e!r}, actual={a!r} (backend={backend})"
                )

    _walk(actual, expected, "$")


def load_baseline_golden() -> dict[str, Any]:
    """Load the frozen ``baseline_feasible.v1.json`` golden from the
    test-tree relative path. The path is resolved from this helper
    module's location so the golden travels with the test code."""
    here = Path(__file__).resolve().parent
    golden_path = here / "data" / "expected" / "baseline_feasible.v1.json"
    with open(golden_path, encoding="utf-8") as f:
        return json.load(f)


__all__ = [
    "a1_engine",
    "a1_session_factory",
    "a2_pg_admin_url",
    "a2_pg_database",
    "a2_pg_engine",
    "a2_pg_session_factory",
    "seed_a1_all_prereqs",
    "seed_a1_project_and_version",
    "seed_a1_orchestration_prereqs",
    "seed_a1_calculation_runs",
    "seed_a1_source_binding",
    "seed_a1_weight_set_and_revision",
    "PROJECT_ID",
    "VERSION_ID",
    "EXEC_SNAPSHOT_ID",
    "COEFF_CONTEXT_ID",
    "IDENTITY_ID",
    "ATTEMPT_ID",
    "ZONE_RUN_ID",
    "COOL_RUN_ID",
    "EQUIP_RUN_ID",
    "POWER_RUN_ID",
    "INVEST_RUN_ID",
    "SOURCE_BINDING_ID",
    "WEIGHT_SET_ID",
    "WEIGHT_REVISION_ID",
    # Test-side expected-output helpers (Commit C, TASK-011B §5)
    "BASELINE_STAGE_LEDGER",
    "EXPECTED_OUTPUT_TOP_LEVEL_FIELDS",
    "build_baseline_expected_output_actual",
    "validate_expected_output_comparison_policy",
    "assert_expected_output_matches",
    "collect_golden_leaf_paths",
    "load_baseline_golden",
]
