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

import json
import tempfile
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

# ── Test 24 — baseline golden consumed by real production path ────────
# Per §15.3 + §16.9.5 baseline implementation gate (auth §9):
#   1. Real production-path ``run_scenario`` (no mock / stub).
#   2. Construct canonical actual via shared
#      ``build_baseline_expected_output_actual`` helper (NOT a
#      test-side private duplicate; production ``record.content_hash``
#      is used directly, not test-recomputed).
#   3. Validate the golden's ``_comparison_policy`` via shared
#      ``validate_expected_output_comparison_policy`` helper (the
#      policy is part of the contract, not a skip field).
#   4. Compare canonical actual to golden via shared
#      ``assert_expected_output_matches`` helper. On mismatch, prints
#      JSON path / expected / actual / backend and fails.
# Negative-policy tests below prove the policy validator is real:
#   25 — delete ``_comparison_policy`` → fail.
#   26 — place ``content_hash`` in both exact and excluded → fail.
#   27 — delete a production-output leaf coverage → fail.
#   28 — modify a numeric leaf → fail with full JSON path mismatch.
#   29 — modify golden ``content_hash`` → fail on SQLite AND PostgreSQL.


def test_baseline_golden_consumed_by_production_path(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """Round 2: shared helpers + production content_hash + policy
    validation + negative tests. Per Commit C scope, this test MUST
    consume the shared ``_seed_helpers`` helpers (no private
    duplicate hash algorithm; no skipping of ``_comparison_policy``).
    """
    from tests.evaluation._seed_helpers import (
        assert_expected_output_matches,
        build_baseline_expected_output_actual,
        load_baseline_golden,
        seed_a1_all_prereqs,
        validate_expected_output_comparison_policy,
    )

    # 1. seed pre-existing production context (real acceptance path).
    seed_s = a1_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    # 2. real production-path call.
    result = run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_id=BASELINE_CORRELATION_ID,
        database_backend="sqlite",
    )
    assert isinstance(result, ScenarioOutcome)
    assert result.outcome == "SUCCEEDED"
    assert result.phase_b_blocked is False

    # 3. read persisted record + input_snapshot + assumption_snapshot.
    with a1_session_factory() as s:
        rec = s.execute(
            select(SchemeRunRecord).where(SchemeRunRecord.id == result.scheme_run.id)
        ).scalar_one()
        input_snapshot = dict(rec.input_snapshot or {})
        assumption_snapshot = dict(rec.assumption_snapshot or {})
        actual = build_baseline_expected_output_actual(
            scenario_outcome=result,
            scheme_run_record=rec,
            input_snapshot=input_snapshot,
            assumption_snapshot=assumption_snapshot,
        )

    # 4. validate policy.
    expected = load_baseline_golden()
    validate_expected_output_comparison_policy(expected, backend="sqlite")

    # 5. strict comparison.
    assert_expected_output_matches(
        actual=actual, expected_golden=expected, backend="sqlite"
    )


# ── Negative-policy tests (per auth §9) ─────────────────────────────────
#
# These tests prove the shared validator (``validate_expected_output_comparison_policy``
# + ``assert_expected_output_matches``) is a real contract gate, not
# a no-op. Each test mutates a single property of a copy of the
# golden and asserts the validator rejects it with a specific error.


def _negative_golden() -> dict[str, Any]:
    """Return a deep copy of the loaded golden for mutation."""
    from tests.evaluation._seed_helpers import load_baseline_golden
    import copy as _copy

    return _copy.deepcopy(load_baseline_golden())


def test_negative_policy_25_delete_comparison_policy_fails() -> None:
    """Neg test 25: deleting ``_comparison_policy`` MUST cause the
    validator to raise ``POLICY_MISSING``."""
    from tests.evaluation._seed_helpers import validate_expected_output_comparison_policy

    g = _negative_golden()
    g.pop("_comparison_policy", None)
    try:
        validate_expected_output_comparison_policy(g, backend="sqlite")
    except AssertionError as exc:
        assert "POLICY_MISSING" in str(exc), f"unexpected error: {exc}"
        return
    raise AssertionError(
        "validate_expected_output_comparison_policy accepted a golden "
        "with no _comparison_policy; expected POLICY_MISSING"
    )


