"""Markdown header-based chunker with precise page attribution."""
from __future__ import annotations

import re

import structlog

from app.rag.chunking.base import BaseChunker, ChunkData
from app.rag.chunking.docling_hybrid import _build_page_index, _find_pages_for_text
from app.rag.chunking.utils import estimate_tokens
from app.rag.parsing.base import ParsedDocument

logger = structlog.get_logger(__name__)

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


class MarkdownHeaderChunker(BaseChunker):
    """Chunker that splits by markdown header levels with page attribution."""

    def __init__(self, max_tokens: int = 500) -> None:
        self._max_tokens = max_tokens

    @property
    def name(self) -> str:
        return "markdown_header"

    def chunk(self, parsed: ParsedDocument, **kwargs) -> list[ChunkData]:
        max_tokens = kwargs.get("max_tokens", self._max_tokens)
        page_index = _build_page_index(parsed.pages)
        sections = self._extract_sections(parsed.content)
        chunks: list[ChunkData] = []
        ordinal = 0

        for section_path, section_text in sections:
            text = section_text.strip()
            if not text:
                continue
            token_count = estimate_tokens(text)

            if token_count <= max_tokens:
                ps, pe = _find_pages_for_text(text, page_index)
                chunks.append(ChunkData(
                    content=text, ordinal=ordinal, chunk_type="text",
                    section_path=section_path, token_count=token_count,
                    page_start=ps, page_end=pe,
                ))
                ordinal += 1
            else:
                sub = self._split_by_paragraphs(text, section_path, max_tokens, ordinal, page_index)
                chunks.extend(sub)
                ordinal += len(sub)

        logger.info("markdown_header_chunked", total_chunks=len(chunks), content_length=len(parsed.content))
        return chunks

    def _extract_sections(self, content: str) -> list[tuple[str | None, str]]:
        if not content.strip():
            return []
        lines = content.split("\n")
        sections: list[tuple[str | None, str]] = []
        header_stack: list[tuple[int, str]] = []
        current_lines: list[str] = []

        def _path() -> str | None:
            return " > ".join(t for _, t in header_stack) if header_stack else None

        for line in lines:
            m = _HEADER_RE.match(line)
            if m:
                if current_lines:
                    sections.append((_path(), "\n".join(current_lines)))
                    current_lines = []
                level, title = len(m.group(1)), m.group(2).strip()
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()
                header_stack.append((level, title))
                current_lines.append(line)
            else:
                current_lines.append(line)
        if current_lines:
            sections.append((_path(), "\n".join(current_lines)))
        return sections

    def _split_by_paragraphs(self, text, section_path, max_tokens, start_ordinal, page_index):
        paragraphs = re.split(r"\n\s*\n", text)
        chunks: list[ChunkData] = []
        current_parts: list[str] = []
        current_tokens = 0
        ordinal = start_ordinal

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            pt = estimate_tokens(para)
            if current_tokens + pt > max_tokens and current_parts:
                chunk_text = "\n\n".join(current_parts)
                ps, pe = _find_pages_for_text(chunk_text, page_index)
                chunks.append(ChunkData(
                    content=chunk_text, ordinal=ordinal, chunk_type="text",
                    section_path=section_path, token_count=estimate_tokens(chunk_text),
                    page_start=ps, page_end=pe,
                ))
                ordinal += 1
                current_parts = []
                current_tokens = 0
            current_parts.append(para)
            current_tokens += pt

        if current_parts:
            chunk_text = "\n\n".join(current_parts)
            ps, pe = _find_pages_for_text(chunk_text, page_index)
            chunks.append(ChunkData(
                content=chunk_text, ordinal=ordinal, chunk_type="text",
                section_path=section_path, token_count=estimate_tokens(chunk_text),
                page_start=ps, page_end=pe,
            ))
        return chunks
