"""Markdown header-based chunker with precise page attribution from segments."""
from __future__ import annotations

import re

import structlog

from app.knowledge.rag.chunking.base import BaseChunker, ChunkData
from app.knowledge.rag.chunking.utils import estimate_tokens
from app.knowledge.rag.parsing.base import ContentSegment, ParsedDocument

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

        if parsed.segments:
            return self._chunk_from_segments(parsed.segments, max_tokens)
        return self._chunk_from_content(parsed.content, max_tokens)

    def _chunk_from_segments(self, segments: list[ContentSegment], max_tokens: int) -> list[ChunkData]:
        """Split segments by headers, each section becomes a chunk with exact pages."""
        chunks: list[ChunkData] = []
        header_stack: list[tuple[int, str]] = []
        current_texts: list[str] = []
        current_pages: list[int] = []
        ordinal = 0

        def _path():
            return " > ".join(t for _, t in header_stack) if header_stack else None

        def _flush():
            nonlocal ordinal
            if not current_texts:
                return
            text = "\n\n".join(current_texts)
            tokens = estimate_tokens(text)
            if tokens <= max_tokens:
                chunks.append(ChunkData(
                    content=text, ordinal=ordinal, chunk_type="text",
                    section_path=_path(), token_count=tokens,
                    page_start=min(current_pages) if current_pages else None,
                    page_end=max(current_pages) if current_pages else None,
                ))
                ordinal += 1
            else:
                # Split large section by individual segments
                for t, p in zip(current_texts, current_pages):
                    chunks.append(ChunkData(
                        content=t, ordinal=ordinal, chunk_type="text",
                        section_path=_path(), token_count=estimate_tokens(t),
                        page_start=p, page_end=p,
                    ))
                    ordinal += 1

        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            m = _HEADER_RE.match(text)
            if m:
                _flush()
                current_texts = []
                current_pages = []
                level, title = len(m.group(1)), m.group(2).strip()
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()
                header_stack.append((level, title))
            current_texts.append(text)
            current_pages.append(seg.page_number)

        _flush()
        logger.info("markdown_header_chunked", total_chunks=len(chunks))
        return chunks

    def _chunk_from_content(self, content: str, max_tokens: int) -> list[ChunkData]:
        """Fallback when no segments available."""
        if not content.strip():
            return []
        lines = content.split("\n")
        sections: list[tuple[str | None, str]] = []
        header_stack: list[tuple[int, str]] = []
        current_lines: list[str] = []

        def _path():
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

        chunks: list[ChunkData] = []
        ordinal = 0
        for section_path, section_text in sections:
            text = section_text.strip()
            if not text:
                continue
            tokens = estimate_tokens(text)
            if tokens <= max_tokens:
                chunks.append(ChunkData(
                    content=text, ordinal=ordinal, chunk_type="text",
                    section_path=section_path, token_count=tokens,
                ))
                ordinal += 1
            else:
                # Split large section by paragraphs
                parts: list[str] = []
                part_tokens = 0
                for para in re.split(r"\n\s*\n", text):
                    para = para.strip()
                    if not para:
                        continue
                    pt = estimate_tokens(para)
                    if part_tokens + pt > max_tokens and parts:
                        chunk_text = "\n\n".join(parts)
                        chunks.append(ChunkData(
                            content=chunk_text, ordinal=ordinal, chunk_type="text",
                            section_path=section_path, token_count=estimate_tokens(chunk_text),
                        ))
                        ordinal += 1
                        parts = []
                        part_tokens = 0
                    parts.append(para)
                    part_tokens += pt
                if parts:
                    chunk_text = "\n\n".join(parts)
                    chunks.append(ChunkData(
                        content=chunk_text, ordinal=ordinal, chunk_type="text",
                        section_path=section_path, token_count=estimate_tokens(chunk_text),
                    ))
                    ordinal += 1

        logger.info("markdown_header_chunked", total_chunks=len(chunks))
        return chunks