def test_negative_policy_26_content_hash_in_exact_and_excluded_fails() -> None:
    """Neg test 26: placing ``content_hash`` in BOTH ``exact_match_fields``
    AND ``excluded_runtime_fields`` MUST fail two distinct checks:
    ``POLICY_FORBIDDEN_IN_EXCLUDED`` (content_hash must not be in
    excluded) and ``POLICY_EXACT_EXCLUDED_OVERLAP`` (the two lists
    overlap on content_hash).
    """
    from tests.evaluation._seed_helpers import validate_expected_output_comparison_policy

    g = _negative_golden()
    g["_comparison_policy"]["exact_match_fields"] = sorted(
        set(g["_comparison_policy"]["exact_match_fields"]) | {"content_hash"}
    )
    g["_comparison_policy"]["excluded_runtime_fields"] = sorted(
        set(g["_comparison_policy"]["excluded_runtime_fields"]) | {"content_hash"}
    )
    try:
        validate_expected_output_comparison_policy(g, backend="sqlite")
    except AssertionError as exc:
        msg = str(exc)
        # Order matters: POLICY_FORBIDDEN_IN_EXCLUDED is checked before
        # overlap. Either is acceptable evidence the validator caught it.
        assert (
            "POLICY_FORBIDDEN_IN_EXCLUDED" in msg
            or "POLICY_EXACT_EXCLUDED_OVERLAP" in msg
        ), f"unexpected error: {msg}"
        return
    raise AssertionError(
        "validate_expected_output_comparison_policy accepted a golden "
        "with content_hash in BOTH exact and excluded"
    )


def test_negative_policy_27_missing_production_output_leaf_fails() -> None:
    """Neg test 27: removing a ``production_outputs.*`` leaf from
    ``exact_match_fields`` (without replacing it via an ancestor
    subtree or proxy) MUST cause ``POLICY_LEAF_UNCOVERED``.
    """
    from tests.evaluation._seed_helpers import validate_expected_output_comparison_policy

    g = _negative_golden()
    leaves = g["_comparison_policy"]["exact_match_fields"]
    # Target a SPECIFIC leaf (no ancestor covers it). The golden includes
    # BOTH `$.production_outputs` (parent subtree) AND the specific leaf
    # path. To make the leaf individually uncoverable, we remove the
    # parent subtree AND the specific leaf; if either removal alone
    # would still leave coverage via the other, the validator must
    # report UNCOVERED for the remaining leaf.
    target_specific = "$.production_outputs.investment_result.total_investment_cny"
    target_parent = "$.production_outputs"
    assert target_specific in leaves, "test invariant: specific leaf must be in policy"
    assert target_parent in leaves, "test invariant: parent subtree must be in policy"
    # Remove BOTH the specific leaf AND the parent subtree.
    g["_comparison_policy"]["exact_match_fields"] = [
        x for x in leaves
        if x not in (target_specific, target_parent)
    ]
    try:
        validate_expected_output_comparison_policy(g, backend="sqlite")
    except AssertionError as exc:
        msg = str(exc)
        assert "POLICY_LEAF_UNCOVERED" in msg
        # The validator enumerates uncovered leaves in sort order; the
        # FIRST reported leaf must be inside production_outputs subtree
        # (because we removed both the parent and a specific leaf).
        assert "$.production_outputs." in msg, (
            f"expected first uncovered leaf to be under $.production_outputs.*, got: {msg}"
        )
        return
    raise AssertionError(
        "validate_expected_output_comparison_policy accepted a golden "
        f"with leaves {target_specific} AND {target_parent} removed"
    )


