"""§16 #10 — PK-set zero-delta rollback invariant — PostgreSQL mirror.

Phase 4 Issue #35 design contract §9.1 + §4.3 require that, if a 5-stage
production roundtrip fails at any point, the set of ``calculation_run``,
``orchestration_source_bindings``, ``scheme_runs``, and
``production_source_archives`` row PKs added or removed by the failed
transaction is empty.  This is the **PK-set zero-delta invariant**.

PostgreSQL parity mirror of ``test_zero_delta_invariant_sqlite.py``.

Per Slice 2D rules:

* No mock that fakes a production state.
* No raw-ORM fabrication of expected 5+1+1+1 rows.
* No latest-row fallback.
* No demo coefficient fallback.
* No production-formula / coefficient / threshold / weight / review-rule
  / migration / calculator change.
* No evaluation manifest / fixture / expected-output / runner change.

Slice: 2D — acceptance closure tests.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import bindparam, text

from tests.integration.test_production_scheme_postgresql import (  # noqa: E402
    SOURCE_BINDING_ID,
    WEIGHT_REVISION_ID,
    _make_service,
    _seed_all_prereqs,
)

pytestmark = pytest.mark.postgresql


# ── Row-set snapshot helpers (PG dialect-aware) ──────────────────────────


# Use the same binding-anchored slot anchor as the §16 #2 PG mirror,
# adapted to PG dialect (no string-quoting differences from SQLite here,
# but bindparam(expanding=True) is the safe way for slot ids).
def _fetch_binding_slot_ids_pg(session: Any) -> list[str]:
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


def _snapshot_pg_production_pk_sets(session: Any) -> dict[str, set[str]]:
    """Return the four production-table PK-sets anchored on the PG binding id."""
    slot_ids = _fetch_binding_slot_ids_pg(session)
    bind_sql = text("SELECT id FROM calculation_runs WHERE id IN :slots").bindparams(
        bindparam("slots", value=slot_ids, expanding=True)
    )
    calc_rows = session.execute(bind_sql).fetchall()
    calc_set = {r[0] for r in calc_rows}
    binding_set = {
        r[0]
        for r in session.execute(
            text("SELECT id FROM orchestration_source_bindings WHERE id = :bid"),
            {"bid": SOURCE_BINDING_ID},
        ).fetchall()
    }
    scheme_set = {
        r[0]
        for r in session.execute(
            text("SELECT id FROM scheme_runs WHERE source_binding_id = :bid"),
            {"bid": SOURCE_BINDING_ID},
        ).fetchall()
    }
    archive_set = {
        r[0]
        for r in session.execute(
            text("SELECT id FROM production_source_archives WHERE source_binding_id = :bid"),
            {"bid": SOURCE_BINDING_ID},
        ).fetchall()
    }
    return {
        "calculation_runs": calc_set,
        "orchestration_source_bindings": binding_set,
        "scheme_runs": scheme_set,
        "production_source_archives": archive_set,
    }


def _assert_zero_delta(
    before: dict[str, set[str]],
    after: dict[str, set[str]],
) -> None:
    """Same invariant as SQLite mirror — see §16 #10 in the design contract."""
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
            f"§16 #10 PK-set zero-delta violated on {t} "
            f"(PostgreSQL mirror): unexpectedly added rows after rollback: "
            f"{sorted(added)!r}"
        )
        assert removed == set(), (
            f"§16 #10 PK-set zero-delta violated on {t} "
            f"(PostgreSQL mirror): unexpectedly removed rows after rollback: "
            f"{sorted(removed)!r}"
        )


# ── Tests ─────────────────────────────────────────────────────────────────


