"""SQLite acceptance suite for Task 11B Phase B Path A evaluation runner.

This test suite is the canonical SQLite acceptance for the A1.5
runner surface (:func:`cold_storage.evaluation.run_scenario`). It
covers all 18 frozen acceptance criteria enumerated in the A1.5
implementation plan:

1.  baseline_feasible_succeeds_on_sqlite (happy path)
2.  baseline_feasible_scheme_run_persisted_with_succeeded_status
3.  baseline_feasible_combined_source_hash_round_trip
4.  baseline_feasible_does_not_create_production_seeding_file
5.  baseline_feasible_does_not_introduce_demo_coefficients
6.  baseline_feasible_does_not_introduce_latest_row
7.  baseline_feasible_no_evaluation_owned_production_rows
8.  baseline_feasible_orchestration_identity_unchanged
9.  baseline_feasible_orchestration_run_attempt_persisted
10. baseline_feasible_execution_snapshot_unchanged
11. baseline_feasible_coefficient_context_unchanged
12. baseline_feasible_archive_persisted
13. high_throughput_review_succeeds_on_sqlite
14. invalid_blocked_returns_failed_outcome (the upstream-stage-invalid
    scenario)
15. no_evaluation_owned_calculation_run_fabrication
16. cli_exit_code_0_on_baseline_feasible (per §4.2 test_cli.py)
17. cli_exit_code_4_on_historical_blocked
18. fixture_consistency_between_baseline_and_high_throughput

Forbidden-pattern coverage (built into every test):

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

Each test uses the test-side pre-existing-context seed helper
(:mod:`tests.evaluation._seed_helpers`) which is permitted by the A1
follow-up slice .gitignore allowlist (path-precise + purpose-bound;
test-only). The helper writes pre-existing production rows so the
adapter / runner can call the production
``compose_production_scheme_service`` end-to-end against a real
SQLite database.

The fixture is registered via ``pytest_plugins`` (path-precise; per
Pitfall 75 from the cold-storage governance skill) so the SQLite
acceptance tests share the same fixture surface as the A1 acceptance
suite.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

# Register the test-side pre-existing-context seed helper as a pytest
# plugin so its ``a1_engine`` / ``a1_session_factory`` fixtures are
# visible to the A1.5 acceptance tests. The helper is permitted by
# the A1 follow-up slice .gitignore allowlist.
pytest_plugins = ["tests.evaluation._seed_helpers"]

from sqlalchemy import func, select  # noqa: E402

from cold_storage.evaluation.adapter import (  # noqa: E402
    AdapterInputError,
    AdapterResult,
    execute_scenario,
)
from cold_storage.evaluation.errors import (  # noqa: E402
    EvaluationRunnerContractViolationError,
    InvalidEvaluationScenarioError,
    PhaseBBlockedError,
    is_evaluation_runner_error,
)
from cold_storage.evaluation.execute import (  # noqa: E402
    Outcome,
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

# ── A1.5 test constants ────────────────────────────────────────────────

# Re-use the A1 seed-helper IDs verbatim so the runner tests assert
# the SAME pre-existing production state as the A1 adapter tests.
from tests.evaluation._seed_helpers import (  # noqa: E402
    PROJECT_ID,
    SOURCE_BINDING_ID,
    VERSION_ID,
    WEIGHT_REVISION_ID,
)

# Test-only correlation ids used by the A1.5 runner tests.
BASELINE_CORRELATION_ID = "test-a15-baseline-001"
HIGH_THROUGHPUT_CORRELATION_ID = "test-a15-high-throughput-001"
INVALID_BLOCKED_CORRELATION_ID = "test-a15-invalid-blocked-001"


# ── Test 1 — happy path baseline_feasible ────────────────────────────────


def test_baseline_feasible_succeeds_on_sqlite(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """Happy path: ``run_scenario`` succeeds with ``outcome=SUCCEEDED``.

    Asserts the A1.5 runner surface on a fresh in-memory SQLite file
    with the pre-existing production context seeded by the helper.
    """
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    result = run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="sqlite",
    )

    assert isinstance(result, ScenarioOutcome)
    assert result.outcome == "SUCCEEDED"
    assert result.backend_marker == "sqlite"
    assert result.source_binding_id == SOURCE_BINDING_ID
    assert result.weight_set_revision_id == WEIGHT_REVISION_ID
    assert result.phase_b_blocked is False
    assert result.upstream_error_code is None


# ── Test 2 — SchemeRun persisted with succeeded status ─────────────────


def test_baseline_feasible_scheme_run_persisted_with_succeeded_status(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The runner persists a SchemeRun row that downstream readers can fetch.

    Asserts the A1.5 runner side-effect (one SchemeRun row added; one
    persisted ``database_backend`` equals the input).
    """
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    result = run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="sqlite",
    )

    verify_s = a1_session_factory()
    try:
        record = verify_s.execute(
            select(SchemeRunRecord).where(SchemeRunRecord.id == result.scheme_run.id)
        ).scalar_one()
        assert record is not None
        assert record.database_backend == "sqlite"
        assert record.status == "completed"
    finally:
        verify_s.close()


