from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.db.repositories import ChunkRepository, DocumentRepository


@dataclass(frozen=True)
class ChunkPreviewItem:
    id: uuid.UUID
    ordinal: int
    chunk_type: str
    section_path: str | None
    content: str
    token_count: int | None
    page_start: int | None
    page_end: int | None
    language: str | None
    product_model: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ChunkPreviewResult:
    document_id: uuid.UUID
    total: int
    items: list[ChunkPreviewItem]


class ChunkPreviewService:
    def __init__(self, session: Session):
        self.session = session

    def list_document_chunks(
        self,
        document_id: str | uuid.UUID,
        chunk_type: str | None = None,
    ) -> ChunkPreviewResult:
        document_uuid = uuid.UUID(str(document_id))
        document = DocumentRepository(self.session).get(document_uuid)
        if document is None:
            raise ValueError(f"Document not found: {document_uuid}")

        chunks = ChunkRepository(self.session).list_by_document(document_uuid, chunk_type=chunk_type)
        items = [
            ChunkPreviewItem(
                id=chunk.id,
                ordinal=chunk.ordinal,
                chunk_type=chunk.chunk_type,
                section_path=chunk.section_path,
                content=chunk.content,
                token_count=chunk.token_count,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                language=chunk.language,
                product_model=chunk.product_model,
                metadata=chunk.metadata_,
            )
            for chunk in chunks
        ]
        return ChunkPreviewResult(document_id=document_uuid, total=len(items), items=items)
