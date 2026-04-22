"""Pydantic schemas for document API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    """Schema for document response."""

    id: uuid.UUID
    title: str
    status: str
    content_hash: str
    knowledge_base_id: uuid.UUID
    source_filename: str
    mime_type: str
    file_size_bytes: int
    document_type: str
    is_enabled: bool
    storage_path: str
    created_at: datetime
    updated_at: datetime
    job_id: uuid.UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    """Schema for listing documents."""

    items: list[DocumentResponse]
    total: int


class ChunkResponse(BaseModel):
    """Schema for chunk preview response."""

    id: uuid.UUID
    ordinal: int
    chunk_type: str
    content: str
    section_path: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    token_count: int | None = None

    model_config = ConfigDict(from_attributes=True)


class ChunkListResponse(BaseModel):
    """Schema for listing chunks."""

    items: list[ChunkResponse]
    total: int
