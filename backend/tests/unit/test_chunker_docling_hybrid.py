"""Tests for the docling_hybrid chunker."""
from __future__ import annotations

import pytest

from app.rag.chunking.docling_hybrid import DoclingHybridChunker
from app.rag.chunking.base import ChunkData
from app.rag.chunking.utils import estimate_tokens
from app.rag.parsing.base import ParsedDocument


def _make_doc(content: str) -> ParsedDocument:
    return ParsedDocument(content=content, pages=[], tables=[])


class TestDoclingHybridChunkerProperties:
    """Test basic properties."""

    def test_name(self):
        chunker = DoclingHybridChunker()
        assert chunker.name == "docling_hybrid"

    def test_is_base_chunker(self):
        from app.rag.chunking.base import BaseChunker
        assert isinstance(DoclingHybridChunker(), BaseChunker)


class TestDoclingHybridChunkerEmpty:
    """Test edge cases with empty/minimal content."""

    def test_empty_content(self):
        chunker = DoclingHybridChunker()
        doc = _make_doc("")
        assert chunker.chunk(doc) == []

    def test_whitespace_only(self):
        chunker = DoclingHybridChunker()
        doc = _make_doc("   \n\n   ")
        assert chunker.chunk(doc) == []


class TestDoclingHybridChunkerSections:
    """Test section-based splitting."""

    def test_single_section_small(self):
        content = "# Title\n\nSome short content here."
        chunker = DoclingHybridChunker(min_tokens=1, max_tokens=1000)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 1
        assert chunks[0].chunk_type == "text"

    def test_multiple_sections(self):
        content = (
            "# Chapter 1\n\nContent of chapter 1.\n\n"
            "# Chapter 2\n\nContent of chapter 2.\n\n"
            "# Chapter 3\n\nContent of chapter 3."
        )
        chunker = DoclingHybridChunker(min_tokens=1, max_tokens=1000)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 3

    def test_nested_sections_have_section_path(self):
        content = (
            "# Chapter 1\n\nIntro.\n\n"
            "## Section 1.1\n\nDetails.\n\n"
            "### Subsection 1.1.1\n\nMore details."
        )
        chunker = DoclingHybridChunker(min_tokens=1, max_tokens=1000)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)

        # Find the deepest section
        paths = [c.section_path for c in chunks if c.section_path]
        assert any("Chapter 1" in p for p in paths)
        # Check nested path
        deep_paths = [p for p in paths if ">" in p]
        assert len(deep_paths) >= 1

    def test_ordinals_are_sequential(self):
        content = "# A\n\nText A.\n\n# B\n\nText B.\n\n# C\n\nText C."
        chunker = DoclingHybridChunker(min_tokens=1, max_tokens=1000)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        ordinals = [c.ordinal for c in chunks]
        assert ordinals == list(range(len(chunks)))


class TestDoclingHybridChunkerTokenLimits:
    """Test token limit enforcement."""

    def test_large_section_is_split(self):
        # Create a section with many paragraphs
        paragraphs = [f"Paragraph {i} with some content to fill tokens." for i in range(50)]
        content = "# Big Section\n\n" + "\n\n".join(paragraphs)
        chunker = DoclingHybridChunker(min_tokens=10, max_tokens=50, overlap_tokens=5)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1

    def test_all_chunks_have_token_count(self):
        content = "# Title\n\nSome content.\n\n# Another\n\nMore content."
        chunker = DoclingHybridChunker(min_tokens=1, max_tokens=1000)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        for chunk in chunks:
            assert chunk.token_count is not None
            assert chunk.token_count >= 0

    def test_small_chunks_merged(self):
        """Small consecutive chunks from the same section should be merged."""
        content = "# Section\n\nA.\n\nB.\n\nC."
        chunker = DoclingHybridChunker(min_tokens=100, max_tokens=1000)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        # All small parts should be merged into one chunk
        assert len(chunks) == 1

    def test_kwargs_override_defaults(self):
        content = "# Title\n\n" + "word " * 200
        chunker = DoclingHybridChunker()
        doc = _make_doc(content)
        # Use very small max_tokens to force splitting
        chunks = chunker.chunk(doc, max_tokens=20, min_tokens=1, overlap_tokens=2)
        assert len(chunks) > 1


class TestDoclingHybridChunkerChinese:
    """Test with Chinese content."""

    def test_chinese_content(self):
        content = (
            "# 第一章 系统概述\n\n"
            "本系统是一个储能管理平台，用于监控和管理储能设备。\n\n"
            "## 1.1 系统架构\n\n"
            "系统采用微服务架构，包含多个核心模块。\n\n"
            "## 1.2 功能特点\n\n"
            "支持实时监控、告警管理、数据分析等功能。"
        )
        chunker = DoclingHybridChunker(min_tokens=1, max_tokens=1000)
        doc = _make_doc(content)
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 1
        # All chunks should have content
        for chunk in chunks:
            assert chunk.content.strip()