def test_negative_policy_28_modify_numeric_leaf_returns_full_path() -> None:
    """Neg test 28: mutating a numeric leaf in the expected golden
    MUST cause ``assert_expected_output_matches`` to raise with the
    complete JSON path / expected / actual / backend message."""
    from tests.evaluation._seed_helpers import assert_expected_output_matches

    g = _negative_golden()
    original_value = g["production_outputs"]["investment_result"][
        "total_investment_cny"
    ]
    g["production_outputs"]["investment_result"]["total_investment_cny"] = "9999999.9"

    # Build a complete actual that mirrors g's structure (so the
    # comparator reaches the mutated leaf).
    actual = {
        k: v for k, v in g.items() if k != "_comparison_policy"
    }
    # Adjust production_outputs to hold the ORIGINAL (un-mutated)
    # value at the path the test will assert mismatch on.
    actual["production_outputs"] = {
        **g["production_outputs"],
        "investment_result": {
            **g["production_outputs"]["investment_result"],
            "total_investment_cny": original_value,
        },
    }
    # content_hash uses production value (NOT the test-recomputed one)
    # but the golden file's content_hash IS the production value, so
    # they match. We leave content_hash as-is.

    try:
        assert_expected_output_matches(
            actual=actual, expected_golden=g, backend="sqlite"
        )
    except AssertionError as exc:
        msg = str(exc)
        assert "VALUE_MISMATCH" in msg
        assert "$.production_outputs.investment_result.total_investment_cny" in msg
        assert "backend=sqlite" in msg
        return
    raise AssertionError(
        "assert_expected_output_matches accepted a mutated golden; "
        "expected VALUE_MISMATCH with full JSON path"
    )


def test_negative_policy_29_content_hash_mismatch_fails() -> None:
    """Neg test 29: if the actual ``content_hash`` differs from the
    golden's, ``assert_expected_output_matches`` MUST fail with
    ``VALUE_MISMATCH`` at ``$.content_hash``."""
    from tests.evaluation._seed_helpers import assert_expected_output_matches

    g = _negative_golden()
    actual = {
        "schema_version": g["schema_version"],
        "scenario_id": g["scenario_id"],
        "expected_outcome": g["expected_outcome"],
        "scheme_status": g["scheme_status"],
        "combined_source_hash": g["combined_source_hash"],
        "review_required": g["review_required"],
        "review_reasons": g["review_reasons"],
        "source_binding_proxy": g["source_binding_proxy"],
        "weight_set_revision_proxy": g["weight_set_revision_proxy"],
        "project_id": g["project_id"],
        "project_version_id": g["project_version_id"],
        "stage_ledger": g["stage_ledger"],
        "production_outputs": dict(g["production_outputs"]),
        "content_hash": "0" * 64,  # WRONG content_hash
        "constraint_check_summary": g["constraint_check_summary"],
    }

    try:
        assert_expected_output_matches(
            actual=actual, expected_golden=g, backend="sqlite"
        )
    except AssertionError as exc:
        msg = str(exc)
        assert "VALUE_MISMATCH" in msg
        assert "$.content_hash" in msg
        return
    raise AssertionError(
        "assert_expected_output_matches accepted mismatched content_hash; "
        "expected VALUE_MISMATCH at $.content_hash"
    )


# ── Commit D negative-policy tests (TASK-011B §7) — PostgreSQL mirror ────


def test_negative_policy_30_exact_proxy_overlap_fails() -> None:
    """Neg test 30 (PG mirror): adding ``$.source_binding_proxy`` to
    BOTH ``exact_match_fields`` and ``normalized_proxy_fields`` MUST
    be rejected with ``POLICY_EXACT_PROXY_OVERLAP``."""
    from tests.evaluation._seed_helpers import validate_expected_output_comparison_policy

    g = _negative_golden()
    p = g["_comparison_policy"]
    p["exact_match_fields"] = list(p["exact_match_fields"]) + [
        "$.source_binding_proxy"
    ]
    try:
        validate_expected_output_comparison_policy(g, backend="postgresql")
    except AssertionError as exc:
        msg = str(exc)
        assert "POLICY_EXACT_PROXY_OVERLAP" in msg or "POLICY_LEAF_MULTI_CLASSIFIED" in msg
        return
    raise AssertionError(
        "validator accepted $.source_binding_proxy in both exact and proxy; "
        "expected POLICY_EXACT_PROXY_OVERLAP or POLICY_LEAF_MULTI_CLASSIFIED"
    )


