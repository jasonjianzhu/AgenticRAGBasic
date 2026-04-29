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
    PartDeltaEvent,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolReturnPart,
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
        # Anthropic-compatible API (e.g. DeepSeek, MiniMax Anthropic endpoint)
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
        provider = None
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

    Architecture: agent.run() in background task + event_stream_handler for streaming.
    - agent.run() runs in asyncio.create_task, doesn't block the SSE generator
    - event_stream_handler captures TextPartDelta (real-time text) and ThinkingPartDelta
    - Tool events emitted via event queue from within tool functions
    - result.response.text used for persistence — always complete, no truncation
    - result.new_messages() captures tool call history for multi-turn context
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
        import time as _time
        _chat_start = _time.monotonic()
        logger.info("agent_chat_start",
                     message=message[:80],
                     session_id=str(session_id) if session_id else "new",
                     kb_ids=[str(k) for k in (kb_ids or [])])
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

        await self._db_session.commit()

        # 2. Build history
        history = await self._session_service.get_context_messages(session_id)

        # 3. Event queue — all events (text tokens, thinking, tool events) go through here
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

        # 6. event_stream_handler — captures text and thinking deltas in real-time
        #
        # DeepSeek via OpenAI-compatible API sends thinking content as <think>...</think>
        # tags inside TextPartDelta (not as ThinkingPartDelta). We parse the tags in
        # real-time to split into "thinking" and "token" events.
        #
        # State machine: _in_think tracks whether we're inside a <think> block.

        _in_think = False

        async def stream_handler(run_ctx, event_stream):
            nonlocal _in_think
            async for event in event_stream:
                if isinstance(event, PartDeltaEvent):
                    delta = event.delta
                    if isinstance(delta, ThinkingPartDelta):
                        # Native thinking support (Anthropic-style) — forward directly
                        content = delta.content_delta
                        if content:
                            await event_queue.put({
                                "event": "thinking",
                                "data": {"content": content},
                            })
                    elif isinstance(delta, TextPartDelta):
                        content = delta.content_delta
                        if not content:
                            continue
                        # Parse <think> tags from the text stream
                        await _parse_think_tags(content, event_queue)

        async def _parse_think_tags(text: str, queue: asyncio.Queue) -> None:
            """Parse <think>...</think> tags from streaming text chunks.

            Handles tags that may be split across multiple chunks:
            - chunk1: "Let me <thi"  chunk2: "nk>reasoning"  chunk3: "</think>answer"
            """
            nonlocal _in_think
            remaining = text

            while remaining:
                if _in_think:
                    # Inside <think> block — look for closing tag
                    close_idx = remaining.find("</think>")
                    if close_idx != -1:
                        # Found closing tag — emit thinking content, switch to text mode
                        think_content = remaining[:close_idx]
                        if think_content:
                            await queue.put({
                                "event": "thinking",
                                "data": {"content": think_content},
                            })
                        _in_think = False
                        remaining = remaining[close_idx + len("</think>"):]
                    else:
                        # No closing tag yet — all remaining is thinking content
                        if remaining:
                            await queue.put({
                                "event": "thinking",
                                "data": {"content": remaining},
                            })
                        remaining = ""
                else:
                    # Outside <think> block — look for opening tag
                    open_idx = remaining.find("<think>")
                    if open_idx != -1:
                        # Found opening tag — emit text before it, switch to think mode
                        text_before = remaining[:open_idx]
                        if text_before:
                            await queue.put({
                                "event": "token",
                                "data": {"content": text_before},
                            })
                        _in_think = True
                        remaining = remaining[open_idx + len("<think>"):]
                    else:
                        # No opening tag — all remaining is regular text
                        if remaining:
                            await queue.put({
                                "event": "token",
                                "data": {"content": remaining},
                            })
                        remaining = ""

        # 7. Run agent in background task
        result_text = ""
        agent_error = None
        collected_charts: list[dict] = []
        new_messages: list[ModelMessage] = []

        async def run_agent():
            nonlocal result_text, agent_error, new_messages
            try:
                result = await agent.run(
                    message,
                    deps=deps,
                    message_history=message_history,
                    model_settings={
                        "temperature": self._settings.llm_temperature,
                        "max_tokens": self._settings.llm_max_tokens,
                    },
                    usage_limits=UsageLimits(tool_calls_limit=8),
                    event_stream_handler=stream_handler,
                )
                result_text = result.response.text or ""
                new_messages = result.new_messages()
                logger.info("agent_run_complete", text_len=len(result_text))
            except Exception as e:
                logger.error("agent_run_error", error=str(e))
                agent_error = str(e)
            finally:
                await event_queue.put(None)  # signal done

        agent_task = asyncio.create_task(run_agent())

        # 8. Yield all events from queue until agent completes
        while True:
            event = await event_queue.get()
            if event is None:
                break
            if event["event"] == "chart":
                collected_charts.append(event["data"])
            yield event

        await agent_task

        # 9. Save assistant message + tool call history
        if result_text:
            cleaned_text = _clean_think_tags(result_text)
            try:
                tool_calls_meta, final_thinking = self._extract_tool_calls_meta(new_messages)
                from app.common.db.session import async_session_factory
                from app.common.db.models import ChatMessage
                async with async_session_factory() as save_session:
                    msg = ChatMessage(
                        session_id=session_id,
                        role="assistant",
                        content=cleaned_text,
                        message_type="text",
                        metadata_={
                            "charts": collected_charts if collected_charts else [],
                            "tool_calls": tool_calls_meta if tool_calls_meta else [],
                            "final_thinking": final_thinking if final_thinking else {},
                        },
                    )
                    save_session.add(msg)
                    await save_session.commit()
            except Exception as e:
                logger.error("save_assistant_message_error", error=str(e))

        # 10. Emit error or citations
        if agent_error:
            yield {"event": "error", "data": {"message": f"Agent 执行失败: {agent_error}"}}
        elif result_text:
            cleaned_text = _clean_think_tags(result_text)
            if deps.collected_citations:
                cited_keys = re.findall(r'【([^】]+)】', cleaned_text)
                emitted: set[str] = set()
                for key in cited_keys:
                    key = key.strip()
                    if key in emitted:
                        continue
                    if key in deps.collected_citations:
                        cit = deps.collected_citations[key]
                        cit["index"] = len(emitted) + 1
                        yield {"event": "citation", "data": cit}
                        emitted.add(key)
                    else:
                        for cite_key, cit in deps.collected_citations.items():
                            if cite_key in key or key in cite_key:
                                if cite_key not in emitted:
                                    cit["index"] = len(emitted) + 1
                                    yield {"event": "citation", "data": cit}
                                    emitted.add(cite_key)
                                break

        # 11. Done
        _chat_duration = round((_time.monotonic() - _chat_start) * 1000)
        logger.info("agent_chat_complete",
                     session_id=str(session_id),
                     duration_ms=_chat_duration,
                     has_error=bool(agent_error),
                     text_len=len(result_text))
        yield {"event": "done", "data": {"session_id": str(session_id)}}

    def _build_message_history(self, history: list[dict]) -> list[ModelMessage]:
        """Build PydanticAI message history from DB records.

        Includes tool call/return parts WITH thinking blocks from metadata.
        DeepSeek requires thinking blocks (content + signature) to be passed
        back alongside tool calls in history.

        IMPORTANT: ThinkingPart must have provider_name="anthropic" so that
        PydanticAI's Anthropic provider serializes it as a proper thinking block
        (not as <think> text). Without this, DeepSeek returns 400.
        """
        messages: list[ModelMessage] = []
        for msg in history:
            role = msg["role"]
            content = msg["content"]
            metadata = msg.get("metadata", {}) or {}

            if role == "user":
                messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
            elif role == "assistant":
                tool_calls_meta = metadata.get("tool_calls", [])

                if tool_calls_meta:
                    for tc in tool_calls_meta:
                        tool_name = tc.get("tool_name", "")
                        tool_call_id = tc.get("tool_call_id", f"tc_{tool_name}")
                        tool_args = tc.get("args", {})
                        tool_result_text = tc.get("result_summary", "")
                        thinking_content = tc.get("thinking_content", "")
                        thinking_signature = tc.get("thinking_signature")

                        # ModelResponse: ThinkingPart + ToolCallPart
                        response_parts: list = []
                        if thinking_content and thinking_signature:
                            response_parts.append(ThinkingPart(
                                content=thinking_content,
                                signature=thinking_signature,
                                provider_name="anthropic",
                            ))
                        response_parts.append(ToolCallPart(
                            tool_name=tool_name,
                            args=tool_args if isinstance(tool_args, dict) else {},
                            tool_call_id=tool_call_id,
                        ))
                        messages.append(ModelResponse(parts=response_parts))

                        # ModelRequest: ToolReturnPart
                        messages.append(ModelRequest(parts=[
                            ToolReturnPart(
                                tool_name=tool_name,
                                content=tool_result_text,
                                tool_call_id=tool_call_id,
                            )
                        ]))

                # Final text response — include thinking if available
                final_thinking = metadata.get("final_thinking", {})
                final_parts: list = []
                ft_content = final_thinking.get("thinking_content", "")
                ft_signature = final_thinking.get("thinking_signature")
                if ft_content and ft_signature:
                    final_parts.append(ThinkingPart(
                        content=ft_content,
                        signature=ft_signature,
                        provider_name="anthropic",
                    ))
                final_parts.append(TextPart(content=content))
                messages.append(ModelResponse(parts=final_parts))

        return messages

    @staticmethod
    def _extract_tool_calls_meta(new_messages: list[ModelMessage]) -> tuple[list[dict], dict]:
        """Extract tool call metadata + thinking from PydanticAI messages for DB persistence.

        Returns:
            (tool_calls, final_thinking) where final_thinking has content + signature
            for the last assistant response's thinking block.
        """
        tool_calls: list[dict] = []
        final_thinking: dict = {}

        # Collect tool returns keyed by tool_call_id
        returns_by_id: dict[str, str] = {}
        for msg in new_messages:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, ToolReturnPart):
                        content = part.content
                        if isinstance(content, str):
                            summary = content[:500]
                        else:
                            summary = str(content)[:500]
                        returns_by_id[part.tool_call_id] = summary

        # Extract tool calls with thinking, and track final response thinking
        for msg in new_messages:
            if isinstance(msg, ModelResponse):
                thinking_content = ""
                thinking_signature = None
                has_tool_call = False

                for part in msg.parts:
                    if isinstance(part, ThinkingPart):
                        thinking_content = part.content or ""
                        thinking_signature = part.signature

                for part in msg.parts:
                    if isinstance(part, ToolCallPart):
                        has_tool_call = True
                        tool_calls.append({
                            "tool_name": part.tool_name,
                            "tool_call_id": part.tool_call_id,
                            "args": part.args if isinstance(part.args, dict) else {},
                            "result_summary": returns_by_id.get(part.tool_call_id, ""),
                            "thinking_content": thinking_content,
                            "thinking_signature": thinking_signature,
                        })

                # If this response has TextPart (final answer) with thinking, save it
                if not has_tool_call and thinking_content:
                    final_thinking = {
                        "thinking_content": thinking_content,
                        "thinking_signature": thinking_signature,
                    }

        return tool_calls, final_thinking
