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

import json
import hashlib

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

BASELINE_CORRELATION_ID = "test-a15-baseline-001"  # unified with sqlite test for cross-backend canonical identity
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
        correlation_id=BASELINE_CORRELATION_ID,
        database_backend="postgresql",
    )

    assert isinstance(result, ScenarioOutcome)
    assert result.outcome == "SUCCEEDED"
    assert result.database_backend == "postgresql"
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
        correlation_id=BASELINE_CORRELATION_ID,
        database_backend="postgresql",
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
        correlation_id=BASELINE_CORRELATION_ID,
        database_backend="postgresql",
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
        correlation_id=BASELINE_CORRELATION_ID,
        database_backend="postgresql",
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
        correlation_id=BASELINE_CORRELATION_ID,
        database_backend="postgresql",
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
        correlation_id=BASELINE_CORRELATION_ID,
        database_backend="postgresql",
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
        correlation_id=BASELINE_CORRELATION_ID,
        database_backend="postgresql",
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
        correlation_id=HIGH_THROUGHPUT_CORRELATION_ID,
        database_backend="postgresql",
    )
    assert result.outcome == "SUCCEEDED"
    assert result.database_backend == "postgresql"


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
            correlation_id=BASELINE_CORRELATION_ID,
            database_backend="postgresql",
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
        correlation_id=BASELINE_CORRELATION_ID,
        database_backend="postgresql",
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

# ── Test 24 — baseline golden comparison (canonical expected-output) ──
# PostgreSQL mirror: this test MUST
# construct the canonical expected-output shape from the persisted
# SchemeRunRecord + input_snapshot of a real production-path
# ``run_scenario`` call, then compare it field-by-field with the
# frozen ``baseline_feasible.v1.json`` golden. NO mock / stub /
# fixture-only call is permitted. Failure MUST print the JSON path
# / expected / actual / backend for the first mismatch.


def _build_canonical_actual(scheme_run_record, input_snapshot, assumption_snapshot):
    """Build the canonical expected-output shape from the persisted
    SchemeRunRecord + input_snapshot. Strips frozen-exclusion fields
    (id, created_at, completed_at, content_hash, phase_b_blocked,
    warning_messages, database_backend)."""
    p = scheme_run_record
    inp = input_snapshot or {}
    canonical = {
        "schema_version": "task11b-expected-output.v1",
        "scenario_id": "baseline_feasible",
        "expected_outcome": "SUCCEEDED",
        "scheme_status": str(p.status),
        "combined_source_hash": str(p.combined_source_hash),
        "review_required": bool(p.requires_review),
        "review_reasons": list(p.warning_messages or []),
        "source_binding_proxy": str(p.source_binding_id),
        "weight_set_revision_proxy": str(p.weight_set_revision_id),
        "project_id": str(p.project_id),
        "project_version_id": str(p.project_version_id),
        "stage_ledger": ["zone", "cooling_load", "equipment", "power", "investment"],
        "production_outputs": {
            "generator_version": str(p.generator_version),
            "source_mode": str(p.source_mode),
            "binding_schema_version": str(p.binding_schema_version),
            "weight_set_generator_compatibility_version": str(p.weight_set_generator_compatibility_version),
            "weight_set_content_hash": str(p.weight_set_content_hash),
            "source_calculation_ids": {
                "zone": str(p.zone_calculation_id),
                "cooling_load": str(p.cooling_load_calculation_id),
                "equipment": str(p.equipment_calculation_id),
                "power": str(p.power_calculation_id),
                "investment": str(p.investment_calculation_id),
            },
            "source_snapshot_hashes": {
                "zone": str(p.zone_result_hash),
                "cooling_load": str(p.cooling_load_result_hash),
                "equipment": str(p.equipment_result_hash),
                "power": str(p.power_result_hash),
                "investment": str(p.investment_result_hash),
            },
            "candidates_snapshot": p.candidates_snapshot,
            "comparison_snapshot": p.comparison_snapshot,
            "assumption_snapshot": dict(assumption_snapshot or {}),
            "cooling_load_result": inp.get("cooling_load_result"),
            "equipment_result": inp.get("equipment_result"),
            "investment_result": inp.get("investment_result"),
            "power_result": inp.get("power_result"),
            "zone_results": inp.get("zone_results"),
            "profile_codes": inp.get("profile_codes"),
            "profile_parameters": inp.get("profile_parameters"),
            "total_daily_throughput_kg_day": inp.get("total_daily_throughput_kg_day"),
            "total_position_count": inp.get("total_position_count"),
            "total_storage_capacity_kg": inp.get("total_storage_capacity_kg"),
            "weight_set_id": inp.get("weight_set_id"),
        },
    }
    cr = p.candidates_snapshot[0]["constraint_results"]
    np_ = sum(1 for c in cr if c["passed"])
    nf_ = sum(1 for c in cr if not c["passed"])
    fc = [c["constraint_code"] for c in cr if not c["passed"]]
    canonical["constraint_check_summary"] = {
        "expected_passed_count": np_,
        "expected_failed_count": nf_,
        "expected_failed_code": fc[0] if fc else None,
    }
    # content_hash derived cross-backend normalized (canonical SHA of stripped body)
    _EXCLUDE = {"id", "created_at", "completed_at", "content_hash", "phase_b_blocked", "warning_messages", "database_backend", "_sa_instance_state"}
    body = {k: v for k, v in p.__dict__.items() if k not in _EXCLUDE}
    canonical_body = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    canonical["content_hash"] = hashlib.sha256(canonical_body.encode()).hexdigest()
    return canonical


