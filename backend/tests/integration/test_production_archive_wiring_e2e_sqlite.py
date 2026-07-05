"""Round-9 P0-1 wiring acceptance test (production composition entry).

The production archive row MUST land in the same UoW + same commit as
the production ``scheme_runs`` row.  Round 9 closes the wiring gap that
round 8 left: the test now drives through the **canonical production
composition entry** ``bootstrap.production_composition.compose_production_scheme_service``
and exercises the real
``ProductionSchemeService.generate_production_scheme_run`` command path.

The composition root is the single place in the production tree that
constructs ``SqlAlchemyProductionSchemeRunRepository``; the architecture
test ``test_production_archive_wiring_boundary`` enforces that no other
file in ``backend/src/cold_storage/`` may construct the repository
without ``build_archive_callable=``.

Acceptance targets
==================

The four user-stated round-9 acceptance targets are all driven by
observable database state from the composition-rooted service:

1.  ``production_source_archives`` row arrives in the SAME transaction
    as ``scheme_runs`` (same UoW session, same ``session.commit()``).
2.  Archive builder failure rolls back the entire SchemeRun UoW
    (no half-committed SchemeRun row, no archive row).
3.  Real ``ProductionSchemeService.generate_production_scheme_run`` call
    results in exactly one ``production_source_archives`` row.
4.  The wiring is acquired through the canonical composition root
    (``bootstrap.production_composition.compose_production_scheme_service``),
    not by manually constructing the repository inside the test.

This module deliberately does NOT:

* import ``SqlAlchemyProductionSchemeRunRepository`` directly,
* import ``make_production_archive_callable`` directly,
* import any module that exposes ``build_archive_callable``.

The composition root owns all three.  Any leakage would be a wiring
regression; the architecture test catches it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

# Import the production-chain golden seed helpers from the existing
# E2E test.  All five ``CalculationRunRecord.result_hash`` values,
# the ``SourceBinding`` row, and the ``SchemeWeightSet`` /
# ``SchemeWeightSetRevision`` rows come from this helper — they are
# identical to the ones the production verifier accepts.
from tests.integration.test_production_transaction_b_e2e_sqlite import (  # noqa: E402
    GOLDEN_COMBINED_SOURCE_HASH,
    GOLDEN_REQUEST_ID,
    GOLDEN_SOURCE_BINDING_ID,
    GOLDEN_WEIGHT_REVISION_ID,
    _seed_all_production_prereqs,
)

pytestmark = pytest.mark.sqlite


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def db_path() -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
    tmp.close()
    try:
        return tmp.name
    finally:
        Path(tmp.name).unlink(missing_ok=True)


@pytest.fixture()
def engine(db_path):
    """SQLite engine after ``alembic upgrade head``."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    assert backend_dir.name == "backend", backend_dir

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["SQLITE_PATH"] = db_path
    env["DATABASE_BACKEND"] = "sqlite"
    env.setdefault("COLD_STORAGE_TESTING", "1")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "upgrade",
            "head",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(backend_dir),
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed (exit={result.returncode}):\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )

    e = create_engine(f"sqlite:///{db_path}", future=True)

    @event.listens_for(e, "connect")
    def _fk_on(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    yield e
    e.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


# ── Production composition entry builder ──────────────────────────────────


def _build_production_service_via_composition(session_factory_obj):
    """Return a ``ProductionSchemeService`` wired through the composition root.

    The composition root is the **single** production-mode factory
    allowed to construct ``SqlAlchemyProductionSchemeRunRepository``
    in ``backend/src/cold_storage/``.  It binds the archive
    closure into the repository constructor and shares the same
    session per UoW request, so the archive INSERT and the
    SchemeRun INSERT land in one transaction.
    """
    from cold_storage.bootstrap.production_composition import (
        compose_production_scheme_service,
    )

    return compose_production_scheme_service(session_factory_obj)


# ── Tests ─────────────────────────────────────────────────────────────────


class TestProductionCompositionWiringE2E:
    """Round-9 acceptance: production composition entry drives the wiring.

    These tests do NOT reach for ``SqlAlchemyProductionSchemeRunRepository``
    or ``make_production_archive_callable`` themselves.  They acquire
    the wiring exclusively through
    ``bootstrap.production_composition.compose_production_scheme_service``.
    """

    def test_composition_root_writes_archive_row_on_generate(
        self,
        engine,
        session_factory,
    ) -> None:
        """Driving ``service.generate_production_scheme_run`` via the
        composition root MUST land both ``scheme_runs`` and
        ``production_source_archives`` rows in the same commit.
        """
        from cold_storage.modules.schemes.application.production_ports import (
            GenerateProductionSchemeCommand,
        )
        from cold_storage.modules.schemes.application.production_service import (
            ProductionSchemeService,
        )

        with session_factory() as session:
            _seed_all_production_prereqs(session)

        service = _build_production_service_via_composition(session_factory)
        assert isinstance(service, ProductionSchemeService)

        cmd = GenerateProductionSchemeCommand(
            source_binding_id=GOLDEN_SOURCE_BINDING_ID,
            weight_set_revision_id=GOLDEN_WEIGHT_REVISION_ID,
            profile_codes=("balanced",),
            profile_parameters={},
            actor="wiring-e2e-composition",
            correlation_id="wiring-e2e-corr-composition-001",
        )

        result = service.generate_production_scheme_run(cmd)

        run_id = result.id
        with session_factory() as session:
            sr_count = session.execute(
                text("SELECT COUNT(*) FROM scheme_runs WHERE id = :rid"),
                {"rid": run_id},
            ).scalar_one()
            assert sr_count == 1, f"Expected exactly 1 scheme_runs row, got {sr_count}"

            row = session.execute(
                text(
                    "SELECT archive_schema_version, archive_hash, "
                    "combined_source_hash, source_binding_id FROM "
                    "production_source_archives WHERE scheme_run_id = :sid"
                ),
                {"sid": run_id},
            ).fetchone()
            assert row is not None, (
                "production_source_archives row missing after compose-generated run"
            )
            archive_schema_version, archive_hash, archive_combined, archive_bid = row
            assert archive_schema_version == "SchemeSourceArchiveV1"
            assert archive_combined == GOLDEN_COMBINED_SOURCE_HASH
            assert archive_bid == GOLDEN_SOURCE_BINDING_ID
            assert len(archive_hash) == 64
            assert all(c in "0123456789abcdef" for c in archive_hash), (
                f"archive_hash must be lowercase hex64, got {archive_hash!r}"
            )

            payload_json = session.execute(
                text(
                    "SELECT archive_payload FROM production_source_archives "
                    "WHERE scheme_run_id = :sid"
                ),
                {"sid": run_id},
            ).scalar_one()
            payload = json.loads(payload_json)
            slot_field = payload["source_slots"]
            assert isinstance(slot_field, list), "source_slots must be an ordered list, not a dict"
            names = [entry[0] for entry in slot_field]
            assert names == [
                "zone",
                "cooling_load",
                "equipment",
                "power",
                "investment",
            ], f"source_slots order regressed to {names!r}; canonical order required"

    def test_composition_archive_row_count_is_one_per_run(
        self,
        engine,
        session_factory,
    ) -> None:
        """One ``generate_production_scheme_run`` MUST produce exactly one archive row."""
        from cold_storage.modules.schemes.application.production_ports import (
            GenerateProductionSchemeCommand,
        )

        with session_factory() as session:
            _seed_all_production_prereqs(session)

        service = _build_production_service_via_composition(session_factory)

        cmd = GenerateProductionSchemeCommand(
            source_binding_id=GOLDEN_SOURCE_BINDING_ID,
            weight_set_revision_id=GOLDEN_WEIGHT_REVISION_ID,
            profile_codes=("balanced",),
            profile_parameters={},
            actor="wiring-e2e-composition-count",
            correlation_id="wiring-e2e-corr-count-001",
        )

        result = service.generate_production_scheme_run(cmd)

        with session_factory() as session:
            count = session.execute(
                text("SELECT COUNT(*) FROM production_source_archives WHERE scheme_run_id = :sid"),
                {"sid": result.id},
            ).scalar_one()
            assert count == 1, f"Expected exactly 1 archive row, got {count}"

    def test_composition_service_has_archive_callable_bound(
        self,
        session_factory,
    ) -> None:
        """The composition root MUST bind ``build_archive_callable``."""
        service = _build_production_service_via_composition(session_factory)
        run_repo = service._run_repo
        assert run_repo is not None, "production service must own a run_repository"
        build_callable = getattr(run_repo, "_build_archive_callable", None)
        assert build_callable is not None and callable(build_callable), (
            "composition root forgot to bind build_archive_callable into "
            "SqlAlchemyProductionSchemeRunRepository"
        )


class TestProductionCompositionFailureRollback:
    """Round-9 acceptance: archive builder failure rolls back via composition."""

    def test_archive_builder_failure_rolls_back_via_composition(
        self,
        engine,
        session_factory,
    ) -> None:
        """Archiving failure under the composition root MUST leave
        zero ``scheme_runs`` rows and zero ``production_source_archives``
        rows behind.
        """
        from cold_storage.modules.orchestration.application import (
            source_archive_builder,
        )
        from cold_storage.modules.schemes.application.production_ports import (
            GenerateProductionSchemeCommand,
        )

        with session_factory() as session:
            _seed_all_production_prereqs(session)

        boom_message = "intentional archive builder raise via composition"

        def _raise_archive(*_args, **_kwargs) -> None:
            raise source_archive_builder.SourceArchiveBuildError(boom_message)

        original = source_archive_builder.build_archive_for_completed_scheme_run
        source_archive_builder.build_archive_for_completed_scheme_run = _raise_archive
        try:
            service = _build_production_service_via_composition(session_factory)
            cmd = GenerateProductionSchemeCommand(
                source_binding_id=GOLDEN_SOURCE_BINDING_ID,
                weight_set_revision_id=GOLDEN_WEIGHT_REVISION_ID,
                profile_codes=("balanced",),
                profile_parameters={},
                actor="wiring-e2e-composition-failure",
                correlation_id="wiring-e2e-corr-failure-001",
            )
            raised = False
            try:
                service.generate_production_scheme_run(cmd)
            except Exception as exc:  # noqa: BLE001
                assert boom_message in str(exc), (
                    f"expected exception message to carry {boom_message!r}, got {exc!r}"
                )
                raised = True
            assert raised, "Composition-rooted service should have raised after archive failure"
        finally:
            source_archive_builder.build_archive_for_completed_scheme_run = original

        with session_factory() as session:
            run_count = session.execute(
                text("SELECT COUNT(*) FROM scheme_runs WHERE source_binding_id = :bid"),
                {"bid": GOLDEN_SOURCE_BINDING_ID},
            ).scalar_one()
            assert run_count == 0, (
                f"SchemeRun row committed despite archive failure (found {run_count} rows)"
            )
            archive_count = session.execute(
                text(
                    "SELECT COUNT(*) FROM production_source_archives WHERE source_binding_id = :bid"
                ),
                {"bid": GOLDEN_SOURCE_BINDING_ID},
            ).scalar_one()
            assert archive_count == 0, (
                f"Archive row committed despite builder failure (found {archive_count} rows)"
            )


# Suppress unused-import warning (used for documentation / type clarity
# on golden constants; not needed at runtime in this test file).
_ = GOLDEN_REQUEST_ID
