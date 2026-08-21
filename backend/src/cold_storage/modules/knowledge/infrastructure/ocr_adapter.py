"""Local, offline Tesseract OCR adapter for selected PDF pages."""

from __future__ import annotations

import hashlib
import re
import subprocess
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pymupdf

from cold_storage.modules.knowledge.domain.models import make_source_page_evidence_id

DEFAULT_OCR_LANGUAGES = "eng+chi_sim"
DEFAULT_OCR_ENGINE = "tesseract"
_CANONICAL_STATUSES = frozenset({"completed", "requires_ocr", "unavailable", "empty", "failed"})


class OcrAdapterError(RuntimeError):
    """Raised when an OCR request is invalid or the source cannot be read."""


@dataclass(frozen=True)
class OcrPageResult:
    """Complete structured evidence for exactly one 1-based source page."""

    source_page_evidence_id: str = ""
    document_id: str = ""
    revision_id: str = ""
    page_number: int = 0
    extraction_method: str = "ocr"
    extraction_status: str = "empty"
    text: str = ""
    text_sha256: str = ""
    source_content_sha256: str = ""
    ocr_engine: str = DEFAULT_OCR_ENGINE
    ocr_engine_version: str = ""
    ocr_languages: str = DEFAULT_OCR_LANGUAGES
    confidence: float | None = None
    confidence_source: str = "unavailable"
    requires_review: bool = True
    review_status: str = "unverified"
    warnings: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ingestion_run_id: str = ""
    ingestion_provenance: dict[str, object] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""

    @property
    def status(self) -> str:
        """Backward-compatible read alias; persistence uses extraction_status."""
        return self.extraction_status

    @property
    def engine(self) -> str:
        """Backward-compatible read alias for the canonical OCR engine field."""
        return self.ocr_engine

    @property
    def languages(self) -> str:
        """Backward-compatible read alias for the canonical language field."""
        return self.ocr_languages

    @property
    def ocr_confidence(self) -> float | None:
        """Backward-compatible read alias for confidence."""
        return self.confidence

    @property
    def is_complete(self) -> bool:
        """Return whether this result is safe to publish as page evidence."""
        return (
            self.extraction_method == "ocr"
            and self.extraction_status == "completed"
            and bool(self.text)
            and bool(self.text_sha256)
            and bool(self.ocr_engine_version)
        )

    @staticmethod
    def _stable_id(revision_id: str, page_number: int) -> str:
        return make_source_page_evidence_id(revision_id, page_number) if revision_id else ""

    @staticmethod
    def _error_list(error_code: str, error_message: str) -> list[dict[str, str]]:
        if not error_code and not error_message:
            return []
        return [{"code": error_code, "message": error_message}]

    @classmethod
    def from_text(
        cls,
        *,
        page_number: int,
        text: str,
        confidence: float | None = None,
        confidence_source: str = "unavailable",
        engine: str = DEFAULT_OCR_ENGINE,
        languages: str = DEFAULT_OCR_LANGUAGES,
        engine_version: str = "",
        document_id: str = "",
        revision_id: str = "",
        source_content_sha256: str = "",
        ingestion_run_id: str = "",
        original_filename: str = "",
        ingestion_provenance: dict[str, object] | None = None,
    ) -> OcrPageResult:
        normalized = unicodedata.normalize("NFKC", text).strip()
        has_text = bool(normalized)
        if has_text and not engine_version:
            status = "unavailable"
            error_code = "ocr_engine_version_unavailable"
            error_message = "OCR engine version is required for completed evidence"
        else:
            status = "completed" if has_text else "empty"
            error_code = "" if has_text else "ocr_empty"
            error_message = "" if has_text else "OCR returned no text"
        now = datetime.now(UTC)
        provenance = dict(ingestion_provenance or {})
        provenance.update(
            {
                "source_authority": "original_artifact",
                "original_filename": original_filename,
                "source_content_sha256": source_content_sha256,
                "ocr_engine": engine,
                "ocr_engine_version": engine_version,
                "ocr_languages": languages,
            }
        )
        return cls(
            source_page_evidence_id=cls._stable_id(revision_id, page_number),
            document_id=document_id,
            revision_id=revision_id,
            page_number=page_number,
            extraction_status=status,
            text=normalized,
            text_sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            source_content_sha256=source_content_sha256,
            ocr_engine=engine,
            ocr_engine_version=engine_version,
            ocr_languages=languages,
            confidence=confidence,
            confidence_source=confidence_source if confidence is not None else "unavailable",
            warnings=[],
            errors=cls._error_list(error_code, error_message),
            created_at=now,
            updated_at=now,
            ingestion_run_id=ingestion_run_id,
            ingestion_provenance=provenance,
            error_code=error_code,
            error_message=error_message,
        )

    @classmethod
    def failure(
        cls,
        *,
        page_number: int,
        status: str | None = None,
        extraction_status: str | None = None,
        error_code: str,
        error_message: str,
        engine: str = DEFAULT_OCR_ENGINE,
        languages: str = DEFAULT_OCR_LANGUAGES,
        engine_version: str = "",
        document_id: str = "",
        revision_id: str = "",
        source_content_sha256: str = "",
        ingestion_run_id: str = "",
        original_filename: str = "",
        ingestion_provenance: dict[str, object] | None = None,
    ) -> OcrPageResult:
        canonical_status = extraction_status or status or "failed"
        canonical_status = {
            "complete": "completed",
            "missing_native_text": "failed",
            "hash_mismatch": "failed",
        }.get(canonical_status, canonical_status)
        if canonical_status not in _CANONICAL_STATUSES:
            canonical_status = "failed"
        empty_hash = hashlib.sha256(b"").hexdigest()
        now = datetime.now(UTC)
        provenance = dict(ingestion_provenance or {})
        provenance.update(
            {
                "source_authority": "original_artifact",
                "original_filename": original_filename,
                "source_content_sha256": source_content_sha256,
                "ocr_engine": engine,
                "ocr_engine_version": engine_version,
                "ocr_languages": languages,
            }
        )
        return cls(
            source_page_evidence_id=cls._stable_id(revision_id, page_number),
            document_id=document_id,
            revision_id=revision_id,
            page_number=page_number,
            extraction_status=canonical_status,
            text="",
            text_sha256=empty_hash,
            source_content_sha256=source_content_sha256,
            ocr_engine=engine,
            ocr_engine_version=engine_version,
            ocr_languages=languages,
            warnings=[],
            errors=cls._error_list(error_code, error_message),
            created_at=now,
            updated_at=now,
            ingestion_run_id=ingestion_run_id,
            ingestion_provenance=provenance,
            error_code=error_code,
            error_message=error_message,
        )


