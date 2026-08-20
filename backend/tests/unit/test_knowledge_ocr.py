"""Unit and persistence-facing contract tests for local OCR provenance."""

from __future__ import annotations

import base64
import hashlib
import io
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# Importing the project/coefficient ORM modules registers the complete Base
# metadata graph used by the repository's SQLite test harness.
from cold_storage.modules.coefficients.infrastructure import orm as _coefficient_orm  # noqa: F401
from cold_storage.modules.knowledge.application.service import KnowledgeService
from cold_storage.modules.knowledge.domain.errors import ApprovedRevisionImmutabilityError
from cold_storage.modules.knowledge.domain.models import (
    make_source_page_evidence_id,
)
from cold_storage.modules.knowledge.infrastructure.ocr_adapter import (
    OcrAdapter,
    OcrAdapterError,
    OcrPageResult,
)
from cold_storage.modules.knowledge.infrastructure.orm import (
    KnowledgeChunkRecord,
    KnowledgePageEvidenceRecord,
)
from cold_storage.modules.knowledge.infrastructure.repository import KnowledgeRepository
from cold_storage.modules.projects.infrastructure.orm import Base
from cold_storage.modules.schemes.infrastructure import orm as _scheme_orm  # noqa: F401

_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _pdf_bytes(*pages: tuple[str, str]) -> bytes:
    """Create pages described as (kind, text), without external fixtures."""
    import pymupdf

    doc = pymupdf.open()
    for kind, text in pages:
        page = doc.new_page()
        if kind == "image":
            page.insert_image(page.rect, stream=_ONE_PIXEL_PNG)
        else:
            page.insert_text((72, 72), text)
    content = doc.tobytes()
    doc.close()
    return content


def _mixed_pdf() -> bytes:
    return _pdf_bytes(
        (
            "native",
            "Native page one has enough deterministic text for the parser threshold.",
        ),
        ("image", ""),
    )


class FakeOcrAdapter:
    """Offline deterministic adapter double with exact request recording."""

    def __init__(self, mode: str = "success") -> None:
        self.mode = mode
        self.calls: list[dict[str, object]] = []

    def ocr_pages(self, **kwargs: object) -> list[OcrPageResult]:
        self.calls.append(kwargs)
        pages = kwargs["page_numbers"]
        assert isinstance(pages, list)
        if self.mode == "empty":
            return [OcrPageResult.from_text(page_number=page, text="") for page in pages]
        if self.mode == "failed":
            return [
                OcrPageResult.failure(
                    page_number=page,
                    status="failed",
                    error_code="fake_failure",
                    error_message="offline test failure",
                )
                for page in pages
            ]
        return [
            OcrPageResult.from_text(
                page_number=page,
                text="OCR derived page text with deterministic provenance and review required.",
                confidence=88.5,
                confidence_source="fake_tsv",
            )
            for page in pages
        ]


