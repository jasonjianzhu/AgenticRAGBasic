from __future__ import annotations

from dataclasses import replace

from app.rag.chunking.models import ChunkDraft, ChunkingOptions
from app.rag.parsing.models import ParsedBlock, ParsedBlockType, ParsedDocument


class TableChunker:
    name = "table_chunker"

    def chunk(self, document: ParsedDocument, options: ChunkingOptions) -> list[ChunkDraft]:
        chunks: list[ChunkDraft] = []
        for block in document.blocks:
            if block.type != ParsedBlockType.TABLE:
                continue
            chunks.extend(self.chunk_block(block, options))
        return chunks

    def chunk_block(self, block: ParsedBlock, options: ChunkingOptions) -> list[ChunkDraft]:
        lines = [line.rstrip() for line in block.text.splitlines() if line.strip()]
        if len(lines) < 3:
            return [
                ChunkDraft(
                    chunk_type="table",
                    content=block.text.strip(),
                    page_start=block.page_start,
                    page_end=block.page_end or block.page_start,
                    metadata={
                        **block.metadata,
                        "table_header": [],
                        "table_row_start": 1,
                        "table_row_count": max(0, len(lines) - 2),
                    },
                )
            ]

        header_line = lines[0]
        separator_line = lines[1]
        row_lines = lines[2:]
        header_cells = self._parse_markdown_row(header_line)
        max_rows = self._estimate_max_rows(header_line, separator_line, row_lines, options.target_chars)

        chunks: list[ChunkDraft] = []
        for row_start in range(0, len(row_lines), max_rows):
            current_rows = row_lines[row_start : row_start + max_rows]
            content = "\n".join([header_line, separator_line, *current_rows]).strip()
            chunks.append(
                ChunkDraft(
                    chunk_type="table",
                    content=content,
                    page_start=block.page_start,
                    page_end=block.page_end or block.page_start,
                    metadata={
                        **block.metadata,
                        "table_header": header_cells,
                        "table_row_start": row_start + 1,
                        "table_row_count": len(current_rows),
                    },
                )
            )
        return chunks

    def _estimate_max_rows(self, header_line: str, separator_line: str, row_lines: list[str], target_chars: int) -> int:
        if not row_lines:
            return 1
        fixed_chars = len(header_line) + len(separator_line) + 2
        avg_row_chars = max(1, sum(len(line) for line in row_lines) // len(row_lines))
        available = max(avg_row_chars, target_chars - fixed_chars)
        max_rows = max(1, available // avg_row_chars)
        return max(1, max_rows + 1)

    def _parse_markdown_row(self, row: str) -> list[str]:
        stripped = row.strip().strip("|")
        if not stripped:
            return []
        return [cell.strip() for cell in stripped.split("|")]
