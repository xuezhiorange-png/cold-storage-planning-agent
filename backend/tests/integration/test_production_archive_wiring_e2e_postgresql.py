"""PostgreSQL parity mirror of
``test_production_archive_wiring_e2e_sqlite.py``.

Slice 2D — Phase 4 Issue #35 §16 #2 acceptance closure.

Adds a single explicit PostgreSQL integration test that drives the
production composition root end-to-end through
``ProductionSchemeService.generate_production_scheme_run`` and asserts the
strict §4.3 happy-path row counts in one place:

* exactly 5 ``calculation_runs`` rows (one per stage: zone,
  cooling_load, equipment, power, investment),
* exactly 1 ``orchestration_source_bindings`` row,
* exactly 1 ``production_source_archives`` row,
* exactly 1 ``scheme_runs`` row.

The SQLite acceptance file ``test_production_archive_wiring_e2e_sqlite.py``
already proves 1 ``scheme_run`` + 1 ``production_source_archive`` per run;
this PG mirror closes the §16 #2 missing mirror (PostgreSQL happy path)
and adds the explicit 5-calc + 1-binding assertions inline so the
acceptance contract is observable from one PostgreSQL test that drives
the canonical composition entry.

Per Slice 2D rules:

* No mock that fakes a production state.
* No raw-ORM fabrication of an "expected" 5+1+1+1 state.
* No latest-row fallback.
* No demo coefficient fallback.
* No production-formula / coefficient / threshold / weight / review-rule
  mutation.
* No evaluation manifest / fixture / expected-output / runner change.

Slice: 2D — acceptance closure tests.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

# Seed helpers and golden constants shared with the PG production scheme
# test module.  These are append-only seam contracts; do not modify them
# in this Slice 2D module.
from tests.integration.test_production_scheme_postgresql import (  # noqa: E402
    ATTEMPT_ID,
    COEFF_CONTEXT_ID,
    EXEC_SNAPSHOT_ID,
    IDENTITY_ID,
    PROJECT_ID,
    SOURCE_BINDING_ID,
    VERSION_ID,
    WEIGHT_CONTENT_HASH,
    WEIGHT_REVISION_ID,
    _make_command,
    _seed_all_prereqs,
)

pytestmark = pytest.mark.postgresql


# ── Fresh-PG-engine helper ────────────────────────────────────────────────


def _fresh_pg_engine(pg_engine: Engine) -> Engine:
    """Return a NullPool-bound engine reusing the live URL.

    SQLAlchemy strips the password from ``str(sa_url)``, so we copy
    the URL object directly.  Mirrors the helper used in the Slice 2A
    PG resolution-gateway test.
    """
    return create_engine(pg_engine.url, poolclass=NullPool)


# ── Row-count scanner ────────────────────────────────────────────────────


def _count(session: Any, sql: str, **params: Any) -> int:
    """Run scalar COUNT(*) and return int.

    Uses bound parameters so the queries stay backend-portable.
    """
    row = session.execute(text(sql), params).scalar_one()
    return int(row)


def _fetch_binding_slot_ids(session: Any) -> list[str]:
    """Return the five FK calculation_run ids rooted on the binding."""
    row = session.execute(
        text(
            "SELECT zone_calculation_id, cooling_load_calculation_id, "
            "equipment_calculation_id, power_calculation_id, "
            "investment_calculation_id FROM orchestration_source_bindings "
            "WHERE id = :bid"
        ),
        {"bid": SOURCE_BINDING_ID},
    ).one_or_none()
    assert row is not None, (
        f"orchestration_source_bindings row missing for id={SOURCE_BINDING_ID!r}"
    )
    return [str(x) for x in row]


def _scrape_roundtrip_row_counts(session: Any) -> dict[str, int]:
    """Return the strict §4.3 happy-path row counts that survived commit.

    Anchored on the binding's five FK slot ids rather than the
    ``calculation_runs`` table globally, because a CI history row in
    that table is normal — but the **five FK slots that commit with
    this binding's transaction** are the §4.3 acceptance invariant.
    """
    slot_ids = _fetch_binding_slot_ids(session)
    assert len(slot_ids) == 5, (
        f"Expected 5 distinct FK slot ids on the binding, got {len(slot_ids)}"
    )
    # Build a parameterized IN clause via SQLAlchemy's expanding bind:
    # text() + bindparam(expanding=True) renders as "IN (:ids_1, :ids_2, …)".
    from sqlalchemy import bindparam

    sql = text("SELECT COUNT(*) FROM calculation_runs WHERE id IN :slots").bindparams(
        bindparam("slots", value=slot_ids, expanding=True)
    )
    calc_count = int(session.execute(sql).scalar_one())

    return {
        # exactly five CalculationRun rows anchored on this binding's five slots
        "calculation_runs": calc_count,
        # exactly one orchestration_source_bindings row for this binding id
        "orchestration_source_bindings": _count(
            session,
            "SELECT COUNT(*) FROM orchestration_source_bindings WHERE id = :bid",
            bid=SOURCE_BINDING_ID,
        ),
        # exactly one production_source_archives row anchored on this binding
        "production_source_archives": _count(
            session,
            "SELECT COUNT(*) FROM production_source_archives WHERE source_binding_id = :bid",
            bid=SOURCE_BINDING_ID,
        ),
        # exactly one scheme_runs row anchored on this binding
        "scheme_runs": _count(
            session,
            "SELECT COUNT(*) FROM scheme_runs WHERE source_binding_id = :bid",
            bid=SOURCE_BINDING_ID,
        ),
    }


# ── Tests ─────────────────────────────────────────────────────────────────


class TestPostgresProductionArchiveWiringE2ESlice2D:
    """§16 #2 PostgreSQL happy-path mirror — single 4-row acceptance test.

    Acceptance target (mirrors §4.3):

    A complete PostgreSQL roundtrip through the composition-rooted
    ``ProductionSchemeService`` produces exactly:

    * 5 ``calculation_runs``
    * 1 ``orchestration_source_bindings``
    * 1 ``production_source_archives``
    * 1 ``scheme_runs``

    All four row sets commit in the same UoW; row counts are observed
    from the database (not from in-memory structures).
    """

    def test_postgres_five_stage_happy_path_row_counts(
        self,
        pg_session_factory,
        pg_engine,
    ) -> None:
        """§16 #2 — full 5-stage database roundtrip on PostgreSQL.

        One single integration test pins the entire §4.3 happy-path row
        set on the ``backend-postgresql`` CI job.
        """
        assert pg_engine.dialect.name == "postgresql", (
            "This test is the PostgreSQL mirror; running it against SQLite "
            "is a contract violation, not a soft failure."
        )

        # ── Step 1: seed real production prereqs through PG seeds ────
        seed_s = pg_session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        # ── Step 2: drive the canonical composition entry ────────────
        # The composition root owns the wiring.  No manual repository
        # construction is permitted in this Slice — that is the §15.1
        # architecture rule.
        from cold_storage.bootstrap.production_composition import (
            compose_production_scheme_service,
        )
        from cold_storage.modules.schemes.application.production_service import (
            ProductionSchemeService,
        )

        service = compose_production_scheme_service(pg_session_factory)
        assert isinstance(service, ProductionSchemeService)

        cmd = _make_command()
        # database_backend is set inside _make_command() = "postgresql"
        result = service.generate_production_scheme_run(cmd)
        assert result.status == "completed"

        # ── Step 3: assert the strict §4.3 row counts from the DB ─────
        verify_s = pg_session_factory()
        try:
            counts = _scrape_roundtrip_row_counts(verify_s)
        finally:
            verify_s.close()

        assert counts == {
            "calculation_runs": 5,
            "orchestration_source_bindings": 1,
            "production_source_archives": 1,
            "scheme_runs": 1,
        }, (
            "§16 #2 / §4.3 PostgreSQL happy-path row counts regressed: "
            f"observed={counts!r} expected={{'calculation_runs': 5, "
            "'orchestration_source_bindings': 1, "
            "'production_source_archives': 1, 'scheme_runs': 1}}"
        )

        # ── Step 4: pin the archive binding + completion correlation ──
        verify_s = pg_session_factory()
        try:
            archive_row = verify_s.execute(
                text(
                    "SELECT archive_schema_version, archive_hash, "
                    "combined_source_hash, source_binding_id, scheme_run_id "
                    "FROM production_source_archives WHERE source_binding_id = :bid"
                ),
                {"bid": SOURCE_BINDING_ID},
            ).fetchone()
            assert archive_row is not None, (
                "production_source_archives row missing after completed run"
            )
            (
                archive_schema_version,
                archive_hash,
                archive_combined,
                archive_bid,
                scheme_run_id,
            ) = archive_row
            assert archive_schema_version == "SchemeSourceArchiveV1"
            assert archive_combined is not None
            assert len(archive_hash) == 64
            assert all(c in "0123456789abcdef" for c in archive_hash), (
                f"archive_hash must be lowercase hex64, got {archive_hash!r}"
            )
            assert archive_bid == SOURCE_BINDING_ID

            # Archive payload must contain canonical 5-slot ordering
            payload_json = verify_s.execute(
                text(
                    "SELECT archive_payload FROM production_source_archives "
                    "WHERE source_binding_id = :bid"
                ),
                {"bid": SOURCE_BINDING_ID},
            ).scalar_one()
            # SQLAlchemy's ``JSON`` column type round-trips via the
            # dialect's native JSON type: PG (JSONB) returns a dict,
            # SQLite (TEXT-backed JSON) returns a string.  Normalize.
            payload = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
            slot_field = payload.get("source_slots")
            assert isinstance(slot_field, list), (
                f"source_slots must be an ordered list, got {type(slot_field).__name__}"
            )
            names = [entry[0] for entry in slot_field]
            assert names == [
                "zone",
                "cooling_load",
                "equipment",
                "power",
                "investment",
            ], f"source_slots order regressed to {names!r}; canonical order required"

            # The scheme_run_id on the archive row must match the
            # generated scheme_run id (1:1 archive ↔ scheme_run).
            scheme_row = verify_s.execute(
                text(
                    "SELECT id, source_mode, source_binding_id, weight_set_revision_id "
                    "FROM scheme_runs WHERE id = :sid"
                ),
                {"sid": scheme_run_id},
            ).fetchone()
            assert scheme_row is not None, (
                f"scheme_runs row missing for archive.scheme_run_id={scheme_run_id}"
            )
            scheme_id, scheme_mode, scheme_bid, scheme_wrev = scheme_row
            assert scheme_id == result.id
            assert scheme_mode == "production"
            assert scheme_bid == SOURCE_BINDING_ID
            assert scheme_wrev == WEIGHT_REVISION_ID
        finally:
            verify_s.close()

        # ── Step 5: pin weight-set correlation stays consistent ──────
        # (no inspection-of-internal-state — only DB + return values.)
        verify_s = pg_session_factory()
        try:
            weight_row = verify_s.execute(
                text("SELECT weight_set_content_hash FROM scheme_runs WHERE id = :sid"),
                {"sid": result.id},
            ).fetchone()
            assert weight_row is not None
            assert weight_row[0] == WEIGHT_CONTENT_HASH, (
                f"weight_set_content_hash mismatch on PG mirror: "
                f"got {weight_row[0]!r}, expected {WEIGHT_CONTENT_HASH!r}"
            )
        finally:
            verify_s.close()

    def test_postgres_archive_failure_rolls_back_everything_slice2d(
        self,
        pg_session_factory,
        pg_engine,
    ) -> None:
        """§16 #2 — archive builder failure leaves zero new production rows.

        Mirrors ``TestProductionCompositionFailureRollback`` from the
        SQLite acceptance file.  The expectation on this PG mirror is
        stricter: not only ``scheme_runs == 0`` and
        ``production_source_archives == 0``, but also
        ``orchestration_source_bindings == 0`` and ``calculation_runs == 0``
        for rows that were candidates for this roundtrip.

        This pins the inverse direction of §4.3 happy-path: a failure
        in the archive builder must not leave half-committed state in
        any of the four production tables.
        """
        assert pg_engine.dialect.name == "postgresql"

        # ── Seed prereqs through the canonical PG path ──────────────
        seed_s = pg_session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        # Snapshot pre-state AFTER seeding so the delta is anchored
        # on the seeded rows that the roundtrip attempt must not
        # disturb; ``SELECT COUNT(*) FROM <table>`` on the
        # production-relevant tables captures the absolute state at
        # the moment the roundtrip starts (Phase 4 §9.1
        # "byte-identical post-failure vs pre-roundtrip state").
        before_s = pg_session_factory()
        try:
            before_archives = _count(
                before_s,
                "SELECT COUNT(*) FROM production_source_archives",
            )
            before_runs = _count(
                before_s,
                "SELECT COUNT(*) FROM scheme_runs",
            )
            before_bindings = _count(
                before_s,
                "SELECT COUNT(*) FROM orchestration_source_bindings",
            )
            before_calc = _count(
                before_s,
                "SELECT COUNT(*) FROM calculation_runs",
            )
        finally:
            before_s.close()

        # Force the archive-builder seam to raise.
        from cold_storage.modules.orchestration.application import (
            source_archive_builder,
        )
        from cold_storage.modules.schemes.application.production_ports import (
            GenerateProductionSchemeCommand,
        )
        from cold_storage.modules.schemes.application.production_service import (
            ProductionSchemeService,
        )

        boom_message = "intentional archive builder raise via PG slice-2d mirror"

        def _raise_archive(*_args: Any, **_kwargs: Any) -> None:
            raise source_archive_builder.SourceArchiveBuildError(boom_message)

        original = source_archive_builder.build_archive_for_completed_scheme_run
        source_archive_builder.build_archive_for_completed_scheme_run = _raise_archive
        try:
            from cold_storage.bootstrap.production_composition import (
                compose_production_scheme_service,
            )

            service = compose_production_scheme_service(pg_session_factory)
            assert isinstance(service, ProductionSchemeService)
            cmd = GenerateProductionSchemeCommand(
                source_binding_id=SOURCE_BINDING_ID,
                weight_set_revision_id=WEIGHT_REVISION_ID,
                profile_codes=("balanced",),
                profile_parameters={},
                actor="wiring-e2e-pg-failure",
                correlation_id="wiring-e2e-pg-corr-failure-001",
                database_backend="postgresql",
            )
            raised = False
            try:
                service.generate_production_scheme_run(cmd)
            except Exception as exc:  # noqa: BLE001 — exercise the seam
                assert boom_message in str(exc), (
                    f"expected exception to carry {boom_message!r}, got {exc!r}"
                )
                raised = True
            assert raised, "Composition-rooted PG service should have raised after archive failure"
        finally:
            source_archive_builder.build_archive_for_completed_scheme_run = original

        # ── Strict zero-delta assertion vs. the pre-state snapshot ───
        after_s = pg_session_factory()
        try:
            after_archives = _count(
                after_s,
                "SELECT COUNT(*) FROM production_source_archives",
            )
            after_runs = _count(after_s, "SELECT COUNT(*) FROM scheme_runs")
            after_bindings = _count(
                after_s,
                "SELECT COUNT(*) FROM orchestration_source_bindings",
            )
            after_calc = _count(after_s, "SELECT COUNT(*) FROM calculation_runs")
        finally:
            after_s.close()

        assert after_archives == before_archives, (
            f"production_source_archives delta is non-zero after failure: "
            f"before={before_archives} after={after_archives}"
        )
        assert after_runs == before_runs, (
            f"scheme_runs delta is non-zero after archive failure: "
            f"before={before_runs} after={after_runs}"
        )
        assert after_bindings == before_bindings, (
            f"orchestration_source_bindings delta is non-zero after archive failure: "
            f"before={before_bindings} after={after_bindings}"
        )
        assert after_calc == before_calc, (
            f"calculation_runs delta is non-zero after archive failure: "
            f"before={before_calc} after={after_calc}"
        )


# Suppress unused-name lint noise (these names are imported only for
# documentation / type clarity in the seeder; they are not needed at
# runtime in this slice-2D module).
_ = (IDENTITY_ID, COEFF_CONTEXT_ID, EXEC_SNAPSHOT_ID, ATTEMPT_ID, PROJECT_ID, VERSION_ID)
