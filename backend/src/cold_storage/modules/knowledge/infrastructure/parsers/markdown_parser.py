"""Markdown file parser — heading hierarchy, code blocks, inline elements."""

from __future__ import annotations

import re
import unicodedata

from cold_storage.modules.knowledge.domain.models import ParsedBlock
from cold_storage.modules.knowledge.infrastructure.parsers.base import (
    PARSER_VERSION,
    ParseResult,
    register_parser,
)


class MarkdownParser:
    """Parse Markdown files (.md) into ParsedBlock list.

    Preserves heading hierarchy for section_path, treats fenced code blocks as
    separate blocks, and records paragraph indices.
    """

    name: str = "markdown"

    def parse(self, content: bytes, filename: str) -> list[ParsedBlock]:
        """Parse a Markdown file into structured blocks."""
        text = content.decode("utf-8", errors="replace")
        text = unicodedata.normalize("NFKC", text)
        if not text.strip():
            return []

        blocks: list[ParsedBlock] = []
        heading_stack: list[str] = []
        order = 0
        current_line = 1

        # Split into segments: headings, code blocks, and paragraph text
        segments = self._segment(text)

        for seg_type, seg_text in segments:
            stripped = seg_text.strip()
            if not stripped:
                current_line += seg_text.count("\n") + 1
                continue

            line_count = seg_text.count("\n") + 1

            if seg_type == "heading":
                level = len(stripped.split(" ", 1)[0])  # count #'s
                heading_text = stripped.split(" ", 1)[1] if " " in stripped else ""
                # Update heading stack
                while len(heading_stack) >= level:
                    heading_stack.pop()
                heading_stack.append(heading_text)
                section = " > ".join(heading_stack)

                blocks.append(
                    ParsedBlock(
                        text=stripped,
                        block_type="heading",
                        section_path=section,
                        page_start=None,
                        page_end=None,
                        source_order=order,
                        metadata={
                            "heading_level": level,
                            "parser_version": PARSER_VERSION,
                        },
                    )
                )
            elif seg_type == "code":
                section = " > ".join(heading_stack) if heading_stack else ""
                blocks.append(
                    ParsedBlock(
                        text=stripped,
                        block_type="code",
                        section_path=section,
                        page_start=None,
                        page_end=None,
                        source_order=order,
                        metadata={"parser_version": PARSER_VERSION},
                    )
                )
            else:
                section = " > ".join(heading_stack) if heading_stack else ""
                blocks.append(
                    ParsedBlock(
                        text=stripped,
                        block_type="paragraph",
                        section_path=section,
                        page_start=None,
                        page_end=None,
                        row_start=current_line,
                        row_end=current_line + line_count - 1,
                        paragraph_index=order,
                        source_order=order,
                        metadata={"parser_version": PARSER_VERSION},
                    )
                )

            order += 1
            current_line += line_count

        return blocks

    def parse_with_metadata(self, content: bytes, filename: str) -> ParseResult:
        """Parse and return ParseResult with blocks and metadata."""
        blocks = self.parse(content, filename)
        return ParseResult(blocks=blocks)

    @staticmethod
    def _segment(text: str) -> list[tuple[str, str]]:
        """Split markdown into (type, text) segments."""
        segments: list[tuple[str, str]] = []
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]

            # Fenced code block
            if line.strip().startswith("```"):
                code_lines: list[str] = [line]
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                if i < len(lines):
                    code_lines.append(lines[i])  # closing fence
                    i += 1
                segments.append(("code", "\n".join(code_lines)))
                continue

            # Heading
            if re.match(r"^#{1,6}\s", line):
                segments.append(("heading", line))
                i += 1
                continue

            # Paragraph — collect consecutive non-empty, non-heading, non-code lines
            para_lines: list[str] = []
            while i < len(lines):
                line_text = lines[i]
                if (
                    line_text.strip() == ""
                    or re.match(r"^#{1,6}\s", line_text)
                    or line_text.strip().startswith("```")
                ):
                    break
                para_lines.append(line_text)
                i += 1
            if para_lines:
                segments.append(("paragraph", "\n".join(para_lines)))

        return segments


register_parser(".md", MarkdownParser())