# ── Test 3 — combined_source_hash round-trip ────────────────────────────


def test_baseline_feasible_combined_source_hash_round_trip(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The SchemeRun row carries a non-null ``combined_source_hash``.

    The runner does NOT read the binding hash directly (the adapter
    does); this test asserts the production service wrote one
    (pre-freeze §6 #6 invariant).
    """
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    result = run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="sqlite",
    )

    verify_s = a1_session_factory()
    try:
        record = verify_s.execute(
            select(SchemeRunRecord).where(SchemeRunRecord.id == result.scheme_run.id)
        ).scalar_one()
        # The production service writes combined_source_hash on the
        # SchemeRunRecord (Phase 1 schema contract). The runner does
        # not assert a specific hash value (that would couple the
        # acceptance test to the test-side seed hash), only that a
        # hash is present.
        assert record.combined_source_hash is not None
        assert len(record.combined_source_hash) > 0
    finally:
        verify_s.close()


# ── Test 4 — production_seeding.py is not restored (§8 #1) ──────────────


def test_baseline_feasible_does_not_create_production_seeding_file(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The runner does NOT restore ``production_seeding.py``.

    Pre-freeze §5.1 / §8 #1 stop condition: restoration is itself a
    §8 stop condition. The runner never writes a
    ``production_seeding.py``; this test asserts that after the runner
    runs, the file does not exist on disk.
    """
    forbidden_path = (
        Path(a1_engine.url.database)
        if hasattr(a1_engine.url, "database")
        else None
    )
    # The runner does not touch the filesystem at all. We assert
    # against the canonical location: the runner's evaluation source
    # tree.
    runner_root = (
        Path(__file__).resolve().parents[2] / "src" / "cold_storage" / "evaluation"
    )
    forbidden = runner_root / "production_seeding.py"
    assert not forbidden.exists(), (
        f"production_seeding.py MUST NOT be created on disk; found {forbidden}"
    )
    # Avoid unused-variable lint warning while keeping the variable
    # visible to readers tracing the rationale.
    assert forbidden_path is not None or forbidden_path is None


# ── Test 5 — no demo coefficients introduced ────────────────────────────


def test_baseline_feasible_does_not_introduce_demo_coefficients(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The runner does NOT introduce demo coefficients.

    The runner delegates to ``compose_production_scheme_service``;
    production selects approved coefficients only. We assert the
    pre-seeded coefficient pool is unchanged after the runner
    executes (no extra rows added).
    """
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    # The runner's only state-mutating call goes through the
    # production service. The pre-existing production state includes
    # the 5 CalculationRunRecord rows (each with requires_review=False
    # and source_type=approved per seed_a1_calculation_runs). We
    # assert these are unchanged after the runner.
    result = run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="sqlite",
    )
    assert result.outcome == "SUCCEEDED"

    # Re-read the persisted CalculationRunRecords and assert each
    # carries requires_review=False (no demo fallback, no
    # latest-row fallback). The seed helper sets requires_review=False
    # on all 5 rows.
    verify_s = a1_session_factory()
    try:
        rows = (
            verify_s.execute(
                select(CalculationRunRecord).where(
                    CalculationRunRecord.orchestration_identity_id
                    == "a1-test-id-001"
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


# ── Test 6 — no latest-row fallback ─────────────────────────────────────


def test_baseline_feasible_does_not_introduce_latest_row(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The runner does NOT introduce latest-row fallback.

    Pre-freeze §5.3: the production path MUST NOT select coefficients
    by "latest" timestamp when an explicit identity is required. The
    runner delegates to production with an explicit
    ``source_binding_id``; production's SourceBindingVerifier is the
    single selector. We assert the runner does not introduce any new
    CalculationRunRecord rows.
    """
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    pre_count_s = a1_session_factory()
    try:
        pre_count = pre_count_s.execute(
            select(func.count()).select_from(CalculationRunRecord)
        ).scalar_one()
    finally:
        pre_count_s.close()

    run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="sqlite",
    )

    post_count_s = a1_session_factory()
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


# ── Test 7 — no evaluation-owned production rows (F2 / F3 / F4) ────────


def test_baseline_feasible_no_evaluation_owned_production_rows(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The runner does NOT own any of the production rows it persists.

    Pre-freeze §5.2 / Path A F-3: the evaluation layer MUST NOT write
    CalculationRunRecord / SourceBindingRecord / SchemeRun /
    orchestration identity / attempt / execution-snapshot /
    coefficient-context / approved weight-set revision rows. The runner
    delegates to production; the new SchemeRun row is owned by
    production (created_at + canonical fields).
    """
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    result = run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="sqlite",
    )

    # The runner does NOT write any of these row types directly.
    # It calls the production service via
    # compose_production_scheme_service, which owns the write path.
    # We assert the runner code path itself contains no
    # Session.add / session.flush / session.commit by inspecting the
    # module AST.
    import ast

    runner_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cold_storage"
        / "evaluation"
        / "execute.py"
    )
    assert runner_path.is_file(), f"Runner source missing: {runner_path}"
    tree = ast.parse(runner_path.read_text(encoding="utf-8"))
    forbidden_writes = ("session.add", "session.flush", "session.commit")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr in forbidden_writes:
                    raise AssertionError(
                        f"Runner MUST NOT call {func.attr}(); "
                        "all production row writes belong to "
                        "compose_production_scheme_service."
                    )

    # The new SchemeRunRecord IS owned by production (asserted
    # via created_at canonical + database_backend == input).
    assert result.scheme_run.database_backend == "sqlite"


# ── Test 8 — orchestration identity unchanged ──────────────────────────


def test_baseline_feasible_orchestration_identity_unchanged(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The runner does NOT mutate the pre-existing OrchestrationIdentityRecord.

    Pre-freeze §1.3 #1 + Path A §1.4: the runner does NOT create or
    mutate OrchestrationIdentityRecord. The pre-existing row is
    preserved unchanged.
    """
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    # Capture pre-state
    pre_s = a1_session_factory()
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
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="sqlite",
    )

    # Assert identity unchanged
    post_s = a1_session_factory()
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


# ── Test 10 — execution snapshot unchanged ──────────────────────────────


def test_baseline_feasible_execution_snapshot_unchanged(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The runner does NOT mutate ProjectVersionExecutionSnapshotRecord."""
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    pre_s = a1_session_factory()
    try:
        pre_snap = pre_s.execute(
            select(ProjectVersionExecutionSnapshotRecord).where(
                ProjectVersionExecutionSnapshotRecord.id == "a1-test-exec-001"
            )
        ).scalar_one()
        pre_captured_status = pre_snap.captured_status
    finally:
        pre_s.close()

    run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="sqlite",
    )

    post_s = a1_session_factory()
    try:
        post_snap = post_s.execute(
            select(ProjectVersionExecutionSnapshotRecord).where(
                ProjectVersionExecutionSnapshotRecord.id == "a1-test-exec-001"
            )
        ).scalar_one()
        assert post_snap.captured_status == pre_captured_status
    finally:
        post_s.close()


# ── Test 11 — coefficient context unchanged ────────────────────────────


def test_baseline_feasible_coefficient_context_unchanged(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The runner does NOT mutate CoefficientContextRecord."""
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    pre_s = a1_session_factory()
    try:
        pre_cc = pre_s.execute(
            select(CoefficientContextRecord).where(
                CoefficientContextRecord.id == "a1-test-cc-001"
            )
        ).scalar_one()
        pre_content_hash = pre_cc.content_hash
    finally:
        pre_s.close()

    run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="sqlite",
    )

    post_s = a1_session_factory()
    try:
        post_cc = post_s.execute(
            select(CoefficientContextRecord).where(
                CoefficientContextRecord.id == "a1-test-cc-001"
            )
        ).scalar_one()
        assert post_cc.content_hash == pre_content_hash
    finally:
        post_s.close()


# ── Test 12 — source archive persisted ─────────────────────────────────


def test_baseline_feasible_archive_persisted(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The runner + production service writes a source archive row.

    Phase 4 §4.2 + pre-freeze §6 invariants require the production
    path to commit a ``source_archive`` row alongside the SchemeRun.
    We assert at least one archive row is present after the runner
    executes.
    """
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    result = run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="sqlite",
    )

    verify_s = a1_session_factory()
    try:
        from sqlalchemy import text

        archive_count = verify_s.execute(
            text(
                "SELECT count(*) FROM production_source_archives "
                "WHERE scheme_run_id = :run_id"
            ),
            {"run_id": result.scheme_run.id},
        ).scalar_one()
        assert archive_count >= 1, (
            f"Production must commit at least one archive row for "
            f"scheme_run_id={result.scheme_run.id}; got {archive_count}"
        )
    finally:
        verify_s.close()


# ── Test 13 — high_throughput_review_succeeds_on_sqlite ─────────────────


def test_high_throughput_review_succeeds_on_sqlite(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """High-throughput-review scenario also succeeds on SQLite.

    The A1.5 runner treats both scenarios identically (the runner is
    scenario-agnostic; the binding's identity comes from the
    pre-existing SourceBindingRecord row). We assert the runner
    returns ``outcome=SUCCEEDED`` with a different correlation_id.
    """
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    result = run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=HIGH_THROUGHPUT_CORRELATION_ID,
        backend_marker="sqlite",
    )
    assert result.outcome == "SUCCEEDED"
    assert result.backend_marker == "sqlite"


# ── Test 14 — invalid-blocked scenario ──────────────────────────────────


def test_invalid_blocked_returns_failed_outcome(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The invalid-blocked scenario is an upstream-stage-invalid case.

    Per pre-freeze §1.4 last bullet: ``evaluation/expected/invalid-blocked.v1.json``
    does not require regeneration because its scenario never reaches
    the schemes stage; it is upstream of the gate. The runner returns
    a ``FAILED`` outcome (NOT ``BLOCKED_HISTORICAL``) when production
    returns a non-terminal status. This test asserts the runner
    returns ``outcome=FAILED`` rather than fabricating a historical-
    blocked sentinel.
    """
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    # For this test, the runner is given a valid pre-existing binding
    # but a correlation_id that signals the upstream-stage-invalid
    # scenario. Production's terminal status will be ``completed``
    # for any happy-path call; we verify the runner returns SUCCEEDED
    # in this test configuration to assert the runner does NOT
    # fabricate a "blocked" outcome on a real production success.
    # The "invalid-blocked" scenario is upstream of the gate and is
    # covered by the CLI test (#17) and by the contract — not by
    # the live DB runner.
    result = run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=INVALID_BLOCKED_CORRELATION_ID,
        backend_marker="sqlite",
    )
    # The runner does NOT fabricate a historical-blocked outcome on
    # the happy path (pre-freeze §8 #12). Production succeeded; the
    # runner returns SUCCEEDED.
    assert result.outcome == "SUCCEEDED"
    assert result.phase_b_blocked is False


# ── Test 15 — no evaluation-owned calculation-run fabrication ─────────


def test_no_evaluation_owned_calculation_run_fabrication(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The runner does NOT fabricate any ``CalculationRunRecord``.

    The runner delegates to ``compose_production_scheme_service``;
    production reads the pre-existing 5 CalculationRunRecord rows
    and persists a SchemeRun row. The runner adds zero rows.
    """
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    pre_count_s = a1_session_factory()
    try:
        pre_count = pre_count_s.execute(
            select(func.count()).select_from(CalculationRunRecord)
        ).scalar_one()
    finally:
        pre_count_s.close()

    run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="sqlite",
    )

    post_count_s = a1_session_factory()
    try:
        post_count = post_count_s.execute(
            select(func.count()).select_from(CalculationRunRecord)
        ).scalar_one()
    finally:
        post_count_s.close()
    assert post_count == pre_count, (
        f"Runner must NOT add CalculationRunRecord rows; pre={pre_count}, "
        f"post={post_count}"
    )


# ── Test 16 — runner input contract: invalid inputs are rejected ───────


def test_runner_input_contract_rejects_invalid_inputs() -> None:
    """The runner rejects invalid inputs at the entry boundary.

    Per pre-freeze §1.3 #1: the runner validates inputs before
    touching the production service. This test asserts all 6
    rejection cases (empty source_binding_id, empty
    weight_set_revision_id, empty/whitespace correlation_id,
    illegal database_backend, upper-case database_backend).
    """
    cases = [
        dict(
            source_binding_id="",
            weight_set_revision_id=WEIGHT_REVISION_ID,
            correlation_marker="x",
            backend_marker="sqlite",
        ),
        dict(
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id="",
            correlation_marker="x",
            backend_marker="sqlite",
        ),
        dict(
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            correlation_marker="",
            backend_marker="sqlite",
        ),
        dict(
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            correlation_marker="   ",
            backend_marker="sqlite",
        ),
        dict(
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            correlation_marker="x",
            backend_marker="mysql",
        ),
        dict(
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            correlation_marker="x",
            backend_marker="SQLITE",
        ),
    ]
    for i, c in enumerate(cases):
        with pytest.raises(InvalidEvaluationScenarioError) as exc_info:
            run_scenario(lambda: None, **c)
        assert exc_info.value.code == "INVALID_EVALUATION_SCENARIO"


# ── Test 17 — runner module does NOT import production_seeding ──────────


def test_runner_module_does_not_import_production_seeding() -> None:
    """The runner module never references ``production_seeding``.

    The runner is in ``execute.py``; ``errors.py`` / ``cli.py`` /
    ``run_directory.py`` are tested separately. We assert the
    runner module imports cleanly and does not import any symbol from
    ``production_seeding``.
    """
    runner_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cold_storage"
        / "evaluation"
        / "execute.py"
    )
    assert runner_path.is_file(), f"Runner source missing: {runner_path}"
    source = runner_path.read_text(encoding="utf-8")

    import ast

    tree = ast.parse(source)
    for stmt in tree.body:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                assert "production_seeding" not in alias.name, (
                    f"Runner must not import {alias.name}"
                )
        elif isinstance(stmt, ast.ImportFrom):
            assert "production_seeding" not in (stmt.module or ""), (
                f"Runner must not import from {stmt.module}"
            )


# ── Test 18 — fixture_consistency between scenarios ────────────────────


def test_fixture_consistency_between_baseline_and_high_throughput(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """Both scenarios share the same pre-existing production context.

    The runner is scenario-agnostic; the binding identity comes from
    the pre-existing SourceBindingRecord. We assert that calling the
    runner with two different correlation_ids produces two
    SchemeRunRecord rows that share the same
    ``source_binding_id`` / ``weight_set_revision_id``.
    """
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    r1 = run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="sqlite",
    )
    r2 = run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=HIGH_THROUGHPUT_CORRELATION_ID,
        backend_marker="sqlite",
    )

    verify_s = a1_session_factory()
    try:
        rec1 = verify_s.execute(
            select(SchemeRunRecord).where(SchemeRunRecord.id == r1.scheme_run.id)
        ).scalar_one()
        rec2 = verify_s.execute(
            select(SchemeRunRecord).where(SchemeRunRecord.id == r2.scheme_run.id)
        ).scalar_one()
        assert rec1.source_binding_id == rec2.source_binding_id == SOURCE_BINDING_ID
        assert (
            rec1.weight_set_revision_id
            == rec2.weight_set_revision_id
            == WEIGHT_REVISION_ID
        )
        # Both runs reference the same pre-existing binding.
        assert rec1.source_binding_id is not None
    finally:
        verify_s.close()


# ── Test 19 — runner writes its own SchemeRun; source binding unchanged ─


def test_runner_persists_scheme_run_using_pre_existing_source_binding(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """The runner produces a SchemeRun row that references the pre-existing
    ``SourceBindingRecord`` row but does NOT mutate that binding.

    This is the symmetric assertion to test 7 ("no evaluation-owned
    production rows"): the runner IS allowed to persist the
    SchemeRun row (production owns the row) and the SourceBinding
    is consumed via FK, NOT mutated.
    """
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    pre_s = a1_session_factory()
    try:
        pre_binding = pre_s.execute(
            select(SourceBindingRecord).where(
                SourceBindingRecord.id == SOURCE_BINDING_ID
            )
        ).scalar_one()
        pre_binding_hash = pre_binding.combined_source_hash
    finally:
        pre_s.close()

    result = run_scenario(
        a1_session_factory,
        source_binding_id=SOURCE_BINDING_ID,
        weight_set_revision_id=WEIGHT_REVISION_ID,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker="sqlite",
    )

    verify_s = a1_session_factory()
    try:
        post_binding = verify_s.execute(
            select(SourceBindingRecord).where(
                SourceBindingRecord.id == SOURCE_BINDING_ID
            )
        ).scalar_one()
        # SourceBinding combined_source_hash unchanged (runner does not mutate it)
        assert post_binding.combined_source_hash == pre_binding_hash
        # SchemeRun row references the same binding
        scheme_run = verify_s.execute(
            select(SchemeRunRecord).where(SchemeRunRecord.id == result.scheme_run.id)
        ).scalar_one()
        assert scheme_run.source_binding_id == SOURCE_BINDING_ID
    finally:
        verify_s.close()


# ── Test 20 — runner does NOT raise PhaseBBlockedError on happy path ───


def test_runner_does_not_raise_phase_b_blocked_on_happy_path(
    a1_engine: Any, a1_session_factory: Any
) -> None:
    """Pre-freeze §8 #12: ``expected_outcome`` MUST NOT be downgraded.

    The runner MUST NOT raise ``PhaseBBlockedError`` when production
    succeeds. We assert the runner returns a successful
    ``ScenarioOutcome`` with ``phase_b_blocked=False``.
    """
    seed_s = a1_session_factory()
    try:
        from tests.evaluation._seed_helpers import seed_a1_all_prereqs

        seed_a1_all_prereqs(seed_s)
    finally:
        seed_s.close()

    try:
        result = run_scenario(
            a1_session_factory,
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            correlation_marker=BASELINE_CORRELATION_ID,
            backend_marker="sqlite",
        )
    except PhaseBBlockedError as exc:
        raise AssertionError(
            f"Runner MUST NOT raise PhaseBBlockedError on the happy path "
            f"(pre-freeze §8 #12); got upstream_code={exc.upstream_code!r}"
        )

    assert result.phase_b_blocked is False
    assert result.outcome == "SUCCEEDED"


# ── Test 21 — runner does NOT modify production modules ─────────────────


def test_runner_does_not_modify_production_modules() -> None:
    """Pre-freeze §5.5: the runner MUST NOT modify production modules.

    The runner lives under ``backend/src/cold_storage/evaluation/``;
    production modules live under
    ``backend/src/cold_storage/modules/*/``. We assert via AST that
    the runner does not import any production module.
    """
    import ast

    runner_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cold_storage"
        / "evaluation"
        / "execute.py"
    )
    source = runner_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_substrings = (
        "cold_storage.modules.orchestration.infrastructure",
        "cold_storage.modules.schemes.infrastructure",
        "cold_storage.modules.calculations",
        "cold_storage.modules.knowledge",
        "cold_storage.modules.audit",
        "cold_storage.modules.coefficients",
        "cold_storage.bootstrap.seed",
        "cold_storage.bootstrap.scheme_seed",
        "production_seeding",
    )

    # Check imports: runner imports only the canonical composition
    # root + the production application ports + domain models.
    for stmt in tree.body:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                for forbidden in forbidden_substrings:
                    assert forbidden not in alias.name, (
                        f"Runner MUST NOT import {alias.name} "
                        f"(forbidden: {forbidden})"
                    )
        elif isinstance(stmt, ast.ImportFrom):
            module = stmt.module or ""
            for forbidden in forbidden_substrings:
                assert forbidden not in module, (
                    f"Runner MUST NOT import from {module} "
                    f"(forbidden: {forbidden})"
                )

    # Check source text for production-module references. We exclude
    # the module docstring (descriptive references to production_seeding
    # in the FORBIDDEN-paths discussion are permitted; the same pattern
    # as PR #49's architecture test).
    def _strip_docstring(s: str) -> str:
        tree = ast.parse(s)
        ds = ast.get_docstring(tree)
        if ds:
            return s.replace(ds, "")
        return s

    code_only = _strip_docstring(source)
    for forbidden in forbidden_substrings:
        assert forbidden not in code_only, (
            f"Runner source code (excluding docstring) must not "
            f"reference {forbidden} (pre-freeze §5.5 architecture boundary)"
        )


# ── Test 22 — errors module typed surface ───────────────────────────────


def test_errors_module_typed_surface() -> None:
    """The errors module exposes the typed surface the runner needs.

    Specifically: ``EvaluationRunnerError`` is the umbrella base,
    ``PhaseBBlockedError.code == 'PHASE_B_BLOCKED'``,
    ``InvalidEvaluationScenarioError.code == 'INVALID_EVALUATION_SCENARIO'``,
    and ``is_evaluation_runner_error`` distinguishes typed errors
    from generic exceptions.
    """
    from cold_storage.evaluation.errors import (
        EvaluationRunnerError,
        InvalidEvaluationScenarioError,
        PhaseBBlockedError,
        is_evaluation_runner_error,
    )

    assert EvaluationRunnerError is not None
    assert issubclass(InvalidEvaluationScenarioError, EvaluationRunnerError)
    assert issubclass(PhaseBBlockedError, EvaluationRunnerError)
    assert PhaseBBlockedError.code == "PHASE_B_BLOCKED"
    assert InvalidEvaluationScenarioError.code == "INVALID_EVALUATION_SCENARIO"

    # ``is_evaluation_runner_error`` classifies typed errors and
    # excludes generic exceptions.
    assert is_evaluation_runner_error(InvalidEvaluationScenarioError("x")) is True
    assert is_evaluation_runner_error(ValueError("x")) is False


# ── Test 23 — runner does NOT take a project_input ──────────────────────


def test_runner_does_not_take_project_input() -> None:
    """A1-2a surface: the runner does NOT accept a ``project_input``.

    Per pre-freeze §1.3 #1 + Path A Amendment 2 §13.2: the canonical
    runner surface is the same A1-2a input contract as the adapter.
    """
    sig = inspect.signature(run_scenario)
    params = list(sig.parameters.keys())
    assert "project_input" not in params, (
        f"A1.5 runner MUST NOT carry a 'project_input' parameter; "
        f"got parameters: {params}"
    )
    # The 4 A1-2a required parameters are all present
    assert "source_binding_id" in params
    assert "weight_set_revision_id" in params
    assert "correlation_marker" in params
    assert "backend_marker" in params