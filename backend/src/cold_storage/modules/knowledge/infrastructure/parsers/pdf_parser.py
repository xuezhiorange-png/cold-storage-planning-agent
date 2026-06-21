"""PDF file parser — PyMuPDF page-by-page extraction with OCR detection."""

from __future__ import annotations

import unicodedata

from cold_storage.modules.knowledge.domain.models import ParsedBlock
from cold_storage.modules.knowledge.infrastructure.parsers.base import (
    PARSER_VERSION,
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
    with insufficient text for OCR processing.
    """

    name: str = "pdf"

    def parse(self, content: bytes, filename: str) -> list[ParsedBlock]:
        """Parse a PDF file into ParsedBlock list.

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

            for page_idx in range(page_count):
                page = doc.load_page(page_idx)  # type: ignore[no-untyped-call]
                page_num = page_idx + 1  # 1-based

                # Extract text
                text = page.get_text("text")
                text = unicodedata.normalize("NFKC", text)
                text = text.strip()

                if not text:
                    # Check if there are images (might need OCR)
                    image_list = page.get_images()
                    if image_list:
                        blocks.append(
                            ParsedBlock(
                                text=f"[Page {page_num} — image-only page, OCR may be required]",
                                block_type="paragraph",
                                section_path=f"page:{page_num}",
                                page_start=page_num,
                                page_end=page_num,
                                source_order=order,
                                metadata={
                                    "parser_version": PARSER_VERSION,
                                    "page_number": page_num,
                                    "requires_ocr": True,
                                    "image_count": len(image_list),
                                },
                            )
                        )
                        order += 1
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

        finally:
            doc.close()  # type: ignore[no-untyped-call]

        return blocks

    def detect_ocr_needed(self, content: bytes) -> bool:
        """Check if a PDF contains insufficient text and requires OCR.

        Returns True if the average text per page is below OCR_TEXT_THRESHOLD.
        """
        if pymupdf is None:
            return False

        doc = pymupdf.open(stream=content, filetype="pdf")  # type: ignore[no-untyped-call]
        try:
            if bool(doc.is_encrypted):
                return True
            if doc.page_count == 0:
                return False
            total_text = 0
            for page_idx in range(doc.page_count):
                page = doc.load_page(page_idx)  # type: ignore[no-untyped-call]
                total_text += len(page.get_text("text").strip())
            avg_text = total_text / doc.page_count
            return bool(avg_text < OCR_TEXT_THRESHOLD)
        finally:
            doc.close()  # type: ignore[no-untyped-call]


register_parser(".pdf", PdfParser())
