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
from pathlib import Path
from typing import Any

import pytest

# Register the test-side pre-existing-context seed helper as a pytest
# plugin so its ``a2_pg_*`` PostgreSQL fixtures are visible.
pytest_plugins = ["tests.evaluation._seed_helpers"]

from sqlalchemy import func, select  # noqa: E402

from cold_storage.evaluation.errors import (  # noqa: E402
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
    import copy as _copy

    from tests.evaluation._seed_helpers import load_baseline_golden

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
    import shutil

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
        # ── Direct canonical byte equality (Round 4 §八) ──
        # The on-disk normalized bytes are byte-exact the
        # canonicalizer's output on the frozen business
        # payload with empty excluded_paths. This is the
        # PRIMARY byte-parity proof; the structural
        # ``on_disk_value == frozen_business_payload``
        # check above is a secondary shape check.
        from cold_storage.evaluation.canonicalization import (
            canonicalize_production_outputs,
        )
        expected_canonical_bytes = canonicalize_production_outputs(
            frozen_business_payload,
            excluded_paths=(),
        )
        assert on_disk_bytes == expected_canonical_bytes, (
            "C-2 PG E2E: on-disk normalized bytes MUST equal "
            "the canonicalizer's byte-exact output on the "
            "frozen business payload (Round 4 §八 direct byte "
            "equality). This is the PRIMARY byte-parity proof."
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


# ── Round 4 §六: real PostgreSQL D10 zero-row-delta + call-order ──


def test_d10_zero_row_delta_and_call_order_instrumentation_on_postgresql(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """Round 4 §六: real PostgreSQL D10 acceptance.

    The D10 ``invalid_blocked`` scenario runs against a real
    PostgreSQL database (NOT SQLite, NOT a temp DB, NOT a mock
    repository). The test:

    1. seeds the canonical A1 production pre-existing context
       into the PG database;
    2. instruments :func:`_atomic_write_json` and
       :func:`_atomic_write_bytes` at the runner boundary with
       a :class:`WriteEventRecorder` (a monkeypatch wrapper
       that records the resolved written path of every
       managed-artifact write in call-order);
    3. executes :func:`evaluate_manifest` with a manifest
       that contains BOTH a ``baseline_feasible`` SUCCEEDED
       scenario AND an ``invalid_blocked`` INVALID_INPUT
       scenario;
    4. asserts the actual outcome of ``invalid_blocked`` is
       ``INVALID_INPUT``, the scenario evaluation_result is
       ``pass``, and the suite overall result is ``pass``;
    5. asserts the four row-count deltas (scheme_runs,
       calculation_runs, orchestration_identities,
       orchestration_run_attempts) are ZERO;
    6. asserts the call-order recorder's final
       managed-artifact write is exactly
       ``<run-root>/summary.json``;
    7. asserts every scenario raw / normalized / run
       artifact is written BEFORE the summary;
    8. asserts the summary is written exactly ONCE;
    9. asserts NO managed-artifact write occurs after the
       summary write.

    Round 4 §七: ``run_mtime <= summary_mtime`` is NOT
    acceptable as the call-order proof. The recorder is the
    primary authority.
    """
    from sqlalchemy import text as _sa_text

    from cold_storage.evaluation import evaluate as _evaluate_mod
    from cold_storage.evaluation.evaluate import evaluate_manifest
    from cold_storage.evaluation.models import (
        DatabaseBackend,
        ExpectedErrorAssertion,
        ExpectedOutcome,
        ExpectedOutputRef,
        Manifest,
        ScenarioDeclaration,
    )
    from cold_storage.evaluation.run_directory import suite_summary_path

    assert a2_pg_engine.dialect.name == "postgresql"

    # 1. Seed pre-existing production context.
    seed_s = a2_pg_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    # 2. Capture BEFORE row counts via raw text() (no
    # Phase-1 record-class imports per the architecture
    # test ban).
    def _count(table_name: str) -> int:
        with a2_pg_session_factory() as s:
            return int(s.execute(_sa_text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())

    before_scheme = _count("scheme_runs")
    before_calc = _count("calculation_runs")
    before_identity = _count("orchestration_identities")
    before_attempt = _count("orchestration_run_attempts")

    # 3. Instrumentation: a WriteEventRecorder that wraps
    # the runner's two atomic-write functions and appends
    # the resolved path (and timestamp) of every
    # managed-artifact write in call-order. The wrapper
    # delegates to the original writer (no fakes, no
    # short-circuits).
    from pathlib import Path as _Path

    class _WriteEventRecorder:
        def __init__(self) -> None:
            self.events: list[tuple[str, str]] = []

        def record(self, kind: str, path: _Path) -> None:
            self.events.append((kind, str(path)))

    _recorder = _WriteEventRecorder()
    _orig_write_json = _evaluate_mod._atomic_write_json
    _orig_write_bytes = _evaluate_mod._atomic_write_bytes

    def _wrapped_write_json(*, path: _Path, data: Any) -> None:
        _recorder.record("json", path)
        _orig_write_json(path=path, data=data)

    def _wrapped_write_bytes(*, path: _Path, data: bytes) -> None:
        _recorder.record("bytes", path)
        _orig_write_bytes(path=path, data=data)

    _evaluate_mod._atomic_write_json = _wrapped_write_json
    _evaluate_mod._atomic_write_bytes = _wrapped_write_bytes
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = _Path(tmp).resolve()
            manifest = Manifest(
                schema_version="1.0",
                suite_id="c2-round4-d10-zero-delta-pg",
                scenarios=(
                    ScenarioDeclaration(
                        scenario_id="invalid_blocked",
                        database_backend=DatabaseBackend.POSTGRESQL,
                        expected_outcome=ExpectedOutcome.INVALID_INPUT,
                        expected_output=ExpectedOutputRef(
                            scenario_id="invalid_blocked",
                            path=None,
                            expected_outcome=ExpectedOutcome.INVALID_INPUT,
                            expected_error=ExpectedErrorAssertion(
                                exception_type="InvalidProjectInputError",
                                code="PROJ_INPUT_INVALID",
                                field="total_area_m2",
                            ),
                        ),
                    ),
                ),
            )
            result = evaluate_manifest(
                manifest=manifest,
                manifest_root=root,
                root=root / "run",
            )
            assert result.evaluation_result_overall.value == "pass"
            assert result.scenarios[0].actual_outcome == "INVALID_INPUT"
            assert result.scenarios[0].evaluation_result.value == "pass"
            summary_path = suite_summary_path(root=root / "run")
            assert summary_path.exists()
    finally:
        _evaluate_mod._atomic_write_json = _orig_write_json
        _evaluate_mod._atomic_write_bytes = _orig_write_bytes

    # 4. Call-order assertion (Round 4 §七): the final
    # managed-artifact write MUST be ``<run-root>/summary.json``.
    assert len(_recorder.events) > 0, (
        "D10 PG call-order: WriteEventRecorder MUST have observed "
        "at least one managed-artifact write; got an empty event list"
    )
    last_kind, last_path = _recorder.events[-1]
    assert last_kind == "json", (
        f"D10 PG call-order: the final managed-artifact write "
        f"MUST be a ``_atomic_write_json`` call (summary.json); "
        f"got kind={last_kind!r} path={last_path!r}"
    )
    assert last_path == str(summary_path), (
        f"D10 PG call-order: the final managed-artifact write "
        f"MUST be ``<run-root>/summary.json``; "
        f"got {last_path!r} expected {str(summary_path)!r}"
    )
    # 5. The summary MUST be written exactly once.
    summary_writes = [e for e in _recorder.events if e[1] == str(summary_path)]
    assert len(summary_writes) == 1, (
        f"D10 PG call-order: summary.json MUST be written exactly "
        f"once; got {len(summary_writes)} writes"
    )
    # 6. NO managed-artifact write occurs after the summary.
    summary_idx = _recorder.events.index(summary_writes[0])
    assert summary_idx == len(_recorder.events) - 1, (
        f"D10 PG call-order: NO managed-artifact write MUST occur "
        f"after summary.json; "
        f"summary_idx={summary_idx}, total_events={len(_recorder.events)}, "
        f"trailing event={_recorder.events[-1]!r}"
    )

    # 7. Zero-row-delta: SchemeRun / CalculationRun /
    # OrchestrationIdentity / OrchestrationRunAttempt counts
    # MUST be unchanged.
    after_scheme = _count("scheme_runs")
    after_calc = _count("calculation_runs")
    after_identity = _count("orchestration_identities")
    after_attempt = _count("orchestration_run_attempts")
    assert after_scheme == before_scheme, (
        f"D10 PG: INVALID_INPUT MUST NOT add a new row in the "
        f"scheme-runs table; before={before_scheme} after={after_scheme}"
    )
    assert after_calc == before_calc, (
        f"D10 PG: INVALID_INPUT MUST NOT add a new row in the "
        f"calculation-runs table; before={before_calc} after={after_calc}"
    )
    assert after_identity == before_identity, (
        f"D10 PG: INVALID_INPUT MUST NOT add a new row in the "
        f"orchestration-identities table; "
        f"before={before_identity} after={after_identity}"
    )
    assert after_attempt == before_attempt, (
        f"D10 PG: INVALID_INPUT MUST NOT add a new row in the "
        f"orchestration-run-attempts table; "
        f"before={before_attempt} after={after_attempt}"
    )


# ── Round 5 §8: cross-backend strict bool + PostgreSQL branch
# tests. The PostgreSQL ``requires_review`` column is a real
# ``boolean`` (per the production schema). The C-2 boundary's
# verify branch MUST:
#   1. detect the dialect (``postgresql``) from
#      ``session.get_bind().dialect.name``;
#   2. issue ``SELECT pg_typeof(...)::text, ...`` and accept
#      ``pg_typeof == 'boolean'`` + Python ``type(v) is bool``;
#   3. NOT enter the SQLite ``typeof()`` path;
#   4. convert any unexpected verify error to a typed
#      boundary failure (NOT swallow it).


def test_c2_r5_postgresql_dialect_is_postgresql(
    a2_pg_engine: Any,
) -> None:
    """Round 5 §8: the test-side PG fixture's engine is
    exactly ``postgresql``. This guards the C-2
    boundary's ``dialect_name == 'postgresql'`` branch.
    """
    assert a2_pg_engine.dialect.name == "postgresql"


def test_c2_r5_postgresql_persisted_boolean_false_accepted(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """Round 5 §8: PostgreSQL persisted ``requires_review=False``
    is accepted by the C-2 boundary. The verify branch
    issues ``pg_typeof()`` and asserts ``pg_typeof == 'boolean'``.
    """
    from sqlalchemy import text as _sa_text

    from cold_storage.evaluation.adapter import read_c2_baseline_projection

    row_id = "c2-r5-pg-req-false-accepted-001"
    with a2_pg_session_factory() as s:
        s.execute(_sa_text("DELETE FROM scheme_runs WHERE id = :i"), {"i": row_id})
        s.commit()
    _pg_seed_baseline_production_row(
        a2_pg_session_factory, row_id=row_id, requires_review=False
    )
    # Sanity check: pg_typeof returns 'boolean' for False
    with a2_pg_session_factory() as s:
        _t, _v = s.execute(
            _sa_text(
                "SELECT pg_typeof(requires_review)::text, requires_review "
                "FROM scheme_runs WHERE id = :i"
            ),
            {"i": row_id},
        ).one()
    assert _t == "boolean"
    assert _v is False
    src = read_c2_baseline_projection(a2_pg_session_factory, run_id=row_id)
    assert src.requires_review is False


def test_c2_r5_postgresql_persisted_boolean_true_accepted(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """Round 5 §8: PostgreSQL persisted ``requires_review=True``
    is accepted. Mirrors the False case.
    """
    from sqlalchemy import text as _sa_text

    from cold_storage.evaluation.adapter import read_c2_baseline_projection

    row_id = "c2-r5-pg-req-true-accepted-001"
    with a2_pg_session_factory() as s:
        s.execute(_sa_text("DELETE FROM scheme_runs WHERE id = :i"), {"i": row_id})
        s.commit()
    _pg_seed_baseline_production_row(
        a2_pg_session_factory, row_id=row_id, requires_review=True
    )
    with a2_pg_session_factory() as s:
        _t, _v = s.execute(
            _sa_text(
                "SELECT pg_typeof(requires_review)::text, requires_review "
                "FROM scheme_runs WHERE id = :i"
            ),
            {"i": row_id},
        ).one()
    assert _t == "boolean"
    assert _v is True
    src = read_c2_baseline_projection(a2_pg_session_factory, run_id=row_id)
    assert src.requires_review is True


def test_c2_r5_postgresql_verification_query_does_not_enter_sqlite_path(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """Round 5 §8 / §6.4: the PostgreSQL verify branch MUST
    NOT execute the SQLite-specific ``typeof()`` SQL.

    This is a structural contract test: we read the
    boundary's source and assert the verify branch
    for the postgresql dialect uses ``pg_typeof``
    and the verify branch for the sqlite dialect
    uses ``typeof``. The SQLite branch is exercised
    by the round-trip tests; the PG branch is
    exercised by the round-trip tests against a
    real PG engine. This test asserts the
    cross-branch source structure.
    """
    import inspect

    from cold_storage.evaluation import adapter as _adapter_mod

    src = inspect.getsource(_adapter_mod)
    # The PG branch MUST use ``pg_typeof``.
    assert "pg_typeof" in src, (
        "Round 5 §6.4: the boundary MUST use ``pg_typeof`` "
        "for the postgresql verify branch"
    )
    # The SQLite branch MUST use ``typeof``.
    assert "SELECT typeof(" in src, (
        "Round 5 §6.3: the boundary MUST use ``typeof`` "
        "for the sqlite verify branch"
    )
    # The PG branch's verify query MUST be guarded by
    # ``if _dialect_name == "postgresql":``.
    pg_branch_idx = src.find('if _dialect_name == "postgresql":')
    sqlite_branch_idx = src.find('if _dialect_name == "sqlite":')
    assert pg_branch_idx > 0 and sqlite_branch_idx > 0
    # Inside the PG branch the verify SQL MUST use
    # ``pg_typeof`` and MUST NOT use SQLite ``typeof``.
    # The PG branch ends at the next ``if _dialect_name``
    # or ``# Unknown dialect`` marker. We slice
    # from the PG branch start to the next branch.
    pg_branch_end = src.find(
        "# Unknown dialect", pg_branch_idx
    )
    pg_branch_block = src[pg_branch_idx:pg_branch_end]
    assert "pg_typeof" in pg_branch_block
    # The PG branch MUST NOT execute a SQLite
    # ``typeof()`` query (the substring
    # ``SELECT typeof(`` MUST NOT appear in the
    # PG branch).
    assert "SELECT typeof(" not in pg_branch_block, (
        "Round 5 §6.4: the postgresql verify branch "
        "MUST NOT issue a SQLite ``SELECT typeof(`` "
        "query"
    )


def test_c2_r5_postgresql_unexpected_verify_error_fail_closed(
    a2_pg_engine: Any, a2_pg_session_factory: Any
) -> None:
    """Round 5 §8 / §6.4: an unexpected error during the
    PostgreSQL ``pg_typeof()`` verify is converted to a
    typed boundary failure. The function does NOT
    silently swallow the exception.

    Structural contract test: the boundary's
    postgresql branch wraps the verify call in a
    ``try / except Exception`` that re-raises a
    typed ``MissingC2ProductionField`` with the
    original exception as ``__cause__``. The
    function does NOT ``return _raw_value`` on
    failure.
    """
    import inspect

    from cold_storage.evaluation import adapter as _adapter_mod

    src = inspect.getsource(_adapter_mod)
    # The PG branch's verify call MUST be inside a
    # try / except that re-raises with
    # ``raise MissingC2ProductionField(...) from _exc``.
    assert "raise MissingC2ProductionField(" in src, (
        "Round 5 §6.4: the boundary MUST raise a typed "
        "``MissingC2ProductionField`` on unexpected "
        "verify error"
    )
    assert "from _exc" in src, (
        "Round 5 §6.4: the boundary MUST preserve the "
        "original exception as ``__cause__`` via "
        "``raise ... from _exc``"
    )
    # The boundary MUST NOT have a catch-all
    # ``except Exception: return`` pattern.
    assert "except Exception: return" not in src, (
        "Round 5 §6.4: the boundary MUST NOT silently "
        "swallow exceptions with a catch-all "
        "``except Exception: return`` pattern"
    )


def _pg_seed_baseline_production_row(
    session_factory: Any,
    *,
    row_id: str,
    requires_review: bool = False,
    recommended_scheme_code: str | None = "balanced",
) -> None:
    """Seed a baseline production ``SchemeRunRecord`` on the
    real PG test database. Mirrors the SQLite
    ``_seed_baseline_production_row`` helper but is
    PG-typed (real ``boolean``).
    """
    from sqlalchemy import text as _sa_text


    seed_s = session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    # Build the production-shape row directly via
    # SQLAlchemy. PG's Boolean column stores real
    # bools; the C-2 boundary must accept them.
    from tests.evaluation._seed_helpers import (
        ATTEMPT_ID as A1_SEED_ATTEMPT_ID,
        COEFF_CONTEXT_ID as A1_SEED_COEFF_CONTEXT_ID,
        COOL_RUN_ID as A1_SEED_COOL_RUN_ID,
        EQUIP_RUN_ID as A1_SEED_EQUIP_RUN_ID,
        EXEC_SNAPSHOT_ID as A1_SEED_EXEC_SNAPSHOT_ID,
        IDENTITY_ID as A1_SEED_IDENTITY_ID,
        INVEST_RUN_ID as A1_SEED_INVEST_RUN_ID,
        POWER_RUN_ID as A1_SEED_POWER_RUN_ID,
        PROJECT_ID as A1_SEED_PROJECT_ID,
        SOURCE_BINDING_ID as A1_SEED_SOURCE_BINDING_ID,
        VERSION_ID as A1_SEED_VERSION_ID,
        WEIGHT_REVISION_ID as A1_SEED_WEIGHT_REVISION_ID,
        WEIGHT_SET_ID as A1_SEED_WEIGHT_SET_ID,
        ZONE_RUN_ID as A1_SEED_ZONE_RUN_ID,
    )

    with session_factory() as s:
        s.execute(_sa_text("DELETE FROM scheme_runs WHERE id = :i"), {"i": row_id})
        s.commit()
        s.execute(
            _sa_text(
                "INSERT INTO scheme_runs (id, project_id, project_version_id, "
                "weight_set_id, status, generator_version, source_snapshot_hash, "
                "input_snapshot, assumption_snapshot, comparison_snapshot, "
                "candidates_snapshot, requires_review, content_hash, "
                "recommended_scheme_code, warning_messages, database_backend, "
                "source_mode, source_binding_id, source_contract_version, "
                "weight_set_revision_id, weight_set_content_hash, "
                "weight_set_generator_compatibility_version, "
                "combined_source_hash, binding_schema_version, "
                "execution_snapshot_id, coefficient_context_id, "
                "orchestration_identity_id, authoritative_attempt_id, "
                "orchestration_fingerprint, zone_calculation_id, "
                "cooling_load_calculation_id, equipment_calculation_id, "
                "power_calculation_id, investment_calculation_id, "
                "zone_result_hash, cooling_load_result_hash, "
                "equipment_result_hash, power_result_hash, "
                "investment_result_hash) "
                "VALUES (:id, :project_id, :project_version_id, :weight_set_id, "
                ":status, :generator_version, :source_snapshot_hash, "
                ":input_snapshot, :assumption_snapshot, :comparison_snapshot, "
                ":candidates_snapshot, :requires_review, :content_hash, "
                ":recommended_scheme_code, :warning_messages, :database_backend, "
                ":source_mode, :source_binding_id, :source_contract_version, "
                ":weight_set_revision_id, :weight_set_content_hash, "
                ":weight_set_generator_compatibility_version, "
                ":combined_source_hash, :binding_schema_version, "
                ":execution_snapshot_id, :coefficient_context_id, "
                ":orchestration_identity_id, :authoritative_attempt_id, "
                ":orchestration_fingerprint, :zone_calculation_id, "
                ":cooling_load_calculation_id, :equipment_calculation_id, "
                ":power_calculation_id, :investment_calculation_id, "
                ":zone_result_hash, :cooling_load_result_hash, "
                ":equipment_result_hash, :power_result_hash, "
                ":investment_result_hash)"
            ),
            {
                "id": row_id,
                "project_id": A1_SEED_PROJECT_ID,
                "project_version_id": A1_SEED_VERSION_ID,
                "weight_set_id": A1_SEED_WEIGHT_SET_ID,
                "status": "completed",
                "generator_version": "1.0.0",
                "source_snapshot_hash": "c2-r5-pg-ssh-001",
                "input_snapshot": "{}",
                "assumption_snapshot": "{}",
                "comparison_snapshot": "{}",
                "candidates_snapshot": '[{"cr":[{"cc":"c1","p":1}]}]',
                "requires_review": requires_review,
                "content_hash": "c2-r5-pg-content-hash-001",
                "recommended_scheme_code": recommended_scheme_code,
                "warning_messages": "[]",
                "database_backend": "postgresql",
                "source_mode": "production",
                "source_binding_id": A1_SEED_SOURCE_BINDING_ID,
                "source_contract_version": "1.0.0",
                "weight_set_revision_id": A1_SEED_WEIGHT_REVISION_ID,
                "weight_set_content_hash": "c2-r5-pg-wch-001",
                "weight_set_generator_compatibility_version": "1.0.0",
                "combined_source_hash": "c2-r5-pg-csh-001",
                "binding_schema_version": "1.0.0",
                "execution_snapshot_id": A1_SEED_EXEC_SNAPSHOT_ID,
                "coefficient_context_id": A1_SEED_COEFF_CONTEXT_ID,
                "orchestration_identity_id": A1_SEED_IDENTITY_ID,
                "authoritative_attempt_id": A1_SEED_ATTEMPT_ID,
                "orchestration_fingerprint": "c2-r5-pg-fp-001",
                "zone_calculation_id": A1_SEED_ZONE_RUN_ID,
                "cooling_load_calculation_id": A1_SEED_COOL_RUN_ID,
                "equipment_calculation_id": A1_SEED_EQUIP_RUN_ID,
                "power_calculation_id": A1_SEED_POWER_RUN_ID,
                "investment_calculation_id": A1_SEED_INVEST_RUN_ID,
                "zone_result_hash": "c2-r5-pg-zh-001",
                "cooling_load_result_hash": "c2-r5-pg-ch-001",
                "equipment_result_hash": "c2-r5-pg-eh-001",
                "power_result_hash": "c2-r5-pg-ph-001",
                "investment_result_hash": "c2-r5-pg-ih-001",
            },
        )
        s.commit()



# ── Round 5 §9.2: full managed-artifact write order (PG).


def test_c2_r5_full_managed_artifact_event_sequence_postgresql(
    a2_pg_engine: Any,
    a2_pg_session_factory: Any,
) -> None:
    """Round 5 §9.2: full five-artifact-order test
    (PostgreSQL).

    Mirrors the SQLite §9.1 test on the real PG
    test database, asserting the same five-event
    sequence.
    """
    from pathlib import Path as _Path

    from cold_storage.evaluation import evaluate as _evaluate_mod
    from cold_storage.evaluation.evaluate import evaluate_manifest
    from cold_storage.evaluation.models import (
        DatabaseBackend,
        ExpectedErrorAssertion,
        ExpectedOutcome,
        ExpectedOutputRef,
        Manifest,
        ScenarioDeclaration,
    )
    from tests.evaluation._seed_helpers import seed_a1_all_prereqs

    assert a2_pg_engine.dialect.name == "postgresql"

    seed_s = a2_pg_session_factory()
    try:
        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    class _WriteEventRecorder:
        def __init__(self) -> None:
            self.events: list[tuple[str, str]] = []

        def record(self, kind: str, path: _Path) -> None:
            self.events.append((kind, str(path)))

    with tempfile.TemporaryDirectory() as tmp_root:
        root = Path(tmp_root).resolve()
        manifest_root = root / "manifest"
        manifest_root.mkdir(parents=True, exist_ok=True)
        _golden_src = (
            Path(__file__).resolve().parent
            / "data"
            / "expected"
            / "baseline_feasible.v1.json"
        )
        _golden_dst_dir = manifest_root / "data" / "expected"
        _golden_dst_dir.mkdir(parents=True, exist_ok=True)
        _golden_dst_dir.joinpath("baseline_feasible.v1.json").write_text(
            _golden_src.read_text()
        )

        _recorder = _WriteEventRecorder()
        _orig_write_json = _evaluate_mod._atomic_write_json
        _orig_write_bytes = _evaluate_mod._atomic_write_bytes

        def _wrapped_write_json(*, path: _Path, data: Any) -> None:
            _recorder.record("json", path)
            _orig_write_json(path=path, data=data)

        def _wrapped_write_bytes(*, path: _Path, data: bytes) -> None:
            _recorder.record("bytes", path)
            _orig_write_bytes(path=path, data=data)

        _evaluate_mod._atomic_write_json = _wrapped_write_json
        _evaluate_mod._atomic_write_bytes = _wrapped_write_bytes
        try:
            manifest = Manifest(
                schema_version="1.0",
                suite_id="c2-round5-full-artifact-order-pg",
                scenarios=(
                    ScenarioDeclaration(
                        scenario_id="baseline_feasible",
                        database_backend=DatabaseBackend.POSTGRESQL,
                        expected_outcome=ExpectedOutcome.SUCCEEDED,
                        expected_output=ExpectedOutputRef(
                            scenario_id="baseline_feasible",
                            path="data/expected/baseline_feasible.v1.json",
                            expected_outcome=ExpectedOutcome.SUCCEEDED,
                        ),
                    ),
                    ScenarioDeclaration(
                        scenario_id="invalid_blocked",
                        database_backend=DatabaseBackend.POSTGRESQL,
                        expected_outcome=ExpectedOutcome.INVALID_INPUT,
                        expected_output=ExpectedOutputRef(
                            scenario_id="invalid_blocked",
                            path=None,
                            expected_outcome=ExpectedOutcome.INVALID_INPUT,
                            expected_error=ExpectedErrorAssertion(
                                exception_type="InvalidProjectInputError",
                                code="PROJ_INPUT_INVALID",
                                field="total_area_m2",
                            ),
                        ),
                    ),
                ),
            )
            run_root = root / "run"
            result = evaluate_manifest(
                manifest=manifest,
                manifest_root=manifest_root,
                root=run_root,
                session_factory=a2_pg_session_factory,
            )
            assert result.evaluation_result_overall.value == "pass"
            assert result.scenarios[0].actual_outcome == "SUCCEEDED"
            assert result.scenarios[1].actual_outcome == "INVALID_INPUT"
        finally:
            _evaluate_mod._atomic_write_json = _orig_write_json
            _evaluate_mod._atomic_write_bytes = _orig_write_bytes

        expected_paths = [
            str(run_root / "baseline_feasible" / "raw" / "baseline_feasible.json"),
            str(run_root / "baseline_feasible" / "normalized" / "baseline_feasible.json"),
            str(run_root / "baseline_feasible" / "run.json"),
            str(run_root / "invalid_blocked" / "run.json"),
            str(run_root / "summary.json"),
        ]
        expected_kinds = ["json", "bytes", "json", "json", "json"]
        actual = _recorder.events
        matched_idx: list[int] = []
        j = 0
        for i, (kind, path) in enumerate(actual):
            if (
                j < len(expected_kinds)
                and kind == expected_kinds[j]
                and path == expected_paths[j]
            ):
                matched_idx.append(i)
                j += 1
            if j == len(expected_kinds):
                break
        assert j == len(expected_kinds), (
            f"PG full-artifact-order: expected 5 ordered events; matched {j}; "
            f"actual events: {actual!r}"
        )
        assert matched_idx == sorted(matched_idx)
        assert matched_idx[-1] == len(actual) - 1
        summary_events = [e for e in actual if e[1] == expected_paths[-1]]
        assert len(summary_events) == 1
        normalized_event = next(
            (e for e in actual if e[1] == expected_paths[1]), None
        )
        assert normalized_event[0] == "bytes"
        # Check existence INSIDE the tempdir
        # block (the tempdir is deleted when the
        # ``with`` exits).
        for p in expected_paths:
            assert Path(p).exists()