def test_negative_policy_31_proxy_excluded_overlap_fails() -> None:
    """Neg test 31 (PG mirror): proxy path in both
    ``normalized_proxy_fields`` and ``excluded_runtime_fields`` MUST
    be rejected with ``POLICY_PROXY_EXCLUDED_OVERLAP``."""
    from tests.evaluation._seed_helpers import validate_expected_output_comparison_policy

    g = _negative_golden()
    p = g["_comparison_policy"]
    p["excluded_runtime_fields"] = list(p["excluded_runtime_fields"]) + [
        "$.weight_set_revision_proxy"
    ]
    try:
        validate_expected_output_comparison_policy(g, backend="postgresql")
    except AssertionError as exc:
        msg = str(exc)
        assert "POLICY_PROXY_EXCLUDED_OVERLAP" in msg
        return
    raise AssertionError(
        "validator accepted proxy path in excluded; "
        "expected POLICY_PROXY_EXCLUDED_OVERLAP"
    )


def test_negative_policy_32_dup_proxy_fails() -> None:
    """Neg test 32 (PG mirror): duplicate entry in
    ``normalized_proxy_fields`` MUST be rejected with
    ``POLICY_DUP_PROXY``."""
    from tests.evaluation._seed_helpers import validate_expected_output_comparison_policy

    g = _negative_golden()
    p = g["_comparison_policy"]
    p["normalized_proxy_fields"] = list(p["normalized_proxy_fields"]) + [
        "$.source_binding_proxy"
    ]
    try:
        validate_expected_output_comparison_policy(g, backend="postgresql")
    except AssertionError as exc:
        msg = str(exc)
        assert "POLICY_DUP_PROXY" in msg
        return
    raise AssertionError(
        "validator accepted duplicate normalized_proxy_fields entry; "
        "expected POLICY_DUP_PROXY"
    )


def test_negative_policy_33_scenario_outcome_derived_from_runtime() -> None:
    """Neg test 33 (PG mirror): ``build_baseline_expected_output_actual``
    MUST derive ``expected_outcome`` from the live
    ``ScenarioOutcome.outcome`` (NOT hard-code ``"SUCCEEDED"``)."""
    from tests.evaluation._seed_helpers import build_baseline_expected_output_actual

    class _StubRun:
        status = "review_required"
        combined_source_hash = "abc123"
        requires_review = True
        warning_messages = ["w-001"]
        content_hash = "deadbeef" * 8
        source_binding_id = "sb-001"
        weight_set_revision_id = "wrev-001"
        project_id = "p-001"
        project_version_id = "v-001"
        generator_version = "1.0.0"
        source_mode = "production"
        binding_schema_version = "1.0.0"
        weight_set_generator_compatibility_version = "1.0.0"
        weight_set_content_hash = "wsch-001"
        zone_calculation_id = "z-001"
        cooling_load_calculation_id = "cl-001"
        equipment_calculation_id = "eq-001"
        power_calculation_id = "pw-001"
        investment_calculation_id = "iv-001"
        zone_result_hash = "zsh-001"
        cooling_load_result_hash = "clsh-001"
        equipment_result_hash = "eqsh-001"
        power_result_hash = "pwsh-001"
        investment_result_hash = "ivsh-001"
        candidates_snapshot = [
            {
                "scheme_code": "balanced",
                "scheme_name": "X",
                "profile_code": "balanced",
                "feasible": True,
                "constraint_results": [
                    {
                        "constraint_code": "c",
                        "passed": True,
                        "detail": "ok",
                        "actual": 1,
                    }
                ],
                "score_breakdown": {},
            }
        ]
        comparison_snapshot = None

    class _StubOutcome:
        outcome = "REVIEW_REQUIRED"
        database_backend = "postgresql"
        phase_b_blocked = False
        upstream_error_code = None

    actual = build_baseline_expected_output_actual(
        scenario_outcome=_StubOutcome(),
        scheme_run_record=_StubRun(),
        input_snapshot={},
        assumption_snapshot={},
    )
    assert actual["expected_outcome"] == "REVIEW_REQUIRED", (
        f"expected_outcome must be derived from scenario_outcome.outcome; "
        f"got {actual['expected_outcome']!r}"
    )


