"""Table-specialized chunker for ParsedDocument tables."""
from __future__ import annotations

import structlog

from app.rag.chunking.base import BaseChunker, ChunkData
from app.rag.chunking.utils import estimate_tokens
from app.rag.parsing.base import ParsedDocument

logger = structlog.get_logger(__name__)


class TableChunker(BaseChunker):
    """Specialized chunker for tables from ParsedDocument.

    Each table becomes one chunk with chunk_type="table".
    If a table is too large, it is split by rows while keeping headers.

    Args:
        max_tokens: Maximum tokens per table chunk (default 500).
    """

    def __init__(self, max_tokens: int = 500) -> None:
        self._max_tokens = max_tokens

    @property
    def name(self) -> str:
        return "table"

    def chunk(self, parsed: ParsedDocument, **kwargs) -> list[ChunkData]:
        """Create chunks from parsed document tables."""
        max_tokens = kwargs.get("max_tokens", self._max_tokens)
        chunks: list[ChunkData] = []
        ordinal = 0

        for table in parsed.tables:
            table_text = table.content.strip()
            if not table_text:
                continue

            token_count = estimate_tokens(table_text)

            if token_count <= max_tokens:
                metadata: dict = {}
                if table.caption:
                    metadata["caption"] = table.caption

                chunks.append(
                    ChunkData(
                        content=table_text,
                        ordinal=ordinal,
                        chunk_type="table",
                        page_start=table.page_number,
                        page_end=table.page_number,
                        token_count=token_count,
                        metadata=metadata,
                    )
                )
                ordinal += 1
            else:
                # Split large table by rows, preserving headers
                sub_chunks = self._split_table(
                    table_text,
                    table.page_number,
                    table.caption,
                    max_tokens,
                    ordinal,
                )
                chunks.extend(sub_chunks)
                ordinal += len(sub_chunks)

        logger.info(
            "table_chunked",
            total_chunks=len(chunks),
            table_count=len(parsed.tables),
        )
        return chunks

    def _split_table(
        self,
        table_text: str,
        page_number: int,
        caption: str | None,
        max_tokens: int,
        start_ordinal: int,
    ) -> list[ChunkData]:
        """Split a large markdown table by rows while keeping headers."""
        lines = table_text.split("\n")
        header_lines = self._extract_header_lines(lines)
        data_lines = lines[len(header_lines) :]

        if not header_lines:
            # No recognizable header, fall back to simple split
            return self._simple_split(
                table_text, page_number, caption, max_tokens, start_ordinal
            )

        header_text = "\n".join(header_lines)
        header_tokens = estimate_tokens(header_text)

        chunks: list[ChunkData] = []
        current_rows: list[str] = []
        current_tokens = header_tokens
        ordinal = start_ordinal

        for row_line in data_lines:
            row_line = row_line.rstrip()
            if not row_line:
                continue
            row_tokens = estimate_tokens(row_line)

            if current_tokens + row_tokens > max_tokens and current_rows:
                chunk_text = header_text + "\n" + "\n".join(current_rows)
                metadata: dict = {}
                if caption:
                    metadata["caption"] = caption

                chunks.append(
                    ChunkData(
                        content=chunk_text,
                        ordinal=ordinal,
                        chunk_type="table",
                        page_start=page_number,
                        page_end=page_number,
                        token_count=estimate_tokens(chunk_text),
                        metadata=metadata,
                    )
                )
                ordinal += 1
                current_rows = []
                current_tokens = header_tokens

            current_rows.append(row_line)
            current_tokens += row_tokens

        # Flush remaining rows
        if current_rows:
            chunk_text = header_text + "\n" + "\n".join(current_rows)
            metadata = {}
            if caption:
                metadata["caption"] = caption

            chunks.append(
                ChunkData(
                    content=chunk_text,
                    ordinal=ordinal,
                    chunk_type="table",
                    page_start=page_number,
                    page_end=page_number,
                    token_count=estimate_tokens(chunk_text),
                    metadata=metadata,
                )
            )

        return chunks

    def _extract_header_lines(self, lines: list[str]) -> list[str]:
        """Extract header lines from a markdown table.

        A markdown table header consists of:
        1. The header row (with | separators)
        2. The separator row (with |---|--- pattern)
        """
        header_lines: list[str] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            header_lines.append(line)
            # Check if next line is a separator row
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if self._is_separator_row(next_line):
                    header_lines.append(lines[i + 1])
                    return header_lines
            # If this line itself is a separator, we have the header
            if self._is_separator_row(stripped):
                return header_lines
            # Only look at first two lines for header detection
            if len(header_lines) >= 2:
                break
        return header_lines

    def _is_separator_row(self, line: str) -> bool:
        """Check if a line is a markdown table separator row (e.g., |---|---|)."""
        stripped = line.strip().strip("|").strip()
        if not stripped:
            return False
        parts = stripped.split("|")
        return all(
            part.strip().replace("-", "").replace(":", "") == "" for part in parts
        )

    def _simple_split(
        self,
        text: str,
        page_number: int,
        caption: str | None,
        max_tokens: int,
        start_ordinal: int,
    ) -> list[ChunkData]:
        """Simple line-based split for tables without clear headers."""
        lines = [l for l in text.split("\n") if l.strip()]
        chunks: list[ChunkData] = []
        current_lines: list[str] = []
        current_tokens = 0
        ordinal = start_ordinal

        for line in lines:
            line_tokens = estimate_tokens(line)
            if current_tokens + line_tokens > max_tokens and current_lines:
                chunk_text = "\n".join(current_lines)
                metadata: dict = {}
                if caption:
                    metadata["caption"] = caption
                chunks.append(
                    ChunkData(
                        content=chunk_text,
                        ordinal=ordinal,
                        chunk_type="table",
                        page_start=page_number,
                        page_end=page_number,
                        token_count=estimate_tokens(chunk_text),
                        metadata=metadata,
                    )
                )
                ordinal += 1
                current_lines = []
                current_tokens = 0

            current_lines.append(line)
            current_tokens += line_tokens

        if current_lines:
            chunk_text = "\n".join(current_lines)
            metadata = {}
            if caption:
                metadata["caption"] = caption
            chunks.append(
                ChunkData(
                    content=chunk_text,
                    ordinal=ordinal,
                    chunk_type="table",
                    page_start=page_number,
                    page_end=page_number,
                    token_count=estimate_tokens(chunk_text),
                    metadata=metadata,
                )
            )

        return chunks
