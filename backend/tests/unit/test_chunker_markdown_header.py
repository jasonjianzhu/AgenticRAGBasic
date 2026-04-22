"""Tests for the markdown_header chunker."""
from __future__ import annotations

import pytest

from app.knowledge.rag.chunking.markdown_header import MarkdownHeaderChunker
from app.knowledge.rag.chunking.base import ChunkData
from app.knowledge.rag.chunking.utils import estimate_tokens
from app.knowledge.rag.parsing.base import ParsedDocument


def _make_doc(content: str) -> ParsedDocument:
    return ParsedDocument(content=content, pages=[], tables=[])


class TestMarkdownHeaderChunkerProperties:
    """Test basic properties."""

    def test_name(self):
        chunker = MarkdownHeaderChunker()
        assert chunker.name == "markdown_header"

    def test_is_base_chunker(self):
        from app.knowledge.rag.chunking.base import BaseChunker
        assert isinstance(MarkdownHeaderChunker(), BaseChunker)


class TestMarkdownHeaderChunkerEmpty:
    """Test edge cases."""

    def test_empty_content(self):
        chunker = MarkdownHeaderChunker()
        doc = _make_doc("")
        assert chunker.chunk(doc) == []

    def test_whitespace_only(self):
        chunker = MarkdownHeaderChunker()
        doc = _make_doc("   \n\n   ")
        assert chunker.chunk(doc) == []


class TestMarkdownHeaderChunkerSplitting:
    """Test header-based splitting."""

    def test_single_section(self):
        content = "# Title\n\nSome content here."
        chunker = MarkdownHeaderChunker()
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert len(chunks) == 1
        assert "Title" in chunks[0].content

    def test_multiple_h1_sections(self):
        content = (
            "# Chapter 1\n\nContent 1.\n\n"
            "# Chapter 2\n\nContent 2.\n\n"
            "# Chapter 3\n\nContent 3."
        )
        chunker = MarkdownHeaderChunker()
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert len(chunks) == 3

    def test_nested_headers_section_path(self):
        content = (
            "# Chapter 1\n\nIntro.\n\n"
            "## Section 1.1\n\nDetails.\n\n"
            "### Subsection 1.1.1\n\nMore details."
        )
        chunker = MarkdownHeaderChunker()
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)

        # Check section paths
        paths = [c.section_path for c in chunks]
        assert any(p and "Chapter 1" in p for p in paths)
        # Nested path should contain >
        nested = [p for p in paths if p and ">" in p]
        assert len(nested) >= 1
        # Deepest path should have all levels
        deepest = [p for p in paths if p and p.count(">") >= 2]
        assert len(deepest) >= 1

    def test_section_path_format(self):
        content = (
            "# A\n\nText.\n\n"
            "## B\n\nText.\n\n"
            "### C\n\nText."
        )
        chunker = MarkdownHeaderChunker()
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        # Find the deepest chunk
        deep_chunk = [c for c in chunks if c.section_path and c.section_path.count(">") == 2]
        assert len(deep_chunk) == 1
        assert deep_chunk[0].section_path == "A > B > C"

    def test_ordinals_sequential(self):
        content = "# A\n\nText.\n\n# B\n\nText.\n\n# C\n\nText."
        chunker = MarkdownHeaderChunker()
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        ordinals = [c.ordinal for c in chunks]
        assert ordinals == list(range(len(chunks)))

    def test_content_without_headers(self):
        content = "Just plain text without any headers.\n\nAnother paragraph."
        chunker = MarkdownHeaderChunker()
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert len(chunks) == 1
        assert chunks[0].section_path is None


class TestMarkdownHeaderChunkerLargeSections:
    """Test splitting of large sections."""

    def test_large_section_split_by_paragraphs(self):
        paragraphs = [f"Paragraph {i} with enough words to count as tokens." for i in range(30)]
        content = "# Big Section\n\n" + "\n\n".join(paragraphs)
        chunker = MarkdownHeaderChunker(max_tokens=50)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1
        # All chunks should reference the same section
        for chunk in chunks:
            assert chunk.section_path is not None
            assert "Big Section" in chunk.section_path

    def test_all_chunks_have_token_count(self):
        content = "# Title\n\nContent.\n\n# Another\n\nMore."
        chunker = MarkdownHeaderChunker()
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        for chunk in chunks:
            assert chunk.token_count is not None
            assert chunk.token_count >= 0

    def test_kwargs_override(self):
        paragraphs = ["Some text content here. " * 10 for _ in range(10)]
        content = "# Section\n\n" + "\n\n".join(paragraphs)
        chunker = MarkdownHeaderChunker()
        doc = _make_doc(content)
        chunks = chunker.chunk(doc, max_tokens=20)
        assert len(chunks) > 1


class TestMarkdownHeaderChunkerMixedLevels:
    """Test with various header levels."""

    def test_h1_to_h6(self):
        content = (
            "# H1\n\nText.\n\n"
            "## H2\n\nText.\n\n"
            "### H3\n\nText.\n\n"
            "#### H4\n\nText.\n\n"
            "##### H5\n\nText.\n\n"
            "###### H6\n\nText."
        )
        chunker = MarkdownHeaderChunker()
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert len(chunks) == 6

    def test_sibling_sections_reset_path(self):
        content = (
            "# Chapter 1\n\n"
            "## Section A\n\nText.\n\n"
            "## Section B\n\nText."
        )
        chunker = MarkdownHeaderChunker()
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        paths = [c.section_path for c in chunks if c.section_path]
        # Section B should not contain Section A
        section_b_paths = [p for p in paths if "Section B" in p]
        assert len(section_b_paths) >= 1
        for p in section_b_paths:
            assert "Section A" not in p
