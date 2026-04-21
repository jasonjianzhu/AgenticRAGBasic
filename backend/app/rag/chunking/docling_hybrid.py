"""Structure-aware hybrid chunker that respects document structure and page boundaries."""
from __future__ import annotations

import re

import structlog

from app.rag.chunking.base import BaseChunker, ChunkData
from app.rag.chunking.utils import estimate_tokens
from app.rag.parsing.base import ParsedDocument, ParsedPage

logger = structlog.get_logger(__name__)

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _build_page_index(pages: list[ParsedPage]) -> list[tuple[int, str]]:
    """Build a list of (page_number, content) for page lookup."""
    return [(p.page_number, p.content) for p in pages if p.content.strip()]


def _find_pages_for_text(text: str, page_index: list[tuple[int, str]]) -> tuple[int | None, int | None]:
    """Find page_start and page_end for a chunk text by matching against page contents."""
    if not page_index or not text.strip():
        return None, None

    snippet = text.strip()[:120]
    matched = []
    for page_num, page_content in page_index:
        if snippet in page_content:
            matched.append(page_num)

    if matched:
        return min(matched), max(matched)

    # Fallback: try shorter snippet
    snippet_short = text.strip()[:50]
    for page_num, page_content in page_index:
        if snippet_short and snippet_short in page_content:
            matched.append(page_num)

    if matched:
        return min(matched), max(matched)

    return None, None


class DoclingHybridChunker(BaseChunker):
    """Structure-aware chunker with precise page attribution.

    Splits by section headers, enforces token limits with overlap,
    and assigns page_start/page_end from ParsedDocument.pages.
    """

    def __init__(self, min_tokens: int = 300, max_tokens: int = 600, overlap_tokens: int = 50) -> None:
        self._min_tokens = min_tokens
        self._max_tokens = max_tokens
        self._overlap_tokens = overlap_tokens

    @property
    def name(self) -> str:
        return "docling_hybrid"

    def chunk(self, parsed: ParsedDocument, **kwargs) -> list[ChunkData]:
        min_tokens = kwargs.get("min_tokens", self._min_tokens)
        max_tokens = kwargs.get("max_tokens", self._max_tokens)
        overlap_tokens = kwargs.get("overlap_tokens", self._overlap_tokens)

        page_index = _build_page_index(parsed.pages)
        sections = self._split_by_sections(parsed.content)
        raw_chunks: list[ChunkData] = []
        ordinal = 0

        for section_path, section_text in sections:
            text = section_text.strip()
            if not text:
                continue
            token_count = estimate_tokens(text)

            if token_count <= max_tokens:
                ps, pe = _find_pages_for_text(text, page_index)
                raw_chunks.append(ChunkData(
                    content=text, ordinal=ordinal, chunk_type="text",
                    section_path=section_path, token_count=token_count,
                    page_start=ps, page_end=pe,
                ))
                ordinal += 1
            else:
                sub = self._split_large_section(text, section_path, max_tokens, overlap_tokens, ordinal, page_index)
                raw_chunks.extend(sub)
                ordinal += len(sub)

        merged = self._merge_small_chunks(raw_chunks, min_tokens, max_tokens, page_index)

        for i, c in enumerate(merged):
            c.ordinal = i
            c.token_count = estimate_tokens(c.content)

        logger.info("docling_hybrid_chunked", total_chunks=len(merged), content_length=len(parsed.content))
        return merged

    def _split_by_sections(self, content: str) -> list[tuple[str | None, str]]:
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

    def _split_large_section(self, text, section_path, max_tokens, overlap_tokens, start_ordinal, page_index):
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
                overlap_parts, oc = [], 0
                for p in reversed(current_parts):
                    t = estimate_tokens(p)
                    if oc + t > overlap_tokens:
                        break
                    overlap_parts.insert(0, p)
                    oc += t
                current_parts, current_tokens = overlap_parts, oc
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

    def _merge_small_chunks(self, chunks, min_tokens, max_tokens, page_index):
        if not chunks:
            return []
        merged: list[ChunkData] = [chunks[0]]
        for chunk in chunks[1:]:
            prev = merged[-1]
            pt = prev.token_count or estimate_tokens(prev.content)
            ct = chunk.token_count or estimate_tokens(chunk.content)
            if pt < min_tokens and prev.section_path == chunk.section_path and pt + ct <= max_tokens:
                prev.content = prev.content + "\n\n" + chunk.content
                prev.token_count = estimate_tokens(prev.content)
                # Merge page ranges
                pages = [x for x in [prev.page_start, prev.page_end, chunk.page_start, chunk.page_end] if x is not None]
                prev.page_start = min(pages) if pages else None
                prev.page_end = max(pages) if pages else None
            else:
                merged.append(chunk)
        return merged
