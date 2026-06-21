"""PostgreSQL integration tests for knowledge module.

Verifies schema existence, JSONB column round-trips, foreign-key constraints,
unique constraints, transaction behavior, and review status persistence.

Requires: DATABASE_URL=postgresql+psycopg2://...
Marker: postgresql
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cold_storage.modules.knowledge.domain.errors import ApprovedRevisionImmutabilityError
from cold_storage.modules.knowledge.domain.lifecycle import assert_not_approved

pytestmark = pytest.mark.postgresql


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_engine():
    """Create a real PostgreSQL engine for testing."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set — skipping PostgreSQL integration tests")
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def pg_session(pg_engine):
    """Create a session bound to the PostgreSQL engine."""
    with Session(pg_engine) as session:
        yield session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_knowledge_document(conn, doc_id: str, code: str) -> None:
    """Insert a knowledge_documents row."""
    conn.execute(
        text(
            "INSERT INTO knowledge_documents "
            "(id, code, title, document_category, source_type, source_reference, "
            " owner, current_revision_number, created_at, updated_at) "
            "VALUES (:id, :code, 'Test Doc', 'standard', 'upload', 'test.pdf', "
            " 'tester', 0, NOW(), NOW())"
        ),
        {"id": doc_id, "code": code},
    )


def _insert_knowledge_revision(
    conn,
    revision_id: str,
    doc_id: str,
    rev_num: int = 1,
    content_hash: str = "abc123",
) -> None:
    """Insert a knowledge_revisions row."""
    conn.execute(
        text(
            "INSERT INTO knowledge_revisions "
            "(id, document_id, revision_number, version_label, original_filename, "
            " safe_filename, mime_type, file_extension, file_size_bytes, "
            " content_sha256, storage_key, ingestion_status, review_status, "
            " requires_ocr, requires_review, parser_name, parser_version, "
            " chunker_version, embedding_version, extracted_text_length, "
            " page_count, sheet_count, metadata_snapshot, warning_messages, "
            " created_at, indexed_at, reviewed_at, approved_at, withdrawn_at) "
            "VALUES (:id, :did, :rev_num, 'v1', 'test.pdf', 'test.pdf', "
            " 'application/pdf', '.pdf', 1024, :hash, :key, 'uploaded', "
            " 'unverified', false, true, 'pdf', 'parser-v1', 'chunk-v1', "
            " 'fake-hash-v1', 500, 5, NULL, CAST('{}' AS JSON), "
            " CAST('[]' AS JSON), NOW(), NULL, NULL, NULL, NULL)"
        ),
        {
            "id": revision_id,
            "did": doc_id,
            "rev_num": rev_num,
            "hash": content_hash,
            "key": f"knowledge/{doc_id}/{rev_num}",
        },
    )


def _cleanup_knowledge(conn, doc_id: str) -> None:
    """Clean up knowledge data for a given document."""
    revisions = conn.execute(
        text("SELECT id FROM knowledge_revisions WHERE document_id = :did"),
        {"did": doc_id},
    ).fetchall()
    for (rev_id,) in revisions:
        conn.execute(text("DELETE FROM knowledge_chunks WHERE revision_id = :rid"), {"rid": rev_id})
        conn.execute(
            text("DELETE FROM knowledge_ingestion_runs WHERE revision_id = :rid"), {"rid": rev_id}
        )
    conn.execute(text("DELETE FROM knowledge_revisions WHERE document_id = :did"), {"did": doc_id})
    conn.execute(text("DELETE FROM knowledge_documents WHERE id = :did"), {"did": doc_id})


# ---------------------------------------------------------------------------
# 1. Dialect test
# ---------------------------------------------------------------------------


class TestKnowledgeDialect:
    def test_dialect_is_postgresql(self, pg_engine) -> None:
        """Engine dialect must be postgresql."""
        assert pg_engine.dialect.name == "postgresql", (
            f"Expected postgresql, got {pg_engine.dialect.name}"
        )


# ---------------------------------------------------------------------------
# 2-4. Migration and table tests
# ---------------------------------------------------------------------------


