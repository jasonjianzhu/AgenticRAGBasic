"""Session service — manages chat sessions and message history."""
from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.config import Settings, get_settings
from app.common.db.models import ChatMessage, ChatSession
from app.common.db.repositories.sessions import SessionRepository


class SessionService:
    """Business logic for chat session management."""

    def __init__(self, db_session: AsyncSession, settings: Settings | None = None) -> None:
        self._repo = SessionRepository(db_session)
        self._settings = settings or get_settings()

    async def create_session(self, title: str = "新对话") -> ChatSession:
        return await self._repo.create_session(title=title)

    async def get_session(self, session_id: uuid.UUID) -> ChatSession | None:
        return await self._repo.get_session(session_id)

    async def list_sessions(
        self, *, status: str | None = "active", skip: int = 0, limit: int = 20
    ) -> tuple[Sequence[ChatSession], int]:
        return await self._repo.list_sessions(status=status, skip=skip, limit=limit)

    async def delete_session(self, session_id: uuid.UUID) -> bool:
        return await self._repo.delete_session(session_id)

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
        return await self._repo.add_message(
            session_id=session_id,
            role=role,
            content=content,
            message_type=message_type,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            metadata=metadata,
        )

    async def get_context_messages(self, session_id: uuid.UUID) -> list[dict]:
        """Get recent messages formatted for LLM context.

        Returns messages in the format expected by PydanticAI:
        [{"role": "user", "content": "...", "metadata": {...}}, ...]

        Includes metadata (tool_calls, charts) so that _build_message_history
        can reconstruct tool call/return parts for multi-turn context.
        """
        window = self._settings.agent_context_window
        messages = await self._repo.get_recent_messages(session_id, limit=window)

        context = []
        for msg in messages:
            # Only include user and assistant messages in LLM context
            if msg.role in ("user", "assistant"):
                context.append({
                    "role": msg.role,
                    "content": msg.content,
                    "metadata": msg.metadata_ if msg.metadata_ else {},
                })
        return context

    async def update_title_from_first_message(self, session_id: uuid.UUID, content: str) -> None:
        """Set session title from the first user message."""
        title = content[:50].strip()
        if len(content) > 50:
            title += "..."
        await self._repo.update_session_title(session_id, title)

    async def get_message_count(self, session_id: uuid.UUID) -> int:
        return await self._repo.count_messages(session_id)