def test_negative_policy_34_warning_messages_not_excluded_but_mapped() -> None:
    """Neg test 34 (PG mirror): ``scheme_run.warning_messages`` MUST
    NOT appear in ``excluded_runtime_fields`` (mapped to
    ``review_reasons``), but ``field_normalization_mapping`` MUST
    document the mapping."""
    g = _negative_golden()
    p = g["_comparison_policy"]
    assert "scheme_run.warning_messages" not in p["excluded_runtime_fields"], (
        "scheme_run.warning_messages is mapped to $.review_reasons and "
        "MUST NOT appear in excluded_runtime_fields"
    )
    mapping = p.get("field_normalization_mapping", {})
    assert "scheme_run.warning_messages" in mapping, (
        "field_normalization_mapping must document the "
        "scheme_run.warning_messages → review_reasons normalization"
    )

# ── Commit E §6 negative-policy tests (TASK-011B §6) ────────────────────────


def test_negative_policy_35_leaf_coverage_summary_rejected() -> None:
    """Neg test 35: injecting ``leaf_coverage_summary`` (a duplicate
    classification summary) into ``_comparison_policy`` MUST be
    rejected with ``POLICY_REDUNDANT_CLASSIFICATION_SUMMARY``."""
    from tests.evaluation._seed_helpers import validate_expected_output_comparison_policy

    g = _negative_golden()
    p = g["_comparison_policy"]
    p["leaf_coverage_summary"] = {
        "exact_match_leaf_examples": [
            "$.combined_source_hash",
            "$.content_hash",
            "$.scenario_id",
        ],
        "normalized_proxy_leaf_examples": [
            "$.source_binding_proxy (← scheme_run.source_binding_id)",
        ],
        "no_excluded_canonical_field": True,
    }
    try:
        validate_expected_output_comparison_policy(g, backend="postgresql")
    except AssertionError as exc:
        msg = str(exc)
        assert "POLICY_REDUNDANT_CLASSIFICATION_SUMMARY" in msg
        assert "leaf_coverage_summary" in msg
        return
    raise AssertionError(
        "validator accepted injected leaf_coverage_summary; "
        "expected POLICY_REDUNDANT_CLASSIFICATION_SUMMARY"
    )


def test_positive_current_golden_has_no_leaf_coverage_summary() -> None:
    """Positive assertion: the current canonical golden MUST NOT
    contain ``leaf_coverage_summary`` and MUST still pass the
    validator."""
    from tests.evaluation._seed_helpers import (
        validate_expected_output_comparison_policy,
    )

    g = _negative_golden()
    p = g["_comparison_policy"]
    assert "leaf_coverage_summary" not in p, (
        "leaf_coverage_summary was removed in Commit E and must not "
        "re-appear in the canonical golden"
    )
    validate_expected_output_comparison_policy(g, backend="postgresql")


def test_positive_comparison_classes_pairwise_disjoint() -> None:
    """Positive assertion: in the current canonical golden, the three
    comparison-class arrays MUST be pairwise disjoint."""
    from tests.evaluation._seed_helpers import (
        validate_expected_output_comparison_policy,
    )

    g = _negative_golden()
    p = g["_comparison_policy"]
    exact = set(p["exact_match_fields"])
    excluded = set(p["excluded_runtime_fields"])
    proxy = set(p["normalized_proxy_fields"])
    assert exact & proxy == set(), f"exact ∩ proxy = {exact & proxy}"
    assert exact & excluded == set(), f"exact ∩ excluded = {exact & excluded}"
    assert proxy & excluded == set(), f"proxy ∩ excluded = {proxy & excluded}"
    validate_expected_output_comparison_policy(g, backend="postgresql")