class TestKnowledgeMigrations:
    def test_migration_0007_tables_exist(self, pg_engine) -> None:
        """All 4 knowledge tables exist after migration."""
        expected = [
            "knowledge_documents",
            "knowledge_revisions",
            "knowledge_ingestion_runs",
            "knowledge_chunks",
        ]
        with pg_engine.connect() as conn:
            for table in expected:
                result = conn.execute(
                    text(
                        "SELECT EXISTS ("
                        "  SELECT FROM information_schema.tables "
                        f"  WHERE table_name = '{table}'"
                        ")"
                    )
                )
                assert result.scalar() is True, f"Table {table} not found"

    def test_four_knowledge_tables_count(self, pg_engine) -> None:
        """Exactly 4 knowledge tables exist."""
        with pg_engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' "
                    "AND table_name LIKE 'knowledge_%'"
                )
            )
            count = result.scalar()
            assert count == 4, f"Expected 4 knowledge tables, got {count}"


# ---------------------------------------------------------------------------
# 5-7. JSONB column tests
# ---------------------------------------------------------------------------


class TestKnowledgeJsonb:
    def test_jsonb_metadata_on_revision(self, pg_engine) -> None:
        """Insert a revision with metadata_snapshot JSONB, read back."""
        doc_id = str(uuid.uuid4())
        rev_id = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_knowledge_document(conn, doc_id, f"pg-meta-{uuid.uuid4().hex[:8]}")
                conn.execute(
                    text(
                        "INSERT INTO knowledge_revisions "
                        "(id, document_id, revision_number, version_label, "
                        " original_filename, safe_filename, mime_type, file_extension, "
                        " file_size_bytes, content_sha256, storage_key, "
                        " ingestion_status, review_status, requires_ocr, requires_review, "
                        " parser_name, parser_version, chunker_version, embedding_version, "
                        " extracted_text_length, page_count, sheet_count, "
                        " metadata_snapshot, warning_messages, "
                        " created_at, indexed_at, reviewed_at, approved_at, withdrawn_at) "
                        "VALUES (:id, :did, 1, 'v1', 'test.pdf', 'test.pdf', "
                        " 'application/pdf', '.pdf', 1024, 'hash1', 'key1', "
                        " 'uploaded', 'unverified', false, true, "
                        " 'pdf', 'parser-v1', 'chunk-v1', 'fake-hash-v1', "
                        " 500, 5, NULL, CAST(:meta AS JSON), "
                        " CAST('[]' AS JSON), NOW(), NULL, NULL, NULL, NULL)"
                    ),
                    {
                        "id": rev_id,
                        "did": doc_id,
                        "meta": json.dumps({"source_format": "pdf", "pages": 5}),
                    },
                )
                conn.commit()

                row = conn.execute(
                    text("SELECT metadata_snapshot FROM knowledge_revisions WHERE id = :id"),
                    {"id": rev_id},
                ).scalar()
                assert row is not None
                assert row["source_format"] == "pdf"
                assert row["pages"] == 5
        finally:
            with pg_engine.connect() as conn:
                _cleanup_knowledge(conn, doc_id)
                conn.commit()

    def test_jsonb_embedding_on_chunk(self, pg_engine) -> None:
        """Insert a chunk with embedding JSONB array, read back."""
        doc_id = str(uuid.uuid4())
        rev_id = str(uuid.uuid4())
        chunk_id = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_knowledge_document(conn, doc_id, f"pg-emb-{uuid.uuid4().hex[:8]}")
                _insert_knowledge_revision(conn, rev_id, doc_id)

                embedding = [0.1, 0.2, -0.3, 0.4, 0.5] * 13  # 65 elements
                conn.execute(
                    text(
                        "INSERT INTO knowledge_chunks "
                        "(id, revision_id, chunk_index, text, text_sha256, "
                        " character_count, token_count, section_path, "
                        " page_start, page_end, sheet_name, row_start, row_end, "
                        " source_locator, embedding, embedding_dimension, "
                        " embedding_version, created_at) "
                        "VALUES (:id, :rid, 0, 'test chunk', 'hash-chunk', "
                        " 11, 2, '', "
                        " 1, 1, NULL, NULL, NULL, "
                        " 'block:0', CAST(:emb AS JSON), 65, "
                        " 'fake-hash-v1', NOW())"
                    ),
                    {
                        "id": chunk_id,
                        "rid": rev_id,
                        "emb": json.dumps(embedding),
                    },
                )
                conn.commit()

                row = conn.execute(
                    text("SELECT embedding FROM knowledge_chunks WHERE id = :id"),
                    {"id": chunk_id},
                ).scalar()
                assert row is not None
                assert len(row) == 65
                assert row[0] == 0.1
                assert row[2] == -0.3
        finally:
            with pg_engine.connect() as conn:
                _cleanup_knowledge(conn, doc_id)
                conn.commit()

    def test_jsonb_embedding_round_trip_pg(self, pg_engine) -> None:
        """Embedding JSONB round-trip preserves all values."""
        doc_id = str(uuid.uuid4())
        rev_id = str(uuid.uuid4())
        chunk_id = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_knowledge_document(conn, doc_id, f"pg-rt-{uuid.uuid4().hex[:8]}")
                _insert_knowledge_revision(conn, rev_id, doc_id)

                embedding = [float(i) / 100.0 for i in range(-50, 50)]  # 100 values
                conn.execute(
                    text(
                        "INSERT INTO knowledge_chunks "
                        "(id, revision_id, chunk_index, text, text_sha256, "
                        " character_count, token_count, section_path, "
                        " page_start, page_end, sheet_name, row_start, row_end, "
                        " source_locator, embedding, embedding_dimension, "
                        " embedding_version, created_at) "
                        "VALUES (:id, :rid, 0, 'round trip test', 'hash-rt', "
                        " 15, 3, '', "
                        " NULL, NULL, NULL, NULL, NULL, "
                        " 'block:0', CAST(:emb AS JSON), 100, "
                        " 'fake-hash-v1', NOW())"
                    ),
                    {
                        "id": chunk_id,
                        "rid": rev_id,
                        "emb": json.dumps(embedding),
                    },
                )
                conn.commit()

                row = conn.execute(
                    text("SELECT embedding FROM knowledge_chunks WHERE id = :id"),
                    {"id": chunk_id},
                ).scalar()
                assert row is not None
                assert len(row) == 100
                for i, expected in enumerate(embedding):
                    assert row[i] == pytest.approx(expected, abs=1e-10)
        finally:
            with pg_engine.connect() as conn:
                _cleanup_knowledge(conn, doc_id)
                conn.commit()


