from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Chunk, Document
from app.db.repositories import QueryLogRepository
from app.rag.embedding.base import EmbeddingProvider
from app.rag.query.context import RetrievalContext
from app.rag.query.processing import QueryProcessor, pack_context_blocks
from app.rag.rerank.base import RerankItem
from app.rag.rerank.factory import build_reranker
from app.rag.retrieval.service import HybridRetrievalService


class AnswerGenerationNotConfiguredError(RuntimeError):
    """Raised when answer generation is requested without a configured LLM."""


@dataclass(frozen=True)
class Citation:
    chunk_id: str
    document_id: str
    source_filename: str
    page_start: int | None
    page_end: int | None
    section_path: str | None


@dataclass(frozen=True)
class RAGAnswerResult:
    query: str
    rewritten_query: str
    answer: str
    citations: list[Citation]
    chunks: list[dict[str, Any]]
    trace: dict[str, Any]


class RAGService:
    def __init__(self, session: Session, settings: Settings, embedding_provider: EmbeddingProvider, vector_store, llm_client=None):
        self.session = session
        self.settings = settings
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.llm_client = llm_client
        self.query_processor = QueryProcessor(
            llm_client=llm_client,
            query_limit=settings.retrieval_query_limit,
            history_limit=settings.retrieval_context_history_limit,
        )
        self.reranker = build_reranker(settings)

    def search(
        self,
        query: str,
        top_k: int = 5,
        knowledge_base_id: str | None = None,
        language: str | None = None,
        use_reranker: bool | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        previous_contexts = self._load_previous_contexts(session_id) if session_id else []
        processed = self.query_processor.process(
            query,
            language=language,
            knowledge_base_id=knowledge_base_id,
            previous_contexts=previous_contexts,
        )
        retrieval = HybridRetrievalService(
            session=self.session,
            settings=self.settings,
            embedding_provider=self.embedding_provider,
            vector_store=self.vector_store,
        ).multi_search(
            queries=processed.retrieval_queries,
            top_k=top_k,
            knowledge_base_id=processed.context.knowledge_base_id,
            language=processed.context.language,
            document_type=processed.context.document_type,
            product_model=processed.context.product_model,
        )
        reranker_requested = self.reranker.enabled if use_reranker is None else use_reranker
        final_items = retrieval.items[:top_k]
        if reranker_requested and retrieval.items:
            reranked_items = self.reranker.rerank(
                query=processed.rewrite.rewritten_query,
                items=[
                    RerankItem(
                        item_id=str(item.chunk_id),
                        content=item.content,
                        score=item.score,
                        metadata=item.metadata,
                    )
                    for item in retrieval.items
                ],
                top_n=top_k,
            )
            reranked_by_id = {item.item_id: item for item in reranked_items}
            final_items = [
                item
                for item in retrieval.items
                if str(item.chunk_id) in reranked_by_id
            ]
            final_items.sort(key=lambda item: reranked_by_id[str(item.chunk_id)].score, reverse=True)
        return {
            "query": retrieval.query,
            "rewritten_query": processed.rewrite.rewritten_query,
            "chunks": [
                {
                    "chunk_id": str(item.chunk_id),
                    "document_id": str(item.document_id),
                    "chunk_type": item.chunk_type,
                    "content": item.content,
                    "section_path": item.section_path,
                    "page_start": item.page_start,
                    "page_end": item.page_end,
                    "score": item.score,
                    "metadata": item.metadata,
                }
                for item in final_items
            ],
            "trace": {
                **retrieval.trace,
                "normalization": {
                    "normalized_query": processed.normalized_query,
                },
                "rewrite": {
                    "rewritten_query": processed.rewrite.rewritten_query,
                    "expanded_queries": processed.rewrite.expanded_queries,
                    "language": processed.context.language,
                    "knowledge_base_id": processed.context.knowledge_base_id,
                    "document_type": processed.context.document_type,
                    "product_model": processed.context.product_model,
                    "fault_code": processed.context.fault_code,
                    "retrieval_queries": processed.retrieval_queries,
                },
                "rerank_enabled": reranker_requested,
                "rerank_available": self.reranker.enabled,
            },
        }

    def answer(
        self,
        query: str,
        top_k: int = 5,
        knowledge_base_id: str | None = None,
        language: str | None = None,
        use_reranker: bool | None = None,
        session_id: str | None = None,
    ) -> RAGAnswerResult:
        search_result = self.search(
            query=query,
            top_k=top_k,
            knowledge_base_id=knowledge_base_id,
            language=language,
            use_reranker=use_reranker,
            session_id=session_id,
        )
        chunks = search_result["chunks"]
        citations = [self._build_citation(chunk_id=item["chunk_id"]) for item in chunks[:3]]
        answer = self._compose_answer(query, chunks, citations)
        QueryLogRepository(self.session).create(
            user_query=query,
            knowledge_base_id=_safe_uuid(knowledge_base_id),
            session_id=session_id,
            rewritten_query=search_result["rewritten_query"],
            answer=answer,
            retrieval_mode="hybrid",
            trace=search_result["trace"],
        )
        self.session.commit()
        return RAGAnswerResult(
            query=query,
            rewritten_query=search_result["rewritten_query"],
            answer=answer,
            citations=citations,
            chunks=chunks,
            trace=search_result["trace"],
        )

    def _build_citation(self, chunk_id: str) -> Citation:
        chunk = self.session.get(Chunk, UUID(chunk_id))
        if chunk is None:
            raise ValueError(f"Chunk not found: {chunk_id}")
        document = self.session.get(Document, chunk.document_id)
        if document is None:
            raise ValueError(f"Document not found: {chunk.document_id}")
        return Citation(
            chunk_id=str(chunk.id),
            document_id=str(document.id),
            source_filename=document.source_filename,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section_path=chunk.section_path,
        )

    def _compose_answer(self, query: str, chunks: list[dict[str, Any]], citations: list[Citation]) -> str:
        if not chunks:
            return f"No grounded answer found for: {query}"
        context_blocks = pack_context_blocks(
            chunks,
            max_items=self.settings.answer_context_max_items,
            max_chars=self.settings.answer_context_max_chars,
        )
        if self.llm_client is None:
            raise AnswerGenerationNotConfiguredError(
                "MiniMax client is not configured. Set ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN, and ANTHROPIC_MODEL."
            )
        return self.llm_client.generate_answer(
            query=query,
            context_blocks=context_blocks,
        )

    def _load_previous_contexts(self, session_id: str) -> list:
        if not session_id:
            return []
        logs = list(reversed(QueryLogRepository(self.session).list_by_session(session_id, limit=self.settings.retrieval_context_history_limit)))
        contexts = []
        for log in logs:
            rewrite_trace = (log.trace or {}).get("rewrite", {})
            contexts.append(
                RetrievalContext(
                    knowledge_base_id=rewrite_trace.get("knowledge_base_id"),
                    language=rewrite_trace.get("language"),
                    document_type=rewrite_trace.get("document_type"),
                    product_model=rewrite_trace.get("product_model"),
                    fault_code=rewrite_trace.get("fault_code"),
                )
            )
        return contexts


def _safe_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None
