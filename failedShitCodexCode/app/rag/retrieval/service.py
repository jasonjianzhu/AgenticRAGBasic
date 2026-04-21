from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Chunk
from app.rag.embedding.base import EmbeddingProvider
from app.rag.retrieval.sparse import build_sparse_vector, tokenize_for_search


@dataclass(frozen=True)
class RetrievalItem:
    chunk_id: UUID
    document_id: UUID
    chunk_type: str
    content: str
    section_path: str | None
    page_start: int | None
    page_end: int | None
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HybridRetrievalResult:
    query: str
    rewritten_query: str
    items: list[RetrievalItem]
    trace: dict[str, Any]


class HybridRetrievalService:
    def __init__(self, session: Session, settings: Settings, embedding_provider: EmbeddingProvider, vector_store):
        self.session = session
        self.settings = settings
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store

    def search(
        self,
        query: str,
        top_k: int = 5,
        knowledge_base_id: str | None = None,
        language: str | None = None,
        document_type: str | None = None,
        product_model: str | None = None,
    ) -> HybridRetrievalResult:
        rewritten_query = query.strip()
        query_vector = self.embedding_provider.embed_query(rewritten_query)
        sparse_vector = build_sparse_vector(rewritten_query, self.settings.sparse_vector_size)
        filters: dict[str, Any] = {"is_enabled": True, "document_status": "ready"}
        if knowledge_base_id is not None:
            filters["knowledge_base_id"] = knowledge_base_id
        if language is not None:
            filters["language"] = language
        if document_type is not None:
            filters["document_type"] = document_type
        if product_model is not None:
            filters["product_model"] = product_model

        dense_hits = self.vector_store.search(
            collection_name=self.settings.qdrant_collection_name,
            query_vector=query_vector,
            limit=max(self.settings.retrieval_candidate_limit, top_k),
            filters=filters,
        )
        sparse_hits = self.vector_store.sparse_search(
            collection_name=self.settings.qdrant_collection_name,
            sparse_vector=sparse_vector,
            limit=max(self.settings.retrieval_candidate_limit, top_k),
            filters=filters,
        )
        fused_hits = _rrf_fuse(
            dense_hits=dense_hits,
            sparse_hits=sparse_hits,
            k=self.settings.retrieval_rrf_k,
        )
        items: list[RetrievalItem] = []
        query_terms = set(tokenize_for_search(rewritten_query))
        for hit in fused_hits:
            chunk = self.session.get(Chunk, UUID(hit.payload["chunk_id"]))
            if chunk is None:
                continue
            lexical_score = _lexical_overlap_score(query_terms, chunk.content)
            combined_score = (hit.score * 0.85) + (lexical_score * 0.15)
            items.append(
                RetrievalItem(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    chunk_type=chunk.chunk_type,
                    content=chunk.content,
                    section_path=chunk.section_path,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    score=combined_score,
                    metadata=chunk.metadata_,
                )
            )
        items.sort(key=lambda item: item.score, reverse=True)
        items = items[:top_k]

        return HybridRetrievalResult(
            query=query,
            rewritten_query=rewritten_query,
            items=items,
            trace={
                "retrieval_mode": "hybrid",
                "dense_hit_count": len(dense_hits),
                "sparse_hit_count": len(sparse_hits),
                "fused_hit_count": len(fused_hits),
                "filters": filters,
                "rrf_k": self.settings.retrieval_rrf_k,
            },
        )

    def multi_search(
        self,
        queries: list[str],
        top_k: int = 5,
        knowledge_base_id: str | None = None,
        language: str | None = None,
        document_type: str | None = None,
        product_model: str | None = None,
    ) -> HybridRetrievalResult:
        aggregated_items: dict[UUID, RetrievalItem] = {}
        query_traces = []
        primary_query = queries[0] if queries else ""
        for index, query in enumerate(queries[: self.settings.retrieval_query_limit]):
            result = self.search(
                query=query,
                top_k=top_k,
                knowledge_base_id=knowledge_base_id,
                language=language,
                document_type=document_type,
                product_model=product_model,
            )
            query_traces.append(
                {
                    "query": query,
                    "trace": result.trace,
                }
            )
            for item in result.items:
                existing = aggregated_items.get(item.chunk_id)
                if existing is None or item.score > existing.score:
                    aggregated_items[item.chunk_id] = item
                elif existing is not None:
                    aggregated_items[item.chunk_id] = RetrievalItem(
                        chunk_id=existing.chunk_id,
                        document_id=existing.document_id,
                        chunk_type=existing.chunk_type,
                        content=existing.content,
                        section_path=existing.section_path,
                        page_start=existing.page_start,
                        page_end=existing.page_end,
                        score=max(existing.score, item.score),
                        metadata=existing.metadata,
                    )
        items = sorted(aggregated_items.values(), key=lambda item: item.score, reverse=True)[:top_k]
        return HybridRetrievalResult(
            query=primary_query,
            rewritten_query=primary_query,
            items=items,
            trace={
                "retrieval_mode": "hybrid_multi_query",
                "queries": query_traces,
                "query_count": len(query_traces),
            },
        )


def _lexical_overlap_score(query_terms: set[str], content: str) -> float:
    if not query_terms:
        return 0.0
    content_terms = set(tokenize_for_search(content))
    if not content_terms:
        return 0.0
    overlap = len(query_terms & content_terms)
    return overlap / len(query_terms)


def _rrf_fuse(*, dense_hits, sparse_hits, k: int) -> list:
    by_id: dict[str, Any] = {}
    scores: dict[str, float] = {}

    for rank, hit in enumerate(dense_hits, start=1):
        by_id[hit.id] = hit
        scores[hit.id] = scores.get(hit.id, 0.0) + (1.0 / (k + rank))

    for rank, hit in enumerate(sparse_hits, start=1):
        by_id[hit.id] = hit
        scores[hit.id] = scores.get(hit.id, 0.0) + (1.0 / (k + rank))

    fused = []
    for hit_id, score in scores.items():
        hit = by_id[hit_id]
        fused.append(type(hit)(id=hit.id, score=score, payload=hit.payload))
    fused.sort(key=lambda item: item.score, reverse=True)
    return fused
