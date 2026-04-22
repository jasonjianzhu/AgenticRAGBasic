"""Pydantic schemas for RAG config API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RAGConfigResponse(BaseModel):
    """Full RAG configuration."""

    search_top_k: int = 10
    answer_top_k: int = 5
    rerank_enabled: bool = False
    rerank_top_n: int = 20
    rewrite_enabled: bool = True
    context_window_tokens: int = 4000
    score_threshold: float = 0.3
    refusal_threshold: float = 0.2
    rrf_k: int = 60
    llm_model: str = ""
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2048


class RAGConfigUpdate(BaseModel):
    """Partial update for RAG configuration. Only provided fields are updated."""

    search_top_k: int | None = Field(default=None, ge=1, le=100)
    answer_top_k: int | None = Field(default=None, ge=1, le=50)
    rerank_enabled: bool | None = None
    rerank_top_n: int | None = Field(default=None, ge=1, le=100)
    rewrite_enabled: bool | None = None
    context_window_tokens: int | None = Field(default=None, ge=500, le=32000)
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    refusal_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    rrf_k: int | None = Field(default=None, ge=1, le=1000)
    llm_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    llm_max_tokens: int | None = Field(default=None, ge=1, le=16384)