class OcrAdapter:
    """Render only requested pages and invoke local Tesseract through stdin."""

    def __init__(
        self,
        *,
        tesseract_binary: str = "tesseract",
        languages: str = DEFAULT_OCR_LANGUAGES,
        timeout_seconds: float = 60.0,
        runner: Callable[..., Any] | None = None,
    ) -> None:
        if not languages:
            raise ValueError("OCR languages must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("OCR timeout must be positive")
        self.tesseract_binary = tesseract_binary
        self.languages = languages
        self.timeout_seconds = timeout_seconds
        self._runner = runner or subprocess.run

    def ocr_pages(
        self,
        *,
        content: bytes,
        revision_id: str,
        source_content_sha256: str,
        page_numbers: list[int],
        document_id: str = "",
        ingestion_run_id: str = "",
        original_filename: str = "",
    ) -> list[OcrPageResult]:
        """OCR exact requested pages and return complete structured evidence."""
        if not revision_id:
            raise OcrAdapterError("revision_id is required")
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != source_content_sha256.lower():
            raise OcrAdapterError(
                "source content hash mismatch: original artifact is authoritative"
            )

        requested = list(page_numbers)
        if not requested:
            raise OcrAdapterError("OCR page request must not be empty")
        if any(isinstance(page, bool) or not isinstance(page, int) for page in requested):
            raise OcrAdapterError("OCR page numbers must be integers")
        if len(requested) != len(set(requested)):
            raise OcrAdapterError("OCR page request contains duplicate page numbers")

        doc = pymupdf.open(stream=content, filetype="pdf")  # type: ignore[no-untyped-call]
        try:
            if bool(doc.is_encrypted):
                raise OcrAdapterError("Encrypted PDF cannot be sent to local OCR")
            page_count = doc.page_count
            invalid = [page for page in requested if page < 1 or page > page_count]
            if invalid:
                raise OcrAdapterError(
                    f"OCR page request contains out-of-range pages {invalid}; "
                    f"PDF page_count={page_count}"
                )

            engine_version = self._runtime_engine_version()
            if not engine_version:
                return [
                    OcrPageResult.failure(
                        page_number=page_number,
                        status="unavailable",
                        error_code="ocr_engine_version_unavailable",
                        error_message="Tesseract runtime version could not be verified",
                        engine_version="",
                        document_id=document_id,
                        revision_id=revision_id,
                        source_content_sha256=source_content_sha256,
                        ingestion_run_id=ingestion_run_id,
                        original_filename=original_filename,
                    )
                    for page_number in sorted(requested)
                ]

            results: list[OcrPageResult] = []
            for page_number in sorted(requested):
                page = doc.load_page(page_number - 1)  # type: ignore[no-untyped-call]
                try:
                    pixmap = page.get_pixmap(
                        matrix=pymupdf.Matrix(2, 2),  # type: ignore[no-untyped-call]
                        alpha=False,
                    )
                    image_bytes = pixmap.tobytes("png")
                    results.append(
                        self._ocr_one_page(
                            page_number,
                            image_bytes,
                            engine_version=engine_version,
                            document_id=document_id,
                            revision_id=revision_id,
                            source_content_sha256=source_content_sha256,
                            ingestion_run_id=ingestion_run_id,
                            original_filename=original_filename,
                        )
                    )
                except Exception as exc:
                    results.append(
                        OcrPageResult.failure(
                            page_number=page_number,
                            status="failed",
                            error_code=type(exc).__name__,
                            error_message=str(exc),
                            engine_version=engine_version,
                            document_id=document_id,
                            revision_id=revision_id,
                            source_content_sha256=source_content_sha256,
                            ingestion_run_id=ingestion_run_id,
                            original_filename=original_filename,
                        )
                    )
            return results
        finally:
            doc.close()  # type: ignore[no-untyped-call]

    def _runtime_engine_version(self) -> str | None:
        """Read and validate the version from the local Tesseract binary."""
        try:
            completed = self._runner(
                [self.tesseract_binary, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None
        if completed.returncode != 0:
            return None
        output = b"\n".join(
            part for part in (completed.stdout or b"", completed.stderr or b"") if part
        ).decode("utf-8", errors="replace")
        match = re.search(r"(?im)^\s*tesseract\s+([0-9]+(?:\.[0-9]+)+)\b", output)
        return match.group(1) if match else None

    def _ocr_one_page(
        self,
        page_number: int,
        image_bytes: bytes,
        *,
        engine_version: str,
        document_id: str,
        revision_id: str,
        source_content_sha256: str,
        ingestion_run_id: str,
        original_filename: str,
    ) -> OcrPageResult:
        command = [
            self.tesseract_binary,
            "stdin",
            "stdout",
            "--psm",
            "6",
            "-l",
            self.languages,
            "tsv",
        ]
        common: dict[str, Any] = {
            "engine_version": engine_version,
            "document_id": document_id,
            "revision_id": revision_id,
            "source_content_sha256": source_content_sha256,
            "ingestion_run_id": ingestion_run_id,
            "original_filename": original_filename,
        }
        try:
            completed = self._runner(
                command,
                input=image_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            return OcrPageResult.failure(
                page_number=page_number,
                status="unavailable",
                error_code="tesseract_not_found",
                error_message=str(exc),
                **common,
            )
        except subprocess.TimeoutExpired as exc:
            return OcrPageResult.failure(
                page_number=page_number,
                status="failed",
                error_code="tesseract_timeout",
                error_message=str(exc),
                **common,
            )
        except Exception as exc:
            return OcrPageResult.failure(
                page_number=page_number,
                status="failed",
                error_code=type(exc).__name__,
                error_message=str(exc),
                **common,
            )

        stdout = completed.stdout or b""
        if completed.returncode != 0:
            stderr = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
            return OcrPageResult.failure(
                page_number=page_number,
                status="failed",
                error_code="tesseract_nonzero_exit",
                error_message=stderr or f"tesseract exited with {completed.returncode}",
                **common,
            )

        text, confidence = self._parse_tsv(stdout)
        return OcrPageResult.from_text(
            page_number=page_number,
            text=text,
            confidence=confidence,
            confidence_source="tesseract_tsv" if confidence is not None else "unavailable",
            engine_version=engine_version,
            engine=DEFAULT_OCR_ENGINE,
            languages=self.languages,
            **{key: value for key, value in common.items() if key != "engine_version"},
        )

    @staticmethod
    def _parse_tsv(payload: bytes) -> tuple[str, float | None]:
        """Extract ordered text and measurable word confidence from TSV."""
        decoded = payload.decode("utf-8", errors="replace")
        lines = decoded.splitlines()
        words: list[str] = []
        confidences: list[float] = []
        for line in lines:
            columns = line.split("\t")
            if len(columns) >= 12 and columns[0] != "level":
                raw_confidence = columns[10].strip()
                word = columns[11].strip()
                if word:
                    words.append(word)
                try:
                    numeric = float(raw_confidence)
                except ValueError:
                    numeric = -1.0
                if numeric >= 0:
                    confidences.append(numeric)

        if not words and decoded.strip() and "\t" not in decoded:
            # Keep adapter tests and compatible local wrappers useful when a
            # runner returns plain text instead of TSV.
            return decoded.strip(), None
        confidence = sum(confidences) / len(confidences) if confidences else None
        return " ".join(words), confidence
