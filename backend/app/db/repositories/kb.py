"""Knowledge base repository - data access layer."""
from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, KnowledgeBase


class KBRepository:
    """Repository for KnowledgeBase CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, name: str, description: str | None = None, settings: dict | None = None) -> KnowledgeBase:
        """Create a new knowledge base."""
        kb = KnowledgeBase(
            name=name,
            description=description,
            settings=settings or {},
        )
        self.session.add(kb)
        await self.session.flush()
        return kb

    async def get_by_id(self, kb_id: uuid.UUID) -> KnowledgeBase | None:
        """Get a knowledge base by ID."""
        stmt = select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> KnowledgeBase | None:
        """Get a knowledge base by name."""
        stmt = select(KnowledgeBase).where(KnowledgeBase.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, *, skip: int = 0, limit: int = 100) -> Sequence[KnowledgeBase]:
        """List all knowledge bases with pagination."""
        stmt = (
            select(KnowledgeBase)
            .order_by(KnowledgeBase.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update(self, kb: KnowledgeBase, **kwargs) -> KnowledgeBase:
        """Update a knowledge base with given fields."""
        for key, value in kwargs.items():
            if hasattr(kb, key):
                setattr(kb, key, value)
        await self.session.flush()
        return kb

    async def delete(self, kb: KnowledgeBase) -> None:
        """Delete a knowledge base."""
        await self.session.delete(kb)
        await self.session.flush()

    async def get_statistics(self, kb_id: uuid.UUID) -> dict:
        """Get statistics for a knowledge base (document and chunk counts)."""
        # Total document count (non-deleted)
        doc_count_stmt = (
            select(func.count(Document.id))
            .where(Document.knowledge_base_id == kb_id)
            .where(Document.is_deleted == False)  # noqa: E712
        )
        doc_count_result = await self.session.execute(doc_count_stmt)
        document_count = doc_count_result.scalar() or 0

        # Ready document count
        ready_stmt = (
            select(func.count(Document.id))
            .where(Document.knowledge_base_id == kb_id)
            .where(Document.is_deleted == False)  # noqa: E712
            .where(Document.status == "ready")
        )
        ready_result = await self.session.execute(ready_stmt)
        ready_doc_count = ready_result.scalar() or 0

        # Failed document count
        failed_stmt = (
            select(func.count(Document.id))
            .where(Document.knowledge_base_id == kb_id)
            .where(Document.is_deleted == False)  # noqa: E712
            .where(Document.status == "failed")
        )
        failed_result = await self.session.execute(failed_stmt)
        failed_doc_count = failed_result.scalar() or 0

        # Chunk count
        chunk_count_stmt = (
            select(func.count(Chunk.id))
            .where(Chunk.knowledge_base_id == kb_id)
        )
        chunk_count_result = await self.session.execute(chunk_count_stmt)
        chunk_count = chunk_count_result.scalar() or 0

        return {
            "document_count": document_count,
            "chunk_count": chunk_count,
            "ready_doc_count": ready_doc_count,
            "failed_doc_count": failed_doc_count,
        }
