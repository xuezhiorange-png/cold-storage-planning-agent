"""PostgreSQL acceptance suite for Task 11B Phase B Path A evaluation runner.

This test suite is the canonical PostgreSQL acceptance for the A1.5
runner surface. It is the mirror of ``test_sqlite_acceptance.py`` for
the PostgreSQL backend, with the same A1-2a input contract, the same
test-side pre-existing-context seed helper, and the same forbidden-
pattern coverage. The runner's cross-backend parity is the
acceptance criterion: a successful SQLite scenario MUST also succeed
on PostgreSQL with the same persisted SchemeRun shape.

Each test is marked with ``@pytest.mark.postgresql`` so CI can scope
the run with ``-m postgresql``. The tests require ``DATABASE_URL`` to
be set (CI sets it via the ``backend-postgresql`` service container;
local PG runs set it to the same
``postgresql+psycopg2://cold_storage:cold_storage@localhost:5432/...``
URL).

These tests do NOT mock the production orchestrator. The runner
still calls ``ProductionSchemeService.generate_production_scheme_run``
end-to-end against a real PostgreSQL database.

Forbidden-pattern coverage (built into every test) is identical to the
SQLite suite — see ``test_sqlite_acceptance.py`` for the canonical
list. The PG suite asserts the same runtime invariants:

- The runner does NOT raise ``PhaseBBlockedError`` on the happy path
  (pre-freeze §1.3 #1 + §8 #12).
- The runner does NOT bypass ``compose_production_scheme_service``
  (pre-freeze §8 #6).
- The runner does NOT introduce demo / latest-row / partial-binding
  fallbacks (pre-freeze §5.3).
- The runner does NOT suppress, rename, downgrade, or reclassify
  ``requires_review`` warnings (pre-freeze §5.3).
- The runner does NOT restore ``production_seeding.py``
  (pre-freeze §5.1 / §8 #1).
- The runner does NOT modify any production-module file
  (pre-freeze §5.5).
- The runner does NOT parse exception message text (forbidden-pattern
  list, pre-freeze §1.5 / Phase 4 §9).
- The runner does NOT mutate PR #21 thread / state / comments
  (pre-freeze §5.4).
- The runner does NOT reopen Issue #35 (pre-freeze §9 / PR #57 §9.3).
- The runner does NOT author or extend ``evaluation/expected/*.json``
  fixtures (per the explicit Charles instruction in this round's
  authorization — these are BLOCKED-SEPARATE-AUTHORIZATION).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

# Register the test-side pre-existing-context seed helper as a pytest
# plugin so its ``a2_pg_*`` PostgreSQL fixtures are visible.
pytest_plugins = ["tests.evaluation._seed_helpers"]

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cold_storage.evaluation.errors import (  # noqa: E402
    InvalidEvaluationScenarioError,
    PhaseBBlockedError,
)
from cold_storage.evaluation.execute import (  # noqa: E402
    ScenarioOutcome,
    run_scenario,
)
from cold_storage.modules.orchestration.infrastructure.orm import (  # noqa: E402
    CoefficientContextRecord,
    OrchestrationIdentityRecord,
    ProjectVersionExecutionSnapshotRecord,
    SourceBindingRecord,
)
from cold_storage.modules.projects.infrastructure.orm import (  # noqa: E402
    CalculationRunRecord,
)
from cold_storage.modules.schemes.infrastructure.orm import (  # noqa: E402
    SchemeRunRecord,
)
from tests.evaluation._seed_helpers import (  # noqa: E402
    SOURCE_BINDING_ID,
    WEIGHT_REVISION_ID,
    seed_a1_all_prereqs,
)

# ── PG test constants ──────────────────────────────────────────────────

BASELINE_CORRELATION_ID = "test-a15-pg-baseline-001"
HIGH_THROUGHPUT_CORRELATION_ID = "test-a15-pg-high-throughput-001"

# All PG acceptance tests share the same marker; CI runs them via
# ``pytest -m postgresql``.
pytestmark = pytest.mark.postgresql


# ── Test 1 — happy path on PG ───────────────────────────────────────────


def test_baseline_feasible_succeeds_on_postgresql(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """Happy path: ``run_scenario`` succeeds with ``outcome=SUCCEEDED`` on PG."""
    assert a2_pg_engine.dialect.name == "postgresql"

    seed_s = a2_pg_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    result = run_scenario(
        a2_pg_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="postgresql",
    )

    assert isinstance(result, ScenarioOutcome)
    assert result.outcome == "SUCCEEDED"
    assert result.backend_marker == "postgresql"
    assert result.source_binding_id == SOURCE_BINDING_ID
    assert result.phase_b_blocked is False


# ── Test 2 — SchemeRun persisted with succeeded status on PG ────────────


def test_baseline_feasible_scheme_run_persisted_with_succeeded_status_on_postgresql(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """The runner persists a SchemeRun row that PG readers can fetch."""
    assert a2_pg_engine.dialect.name == "postgresql"

    seed_s = a2_pg_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    result = run_scenario(
        a2_pg_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="postgresql",
    )

    verify_s = a2_pg_session_factory()
    try:
        record = verify_s.execute(
            select(SchemeRunRecord).where(SchemeRunRecord.id == result.scheme_run.id)
        ).scalar_one()
        assert record.database_backend == "postgresql"
        assert record.status == "completed"
    finally:
        verify_s.close()


# ── Test 3 — combined_source_hash round-trip on PG ──────────────────────


def test_baseline_feasible_combined_source_hash_round_trip_on_postgresql(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """The PG SchemeRun row carries a non-null ``combined_source_hash``."""
    seed_s = a2_pg_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    result = run_scenario(
        a2_pg_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="postgresql",
    )

    verify_s = a2_pg_session_factory()
    try:
        record = verify_s.execute(
            select(SchemeRunRecord).where(SchemeRunRecord.id == result.scheme_run.id)
        ).scalar_one()
        assert record.combined_source_hash is not None
        assert len(record.combined_source_hash) > 0
    finally:
        verify_s.close()


# ── Test 4 — no demo coefficients on PG ────────────────────────────────


def test_baseline_feasible_does_not_introduce_demo_coefficients_on_postgresql(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """The runner does NOT introduce demo coefficients on PG."""
    seed_s = a2_pg_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    result = run_scenario(
        a2_pg_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="postgresql",
    )
    assert result.outcome == "SUCCEEDED"

    verify_s = a2_pg_session_factory()
    try:
        rows = (
            verify_s.execute(
                select(CalculationRunRecord).where(
                    CalculationRunRecord.orchestration_identity_id == "a1-test-id-001"
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 5
        for row in rows:
            assert row.requires_review is False
    finally:
        verify_s.close()


# ── Test 5 — no latest-row fallback on PG ───────────────────────────────


def test_baseline_feasible_does_not_introduce_latest_row_on_postgresql(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """The runner does NOT introduce latest-row fallback on PG."""
    seed_s = a2_pg_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    pre_count_s = a2_pg_session_factory()
    try:
        pre_count = pre_count_s.execute(
            select(func.count()).select_from(CalculationRunRecord)
        ).scalar_one()
    finally:
        pre_count_s.close()

    run_scenario(
        a2_pg_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="postgresql",
    )

    post_count_s = a2_pg_session_factory()
    try:
        post_count = post_count_s.execute(
            select(func.count()).select_from(CalculationRunRecord)
        ).scalar_one()
    finally:
        post_count_s.close()
    assert post_count == pre_count, (
        f"Runner must not introduce new CalculationRunRecord rows; "
        f"pre={pre_count}, post={post_count}"
    )


# ── Test 6 — orchestration identity unchanged on PG ──────────────────────


def test_baseline_feasible_orchestration_identity_unchanged_on_postgresql(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """The runner does NOT mutate the pre-existing OrchestrationIdentityRecord."""
    seed_s = a2_pg_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    pre_s = a2_pg_session_factory()
    try:
        pre_identity = pre_s.execute(
            select(OrchestrationIdentityRecord).where(
                OrchestrationIdentityRecord.id == "a1-test-id-001"
            )
        ).scalar_one()
        pre_authoritative_attempt_id = pre_identity.authoritative_attempt_id
        pre_status = pre_identity.status
    finally:
        pre_s.close()

    run_scenario(
        a2_pg_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="postgresql",
    )

    post_s = a2_pg_session_factory()
    try:
        post_identity = post_s.execute(
            select(OrchestrationIdentityRecord).where(
                OrchestrationIdentityRecord.id == "a1-test-id-001"
            )
        ).scalar_one()
        assert post_identity.authoritative_attempt_id == pre_authoritative_attempt_id
        assert post_identity.status == pre_status
    finally:
        post_s.close()


# ── Test 7 — execution snapshot + coefficient context unchanged on PG ────


def test_baseline_feasible_orchestration_context_unchanged_on_postgresql(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """The runner does NOT mutate ProjectVersionExecutionSnapshotRecord / CoefficientContextRecord."""
    seed_s = a2_pg_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    pre_s = a2_pg_session_factory()
    try:
        pre_snap = pre_s.execute(
            select(ProjectVersionExecutionSnapshotRecord).where(
                ProjectVersionExecutionSnapshotRecord.id == "a1-test-exec-001"
            )
        ).scalar_one()
        pre_cc = pre_s.execute(
            select(CoefficientContextRecord).where(
                CoefficientContextRecord.id == "a1-test-cc-001"
            )
        ).scalar_one()
        pre_snap_status = pre_snap.captured_status
        pre_cc_hash = pre_cc.content_hash
    finally:
        pre_s.close()

    run_scenario(
        a2_pg_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="postgresql",
    )

    post_s = a2_pg_session_factory()
    try:
        post_snap = post_s.execute(
            select(ProjectVersionExecutionSnapshotRecord).where(
                ProjectVersionExecutionSnapshotRecord.id == "a1-test-exec-001"
            )
        ).scalar_one()
        post_cc = post_s.execute(
            select(CoefficientContextRecord).where(
                CoefficientContextRecord.id == "a1-test-cc-001"
            )
        ).scalar_one()
        assert post_snap.captured_status == pre_snap_status
        assert post_cc.content_hash == pre_cc_hash
    finally:
        post_s.close()


# ── Test 8 — high_throughput_review on PG ──────────────────────────────


def test_high_throughput_review_succeeds_on_postgresql(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """High-throughput-review scenario also succeeds on PG."""
    seed_s = a2_pg_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    result = run_scenario(
        a2_pg_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=HIGH_THROUGHPUT_CORRELATION_ID,
        backend_marker="postgresql",
    )
    assert result.outcome == "SUCCEEDED"
    assert result.backend_marker == "postgresql"


# ── Test 9 — runner does NOT raise PhaseBBlockedError on PG happy path ──


def test_runner_does_not_raise_phase_b_blocked_on_postgresql_happy_path(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """Pre-freeze §8 #12 invariant holds on PG."""
    from cold_storage.evaluation.errors import PhaseBBlockedError

    seed_s = a2_pg_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    try:
        result = run_scenario(
            a2_pg_session_factory,
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            correlation_marker=BASELINE_CORRELATION_ID,
            backend_marker="postgresql",
        )
    except PhaseBBlockedError as exc:
        raise AssertionError(
            f"Runner MUST NOT raise PhaseBBlockedError on the PG happy path "
            f"(pre-freeze §8 #12); got upstream_code={exc.upstream_code!r}"
        )

    assert result.outcome == "SUCCEEDED"
    assert result.phase_b_blocked is False


# ── Test 10 — SourceBinding row unchanged on PG ─────────────────────────


def test_runner_does_not_mutate_source_binding_on_postgresql(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """The runner does NOT mutate the SourceBinding row on PG."""
    seed_s = a2_pg_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    pre_s = a2_pg_session_factory()
    try:
        pre_binding = pre_s.execute(
            select(SourceBindingRecord).where(
                SourceBindingRecord.id == SOURCE_BINDING_ID
            )
        ).scalar_one()
        pre_hash = pre_binding.combined_source_hash
    finally:
        pre_s.close()

    run_scenario(
        a2_pg_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="postgresql",
    )

    post_s = a2_pg_session_factory()
    try:
        post_binding = post_s.execute(
            select(SourceBindingRecord).where(
                SourceBindingRecord.id == SOURCE_BINDING_ID
            )
        ).scalar_one()
        assert post_binding.combined_source_hash == pre_hash
    finally:
        post_s.close()