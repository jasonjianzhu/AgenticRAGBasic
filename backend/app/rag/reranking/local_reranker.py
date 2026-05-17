"""Local reranker using sentence-transformers CrossEncoder.

Loads the model once into memory and scores query-document pairs.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.common.core.logging import get_logger
from app.rag.reranking.base import BaseReranker, RerankResult

logger = get_logger(__name__)


class LocalReranker(BaseReranker):
    """Reranker using a local CrossEncoder model (e.g. bge-reranker-v2-m3).

    Args:
        model_path: Path to local model directory.
        batch_size: Maximum pairs per batch (default 32).
    """

    def __init__(self, model_path: str, batch_size: int = 32) -> None:
        self._model_path = model_path
        self._batch_size = batch_size
        self._model = None

    def _ensure_model(self) -> Any:
        """Lazily load the CrossEncoder model on first use."""
        if self._model is None:
            logger.info("loading_reranker_model", model_path=self._model_path)
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                self._model_path,
                trust_remote_code=True,
                model_kwargs={"low_cpu_mem_usage": False},
            )
            logger.info("reranker_model_loaded", model_path=self._model_path)
        return self._model

    def _score_pairs(self, query: str, documents: list[str]) -> list[float]:
        """Score query-document pairs synchronously."""
        model = self._ensure_model()
        pairs = [[query, doc] for doc in documents]
        scores = model.predict(pairs, batch_size=self._batch_size)
        return [float(s) for s in scores]

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        """Rerank documents by relevance to the query."""
        if not documents:
            return []

        scores = await asyncio.to_thread(self._score_pairs, query, documents)

        results = [
            RerankResult(index=i, score=score, content=documents[i])
            for i, score in enumerate(scores)
        ]
        results.sort(key=lambda r: r.score, reverse=True)

        if top_n is not None:
            results = results[:top_n]

        logger.info(
            "rerank_complete",
            query_len=len(query),
            candidates=len(documents),
            returned=len(results),
            top_score=results[0].score if results else 0,
        )
        return results
