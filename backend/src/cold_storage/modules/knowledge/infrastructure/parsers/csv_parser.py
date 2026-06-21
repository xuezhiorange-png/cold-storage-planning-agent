"""CSV file parser — structured row extraction with header preservation."""

from __future__ import annotations

import csv
import io
import unicodedata

from cold_storage.modules.knowledge.domain.models import ParsedBlock
from cold_storage.modules.knowledge.infrastructure.parsers.base import (
    PARSER_VERSION,
    register_parser,
)

MAX_CSV_ROWS: int = 10_000
MAX_CSV_COLUMNS: int = 100


class CsvParser:
    """Parse CSV files into ParsedBlock list.

    Each row becomes a structured text block with row-range metadata.
    Headers are preserved in a metadata block.
    """

    name: str = "csv"

    def parse(self, content: bytes, filename: str) -> list[ParsedBlock]:
        """Parse a CSV file, respecting row and column limits."""
        text = content.decode("utf-8-sig", errors="replace")
        text = unicodedata.normalize("NFKC", text)
        if not text.strip():
            return []

        reader = csv.reader(io.StringIO(text))
        blocks: list[ParsedBlock] = []
        order = 0
        row_num = 0

        # Read header row
        try:
            headers = next(reader)
        except StopIteration:
            return []

        # Trim to column limit
        if len(headers) > MAX_CSV_COLUMNS:
            headers = headers[:MAX_CSV_COLUMNS]

        # Emit metadata block with headers
        header_text = " | ".join(h.strip() for h in headers)
        blocks.append(
            ParsedBlock(
                text=header_text,
                block_type="metadata",
                section_path="headers",
                page_start=None,
                page_end=None,
                sheet_name=None,
                row_start=1,
                row_end=1,
                source_order=order,
                metadata={
                    "headers": headers,
                    "parser_version": PARSER_VERSION,
                },
            )
        )
        order += 1

        # Process data rows
        for row in reader:
            row_num += 1
            if row_num > MAX_CSV_ROWS:
                break
            # Skip empty rows
            if not any(cell.strip() for cell in row):
                continue
            # Trim to column limit
            cells = row[:MAX_CSV_COLUMNS] if len(row) > MAX_CSV_COLUMNS else row
            # Build structured text
            pairs = []
            for i, cell in enumerate(cells):
                if i < len(headers) and headers[i].strip():
                    pairs.append(f"{headers[i].strip()}: {cell.strip()}")
                else:
                    pairs.append(cell.strip())
            row_text = " | ".join(pairs)
            if not row_text.strip():
                continue

            blocks.append(
                ParsedBlock(
                    text=row_text,
                    block_type="paragraph",
                    section_path="",
                    page_start=None,
                    page_end=None,
                    sheet_name=None,
                    row_start=row_num + 1,
                    row_end=row_num + 1,
                    source_order=order,
                    metadata={
                        "parser_version": PARSER_VERSION,
                        "row_number": row_num + 1,
                    },
                )
            )
            order += 1

        return blocks


register_parser(".csv", CsvParser())
