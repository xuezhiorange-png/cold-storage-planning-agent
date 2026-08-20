"""PDF file parser — PyMuPDF page-by-page extraction with OCR detection."""

from __future__ import annotations

import unicodedata

from cold_storage.modules.knowledge.domain.models import ParsedBlock
from cold_storage.modules.knowledge.infrastructure.parsers.base import (
    PARSER_VERSION,
    ParseResult,
    register_parser,
)

try:
    import pymupdf  # PyMuPDF / fitz
except ImportError:
    pymupdf = None  # type: ignore[assignment]

# Native text is sufficient only when the normalized, non-whitespace character
# count meets this threshold.  The policy is deliberately page-scoped and
# deterministic so low-text pages cannot silently bypass OCR.
OCR_TEXT_THRESHOLD: int = 50
NATIVE_TEXT_SUFFICIENCY_POLICY: str = "non_whitespace_characters>=OCR_TEXT_THRESHOLD"


def native_text_is_sufficient(text: str) -> bool:
    """Return whether normalized native text is sufficient for this page."""
    normalized = unicodedata.normalize("NFKC", text)
    return len("".join(normalized.split())) >= OCR_TEXT_THRESHOLD


class PdfParser:
    """Parse PDF files using PyMuPDF (fitz).

    Extracts text page-by-page, detects encrypted PDFs, and flags pages
    with insufficient text for OCR processing.  Returns a ``ParseResult``
    whose ``ocr_page_numbers`` and ``page_count`` carry the OCR metadata;
    the application service reads these directly.
    """

    name: str = "pdf"

    def parse(self, content: bytes, filename: str) -> ParseResult:
        """Parse a PDF file into a ParseResult with blocks + OCR metadata.

        Raises
        ------
        ImportError
            If pymupdf is not installed.
        ValueError
            If the PDF is encrypted.
        """
        if pymupdf is None:
            raise ImportError("PyMuPDF is required for PDF parsing: pip install pymupdf")

        doc = pymupdf.open(stream=content, filetype="pdf")  # type: ignore[no-untyped-call]

        try:
            # Check for encryption
            if bool(doc.is_encrypted):
                raise ValueError("Encrypted PDF is not supported")

            blocks: list[ParsedBlock] = []
            order = 0
            page_count = doc.page_count
            ocr_page_numbers: list[int] = []

            for page_idx in range(page_count):
                page = doc.load_page(page_idx)  # type: ignore[no-untyped-call]
                page_num = page_idx + 1  # 1-based

                # Extract text
                text = page.get_text("text")
                text = unicodedata.normalize("NFKC", text)
                text = text.strip()

                if not native_text_is_sufficient(text):
                    # A page with no text, low native text, or only an image
                    # is selected for OCR.  Do not publish a native block for
                    # it: successful OCR must not duplicate full-page text.
                    ocr_page_numbers.append(page_num)
                    continue

                # Split page text into paragraphs
                paragraphs = text.split("\n\n")
                for para in paragraphs:
                    para = para.strip()
                    if not para:
                        continue
                    blocks.append(
                        ParsedBlock(
                            text=para,
                            block_type="paragraph",
                            section_path=f"page:{page_num}",
                            page_start=page_num,
                            page_end=page_num,
                            source_order=order,
                            metadata={
                                "parser_version": PARSER_VERSION,
                                "page_number": page_num,
                                "extraction_method": "native",
                                "native_text_sufficient": True,
                            },
                        )
                    )
                    order += 1

            # Build warnings
            warnings: list[str] = []
            if ocr_page_numbers:
                warnings.append(
                    "OCR required for pages below the deterministic native-text "
                    f"sufficiency threshold ({OCR_TEXT_THRESHOLD} non-whitespace "
                    f"characters): {ocr_page_numbers}"
                )

            return ParseResult(
                blocks=blocks,
                warnings=warnings,
                page_count=page_count,
                ocr_page_numbers=ocr_page_numbers,
            )

        finally:
            doc.close()  # type: ignore[no-untyped-call]


register_parser(".pdf", PdfParser())