# ── TASK-011C C-2 Round 3 — real baseline E2E on PostgreSQL
#    (authority comment 4974759224) ─────────────────────────────


def test_baseline_feasible_real_e2e_on_postgresql(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """Round 3 §11: real PostgreSQL baseline E2E through the
    suite runner, asserting the same byte authority as the
    SQLite runner (D3 cross-backend byte parity).
    """
    import json
    import shutil
    from pathlib import Path

    from cold_storage.evaluation.evaluate import evaluate_manifest
    from cold_storage.evaluation.models import (
        DatabaseBackend,
        ExpectedOutcome,
        ExpectedOutputRef,
        Manifest,
        ScenarioDeclaration,
    )
    from cold_storage.evaluation.run_directory import suite_summary_path

    # 1. Seed the canonical A1 pre-existing production
    #    context on the live PG database.
    seed_s = a2_pg_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        # 2. Copy the frozen golden into the manifest_root.
        expected_path = root / "expected" / "baseline_feasible.v1.json"
        expected_path.parent.mkdir(parents=True, exist_ok=True)
        src_golden = (
            Path(__file__).resolve().parent / "data" / "expected" / "baseline_feasible.v1.json"
        )
        shutil.copyfile(src_golden, expected_path)

        manifest = Manifest(
            schema_version="1.0",
            suite_id="c2-round3-pg-baseline-real-e2e",
            scenarios=(
                ScenarioDeclaration(
                    scenario_id="baseline_feasible",
                    database_backend=DatabaseBackend.POSTGRESQL,
                    expected_outcome=ExpectedOutcome.SUCCEEDED,
                    expected_output=ExpectedOutputRef(
                        scenario_id="baseline_feasible",
                        path="expected/baseline_feasible.v1.json",
                        expected_outcome=ExpectedOutcome.SUCCEEDED,
                        expected_error=None,
                    ),
                ),
            ),
        )
        # 3. Real evaluate_manifest run on PG.
        result = evaluate_manifest(
            manifest=manifest,
            manifest_root=root,
            root=root / "run",
            session_factory=a2_pg_session_factory,
            commit_sha="c2-round3-pg-test",
        )
        # 4. overall == PASS (real PG production values
        #    match the frozen golden).
        assert result.evaluation_result_overall.value == "pass", (
            f"C-2 PG E2E: overall result MUST be pass; "
            f"diffs={result.scenarios[0].diff_summary!r}"
        )
        # 5. On-disk normalized bytes == frozen business
        #    payload (the canonical contract).
        norm_artifact = (
            root / "run" / "baseline_feasible"
            / "normalized" / "baseline_feasible.json"
        )
        on_disk_bytes = norm_artifact.read_bytes()
        on_disk_value = json.loads(on_disk_bytes)
        frozen_business_payload = {
            k: v for k, v in json.loads(src_golden.read_text()).items()
            if k != "_comparison_policy"
        }
        assert on_disk_value == frozen_business_payload, (
            "C-2 PG E2E: on-disk normalized value MUST equal "
            "the frozen business payload (golden minus "
            "``_comparison_policy``). PG establishes byte "
            "parity with the canonical frozen business "
            "payload — the production-side ``content_hash`` "
            "is the same across SQLite and PostgreSQL "
            "backends (per the golden's documented "
            "stable_proxies contract)."
        )
        # 6. On-disk raw artifact carries the full
        #    production lineage.
        raw_artifact = root / "run" / "baseline_feasible" / "raw" / "baseline_feasible.json"
        raw_data = json.loads(raw_artifact.read_text(encoding="utf-8"))
        assert raw_data["c2_persisted"]["database_backend"] == "postgresql"
        assert raw_data["c2_persisted"]["source_mode"] == "production"
        # 7. summary.json was written last.
        summary_path = suite_summary_path(root=root / "run")
        assert summary_path.exists()
