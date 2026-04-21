from __future__ import annotations

from app.core.config import Settings
from app.rag.embedding.base import EmbeddingProvider
from app.rag.embedding.tei import TEIEmbeddingProvider


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_backend == "tei":
        return TEIEmbeddingProvider(
            base_url=settings.tei_base_url,
            api_key=settings.tei_api_key,
            model_name=settings.embedding_model_name,
            dimension=settings.embedding_dimension,
            batch_size=settings.embedding_batch_size,
        )
    raise ValueError(f"Unsupported embedding backend for production use: {settings.embedding_backend}")