@pytest.fixture()
def session(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setenv("KNOWLEDGE_STORAGE_DIR", str(tmp_path / "knowledge-storage"))
    with Session(engine, expire_on_commit=False) as db_session:
        yield db_session, engine
    engine.dispose()


def _create_revision(service: KnowledgeService, content: bytes) -> dict[str, object]:
    content_hash = hashlib.sha256(content).hexdigest()
    return service.create_document(
        code="OCR-UNIT-001",
        title="OCR Unit Document",
        file=io.BytesIO(content),
        content_sha256=content_hash,
        file_size=len(content),
        filename="ocr-unit.pdf",
        mime_type="application/pdf",
        owner="tester",
    )


class TestOcrAdapter:
    def test_exact_pages_hash_and_confidence(self) -> None:
        content = _mixed_pdf()
        content_hash = hashlib.sha256(content).hexdigest()
        tsv = (
            b"level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\t"
            b"width\theight\tconf\ttext\n"
            b"5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t90.0\tHello\n"
            b"5\t1\t1\t1\t1\t2\t0\t0\t10\t10\t80.0\tworld\n"
        )
        calls: list[list[str]] = []

        def runner(command: list[str], **_: object) -> SimpleNamespace:
            calls.append(command)
            return SimpleNamespace(returncode=0, stdout=tsv, stderr=b"")

        results = OcrAdapter(runner=runner).ocr_pages(
            content=content,
            revision_id="revision-1",
            source_content_sha256=content_hash,
            page_numbers=[2, 1],
        )
        assert [result.page_number for result in results] == [1, 2]
        assert results[0].text == "Hello world"
        assert results[0].confidence == pytest.approx(85.0)
        assert results[0].confidence_source == "tesseract_tsv"
        assert calls and "eng+chi_sim" in calls[0]

    def test_invalid_requests_rejected_before_runner(self) -> None:
        content = _mixed_pdf()
        content_hash = hashlib.sha256(content).hexdigest()
        adapter = OcrAdapter(runner=lambda *_args, **_kwargs: pytest.fail("runner called"))
        for pages in ([], [1, 1], [0], [3]):
            with pytest.raises(OcrAdapterError):
                adapter.ocr_pages(
                    content=content,
                    revision_id="revision-1",
                    source_content_sha256=content_hash,
                    page_numbers=pages,
                )

    def test_hash_mismatch_is_rejected(self) -> None:
        with pytest.raises(OcrAdapterError, match="hash mismatch"):
            OcrAdapter().ocr_pages(
                content=b"immutable source",
                revision_id="revision-1",
                source_content_sha256=hashlib.sha256(b"different source").hexdigest(),
                page_numbers=[1],
            )


class TestPageEvidenceContract:
    def test_stable_revision_page_identity(self) -> None:
        first = make_source_page_evidence_id("revision-1", 3)
        second = make_source_page_evidence_id("revision-1", 3)
        different_page = make_source_page_evidence_id("revision-1", 4)
        assert first == second
        assert first != different_page
        assert first.startswith("spe-")

    def test_mixed_lineage_restart_and_idempotency(self, session) -> None:
        db_session, engine = session
        content = _mixed_pdf()
        content_hash = hashlib.sha256(content).hexdigest()
        adapter = FakeOcrAdapter()
        service = KnowledgeService(db_session, ocr_adapter=adapter)
        created = _create_revision(service, content)

        first = service.ingest_revision(document_id=created["document_id"], revision_number=1)
        assert first["ingestion_status"] == "indexed"
        assert adapter.calls[0]["page_numbers"] == [2]
        assert created["revision_id"]

        repo = KnowledgeRepository(db_session)
        evidence = repo.list_page_evidence(str(created["revision_id"]))
        chunks = repo.get_chunks(str(created["revision_id"]))
        assert [item.page_number for item in evidence] == [1, 2]
        assert evidence[0].extraction_method == "native"
        assert evidence[1].extraction_method == "ocr"
        assert evidence[1].requires_review is True
        assert evidence[1].source_content_sha256 == content_hash
        assert all(chunk.source_page_evidence_id for chunk in chunks)
        assert all(len(chunk.id) == 36 for chunk in chunks)
        assert any(chunk.page_evidence.is_derived_evidence for chunk in chunks)

        search_result = service.search(query="OCR derived", include_unverified=True)
        ocr_results = [item for item in search_result["results"] if item["is_ocr_derived"]]
        assert ocr_results
        assert (
            ocr_results[0]["citation"]["source_page_evidence_id"]
            == evidence[1].source_page_evidence_id
        )
        assert ocr_results[0]["citation"]["content_sha256"] == content_hash

        retry = service.ingest_revision(document_id=created["document_id"], revision_number=1)
        assert retry["chunk_count"] == first["chunk_count"]
        assert len(repo.list_page_evidence(str(created["revision_id"]))) == 2
        assert len(repo.get_chunks(str(created["revision_id"]))) == first["chunk_count"]

        db_session.commit()
        with Session(engine, expire_on_commit=False) as restarted:
            restarted_repo = KnowledgeRepository(restarted)
            readback = restarted_repo.list_page_evidence(str(created["revision_id"]))
            assert readback[1].source_page_evidence_id == evidence[1].source_page_evidence_id
            assert restarted_repo.get_chunks(str(created["revision_id"]))

    @pytest.mark.parametrize("mode", ["empty", "failed"])
    def test_incomplete_ocr_fail_closed_then_retry(self, session, mode: str) -> None:
        db_session, _ = session
        content = _mixed_pdf()
        adapter = FakeOcrAdapter(mode=mode)
        service = KnowledgeService(db_session, ocr_adapter=adapter)
        created = _create_revision(service, content)

        blocked = service.ingest_revision(document_id=created["document_id"], revision_number=1)
        assert blocked["ingestion_status"] == "requires_ocr"
        repo = KnowledgeRepository(db_session)
        assert repo.get_chunks(str(created["revision_id"])) == []
        failed_evidence = repo.list_page_evidence(str(created["revision_id"]))
        assert failed_evidence[1].is_complete is False
        assert failed_evidence[1].requires_review is True

        adapter.mode = "success"
        recovered = service.ingest_revision(document_id=created["document_id"], revision_number=1)
        assert recovered["ingestion_status"] == "indexed"
        assert len(repo.list_page_evidence(str(created["revision_id"]))) == 2
        assert repo.get_chunks(str(created["revision_id"]))

    def test_native_pdf_does_not_invoke_ocr(self, session) -> None:
        db_session, _ = session
        content = _pdf_bytes(
            (
                "native",
                "Native page one has enough deterministic text for this threshold.",
            ),
            (
                "native",
                "Native page two has enough deterministic text for this threshold.",
            ),
        )
        adapter = FakeOcrAdapter()
        service = KnowledgeService(db_session, ocr_adapter=adapter)
        created = _create_revision(service, content)
        result = service.ingest_revision(document_id=created["document_id"], revision_number=1)
        assert result["ingestion_status"] == "indexed"
        assert adapter.calls == []
        evidence = KnowledgeRepository(db_session).list_page_evidence(str(created["revision_id"]))
        assert all(item.extraction_method == "native" for item in evidence)

    def test_approved_revision_cannot_be_reocrated(self, session) -> None:
        db_session, _ = session
        adapter = FakeOcrAdapter()
        service = KnowledgeService(db_session, ocr_adapter=adapter)
        created = _create_revision(service, _mixed_pdf())
        service.ingest_revision(document_id=created["document_id"], revision_number=1)
        service.transition_review_status(
            document_id=created["document_id"], revision_number=1, target_status="reviewed"
        )
        service.transition_review_status(
            document_id=created["document_id"], revision_number=1, target_status="approved"
        )
        with pytest.raises(ApprovedRevisionImmutabilityError):
            service.ingest_revision(document_id=created["document_id"], revision_number=1)
        assert (
            len(
                db_session.query(KnowledgePageEvidenceRecord)
                .filter_by(revision_id=created["revision_id"])
                .all()
            )
            == 2
        )
        assert (
            db_session.query(KnowledgeChunkRecord)
            .filter_by(revision_id=created["revision_id"])
            .count()
            > 0
        )
