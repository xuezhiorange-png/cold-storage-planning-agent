"""Plain text file parser — handles UTF-8, BOM, and paragraph preservation."""

from __future__ import annotations

import unicodedata

from cold_storage.modules.knowledge.domain.models import ParsedBlock
from cold_storage.modules.knowledge.infrastructure.parsers.base import (
    PARSER_VERSION,
    register_parser,
)


class TextParser:
    """Parse plain text files (.txt) into ParsedBlock list."""

    name: str = "text"

    def parse(self, content: bytes, filename: str) -> list[ParsedBlock]:
        """Parse a plain text file.

        Handles UTF-8 with or without BOM, records line ranges as paragraph metadata,
        and splits on double-newlines into paragraphs.
        """
        text = self._decode(content)
        text = unicodedata.normalize("NFKC", text)
        if not text.strip():
            return []

        # Split into paragraphs on double newlines
        paragraphs = text.split("\n\n")
        blocks: list[ParsedBlock] = []
        order = 0

        current_line = 1
        for para in paragraphs:
            stripped = para.strip()
            if not stripped:
                current_line += para.count("\n") + 1
                continue

            line_count = para.count("\n") + 1
            blocks.append(
                ParsedBlock(
                    text=stripped,
                    block_type="paragraph",
                    section_path="",
                    page_start=None,
                    page_end=None,
                    sheet_name=None,
                    row_start=current_line,
                    row_end=current_line + line_count - 1,
                    table_index=None,
                    paragraph_index=order,
                    source_order=order,
                    metadata={"source_format": "text", "parser_version": PARSER_VERSION},
                )
            )
            order += 1
            current_line += line_count

        return blocks

    @staticmethod
    def _decode(content: bytes) -> str:
        """Decode bytes to string, handling UTF-8 BOM."""
        if content[:3] == b"\xef\xbb\xbf":
            return content[3:].decode("utf-8")
        return content.decode("utf-8")


register_parser(".txt", TextParser())
