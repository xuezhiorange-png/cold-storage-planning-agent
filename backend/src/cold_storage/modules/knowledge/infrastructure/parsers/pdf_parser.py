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

# If text on a page is below this threshold (in characters), flag as OCR-required
OCR_TEXT_THRESHOLD: int = 50


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
            ocr_image_counts: list[int] = []

            for page_idx in range(page_count):
                page = doc.load_page(page_idx)  # type: ignore[no-untyped-call]
                page_num = page_idx + 1  # 1-based

                # Extract text
                text = page.get_text("text")
                text = unicodedata.normalize("NFKC", text)
                text = text.strip()

                # Check for images before deciding what to do
                image_list = page.get_images()

                if not text:
                    # Image-only page — do NOT generate a fake ParsedBlock.
                    # Record in metadata; the application service will set
                    # requires_ocr and warn about missing pages.
                    if image_list:
                        ocr_page_numbers.append(page_num)
                        ocr_image_counts.append(len(image_list))
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
                            },
                        )
                    )
                    order += 1

            # Build warnings
            warnings: list[str] = []
            if ocr_page_numbers:
                warnings.append(f"OCR may be required for image-only pages: {ocr_page_numbers}")

            return ParseResult(
                blocks=blocks,
                warnings=warnings,
                page_count=page_count,
                ocr_page_numbers=ocr_page_numbers,
            )

        finally:
            doc.close()  # type: ignore[no-untyped-call]


register_parser(".pdf", PdfParser())