def _compare_canonical_actual(actual, expected, backend):
    """Strict field-by-field comparison; on mismatch prints JSON path /
    expected / actual / backend and raises AssertionError."""
    def _walk(a, e, path):
        if type(a) != type(e):
            raise AssertionError(f"TYPE_MISMATCH {path}: actual={type(a).__name__} {a!r}, expected={type(e).__name__} {e!r} (backend={backend})")
        if isinstance(a, dict):
            # Skip _comparison_policy — it is meta-documentation about how
            # to perform the comparison, not a value produced by the
            # production adapter. Per §15.3 it is required in the golden
            # JSON; per §15.4 it is NOT in the exact_match_fields list.
            for k in sorted(set(a.keys()) | set(e.keys())):
                if k == "_comparison_policy":
                    continue
                if k not in a:
                    raise AssertionError(f"MISSING_ACTUAL {path}.{k}: expected={e[k]!r} (backend={backend})")
                if k not in e:
                    raise AssertionError(f"EXTRA_ACTUAL {path}.{k}: actual={a[k]!r} (backend={backend})")
                _walk(a[k], e[k], f"{path}.{k}")
        elif isinstance(a, list):
            if len(a) != len(e):
                raise AssertionError(f"LIST_LEN {path}: actual={len(a)}, expected={len(e)} (backend={backend})")
            for i, (av, ev) in enumerate(zip(a, e)):
                _walk(av, ev, f"{path}[{i}]")
        else:
            if a != e:
                raise AssertionError(f"VALUE_MISMATCH {path}: expected={e!r}, actual={a!r} (backend={backend})")
    _walk(actual, expected, "$")


def test_baseline_golden_consumed_by_production_path(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """The frozen ``baseline_feasible.v1.json`` golden is consumed by
    a real SQLite acceptance-path ``run_scenario`` call. The test:

    1. Seeds the pre-existing production context via
       ``seed_a1_all_prereqs`` (no mock / stub) on PostgreSQL.
    2. Calls ``run_scenario`` against the real adapter.
    3. Constructs the canonical expected-output shape from the
       persisted SchemeRunRecord + input_snapshot.
    4. Compares it field-by-field with
       ``backend/tests/evaluation/data/expected/baseline_feasible.v1.json``.
    5. On mismatch, prints the JSON path / expected / actual /
       backend and fails.

    Forbidden: file-exists / hash-non-empty shortcuts. Forbidden:
    fuzzy global tolerance. Forbidden: ignore-numerical-fields
    contracts. This test MUST produce a per-field error if any
    field diverges.
    """
    # 1. seed
    seed_s = a2_pg_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    # 2. real production-path call
    result = run_scenario(
        a2_pg_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_id=BASELINE_CORRELATION_ID,
        database_backend="postgresql",
    )
    assert isinstance(result, ScenarioOutcome)
    assert result.outcome == "SUCCEEDED"
    assert result.phase_b_blocked is False

    # 3. build canonical actual
    with a2_pg_session_factory() as s:
        rec = s.execute(
            select(SchemeRunRecord).where(SchemeRunRecord.id == result.scheme_run.id)
        ).scalar_one()
        # re-fetch input_snapshot from the same row (it's stored as JSON column)
        input_snapshot = dict(rec.input_snapshot or {})
        # assumption_snapshot is a column on SchemeRunRecord (NOT on
        # SourceBindingRecord); the production adapter writes it into
        # SchemeRunRecord.assumption_snapshot as a JSON dict.
        assumption_snapshot = dict(rec.assumption_snapshot or {})
    actual = _build_canonical_actual(rec, input_snapshot, assumption_snapshot)

    # 4. load golden
    golden_path = (
        Path(__file__).parent / "data" / "expected" / "baseline_feasible.v1.json"
    )
    with open(golden_path) as f:
        expected = json.load(f)

    # 5. strict comparison
    _compare_canonical_actual(actual, expected, backend="postgresql")
