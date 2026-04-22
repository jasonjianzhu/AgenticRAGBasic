"""Local BGE-M3 embedding provider using FlagEmbedding.

Loads the model once into memory and produces dense + sparse vectors
in a single forward pass. Replaces TEI for sparse embedding support.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.common.core.logging import get_logger
from app.common.rag.embedding.base import EmbeddingProvider, EmbeddingResult

logger = get_logger(__name__)


class BGEM3LocalEmbeddingProvider(EmbeddingProvider):
    """Embedding provider using FlagEmbedding's BGEM3FlagModel locally.

    Loads the model lazily on first call. Produces both dense and sparse
    vectors in one inference pass.

    Args:
        model_path: Path to local model directory (e.g. ~/LocalLLMs/bge-m3).
        use_fp16: Whether to use FP16 for inference (default True).
        batch_size: Maximum texts per batch (default 32).
        dim: Dense vector dimension (default 1024 for BGE-M3).
    """

    def __init__(
        self,
        model_path: str,
        use_fp16: bool = True,
        batch_size: int = 32,
        dim: int = 1024,
    ) -> None:
        self._model_path = model_path
        self._use_fp16 = use_fp16
        self._batch_size = batch_size
        self._dim = dim
        self._model = None

    @property
    def dimension(self) -> int:
        return self._dim

    def _ensure_model(self) -> Any:
        """Lazily load the BGE-M3 model on first use."""
        if self._model is None:
            logger.info(
                "loading_bge_m3_model",
                model_path=self._model_path,
                use_fp16=self._use_fp16,
            )
            from FlagEmbedding import BGEM3FlagModel

            self._model = BGEM3FlagModel(
                self._model_path,
                use_fp16=self._use_fp16,
            )
            logger.info("bge_m3_model_loaded", model_path=self._model_path)
        return self._model

    def _encode_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Synchronous encode returning dense + sparse."""
        model = self._ensure_model()

        output = model.encode(
            texts,
            batch_size=self._batch_size,
            max_length=8192,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )

        results: list[EmbeddingResult] = []
        for i in range(len(texts)):
            dense = output["dense_vecs"][i].tolist()
            # lexical_weights[i] is a dict {token_id: weight}
            sparse = {int(k): float(v) for k, v in output["lexical_weights"][i].items()}
            results.append(EmbeddingResult(dense=dense, sparse=sparse))

        return results

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed a batch of texts, returning dense + sparse vectors."""
        all_results: list[EmbeddingResult] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            batch_results = await asyncio.to_thread(self._encode_batch, batch)
            all_results.extend(batch_results)

        return all_results

    async def embed_query(self, query: str) -> EmbeddingResult:
        """Embed a single query text."""
        results = await self.embed_texts([query])
        return results[0]
