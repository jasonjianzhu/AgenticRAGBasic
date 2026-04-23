"""Chat session repository — data access layer."""
from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.db.models import ChatMessage, ChatSession


class SessionRepository:
    """Repository for ChatSession and ChatMessage CRUD."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Sessions ──────────────────────────────────────────────

    async def create_session(self, title: str = "新对话", metadata: dict | None = None) -> ChatSession:
        chat_session = ChatSession(title=title, metadata_=metadata or {})
        self.session.add(chat_session)
        await self.session.flush()
        return chat_session

    async def get_session(self, session_id: uuid.UUID) -> ChatSession | None:
        stmt = (
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sessions(
        self, *, status: str | None = None, skip: int = 0, limit: int = 20
    ) -> tuple[Sequence[ChatSession], int]:
        base = select(ChatSession)
        count_base = select(func.count(ChatSession.id))
        if status:
            base = base.where(ChatSession.status == status)
            count_base = count_base.where(ChatSession.status == status)

        count_result = await self.session.execute(count_base)
        total = count_result.scalar() or 0

        stmt = base.order_by(ChatSession.updated_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        items = result.scalars().all()
        return items, total

    async def delete_session(self, session_id: uuid.UUID) -> bool:
        chat_session = await self.get_session(session_id)
        if not chat_session:
            return False
        await self.session.delete(chat_session)
        await self.session.flush()
        return True

    async def update_session_title(self, session_id: uuid.UUID, title: str) -> None:
        chat_session = await self.get_session(session_id)
        if chat_session:
            chat_session.title = title
            await self.session.flush()

    # ── Messages ──────────────────────────────────────────────

    async def add_message(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        message_type: str = "text",
        tool_name: str | None = None,
        tool_args: dict | None = None,
        tool_result: dict | None = None,
        metadata: dict | None = None,
    ) -> ChatMessage:
        msg = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            message_type=message_type,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            metadata_=metadata or {},
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def get_recent_messages(
        self, session_id: uuid.UUID, limit: int = 20
    ) -> Sequence[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        messages = list(result.scalars().all())
        messages.reverse()  # chronological order
        return messages

    async def count_messages(self, session_id: uuid.UUID) -> int:
        stmt = select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id)
        result = await self.session.execute(stmt)
        return result.scalar() or 0
