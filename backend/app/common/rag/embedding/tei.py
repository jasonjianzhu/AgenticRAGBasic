"""TEI (Text Embeddings Inference) client for BGE-M3 embeddings.

Calls the TEI HTTP API for dense and sparse embeddings.
Endpoints:
  - POST {base_url}/embed       → dense vectors
  - POST {base_url}/embed_sparse → sparse vectors
"""
from __future__ import annotations

from typing import Any

import httpx

from app.common.core.logging import get_logger
from app.common.rag.embedding.base import EmbeddingProvider, EmbeddingResult

logger = get_logger(__name__)


class TEIEmbeddingProvider(EmbeddingProvider):
    """Embedding provider using TEI (Text Embeddings Inference) for BGE-M3.

    Args:
        base_url: TEI server base URL (e.g. "http://localhost:8080").
        api_key: Optional API key for authentication.
        batch_size: Maximum texts per request (default 32).
        timeout: HTTP request timeout in seconds (default 60).
        dim: Dense vector dimension (default 1024 for BGE-M3).
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        batch_size: int = 32,
        timeout: float = 60.0,
        dim: int = 1024,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._batch_size = batch_size
        self._timeout = timeout
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed a batch of texts via TEI, processing in sub-batches."""
        all_results: list[EmbeddingResult] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            dense_vectors = await self._request_dense(batch)
            sparse_vectors = await self._request_sparse(batch)

            for dense, sparse in zip(dense_vectors, sparse_vectors):
                all_results.append(EmbeddingResult(dense=dense, sparse=sparse))

        return all_results

    async def embed_query(self, query: str) -> EmbeddingResult:
        """Embed a single query text."""
        results = await self.embed_texts([query])
        return results[0]

    async def _request_dense(self, texts: list[str]) -> list[list[float]]:
        """Request dense embeddings from TEI."""
        url = f"{self._base_url}/embed"
        payload: dict[str, Any] = {"inputs": texts}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def _request_sparse(self, texts: list[str]) -> list[dict[int, float]]:
        """Request sparse embeddings from TEI.

        Falls back to empty sparse vectors if the endpoint is not available
        (e.g., model doesn't support sparse output).
        """
        url = f"{self._base_url}/embed_sparse"
        payload: dict[str, Any] = {"inputs": texts}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=self._headers())
                response.raise_for_status()
                # TEI returns list of list of {index, value} objects
                raw = response.json()
                results: list[dict[int, float]] = []
                for item in raw:
                    sparse: dict[int, float] = {}
                    for entry in item:
                        sparse[entry["index"]] = entry["value"]
                    results.append(sparse)
                return results
        except Exception as e:
            logger.warning(
                "sparse_embedding_unavailable",
                url=url,
                error=str(e),
            )
            # Return empty sparse vectors as fallback (TEI may not support sparse for this model)
            return [{} for _ in texts]
