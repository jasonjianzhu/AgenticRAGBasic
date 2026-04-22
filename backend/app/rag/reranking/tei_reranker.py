"""TEI Reranker client.

Calls the TEI rerank HTTP endpoint to re-score candidate documents.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.common.core.logging import get_logger
from app.rag.reranking.base import BaseReranker, RerankResult

logger = get_logger(__name__)


class TEIReranker(BaseReranker):
    """Reranker using TEI (Text Embeddings Inference) rerank endpoint.

    Args:
        base_url: TEI server base URL (e.g. "http://localhost:8082").
        api_key: Optional API key.
        timeout: HTTP request timeout in seconds (default 30).
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        """Rerank documents via TEI rerank endpoint."""
        if not documents:
            return []

        url = f"{self._base_url}/rerank"
        payload: dict[str, Any] = {
            "query": query,
            "texts": documents,
        }
        if top_n is not None:
            payload["truncate"] = True

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            response.raise_for_status()
            raw = response.json()

        # TEI returns list of {index, score} sorted by score desc
        results = [
            RerankResult(
                index=item["index"],
                score=item["score"],
                content=documents[item["index"]],
            )
            for item in raw
        ]

        # Sort by score descending (TEI usually returns sorted, but be safe)
        results.sort(key=lambda r: r.score, reverse=True)

        if top_n is not None:
            results = results[:top_n]

        logger.info(
            "rerank_complete",
            query_len=len(query),
            candidates=len(documents),
            returned=len(results),
        )
        return results
