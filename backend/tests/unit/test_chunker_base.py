"""Tests for ChunkData, BaseChunker, and ChunkerRegistry."""
from __future__ import annotations

import pytest

from app.rag.chunking.base import BaseChunker, ChunkData
from app.rag.parsing.base import ParsedDocument


# ---------------------------------------------------------------------------
# ChunkData tests
# ---------------------------------------------------------------------------

class TestChunkData:
    """Tests for the ChunkData dataclass."""

    def test_minimal_creation(self):
        chunk = ChunkData(content="hello", ordinal=0)
        assert chunk.content == "hello"
        assert chunk.ordinal == 0
        assert chunk.chunk_type == "text"
        assert chunk.section_path is None
        assert chunk.page_start is None
        assert chunk.page_end is None
        assert chunk.token_count is None
        assert chunk.metadata == {}

    def test_full_creation(self):
        chunk = ChunkData(
            content="table data",
            ordinal=5,
            chunk_type="table",
            section_path="Chapter 1 > Section 2",
            page_start=10,
            page_end=12,
            token_count=42,
            metadata={"caption": "Table 1"},
        )
        assert chunk.chunk_type == "table"
        assert chunk.section_path == "Chapter 1 > Section 2"
        assert chunk.page_start == 10
        assert chunk.page_end == 12
        assert chunk.token_count == 42
        assert chunk.metadata == {"caption": "Table 1"}

    def test_metadata_default_is_independent(self):
        """Each ChunkData should get its own metadata dict."""
        c1 = ChunkData(content="a", ordinal=0)
        c2 = ChunkData(content="b", ordinal=1)
        c1.metadata["key"] = "value"
        assert "key" not in c2.metadata


# ---------------------------------------------------------------------------
# BaseChunker ABC tests
# ---------------------------------------------------------------------------

class _DummyChunker(BaseChunker):
    """Concrete chunker for testing."""

    @property
    def name(self) -> str:
        return "dummy"

    def chunk(self, parsed: ParsedDocument, **kwargs) -> list[ChunkData]:
        return [ChunkData(content=parsed.content, ordinal=0)]


class TestBaseChunker:
    """Tests for the BaseChunker abstract base class."""

    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            BaseChunker()  # type: ignore[abstract]

    def test_concrete_subclass(self):
        chunker = _DummyChunker()
        assert chunker.name == "dummy"

    def test_chunk_returns_list(self):
        chunker = _DummyChunker()
        parsed = ParsedDocument(content="hello world", pages=[], tables=[])
        result = chunker.chunk(parsed)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].content == "hello world"

    def test_incomplete_subclass_raises(self):
        """A subclass that doesn't implement all abstract methods can't be instantiated."""

        class Incomplete(BaseChunker):
            @property
            def name(self) -> str:
                return "incomplete"

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# ChunkerRegistry tests
# ---------------------------------------------------------------------------

from app.rag.chunking.registry import ChunkerRegistry


class TestChunkerRegistry:
    """Tests for the ChunkerRegistry."""

    def test_register_and_get(self):
        registry = ChunkerRegistry()
        chunker = _DummyChunker()
        registry.register(chunker)
        assert registry.get("dummy") is chunker

    def test_get_unknown_raises(self):
        registry = ChunkerRegistry()
        with pytest.raises(KeyError, match="not registered"):
            registry.get("nonexistent")

    def test_register_duplicate_raises(self):
        registry = ChunkerRegistry()
        registry.register(_DummyChunker())
        with pytest.raises(ValueError, match="already registered"):
            registry.register(_DummyChunker())

    def test_list_names_empty(self):
        registry = ChunkerRegistry()
        assert registry.list_names() == []

    def test_list_names_sorted(self):
        registry = ChunkerRegistry()

        class ChunkerA(BaseChunker):
            @property
            def name(self) -> str:
                return "zzz"

            def chunk(self, parsed, **kwargs):
                return []

        class ChunkerB(BaseChunker):
            @property
            def name(self) -> str:
                return "aaa"

            def chunk(self, parsed, **kwargs):
                return []

        registry.register(ChunkerA())
        registry.register(ChunkerB())
        assert registry.list_names() == ["aaa", "zzz"]


# ---------------------------------------------------------------------------
# Default registry tests
# ---------------------------------------------------------------------------

class TestDefaultRegistry:
    """Tests for the default registry with all built-in chunkers."""

    def test_default_registry_has_all_chunkers(self):
        from app.rag.chunking.registry import default_registry

        names = default_registry.list_names()
        assert "docling_hybrid" in names
        assert "markdown_header" in names
        assert "recursive_token" in names
        assert "table" in names

    def test_default_registry_get_each(self):
        from app.rag.chunking.registry import default_registry

        for name in ["docling_hybrid", "markdown_header", "recursive_token", "table"]:
            chunker = default_registry.get(name)
            assert chunker.name == name
