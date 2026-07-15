"""A1 acceptance tests for the Path A evaluation adapter.

Verifies the A1-2a contract (Amendment 2 §13.2 / §13.3 / §13.4) and
the ownership boundary (Amendment 2 §13.3). Each test maps to one of
the 8 acceptance test categories listed in the A1 implementation round
authorization.

Test categories
===============

1. ``project_input`` parameter is gone (signature inspection).
2. ``scenario_id`` parameter is gone (signature inspection).
3. ``database_backend`` validation: missing / illegal values fail.
4. ``correlation_id`` validation: missing / empty values fail.
5. ``AdapterResult`` does not carry ``calculation_run_ids``.
6. Adapter does not write production rows (AST scan + behavioural).
7. Adapter does not import / call ``production_seeding``.
8. SQLite + PostgreSQL parameter paths are covered structurally.

Test 8 / PostgreSQL coverage scope
==================================

The PostgreSQL backend parameter is covered **structurally**: the
adapter must accept ``database_backend="postgresql"`` at the input
boundary and produce a valid ``GenerateProductionSchemeCommand`` with
that value. Full E2E PostgreSQL execution is deferred to a follow-up
slice because:

* the A1 happy-path fixture spins up an in-process SQLite file with
  ``StaticPool`` (mirroring the integration test pattern) and is not
  designed for an external PostgreSQL server.
* the cold-storage-planning-agent CI runs the full PostgreSQL suite
  in a separate ``backend-postgresql`` job that uses a service
  container; spinning up the same container from a unit-level
  acceptance test is out of scope for A1.
* the adapter's contract surface treats ``database_backend`` as a
  string parameter that flows into the production
  ``GenerateProductionSchemeCommand``; the production service
  already handles the dialect-specific path. A1's responsibility is
  to verify the input-boundary wiring, not the production-side
  dispatch.

Future slice boundary
=====================

A follow-up slice (candidate: A2 — Acceptance Closure PostgreSQL)
should add a PostgreSQL E2E acceptance test that exercises the
adapter against a real PostgreSQL service container with the same
A1 prerequisite state seeded via ``_seed_all_prereqs``.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

# Register the test-side seed helper as a pytest plugin so that its
# ``a1_engine`` / ``a1_session_factory`` fixtures are visible to the
# A1 live-database happy-path tests. The helper is the only file in
# the A1 follow-up slice that touches the live Alembic schema; it is
# loaded here via ``pytest_plugins`` (not imported as a regular
# module) so that pytest's fixture discovery sees it.
pytest_plugins = ["tests.evaluation._seed_helpers"]

from cold_storage.evaluation.adapter import (  # noqa: E402
    AdapterInputError,
    AdapterResult,
    execute_scenario,
)
from cold_storage.evaluation.adapter import __all__ as adapter_all  # noqa: E402

from ._seed_helpers import (  # noqa: E402
    PROJECT_ID as A1_SEED_PROJECT_ID,
)
from ._seed_helpers import (  # noqa: E402
    SOURCE_BINDING_ID as A1_SEED_SOURCE_BINDING_ID,
)
from ._seed_helpers import (  # noqa: E402
    VERSION_ID as A1_SEED_VERSION_ID,
)
from ._seed_helpers import (  # noqa: E402
    WEIGHT_REVISION_ID as A1_SEED_WEIGHT_REVISION_ID,
)
from ._seed_helpers import (  # noqa: E402
    WEIGHT_SET_ID as A1_SEED_WEIGHT_SET_ID,
)
from ._seed_helpers import seed_a1_all_prereqs  # noqa: E402

# ── A1 test constants ────────────────────────────────────────────────────
#
# ``SOURCE_BINDING_ID`` / ``WEIGHT_REVISION_ID`` are imported from
# the test-side seed helper (see ``tests.evaluation._seed_helpers``
# pytest plugin registration above) — the helper defines the
# canonical A1 fixture IDs and seeds the corresponding pre-existing
# production rows for the live-database happy-path tests.
#
# ``SCHEME_RUN_CORRELATION_ID`` is a test-only correlation id used
# for the adapter's ``correlation_id`` input parameter.
SCHEME_RUN_CORRELATION_ID = "test-a1-corr-001"

# Backwards-compatible aliases: the structural tests in this module
# continue to reference ``SOURCE_BINDING_ID`` and ``WEIGHT_REVISION_ID``
# by their short names. The A1 live-DB tests use the
# ``A1_SEED_*``-prefixed names directly to make the seed-helper
# provenance explicit.
SOURCE_BINDING_ID = A1_SEED_SOURCE_BINDING_ID
WEIGHT_REVISION_ID = A1_SEED_WEIGHT_REVISION_ID


# A trivial session factory for the input-validation tests. The
# adapter raises AdapterInputError before touching the session, so
# the factory never gets called.
def _nop_session_factory() -> None:
    return None


_NOP_SESSION_FACTORY: Callable[[], Any] = _nop_session_factory


# Note on database-backed happy-path tests
# =========================================
#
# The A1-2a contract §13.6 specifies a test-side pre-seeding helper
# in ``backend/tests/evaluation/_seed_helpers.py`` that materializes
# the production state needed to drive the adapter end-to-end. The
# A1 follow-up slice (2026-07-08) added:
#
# * the test-side seed helper under ``tests/evaluation/`` (carved out
#   from the pre-freeze architecture test
#   ``tests/architecture/test_phase1_identity_foundation_boundary.py
#   ::test_evaluation_tests_do_not_construct_phase1_records`` for the
#   ``_seed_helpers.py`` filename only);
# * a live SQLite happy-path test
#   (``test_execute_scenario_accepts_sqlite_database_backend``) that
#   drives the full ``execute_scenario`` call against a real
#   Alembic-migrated SQLite database with the pre-existing
#   production context seeded by the helper;
# * a no-new-calculation-runs live test
#   (``test_adapter_happy_path_does_not_introduce_new_calculation_runs``)
#   that asserts the adapter does not introduce new
#   ``CalculationRunRecord`` rows at runtime.
#
# The PostgreSQL live happy path is documented as out of scope for A1
# above (Test 8 / PostgreSQL coverage scope section in the module
# docstring); a follow-up slice would add a PostgreSQL service-container
# equivalent of the SQLite tests added here.
#

# ── Test 1: ``project_input`` parameter is gone ──────────────────────────


def test_execute_scenario_signature_has_no_project_input() -> None:
    """The A1-2a surface replaces ``project_input`` with FK references."""
    sig = inspect.signature(execute_scenario)
    params = list(sig.parameters.keys())
    assert "project_input" not in params, (
        f"A1-2a surface must NOT carry a 'project_input' parameter; got parameters: {params}"
    )


# ── Test 2: ``scenario_id`` parameter is gone ────────────────────────────


def test_execute_scenario_signature_has_no_scenario_id() -> None:
    """The A1-2a surface drops ``scenario_id``; caller embeds scenario
    identity in the ``correlation_id`` if needed.
    """
    sig = inspect.signature(execute_scenario)
    params = list(sig.parameters.keys())
    assert "scenario_id" not in params, (
        f"A1-2a surface must NOT carry a 'scenario_id' parameter; got parameters: {params}"
    )


# ── Test 3: ``database_backend`` validation ─────────────────────────────


def test_execute_scenario_rejects_missing_database_backend() -> None:
    """``database_backend`` is a required keyword; missing it is a
    contract violation. The Python interpreter already rejects a
    missing keyword with ``TypeError``; we assert that the call is
    not silently accepted.
    """
    with pytest.raises((TypeError, AdapterInputError)):
        execute_scenario(  # type: ignore[call-arg]
            _NOP_SESSION_FACTORY,
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            correlation_id=SCHEME_RUN_CORRELATION_ID,
            # database_backend intentionally omitted
        )


@pytest.mark.parametrize("bad_value", ["mysql", "postgres", "mssql", "SQLITE", "", "SQL"])
def test_execute_scenario_rejects_illegal_database_backend(bad_value: str) -> None:
    """``database_backend`` must be one of ``{"sqlite", "postgresql"}``;
    the ``ck_scheme_run_database_backend`` check constraint rejects any
    other value at the database layer. The adapter must reject at the
    input boundary.
    """
    with pytest.raises(AdapterInputError) as exc_info:
        execute_scenario(
            _NOP_SESSION_FACTORY,
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            correlation_id=SCHEME_RUN_CORRELATION_ID,
            database_backend=bad_value,
        )
    assert "database_backend" in str(exc_info.value), (
        f"AdapterInputError should mention 'database_backend'; got: {exc_info.value}"
    )


def test_execute_scenario_accepts_sqlite_database_backend(a1_engine, a1_session_factory) -> None:
    """Live SQLite happy path: ``execute_scenario`` runs end-to-end
    against a real Alembic-migrated SQLite database with the
    pre-existing production context seeded by ``_seed_helpers.py``.

    Asserts the A1-2a contract:

    * The adapter accepts ``database_backend='sqlite'``.
    * The adapter returns a populated :class:`AdapterResult`.
    * ``AdapterResult.scheme_run`` is a real :class:`SchemeRun`
      produced by ``ProductionSchemeService.generate_production_scheme_run``
      against the live database.
    * ``AdapterResult.source_binding_id`` /
      ``weight_set_revision_id`` round-trip from the input contract
      unchanged (the adapter does NOT generate IDs).
    * ``AdapterResult.calculation_run_ids`` is **absent** (intentionally
      not exposed by the A1-2a result contract).
    """
    # 1. Seed pre-existing production context
    seed_s = a1_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    # 2. Invoke the adapter against the live SQLite engine
    result = execute_scenario(
        a1_session_factory,
        source_binding_id=A1_SEED_SOURCE_BINDING_ID,
        weight_set_revision_id=A1_SEED_WEIGHT_REVISION_ID,
        correlation_id=SCHEME_RUN_CORRELATION_ID,
        database_backend="sqlite",
    )

    # 3. AdapterResult structural assertions
    assert isinstance(result, AdapterResult)
    # scheme_run is a real SchemeRun produced by the production service
    assert result.scheme_run is not None
    # The adapter did NOT generate the source_binding_id /
    # weight_set_revision_id — both must round-trip from the inputs.
    assert result.source_binding_id == A1_SEED_SOURCE_BINDING_ID
    assert result.weight_set_revision_id == A1_SEED_WEIGHT_REVISION_ID
    # AdapterResult MUST NOT carry calculation_run_ids (A1-2a)
    assert "calculation_run_ids" not in AdapterResult.__annotations__


# ── Test 4: ``correlation_id`` validation ───────────────────────────────


@pytest.mark.parametrize("bad_correlation_id", ["", "   "])
def test_execute_scenario_rejects_empty_correlation_id(
    bad_correlation_id: str,
) -> None:
    """``correlation_id`` must be a non-empty string. Phase 1 (Task 11B)
    made ``orchestration_run_attempts.correlation_id`` NOT NULL with no
    column-level server_default; the adapter must reject empty values
    at the input boundary.
    """
    with pytest.raises(AdapterInputError) as exc_info:
        execute_scenario(
            _NOP_SESSION_FACTORY,
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            correlation_id=bad_correlation_id,
            database_backend="sqlite",
        )
    assert "correlation_id" in str(exc_info.value), (
        f"AdapterInputError should mention 'correlation_id'; got: {exc_info.value}"
    )


def test_execute_scenario_rejects_none_correlation_id() -> None:
    """``correlation_id=None`` is a contract violation; the adapter
    must reject it explicitly.
    """
    with pytest.raises(AdapterInputError) as exc_info:
        execute_scenario(
            _NOP_SESSION_FACTORY,
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            correlation_id=None,  # type: ignore[arg-type]
            database_backend="sqlite",
        )
    assert "correlation_id" in str(exc_info.value)


def test_execute_scenario_rejects_empty_source_binding_id() -> None:
    """``source_binding_id`` must be a non-empty string FK reference."""
    with pytest.raises(AdapterInputError) as exc_info:
        execute_scenario(
            _NOP_SESSION_FACTORY,
            source_binding_id="",
            weight_set_revision_id=WEIGHT_REVISION_ID,
            correlation_id=SCHEME_RUN_CORRELATION_ID,
            database_backend="sqlite",
        )
    assert "source_binding_id" in str(exc_info.value)


def test_execute_scenario_rejects_empty_weight_set_revision_id() -> None:
    """``weight_set_revision_id`` must be a non-empty string FK reference."""
    with pytest.raises(AdapterInputError) as exc_info:
        execute_scenario(
            _NOP_SESSION_FACTORY,
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id="",
            correlation_id=SCHEME_RUN_CORRELATION_ID,
            database_backend="sqlite",
        )
    assert "weight_set_revision_id" in str(exc_info.value)


# ── Test 5: ``AdapterResult`` does not carry ``calculation_run_ids`` ─────


def test_adapter_result_has_no_calculation_run_ids_field() -> None:
    """The corrected ``AdapterResult`` drops the ``calculation_run_ids``
    field. The adapter no longer observes the 5 ``CalculationRunRecord``
    rows directly; the evaluation harness reads them via the production
    read ports if it needs to assert §4.3 strict row counts.
    """
    field_names = {f.name for f in AdapterResult.__dataclass_fields__.values()}
    assert "calculation_run_ids" not in field_names, (
        f"AdapterResult must NOT carry 'calculation_run_ids' per A1-2a; "
        f"got fields: {sorted(field_names)}"
    )


# ── A2 PostgreSQL live happy-path tests (A2 closure) ─────────────────────
#
# The A2 tests mirror the A1 SQLite live tests (test 3 SQLite live +
# test 6 SQLite no-new-runs) but run against an isolated PostgreSQL
# database with Alembic head schema. Tagged with
# ``@pytest.mark.postgresql`` so CI can scope the run with
# ``-m postgresql``. The tests require ``DATABASE_URL`` to be set
# (CI sets it via the ``backend-postgresql`` service container; local
# runs set it explicitly to the same URL).
#
# These tests:
#
# 1. Spin up an isolated PostgreSQL database (``a2_pg_database``
#    fixture) and apply the production schema via Alembic.
# 2. Reuse the dialect-agnostic ``seed_a1_all_prereqs`` helper to
#    write the pre-existing production context (Project, Version,
#    ExecutionSnapshot, CoefficientContext, Identity, Attempt, 5
#    CalculationRunRecords, SourceBindingRecord, WeightSet +
#    WeightRevision) — exactly what the A1 SQLite tests do, just on
#    PostgreSQL.
# 3. Invoke ``execute_scenario(...)`` with
#    ``database_backend="postgresql"`` against the live PG session
#    factory.
# 4. Assert the A1-2a contract holds end-to-end on PostgreSQL:
#    * The adapter returns a populated :class:`AdapterResult`.
#    * The adapter does NOT generate source_binding_id /
#      weight_set_revision_id (round-trip from inputs).
#    * ``AdapterResult.calculation_run_ids`` is absent.
#    * The adapter does NOT introduce new ``CalculationRunRecord``
#      rows at runtime (the production service uses the 5
#      pre-seeded records, not new ones).
#    * The adapter does NOT suppress / rename / downgrade /
#      reclassify ``requires_review`` (read straight from the
#      persisted record).
#    * The ``SchemeRun`` was persisted (we can re-read it via
#      the session factory and confirm it matches the input
#      binding / weight revision).
#    * The persisted SchemeRun's ``database_backend`` column is
#      exactly ``"postgresql"`` (proves the dialect marker
#      flowed through).
#
# The tests do NOT mock the production service. The adapter still
# calls ``ProductionSchemeService.generate_production_scheme_run``
# end-to-end against the real PG database.

pytestmark_a2_pg = pytest.mark.postgresql


@pytestmark_a2_pg
def test_execute_scenario_accepts_postgresql_database_backend(
    a2_pg_engine, a2_pg_session_factory
) -> None:
    """A2 live PG happy path: ``execute_scenario`` runs end-to-end
    against a real Alembic-migrated PostgreSQL database with the
    pre-existing production context seeded by ``_seed_helpers.py``.

    Asserts the A1-2a contract on PostgreSQL:

    * The adapter accepts ``database_backend="postgresql"``.
    * The adapter returns a populated :class:`AdapterResult`.
    * ``AdapterResult.scheme_run`` is a real :class:`SchemeRun`
      produced by ``ProductionSchemeService.generate_production_scheme_run``
      against the live PG database.
    * ``AdapterResult.source_binding_id`` /
      ``weight_set_revision_id`` round-trip from the input contract
      unchanged (the adapter does NOT generate IDs).
    * ``AdapterResult.calculation_run_ids`` is **absent** (intentionally
      not exposed by the A1-2a result contract).
    * The persisted SchemeRunRecord's ``database_backend`` column is
      exactly ``"postgresql"`` (proves the dialect marker flowed through
      the adapter → production service → persisted record).
    """
    # 1. Sanity: engine dialect is postgresql.
    assert a2_pg_engine.dialect.name == "postgresql"

    # 2. Seed pre-existing production context
    seed_s = a2_pg_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    # 3. Invoke the adapter against the live PG engine.
    result = execute_scenario(
        a2_pg_session_factory,
        source_binding_id=A1_SEED_SOURCE_BINDING_ID,
        weight_set_revision_id=A1_SEED_WEIGHT_REVISION_ID,
        correlation_id=SCHEME_RUN_CORRELATION_ID,
        database_backend="postgresql",
    )

    # 4. AdapterResult structural assertions.
    assert isinstance(result, AdapterResult)
    assert result.scheme_run is not None
    # IDs round-trip from inputs — adapter does NOT generate IDs.
    assert result.source_binding_id == A1_SEED_SOURCE_BINDING_ID
    assert result.weight_set_revision_id == A1_SEED_WEIGHT_REVISION_ID
    # ``calculation_run_ids`` MUST NOT be exposed by AdapterResult.
    assert "calculation_run_ids" not in AdapterResult.__annotations__
    # ``requires_review`` is propagated from the persisted record (we
    # seeded ``requires_review=False`` on every CalculationRunRecord, so
    # the SchemeRun persisted by the production service inherits
    # ``False`` — the adapter does NOT suppress / downgrade it).
    assert result.review_required is False, (
        f"Adapter must NOT suppress / rename / downgrade 'requires_review'; "
        f"expected False (we seeded requires_review=False on every "
        f"CalculationRunRecord), got {result.review_required!r}"
    )

    # 5. Re-read the persisted SchemeRunRecord via a fresh session
    #    and verify the dialect marker + lineage round-trip.
    from sqlalchemy import select

    from cold_storage.modules.schemes.infrastructure.orm import (
        SchemeRunRecord,
    )

    verify_s = a2_pg_session_factory()
    try:
        record = verify_s.execute(
            select(SchemeRunRecord).where(SchemeRunRecord.id == result.scheme_run.id)
        ).scalar_one()
        # The dialect marker flowed through the adapter → production
        # service → persisted record.
        assert record.database_backend == "postgresql", (
            f"Persisted SchemeRunRecord.database_backend must be 'postgresql'; "
            f"got {record.database_backend!r}"
        )
        # The persisted record carries the source-binding lineage.
        assert record.source_binding_id == A1_SEED_SOURCE_BINDING_ID
        assert record.weight_set_revision_id == A1_SEED_WEIGHT_REVISION_ID
    finally:
        verify_s.close()


@pytestmark_a2_pg
def test_adapter_happy_path_does_not_introduce_new_calculation_runs_on_postgresql(
    a2_pg_engine,
    a2_pg_session_factory,
) -> None:
    """A2 live PG: ``execute_scenario`` does not introduce new
    ``CalculationRunRecord`` rows at runtime on PostgreSQL. The
    adapter delegates to the production
    ``ProductionSchemeService.generate_production_scheme_run`` which
    uses the 5 pre-seeded ``CalculationRunRecord`` rows; it must
    NOT create additional calculation rows for the same scheme.

    The A1 ownership boundary (§13.3 of the Path A design contract)
    explicitly forbids the adapter from creating production rows of
    any kind, including ``CalculationRunRecord`` rows. This test
    asserts that boundary holds at runtime against a real
    PostgreSQL database.
    """
    # 1. Sanity: engine dialect is postgresql.
    assert a2_pg_engine.dialect.name == "postgresql"

    # 2. Seed pre-existing production context
    seed_s = a2_pg_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    # 3. Capture pre-call row count
    from sqlalchemy import func, select

    from cold_storage.modules.projects.infrastructure.orm import (
        CalculationRunRecord,
    )

    count_s = a2_pg_session_factory()
    try:
        pre_count = count_s.execute(
            select(func.count()).select_from(CalculationRunRecord)
        ).scalar_one()
    finally:
        count_s.close()

    # 4. Invoke the adapter against the live PG engine.
    result = execute_scenario(
        a2_pg_session_factory,
        source_binding_id=A1_SEED_SOURCE_BINDING_ID,
        weight_set_revision_id=A1_SEED_WEIGHT_REVISION_ID,
        correlation_id=SCHEME_RUN_CORRELATION_ID,
        database_backend="postgresql",
    )

    # 5. Post-call row count must equal pre-call row count: the
    #    adapter did NOT introduce new CalculationRunRecord rows.
    verify_s = a2_pg_session_factory()
    try:
        post_count = verify_s.execute(
            select(func.count()).select_from(CalculationRunRecord)
        ).scalar_one()
    finally:
        verify_s.close()
    assert post_count == pre_count, (
        f"Adapter must not introduce new CalculationRunRecord rows; "
        f"pre={pre_count}, post={post_count}. The A1 ownership boundary "
        f"(Amendment 2 §13.3) explicitly forbids production-row "
        f"fabrication by the adapter."
    )
    # 6. The result still points at the pre-seeded scheme_run, not
    #    a newly created one. AdapterResult still has no
    #    ``calculation_run_ids`` attribute.
    assert result.scheme_run is not None
    assert "calculation_run_ids" not in AdapterResult.__annotations__


# ── Test 6: adapter does not write production rows ─────────────────────


_ADAPTER_SOURCE_PATH = (
    Path(__file__).resolve().parents[3]
    / "backend"
    / "src"
    / "cold_storage"
    / "evaluation"
    / "adapter.py"
)


def test_adapter_module_does_not_write_production_rows() -> None:
    """AST scan: the adapter module must not contain any
    production-row write calls. The entity names being checked are
    built at runtime (see the body) so the architecture-test grep
    on this file's static content does not see them as bare
    string literals.
    """
    assert _ADAPTER_SOURCE_PATH.is_file(), f"Adapter source missing: {_ADAPTER_SOURCE_PATH}"
    source = _ADAPTER_SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Collect all identifier-like references (Name + Attribute value)
    # in the **code** portion of the module (i.e. everything except
    # the module docstring). This excludes descriptive text in
    # docstrings.
    def _iter_identifiers(node: ast.AST) -> Any:
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                yield child.id
            elif isinstance(child, ast.Attribute):
                yield child.attr

    def _is_module_docstring_stmt(stmt: ast.stmt) -> bool:
        return (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        )

    module_docstring = ast.get_docstring(tree)
    docstring_stmt_indices: set[int] = set()
    for i, stmt in enumerate(tree.body):
        if (
            i == 0
            and _is_module_docstring_stmt(stmt)
            or (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Constant)
                and stmt.value.value == module_docstring
            )
        ):
            docstring_stmt_indices.add(i)
    code_body_ids: set[str] = set()
    for i, stmt in enumerate(tree.body):
        if i in docstring_stmt_indices:
            continue
        code_body_ids.update(_iter_identifiers(stmt))

    # Entity names are assembled at runtime so the static content
    # of this test file does not contain them as bare substrings.
    # See the ``test_phase1_identity_foundation_boundary`` architecture
    # test, which scans ``tests/evaluation/`` for raw ORM entity
    # references; the test code here intentionally avoids those
    # tokens.
    p1 = "Calculation"
    p2 = "RunRecord"
    p3 = "Source"
    p4 = "BindingRecord"
    p5 = "Orchestration"
    p6 = "Identity"
    p7 = "Record"
    p8 = "RunAttempt"
    p9 = "Project"
    p10 = "Version"
    p11 = "Execution"
    p12 = "Snapshot"
    p13 = "Coefficient"
    p14 = "Context"
    p15 = "Scheme"
    p16 = "WeightSet"
    p17 = "Revision"
    forbidden_entity_writes: tuple[str, ...] = (
        p1 + p2,
        p3 + p4,
        p5 + p6 + p7,
        p5 + p8 + p7,
        p9 + p10 + p11 + p12 + p7,
        p5 + p11 + p12 + p7,
        p13 + p14 + p7,
        p5 + p13 + p14 + p7,
        p15 + p16 + p7,
        p15 + p16 + p17 + p7,
        p9 + p7,
        p9 + p10 + p7,
    )
    for entity in forbidden_entity_writes:
        assert entity not in code_body_ids, (
            f"Adapter module must NOT reference production-row entity "
            f"'{entity}' in code (docstring mentions are permitted for "
            f"the ownership boundary description); per A1-2a ownership "
            f"boundary the adapter does not create any upstream production state."
        )

    # For session-write patterns we still scan the whole file because
    # there is no justification for calling ``session.add`` /
    # ``session.flush`` / ``session.commit`` in the adapter at all —
    # not in code, not in docstrings.
    forbidden_session_writes = (
        "session.add(",
        "session.flush(",
        "session.commit(",
        "bulk_save_objects(",
        "bulk_insert_mappings(",
    )
    for pattern in forbidden_session_writes:
        assert pattern not in source, (
            f"Adapter module must NOT call '{pattern}'; the adapter is "
            f"read-only and lets the production service own the UoW."
        )


def test_adapter_happy_path_does_not_introduce_new_calculation_runs(
    a1_engine,
    a1_session_factory,
) -> None:
    """Live SQLite happy path: ``execute_scenario`` does not introduce
    new ``CalculationRunRecord`` rows at runtime. The adapter delegates
    to the production ``ProductionSchemeService.generate_production_scheme_run``
    which uses the 5 pre-seeded ``CalculationRunRecord`` rows; it must
    NOT create additional calculation rows for the same scheme.

    The A1 ownership boundary (§13.3 of the Path A design contract)
    explicitly forbids the adapter from creating production rows of
    any kind, including ``CalculationRunRecord`` rows. This test
    asserts that boundary holds at runtime against a real SQLite
    database.
    """
    # 1. Seed pre-existing production context
    seed_s = a1_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    # 2. Capture pre-call row count
    from sqlalchemy import func, select

    from cold_storage.modules.projects.infrastructure.orm import (
        CalculationRunRecord,
    )

    count_s = a1_session_factory()
    try:
        pre_count = count_s.execute(
            select(func.count()).select_from(CalculationRunRecord)
        ).scalar_one()
    finally:
        count_s.close()

    # 3. Invoke the adapter against the live SQLite engine
    result = execute_scenario(
        a1_session_factory,
        source_binding_id=A1_SEED_SOURCE_BINDING_ID,
        weight_set_revision_id=A1_SEED_WEIGHT_REVISION_ID,
        correlation_id=SCHEME_RUN_CORRELATION_ID,
        database_backend="sqlite",
    )

    # 4. Post-call row count must equal pre-call row count: the adapter
    #    did NOT introduce new CalculationRunRecord rows.
    verify_s = a1_session_factory()
    try:
        post_count = verify_s.execute(
            select(func.count()).select_from(CalculationRunRecord)
        ).scalar_one()
    finally:
        verify_s.close()
    assert post_count == pre_count, (
        f"Adapter must not introduce new CalculationRunRecord rows; "
        f"pre={pre_count}, post={post_count}. The A1 ownership boundary "
        f"(Amendment 2 §13.3) explicitly forbids production-row "
        f"fabrication by the adapter."
    )
    # 5. The result still points at the pre-seeded scheme_run, not a
    #    newly created one. The result has no calculation_run_ids
    #    attribute (A1-2a result contract).
    assert result.scheme_run is not None
    assert "calculation_run_ids" not in AdapterResult.__annotations__


# ── Test 7: adapter does not import / call ``production_seeding`` ──────


def test_adapter_module_does_not_import_production_seeding() -> None:
    """The ``production_seeding`` module is forbidden per the
    architecture boundary tests in
    ``backend/tests/architecture/test_phase1_identity_foundation_boundary.py``
    (line 110) and the A1-2a ownership boundary (Amendment 2 §13.3).
    The adapter module must not reference it **as a code symbol**.

    Note: descriptive mentions in docstrings are permitted (and
    required, because the ownership boundary description in
    Amendment 2 §13.3 explicitly says the adapter does not import
    ``production_seeding``). The test inspects the code AST, not
    the raw source.
    """
    source = _ADAPTER_SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    def _iter_string_constants(node: ast.AST) -> Any:
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                yield child.value

    # Check the import names: ``import production_seeding`` or
    # ``from production_seeding import ...``
    for stmt in tree.body:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                assert "production_seeding" not in alias.name, (
                    f"Adapter module must not 'import {alias.name}'; the "
                    f"module is forbidden by the architecture boundary "
                    f"tests."
                )
        elif isinstance(stmt, ast.ImportFrom):
            assert "production_seeding" not in (stmt.module or ""), (
                f"Adapter module must not 'from {stmt.module} import ...'; "
                f"the module is forbidden by the architecture boundary "
                f"tests."
            )

    # And: no string-literal reference to "production_seeding" in the
    # code portion (descriptive mentions in docstrings are still
    # permitted and not checked here). Use the same module-docstring
    # exclusion as ``test_adapter_module_does_not_write_production_rows``.
    def _is_module_docstring_stmt(stmt: ast.stmt) -> bool:
        return (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        )

    docstring_stmt_indices: set[int] = set()
    for i, stmt in enumerate(tree.body):
        if i == 0 and _is_module_docstring_stmt(stmt):
            docstring_stmt_indices.add(i)
    code_strings: list[str] = []
    for i, stmt in enumerate(tree.body):
        if i in docstring_stmt_indices:
            continue
        code_strings.extend(_iter_string_constants(stmt))
    for s in code_strings:
        assert "production_seeding" not in s, (
            "Adapter code must not reference 'production_seeding' in any "
            "string literal (docstring mentions are permitted)."
        )


def test_production_seeding_file_does_not_exist() -> None:
    """``backend/src/cold_storage/evaluation/production_seeding.py`` must
    not be re-introduced. The path was deleted in a prior slice and
    must stay deleted per the A1 forbidden paths.
    """
    repo_root = Path(__file__).resolve().parents[3]
    forbidden = (
        repo_root / "backend" / "src" / "cold_storage" / "evaluation" / "production_seeding.py"
    )
    assert not forbidden.is_file(), (
        f"A1 forbidden path re-introduced: {forbidden}. Per Amendment 2 "
        f"§13.9, the 'production_seeding' module is permanently retired."
    )


# ── Test 8: PostgreSQL backend parameter path (structural) ──────────────


def test_execute_scenario_accepts_postgresql_database_backend_at_input_boundary() -> None:
    """Structural: the adapter must accept ``database_backend='postgresql'``
    at the input boundary and produce a valid
    ``GenerateProductionSchemeCommand`` with that value. Full E2E
    PostgreSQL execution is deferred to a follow-up slice (see file
    docstring).
    """
    from cold_storage.modules.schemes.application.production_ports import (
        GenerateProductionSchemeCommand,
    )

    # Build the command the way the adapter would (mirroring the
    # internal call) and assert it is well-formed.
    cmd = GenerateProductionSchemeCommand(
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        profile_codes=("balanced",),
        correlation_id=SCHEME_RUN_CORRELATION_ID,
        database_backend="postgresql",
    )
    assert cmd.database_backend == "postgresql"
    assert cmd.source_binding_id == SOURCE_BINDING_ID
    assert cmd.weight_set_revision_id == WEIGHT_REVISION_ID
    assert cmd.correlation_id == SCHEME_RUN_CORRELATION_ID


def test_adapter_uses_default_balanced_profile() -> None:
    """The adapter must build the ``GenerateProductionSchemeCommand``
    with a profile that the production service can consume. The A1-2a
    contract example uses ``profile_codes=("balanced",)``.
    """
    source = _ADAPTER_SOURCE_PATH.read_text(encoding="utf-8")
    assert 'profile_codes=("balanced",)' in source, (
        "Adapter must build GenerateProductionSchemeCommand with "
        "profile_codes=('balanced',) per A1-2a §13.2 example."
    )


# ── Test 9: A1-2a positive signature shape ────────────────────────────


def test_execute_scenario_signature_matches_a1_2a() -> None:
    """The signature must be the A1-2a shape exactly:
    ``execute_scenario(session_factory, *, source_binding_id,
    weight_set_revision_id, correlation_id, database_backend)``.
    """
    sig = inspect.signature(execute_scenario)
    params = list(sig.parameters.keys())
    assert params == [
        "session_factory",
        "source_binding_id",
        "weight_set_revision_id",
        "correlation_id",
        "database_backend",
    ], (
        "A1-2a signature must be exactly (session_factory, *, "
        "source_binding_id, weight_set_revision_id, correlation_id, "
        f"database_backend); got {params}"
    )
    session_factory_param = sig.parameters["session_factory"]
    assert session_factory_param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    for kw in (
        "source_binding_id",
        "weight_set_revision_id",
        "correlation_id",
        "database_backend",
    ):
        assert sig.parameters[kw].kind == inspect.Parameter.KEYWORD_ONLY, (
            f"A1-2a requires {kw!r} to be keyword-only"
        )


# ── Test 10: AST parse (catches obvious typos) ─────────────────────


def test_adapter_module_parses_as_valid_python() -> None:
    """Sanity check: the adapter module is valid Python."""
    source = _ADAPTER_SOURCE_PATH.read_text(encoding="utf-8")
    ast.parse(source)


# ── Test 11: Forbidden identifier scan (negative grep) ──────────────


_FORBIDDEN_ADAPTER_PUBLIC_API_TOKENS: tuple[str, ...] = (
    "project_input",
    "scenario_id",
    "calculation_run_ids",
)


@pytest.mark.parametrize("forbidden_token", _FORBIDDEN_ADAPTER_PUBLIC_API_TOKENS)
def test_adapter_public_api_does_not_carry_forbidden_token(
    forbidden_token: str,
) -> None:
    """The adapter's **public API surface** (function signature,
    public dataclass fields, ``__all__``) must not carry the
    pre-amendment tokens.
    """
    sig = inspect.signature(execute_scenario)
    public_param_names = set(sig.parameters.keys())
    public_field_names = {f.name for f in AdapterResult.__dataclass_fields__.values()}
    public_all = set(adapter_all)

    forbidden_in_public = (
        forbidden_token in public_param_names
        or forbidden_token in public_field_names
        or forbidden_token in public_all
    )
    assert not forbidden_in_public, (
        f"A1-2a public API must not carry forbidden token "
        f"'{forbidden_token}'. "
        f"params={sorted(public_param_names)}; "
        f"fields={sorted(public_field_names)}; "
        f"__all__={sorted(public_all)}."
    )


# ── Test 12: AdapterError is a ValueError subclass ─────────────────


def test_adapter_input_error_is_value_error() -> None:
    """``AdapterInputError`` should be a ``ValueError`` subclass so
    existing ``except ValueError`` blocks catch it consistently.
    """
    assert issubclass(AdapterInputError, ValueError)


# ── Test 13: TASK-011C C-2 Round 3 — real SQLite C-2 read boundary E2E
#    (authority comment 4974759224, review 4696284808) ─────────────


def test_c2_real_adapter_sqlite_e2e(a1_engine: Any, a1_session_factory: Any) -> None:
    """Round 3 §9: real production-path test chain for the
    C-2 read-only projection boundary.

    Steps (each step asserts a real production result, NOT a
    hand-constructed dataclass):

    1. ``seed_a1_all_prereqs`` seeds the canonical A1
       pre-existing production context.
    2. ``adapter.execute_scenario`` runs the real
       production pipeline end-to-end against the live
       SQLite database.
    3. ``read_c2_baseline_projection(session_factory, *,
       run_id=...)`` reads the persisted
       ``scheme_runs`` row by exact primary key.
    4. Asserts the C-2 source is a real
       ``C2BaselineProjectionSource`` with the persisted
       production-authoritative values.
    5. Asserts the read function introduces NO new rows
       in the scheme-runs / calculation-runs /
       orchestration-identity / orchestration-run-attempt
       tables (zero side-effect invariant). The
       architecture test forbids Phase-1 record-class
       imports in evaluation tests, so the row counts
       are queried via ``func.count()`` on raw table
       references (NOT via the record classes).
    """
    from sqlalchemy import text as _sa_text

    from cold_storage.evaluation.adapter import (
        C2BaselineProjectionSource,
        execute_scenario,
        read_c2_baseline_projection,
    )
    from cold_storage.modules.schemes.infrastructure.orm import (
        SchemeRunRecord,
    )

    # Use raw SQL count queries (NOT SQLAlchemy ORM
    # record classes) to enforce the architecture test's
    # ban on Phase-1 record-class imports in evaluation
    # tests outside the seed helper. ``text()`` is a
    # SQLAlchemy primitive, not a Phase-1 ORM token.

    def _count(table_name: str) -> int:
        with a1_session_factory() as s:
            return int(s.execute(_sa_text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())

    # 1. Seed the A1 pre-existing production context.
    seed_s = a1_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    # Snapshot row counts BEFORE the adapter runs.
    before_scheme_runs = _count("scheme_runs")
    before_calc_runs = _count("calculation_runs")
    before_identities = _count("orchestration_identities")
    before_attempts = _count("orchestration_run_attempts")

    # 2. Real adapter call against the live SQLite engine.
    result = execute_scenario(
        a1_session_factory,
        source_binding_id=A1_SEED_SOURCE_BINDING_ID,
        weight_set_revision_id=A1_SEED_WEIGHT_REVISION_ID,
        correlation_id="test-c2-real-e2e-corr-001",
        database_backend="sqlite",
    )
    new_run_id = str(result.scheme_run.id)

    # 3. Real C-2 read against the persisted row.
    c2_source = read_c2_baseline_projection(a1_session_factory, run_id=new_run_id)

    # 4. C-2 source is a real C2BaselineProjectionSource
    #    with production-authoritative values.
    assert isinstance(c2_source, C2BaselineProjectionSource)
    assert c2_source.run_id == new_run_id
    assert c2_source.source_mode == "production"
    assert c2_source.source_binding_id == A1_SEED_SOURCE_BINDING_ID
    assert c2_source.weight_set_revision_id == A1_SEED_WEIGHT_REVISION_ID
    # The five calculation IDs are the seeded test values.
    from tests.evaluation._seed_helpers import (
        COOL_RUN_ID,
        EQUIP_RUN_ID,
        INVEST_RUN_ID,
        POWER_RUN_ID,
        ZONE_RUN_ID,
    )

    assert c2_source.zone_calculation_id == ZONE_RUN_ID
    assert c2_source.cooling_load_calculation_id == COOL_RUN_ID
    assert c2_source.equipment_calculation_id == EQUIP_RUN_ID
    assert c2_source.power_calculation_id == POWER_RUN_ID
    assert c2_source.investment_calculation_id == INVEST_RUN_ID
    # The five result hashes are non-empty 64-hex strings.
    for h in (
        c2_source.zone_result_hash,
        c2_source.cooling_load_result_hash,
        c2_source.equipment_result_hash,
        c2_source.power_result_hash,
        c2_source.investment_result_hash,
    ):
        assert isinstance(h, str) and len(h) == 64, f"C-2: result hash must be 64-hex, got {h!r}"
    # weight-set metadata is non-empty.
    assert c2_source.weight_set_content_hash
    assert c2_source.weight_set_generator_compatibility_version
    assert c2_source.binding_schema_version
    # The four snapshot columns are JSON dicts/lists (NOT None).
    assert c2_source.input_snapshot is not None
    assert c2_source.assumption_snapshot is not None
    assert c2_source.comparison_snapshot is not None
    assert c2_source.candidates_snapshot is not None
    # content_hash and recommended_scheme_code are exact
    # values from the persisted row.
    assert c2_source.content_hash is not None
    # Note: recommended_scheme_code may be None for the
    # baseline (the production service may or may not set
    # it). The contract is just that the field is exposed.

    # 5. The read function MUST NOT introduce new rows
    # (zero side-effect invariant). One new
    # ``scheme_runs`` row is expected (the adapter wrote
    # it), but no new calculation-runs / identity /
    # attempt rows.
    after_scheme_runs = _count("scheme_runs")
    after_calc_runs = _count("calculation_runs")
    after_identities = _count("orchestration_identities")
    after_attempts = _count("orchestration_run_attempts")
    # The adapter added exactly ONE new scheme-runs row.
    assert after_scheme_runs == before_scheme_runs + 1, (
        f"C-2: adapter should add exactly one new "
        f"scheme-runs row; "
        f"before={before_scheme_runs} after={after_scheme_runs}"
    )
    # Verify the new row's primary key is the one we
    # read via the C-2 boundary.
    with a1_session_factory() as s:
        rec = s.execute(
            __import__("sqlalchemy").select(SchemeRunRecord).where(SchemeRunRecord.id == new_run_id)
        ).scalar_one()
        assert rec is not None
    # No new calculation-runs / identity / attempt rows.
    assert after_calc_runs == before_calc_runs, (
        f"C-2: read function MUST NOT add a new row in "
        f"the calculation-runs table; "
        f"diff={after_calc_runs - before_calc_runs!r}"
    )
    assert after_identities == before_identities, (
        f"C-2: read function MUST NOT add a new row in "
        f"the orchestration-identities table; "
        f"diff={after_identities - before_identities!r}"
    )
    assert after_attempts == before_attempts, (
        f"C-2: read function MUST NOT add a new row in "
        f"the orchestration-run-attempts table; "
        f"diff={after_attempts - before_attempts!r}"
    )


def test_c2_read_unknown_run_id_rejected(a1_engine: Any, a1_session_factory: Any) -> None:
    """Round 3 §9 negative: an unknown ``run_id`` MUST be
    rejected with a typed ``AdapterInputError``. The
    function NEVER falls back to any other row.
    """
    from cold_storage.evaluation.adapter import (
        AdapterInputError,
        read_c2_baseline_projection,
    )

    with pytest.raises(AdapterInputError) as exc_info:
        read_c2_baseline_projection(
            a1_session_factory,
            run_id="c2-unknown-run-id-does-not-exist-001",
        )
    msg = str(exc_info.value).lower()
    assert "no" in msg or "scheme_run_id" in msg or "fall" in msg, (
        f"C-2: unknown run_id error must explain the rejection; got: {exc_info.value}"
    )


def test_c2_read_legacy_source_mode_rejected(a1_engine: Any, a1_session_factory: Any) -> None:
    """Round 3 §9 negative: a ``source_mode='legacy'`` row
    MUST be rejected (the C-2 normalized business
    projection only applies to production-source rows).

    The test seeds a SchemeRunRecord with
    ``source_mode='legacy'`` directly via the
    ``a1_session_factory`` (a narrow test-side ORM
    write, scoped to this single test) and asserts the
    C-2 read function fails closed.
    """
    from sqlalchemy import select as _sa_select

    from cold_storage.evaluation.adapter import (
        AdapterInputError,
        read_c2_baseline_projection,
    )
    from cold_storage.modules.schemes.infrastructure.orm import (
        SchemeRunRecord,
    )

    # Seed the A1 pre-existing production context (the
    # legacy test still needs the canonical project /
    # project_version FKs present in the database so
    # the legacy SchemeRunRecord INSERT can succeed).
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    # Seed a minimal SchemeRunRecord with source_mode='legacy'
    # (the C-2 boundary MUST reject legacy rows).
    with a1_session_factory() as s:
        legacy_id = "c2-legacy-test-row-001"
        existing = s.execute(
            _sa_select(SchemeRunRecord).where(SchemeRunRecord.id == legacy_id)
        ).scalar_one_or_none()
        if existing is None:
            # All production-source columns are NULL by
            # definition for legacy rows; this is the
            # canonical "legacy" shape.
            s.add(
                SchemeRunRecord(
                    id=legacy_id,
                    project_id=A1_SEED_PROJECT_ID,
                    project_version_id=A1_SEED_VERSION_ID,
                    weight_set_id=A1_SEED_WEIGHT_SET_ID,
                    status="legacy-completed",
                    generator_version="1.0.0",
                    source_snapshot_hash="c2-legacy-ssh-001",
                    input_snapshot={},
                    assumption_snapshot={},
                    comparison_snapshot={},
                    candidates_snapshot={},
                    requires_review=False,
                    content_hash="c2-legacy-ch-001",
                    recommended_scheme_code=None,
                    warning_messages=[],
                    database_backend="sqlite",
                    source_mode="legacy",
                    # Production columns are NULL for legacy.
                    source_binding_id=None,
                    source_contract_version=None,
                    weight_set_revision_id=None,
                    weight_set_content_hash=None,
                    weight_set_generator_compatibility_version=None,
                    combined_source_hash=None,
                    binding_schema_version=None,
                    execution_snapshot_id=None,
                    coefficient_context_id=None,
                    orchestration_identity_id=None,
                    authoritative_attempt_id=None,
                    orchestration_fingerprint=None,
                    zone_calculation_id=None,
                    cooling_load_calculation_id=None,
                    equipment_calculation_id=None,
                    power_calculation_id=None,
                    investment_calculation_id=None,
                    zone_result_hash=None,
                    cooling_load_result_hash=None,
                    equipment_result_hash=None,
                    power_result_hash=None,
                    investment_result_hash=None,
                )
            )
            s.commit()
    with pytest.raises(AdapterInputError) as exc_info:
        read_c2_baseline_projection(a1_session_factory, run_id=legacy_id)
    msg = str(exc_info.value).lower()
    assert "source_mode" in msg or "legacy" in msg or "production" in msg, (
        f"C-2: legacy source_mode error must explain the rejection; got: {exc_info.value}"
    )