class TestZeroDeltaInvariantPostgreSQLSlice2D:
    """§16 #10 — PK-set zero-delta invariant on PostgreSQL."""

    def test_pg_archive_builder_failure_leaves_no_production_pk_delta(
        self,
        pg_session_factory,
        pg_engine,
    ) -> None:
        """Archive-builder failure → zero PK-set delta on all 4 PG tables."""
        assert pg_engine.dialect.name == "postgresql"

        # ── 1. Seed real PG prereqs through the canonical path ─────
        seed_s = pg_session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        # ── 2. Snapshot PK-sets BEFORE the roundtrip attempt ───────
        before_s = pg_session_factory()
        try:
            before = _snapshot_pg_production_pk_sets(before_s)
        finally:
            before_s.close()

        # Anchor: 5 calc + 1 binding should already exist
        assert len(before["calculation_runs"]) == 5, (
            f"PG pre-state calculation_runs expected 5 seeded slots, "
            f"got {len(before['calculation_runs'])}: {before['calculation_runs']!r}"
        )
        assert len(before["orchestration_source_bindings"]) == 1, (
            f"PG pre-state orchestration_source_bindings expected 1, "
            f"got {len(before['orchestration_source_bindings'])}"
        )

        # ── 3. Force the archive-builder seam to raise ──────────────
        from cold_storage.bootstrap.production_composition import (
            compose_production_scheme_service,
        )
        from cold_storage.modules.orchestration.application import (
            source_archive_builder,
        )
        from cold_storage.modules.schemes.application.production_ports import (
            GenerateProductionSchemeCommand,
        )
        from cold_storage.modules.schemes.application.production_service import (
            ProductionSchemeService,
        )

        boom_message = "intentional slice-2d pg zero-delta archive raise"

        def _raise_archive(*_args: Any, **_kwargs: Any) -> None:
            raise source_archive_builder.SourceArchiveBuildError(boom_message)

        original = source_archive_builder.build_archive_for_completed_scheme_run
        source_archive_builder.build_archive_for_completed_scheme_run = _raise_archive

        raised = False
        try:
            service = compose_production_scheme_service(pg_session_factory)
            assert isinstance(service, ProductionSchemeService)
            cmd = GenerateProductionSchemeCommand(
                source_binding_id=SOURCE_BINDING_ID,
                weight_set_revision_id=WEIGHT_REVISION_ID,
                profile_codes=("balanced",),
                profile_parameters={},
                actor="zero-delta-pg-slice2d",
                correlation_id="zero-delta-pg-corr-001",
                database_backend="postgresql",
            )
            try:
                service.generate_production_scheme_run(cmd)
            except Exception as exc:  # noqa: BLE001
                assert boom_message in str(exc), (
                    f"expected exception to carry {boom_message!r}, got {exc!r}"
                )
                raised = True
        finally:
            source_archive_builder.build_archive_for_completed_scheme_run = original

        assert raised, (
            "PG roundtrip was expected to raise after archive-builder failure; "
            "no exception was observed."
        )

        # ── 4. Snapshot PK-sets AFTER the failure ───────────────────
        after_s = pg_session_factory()
        try:
            after = _snapshot_pg_production_pk_sets(after_s)
        finally:
            after_s.close()

        # ── 5. Assert PK-set zero-delta invariant on all 4 tables ───
        _assert_zero_delta(before, after)

    def test_pg_midpipeline_failure_leaves_no_scheme_or_archive_rows(
        self,
        pg_session_factory,
        pg_engine,
    ) -> None:
        """PG mirror — mid-pipeline raise after scheme_runs flush must
        still produce zero PK-set delta in scheme_runs + archive."""
        assert pg_engine.dialect.name == "postgresql"

        seed_s = pg_session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        before_s = pg_session_factory()
        try:
            before = _snapshot_pg_production_pk_sets(before_s)
        finally:
            before_s.close()

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
                database_backend=kwargs.get("database_backend", "postgresql"),
            )
            session.add(run_rec)
            session.flush()
            raise RuntimeError("Simulated slice-2d PG mid-pipeline raise after scheme_runs flush")

        SqlAlchemyProductionSchemeRunRepository.save_production_run = _save_then_raise
        try:
            service = _make_service(pg_engine)
            from cold_storage.modules.schemes.application.production_ports import (
                GenerateProductionSchemeCommand,
            )

            cmd = GenerateProductionSchemeCommand(
                source_binding_id=SOURCE_BINDING_ID,
                weight_set_revision_id=WEIGHT_REVISION_ID,
                profile_codes=("balanced",),
                profile_parameters={},
                actor="zero-delta-midpipe-pg-slice2d",
                correlation_id="zero-delta-midpipe-pg-corr-001",
                database_backend="postgresql",
            )
            raised = False
            try:
                service.generate_production_scheme_run(cmd)
            except Exception as exc:  # noqa: BLE001
                assert "Simulated slice-2d PG mid-pipeline raise" in str(exc), (
                    f"expected mid-pipeline raise, got {exc!r}"
                )
                raised = True
            assert raised, "PG mid-pipeline seam should have raised; no raise observed."
        finally:
            SqlAlchemyProductionSchemeRunRepository.save_production_run = _original_save

        after_s = pg_session_factory()
        try:
            after = _snapshot_pg_production_pk_sets(after_s)
        finally:
            after_s.close()

        _assert_zero_delta(before, after)
