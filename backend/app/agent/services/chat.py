"""Chat service — orchestrates Agent execution and SSE event streaming."""
from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any, AsyncIterator

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
    PartStartEvent,
    PartDeltaEvent,
    TextPartDelta,
)
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic_ai.usage import UsageLimits
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

_agent: Agent | None = None
_schema_description: str = ""


async def _get_or_create_agent(settings: Settings) -> Agent:
    """Get or create the PydanticAI Agent singleton."""
    global _agent, _schema_description

    if _agent is not None:
        return _agent

    import os

    # Determine provider based on LLM_BASE_URL
    base_url = settings.llm_base_url
    api_key = settings.llm_api_key
    model_id = settings.llm_model

    if "/anthropic" in base_url:
        # Anthropic-compatible API (e.g. MiniMax Anthropic endpoint)
        # PydanticAI anthropic: prefix uses Anthropic SDK
        os.environ.setdefault("ANTHROPIC_API_KEY", api_key)
        from pydantic_ai.providers.anthropic import AnthropicProvider
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url)
        provider = AnthropicProvider(anthropic_client=client)
        model_name = f"anthropic:{model_id}"
        logger.info("agent_using_anthropic_provider", base_url=base_url, model=model_id)
    else:
        # OpenAI-compatible API
        os.environ.setdefault("OPENAI_API_KEY", api_key)
        os.environ.setdefault("OPENAI_BASE_URL", base_url)
        provider = None  # use default openai provider
        model_name = f"openai:{model_id}"
        logger.info("agent_using_openai_provider", base_url=base_url, model=model_id)

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
    _agent = create_agent(model_name=model_name, system_prompt=system_prompt, provider=provider)
    return _agent


def _parse_allowed_tables(config_value: str) -> set[str] | None:
    if config_value.strip() == "*":
        return None
    return {t.strip() for t in config_value.split(",") if t.strip()}


def _clean_think_tags(text: str) -> str:
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>[\s\S]*", "", cleaned).strip()
    return cleaned


class ChatService:
    """Orchestrates Agent chat with real-time SSE streaming.

    Uses agent.run() with event_stream_handler for true streaming:
    - Text tokens streamed in real-time as LLM generates them
    - Tool events (tool_start, tool_result, citation, chart) emitted during execution
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
        """Process a chat message and yield SSE events with real-time streaming."""
        # 1. Session management
        if session_id:
            session = await self._session_service.get_session(session_id)
            if not session:
                yield {"event": "error", "data": {"message": f"会话 {session_id} 不存在"}}
                return
        else:
            session = await self._session_service.create_session()
            session_id = session.id

        await self._session_service.add_message(session_id, role="user", content=message)

        msg_count = await self._session_service.get_message_count(session_id)
        if msg_count <= 1:
            await self._session_service.update_title_from_first_message(session_id, message)

        # 2. Build history
        history = await self._session_service.get_context_messages(session_id)

        # 3. Event queue — both tool callbacks and LLM stream events go here
        event_queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def emit_event(event_type: str, data: Any) -> None:
            await event_queue.put({"event": event_type, "data": data})

        # 4. Build deps
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

        # 5. Get Agent
        agent = await _get_or_create_agent(self._settings)
        message_history = self._build_message_history(history[:-1] if history else [])

        # 6. Event stream handler — real-time token streaming
        # Two strategies:
        # - Anthropic API: part_kind='thinking' vs 'text', filter by part kind
        # - OpenAI API: <think> tags in text, filter by buffer matching
        _text_indices: set[int] = set()
        _thinking_indices: set[int] = set()
        _has_thinking_parts = False  # True if provider separates thinking
        _buf = ""
        _in_think = False

        async def stream_handler(run_ctx, event_stream):
            nonlocal _has_thinking_parts, _buf, _in_think
            async for event in event_stream:
                if isinstance(event, PartStartEvent):
                    kind = getattr(event.part, 'part_kind', 'unknown')
                    if kind == 'thinking':
                        _thinking_indices.add(event.index)
                        _has_thinking_parts = True
                    elif kind == 'text':
                        _text_indices.add(event.index)

                elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    # Skip thinking parts (Anthropic provider)
                    if event.index in _thinking_indices:
                        continue

                    content = event.delta.content_delta
                    if not content:
                        continue

                    if _has_thinking_parts:
                        # Provider separates thinking, emit text directly
                        await event_queue.put({"event": "token", "data": {"content": content}})
                    else:
                        # OpenAI provider: need buffer filtering for <think> tags
                        _buf += content
                        await _flush_buf()

            # Final flush for buffer mode
            if not _has_thinking_parts:
                await _flush_buf(force=True)

        async def _flush_buf(force: bool = False):
            nonlocal _buf, _in_think
            while _buf:
                if _in_think:
                    end = _buf.find("</think>")
                    if end != -1:
                        _buf = _buf[end + 8:]
                        _in_think = False
                    else:
                        if len(_buf) > 8:
                            _buf = _buf[-8:]
                        break
                else:
                    start = _buf.find("<think>")
                    if start != -1:
                        if start > 0:
                            await event_queue.put({"event": "token", "data": {"content": _buf[:start]}})
                        _buf = _buf[start + 7:]
                        _in_think = True
                    elif not force and len(_buf) < 7:
                        break
                    elif not force and _buf[-1] == "<":
                        if len(_buf) > 1:
                            await event_queue.put({"event": "token", "data": {"content": _buf[:-1]}})
                            _buf = "<"
                        break
                    else:
                        await event_queue.put({"event": "token", "data": {"content": _buf}})
                        _buf = ""
                        break

        # 7. Run Agent in background with streaming
        result_text = ""
        agent_error = None

        async def run_agent():
            nonlocal result_text, agent_error
            try:
                result = await agent.run(
                    message,
                    deps=deps,
                    message_history=message_history,
                    model_settings={
                        "temperature": self._settings.llm_temperature,
                        "max_tokens": self._settings.llm_max_tokens,
                    },
                    usage_limits=UsageLimits(tool_calls_limit=5),
                    event_stream_handler=stream_handler,
                )
                result_text = result.response.text or ""
            except Exception as e:
                logger.error("agent_run_error", error=str(e))
                agent_error = str(e)
            finally:
                # Save assistant message with independent DB session
                if result_text:
                    try:
                        from app.common.db.session import async_session_factory
                        from app.common.db.models import ChatMessage
                        async with async_session_factory() as save_session:
                            msg = ChatMessage(
                                session_id=session_id,
                                role="assistant",
                                content=_clean_think_tags(result_text),
                                message_type="text",
                                metadata_={},
                            )
                            save_session.add(msg)
                            await save_session.commit()
                    except Exception as e:
                        logger.error("save_assistant_message_error", error=str(e))
                await event_queue.put(None)  # signal done

        agent_task = asyncio.create_task(run_agent())

        # 8. Yield all events (tool events + streaming tokens)
        while True:
            event = await event_queue.get()
            if event is None:
                break
            yield event

        await agent_task

        # 9. Error
        if agent_error:
            yield {"event": "error", "data": {"message": f"Agent 执行失败: {agent_error}"}}

        # 10. Done
        yield {"event": "done", "data": {"session_id": str(session_id)}}

    def _build_message_history(self, history: list[dict]) -> list[ModelMessage]:
        messages: list[ModelMessage] = []
        for msg in history:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
            elif role == "assistant":
                messages.append(ModelResponse(parts=[TextPart(content=content)]))
        return messages
