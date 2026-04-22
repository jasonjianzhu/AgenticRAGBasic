"""Abstract base classes and data models for document chunking."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field

from app.knowledge.rag.parsing.base import ParsedDocument


@dataclass
class ChunkData:
    """A single chunk produced by a chunker."""

    content: str
    ordinal: int
    chunk_type: str = "text"  # text, table, image_caption
    section_path: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    token_count: int | None = None
    metadata: dict = field(default_factory=dict)


class BaseChunker(abc.ABC):
    """Abstract base class for document chunkers."""

    @abc.abstractmethod
    def chunk(self, parsed: ParsedDocument, **kwargs) -> list[ChunkData]:
        """Split a parsed document into chunks.

        Args:
            parsed: A ParsedDocument with extracted content.
            **kwargs: Additional chunker-specific options.

        Returns:
            A list of ChunkData instances.
        """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Chunker name identifier."""
