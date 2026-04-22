"""Search debug API routes."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.api.schemas.search import (
    SearchDebugRequest,
    SearchDebugResponse,
    SearchResultItem,
    SearchTrace,
)
from app.common.core.config import Settings, get_settings
from app.common.core.dependencies import get_db
from app.common.rag.embedding.base import EmbeddingProvider
from app.common.rag.vector_store.base import VectorStore
from app.knowledge.services.kb import KBNotFoundError, KBService
from app.knowledge.services.search_debug import SearchDebugService

router = APIRouter(prefix="/kb", tags=["search-debug"])


def _get_embedding_provider(settings: Settings = Depends(get_settings)) -> EmbeddingProvider:
    """Dependency to get embedding provider."""
    from app.common.rag.embedding.tei import TEIEmbeddingProvider

    return TEIEmbeddingProvider(
        base_url=settings.tei_base_url,
        api_key=settings.tei_api_key,
        batch_size=settings.embedding_batch_size,
        dim=settings.embedding_dimension,
    )


def _get_vector_store(settings: Settings = Depends(get_settings)) -> VectorStore:
    """Dependency to get vector store."""
    from app.common.rag.vector_store.qdrant import QdrantVectorStore

    return QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection_name,
        api_key=settings.qdrant_api_key,
        dense_dim=settings.embedding_dimension,
    )


def _get_search_debug_service(
    session: AsyncSession = Depends(get_db),
    embedding_provider: EmbeddingProvider = Depends(_get_embedding_provider),
    vector_store: VectorStore = Depends(_get_vector_store),
    settings: Settings = Depends(get_settings),
) -> SearchDebugService:
    """Dependency to get search debug service."""
    return SearchDebugService(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        session=session,
        settings=settings,
    )


@router.post(
    "/{kb_id}/search_debug",
    response_model=SearchDebugResponse,
    status_code=status.HTTP_200_OK,
)
async def search_debug(
    kb_id: uuid.UUID,
    payload: SearchDebugRequest,
    session: AsyncSession = Depends(get_db),
    service: SearchDebugService = Depends(_get_search_debug_service),
) -> SearchDebugResponse:
    """Execute hybrid search with debug information.

    Returns ranked results with RRF fusion scores and trace data.
    """
    # Verify KB exists
    kb_service = KBService(session)
    try:
        await kb_service.get_kb(kb_id)
    except KBNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base {kb_id} not found",
        )

    # Build filters dict from request
    filters: dict | None = None
    if payload.filters:
        filters = {}
        if payload.filters.document_type is not None:
            filters["document_type"] = payload.filters.document_type
        if payload.filters.language is not None:
            filters["language"] = payload.filters.language
        if payload.filters.product_model is not None:
            filters["product_model"] = payload.filters.product_model
        if not filters:
            filters = None

    # Execute search
    result = await service.search(
        kb_id=kb_id,
        query=payload.query,
        top_k=payload.top_k,
        filters=filters,
    )

    # Build response
    result_items = [
        SearchResultItem(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            document_title=r["document_title"],
            content=r["content"],
            score=r["score"],
            chunk_type=r["chunk_type"],
            page_start=r.get("page_start"),
            page_end=r.get("page_end"),
            section_path=r.get("section_path"),
            metadata=r.get("metadata", {}),
        )
        for r in result.results
    ]

    return SearchDebugResponse(
        query=result.query,
        results=result_items,
        trace=SearchTrace(
            dense_hits=result.dense_hits,
            sparse_hits=result.sparse_hits,
            fused_total=result.fused_total,
            returned=result.returned,
        ),
    )
