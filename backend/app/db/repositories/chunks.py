"""Chunk repository - data access layer for chunk management."""
from __future__ import annotations

import hashlib
import uuid
from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk


class ChunkRepository:
    """Repository for Chunk CRUD operations."""

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

    async def create_chunks_batch(
        self,
        *,
        knowledge_base_id: uuid.UUID,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
        chunks_data: list[dict],
    ) -> list[Chunk]:
        """Bulk insert chunks into the database.

        Each dict in chunks_data should contain:
            - content (str): The chunk text content.
            - ordinal (int): The chunk ordinal/sequence number.
            - chunk_type (str, optional): "text", "table", or "image_caption".
            - section_path (str | None, optional): Section path.
            - page_start (int | None, optional): Start page.
            - page_end (int | None, optional): End page.
            - token_count (int | None, optional): Token count.
            - metadata (dict, optional): Additional metadata.

        Args:
            knowledge_base_id: The knowledge base ID.
            document_id: The document ID.
            document_version_id: The document version ID.
            chunks_data: List of chunk data dicts.

        Returns:
            List of created Chunk ORM instances.
        """
        created: list[Chunk] = []

        for data in chunks_data:
            content = data["content"]
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

            chunk = Chunk(
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
                document_version_id=document_version_id,
                ordinal=data["ordinal"],
                chunk_type=data.get("chunk_type", "text"),
                section_path=data.get("section_path"),
                content=content,
                content_hash=content_hash,
                token_count=data.get("token_count"),
                page_start=data.get("page_start"),
                page_end=data.get("page_end"),
                metadata_=data.get("metadata", {}),
            )
            self.session.add(chunk)
            created.append(chunk)

        await self.session.flush()
        return created

    async def delete_by_document_version(
        self,
        document_version_id: uuid.UUID,
    ) -> int:
        """Delete all chunks for a document version.

        Returns the number of deleted rows.
        """
        stmt = delete(Chunk).where(
            Chunk.document_version_id == document_version_id
        )
        result = await self.session.execute(stmt)
        return result.rowcount  # type: ignore[return-value]
