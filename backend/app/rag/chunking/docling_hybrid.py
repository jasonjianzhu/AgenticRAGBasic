"""Structure-aware hybrid chunker with precise page attribution from segments."""
from __future__ import annotations

import re

import structlog

from app.rag.chunking.base import BaseChunker, ChunkData
from app.rag.chunking.utils import estimate_tokens
from app.rag.parsing.base import ContentSegment, ParsedDocument

logger = structlog.get_logger(__name__)

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


class DoclingHybridChunker(BaseChunker):
    """Structure-aware chunker with precise page attribution.

    When ParsedDocument has segments (text + page_number pairs from Docling),
    uses them directly for exact page attribution. Falls back to content-based
    splitting when segments are not available.
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

        if parsed.segments:
            chunks = self._chunk_from_segments(parsed.segments, max_tokens, overlap_tokens)
        else:
            chunks = self._chunk_from_content(parsed.content, max_tokens, overlap_tokens)

        # Merge small consecutive chunks from the same section
        merged = self._merge_small_chunks(chunks, min_tokens, max_tokens)

        for i, c in enumerate(merged):
            c.ordinal = i
            c.token_count = estimate_tokens(c.content)

        logger.info("docling_hybrid_chunked", total_chunks=len(merged))
        return merged

    def _chunk_from_segments(
        self, segments: list[ContentSegment], max_tokens: int, overlap_tokens: int
    ) -> list[ChunkData]:
        """Build chunks from segments with exact page attribution."""
        chunks: list[ChunkData] = []
        current_texts: list[str] = []
        current_pages: list[int] = []
        current_tokens = 0
        current_section: str | None = None
        ordinal = 0

        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue

            seg_tokens = estimate_tokens(text)

            # Track section path from headers
            header_match = _HEADER_RE.match(text)
            if header_match:
                current_section = header_match.group(2).strip()

            # If adding this segment exceeds max, flush current chunk
            if current_tokens + seg_tokens > max_tokens and current_texts:
                chunk_text = "\n\n".join(current_texts)
                chunks.append(ChunkData(
                    content=chunk_text,
                    ordinal=ordinal,
                    chunk_type="text",
                    section_path=current_section,
                    token_count=estimate_tokens(chunk_text),
                    page_start=min(current_pages),
                    page_end=max(current_pages),
                ))
                ordinal += 1

                # Overlap: keep trailing segments within overlap_tokens
                overlap_texts, overlap_pages, oc = [], [], 0
                for t, p in reversed(list(zip(current_texts, current_pages))):
                    tt = estimate_tokens(t)
                    if oc + tt > overlap_tokens:
                        break
                    overlap_texts.insert(0, t)
                    overlap_pages.insert(0, p)
                    oc += tt
                current_texts, current_pages, current_tokens = overlap_texts, overlap_pages, oc

            current_texts.append(text)
            current_pages.append(seg.page_number)
            current_tokens += seg_tokens

        # Flush remaining
        if current_texts:
            chunk_text = "\n\n".join(current_texts)
            chunks.append(ChunkData(
                content=chunk_text,
                ordinal=ordinal,
                chunk_type="text",
                section_path=current_section,
                token_count=estimate_tokens(chunk_text),
                page_start=min(current_pages),
                page_end=max(current_pages),
            ))

        return chunks

    def _chunk_from_content(
        self, content: str, max_tokens: int, overlap_tokens: int
    ) -> list[ChunkData]:
        """Fallback: split by sections when no segments available."""
        sections = self._split_by_sections(content)
        chunks: list[ChunkData] = []
        ordinal = 0

        for section_path, section_text in sections:
            text = section_text.strip()
            if not text:
                continue
            token_count = estimate_tokens(text)
            if token_count <= max_tokens:
                chunks.append(ChunkData(
                    content=text, ordinal=ordinal, chunk_type="text",
                    section_path=section_path, token_count=token_count,
                ))
                ordinal += 1
            else:
                for para in re.split(r"\n\s*\n", text):
                    para = para.strip()
                    if para:
                        chunks.append(ChunkData(
                            content=para, ordinal=ordinal, chunk_type="text",
                            section_path=section_path, token_count=estimate_tokens(para),
                        ))
                        ordinal += 1
        return chunks

    def _split_by_sections(self, content: str) -> list[tuple[str | None, str]]:
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
        return sections

    def _merge_small_chunks(self, chunks, min_tokens, max_tokens):
        if not chunks:
            return []
        merged: list[ChunkData] = [chunks[0]]
        for chunk in chunks[1:]:
            prev = merged[-1]
            pt = prev.token_count or estimate_tokens(prev.content)
            ct = chunk.token_count or estimate_tokens(chunk.content)
            if pt < min_tokens and pt + ct <= max_tokens:
                prev.content = prev.content + "\n\n" + chunk.content
                prev.token_count = estimate_tokens(prev.content)
                pages = [x for x in [prev.page_start, prev.page_end, chunk.page_start, chunk.page_end] if x is not None]
                prev.page_start = min(pages) if pages else None
                prev.page_end = max(pages) if pages else None
            else:
                merged.append(chunk)
        return merged