# ---------------------------------------------------------------------------
# 8. Long text chunk storage
# ---------------------------------------------------------------------------


class TestKnowledgeLongText:
    def test_long_text_chunk(self, pg_engine) -> None:
        """Large text (100KB) is stored and retrieved correctly."""
        doc_id = str(uuid.uuid4())
        rev_id = str(uuid.uuid4())
        chunk_id = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_knowledge_document(conn, doc_id, f"pg-long-{uuid.uuid4().hex[:8]}")
                _insert_knowledge_revision(conn, rev_id, doc_id)

                long_text = "A" * 100_000  # 100KB
                conn.execute(
                    text(
                        "INSERT INTO knowledge_chunks "
                        "(id, revision_id, chunk_index, text, text_sha256, "
                        " character_count, token_count, section_path, "
                        " page_start, page_end, sheet_name, row_start, row_end, "
                        " source_locator, embedding, embedding_dimension, "
                        " embedding_version, created_at) "
                        "VALUES (:id, :rid, 0, :text, 'hash-long', "
                        " :char_count, 1, '', "
                        " NULL, NULL, NULL, NULL, NULL, "
                        " 'block:0', CAST('[]' AS JSON), 0, "
                        " 'fake-hash-v1', NOW())"
                    ),
                    {
                        "id": chunk_id,
                        "rid": rev_id,
                        "text": long_text,
                        "char_count": len(long_text),
                    },
                )
                conn.commit()

                row = conn.execute(
                    text("SELECT text, character_count FROM knowledge_chunks WHERE id = :id"),
                    {"id": chunk_id},
                ).fetchone()
                assert row is not None
                assert len(row[0]) == 100_000
                assert row[1] == 100_000
        finally:
            with pg_engine.connect() as conn:
                _cleanup_knowledge(conn, doc_id)
                conn.commit()


