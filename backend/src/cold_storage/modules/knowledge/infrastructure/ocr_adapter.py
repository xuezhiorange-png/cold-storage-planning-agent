"""Local, offline Tesseract OCR adapter for selected PDF pages."""

from __future__ import annotations

import hashlib
import subprocess
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pymupdf

DEFAULT_OCR_LANGUAGES = "eng+chi_sim"
DEFAULT_OCR_ENGINE = "tesseract"


class OcrAdapterError(RuntimeError):
    """Raised when an OCR request is invalid or the source cannot be read."""


@dataclass(frozen=True)
class OcrPageResult:
    """Deterministic result for exactly one 1-based source page."""

    page_number: int
    text: str = ""
    text_sha256: str = ""
    status: str = "empty"
    confidence: float | None = None
    confidence_source: str = "unavailable"
    engine: str = DEFAULT_OCR_ENGINE
    languages: str = DEFAULT_OCR_LANGUAGES
    error_code: str = ""
    error_message: str = ""

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
    ) -> OcrPageResult:
        normalized = unicodedata.normalize("NFKC", text).strip()
        return cls(
            page_number=page_number,
            text=normalized,
            text_sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            status="complete" if normalized else "empty",
            confidence=confidence,
            confidence_source=confidence_source if confidence is not None else "unavailable",
            engine=engine,
            languages=languages,
        )

    @classmethod
    def failure(
        cls,
        *,
        page_number: int,
        status: str,
        error_code: str,
        error_message: str,
        engine: str = DEFAULT_OCR_ENGINE,
        languages: str = DEFAULT_OCR_LANGUAGES,
    ) -> OcrPageResult:
        empty_hash = hashlib.sha256(b"").hexdigest()
        return cls(
            page_number=page_number,
            text="",
            text_sha256=empty_hash,
            status=status,
            confidence=None,
            confidence_source="unavailable",
            engine=engine,
            languages=languages,
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
    ) -> list[OcrPageResult]:
        """OCR the exact requested pages, returning one result per page.

        The source bytes are hashed before rendering.  Page numbering is
        validated against the PDF and normalized to deterministic ascending
        order; invalid, empty, duplicate, or out-of-range requests are
        rejected before Tesseract is invoked.
        """
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

            results: list[OcrPageResult] = []
            for page_number in sorted(requested):
                page = doc.load_page(page_number - 1)  # type: ignore[no-untyped-call]
                try:
                    pixmap = page.get_pixmap(
                        matrix=pymupdf.Matrix(2, 2),  # type: ignore[no-untyped-call]
                        alpha=False,
                    )
                    image_bytes = pixmap.tobytes("png")
                    results.append(self._ocr_one_page(page_number, image_bytes))
                except Exception as exc:
                    results.append(
                        OcrPageResult.failure(
                            page_number=page_number,
                            status="failed",
                            error_code=type(exc).__name__,
                            error_message=str(exc),
                            languages=self.languages,
                        )
                    )
            return results
        finally:
            doc.close()  # type: ignore[no-untyped-call]

    def _ocr_one_page(self, page_number: int, image_bytes: bytes) -> OcrPageResult:
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
                languages=self.languages,
            )
        except subprocess.TimeoutExpired as exc:
            return OcrPageResult.failure(
                page_number=page_number,
                status="failed",
                error_code="tesseract_timeout",
                error_message=str(exc),
                languages=self.languages,
            )
        except Exception as exc:
            return OcrPageResult.failure(
                page_number=page_number,
                status="failed",
                error_code=type(exc).__name__,
                error_message=str(exc),
                languages=self.languages,
            )

        stdout = completed.stdout or b""
        if completed.returncode != 0:
            stderr = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
            return OcrPageResult.failure(
                page_number=page_number,
                status="failed",
                error_code="tesseract_nonzero_exit",
                error_message=stderr or f"tesseract exited with {completed.returncode}",
                languages=self.languages,
            )

        text, confidence = self._parse_tsv(stdout)
        return OcrPageResult.from_text(
            page_number=page_number,
            text=text,
            confidence=confidence,
            confidence_source="tesseract_tsv" if confidence is not None else "unavailable",
            languages=self.languages,
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
            # Keep adapter tests and compatible Tesseract wrappers useful when
            # a runner returns plain text instead of TSV; confidence remains
            # explicitly unavailable in that mode.
            return decoded.strip(), None
        confidence = sum(confidences) / len(confidences) if confidences else None
        return " ".join(words), confidence
