"""Document repository - data access layer for document management."""
from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document


class DocumentRepository:
    """Repository for Document CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        knowledge_base_id: uuid.UUID,
        title: str,
        source_filename: str,
        storage_path: str,
        content_hash: str,
        mime_type: str,
        file_size_bytes: int,
        document_type: str = "unknown",
        status: str = "uploaded",
        metadata: dict | None = None,
    ) -> Document:
        """Create a new document record."""
        doc = Document(
            knowledge_base_id=knowledge_base_id,
            title=title,
            source_filename=source_filename,
            storage_path=storage_path,
            content_hash=content_hash,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            document_type=document_type,
            status=status,
            metadata_=metadata or {},
        )
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def get_by_id(self, doc_id: uuid.UUID) -> Document | None:
        """Get a document by its primary key (excludes soft-deleted)."""
        stmt = select(Document).where(
            Document.id == doc_id,
            Document.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_include_deleted(self, doc_id: uuid.UUID) -> Document | None:
        """Get a document by ID, including soft-deleted ones."""
        stmt = select(Document).where(Document.id == doc_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_kb_and_hash(
        self, knowledge_base_id: uuid.UUID, content_hash: str
    ) -> Document | None:
        """Find a document by knowledge_base_id and content_hash (for dedup)."""
        stmt = select(Document).where(
            Document.knowledge_base_id == knowledge_base_id,
            Document.content_hash == content_hash,
            Document.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_documents(
        self,
        *,
        knowledge_base_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> int:
        """Count documents matching filters, excluding soft-deleted."""
        stmt = select(func.count(Document.id)).where(Document.is_deleted == False)  # noqa: E712
        if knowledge_base_id is not None:
            stmt = stmt.where(Document.knowledge_base_id == knowledge_base_id)
        if status is not None:
            stmt = stmt.where(Document.status == status)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def list_documents(
        self,
        *,
        knowledge_base_id: uuid.UUID | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Document]:
        """List documents with optional filters, excluding soft-deleted."""
        stmt = select(Document).where(Document.is_deleted == False)  # noqa: E712

        if knowledge_base_id is not None:
            stmt = stmt.where(Document.knowledge_base_id == knowledge_base_id)
        if status is not None:
            stmt = stmt.where(Document.status == status)

        stmt = stmt.order_by(Document.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update(self, doc: Document, **kwargs) -> Document:
        """Update a document with given fields."""
        for key, value in kwargs.items():
            if key == "metadata":
                setattr(doc, "metadata_", value)
            elif hasattr(doc, key):
                setattr(doc, key, value)
        await self.session.flush()
        return doc

    async def soft_delete(self, doc: Document) -> Document:
        """Soft-delete a document by setting is_deleted=True."""
        doc.is_deleted = True
        await self.session.flush()
        return doc
