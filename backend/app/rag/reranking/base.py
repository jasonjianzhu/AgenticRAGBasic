"""Abstract base class for rerankers."""
from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class RerankResult:
    """A single reranked item with its new score."""

    index: int  # original index in the input list
    score: float
    content: str


class BaseReranker(abc.ABC):
    """Abstract base class for rerankers.

    Rerankers take a query and a list of candidate texts,
    and return them re-scored and re-ordered by relevance.
    """

    @abc.abstractmethod
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        """Rerank documents by relevance to the query.

        Args:
            query: The search query.
            documents: List of candidate document texts.
            top_n: Return only top N results (None = return all).

        Returns:
            List of RerankResult sorted by score descending.
        """
