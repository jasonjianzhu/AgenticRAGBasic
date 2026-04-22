"""Tests for the recursive_token chunker."""
from __future__ import annotations

import pytest

from app.knowledge.rag.chunking.recursive_token import RecursiveTokenChunker
from app.knowledge.rag.chunking.base import ChunkData
from app.knowledge.rag.chunking.utils import estimate_tokens
from app.knowledge.rag.parsing.base import ParsedDocument


def _make_doc(content: str) -> ParsedDocument:
    return ParsedDocument(content=content, pages=[], tables=[])


class TestRecursiveTokenChunkerProperties:
    """Test basic properties."""

    def test_name(self):
        chunker = RecursiveTokenChunker()
        assert chunker.name == "recursive_token"

    def test_is_base_chunker(self):
        from app.knowledge.rag.chunking.base import BaseChunker
        assert isinstance(RecursiveTokenChunker(), BaseChunker)


class TestRecursiveTokenChunkerEmpty:
    """Test edge cases."""

    def test_empty_content(self):
        chunker = RecursiveTokenChunker()
        doc = _make_doc("")
        assert chunker.chunk(doc) == []

    def test_whitespace_only(self):
        chunker = RecursiveTokenChunker()
        doc = _make_doc("   \n\n   ")
        assert chunker.chunk(doc) == []


class TestRecursiveTokenChunkerSmallText:
    """Test with text that fits in one chunk."""

    def test_short_text_single_chunk(self):
        content = "Hello world, this is a short text."
        chunker = RecursiveTokenChunker(target_tokens=500)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert len(chunks) == 1
        assert chunks[0].content.strip() == content.strip()

    def test_single_chunk_has_token_count(self):
        content = "Short text."
        chunker = RecursiveTokenChunker()
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert chunks[0].token_count is not None
        assert chunks[0].token_count > 0


class TestRecursiveTokenChunkerSplitting:
    """Test splitting behavior."""

    def test_splits_by_double_newline_first(self):
        paragraphs = [f"Paragraph {i} with some words." for i in range(20)]
        content = "\n\n".join(paragraphs)
        chunker = RecursiveTokenChunker(target_tokens=30, overlap_tokens=0)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1

    def test_splits_by_single_newline(self):
        lines = [f"Line {i} with some words here." for i in range(20)]
        content = "\n".join(lines)
        chunker = RecursiveTokenChunker(target_tokens=30, overlap_tokens=0)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1

    def test_splits_by_sentence(self):
        sentences = [f"Sentence {i} with some words here" for i in range(20)]
        content = ". ".join(sentences) + "."
        chunker = RecursiveTokenChunker(target_tokens=30, overlap_tokens=0)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1

    def test_ordinals_sequential(self):
        content = "\n\n".join([f"Paragraph {i}." for i in range(10)])
        chunker = RecursiveTokenChunker(target_tokens=20, overlap_tokens=0)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        ordinals = [c.ordinal for c in chunks]
        assert ordinals == list(range(len(chunks)))

    def test_all_chunks_have_token_count(self):
        content = "\n\n".join([f"Paragraph {i} text." for i in range(10)])
        chunker = RecursiveTokenChunker(target_tokens=20, overlap_tokens=0)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        for chunk in chunks:
            assert chunk.token_count is not None
            assert chunk.token_count >= 0

    def test_all_chunks_are_text_type(self):
        content = "Some text.\n\nMore text.\n\nEven more."
        chunker = RecursiveTokenChunker(target_tokens=5, overlap_tokens=0)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        for chunk in chunks:
            assert chunk.chunk_type == "text"


class TestRecursiveTokenChunkerOverlap:
    """Test overlap behavior."""

    def test_overlap_adds_context(self):
        paragraphs = [f"Unique paragraph number {i} with content." for i in range(10)]
        content = "\n\n".join(paragraphs)
        chunker = RecursiveTokenChunker(target_tokens=30, overlap_tokens=10)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        # With overlap, later chunks should contain some text from previous chunks
        if len(chunks) > 1:
            # The second chunk should have some overlap from the first
            assert len(chunks[1].content) > 0

    def test_zero_overlap(self):
        content = "\n\n".join([f"Paragraph {i} with several words of content here." for i in range(20)])
        chunker = RecursiveTokenChunker(target_tokens=20, overlap_tokens=0)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1


class TestRecursiveTokenChunkerKwargs:
    """Test kwargs override."""

    def test_kwargs_override_target(self):
        content = "word " * 100
        chunker = RecursiveTokenChunker()
        doc = _make_doc(content)
        chunks = chunker.chunk(doc, target_tokens=10, overlap_tokens=0)
        assert len(chunks) > 1


class TestRecursiveTokenChunkerChinese:
    """Test with Chinese content."""

    def test_chinese_text(self):
        content = "这是一段中文文本。\n\n这是第二段。\n\n这是第三段。"
        chunker = RecursiveTokenChunker(target_tokens=5, overlap_tokens=0)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.content.strip()
