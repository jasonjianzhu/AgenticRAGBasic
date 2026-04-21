from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends
from qdrant_client import QdrantClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings as get_app_settings
from app.db.session import get_db_session
from app.jobs.queue import get_indexing_queue, get_ingestion_queue
from app.jobs.types import TaskQueue
from app.llm.minimax import MiniMaxClient
from app.rag.embedding.factory import build_embedding_provider
from app.rag.vector_store.memory import InMemoryVectorStore
from app.rag.vector_store.qdrant import QdrantVectorStore


def _get_settings() -> Settings:
    return get_app_settings()


SettingsDep = Annotated[Settings, Depends(_get_settings)]
DbSessionDep = Annotated[Session, Depends(get_db_session)]
IngestionQueueDep = Annotated[TaskQueue, Depends(get_ingestion_queue)]
IndexingQueueDep = Annotated[TaskQueue, Depends(get_indexing_queue)]


def get_settings_dependency() -> SettingsDep:
    return Depends(_get_settings)


def get_settings() -> Settings:
    return _get_settings()


def _get_embedding_provider():
    settings = _get_settings()
    return build_embedding_provider(settings)


def _get_vector_store():
    settings = _get_settings()
    if settings.vector_store_backend == "memory":
        return InMemoryVectorStore()

    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )
    return QdrantVectorStore(
        client=client,
        collection_name=settings.qdrant_collection_name,
        vector_size=settings.embedding_dimension,
        dense_vector_name=settings.qdrant_dense_vector_name,
        sparse_vector_name=settings.qdrant_sparse_vector_name,
    )


def _get_llm_client():
    settings = _get_settings()
    if settings.minimax_base_url and settings.minimax_api_key:
        return MiniMaxClient(
            base_url=settings.minimax_base_url,
            api_key=settings.minimax_api_key,
            model=settings.minimax_model,
        )
    return None


EmbeddingProviderDep = Annotated[Any, Depends(_get_embedding_provider)]
VectorStoreDep = Annotated[Any, Depends(_get_vector_store)]
LLMClientDep = Annotated[Any, Depends(_get_llm_client)]
