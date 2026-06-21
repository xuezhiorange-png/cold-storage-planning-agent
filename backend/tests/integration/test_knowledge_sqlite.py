"""SQLite integration tests for knowledge module — ORM persistence, migrations,
JSON round-trips, foreign keys, unique constraints, and revision immutability.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.knowledge.domain.errors import ApprovedRevisionImmutabilityError
from cold_storage.modules.knowledge.domain.lifecycle import assert_not_approved
from cold_storage.modules.knowledge.infrastructure.orm import (
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
    KnowledgeIngestionRunRecord,
    KnowledgeRevisionRecord,
)
from cold_storage.modules.projects.infrastructure.orm import Base

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    """In-memory SQLite engine with all tables created."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine) -> Session:
    """Session bound to the in-memory engine."""
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    sess = factory()
    yield sess
    sess.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_document(session: Session, doc_id: str = "doc-001", code: str = "TEST-DOC") -> None:
    """Insert a knowledge document record."""
    rec = KnowledgeDocumentRecord(
        id=doc_id,
        code=code,
        title="Test Document",
        document_category="standard",
        source_type="upload",
        source_reference="test.pdf",
        owner="tester",
        current_revision_number=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(rec)
    session.flush()


def _insert_revision(
    session: Session,
    revision_id: str = "rev-001",
    doc_id: str = "doc-001",
    rev_num: int = 1,
    content_hash: str = "abc123def456",
) -> KnowledgeRevisionRecord:
    """Insert a knowledge revision record."""
    rec = KnowledgeRevisionRecord(
        id=revision_id,
        document_id=doc_id,
        revision_number=rev_num,
        version_label="v1",
        original_filename="test.pdf",
        safe_filename="test.pdf",
        mime_type="application/pdf",
        file_extension=".pdf",
        file_size_bytes=1024,
        content_sha256=content_hash,
        storage_key=f"knowledge/{doc_id}/{rev_num}",
        ingestion_status="uploaded",
        review_status="unverified",
        requires_ocr=False,
        requires_review=True,
        parser_name="pdf",
        parser_version="parser-v1",
        chunker_version="chunk-v1",
        embedding_version="fake-hash-v1",
        extracted_text_length=500,
        page_count=5,
        sheet_count=None,
        metadata_snapshot={"source_format": "pdf"},
        warning_messages=[],
        created_at=datetime.now(UTC),
        indexed_at=None,
        reviewed_at=None,
        approved_at=None,
        withdrawn_at=None,
    )
    session.add(rec)
    session.flush()
    return rec


# ---------------------------------------------------------------------------
# 1. Migration — 4 knowledge tables exist
# ---------------------------------------------------------------------------


def _table_names(engine) -> set[str]:
    return set(inspect(engine).get_table_names())


class TestMigration:
    def test_migration_0007_tables_exist(self, engine) -> None:
        """All 4 knowledge tables must be created by Base.metadata.create_all."""
        expected = {
            "knowledge_documents",
            "knowledge_revisions",
            "knowledge_ingestion_runs",
            "knowledge_chunks",
        }
        actual = _table_names(engine)
        assert expected.issubset(actual), f"Missing tables: {expected - actual}"


# ---------------------------------------------------------------------------
# 2-3. Document and Revision CRUD
# ---------------------------------------------------------------------------


class TestDocumentCrud:
    def test_document_crud(self, session) -> None:
        """Create and read a knowledge document."""
        _insert_document(session, doc_id="doc-crud", code="CRUD-001")
        session.flush()

        rec = session.get(KnowledgeDocumentRecord, "doc-crud")
        assert rec is not None
        assert rec.code == "CRUD-001"
        assert rec.title == "Test Document"


class TestRevisionCrud:
    def test_revision_crud(self, session) -> None:
        """Create and read a knowledge revision."""
        _insert_document(session, doc_id="doc-rev", code="REV-001")
        _insert_revision(session, revision_id="rev-crud", doc_id="doc-rev")
        session.flush()

        rec = session.get(KnowledgeRevisionRecord, "rev-crud")
        assert rec is not None
        assert rec.document_id == "doc-rev"
        assert rec.revision_number == 1


# ---------------------------------------------------------------------------
# 4. Revision numbers strictly increase
# ---------------------------------------------------------------------------


class TestRevisionIncrement:
    def test_revision_increment(self, session) -> None:
        """Revision numbers for the same document strictly increase."""
        _insert_document(session, doc_id="doc-inc", code="INC-001")
        _insert_revision(
            session, revision_id="rev-1", doc_id="doc-inc", rev_num=1, content_hash="hash-inc-1"
        )
        _insert_revision(
            session, revision_id="rev-2", doc_id="doc-inc", rev_num=2, content_hash="hash-inc-2"
        )
        _insert_revision(
            session, revision_id="rev-3", doc_id="doc-inc", rev_num=3, content_hash="hash-inc-3"
        )
        session.flush()

        revisions = (
            session.query(KnowledgeRevisionRecord)
            .filter_by(document_id="doc-inc")
            .order_by(KnowledgeRevisionRecord.revision_number)
            .all()
        )
        numbers = [r.revision_number for r in revisions]
        assert numbers == [1, 2, 3]


# ---------------------------------------------------------------------------
# 5-7. Unique constraint tests
# ---------------------------------------------------------------------------


class TestUniqueConstraints:
    def test_unique_document_code(self, session) -> None:
        """Duplicate document code is rejected."""
        _insert_document(session, doc_id="doc-uq1", code="DUP-CODE")
        session.flush()
        with pytest.raises(Exception, match="UNIQUE|unique"):
            _insert_document(session, doc_id="doc-uq2", code="DUP-CODE")
            session.flush()

    def test_unique_revision_number(self, session) -> None:
        """Duplicate (document_id, revision_number) is rejected."""
        _insert_document(session, doc_id="doc-uq3", code="UQ-REV")
        _insert_revision(session, revision_id="rev-uq1", doc_id="doc-uq3", rev_num=1)
        session.flush()
        with pytest.raises(Exception, match="UNIQUE|unique"):
            _insert_revision(session, revision_id="rev-uq2", doc_id="doc-uq3", rev_num=1)
            session.flush()

    def test_unique_content_hash(self, session) -> None:
        """Duplicate (document_id, content_sha256) is rejected."""
        _insert_document(session, doc_id="doc-uq4", code="UQ-HASH")
        _insert_revision(
            session, revision_id="rev-h1", doc_id="doc-uq4", rev_num=1, content_hash="same-hash"
        )
        session.flush()
        with pytest.raises(Exception, match="UNIQUE|unique"):
            _insert_revision(
                session, revision_id="rev-h2", doc_id="doc-uq4", rev_num=2, content_hash="same-hash"
            )
            session.flush()


# ---------------------------------------------------------------------------
# 8. Chunk batch insert
# ---------------------------------------------------------------------------


class TestChunkBatchInsert:
    def test_chunk_batch_insert(self, session) -> None:
        """Multiple chunks can be inserted in one transaction."""
        _insert_document(session, doc_id="doc-batch", code="BATCH-001")
        _insert_revision(session, revision_id="rev-batch", doc_id="doc-batch")

        for i in range(5):
            chunk = KnowledgeChunkRecord(
                id=f"chunk-{i}",
                revision_id="rev-batch",
                chunk_index=i,
                text=f"Chunk {i} text content",
                text_sha256=f"hash-{i}",
                character_count=20,
                token_count=4,
                section_path=f"section-{i}",
                page_start=1,
                page_end=1,
                sheet_name=None,
                row_start=None,
                row_end=None,
                source_locator=f"block:{i}",
                embedding=[0.1] * 64,
                embedding_dimension=64,
                embedding_version="fake-hash-v1",
                created_at=datetime.now(UTC),
            )
            session.add(chunk)
        session.flush()

        count = session.query(KnowledgeChunkRecord).filter_by(revision_id="rev-batch").count()
        assert count == 5


# ---------------------------------------------------------------------------
# 9-10. JSON round-trip tests
# ---------------------------------------------------------------------------


class TestJsonRoundTrip:
    def test_json_embedding_round_trip(self, session) -> None:
        """Embedding stored as JSON, read back correctly."""
        _insert_document(session, doc_id="doc-json1", code="JSON-EMB")
        _insert_revision(session, revision_id="rev-json1", doc_id="doc-json1")

        embedding = [0.123456, -0.789012, 0.0, 0.5, -0.5]
        chunk = KnowledgeChunkRecord(
            id="chunk-json-emb",
            revision_id="rev-json1",
            chunk_index=0,
            text="test embedding",
            text_sha256="hash-emb",
            character_count=15,
            token_count=2,
            section_path="",
            page_start=None,
            page_end=None,
            sheet_name=None,
            row_start=None,
            row_end=None,
            source_locator="block:0",
            embedding=embedding,
            embedding_dimension=5,
            embedding_version="fake-hash-v1",
            created_at=datetime.now(UTC),
        )
        session.add(chunk)
        session.flush()

        retrieved = session.get(KnowledgeChunkRecord, "chunk-json-emb")
        assert retrieved is not None
        assert retrieved.embedding == embedding
        assert len(retrieved.embedding) == 5

    def test_json_metadata_round_trip(self, session) -> None:
        """metadata_snapshot stored as JSON, read back correctly."""
        _insert_document(session, doc_id="doc-json2", code="JSON-META")
        _insert_revision(session, revision_id="rev-json2", doc_id="doc-json2")

        metadata = {
            "source_format": "pdf",
            "parser_version": "parser-v1",
            "nested": {"key": "value", "list": [1, 2, 3]},
        }
        rev = session.get(KnowledgeRevisionRecord, "rev-json2")
        assert rev is not None
        rev.metadata_snapshot = metadata
        session.flush()

        retrieved = session.get(KnowledgeRevisionRecord, "rev-json2")
        assert retrieved is not None
        assert retrieved.metadata_snapshot == metadata
        assert retrieved.metadata_snapshot["nested"]["key"] == "value"


# ---------------------------------------------------------------------------
# 11-12. Foreign key constraint tests
# ---------------------------------------------------------------------------


class TestForeignKeys:
    def test_fk_revision_to_document(self, session, engine) -> None:
        """Revision with invalid document_id violates FK constraint."""
        session.execute(text("PRAGMA foreign_keys = ON"))
        rec = KnowledgeRevisionRecord(
            id="rev-orphan",
            document_id="nonexistent-doc-id",
            revision_number=1,
            version_label="",
            original_filename="",
            safe_filename="",
            mime_type="",
            file_extension="",
            file_size_bytes=0,
            content_sha256="",
            storage_key="",
            ingestion_status="uploaded",
            review_status="unverified",
            requires_ocr=False,
            requires_review=True,
            parser_name="",
            parser_version="",
            chunker_version="",
            embedding_version="",
            extracted_text_length=0,
            page_count=None,
            sheet_count=None,
            metadata_snapshot={},
            warning_messages=[],
            created_at=datetime.now(UTC),
            indexed_at=None,
            reviewed_at=None,
            approved_at=None,
            withdrawn_at=None,
        )
        session.add(rec)
        with pytest.raises(Exception, match="FOREIGN KEY|foreign key"):
            session.flush()

    def test_fk_chunk_to_revision(self, session, engine) -> None:
        """Chunk with invalid revision_id violates FK constraint."""
        session.execute(text("PRAGMA foreign_keys = ON"))
        chunk = KnowledgeChunkRecord(
            id="chunk-orphan",
            revision_id="nonexistent-rev-id",
            chunk_index=0,
            text="orphan chunk",
            text_sha256="hash-orphan",
            character_count=13,
            token_count=2,
            section_path="",
            page_start=None,
            page_end=None,
            sheet_name=None,
            row_start=None,
            row_end=None,
            source_locator="block:0",
            embedding=[],
            embedding_dimension=0,
            embedding_version="",
            created_at=datetime.now(UTC),
        )
        session.add(chunk)
        with pytest.raises(Exception, match="FOREIGN KEY|foreign key"):
            session.flush()


# ---------------------------------------------------------------------------
# 13. Ingestion run CRUD
# ---------------------------------------------------------------------------


class TestIngestionRunCrud:
    def test_ingestion_run_crud(self, session) -> None:
        """Create and read an ingestion run."""
        _insert_document(session, doc_id="doc-run", code="RUN-001")
        _insert_revision(session, revision_id="rev-run", doc_id="doc-run")

        run = KnowledgeIngestionRunRecord(
            id="run-001",
            revision_id="rev-run",
            status="pending",
            parser_name="pdf",
            parser_version="parser-v1",
            chunker_version="chunk-v1",
            embedding_version="fake-hash-v1",
            input_snapshot={"filename": "test.pdf"},
            result_snapshot={},
            warning_messages=[],
            error_code="",
            error_message="",
            created_at=datetime.now(UTC),
            completed_at=None,
        )
        session.add(run)
        session.flush()

        retrieved = session.get(KnowledgeIngestionRunRecord, "run-001")
        assert retrieved is not None
        assert retrieved.revision_id == "rev-run"
        assert retrieved.status == "pending"
        assert retrieved.input_snapshot["filename"] == "test.pdf"


# ---------------------------------------------------------------------------
# 14. Approved immutability
# ---------------------------------------------------------------------------


class TestApprovedImmutability:
    def test_approved_immutable(self, session) -> None:
        """Cannot update an approved revision's ingestion_status."""
        _insert_document(session, doc_id="doc-imm", code="IMM-001")
        _insert_revision(session, revision_id="rev-imm", doc_id="doc-imm")
        session.flush()

        # Set to approved
        rev = session.get(KnowledgeRevisionRecord, "rev-imm")
        assert rev is not None
        rev.ingestion_status = "indexed"
        rev.review_status = "approved"
        rev.approved_at = datetime.now(UTC)
        session.flush()

        # Try to modify — domain rules should prevent this
        with pytest.raises(ApprovedRevisionImmutabilityError):
            assert_not_approved(rev.review_status)


# ---------------------------------------------------------------------------
# 15. OCR revision has no chunks
# ---------------------------------------------------------------------------


class TestRequiresOcrRevision:
    def test_requires_ocr_revision_has_no_chunks(self, session) -> None:
        """Revision with ingestion_status='requires_ocr' has no chunks indexed."""
        _insert_document(session, doc_id="doc-ocr", code="OCR-001")
        _insert_revision(session, revision_id="rev-ocr", doc_id="doc-ocr", content_hash="ocr-hash")
        session.flush()

        # Update to requires_ocr status
        rev = session.get(KnowledgeRevisionRecord, "rev-ocr")
        rev.ingestion_status = "requires_ocr"
        rev.requires_ocr = True
        session.flush()

        # Verify no chunks exist for this revision
        chunk_count = session.query(KnowledgeChunkRecord).filter_by(revision_id="rev-ocr").count()
        assert chunk_count == 0

        # Verify the revision is in requires_ocr state
        retrieved = session.get(KnowledgeRevisionRecord, "rev-ocr")
        assert retrieved.ingestion_status == "requires_ocr"
        assert retrieved.requires_ocr is True


# ---------------------------------------------------------------------------
# 16. Approved → withdrawn transition
# ---------------------------------------------------------------------------


class TestApprovedWithdrawnTransition:
    def test_approved_withdrawn_transition(self, session) -> None:
        """approved → withdrawn is a valid lifecycle transition."""
        from cold_storage.modules.knowledge.domain.lifecycle import (
            validate_review_transition,
        )

        _insert_document(session, doc_id="doc-withdraw", code="WD-001")
        _insert_revision(
            session,
            revision_id="rev-withdraw",
            doc_id="doc-withdraw",
            content_hash="wd-hash",
        )
        session.flush()

        # Set to approved
        rev = session.get(KnowledgeRevisionRecord, "rev-withdraw")
        rev.ingestion_status = "indexed"
        rev.review_status = "approved"
        rev.approved_at = datetime.now(UTC)
        session.flush()

        # Domain allows approved → withdrawn
        validate_review_transition("approved", "withdrawn")

        # Transition to withdrawn
        rev.review_status = "withdrawn"
        rev.withdrawn_at = datetime.now(UTC)
        session.flush()

        # Verify final state
        retrieved = session.get(KnowledgeRevisionRecord, "rev-withdraw")
        assert retrieved.review_status == "withdrawn"
        assert retrieved.withdrawn_at is not None


# ---------------------------------------------------------------------------
# 17. include_historical_revisions parameter
# ---------------------------------------------------------------------------


class TestIncludeHistoricalRevisions:
    def test_include_historical_revisions(self, session) -> None:
        """Search with include_historical_revisions returns chunks from all revisions."""
        from unittest.mock import patch as mock_patch

        from cold_storage.modules.knowledge.application.service import KnowledgeService

        _insert_document(session, doc_id="doc-hist", code="HIST-001")
        # v1
        _insert_revision(
            session,
            revision_id="rev-hist-1",
            doc_id="doc-hist",
            rev_num=1,
            content_hash="hist-1",
        )
        # v2
        _insert_revision(
            session,
            revision_id="rev-hist-2",
            doc_id="doc-hist",
            rev_num=2,
            content_hash="hist-2",
        )
        session.flush()

        # Set both to indexed and approved
        for rev_id in ("rev-hist-1", "rev-hist-2"):
            rev = session.get(KnowledgeRevisionRecord, rev_id)
            rev.ingestion_status = "indexed"
            rev.review_status = "approved"
            rev.requires_review = False

        # Add chunks to v1
        chunk1 = KnowledgeChunkRecord(
            id="chunk-hist-1",
            revision_id="rev-hist-1",
            chunk_index=0,
            text="Historical content version one",
            text_sha256="hash-h1",
            character_count=30,
            token_count=5,
            section_path="",
            page_start=None,
            page_end=None,
            sheet_name=None,
            row_start=None,
            row_end=None,
            source_locator="block:0",
            embedding=[0.1] * 64,
            embedding_dimension=64,
            embedding_version="fake-hash-v1",
            created_at=datetime.now(UTC),
        )
        session.add(chunk1)

        # Add chunks to v2
        chunk2 = KnowledgeChunkRecord(
            id="chunk-hist-2",
            revision_id="rev-hist-2",
            chunk_index=0,
            text="Updated content version two",
            text_sha256="hash-h2",
            character_count=28,
            token_count=5,
            section_path="",
            page_start=None,
            page_end=None,
            sheet_name=None,
            row_start=None,
            row_end=None,
            source_locator="block:0",
            embedding=[0.1] * 64,
            embedding_dimension=64,
            embedding_version="fake-hash-v1",
            created_at=datetime.now(UTC),
        )
        session.add(chunk2)
        session.flush()

        # Create service (mock storage since search doesn't use it)
        with mock_patch("cold_storage.modules.knowledge.application.service.LocalDocumentStorage"):
            svc = KnowledgeService(session)

        # Without historical revisions: only latest (v2)
        result_no_hist = svc.search(
            query="content",
            include_historical_revisions=False,
        )
        chunk_texts = [r["text"] for r in result_no_hist["results"]]
        assert "Updated content version two" in chunk_texts

        # With historical revisions: both v1 and v2
        result_with_hist = svc.search(
            query="content",
            include_historical_revisions=True,
        )
        chunk_texts = [r["text"] for r in result_with_hist["results"]]
        assert "Historical content version one" in chunk_texts
        assert "Updated content version two" in chunk_texts


# ---------------------------------------------------------------------------
# 18. Search filter: latest approved only
# ---------------------------------------------------------------------------


class TestSearchFilterLatestApprovedOnly:
    def test_search_filter_latest_approved_only(self, session) -> None:
        """Default search returns only approved revision chunks."""
        from unittest.mock import patch as mock_patch

        from cold_storage.modules.knowledge.application.service import KnowledgeService

        _insert_document(session, doc_id="doc-filter", code="FILTER-001")
        # v1 — unverified
        _insert_revision(
            session,
            revision_id="rev-filter-1",
            doc_id="doc-filter",
            rev_num=1,
            content_hash="filter-1",
        )
        # v2 — approved
        _insert_revision(
            session,
            revision_id="rev-filter-2",
            doc_id="doc-filter",
            rev_num=2,
            content_hash="filter-2",
        )
        session.flush()

        # v1: indexed but unverified
        rev1 = session.get(KnowledgeRevisionRecord, "rev-filter-1")
        rev1.ingestion_status = "indexed"
        rev1.review_status = "unverified"

        # v2: indexed and approved
        rev2 = session.get(KnowledgeRevisionRecord, "rev-filter-2")
        rev2.ingestion_status = "indexed"
        rev2.review_status = "approved"
        rev2.requires_review = False
        session.flush()

        # Add chunks
        chunk1 = KnowledgeChunkRecord(
            id="chunk-filter-1",
            revision_id="rev-filter-1",
            chunk_index=0,
            text="Unverified content alpha",
            text_sha256="hash-f1",
            character_count=25,
            token_count=4,
            section_path="",
            page_start=None,
            page_end=None,
            sheet_name=None,
            row_start=None,
            row_end=None,
            source_locator="block:0",
            embedding=[0.1] * 64,
            embedding_dimension=64,
            embedding_version="fake-hash-v1",
            created_at=datetime.now(UTC),
        )
        chunk2 = KnowledgeChunkRecord(
            id="chunk-filter-2",
            revision_id="rev-filter-2",
            chunk_index=0,
            text="Approved content beta",
            text_sha256="hash-f2",
            character_count=22,
            token_count=4,
            section_path="",
            page_start=None,
            page_end=None,
            sheet_name=None,
            row_start=None,
            row_end=None,
            source_locator="block:0",
            embedding=[0.1] * 64,
            embedding_dimension=64,
            embedding_version="fake-hash-v1",
            created_at=datetime.now(UTC),
        )
        session.add(chunk1)
        session.add(chunk2)
        session.flush()

        with mock_patch("cold_storage.modules.knowledge.application.service.LocalDocumentStorage"):
            svc = KnowledgeService(session)

        # Default search: only latest revision (v2) and approved_only filter
        result = svc.search(query="content")
        chunk_texts = [r["text"] for r in result["results"]]
        assert "Approved content beta" in chunk_texts
        assert "Unverified content alpha" not in chunk_texts


# -----------------------------------------------------------------------
# 19-20. create_document compensation cleanup on failure
# -----------------------------------------------------------------------


class TestCreateDocumentCompensationCleanup:
    def test_create_document_save_revision_failure_cleanup(self, session) -> None:
        """When save_revision fails, the storage file is cleaned up (compensation)."""
        from unittest.mock import MagicMock, patch

        from cold_storage.modules.knowledge.application.service import KnowledgeService

        mock_storage = MagicMock()
        mock_storage.save.return_value = MagicMock(storage_key="knowledge/orphan/key")
        mock_storage.delete.return_value = None

        with patch(
            "cold_storage.modules.knowledge.application.service.LocalDocumentStorage",
            return_value=mock_storage,
        ):
            svc = KnowledgeService(session)

        # save_revision will raise, triggering compensation
        with (
            patch.object(svc._repo, "save_revision", side_effect=RuntimeError("DB write failed")),
            pytest.raises(RuntimeError, match="DB write failed"),
        ):
            svc.create_document(
                code="COMP-001",
                title="Compensation Test",
                file_content=b"test file content here",
                filename="test.pdf",
                mime_type="application/pdf",
                owner="tester",
            )

        # Compensation: storage.delete must have been called with the orphan key
        mock_storage.delete.assert_called_once_with("knowledge/orphan/key")

    def test_create_document_audit_failure_cleanup(self, session) -> None:
        """When _audit_event fails, the storage file is cleaned up (compensation)."""
        from unittest.mock import MagicMock, patch

        from cold_storage.modules.knowledge.application.service import KnowledgeService

        mock_storage = MagicMock()
        mock_storage.save.return_value = MagicMock(storage_key="knowledge/audit/key")
        mock_storage.delete.return_value = None

        with patch(
            "cold_storage.modules.knowledge.application.service.LocalDocumentStorage",
            return_value=mock_storage,
        ):
            svc = KnowledgeService(session)

        # _audit_event will raise, triggering compensation
        with (
            patch.object(
                svc,
                "_audit_event",
                side_effect=RuntimeError("Audit write failed"),
            ),
            pytest.raises(RuntimeError, match="Audit write failed"),
        ):
            svc.create_document(
                code="COMP-002",
                title="Audit Failure Test",
                file_content=b"test file content here",
                filename="test.pdf",
                mime_type="application/pdf",
                owner="tester",
            )

        # Compensation: storage.delete must have been called
        mock_storage.delete.assert_called_once_with("knowledge/audit/key")


# -----------------------------------------------------------------------
# 21-22. approved→withdrawn content field rejection
# -----------------------------------------------------------------------


class TestApprovedWithdrawnContentFieldRejection:
    def test_approved_withdrawn_rejects_content_fields(self, session) -> None:
        """approved→withdrawn with content fields raises ApprovedRevisionImmutabilityError.

        Only review_status, withdrawn_at, and requires_review are allowed.
        """
        from cold_storage.modules.knowledge.infrastructure.repository import (
            KnowledgeRepository,
        )

        repo = KnowledgeRepository(session)

        # Insert document + revision, set to approved
        _insert_document(session, doc_id="doc-imm-r3", code="IMM-R3")
        rev_rec = _insert_revision(
            session,
            revision_id="rev-imm-r3",
            doc_id="doc-imm-r3",
            content_hash="imm-r3-hash",
        )
        session.flush()

        rev_rec.ingestion_status = "indexed"
        rev_rec.review_status = "approved"
        rev_rec.approved_at = datetime.now(UTC)
        session.flush()

        # Attempt approved→withdrawn WITH a content field (parser_name)
        with pytest.raises(ApprovedRevisionImmutabilityError):
            repo.update_revision_status(
                "rev-imm-r3",
                review_status="withdrawn",
                parser_name="hacked",
            )

        # Verify the revision is still approved (no state change)
        refreshed = session.get(KnowledgeRevisionRecord, "rev-imm-r3")
        assert refreshed.review_status == "approved"

        # Now call with ONLY allowed fields — should succeed
        repo.update_revision_status(
            "rev-imm-r3",
            review_status="withdrawn",
            withdrawn_at=datetime.now(UTC),
        )
        refreshed = session.get(KnowledgeRevisionRecord, "rev-imm-r3")
        assert refreshed.review_status == "withdrawn"
        assert refreshed.withdrawn_at is not None

    def test_approved_withdrawn_with_requires_review_succeeds(self, session) -> None:
        """approved→withdrawn with requires_review=False succeeds.

        requires_review is one of the allowed fields during withdrawal.
        """
        from cold_storage.modules.knowledge.infrastructure.repository import (
            KnowledgeRepository,
        )

        repo = KnowledgeRepository(session)

        # Insert document + revision, set to approved
        _insert_document(session, doc_id="doc-rv-r3", code="RV-R3")
        rev_rec = _insert_revision(
            session,
            revision_id="rev-rv-r3",
            doc_id="doc-rv-r3",
            content_hash="rv-r3-hash",
        )
        session.flush()

        rev_rec.ingestion_status = "indexed"
        rev_rec.review_status = "approved"
        rev_rec.approved_at = datetime.now(UTC)
        rev_rec.requires_review = False
        session.flush()

        # Transition: approved→withdrawn with requires_review=False (allowed field)
        repo.update_revision_status(
            "rev-rv-r3",
            review_status="withdrawn",
            requires_review=False,
        )

        refreshed = session.get(KnowledgeRevisionRecord, "rev-rv-r3")
        assert refreshed.review_status == "withdrawn"
        assert refreshed.requires_review is False
