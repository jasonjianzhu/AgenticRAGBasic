"""Chunk repository - data access layer for chunk preview."""
from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk


class ChunkRepository:
    """Repository for Chunk read operations (preview)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_document(
        self,
        document_id: uuid.UUID,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Chunk]:
        """List chunks for a document, ordered by ordinal."""
        stmt = (
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.ordinal.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
