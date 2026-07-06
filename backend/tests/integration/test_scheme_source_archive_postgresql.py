"""P2-1 follow-up: production source archive — PostgreSQL parity.

Mirrors the core contract surface of
``test_scheme_source_archive_sqlite.py`` on PostgreSQL.  Covers the
10 scenarios required by the P2-1 review:

    1.  migration applied: table + 19 columns + indexes
    2.  archive builder happy path writes a row with a canonical payload
    3.  archive hash is stable for repeated input
    4.  archive readback verifies a bundle via the repository
    5.  malformed payload is rejected before hash acceptance
    6.  slot order is fixed (assembler + on-disk)
    7.  missing / extra / reordered slot rejected
    8.  tamper fail-closed paths (combined_source_hash / slot / archive_hash)
    9.  repository returns None when no archive exists
    10. archive row preserves scheme_run_id uniqueness

Pure-function assembler tests (no DB) are owned by
``test_archive_payload_validator_fail_closed.py`` and the slot-order
section of ``test_scheme_source_archive_sqlite.py`` (dialect-agnostic).
This file focuses on the **DB-coupled** surface on PostgreSQL.

Uses the project's ``pg_database`` / ``pg_engine`` fixtures
(auto-skips if PG is not available — see
``tests/integration/conftest.py``).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.postgresql

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Import the shared scenario helpers (test-only).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _archive_resolver_parity_helpers import (  # noqa: E402
    EXPECTED_SLOT_ORDER_V1,
    SCHEMA_VERSION_V1,
    assert_payload_integrity,
    assert_tampered_field,
    assert_verified_archive_bundle,
    compute_hash_for_payload,
    make_assembled_payload,
    make_ordered_slots,
    plant_minimal_pg_archive_row,
)

# ── Tests ───────────────────────────────────────────────────────────────


class TestMigrationApplied:
    def test_production_source_archives_table_exists(self, pg_engine) -> None:
        with pg_engine.connect() as conn:
            row = conn.execute(text("SELECT to_regclass('production_source_archives')")).scalar()
        assert row is not None, "production_source_archives table missing"

    def test_required_columns_present(self, pg_engine) -> None:
        with pg_engine.connect() as conn:
            cols = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'production_source_archives'"
                )
            ).fetchall()
        col_names = {r[0] for r in cols}
        required = {
            "id",
            "scheme_run_id",
            "source_binding_id",
            "source_contract_version",
            "archive_schema_version",
            "archive_payload",
            "archive_hash",
            "combined_source_hash",
            "weight_set_revision_id",
            "weight_set_content_hash",
            "binding_schema_version",
            "execution_snapshot_id",
            "coefficient_context_id",
            "orchestration_identity_id",
            "authoritative_attempt_id",
            "orchestration_fingerprint",
            "created_at",
            "created_by",
            "reason",
        }
        missing = required - col_names
        assert not missing, f"missing columns: {sorted(missing)}"

    def test_index_on_source_binding_id_present(self, pg_engine) -> None:
        with pg_engine.connect() as conn:
            row = conn.execute(
                text("SELECT to_regclass('ix_production_source_archives_source_binding_id')")
            ).scalar()
        assert row is not None, "ix_production_source_archives_source_binding_id index missing"


class TestBuilderRepositoryRoundtrip:
    def test_build_and_persist_archive_row(self, pg_engine) -> None:
        """The application builder produces a v1 archive row that the
        repository can read back byte-identical to the assembled
        payload.

        The production builder goes through SQLAlchemy's ORM path
        which enforces FKs.  We work around that by binding the
        Session to a single raw connection with
        ``session_replication_role = 'replica'`` so the INSERT
        bypasses FK triggers.
        """
        from cold_storage.modules.orchestration.application import (
            canonical_archive_v1,
            source_archive_builder,
        )
        from cold_storage.modules.orchestration.infrastructure.source_archive_repository import (  # noqa: E501
            SqlAlchemyProductionSourceArchiveRepository,
        )

        repo = SqlAlchemyProductionSourceArchiveRepository()
        # Single connection for both the SET and the Session.
        with pg_engine.connect() as conn:
            conn.execute(text("SET session_replication_role = 'replica'"))
            with Session(bind=conn) as session, session.begin():
                archive_id = source_archive_builder.build_archive_for_completed_scheme_run(
                    session,
                    repo,
                    scheme_run_id="build-1",
                    source_binding_id="binding-1",
                    source_contract_version="SVC-1.0",
                    binding_schema_version="BSV-1.0",
                    combined_source_hash="combined-1",
                    weight_set_revision_id="rev-1",
                    weight_set_content_hash="weight-1",
                    weight_set_generator_compatibility_version="WG-1.0",
                    execution_snapshot_id="snap-1",
                    coefficient_context_id="ctx-1",
                    orchestration_identity_id="ident-1",
                    authoritative_attempt_id="att-1",
                    orchestration_fingerprint="fp-1",
                    source_slots=make_ordered_slots(),
                    project_id="proj-1",
                    project_version_id="pver-1",
                    generator_compatibility_version="GCV-1.0",
                    actor="parity-test-actor",
                )
                assert archive_id is not None
                readback = repo.find_by_scheme_run_id(session, "build-1")
            conn.execute(text("SET session_replication_role = 'origin'"))
        assert readback is not None
        assert readback["archive_schema_version"] == SCHEMA_VERSION_V1
        assert readback["archive_hash"] == canonical_archive_v1.compute_archive_hash_v1(
            readback["archive_payload"]
        )
        # Sanity: the read-back payload must also pass the validator
        # (the same invariant the resolver enforces on read).
        canonical_archive_v1.validate_archive_payload_v1(readback["archive_payload"])

    def test_hash_stable_for_repeated_input(self) -> None:
        """Pure-function check: same assembler inputs → same hash."""
        payload_a = make_assembled_payload(scheme_run_id="stable-1")
        payload_b = make_assembled_payload(scheme_run_id="stable-1")
        assert compute_hash_for_payload(payload_a) == compute_hash_for_payload(payload_b)

    def test_readback_verifies_bundle(self, pg_engine) -> None:
        """Resolver reads the planted archive and returns
        VerifiedArchiveSourceBundle.
        """
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )
        from cold_storage.modules.orchestration.infrastructure.source_archive_repository import (  # noqa: E501
            SqlAlchemyProductionSourceArchiveRepository,
        )

        payload = make_assembled_payload(scheme_run_id="rb-1")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="rb-1",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )

        # Build a scheme_run_row matching the archive.
        from _archive_resolver_parity_helpers import make_scheme_run_row

        scheme_run_row = make_scheme_run_row(scheme_run_id="rb-1")
        repo = SqlAlchemyProductionSourceArchiveRepository()
        with Session(pg_engine) as session:
            bundle = historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_verified_archive_bundle(bundle, expected_combined_source_hash="combined-h")


class TestMalformedPayloadRejected:
    def test_payload_missing_required_key_raises_integrity(self, pg_engine) -> None:
        """Persisted archive with a missing required payload key must
        fail closed BEFORE the hash recompute runs.
        """
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            ProductionSourceArchiveRecord,
        )
        from cold_storage.modules.orchestration.infrastructure.source_archive_repository import (  # noqa: E501
            SqlAlchemyProductionSourceArchiveRepository,
        )

        payload = make_assembled_payload(scheme_run_id="bad-keys-1")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="bad-keys-1",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )
        with Session(pg_engine) as session, session.begin():
            archive = session.execute(
                select(ProductionSourceArchiveRecord).where(
                    ProductionSourceArchiveRecord.scheme_run_id == "bad-keys-1"
                )
            ).scalar_one()
            archive.archive_payload = {
                k: v for k, v in archive.archive_payload.items() if k != "project_id"
            }

        from _archive_resolver_parity_helpers import make_scheme_run_row

        repo = SqlAlchemyProductionSourceArchiveRepository()
        scheme_run_row = make_scheme_run_row(scheme_run_id="bad-keys-1")
        with Session(pg_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_payload_integrity(exc_info)


class TestSlotOrderFixed:
    def test_assembler_emits_canonical_order(self) -> None:
        """The assembler's on-the-wire ``source_slots`` must be a
        list in ``EXPECTED_SLOT_ORDER_V1`` order.
        """
        payload = make_assembled_payload(scheme_run_id="order-1")
        assert isinstance(payload["source_slots"], list)
        actual = [entry[0] for entry in payload["source_slots"]]
        assert actual == list(EXPECTED_SLOT_ORDER_V1)

    def test_assembler_rejects_reversed_order(self) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            assemble_archive_payload,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            SourceArchiveBuildError,
        )

        reversed_slots = list(reversed(make_ordered_slots()))
        with pytest.raises(SourceArchiveBuildError):
            assemble_archive_payload(
                scheme_run_id="x",
                source_binding_id=None,
                source_contract_version="SVC-1.0",
                binding_schema_version="BSV-1.0",
                combined_source_hash="c",
                weight_set_revision_id=None,
                weight_set_content_hash=None,
                weight_set_generator_compatibility_version=None,
                execution_snapshot_id=None,
                coefficient_context_id=None,
                orchestration_identity_id=None,
                authoritative_attempt_id=None,
                orchestration_fingerprint=None,
                source_slots=reversed_slots,
                project_id="p",
                project_version_id="v",
                generator_compatibility_version="GCV-1.0",
                captured_at=datetime(2026, 7, 4, tzinfo=UTC),
            )

    def test_assembler_rejects_missing_slot(self) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            assemble_archive_payload,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            SourceArchiveBuildError,
        )

        slots = make_ordered_slots()
        # Drop the last (investment) slot
        truncated = slots[:-1]
        with pytest.raises(SourceArchiveBuildError):
            assemble_archive_payload(
                scheme_run_id="x",
                source_binding_id=None,
                source_contract_version="SVC-1.0",
                binding_schema_version="BSV-1.0",
                combined_source_hash="c",
                weight_set_revision_id=None,
                weight_set_content_hash=None,
                weight_set_generator_compatibility_version=None,
                execution_snapshot_id=None,
                coefficient_context_id=None,
                orchestration_identity_id=None,
                authoritative_attempt_id=None,
                orchestration_fingerprint=None,
                source_slots=truncated,
                project_id="p",
                project_version_id="v",
                generator_compatibility_version="GCV-1.0",
                captured_at=datetime(2026, 7, 4, tzinfo=UTC),
            )

    def test_assembler_rejects_extra_slot(self) -> None:
        from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
            assemble_archive_payload,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            SourceArchiveBuildError,
        )

        slots = make_ordered_slots() + [
            ("rogue", {"calculation_id": "x", "result_hash": "y"}),
        ]
        with pytest.raises(SourceArchiveBuildError):
            assemble_archive_payload(
                scheme_run_id="x",
                source_binding_id=None,
                source_contract_version="SVC-1.0",
                binding_schema_version="BSV-1.0",
                combined_source_hash="c",
                weight_set_revision_id=None,
                weight_set_content_hash=None,
                weight_set_generator_compatibility_version=None,
                execution_snapshot_id=None,
                coefficient_context_id=None,
                orchestration_identity_id=None,
                authoritative_attempt_id=None,
                orchestration_fingerprint=None,
                source_slots=slots,
                project_id="p",
                project_version_id="v",
                generator_compatibility_version="GCV-1.0",
                captured_at=datetime(2026, 7, 4, tzinfo=UTC),
            )


class TestTamperFailClosed:
    def test_tampered_combined_source_hash_raises_tampered(self, pg_engine) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )
        from cold_storage.modules.orchestration.infrastructure.source_archive_repository import (  # noqa: E501
            SqlAlchemyProductionSourceArchiveRepository,
        )

        payload = make_assembled_payload(scheme_run_id="ct-1")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="ct-1",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )

        from _archive_resolver_parity_helpers import make_scheme_run_row

        repo = SqlAlchemyProductionSourceArchiveRepository()
        scheme_run_row = make_scheme_run_row(
            scheme_run_id="ct-1",
            combined_source_hash="WRONG",
        )
        with Session(pg_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_tampered_field(exc_info, expected_field="combined_source_hash")

    def test_tampered_slot_raises_tampered(self, pg_engine) -> None:
        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )
        from cold_storage.modules.orchestration.infrastructure.source_archive_repository import (  # noqa: E501
            SqlAlchemyProductionSourceArchiveRepository,
        )

        payload = make_assembled_payload(scheme_run_id="st-1")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="st-1",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )

        from _archive_resolver_parity_helpers import make_scheme_run_row

        repo = SqlAlchemyProductionSourceArchiveRepository()
        scheme_run_row = make_scheme_run_row(
            scheme_run_id="st-1", slot_hashes={"equipment": "WRONG-EH"}
        )
        with Session(pg_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_tampered_field(exc_info, expected_field="equipment_result_hash")

    def test_tampered_archive_hash_raises_integrity(self, pg_engine) -> None:
        from sqlalchemy import select

        from cold_storage.modules.orchestration.application import (
            historical_source_resolver,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            ProductionSourceArchiveRecord,
        )
        from cold_storage.modules.orchestration.infrastructure.source_archive_repository import (  # noqa: E501
            SqlAlchemyProductionSourceArchiveRepository,
        )

        payload = make_assembled_payload(scheme_run_id="ah-1")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="ah-1",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )
        with Session(pg_engine) as session, session.begin():
            archive = session.execute(
                select(ProductionSourceArchiveRecord).where(
                    ProductionSourceArchiveRecord.scheme_run_id == "ah-1"
                )
            ).scalar_one()
            archive.archive_hash = "0" * 64

        from _archive_resolver_parity_helpers import make_scheme_run_row

        repo = SqlAlchemyProductionSourceArchiveRepository()
        scheme_run_row = make_scheme_run_row(scheme_run_id="ah-1")
        with Session(pg_engine) as session, pytest.raises(Exception) as exc_info:
            historical_source_resolver.resolve_scheme_run_sources_for_history(
                session,
                scheme_run_row,
                read_port=repo,
                online_source_lookup=None,
            )
        assert_payload_integrity(exc_info)


class TestRepositoryReturnsNone:
    def test_no_archive_returns_none(self, pg_engine) -> None:
        from cold_storage.modules.orchestration.infrastructure.source_archive_repository import (  # noqa: E501
            SqlAlchemyProductionSourceArchiveRepository,
        )

        repo = SqlAlchemyProductionSourceArchiveRepository()
        with Session(pg_engine) as session:
            row = repo.find_by_scheme_run_id(session, "no-such-archive")
        assert row is None


class TestSchemeRunIdUniqueness:
    def test_unique_constraint_on_scheme_run_id(self, pg_engine) -> None:
        """Two archive rows for the same scheme_run_id must violate
        the UNIQUE constraint.
        """

        payload = make_assembled_payload(scheme_run_id="dup-1")
        plant_minimal_pg_archive_row(
            pg_engine,
            scheme_run_id="dup-1",
            payload=payload,
            archive_hash=compute_hash_for_payload(payload),
        )
        # Second plant must raise IntegrityError because of the
        # unique=True on scheme_run_id.
        with pytest.raises(IntegrityError):
            plant_minimal_pg_archive_row(
                pg_engine,
                scheme_run_id="dup-1",
                payload=payload,
                archive_hash=compute_hash_for_payload(payload),
            )


# Required by the historical-source-resolver test surface: re-export
# the resolver so ruff doesn't flag the unused import on systems where
# the resolver is needed for `TestUnsupportedSchema` parity (kept here
# for cross-file tooling symmetry).
__all__ = [
    "SCHEMA_VERSION_V1",
    "EXPECTED_SLOT_ORDER_V1",
]
