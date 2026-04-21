from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.dependencies import DbSessionDep, EmbeddingProviderDep, LLMClientDep, SettingsDep, VectorStoreDep
from app.services.rag import AnswerGenerationNotConfiguredError, RAGService


router = APIRouter(prefix="/rag", tags=["rag"])


class RAGSearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    knowledge_base_id: str | None = None
    session_id: str | None = None
    language: str | None = None
    use_reranker: bool | None = None


class RAGAnswerRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    knowledge_base_id: str | None = None
    session_id: str | None = None
    language: str | None = None
    use_reranker: bool | None = None


@router.post("/search")
def rag_search(
    request: RAGSearchRequest,
    db_session: DbSessionDep,
    settings: SettingsDep,
    embedding_provider: EmbeddingProviderDep,
    vector_store: VectorStoreDep,
    llm_client: LLMClientDep,
):
    return RAGService(
        session=db_session,
        settings=settings,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        llm_client=llm_client,
    ).search(
        query=request.query,
        top_k=request.top_k,
        knowledge_base_id=request.knowledge_base_id,
        language=request.language,
        use_reranker=request.use_reranker,
        session_id=request.session_id,
    )


@router.post("/answer")
def rag_answer(
    request: RAGAnswerRequest,
    db_session: DbSessionDep,
    settings: SettingsDep,
    embedding_provider: EmbeddingProviderDep,
    vector_store: VectorStoreDep,
    llm_client: LLMClientDep,
):
    try:
        result = RAGService(
            session=db_session,
            settings=settings,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            llm_client=llm_client,
        ).answer(
            query=request.query,
            top_k=request.top_k,
            knowledge_base_id=request.knowledge_base_id,
            language=request.language,
            use_reranker=request.use_reranker,
            session_id=request.session_id,
        )
    except AnswerGenerationNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "query": result.query,
        "rewritten_query": result.rewritten_query,
        "answer": result.answer,
        "citations": [
            {
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "source_filename": item.source_filename,
                "page_start": item.page_start,
                "page_end": item.page_end,
                "section_path": item.section_path,
            }
            for item in result.citations
        ],
        "chunks": result.chunks,
        "trace": result.trace,
    }
