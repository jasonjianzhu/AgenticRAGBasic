"""Knowledge base service - business logic layer."""
from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import KnowledgeBase
from app.db.repositories.kb import KBRepository

logger = get_logger(__name__)


class KBServiceError(Exception):
    """Base exception for KB service errors."""


class KBNotFoundError(KBServiceError):
    """Raised when a knowledge base is not found."""


class KBDuplicateNameError(KBServiceError):
    """Raised when a knowledge base name already exists."""


class KBService:
    """Service layer for knowledge base operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.repo = KBRepository(session)
        self.session = session

    async def create_kb(
        self,
        *,
        name: str,
        description: str | None = None,
        settings: dict | None = None,
    ) -> KnowledgeBase:
        """Create a new knowledge base."""
        # Check for duplicate name
        existing = await self.repo.get_by_name(name)
        if existing is not None:
            raise KBDuplicateNameError(f"Knowledge base with name '{name}' already exists")

        kb = await self.repo.create(name=name, description=description, settings=settings)
        logger.info("kb_created", kb_id=str(kb.id), name=name)
        return kb

    async def get_kb(self, kb_id: uuid.UUID) -> KnowledgeBase:
        """Get a knowledge base by ID, raising if not found."""
        kb = await self.repo.get_by_id(kb_id)
        if kb is None:
            raise KBNotFoundError(f"Knowledge base {kb_id} not found")
        return kb

    async def get_kb_with_stats(self, kb_id: uuid.UUID) -> tuple[KnowledgeBase, dict]:
        """Get a knowledge base with statistics."""
        kb = await self.get_kb(kb_id)
        stats = await self.repo.get_statistics(kb_id)
        return kb, stats

    async def list_kbs(self, *, skip: int = 0, limit: int = 100) -> list[KnowledgeBase]:
        """List all knowledge bases."""
        kbs = await self.repo.list_all(skip=skip, limit=limit)
        return list(kbs)

    async def update_kb(
        self,
        kb_id: uuid.UUID,
        **kwargs,
    ) -> KnowledgeBase:
        """Update a knowledge base."""
        kb = await self.get_kb(kb_id)

        # Check for duplicate name if name is being changed
        new_name = kwargs.get("name")
        if new_name is not None and new_name != kb.name:
            existing = await self.repo.get_by_name(new_name)
            if existing is not None:
                raise KBDuplicateNameError(f"Knowledge base with name '{new_name}' already exists")

        # Filter out None values
        update_data = {k: v for k, v in kwargs.items() if v is not None}
        if update_data:
            kb = await self.repo.update(kb, **update_data)
            logger.info("kb_updated", kb_id=str(kb_id), fields=list(update_data.keys()))

        return kb

    async def delete_kb(self, kb_id: uuid.UUID) -> None:
        """Delete a knowledge base."""
        kb = await self.get_kb(kb_id)
        await self.repo.delete(kb)
        logger.info("kb_deleted", kb_id=str(kb_id))
