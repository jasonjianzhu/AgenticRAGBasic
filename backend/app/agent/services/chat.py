"""Chat service — orchestrates Agent execution and SSE event streaming."""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any, AsyncIterator

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.config import Settings, get_settings
from app.common.core.logging import get_logger
from app.agent.core.agent import AgentDeps, create_agent
from app.agent.core.prompts import build_system_prompt
from app.agent.services.session import SessionService
from app.agent.sql.executor import SQLExecutor
from app.agent.sql.schema_loader import SchemaLoader
from app.agent.sql.validator import SQLValidator
from app.rag.services.rag_service import RAGService

logger = get_logger(__name__)

# Module-level Agent singleton (created once with schema)
_agent: Agent | None = None
_schema_description: str = ""


async def _get_or_create_agent(settings: Settings) -> Agent:
    """Get or create the PydanticAI Agent singleton."""
    global _agent, _schema_description

    if _agent is not None:
        return _agent

    # Load business DB schema for prompt injection
    try:
        from app.agent.sql.executor import _get_business_session_factory
        factory = _get_business_session_factory(settings)
        allowed = _parse_allowed_tables(settings.business_db_allowed_tables)
        loader = SchemaLoader(factory, allowed_tables=allowed)
        _schema_description = await loader.format_for_prompt()
        logger.info("business_db_schema_loaded", tables=_schema_description[:200])
    except Exception as e:
        logger.warning("business_db_schema_load_failed", error=str(e))
        _schema_description = "（业务数据库暂不可用）"

    system_prompt = build_system_prompt(_schema_description)

    # Build PydanticAI model name from settings
    # MiniMax uses OpenAI-compatible API, so we use openai: prefix
    model_name = f"openai:{settings.llm_model}"

    _agent = create_agent(model_name=model_name, system_prompt=system_prompt)
    return _agent


def _parse_allowed_tables(config_value: str) -> set[str] | None:
    """Parse BUSINESS_DB_ALLOWED_TABLES config."""
    if config_value.strip() == "*":
        return None
    return {t.strip() for t in config_value.split(",") if t.strip()}


class ChatService:
    """Orchestrates Agent chat: receives message, runs Agent, streams SSE events.

    Args:
        rag_service: Phase 2 RAG service for knowledge QA.
        db_session: Async DB session for session persistence.
        settings: Application settings.
    """

    def __init__(
        self,
        rag_service: RAGService,
        db_session: AsyncSession,
        settings: Settings | None = None,
    ) -> None:
        self._rag_service = rag_service
        self._db_session = db_session
        self._settings = settings or get_settings()
        self._session_service = SessionService(db_session, self._settings)

    async def chat_stream(
        self,
        message: str,
        session_id: uuid.UUID | None = None,
        kb_ids: list[uuid.UUID] | None = None,
    ) -> AsyncIterator[dict]:
        """Process a chat message and yield SSE events.

        Event types: tool_start, tool_result, citation, data_table, chart, token, done, error
        """
        # 1. Get or create session
        if session_id:
            session = await self._session_service.get_session(session_id)
            if not session:
                yield {"event": "error", "data": {"message": f"会话 {session_id} 不存在"}}
                return
        else:
            session = await self._session_service.create_session()
            session_id = session.id

        # 2. Save user message
        await self._session_service.add_message(session_id, role="user", content=message)

        # Update title from first message
        msg_count = await self._session_service.get_message_count(session_id)
        if msg_count <= 1:
            await self._session_service.update_title_from_first_message(session_id, message)

        # 3. Build message history for Agent
        history = await self._session_service.get_context_messages(session_id)

        # 4. Set up event queue for tool callbacks
        event_queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def emit_event(event_type: str, data: Any) -> None:
            await event_queue.put({"event": event_type, "data": data})

        # 5. Build Agent dependencies
        sql_executor = SQLExecutor(self._settings)
        allowed = _parse_allowed_tables(self._settings.business_db_allowed_tables)
        sql_validator = SQLValidator(
            allowed_tables=allowed,
            max_rows=self._settings.business_db_max_rows,
        )

        deps = AgentDeps(
            rag_service=self._rag_service,
            sql_executor=sql_executor,
            sql_validator=sql_validator,
            kb_ids=kb_ids or [],
            emit_event=emit_event,
        )

        # 6. Get Agent
        agent = await _get_or_create_agent(self._settings)

        # 7. Run Agent in background task, stream results
        result_text = ""
        agent_error = None

        async def run_agent():
            nonlocal result_text, agent_error
            try:
                # Build message history for PydanticAI
                # PydanticAI expects the last user message separately
                message_history = self._build_message_history(history[:-1] if history else [])

                result = await agent.run(
                    message,
                    deps=deps,
                    message_history=message_history,
                    model_settings={
                        "temperature": self._settings.llm_temperature,
                        "max_tokens": self._settings.llm_max_tokens,
                    },
                )
                result_text = result.data
            except Exception as e:
                logger.error("agent_run_error", error=str(e))
                agent_error = str(e)
            finally:
                await event_queue.put(None)  # signal done

        # Start agent in background
        agent_task = asyncio.create_task(run_agent())

        # Yield tool events as they come in
        while True:
            event = await event_queue.get()
            if event is None:
                break
            yield event

        # Wait for agent to finish
        await agent_task

        # 8. Stream the final text response as tokens
        if agent_error:
            yield {"event": "error", "data": {"message": f"Agent 执行失败: {agent_error}"}}
        elif result_text:
            # Clean think tags
            cleaned = re.sub(r"<think>[\s\S]*?</think>", "", result_text).strip()
            if "<think>" in cleaned:
                cleaned = re.sub(r"<think>[\s\S]*", "", cleaned).strip()

            # Stream tokens (split into chunks for smooth rendering)
            chunk_size = 4
            for i in range(0, len(cleaned), chunk_size):
                yield {"event": "token", "data": {"content": cleaned[i:i + chunk_size]}}

        # 9. Save assistant message
        await self._session_service.add_message(
            session_id,
            role="assistant",
            content=result_text or "",
            message_type="text",
        )

        # 10. Done
        yield {"event": "done", "data": {"session_id": str(session_id)}}

    def _build_message_history(self, history: list[dict]) -> list[ModelMessage]:
        """Convert chat history to PydanticAI ModelMessage format."""
        messages: list[ModelMessage] = []
        for msg in history:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
            elif role == "assistant":
                messages.append(ModelResponse(parts=[TextPart(content=content)]))
        return messages