# ---------------------------------------------------------------------------
# 9-10. Foreign key constraint tests
# ---------------------------------------------------------------------------


class TestKnowledgeForeignKeys:
    def test_document_revision_fk(self, pg_engine) -> None:
        """Revision with invalid document_id raises IntegrityError."""
        fake_doc_id = str(uuid.uuid4())
        rev_id = str(uuid.uuid4())
        with pg_engine.connect() as conn:
            with pytest.raises(IntegrityError):
                _insert_knowledge_revision(conn, rev_id, fake_doc_id)
                conn.commit()
            conn.rollback()

    def test_revision_chunk_fk(self, pg_engine) -> None:
        """Chunk with invalid revision_id raises IntegrityError."""
        fake_rev_id = str(uuid.uuid4())
        chunk_id = str(uuid.uuid4())
        with pg_engine.connect() as conn:
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO knowledge_chunks "
                        "(id, revision_id, chunk_index, text, text_sha256, "
                        " character_count, token_count, section_path, "
                        " page_start, page_end, sheet_name, row_start, row_end, "
                        " source_locator, embedding, embedding_dimension, "
                        " embedding_version, created_at) "
                        "VALUES (:id, :rid, 0, 'orphan', 'hash', "
                        " 6, 1, '', "
                        " NULL, NULL, NULL, NULL, NULL, "
                        " 'block:0', CAST('[]' AS JSON), 0, "
                        " 'v', NOW())"
                    ),
                    {"id": chunk_id, "rid": fake_rev_id},
                )
                conn.commit()
            conn.rollback()


# ---------------------------------------------------------------------------
# 11-13. Unique constraint tests
# ---------------------------------------------------------------------------


class TestKnowledgeUniqueConstraints:
    def test_unique_document_code_pg(self, pg_engine) -> None:
        """Duplicate document code raises IntegrityError."""
        code = f"pg-uq-{uuid.uuid4().hex[:8]}"
        doc_id_1 = str(uuid.uuid4())
        doc_id_2 = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_knowledge_document(conn, doc_id_1, code)
                conn.commit()

                with pytest.raises(IntegrityError):
                    _insert_knowledge_document(conn, doc_id_2, code)
                    conn.commit()
                conn.rollback()
        finally:
            with pg_engine.connect() as conn:
                _cleanup_knowledge(conn, doc_id_1)
                conn.commit()

    def test_unique_revision_number_pg(self, pg_engine) -> None:
        """Duplicate (document_id, revision_number) raises IntegrityError."""
        doc_id = str(uuid.uuid4())
        rev_id_1 = str(uuid.uuid4())
        rev_id_2 = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_knowledge_document(conn, doc_id, f"pg-uqr-{uuid.uuid4().hex[:8]}")
                _insert_knowledge_revision(conn, rev_id_1, doc_id, rev_num=1, content_hash="hash1")
                conn.commit()

                with pytest.raises(IntegrityError):
                    _insert_knowledge_revision(
                        conn, rev_id_2, doc_id, rev_num=1, content_hash="hash2"
                    )
                    conn.commit()
                conn.rollback()
        finally:
            with pg_engine.connect() as conn:
                _cleanup_knowledge(conn, doc_id)
                conn.commit()

    def test_unique_content_hash_pg(self, pg_engine) -> None:
        """Duplicate (document_id, content_sha256) raises IntegrityError."""
        doc_id = str(uuid.uuid4())
        rev_id_1 = str(uuid.uuid4())
        rev_id_2 = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_knowledge_document(conn, doc_id, f"pg-uqh-{uuid.uuid4().hex[:8]}")
                _insert_knowledge_revision(
                    conn, rev_id_1, doc_id, rev_num=1, content_hash="dup-hash"
                )
                conn.commit()

                with pytest.raises(IntegrityError):
                    _insert_knowledge_revision(
                        conn, rev_id_2, doc_id, rev_num=2, content_hash="dup-hash"
                    )
                    conn.commit()
                conn.rollback()
        finally:
            with pg_engine.connect() as conn:
                _cleanup_knowledge(conn, doc_id)
                conn.commit()


