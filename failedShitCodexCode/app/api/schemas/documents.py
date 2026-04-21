from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentUploadResponse(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    title: str
    source_filename: str
    storage_path: str
    content_hash: str
    mime_type: str
    file_size_bytes: int
    document_type: str
    status: str
    is_enabled: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentJobResponse(BaseModel):
    id: UUID
    queue_name: str
    job_type: str
    status: str
    rq_job_id: str | None
    attempts: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    payload: dict

    model_config = ConfigDict(from_attributes=True)


class DocumentDetailResponse(DocumentUploadResponse):
    jobs: list[DocumentJobResponse] = []


class ChunkPreviewItemResponse(BaseModel):
    id: UUID
    ordinal: int
    chunk_type: str
    section_path: str | None
    content: str
    token_count: int | None
    page_start: int | None
    page_end: int | None
    language: str | None
    product_model: str | None
    metadata: dict

    model_config = ConfigDict(from_attributes=True)


class DocumentChunkPreviewResponse(BaseModel):
    document_id: UUID
    total: int
    items: list[ChunkPreviewItemResponse]

    model_config = ConfigDict(from_attributes=True)
