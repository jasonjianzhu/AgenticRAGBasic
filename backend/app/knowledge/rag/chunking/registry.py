"""Chunker registry for managing chunker implementations."""
from __future__ import annotations

import structlog

from app.knowledge.rag.chunking.base import BaseChunker

logger = structlog.get_logger(__name__)


class ChunkerRegistry:
    """Registry for chunker implementations. Get chunker by name."""

    def __init__(self) -> None:
        self._chunkers: dict[str, BaseChunker] = {}

    def register(self, chunker: BaseChunker) -> None:
        """Register a chunker instance.

        Args:
            chunker: A BaseChunker implementation.

        Raises:
            ValueError: If a chunker with the same name is already registered.
        """
        name = chunker.name
        if name in self._chunkers:
            raise ValueError(f"Chunker '{name}' is already registered")
        self._chunkers[name] = chunker
        logger.info("chunker_registered", name=name)

    def get(self, name: str) -> BaseChunker:
        """Get a chunker by name.

        Args:
            name: The chunker name identifier.

        Returns:
            The registered BaseChunker instance.

        Raises:
            KeyError: If no chunker with the given name is registered.
        """
        if name not in self._chunkers:
            raise KeyError(f"Chunker '{name}' is not registered")
        return self._chunkers[name]

    def list_names(self) -> list[str]:
        """Return a sorted list of registered chunker names."""
        return sorted(self._chunkers.keys())


def _build_default_registry() -> ChunkerRegistry:
    """Build and return the default registry with all built-in chunkers."""
    from app.knowledge.rag.chunking.docling_hybrid import DoclingHybridChunker
    from app.knowledge.rag.chunking.markdown_header import MarkdownHeaderChunker
    from app.knowledge.rag.chunking.recursive_token import RecursiveTokenChunker
    from app.knowledge.rag.chunking.table import TableChunker

    registry = ChunkerRegistry()
    registry.register(DoclingHybridChunker())
    registry.register(MarkdownHeaderChunker())
    registry.register(RecursiveTokenChunker())
    registry.register(TableChunker())
    return registry


default_registry: ChunkerRegistry = _build_default_registry()
