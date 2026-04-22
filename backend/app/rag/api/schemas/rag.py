"""Pydantic schemas for RAG API."""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class RAGSearchFilters(BaseModel):
    """Optional filters for RAG search."""

    document_type: str | None = None
    language: str | None = None
    product_model: str | None = None


class RAGSearchRequest(BaseModel):
    """Request body for /rag/search."""

    query: str = Field(..., min_length=1, max_length=2000)
    kb_ids: list[uuid.UUID] = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)
    filters: RAGSearchFilters | None = None
    enable_rewrite: bool | None = None


class RAGSearchResultItem(BaseModel):
    """A single search result."""

    chunk_id: str
    document_id: str
    document_title: str
    content: str
    score: float
    rerank_score: float | None = None
    chunk_type: str = "text"
    page_start: int | None = None
    page_end: int | None = None
    section_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGSearchTrace(BaseModel):
    """Trace information for search."""

    query_normalized: str
    query_rewritten: str | None = None
    retrieval_context: dict[str, Any] = Field(default_factory=dict)
    dense_hits: int = 0
    sparse_hits: int = 0
    fused_total: int = 0
    reranked: bool = False
    returned: int = 0
    latency_ms: dict[str, Any] = Field(default_factory=dict)


class RAGSearchResponse(BaseModel):
    """Response for /rag/search."""

    query: str
    rewritten_query: str | None = None
    results: list[RAGSearchResultItem]
    trace: RAGSearchTrace


class RAGAnswerRequest(BaseModel):
    """Request body for /rag/answer (SSE stream)."""

    query: str = Field(..., min_length=1, max_length=2000)
    kb_ids: list[uuid.UUID] = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    filters: RAGSearchFilters | None = None
    enable_rewrite: bool | None = None
    enable_rerank: bool | None = None
