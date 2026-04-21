"""Tests for the table chunker."""
from __future__ import annotations

import pytest

from app.rag.chunking.table import TableChunker
from app.rag.chunking.base import ChunkData
from app.rag.chunking.utils import estimate_tokens
from app.rag.parsing.base import ParsedDocument, ParsedTable


def _make_doc(tables: list[ParsedTable]) -> ParsedDocument:
    return ParsedDocument(content="", pages=[], tables=tables)


def _make_table(content: str, page: int = 1, caption: str | None = None) -> ParsedTable:
    return ParsedTable(content=content, page_number=page, caption=caption)


SIMPLE_TABLE = (
    "| Name | Value |\n"
    "|------|-------|\n"
    "| A    | 1     |\n"
    "| B    | 2     |\n"
    "| C    | 3     |"
)


class TestTableChunkerProperties:
    """Test basic properties."""

    def test_name(self):
        chunker = TableChunker()
        assert chunker.name == "table"

    def test_is_base_chunker(self):
        from app.rag.chunking.base import BaseChunker
        assert isinstance(TableChunker(), BaseChunker)


class TestTableChunkerEmpty:
    """Test edge cases."""

    def test_no_tables(self):
        chunker = TableChunker()
        doc = _make_doc([])
        assert chunker.chunk(doc) == []

    def test_empty_table_content(self):
        chunker = TableChunker()
        doc = _make_doc([_make_table("")])
        assert chunker.chunk(doc) == []

    def test_whitespace_table(self):
        chunker = TableChunker()
        doc = _make_doc([_make_table("   \n  ")])
        assert chunker.chunk(doc) == []


class TestTableChunkerSingleTable:
    """Test with a single table."""

    def test_small_table_single_chunk(self):
        chunker = TableChunker(max_tokens=1000)
        doc = _make_doc([_make_table(SIMPLE_TABLE)])
        chunks = chunker.chunk(doc)
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "table"
        assert "Name" in chunks[0].content
        assert "Value" in chunks[0].content

    def test_table_has_page_info(self):
        chunker = TableChunker()
        doc = _make_doc([_make_table(SIMPLE_TABLE, page=5)])
        chunks = chunker.chunk(doc)
        assert chunks[0].page_start == 5
        assert chunks[0].page_end == 5

    def test_table_has_caption_in_metadata(self):
        chunker = TableChunker()
        doc = _make_doc([_make_table(SIMPLE_TABLE, caption="Table 1: Test Data")])
        chunks = chunker.chunk(doc)
        assert chunks[0].metadata.get("caption") == "Table 1: Test Data"

    def test_table_has_token_count(self):
        chunker = TableChunker()
        doc = _make_doc([_make_table(SIMPLE_TABLE)])
        chunks = chunker.chunk(doc)
        assert chunks[0].token_count is not None
        assert chunks[0].token_count > 0

    def test_ordinal_starts_at_zero(self):
        chunker = TableChunker()
        doc = _make_doc([_make_table(SIMPLE_TABLE)])
        chunks = chunker.chunk(doc)
        assert chunks[0].ordinal == 0


class TestTableChunkerMultipleTables:
    """Test with multiple tables."""

    def test_multiple_tables(self):
        table1 = _make_table(SIMPLE_TABLE, page=1, caption="Table 1")
        table2 = _make_table(SIMPLE_TABLE, page=3, caption="Table 2")
        chunker = TableChunker()
        doc = _make_doc([table1, table2])
        chunks = chunker.chunk(doc)
        assert len(chunks) == 2
        assert chunks[0].ordinal == 0
        assert chunks[1].ordinal == 1
        assert chunks[0].page_start == 1
        assert chunks[1].page_start == 3


class TestTableChunkerLargeTable:
    """Test splitting of large tables."""

    def test_large_table_split_preserves_headers(self):
        # Create a large table
        header = "| Col1 | Col2 | Col3 |\n|------|------|------|\n"
        rows = "".join([f"| Row{i}A | Row{i}B | Row{i}C |\n" for i in range(50)])
        large_table = header + rows

        chunker = TableChunker(max_tokens=30)
        doc = _make_doc([_make_table(large_table)])
        chunks = chunker.chunk(doc)

        assert len(chunks) > 1
        # Each chunk should contain the header
        for chunk in chunks:
            assert "Col1" in chunk.content
            assert "Col2" in chunk.content
            assert chunk.chunk_type == "table"

    def test_large_table_all_rows_present(self):
        header = "| ID | Name |\n|-----|------|\n"
        rows = "".join([f"| {i} | Item{i} |\n" for i in range(20)])
        large_table = header + rows

        chunker = TableChunker(max_tokens=30)
        doc = _make_doc([_make_table(large_table)])
        chunks = chunker.chunk(doc)

        # All data rows should appear in some chunk
        all_content = " ".join(c.content for c in chunks)
        for i in range(20):
            assert f"Item{i}" in all_content

    def test_split_table_ordinals_sequential(self):
        header = "| A | B |\n|---|---|\n"
        rows = "".join([f"| {i} | val |\n" for i in range(50)])
        large_table = header + rows

        chunker = TableChunker(max_tokens=20)
        doc = _make_doc([_make_table(large_table)])
        chunks = chunker.chunk(doc)
        ordinals = [c.ordinal for c in chunks]
        assert ordinals == list(range(len(chunks)))

    def test_kwargs_override_max_tokens(self):
        header = "| A | B |\n|---|---|\n"
        rows = "".join([f"| {i} | val |\n" for i in range(30)])
        large_table = header + rows

        chunker = TableChunker(max_tokens=10000)
        doc = _make_doc([_make_table(large_table)])
        # Override with small max_tokens
        chunks = chunker.chunk(doc, max_tokens=20)
        assert len(chunks) > 1
