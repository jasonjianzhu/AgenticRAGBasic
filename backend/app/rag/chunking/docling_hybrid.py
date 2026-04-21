"""Structure-aware hybrid chunker that respects document structure."""
from __future__ import annotations

import re

import structlog

from app.rag.chunking.base import BaseChunker, ChunkData
from app.rag.chunking.utils import estimate_tokens
from app.rag.parsing.base import ParsedDocument

logger = structlog.get_logger(__name__)

# Regex to match markdown headers
_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


class DoclingHybridChunker(BaseChunker):
    """Structure-aware chunker that respects document section boundaries.

    Splits by section headers in markdown content, then enforces token limits
    with overlap between chunks.

    Args:
        min_tokens: Minimum tokens per chunk (default 300).
        max_tokens: Maximum tokens per chunk (default 600).
        overlap_tokens: Overlap between consecutive chunks (default 50).
    """

    def __init__(
        self,
        min_tokens: int = 300,
        max_tokens: int = 600,
        overlap_tokens: int = 50,
    ) -> None:
        self._min_tokens = min_tokens
        self._max_tokens = max_tokens
        self._overlap_tokens = overlap_tokens

    @property
    def name(self) -> str:
        return "docling_hybrid"

    def chunk(self, parsed: ParsedDocument, **kwargs) -> list[ChunkData]:
        """Split a parsed document into structure-aware chunks."""
        min_tokens = kwargs.get("min_tokens", self._min_tokens)
        max_tokens = kwargs.get("max_tokens", self._max_tokens)
        overlap_tokens = kwargs.get("overlap_tokens", self._overlap_tokens)

        sections = self._split_by_sections(parsed.content)
        raw_chunks: list[ChunkData] = []
        ordinal = 0

        for section_path, section_text in sections:
            text = section_text.strip()
            if not text:
                continue

            token_count = estimate_tokens(text)

            if token_count <= max_tokens:
                # Section fits in one chunk
                raw_chunks.append(
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
                # Section too large, split by paragraphs with overlap
                sub_chunks = self._split_large_section(
                    text, section_path, max_tokens, overlap_tokens, ordinal
                )
                raw_chunks.extend(sub_chunks)
                ordinal += len(sub_chunks)

        # Merge small consecutive chunks from the same section
        merged = self._merge_small_chunks(raw_chunks, min_tokens, max_tokens)

        # Re-number ordinals and compute token counts
        for i, c in enumerate(merged):
            c.ordinal = i
            c.token_count = estimate_tokens(c.content)

        logger.info(
            "docling_hybrid_chunked",
            total_chunks=len(merged),
            content_length=len(parsed.content),
        )
        return merged

    def _split_by_sections(self, content: str) -> list[tuple[str | None, str]]:
        """Split markdown content by header boundaries.

        Returns list of (section_path, section_text) tuples.
        """
        if not content.strip():
            return []

        lines = content.split("\n")
        sections: list[tuple[str | None, str]] = []
        header_stack: list[tuple[int, str]] = []  # (level, title)
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

    def _split_large_section(
        self,
        text: str,
        section_path: str | None,
        max_tokens: int,
        overlap_tokens: int,
        start_ordinal: int,
    ) -> list[ChunkData]:
        """Split a large section into smaller chunks with overlap."""
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
                # Emit current chunk
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

                # Overlap: keep trailing parts that fit within overlap_tokens
                overlap_parts: list[str] = []
                overlap_count = 0
                for p in reversed(current_parts):
                    pt = estimate_tokens(p)
                    if overlap_count + pt > overlap_tokens:
                        break
                    overlap_parts.insert(0, p)
                    overlap_count += pt

                current_parts = overlap_parts
                current_tokens = overlap_count

            current_parts.append(para)
            current_tokens += para_tokens

        # Flush remaining
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

    def _merge_small_chunks(
        self,
        chunks: list[ChunkData],
        min_tokens: int,
        max_tokens: int,
    ) -> list[ChunkData]:
        """Merge consecutive small chunks from the same section."""
        if not chunks:
            return []

        merged: list[ChunkData] = [chunks[0]]

        for chunk in chunks[1:]:
            prev = merged[-1]
            prev_tokens = prev.token_count or estimate_tokens(prev.content)
            curr_tokens = chunk.token_count or estimate_tokens(chunk.content)

            if (
                prev_tokens < min_tokens
                and prev.section_path == chunk.section_path
                and prev_tokens + curr_tokens <= max_tokens
            ):
                # Merge into previous
                prev.content = prev.content + "\n\n" + chunk.content
                prev.token_count = estimate_tokens(prev.content)
            else:
                merged.append(chunk)

        return merged
