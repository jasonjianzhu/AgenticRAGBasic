"""Pydantic schemas for knowledge base API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KBSettings(BaseModel):
    """Knowledge base settings schema."""

    default_chunker: str = Field(default="docling_hybrid", description="Default chunker strategy")
    default_parser_profile: str = Field(default="balanced", description="Default parser profile")
    embedding_model: str = Field(default="BAAI/bge-m3", description="Embedding model name")

    model_config = ConfigDict(extra="forbid")


class KBCreate(BaseModel):
    """Schema for creating a knowledge base."""

    name: str = Field(..., min_length=1, max_length=200, description="Knowledge base name")
    description: str | None = Field(default=None, description="Knowledge base description")
    settings: KBSettings = Field(default_factory=KBSettings, description="Knowledge base settings")


class KBUpdate(BaseModel):
    """Schema for updating a knowledge base."""

    name: str | None = Field(default=None, min_length=1, max_length=200, description="Knowledge base name")
    description: str | None = Field(default=None, description="Knowledge base description")
    settings: KBSettings | None = Field(default=None, description="Knowledge base settings")
    is_active: bool | None = Field(default=None, description="Whether the knowledge base is active")


class KBStatistics(BaseModel):
    """Knowledge base statistics."""

    document_count: int = 0
    chunk_count: int = 0
    ready_doc_count: int = 0
    failed_doc_count: int = 0


class KBResponse(BaseModel):
    """Schema for knowledge base response."""

    id: uuid.UUID
    name: str
    description: str | None = None
    is_active: bool
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KBDetailResponse(KBResponse):
    """Schema for knowledge base detail response with statistics."""

    statistics: KBStatistics = Field(default_factory=KBStatistics)


class KBListResponse(BaseModel):
    """Schema for listing knowledge bases."""

    items: list[KBResponse]
    total: int
