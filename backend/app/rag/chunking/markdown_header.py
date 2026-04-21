"""Markdown header-based chunker that splits by heading levels."""
from __future__ import annotations

import re

import structlog

from app.rag.chunking.base import BaseChunker, ChunkData
from app.rag.chunking.utils import estimate_tokens
from app.rag.parsing.base import ParsedDocument

logger = structlog.get_logger(__name__)

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


class MarkdownHeaderChunker(BaseChunker):
    """Chunker that splits by markdown header levels.

    Each section becomes a chunk. If a section exceeds max_tokens,
    it is further split by paragraphs.

    Args:
        max_tokens: Maximum tokens per chunk (default 500).
    """

    def __init__(self, max_tokens: int = 500) -> None:
        self._max_tokens = max_tokens

    @property
    def name(self) -> str:
        return "markdown_header"

    def chunk(self, parsed: ParsedDocument, **kwargs) -> list[ChunkData]:
        """Split a parsed document by markdown headers."""
        max_tokens = kwargs.get("max_tokens", self._max_tokens)
        sections = self._extract_sections(parsed.content)
        chunks: list[ChunkData] = []
        ordinal = 0

        for section_path, section_text in sections:
            text = section_text.strip()
            if not text:
                continue

            token_count = estimate_tokens(text)

            if token_count <= max_tokens:
                chunks.append(
                    ChunkData(
                        content=text,
                        ordinal=ordinal,
                        chunk_type="text",
                        section_path=section_path,
                        token_count=token_count,
                    )
                )
                ordinal += 1
            else:
                # Split large section by paragraphs
                sub_chunks = self._split_by_paragraphs(
                    text, section_path, max_tokens, ordinal
                )
                chunks.extend(sub_chunks)
                ordinal += len(sub_chunks)

        logger.info(
            "markdown_header_chunked",
            total_chunks=len(chunks),
            content_length=len(parsed.content),
        )
        return chunks

    def _extract_sections(self, content: str) -> list[tuple[str | None, str]]:
        """Extract sections from markdown content.

        Returns list of (section_path, section_text) tuples.
        The section_path is built from nested headers like
        "Chapter 1 > Section 2 > Subsection 3".
        """
        if not content.strip():
            return []

        lines = content.split("\n")
        sections: list[tuple[str | None, str]] = []
        header_stack: list[tuple[int, str]] = []
        current_lines: list[str] = []

        def _section_path() -> str | None:
            if not header_stack:
                return None
            return " > ".join(title for _, title in header_stack)

        for line in lines:
            match = _HEADER_RE.match(line)
            if match:
                # Flush current section
                if current_lines:
                    sections.append((_section_path(), "\n".join(current_lines)))
                    current_lines = []

                level = len(match.group(1))
                title = match.group(2).strip()

                # Pop headers at same or deeper level
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()
                header_stack.append((level, title))

                current_lines.append(line)
            else:
                current_lines.append(line)

        # Flush remaining
        if current_lines:
            sections.append((_section_path(), "\n".join(current_lines)))

        return sections

    def _split_by_paragraphs(
        self,
        text: str,
        section_path: str | None,
        max_tokens: int,
        start_ordinal: int,
    ) -> list[ChunkData]:
        """Split a large section into paragraph-based chunks."""
        paragraphs = re.split(r"\n\s*\n", text)
        chunks: list[ChunkData] = []
        current_parts: list[str] = []
        current_tokens = 0
        ordinal = start_ordinal

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            para_tokens = estimate_tokens(para)

            if current_tokens + para_tokens > max_tokens and current_parts:
                chunk_text = "\n\n".join(current_parts)
                chunks.append(
                    ChunkData(
                        content=chunk_text,
                        ordinal=ordinal,
                        chunk_type="text",
                        section_path=section_path,
                        token_count=estimate_tokens(chunk_text),
                    )
                )
                ordinal += 1
                current_parts = []
                current_tokens = 0

            current_parts.append(para)
            current_tokens += para_tokens

        if current_parts:
            chunk_text = "\n\n".join(current_parts)
            chunks.append(
                ChunkData(
                    content=chunk_text,
                    ordinal=ordinal,
                    chunk_type="text",
                    section_path=section_path,
                    token_count=estimate_tokens(chunk_text),
                )
            )

        return chunks
