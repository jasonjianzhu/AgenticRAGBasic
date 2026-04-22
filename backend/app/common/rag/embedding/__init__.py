"""Embedding provider interfaces and implementations."""
from app.common.rag.embedding.base import EmbeddingProvider, EmbeddingResult

__all__ = ["EmbeddingProvider", "EmbeddingResult", "create_embedding_provider"]


def create_embedding_provider() -> EmbeddingProvider:
    """Create an embedding provider based on application settings.

    Returns BGEM3LocalEmbeddingProvider when EMBEDDING_PROVIDER=local,
    TEIEmbeddingProvider when EMBEDDING_PROVIDER=tei.
    """
    from app.common.core.config import get_settings

    settings = get_settings()

    if settings.embedding_provider == "local":
        from app.common.rag.embedding.bge_m3_local import BGEM3LocalEmbeddingProvider

        return BGEM3LocalEmbeddingProvider(
            model_path=settings.embedding_model_path,
            use_fp16=settings.embedding_use_fp16,
            batch_size=settings.embedding_batch_size,
            dim=settings.embedding_dimension,
        )
    else:
        from app.common.rag.embedding.tei import TEIEmbeddingProvider

        return TEIEmbeddingProvider(
            base_url=settings.tei_base_url,
            api_key=settings.tei_api_key,
            batch_size=settings.embedding_batch_size,
            dim=settings.embedding_dimension,
        )
