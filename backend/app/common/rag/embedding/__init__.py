"""Embedding provider interfaces and implementations."""
from app.common.rag.embedding.base import EmbeddingProvider, EmbeddingResult

__all__ = ["EmbeddingProvider", "EmbeddingResult", "create_embedding_provider"]

_cached_provider: EmbeddingProvider | None = None


def create_embedding_provider() -> EmbeddingProvider:
    """Create or return cached embedding provider based on application settings.

    Returns BGEM3LocalEmbeddingProvider when EMBEDDING_PROVIDER=local,
    TEIEmbeddingProvider when EMBEDDING_PROVIDER=tei.
    Singleton — model loaded once, reused across requests.
    """
    global _cached_provider
    if _cached_provider is not None:
        return _cached_provider

    from app.common.core.config import get_settings

    settings = get_settings()

    if settings.embedding_provider == "local":
        from app.common.rag.embedding.bge_m3_local import BGEM3LocalEmbeddingProvider

        _cached_provider = BGEM3LocalEmbeddingProvider(
            model_path=settings.embedding_model_path,
            use_fp16=settings.embedding_use_fp16,
            batch_size=settings.embedding_batch_size,
            dim=settings.embedding_dimension,
        )
    else:
        from app.common.rag.embedding.tei import TEIEmbeddingProvider

        _cached_provider = TEIEmbeddingProvider(
            base_url=settings.tei_base_url,
            api_key=settings.tei_api_key,
            batch_size=settings.embedding_batch_size,
            dim=settings.embedding_dimension,
        )

    return _cached_provider
