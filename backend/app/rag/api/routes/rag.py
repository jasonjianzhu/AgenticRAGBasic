"""RAG API routes: search and answer."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.config import Settings, get_settings
from app.common.core.dependencies import get_db
from app.common.rag.embedding import create_embedding_provider
from app.common.rag.embedding.base import EmbeddingProvider
from app.common.rag.vector_store.base import VectorStore
from app.rag.api.schemas.rag import (
    RAGAnswerRequest,
    RAGSearchRequest,
    RAGSearchResponse,
    RAGSearchResultItem,
    RAGSearchTrace,
)
from app.rag.generation.base import BaseLLMClient
from app.rag.reranking.base import BaseReranker
from app.rag.services.rag_service import RAGService

router = APIRouter(prefix="/rag", tags=["rag"])

# Module-level singletons for heavy resources (models loaded once)
_embedding_provider: EmbeddingProvider | None = None
_reranker: BaseReranker | None = None
_reranker_initialized = False


def _get_embedding_provider() -> EmbeddingProvider:
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = create_embedding_provider()
    return _embedding_provider


def _get_vector_store(settings: Settings = Depends(get_settings)) -> VectorStore:
    from app.common.rag.vector_store.qdrant import QdrantVectorStore

    return QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection_name,
        api_key=settings.qdrant_api_key,
        dense_dim=settings.embedding_dimension,
    )


def _get_llm_client(settings: Settings = Depends(get_settings)) -> BaseLLMClient:
    from app.rag.generation.minimax import MiniMaxClient

    return MiniMaxClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout,
    )


def _get_reranker(settings: Settings = Depends(get_settings)) -> BaseReranker | None:
    global _reranker, _reranker_initialized
    if _reranker_initialized:
        return _reranker
    _reranker_initialized = True

    if not settings.reranker_enabled:
        return None
    if settings.reranker_provider == "local" and settings.reranker_model_path:
        from app.rag.reranking.local_reranker import LocalReranker
        _reranker = LocalReranker(model_path=settings.reranker_model_path)
    elif settings.reranker_base_url:
        from app.rag.reranking.tei_reranker import TEIReranker
        _reranker = TEIReranker(
            base_url=settings.reranker_base_url,
            api_key=settings.reranker_api_key,
        )
    return _reranker


def _get_rag_service(
    session: AsyncSession = Depends(get_db),
    embedding: EmbeddingProvider = Depends(_get_embedding_provider),
    vector_store: VectorStore = Depends(_get_vector_store),
    llm: BaseLLMClient = Depends(_get_llm_client),
    reranker: BaseReranker | None = Depends(_get_reranker),
    settings: Settings = Depends(get_settings),
) -> RAGService:
    return RAGService(
        embedding_provider=embedding,
        vector_store=vector_store,
        session=session,
        llm_client=llm,
        reranker=reranker,
        settings=settings,
    )


@router.post("/search", response_model=RAGSearchResponse)
async def rag_search(
    payload: RAGSearchRequest,
    service: RAGService = Depends(_get_rag_service),
) -> RAGSearchResponse:
    """Execute RAG search: normalize → rewrite → hybrid search → rerank."""
    filters = None
    if payload.filters:
        filters = {k: v for k, v in payload.filters.model_dump().items() if v is not None}

    result = await service.search(
        query=payload.query,
        kb_ids=payload.kb_ids,
        top_k=payload.top_k,
        filters=filters,
        enable_rewrite=payload.enable_rewrite,
    )

    return RAGSearchResponse(
        query=result.query,
        rewritten_query=result.rewritten_query,
        results=[
            RAGSearchResultItem(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                document_title=r.document_title,
                content=r.content,
                score=r.score,
                rerank_score=r.rerank_score,
                chunk_type=r.chunk_type,
                page_start=r.page_start,
                page_end=r.page_end,
                section_path=r.section_path,
                metadata=r.metadata,
            )
            for r in result.results
        ],
        trace=RAGSearchTrace(
            query_normalized=result.trace.query_normalized,
            query_rewritten=result.trace.query_rewritten,
            retrieval_context=result.trace.retrieval_context,
            dense_hits=result.trace.dense_hits,
            sparse_hits=result.trace.sparse_hits,
            fused_total=result.trace.fused_total,
            reranked=result.trace.reranked,
            returned=result.trace.returned,
            latency_ms=result.trace.latency_ms,
        ),
    )


@router.post("/answer")
async def rag_answer(
    payload: RAGAnswerRequest,
    request: Request,
    service: RAGService = Depends(_get_rag_service),
) -> StreamingResponse:
    """Execute RAG answer: search → generate with SSE streaming."""
    filters = None
    if payload.filters:
        filters = {k: v for k, v in payload.filters.model_dump().items() if v is not None}

    async def event_generator():
        async for event in service.answer_stream(
            query=payload.query,
            kb_ids=payload.kb_ids,
            top_k=payload.top_k,
            filters=filters,
            enable_rewrite=payload.enable_rewrite,
        ):
            # Check if client disconnected
            if await request.is_disconnected():
                break
            event_type = event["event"]
            data = json.dumps(event["data"], ensure_ascii=False)
            yield f"event: {event_type}\ndata: {data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