# ---------------------------------------------------------------------------
# 14-15. Transaction tests
# ---------------------------------------------------------------------------


class TestKnowledgeTransactions:
    def test_transaction_rollback(self, pg_engine) -> None:
        """Rolled-back document data must not persist."""
        doc_id = str(uuid.uuid4())
        code = f"pg-rb-{uuid.uuid4().hex[:8]}"

        with pg_engine.connect() as conn:
            _insert_knowledge_document(conn, doc_id, code)
            conn.rollback()

        with pg_engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM knowledge_documents WHERE id = :id"),
                {"id": doc_id},
            ).scalar()
            assert count == 0, f"Rolled-back document still exists (count={count})"

    def test_chunk_batch_atomicity(self, pg_engine) -> None:
        """All chunks are inserted atomically — if one fails, none persist."""
        doc_id = str(uuid.uuid4())
        rev_id = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_knowledge_document(conn, doc_id, f"pg-atom-{uuid.uuid4().hex[:8]}")
                _insert_knowledge_revision(conn, rev_id, doc_id)
                conn.commit()

                # Try to insert 3 good chunks + 1 with invalid revision_id
                with pytest.raises(IntegrityError):
                    for i in range(3):
                        chunk_id = str(uuid.uuid4())
                        conn.execute(
                            text(
                                "INSERT INTO knowledge_chunks "
                                "(id, revision_id, chunk_index, text, text_sha256, "
                                " character_count, token_count, section_path, "
                                " page_start, page_end, sheet_name, row_start, row_end, "
                                " source_locator, embedding, embedding_dimension, "
                                " embedding_version, created_at) "
                                "VALUES (:id, :rid, :idx, :text, :hash, "
                                " :char_count, 1, '', "
                                " NULL, NULL, NULL, NULL, NULL, "
                                " 'block:0', CAST('[]' AS JSON), 0, "
                                " 'v', NOW())"
                            ),
                            {
                                "id": chunk_id,
                                "rid": rev_id,
                                "idx": i,
                                "text": f"chunk {i}",
                                "hash": f"hash-{i}",
                                "char_count": len(f"chunk {i}"),
                            },
                        )
                    # This one fails
                    conn.execute(
                        text(
                            "INSERT INTO knowledge_chunks "
                            "(id, revision_id, chunk_index, text, text_sha256, "
                            " character_count, token_count, section_path, "
                            " page_start, page_end, sheet_name, row_start, row_end, "
                            " source_locator, embedding, embedding_dimension, "
                            " embedding_version, created_at) "
                            "VALUES (:id, :rid, 3, 'fail', 'hash-fail', "
                            " 4, 1, '', "
                            " NULL, NULL, NULL, NULL, NULL, "
                            " 'block:3', CAST('[]' AS JSON), 0, "
                            " 'v', NOW())"
                        ),
                        {"id": str(uuid.uuid4()), "rid": "nonexistent-rev"},
                    )
                    conn.commit()
                conn.rollback()

                # Verify no chunks persisted
                count = conn.execute(
                    text("SELECT COUNT(*) FROM knowledge_chunks WHERE revision_id = :rid"),
                    {"rid": rev_id},
                ).scalar()
                assert count == 0, f"Expected 0 chunks after rollback, got {count}"
        finally:
            with pg_engine.connect() as conn:
                _cleanup_knowledge(conn, doc_id)
                conn.commit()


# ---------------------------------------------------------------------------
# 16-17. Review status and immutability tests
# ---------------------------------------------------------------------------


