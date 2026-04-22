"""Abstract base classes and data models for vector stores."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class VectorPoint:
    """A point to upsert into the vector store.

    Attributes:
        id: Unique point identifier (string UUID).
        dense_vector: Dense embedding vector.
        sparse_vector: Sparse embedding as token_id -> weight.
        payload: Metadata payload for filtering and retrieval.
    """

    id: str
    dense_vector: list[float]
    sparse_vector: dict[int, float] = field(default_factory=dict)
    payload: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    """A single search result from the vector store.

    Attributes:
        id: Point identifier.
        score: Similarity/relevance score.
        payload: Metadata payload.
    """

    id: str
    score: float
    payload: dict = field(default_factory=dict)


class VectorStore(abc.ABC):
    """Abstract base class for vector store backends."""

    @abc.abstractmethod
    async def ensure_collection(self) -> None:
        """Ensure the collection exists with proper configuration.

        Creates the collection if it doesn't exist, or verifies
        the existing collection has the correct schema.
        """

    @abc.abstractmethod
    async def upsert(self, points: list[VectorPoint]) -> None:
        """Upsert points into the collection.

        Args:
            points: List of VectorPoint instances to upsert.
        """

    @abc.abstractmethod
    async def delete(self, point_ids: list[str]) -> None:
        """Delete points by their IDs.

        Args:
            point_ids: List of point ID strings to delete.
        """

    @abc.abstractmethod
    async def search_dense(
        self,
        vector: list[float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """Search using dense vector similarity.

        Args:
            vector: Query dense vector.
            limit: Maximum number of results.
            filters: Optional metadata filters.

        Returns:
            List of SearchResult sorted by score descending.
        """

    @abc.abstractmethod
    async def search_sparse(
        self,
        sparse_vector: dict[int, float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """Search using sparse vector similarity.

        Args:
            sparse_vector: Query sparse vector (token_id -> weight).
            limit: Maximum number of results.
            filters: Optional metadata filters.

        Returns:
            List of SearchResult sorted by score descending.
        """
