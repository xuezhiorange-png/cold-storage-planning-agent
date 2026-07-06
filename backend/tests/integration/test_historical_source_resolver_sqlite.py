"""P2-1 follow-up: historical source resolver parity — SQLite.

Mirrors ``test_historical_source_resolver_postgresql.py`` (same 14
scenarios, same scenario helpers from
``_archive_resolver_parity_helpers``).  Closes P2-1 of the PR #33 /
Issue #22E repo-backed engineering review (SQLite parity side).

Test surface:

    1.  legacy SchemeRun → LegacySourceBundle
    2.  production online binding hit → VerifiedOnlineSourceBundle
    3.  production online miss + valid archive → VerifiedArchiveSourceBundle
    4.  production online miss + no archive → SchemeRunHistoricalSourceUnavailableError
    5.  unsupported archive schema → SchemeSourceArchiveUnsupportedSchemaError
    6.  payload missing required key → SchemeSourceArchiveIntegrityError
    7.  payload extra key → SchemeSourceArchiveIntegrityError
    8.  malformed / reordered source_slots → SchemeSourceArchiveIntegrityError
    9.  tampered archive_hash column → SchemeSourceArchiveIntegrityError
    10. tampered combined_source_hash → TamperedError(field='combined_source_hash')
    11. tampered per-slot result_hash → TamperedError(field=<slot column>)
    12. tampered weight_set_content_hash → TamperedError(field='weight_set_content_hash')   # P2-2
    13. tampered binding_schema_version → TamperedError(field='binding_schema_version')     # P2-2
    14. online hit suppresses archive lookup (no latest-row fallback)
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite resolver parity tests cannot run on PostgreSQL — use "
        "test_historical_source_resolver_postgresql.py instead",
        allow_module_level=True,
    )

pytestmark = pytest.mark.sqlite

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Import the shared scenario helpers.  They are test-only.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _archive_resolver_parity_helpers import (  # noqa: E402
    SCHEMA_VERSION_V1,
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
)

# ── fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def migrated_engine() -> Iterator:
    """Apply alembic head to a fresh sqlite file.  Yields the engine."""
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
    tmp.close()
    db_path = Path(tmp.name)
    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)

    import subprocess

    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        db_path.unlink(missing_ok=True)
        pytest.fail(f"alembic upgrade failed:\n{r.stderr}\n{r.stdout}")

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _rec):  # noqa: ANN001
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    yield engine
    engine.dispose()
    db_path.unlink(missing_ok=True)


@pytest.fixture()
def repo():
    """Return a fresh repository instance per-test."""
    from cold_storage.modules.orchestration.infrastructure.source_archive_repository import (  # noqa: E501
        SqlAlchemyProductionSourceArchiveRepository,
    )

    return SqlAlchemyProductionSourceArchiveRepository()


def _persist_archive(
    session: Session,
    *,
    scheme_run_id: str,
    payload: dict,
    archive_hash: str | None = None,
    archive_schema_version: str = SCHEMA_VERSION_V1,
) -> None:
    """Insert a v1 archive row using the production repository."""
    from cold_storage.modules.orchestration.infrastructure.source_archive_repository import (  # noqa: E501
        SqlAlchemyProductionSourceArchiveRepository,
    )

    repo = SqlAlchemyProductionSourceArchiveRepository()
    repo.add_archive(
        session,
        archive_id=str(uuid.uuid4()),
        scheme_run_id=scheme_run_id,
        source_binding_id="binding-1",
        source_contract_version="SVC-1.0",
        archive_schema_version=archive_schema_version,
        archive_payload=payload,
        archive_hash=archive_hash or compute_hash_for_payload(payload),
        combined_source_hash=payload["combined_source_hash"],
        weight_set_revision_id="rev-1",
        weight_set_content_hash=payload["weight_set_content_hash"],
        binding_schema_version=payload["binding_schema_version"],
        execution_snapshot_id="snap-1",
        coefficient_context_id="ctx-1",
        orchestration_identity_id="ident-1",
        authoritative_attempt_id="att-1",
        orchestration_fingerprint="fp-1",
        created_at=datetime.now(UTC),
        created_by="parity-test-seed",
        reason="completed",
    )


# ── Tests ───────────────────────────────────────────────────────────────


class TestLegacyShortCircuit:
    def test_legacy_scheme_run_returns_legacy_bundle(self, migrated_engine, repo) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        scheme_run_row = make_scheme_run_row(scheme_run_id="legacy-1", source_mode="legacy")
        with Session(migrated_engine) as session:
            bundle = historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_legacy_bundle(bundle)


class TestOnlineHit:
    def test_production_online_hit_returns_verified_online_bundle(
        self, migrated_engine, repo
    ) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        scheme_run_row = make_scheme_run_row(scheme_run_id="online-1")
        lookup = make_online_source_lookup(
            scheme_run_id="online-1",
            source_binding_id="binding-online",
            combined_source_hash="combined-online",
        )
        with Session(migrated_engine) as session:
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


class TestArchiveFallback:
    def test_production_online_miss_with_valid_archive_returns_verified_archive_bundle(
        self, migrated_engine, repo
    ) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        payload = make_assembled_payload(scheme_run_id="archive-1")
        with Session(migrated_engine) as session, session.begin():
            _persist_archive(session, scheme_run_id="archive-1", payload=payload)

        scheme_run_row = make_scheme_run_row(scheme_run_id="archive-1")
        with Session(migrated_engine) as session:
            bundle = historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_verified_archive_bundle(bundle, expected_combined_source_hash="combined-h")

    def test_production_online_miss_no_archive_raises_unavailable(
        self, migrated_engine, repo
    ) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        scheme_run_row = make_scheme_run_row(scheme_run_id="no-archive-1")
        with Session(migrated_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_unavailable(exc_info)


class TestUnsupportedSchema:
    def test_unsupported_archive_schema_version_raises_unsupported(
        self, migrated_engine, repo
    ) -> None:
        """A row with a non-V1 ``archive_schema_version`` must fail closed.

        The production SQL CHECK ``ck_archive_schema_version_v1`` blocks
        such an INSERT in normal use; we side-step it by relaxing the
        constraint for this single test (mirrors the strategy used by
        ``test_migration_0034_downgrade_guard_hex_postgresql.py`` for
        the hex64 length CHECK).
        """
        import json

        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        payload = make_assembled_payload(scheme_run_id="bad-schema-1")
        archive_hash = compute_hash_for_payload(payload)

        with migrated_engine.connect() as conn:
            # SQLite has no ``ALTER TABLE ... DROP CONSTRAINT``;
            # ``PRAGMA ignore_check_constraints=1`` is the documented
            # escape hatch.  The existing
            # ``test_scheme_source_archive_sqlite.py`` uses the same
            # approach.
            conn.execute(text("PRAGMA ignore_check_constraints=1"))
            conn.execute(
                text(
                    "INSERT INTO production_source_archives "
                    "(id, scheme_run_id, source_binding_id, "
                    "source_contract_version, archive_schema_version, "
                    "archive_payload, archive_hash, "
                    "combined_source_hash, weight_set_revision_id, "
                    "weight_set_content_hash, binding_schema_version, "
                    "execution_snapshot_id, coefficient_context_id, "
                    "orchestration_identity_id, authoritative_attempt_id, "
                    "orchestration_fingerprint, created_at, "
                    "created_by, reason) VALUES ("
                    ":aid, :sid, :bid, 'SVC-1.0', :asv, "
                    ":payload, :ahash, 'combined-h', "
                    "'rev-1', 'weight-h', 'BSV-1.0', "
                    "'snap-1', 'ctx-1', 'ident-1', 'att-1', 'fp-1', "
                    ":cat, 'parity-test-seed', 'completed')"
                ),
                {
                    "aid": str(uuid.uuid4()),
                    "sid": "bad-schema-1",
                    "bid": "binding-1",
                    "asv": "SchemeSourceArchiveV9",
                    "payload": json.dumps(payload),
                    "ahash": archive_hash,
                    "cat": datetime.now(UTC),
                },
            )
            conn.commit()
            conn.execute(text("PRAGMA ignore_check_constraints=0"))

        scheme_run_row = make_scheme_run_row(scheme_run_id="bad-schema-1")
        with Session(migrated_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_unsupported_schema(exc_info)


class TestPayloadValidation:
    def test_payload_missing_required_key_raises_integrity(self, migrated_engine, repo) -> None:
        from sqlalchemy import select

        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            ProductionSourceArchiveRecord,
        )

        payload = make_assembled_payload(scheme_run_id="missing-key-1")
        with Session(migrated_engine) as session, session.begin():
            _persist_archive(session, scheme_run_id="missing-key-1", payload=payload)
            # Tamper: drop a required key.
            archive = session.execute(
                select(ProductionSourceArchiveRecord).where(
                    ProductionSourceArchiveRecord.scheme_run_id == "missing-key-1"
                )
            ).scalar_one()
            archive.archive_payload = {
                k: v for k, v in archive.archive_payload.items() if k != "project_id"
            }

        scheme_run_row = make_scheme_run_row(scheme_run_id="missing-key-1")
        with Session(migrated_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_payload_integrity(exc_info)

    def test_payload_extra_key_raises_integrity(self, migrated_engine, repo) -> None:
        from sqlalchemy import select

        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            ProductionSourceArchiveRecord,
        )

        payload = make_assembled_payload(scheme_run_id="extra-key-1")
        with Session(migrated_engine) as session, session.begin():
            _persist_archive(session, scheme_run_id="extra-key-1", payload=payload)
            archive = session.execute(
                select(ProductionSourceArchiveRecord).where(
                    ProductionSourceArchiveRecord.scheme_run_id == "extra-key-1"
                )
            ).scalar_one()
            payload_dict = dict(archive.archive_payload)
            payload_dict["rogue_field"] = "tampered"
            archive.archive_payload = payload_dict

        scheme_run_row = make_scheme_run_row(scheme_run_id="extra-key-1")
        with Session(migrated_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_payload_integrity(exc_info)

    def test_payload_reordered_source_slots_raises_integrity(self, migrated_engine, repo) -> None:
        from sqlalchemy import select

        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            ProductionSourceArchiveRecord,
        )

        payload = make_assembled_payload(scheme_run_id="reorder-1")
        with Session(migrated_engine) as session, session.begin():
            _persist_archive(session, scheme_run_id="reorder-1", payload=payload)
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
        with Session(migrated_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_payload_integrity(exc_info)


class TestTamperedArchive:
    def test_tampered_archive_hash_column_raises_integrity(self, migrated_engine, repo) -> None:
        """On-disk archive_hash mismatches the recomputed one → IntegrityError."""
        from sqlalchemy import select

        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            ProductionSourceArchiveRecord,
        )

        payload = make_assembled_payload(scheme_run_id="archive-hash-tamper")
        with Session(migrated_engine) as session, session.begin():
            _persist_archive(session, scheme_run_id="archive-hash-tamper", payload=payload)
            archive = session.execute(
                select(ProductionSourceArchiveRecord).where(
                    ProductionSourceArchiveRecord.scheme_run_id == "archive-hash-tamper"
                )
            ).scalar_one()
            # Overwrite archive_hash with a wrong-but-valid hex64 so CHECK
            # passes but recompute fails.
            archive.archive_hash = "0" * 64

        scheme_run_row = make_scheme_run_row(scheme_run_id="archive-hash-tamper")
        with Session(migrated_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_payload_integrity(exc_info)


class TestTamperedFields:
    def test_tampered_combined_source_hash_raises_tampered(self, migrated_engine, repo) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        payload = make_assembled_payload(scheme_run_id="combined-tamper")
        with Session(migrated_engine) as session, session.begin():
            _persist_archive(session, scheme_run_id="combined-tamper", payload=payload)

        # scheme_run_row has WRONG combined_source_hash.
        scheme_run_row = make_scheme_run_row(
            scheme_run_id="combined-tamper",
            combined_source_hash="WRONG-COMBINED",
        )
        with Session(migrated_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_tampered_field(exc_info, expected_field="combined_source_hash")

    def test_tampered_per_slot_result_hash_raises_tampered(self, migrated_engine, repo) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        payload = make_assembled_payload(scheme_run_id="slot-tamper")
        with Session(migrated_engine) as session, session.begin():
            _persist_archive(session, scheme_run_id="slot-tamper", payload=payload)

        # scheme_run_row has WRONG zone_result_hash.
        scheme_run_row = make_scheme_run_row(
            scheme_run_id="slot-tamper", slot_hashes={"zone": "WRONG-ZH"}
        )
        with Session(migrated_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_tampered_field(exc_info, expected_field="zone_result_hash")

    # ── P2-2 explicit tests ───────────────────────────────────────────

    def test_tampered_weight_set_content_hash_raises_tampered(self, migrated_engine, repo) -> None:
        """P2-2: weight_set_content_hash mismatch is fail-closed with the
        exact ``field='weight_set_content_hash'`` marker.
        """
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        payload = make_assembled_payload(scheme_run_id="wch-tamper")
        with Session(migrated_engine) as session, session.begin():
            _persist_archive(session, scheme_run_id="wch-tamper", payload=payload)

        scheme_run_row = make_scheme_run_row(
            scheme_run_id="wch-tamper",
            weight_set_content_hash="WRONG-WCH",
        )
        with Session(migrated_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_tampered_field(exc_info, expected_field="weight_set_content_hash")

    def test_tampered_binding_schema_version_raises_tampered(self, migrated_engine, repo) -> None:
        """P2-2: binding_schema_version mismatch is fail-closed with the
        exact ``field='binding_schema_version'`` marker.
        """
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        payload = make_assembled_payload(scheme_run_id="bsv-tamper")
        with Session(migrated_engine) as session, session.begin():
            _persist_archive(session, scheme_run_id="bsv-tamper", payload=payload)

        scheme_run_row = make_scheme_run_row(
            scheme_run_id="bsv-tamper",
            binding_schema_version="WRONG-BSV",
        )
        with Session(migrated_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_tampered_field(exc_info, expected_field="binding_schema_version")


class TestNoSilentFallback:
    """Defensive: online hit must suppress archive lookup; resolver must
    never 'latest-row' or partial-source a non-matching scheme_run.
    """

    def test_online_hit_does_not_consult_archive(self, migrated_engine, repo) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )

        # Even if a DIFFERENT scheme_run has a perfect archive, an online
        # hit for THIS scheme_run_id must short-circuit and return the
        # online bundle.  No latest-row / no partial-source.
        payload = make_assembled_payload(scheme_run_id="other-archive")
        with Session(migrated_engine) as session, session.begin():
            _persist_archive(session, scheme_run_id="other-archive", payload=payload)

        scheme_run_row = make_scheme_run_row(scheme_run_id="online-2")
        lookup = make_online_source_lookup(
            scheme_run_id="online-2",
            source_binding_id="binding-online-2",
            combined_source_hash="combined-online-2",
        )
        with Session(migrated_engine) as session:
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
