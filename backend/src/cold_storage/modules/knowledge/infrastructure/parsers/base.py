"""Parser base class and registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from cold_storage.modules.knowledge.domain.models import ParsedBlock

PARSER_VERSION: str = "parser-v1"


@dataclass
class ParseResult:
    """Rich result from a parser, carrying blocks plus metadata."""

    blocks: list[ParsedBlock]
    warnings: list[str] = field(default_factory=list)
    page_count: int | None = None
    ocr_page_numbers: list[int] = field(default_factory=list)


class Parser(Protocol):
    """Protocol that all file parsers must implement."""

    name: str

    def parse(self, content: bytes, filename: str) -> list[ParsedBlock]:
        """Parse raw file content into a list of ParsedBlock."""
        ...


# Optional method: ``parse_with_metadata(content, filename) -> ParseResult``
# is NOT part of the Protocol because most parsers don't need it.
# Only PdfParser implements it; the application service uses ``hasattr``
# to check for this capability before calling it.


# ---------------------------------------------------------------------------
# Parser registry
# ---------------------------------------------------------------------------
_PARSERS: dict[str, Parser] = {}


def register_parser(ext: str, parser: Parser) -> None:
    """Register a parser for a file extension (e.g. '.txt', '.pdf')."""
    _PARSERS[ext.lower()] = parser


def get_parser(extension: str) -> Parser | None:
    """Look up a parser by file extension."""
    return _PARSERS.get(extension.lower())


def get_parser_for_file(filename: str, mime_type: str) -> Parser | None:
    """Resolve the best parser for a file given its name and MIME type."""
    # Try extension first
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
    parser = get_parser(ext)
    if parser is not None:
        return parser
    # Fallback: try common MIME-type → extension mappings
    _MIME_MAP: dict[str, str] = {
        "text/plain": ".txt",
        "text/markdown": ".md",
        "text/csv": ".csv",
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    }
    fallback_ext = _MIME_MAP.get(mime_type.lower())
    if fallback_ext:
        return get_parser(fallback_ext)
    return None
