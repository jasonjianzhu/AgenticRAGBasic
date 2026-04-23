"""Agent chat route — SSE streaming dialogue."""
from __future__ import annotations

import json
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.config import Settings, get_settings
from app.common.core.dependencies import get_db
from app.common.rag.embedding import create_embedding_provider
from app.common.rag.embedding.base import EmbeddingProvider
from app.common.rag.vector_store.base import VectorStore
from app.rag.generation.base import BaseLLMClient
from app.rag.reranking.base import BaseReranker
from app.rag.services.rag_service import RAGService
from app.agent.api.schemas.chat import ChatRequest
from app.agent.services.chat import ChatService

router = APIRouter(prefix="/agent", tags=["agent"])

# ── Dependency singletons (reuse from RAG where possible) ──

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


@router.post("/chat")
async def agent_chat(
    payload: ChatRequest,
    request: Request,
    rag_service: RAGService = Depends(_get_rag_service),
    db_session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Agent chat endpoint — SSE streaming response.

    Supports: knowledge QA, SQL data analysis, chart generation, mixed queries.
    """
    # Set OpenAI-compatible env vars for PydanticAI
    # PydanticAI uses these when model is "openai:xxx"
    os.environ.setdefault("OPENAI_API_KEY", settings.llm_api_key)
    os.environ.setdefault("OPENAI_BASE_URL", settings.llm_base_url)

    session_id = None
    if payload.session_id:
        try:
            session_id = uuid.UUID(payload.session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的会话 ID")

    kb_ids = []
    for kid in payload.kb_ids:
        try:
            kb_ids.append(uuid.UUID(kid))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的知识库 ID: {kid}")

    chat_service = ChatService(
        rag_service=rag_service,
        db_session=db_session,
        settings=settings,
    )

    async def event_generator():
        async for event in chat_service.chat_stream(
            message=payload.message,
            session_id=session_id,
            kb_ids=kb_ids,
        ):
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
