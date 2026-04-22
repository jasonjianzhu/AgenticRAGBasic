"""Pydantic schemas for search debug API."""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SearchFilters(BaseModel):
    """Filters for search debug queries."""

    document_type: str | None = Field(default=None, description="Filter by document type (manual/faq/qa/spec)")
    language: str | None = Field(default=None, description="Filter by language (zh/en)")
    product_model: str | None = Field(default=None, description="Filter by product model")


class SearchDebugRequest(BaseModel):
    """Request body for search debug endpoint."""

    query: str = Field(..., min_length=1, max_length=1000, description="Search query text")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")
    filters: SearchFilters | None = Field(default=None, description="Optional metadata filters")


class SearchResultItem(BaseModel):
    """A single search result with debug information."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    content: str
    score: float
    chunk_type: str
    page_start: int | None = None
    page_end: int | None = None
    section_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class SearchTrace(BaseModel):
    """Debug trace information for the search."""

    dense_hits: int
    sparse_hits: int
    fused_total: int
    returned: int


class SearchDebugResponse(BaseModel):
    """Response for search debug endpoint."""

    query: str
    results: list[SearchResultItem]
    trace: SearchTrace
