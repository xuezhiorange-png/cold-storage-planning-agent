"""P2-1 follow-up: historical source resolver parity — PostgreSQL.

Mirrors ``test_historical_source_resolver_sqlite.py`` (same 14
scenarios, same scenario helpers from
``_archive_resolver_parity_helpers``).  Closes P2-1 of the PR #33 /
Issue #22E repo-backed engineering review (PostgreSQL parity side).

PG-specific note: ``production_source_archives`` has 7 foreign keys.
We plant minimal archive rows via raw SQL with
``SET session_replication_role = 'replica'`` (same pattern used by
``test_migration_0034_downgrade_guard_hex_postgresql.py``) so the
planting transaction does not require a full SourceBinding chain.

Uses the project's ``pg_database`` fixture (auto-skips if PG is not
available — see ``tests/integration/conftest.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.postgresql

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Import the shared scenario helpers (test-only).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _archive_resolver_parity_helpers import (  # noqa: E402
    assert_legacy_bundle,
    assert_payload_integrity,
    assert_tampered_field,
    assert_unavailable,
    assert_unsupported_schema,
    assert_verified_archive_bundle,
    assert_verified_online_bundle,
    compute_hash_for_payload,
    make_assembled_payload,
    make_online_source_lookup,
    make_scheme_run_row,
    plant_minimal_pg_archive_row,
)

# ── fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def repo():
    """Return a fresh repository instance per-test."""
    from cold_storage.modules.orchestration.infrastructure.source_archive_repository import (  # noqa: E501
        SqlAlchemyProductionSourceArchiveRepository,
    )

    return SqlAlchemyProductionSourceArchiveRepository()


def _open_engine(pg_database):
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    return create_engine(pg_database, poolclass=NullPool)


# ── Tests ───────────────────────────────────────────────────────────────


class TestLegacyShortCircuit:
    def test_legacy_scheme_run_returns_legacy_bundle(self, pg_database, repo) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        engine = _open_engine(pg_database)
        try:
            scheme_run_row = make_scheme_run_row(scheme_run_id="legacy-1", source_mode="legacy")
            with Session(engine) as session:
                bundle = historical_source_resolver.resolve_scheme_run_sources_for_history(
                    session,
                    scheme_run_row,
                    read_port=repo,
                    online_source_lookup=None,
                )
            assert_legacy_bundle(bundle)
        finally:
            engine.dispose()


class TestOnlineHit:
    def test_production_online_hit_returns_verified_online_bundle(self, pg_database, repo) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        engine = _open_engine(pg_database)
        try:
            scheme_run_row = make_scheme_run_row(scheme_run_id="online-1")
            lookup = make_online_source_lookup(
                scheme_run_id="online-1",
                source_binding_id="binding-online",
                combined_source_hash="combined-online",
            )
            with Session(engine) as session:
                bundle = historical_source_resolver.resolve_scheme_run_sources_for_history(
                    session,
                    scheme_run_row,
                    read_port=repo,
                    online_source_lookup=lookup,
                )
            assert_verified_online_bundle(
                bundle,
                expected_source_binding_id="binding-online",
                expected_combined_source_hash="combined-online",
            )
        finally:
            engine.dispose()


class TestArchiveFallback:
    def test_production_online_miss_with_valid_archive_returns_verified_archive_bundle(
        self, pg_engine, repo
    ) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        payload = make_assembled_payload(scheme_run_id="archive-1")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="archive-1",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )

        scheme_run_row = make_scheme_run_row(scheme_run_id="archive-1")
        with Session(pg_engine) as session:
            bundle = historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_verified_archive_bundle(bundle, expected_combined_source_hash="combined-h")

    def test_production_online_miss_no_archive_raises_unavailable(self, pg_database, repo) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        engine = _open_engine(pg_database)
        try:
            scheme_run_row = make_scheme_run_row(scheme_run_id="no-archive-1")
            with Session(engine) as session, pytest.raises(Exception) as exc_info:
                historical_source_resolver.resolve_scheme_run_sources_for_history(
                    session,
                    scheme_run_row,
                    read_port=repo,
                    online_source_lookup=None,
                )
            assert_unavailable(exc_info)
        finally:
            engine.dispose()


class TestUnsupportedSchema:
    def test_unsupported_archive_schema_version_raises_unsupported(self, pg_engine) -> None:
        """A row with a non-V1 ``archive_schema_version`` must fail closed.

        The production SQL CHECK ``ck_archive_schema_version_v1`` blocks
        such an INSERT in normal use; we side-step it the same way the
        hex-PG test does (DROP CONSTRAINT inside the test session).
        """
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )
        from cold_storage.modules.orchestration.infrastructure.source_archive_repository import (  # noqa: E501
            SqlAlchemyProductionSourceArchiveRepository,
        )

        payload = make_assembled_payload(scheme_run_id="bad-schema-1")
        archive_hash = compute_hash_for_payload(payload)

        with pg_engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE production_source_archives "
                    "DROP CONSTRAINT ck_archive_schema_version_v1"
                )
            )
        try:
            plant_minimal_pg_archive_row(
                pg_engine,
                scheme_run_id="bad-schema-1",
                payload=payload,
                archive_hash=archive_hash,
                archive_schema_version="SchemeSourceArchiveV9",
            )

            repo = SqlAlchemyProductionSourceArchiveRepository()
            scheme_run_row = make_scheme_run_row(scheme_run_id="bad-schema-1")
            with Session(pg_engine) as session, pytest.raises(Exception) as exc_info:
                historical_source_resolver.resolve_scheme_run_sources_for_history(
                    session,
                    scheme_run_row,
                    read_port=repo,
                    online_source_lookup=None,
                )
            assert_unsupported_schema(exc_info)
        finally:
            # The factory drops the test database after the session
            # so we do not need to restore the constraint here.
            # (Re-adding it would fail because the planted row
            # carries ``archive_schema_version='SchemeSourceArchiveV9'``,
            # which is the whole point of the test.)
            pass


class TestPayloadValidation:
    def test_payload_missing_required_key_raises_integrity(self, pg_engine, repo) -> None:
        from sqlalchemy import select

        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            ProductionSourceArchiveRecord,
        )

        payload = make_assembled_payload(scheme_run_id="missing-key-1")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="missing-key-1",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )
        with Session(pg_engine) as session, session.begin():
            archive = session.execute(
                select(ProductionSourceArchiveRecord).where(
                    ProductionSourceArchiveRecord.scheme_run_id == "missing-key-1"
                )
            ).scalar_one()
            archive.archive_payload = {
                k: v for k, v in archive.archive_payload.items() if k != "project_id"
            }

        scheme_run_row = make_scheme_run_row(scheme_run_id="missing-key-1")
        with Session(pg_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_payload_integrity(exc_info)

    def test_payload_extra_key_raises_integrity(self, pg_engine, repo) -> None:
        from sqlalchemy import select

        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            ProductionSourceArchiveRecord,
        )

        payload = make_assembled_payload(scheme_run_id="extra-key-1")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="extra-key-1",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )
        with Session(pg_engine) as session, session.begin():
            archive = session.execute(
                select(ProductionSourceArchiveRecord).where(
                    ProductionSourceArchiveRecord.scheme_run_id == "extra-key-1"
                )
            ).scalar_one()
            payload_dict = dict(archive.archive_payload)
            payload_dict["rogue_field"] = "tampered"
            archive.archive_payload = payload_dict

        scheme_run_row = make_scheme_run_row(scheme_run_id="extra-key-1")
        with Session(pg_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_payload_integrity(exc_info)

    def test_payload_reordered_source_slots_raises_integrity(self, pg_engine, repo) -> None:
        from sqlalchemy import select

        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            ProductionSourceArchiveRecord,
        )

        payload = make_assembled_payload(scheme_run_id="reorder-1")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="reorder-1",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )
        with Session(pg_engine) as session, session.begin():
            archive = session.execute(
                select(ProductionSourceArchiveRecord).where(
                    ProductionSourceArchiveRecord.scheme_run_id == "reorder-1"
                )
            ).scalar_one()
            payload_dict = dict(archive.archive_payload)
            slots = payload_dict["source_slots"]
            assert isinstance(slots, list)
            payload_dict["source_slots"] = list(reversed(slots))
            archive.archive_payload = payload_dict

        scheme_run_row = make_scheme_run_row(scheme_run_id="reorder-1")
        with Session(pg_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_payload_integrity(exc_info)


class TestTamperedArchive:
    def test_tampered_archive_hash_column_raises_integrity(self, pg_engine, repo) -> None:
        """On-disk archive_hash mismatches the recomputed one → IntegrityError."""
        from sqlalchemy import select

        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            ProductionSourceArchiveRecord,
        )

        payload = make_assembled_payload(scheme_run_id="archive-hash-tamper")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="archive-hash-tamper",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )
        with Session(pg_engine) as session, session.begin():
            archive = session.execute(
                select(ProductionSourceArchiveRecord).where(
                    ProductionSourceArchiveRecord.scheme_run_id == "archive-hash-tamper"
                )
            ).scalar_one()
            archive.archive_hash = "0" * 64

        scheme_run_row = make_scheme_run_row(scheme_run_id="archive-hash-tamper")
        with Session(pg_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_payload_integrity(exc_info)


class TestTamperedFields:
    def test_tampered_combined_source_hash_raises_tampered(self, pg_engine, repo) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        payload = make_assembled_payload(scheme_run_id="combined-tamper")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="combined-tamper",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )

        scheme_run_row = make_scheme_run_row(
            scheme_run_id="combined-tamper",
            combined_source_hash="WRONG-COMBINED",
        )
        with Session(pg_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_tampered_field(exc_info, expected_field="combined_source_hash")

    def test_tampered_per_slot_result_hash_raises_tampered(self, pg_engine, repo) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        payload = make_assembled_payload(scheme_run_id="slot-tamper")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="slot-tamper",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )

        scheme_run_row = make_scheme_run_row(
            scheme_run_id="slot-tamper", slot_hashes={"zone": "WRONG-ZH"}
        )
        with Session(pg_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_tampered_field(exc_info, expected_field="zone_result_hash")

    # ── P2-2 explicit tests (PG side) ─────────────────────────────────

    def test_tampered_weight_set_content_hash_raises_tampered(self, pg_engine, repo) -> None:
        """P2-2 (PG): weight_set_content_hash mismatch is fail-closed."""
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        payload = make_assembled_payload(scheme_run_id="wch-tamper")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="wch-tamper",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )

        scheme_run_row = make_scheme_run_row(
            scheme_run_id="wch-tamper",
            weight_set_content_hash="WRONG-WCH",
        )
        with Session(pg_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_tampered_field(exc_info, expected_field="weight_set_content_hash")

    def test_tampered_binding_schema_version_raises_tampered(self, pg_engine, repo) -> None:
        """P2-2 (PG): binding_schema_version mismatch is fail-closed."""
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        payload = make_assembled_payload(scheme_run_id="bsv-tamper")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="bsv-tamper",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )

        scheme_run_row = make_scheme_run_row(
            scheme_run_id="bsv-tamper",
            binding_schema_version="WRONG-BSV",
        )
        with Session(pg_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_tampered_field(exc_info, expected_field="binding_schema_version")


class TestNoSilentFallback:
    def test_online_hit_does_not_consult_archive(self, pg_engine, repo) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        payload = make_assembled_payload(scheme_run_id="other-archive")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="other-archive",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )

        scheme_run_row = make_scheme_run_row(scheme_run_id="online-2")
        lookup = make_online_source_lookup(
            scheme_run_id="online-2",
            source_binding_id="binding-online-2",
            combined_source_hash="combined-online-2",
        )
        with Session(pg_engine) as session:
            bundle = historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=lookup,
            )
        assert_verified_online_bundle(
            bundle,
            expected_source_binding_id="binding-online-2",
            expected_combined_source_hash="combined-online-2",
        )