class TestKnowledgeReviewStatus:
    def test_review_status_persistence(self, pg_engine) -> None:
        """Review status changes persist correctly."""
        doc_id = str(uuid.uuid4())
        rev_id = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_knowledge_document(conn, doc_id, f"pg-rev-{uuid.uuid4().hex[:8]}")
                _insert_knowledge_revision(conn, rev_id, doc_id)
                conn.commit()

                # Update review status
                conn.execute(
                    text(
                        "UPDATE knowledge_revisions SET review_status = :status, "
                        " indexed_at = NOW() WHERE id = :id"
                    ),
                    {"id": rev_id, "status": "reviewed"},
                )
                conn.commit()

                row = conn.execute(
                    text(
                        "SELECT review_status, indexed_at FROM knowledge_revisions WHERE id = :id"
                    ),
                    {"id": rev_id},
                ).fetchone()
                assert row is not None
                assert row[0] == "reviewed"
                assert row[1] is not None
        finally:
            with pg_engine.connect() as conn:
                _cleanup_knowledge(conn, doc_id)
                conn.commit()

    def test_approved_immutable_pg(self, pg_engine) -> None:
        """Domain rule: approved revision cannot be modified."""
        doc_id = str(uuid.uuid4())
        rev_id = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_knowledge_document(conn, doc_id, f"pg-imm-{uuid.uuid4().hex[:8]}")
                _insert_knowledge_revision(conn, rev_id, doc_id)
                conn.execute(
                    text(
                        "UPDATE knowledge_revisions SET review_status = 'approved', "
                        " approved_at = NOW() WHERE id = :id"
                    ),
                    {"id": rev_id},
                )
                conn.commit()

            # Domain-level immutability check
            with pytest.raises(ApprovedRevisionImmutabilityError):
                assert_not_approved("approved")
        finally:
            with pg_engine.connect() as conn:
                _cleanup_knowledge(conn, doc_id)
                conn.commit()


# -----------------------------------------------------------------------
# 18. JSONB column type verification
# -----------------------------------------------------------------------


class TestJsonbColumnTypes:
    def test_jsonb_column_type(self, pg_engine) -> None:
        """Verify JSONB column types for metadata, warnings, and embedding columns."""
        with pg_engine.connect() as conn:
            # knowledge_revisions: metadata_snapshot and warning_messages
            result = conn.execute(
                text(
                    "SELECT column_name, udt_name "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'knowledge_revisions' "
                    "AND column_name IN ('metadata_snapshot', 'warning_messages')"
                )
            )
            rows = {row[0]: row[1] for row in result.fetchall()}
            assert rows.get("metadata_snapshot") == "jsonb", (
                f"Expected jsonb for metadata_snapshot, got {rows.get('metadata_snapshot')}"
            )
            assert rows.get("warning_messages") == "jsonb", (
                f"Expected jsonb for warning_messages, got {rows.get('warning_messages')}"
            )

            # knowledge_chunks: embedding
            result = conn.execute(
                text(
                    "SELECT column_name, udt_name "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'knowledge_chunks' "
                    "AND column_name = 'embedding'"
                )
            )
            row = result.fetchone()
            assert row is not None, "embedding column not found in knowledge_chunks"
            assert row[1] == "jsonb", (
                f"Expected jsonb for embedding, got {row[1]}"
            )

            # knowledge_ingestion_runs: input_snapshot and result_snapshot
            result = conn.execute(
                text(
                    "SELECT column_name, udt_name "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'knowledge_ingestion_runs' "
                    "AND column_name IN ('input_snapshot', 'result_snapshot')"
                )
            )
            rows = {row[0]: row[1] for row in result.fetchall()}
            assert rows.get("input_snapshot") == "jsonb", (
                f"Expected jsonb for input_snapshot, got {rows.get('input_snapshot')}"
            )
            assert rows.get("result_snapshot") == "jsonb", (
                f"Expected jsonb for result_snapshot, got {rows.get('result_snapshot')}"
            )
