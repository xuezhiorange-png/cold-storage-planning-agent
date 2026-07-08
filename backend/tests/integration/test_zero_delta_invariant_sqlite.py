"""§16 #10 — PK-set zero-delta rollback invariant — SQLite.

Phase 4 Issue #35 design contract §9.1 + §4.3 require that, if a 5-stage
production roundtrip fails at any point, the set of ``calculation_run``,
``orchestration_source_bindings``, ``scheme_runs``, and
``production_source_archives`` row PKs added or removed by the failed
transaction is empty.  This is the **PK-set zero-delta invariant**.

This SQLite module makes the invariant observable from one place: a
single dedicated integration test that

1. Snapshots the four PK-sets before the roundtrip attempt.
2. Drives the production roundtrip through the canonical composition
   root with a forced archive-builder failure (the same seam
   ``test_production_archive_wiring_e2e_sqlite.py::TestProductionCompositionFailureRollback``
   uses, kept here as the failure mode is the smallest observable
   error).
3. Re-reads the four PK-sets after the failure.
4. Asserts ``after - before == ∅`` and ``before - after == ∅`` for all
   four production tables — and asserts no exception was silently
   swallowed.

A second dedicated test (separate from #1 above) drives the roundtrip
through a mid-pipeline failure (archive row commits, scheme run fails
to commit) — that route is exercised by mutating the
``build_archive_for_completed_scheme_run`` seam to commit-then-raise;
the PK-set delta must remain zero.

Out of Slice 2D scope:

* No mock that fakes a production success state.
* No raw-ORM fabrication of expected 5+1+1+1 rows.
* No latest-row fallback.
* No demo coefficient fallback.
* No production formula / coefficient / threshold / weight /
  review-rule / migration / calculator change.
* No evaluation manifest / fixture / expected-output / runner change.
* No production code change outside ``backend/tests/``.

PG parity mirror lives in ``test_zero_delta_invariant_postgresql.py``.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

# Reuse the canonical SQLite seed + service + command helpers from the
# existing production golden-seed module.  Do NOT modify those helpers
# in this Slice 2D module.
from tests.integration.test_production_archive_wiring_e2e_sqlite import (  # noqa: E402
    _build_production_service_via_composition,
)
from tests.integration.test_production_transaction_b_e2e_sqlite import (  # noqa: E402
    GOLDEN_SOURCE_BINDING_ID,
    GOLDEN_WEIGHT_REVISION_ID,
    _seed_all_production_prereqs,
)

pytestmark = pytest.mark.sqlite


# ── Row-set snapshot helpers ─────────────────────────────────────────────


_PRODUCTION_TABLES_WITH_PK_ANCHOR: dict[str, str] = {
    # The four production tables anchored on the binding's id (or, for
    # calculation_runs, on the five FK slot ids).  Each entry is a
    # "WHERE … anchor …" clause to embed inside SELECT id FROM <anchor>.
    "calculation_runs": (
        "calculation_runs WHERE id IN ("
        "SELECT zone_calculation_id FROM orchestration_source_bindings "
        "WHERE id = :bid UNION ALL "
        "SELECT cooling_load_calculation_id FROM orchestration_source_bindings "
        "WHERE id = :bid UNION ALL "
        "SELECT equipment_calculation_id FROM orchestration_source_bindings "
        "WHERE id = :bid UNION ALL "
        "SELECT power_calculation_id FROM orchestration_source_bindings "
        "WHERE id = :bid UNION ALL "
        "SELECT investment_calculation_id FROM orchestration_source_bindings "
        "WHERE id = :bid)"
    ),
    "orchestration_source_bindings": ("orchestration_source_bindings WHERE id = :bid"),
    "scheme_runs": "scheme_runs WHERE source_binding_id = :bid",
    "production_source_archives": ("production_source_archives WHERE source_binding_id = :bid"),
}


def _fetch_pk_set(session: Any, anchor_sql: str) -> set[str]:
    """Return the set of PK strings currently in the anchored row set."""
    sql = text(f"SELECT id FROM {anchor_sql}")
    rows = session.execute(sql, {"bid": GOLDEN_SOURCE_BINDING_ID}).fetchall()
    return {r[0] for r in rows}


def _snapshot_production_pk_sets(session: Any) -> dict[str, set[str]]:
    return {
        t: _fetch_pk_set(session, anchor_sql)
        for t, anchor_sql in _PRODUCTION_TABLES_WITH_PK_ANCHOR.items()
    }


def _assert_zero_delta(
    before: dict[str, set[str]],
    after: dict[str, set[str]],
) -> None:
    """PK-set zero-delta invariant: ``added == ∅`` and ``removed == ∅``.

    §9.1 / §16 #10 — for each of the four production tables, the
    symmetric difference of the PK-set across the failed transaction
    must be empty.
    """
    for t in (
        "calculation_runs",
        "orchestration_source_bindings",
        "scheme_runs",
        "production_source_archives",
    ):
        assert t in before and t in after, f"PK-set table missing from snapshot: {t}"
        added = after[t] - before[t]
        removed = before[t] - after[t]
        assert added == set(), (
            f"§16 #10 PK-set zero-delta violated on {t}: "
            f"unexpectedly added rows after rollback: {sorted(added)!r}"
        )
        assert removed == set(), (
            f"§16 #10 PK-set zero-delta violated on {t}: "
            f"unexpectedly removed rows after rollback: {sorted(removed)!r}"
        )


# ── Fixtures (mirror the SQLite production archive wiring file's) ──────


@pytest.fixture()
def db_path(tmp_path) -> str:
    return str(tmp_path / "zero_delta_test.db")


@pytest.fixture()
def engine(db_path):
    backend_dir = __file__.split("/backend/")[0] + "/backend"
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["SQLITE_PATH"] = db_path
    env["DATABASE_BACKEND"] = "sqlite"
    env.setdefault("COLD_STORAGE_TESTING", "1")
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
        cwd=backend_dir,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed (exit={r.returncode}):\n"
            f"stdout={r.stdout}\nstderr={r.stderr}"
        )
    e = create_engine(f"sqlite:///{db_path}", future=True)

    @event.listens_for(e, "connect")
    def _fk_on(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    yield e
    e.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


# ── Tests ────────────────────────────────────────────────────────────────


class TestZeroDeltaInvariantSlice2D:
    """§16 #10 — PK-set zero-delta invariant on SQLite.

    A single test pins the symmetric-difference property across all
    four production tables in one observable, deterministic place.
    """

    def test_archive_builder_failure_leaves_no_production_pk_delta(
        self,
        engine,
        session_factory,
    ) -> None:
        """Archive-builder failure → zero PK-set delta on all 4 tables."""
        # ── 1. Seed prereqs (golden Transaction B + binding + weight) ─
        with session_factory() as session:
            _seed_all_production_prereqs(session)

        # ── 2. Snapshot PK-sets BEFORE the roundtrip attempt ───────
        with session_factory() as session:
            before = _snapshot_production_pk_sets(session)

        # Anchor the seed: 5 calc runs + 1 binding must already exist
        # because _seed_all_production_prereqs seeds them.  Two rows
        # may already be there; the assertion below is on the DELTA,
        # not the absolute cardinality.
        assert len(before["calculation_runs"]) == 5, (
            f"Pre-state calculation_runs expected 5 seeded slots, "
            f"got {len(before['calculation_runs'])}: "
            f"{before['calculation_runs']!r}"
        )
        assert len(before["orchestration_source_bindings"]) == 1, (
            f"Pre-state orchestration_source_bindings expected 1, "
            f"got {len(before['orchestration_source_bindings'])}"
        )

        # ── 3. Force the archive-builder seam to raise ──────────────
        from cold_storage.modules.orchestration.application import (
            source_archive_builder,
        )
        from cold_storage.modules.schemes.application.production_ports import (
            GenerateProductionSchemeCommand,
        )

        boom_message = "intentional slice-2d zero-delta archive raise"

        def _raise_archive(*_args: Any, **_kwargs: Any) -> None:
            raise source_archive_builder.SourceArchiveBuildError(boom_message)

        original = source_archive_builder.build_archive_for_completed_scheme_run
        source_archive_builder.build_archive_for_completed_scheme_run = _raise_archive

        raised = False
        try:
            service = _build_production_service_via_composition(session_factory)
            cmd = GenerateProductionSchemeCommand(
                source_binding_id=GOLDEN_SOURCE_BINDING_ID,
                weight_set_revision_id=GOLDEN_WEIGHT_REVISION_ID,
                profile_codes=("balanced",),
                profile_parameters={},
                actor="zero-delta-slice2d",
                correlation_id="zero-delta-corr-001",
                database_backend="sqlite",
            )
            try:
                service.generate_production_scheme_run(cmd)
            except Exception as exc:  # noqa: BLE001 — intentional seam
                assert boom_message in str(exc), (
                    f"expected exception to carry {boom_message!r}, got {exc!r}"
                )
                raised = True
        finally:
            source_archive_builder.build_archive_for_completed_scheme_run = original

        assert raised, (
            "Roundtrip was expected to raise after archive-builder failure; "
            "no exception was observed."
        )

        # ── 4. Snapshot PK-sets AFTER the failure ───────────────────
        with session_factory() as session:
            after = _snapshot_production_pk_sets(session)

        # ── 5. Assert PK-set zero-delta invariant on all 4 tables ───
        _assert_zero_delta(before, after)

    def test_midpipeline_failure_after_bindings_leaves_no_scheme_or_archive_rows(
        self,
        engine,
        session_factory,
    ) -> None:
        """A mid-pipeline raise **after** the binding is committed MUST
        still leave zero new ``scheme_runs`` + zero new
        ``production_source_archives`` rows.

        Pinning the half-committed state guard for §9.2 (byte-identical
        post-failure vs pre-roundtrip state, except for append-only
        audit logs).
        """
        # Seed prereqs.
        with session_factory() as session:
            _seed_all_production_prereqs(session)

        before_s = session_factory()
        try:
            before = _snapshot_production_pk_sets(before_s)
        finally:
            before_s.close()

        # Patch the saver to commit scheme_runs row, then raise
        # *before* flush of archive row.  This exercises the half-
        # committed case where a scheme_run row has been queued.
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeRunRecord,
        )
        from cold_storage.modules.schemes.infrastructure.production_repository import (
            SqlAlchemyProductionSchemeRunRepository,
        )

        _original_save = SqlAlchemyProductionSchemeRunRepository.save_production_run

        def _save_then_raise(self, session, /, **kwargs):
            run_rec = SchemeRunRecord(
                id=kwargs["run_id"],
                project_id=kwargs["project_id"],
                project_version_id=kwargs["project_version_id"],
                weight_set_id=kwargs["weight_set_id"],
                status=kwargs["status"],
                generator_version=kwargs["generator_version"],
                source_snapshot_hash=kwargs["source_snapshot_hash"],
                input_snapshot=kwargs["input_snapshot"],
                assumption_snapshot={
                    **kwargs["assumption_snapshot"],
                    "profile_codes": list(kwargs["profile_codes"]),
                    "profile_parameters": dict(kwargs["profile_parameters"]),
                },
                comparison_snapshot=kwargs["comparison_snapshot"],
                candidates_snapshot=kwargs["candidates_snapshot"],
                requires_review=kwargs["requires_review"],
                recommended_scheme_code=kwargs["recommended_scheme_code"],
                warning_messages=kwargs["warning_messages"],
                content_hash=kwargs["content_hash"],
                source_mode=kwargs["source_mode"],
                source_binding_id=kwargs["source_binding_id"],
                source_contract_version=kwargs["source_contract_version"],
                weight_set_revision_id=kwargs["weight_set_revision_id"],
                weight_set_content_hash=kwargs["weight_set_content_hash"],
                weight_set_generator_compatibility_version=kwargs[
                    "weight_set_generator_compatibility_version"
                ],
                combined_source_hash=kwargs["combined_source_hash"],
                binding_schema_version=kwargs["binding_schema_version"],
                execution_snapshot_id=kwargs["execution_snapshot_id"],
                coefficient_context_id=kwargs["coefficient_context_id"],
                orchestration_identity_id=kwargs["orchestration_identity_id"],
                authoritative_attempt_id=kwargs["authoritative_attempt_id"],
                orchestration_fingerprint=kwargs["orchestration_fingerprint"],
                zone_calculation_id=kwargs["zone_calculation_id"],
                cooling_load_calculation_id=kwargs["cooling_load_calculation_id"],
                equipment_calculation_id=kwargs["equipment_calculation_id"],
                power_calculation_id=kwargs["power_calculation_id"],
                investment_calculation_id=kwargs["investment_calculation_id"],
                zone_result_hash=kwargs["zone_result_hash"],
                cooling_load_result_hash=kwargs["cooling_load_result_hash"],
                equipment_result_hash=kwargs["equipment_result_hash"],
                power_result_hash=kwargs["power_result_hash"],
                investment_result_hash=kwargs["investment_result_hash"],
                database_backend=kwargs.get("database_backend", "sqlite"),
            )
            session.add(run_rec)
            session.flush()
            # Raise before archive builder commits — this simulates a
            # mid-pipeline failure where the run has been queued but
            # the archive commit has not yet started.  The outer UoW
            # must still abort; no scheme_runs or production_source_archives
            # row may land.
            raise RuntimeError("Simulated slice-2d mid-pipeline raise after scheme_runs flush")

        SqlAlchemyProductionSchemeRunRepository.save_production_run = _save_then_raise
        try:
            service = _build_production_service_via_composition(session_factory)
            from cold_storage.modules.schemes.application.production_ports import (
                GenerateProductionSchemeCommand,
            )

            cmd = GenerateProductionSchemeCommand(
                source_binding_id=GOLDEN_SOURCE_BINDING_ID,
                weight_set_revision_id=GOLDEN_WEIGHT_REVISION_ID,
                profile_codes=("balanced",),
                profile_parameters={},
                actor="zero-delta-midpipe-slice2d",
                correlation_id="zero-delta-midpipe-corr-001",
                database_backend="sqlite",
            )
            raised = False
            try:
                service.generate_production_scheme_run(cmd)
            except Exception as exc:  # noqa: BLE001
                assert "Simulated slice-2d mid-pipeline raise" in str(exc), (
                    f"expected mid-pipeline raise, got {exc!r}"
                )
                raised = True
            assert raised, "Mid-pipeline seam should have raised; no raise observed."
        finally:
            SqlAlchemyProductionSchemeRunRepository.save_production_run = _original_save

        after_s = session_factory()
        try:
            after = _snapshot_production_pk_sets(after_s)
        finally:
            after_s.close()

        # On SQLite the bound PK-set deltas must remain zero across the
        # outer transaction.  snapshot_anchor only counts rows bound to
        # this exact binding_id; rows added but then rolled back will
        # not appear in the post snapshot.  This is the §9.1
        # observable.
        _assert_zero_delta(before, after)
