"""Abstract base classes and data models for embedding providers."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class EmbeddingResult:
    """Result of embedding a single text.

    Attributes:
        dense: Dense vector (e.g. 1024-dim for BGE-M3).
        sparse: Sparse vector as token_id -> weight mapping.
    """

    dense: list[float]
    sparse: dict[int, float] = field(default_factory=dict)


class EmbeddingProvider(abc.ABC):
    """Abstract base class for embedding providers.

    Implementations must support both dense and sparse embeddings
    for hybrid retrieval (dense + sparse → RRF fusion).
    """

    @abc.abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed a batch of texts, returning dense + sparse vectors.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of EmbeddingResult, one per input text.
        """

    @abc.abstractmethod
    async def embed_query(self, query: str) -> EmbeddingResult:
        """Embed a single query text.

        Args:
            query: The query string to embed.

        Returns:
            An EmbeddingResult with dense and sparse vectors.
        """

    @property
    @abc.abstractmethod
    def dimension(self) -> int:
        """Return the dense vector dimension."""
