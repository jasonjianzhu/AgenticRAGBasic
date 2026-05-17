"""Chat service — orchestrates Agent execution and SSE event streaming."""
from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.usage import UsageLimits
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.core.agent import AgentDeps, create_agent
from app.agent.core.prompts import build_system_prompt
from app.agent.services.session import SessionService
from app.agent.sql.executor import SQLExecutor
from app.agent.sql.schema_loader import SchemaLoader
from app.agent.sql.validator import SQLValidator
from app.common.core.config import Settings, get_settings
from app.common.core.logging import get_logger
from app.rag.services.rag_service import RAGService

logger = get_logger(__name__)

_agent: Agent | None = None
_schema_description: str = ""
_EMPTY_RESPONSE_RETRY_HINT = (
    "上一轮没有生成最终答案。请基于当前会话上下文回答用户刚才的问题；"
    "如涉及业务数据请调用 sql_query；必须输出最终回答，不要只输出思考过程。"
)


def _suffix_prefix_len(text: str, marker: str) -> int:
    """Length of the longest text suffix that is also a marker prefix."""
    max_len = min(len(text), len(marker) - 1)
    for size in range(max_len, 0, -1):
        if marker.startswith(text[-size:]):
            return size
    return 0


class _ThinkTagStreamParser:
    """Split streamed text into answer tokens and thinking chunks."""

    _OPEN = "<think>"
    _CLOSE = "</think>"

    def __init__(self) -> None:
        self._in_think = False
        self._pending = ""

    def feed(self, text: str) -> list[tuple[str, str]]:
        events: list[tuple[str, str]] = []
        remaining = self._pending + text
        self._pending = ""

        while remaining:
            marker = self._CLOSE if self._in_think else self._OPEN
            marker_idx = remaining.find(marker)

            if marker_idx >= 0:
                content = remaining[:marker_idx]
                if content:
                    events.append((self._event_type, content))
                self._in_think = not self._in_think
                remaining = remaining[marker_idx + len(marker):]
                continue

            pending_len = _suffix_prefix_len(remaining, marker)
            content = remaining[:-pending_len] if pending_len else remaining
            if content:
                events.append((self._event_type, content))
            self._pending = remaining[-pending_len:] if pending_len else ""
            break

        return events

    def flush(self) -> list[tuple[str, str]]:
        if not self._pending:
            return []
        event = (self._event_type, self._pending)
        self._pending = ""
        return [event]

    @property
    def _event_type(self) -> str:
        return "thinking" if self._in_think else "token"


async def _emit_parsed_text(
    content: str,
    parser: _ThinkTagStreamParser,
    event_queue: asyncio.Queue[dict | None],
) -> None:
    for event_type, text in parser.feed(content):
        await event_queue.put({
            "event": event_type,
            "data": {"content": text},
        })


async def _handle_agent_stream_event(
    event: Any,
    parser: _ThinkTagStreamParser,
    event_queue: asyncio.Queue[dict | None],
) -> None:
    if isinstance(event, PartStartEvent):
        part = event.part
        if isinstance(part, ThinkingPart) and part.content:
            await event_queue.put({
                "event": "thinking",
                "data": {"content": part.content},
            })
        elif isinstance(part, TextPart) and part.content:
            await _emit_parsed_text(part.content, parser, event_queue)
        return

    if isinstance(event, PartDeltaEvent):
        delta = event.delta
        if isinstance(delta, ThinkingPartDelta):
            content = delta.content_delta
            if content:
                await event_queue.put({
                    "event": "thinking",
                    "data": {"content": content},
                })
        elif isinstance(delta, TextPartDelta):
            content = delta.content_delta
            if content:
                await _emit_parsed_text(content, parser, event_queue)


def _new_stream_stats() -> dict[str, Any]:
    return {
        "first_event_type": None,
        "last_event_type": None,
        "thinking_chars": 0,
        "token_chars": 0,
        "tool_start_count": 0,
        "tool_result_count": 0,
        "chart_count": 0,
        "data_table_count": 0,
        "citation_count": 0,
    }


def _record_stream_event(stream_stats: dict[str, Any], event: dict) -> None:
    event_type = event["event"]
    if stream_stats["first_event_type"] is None:
        stream_stats["first_event_type"] = event_type
    stream_stats["last_event_type"] = event_type

    if event_type == "thinking":
        content = event.get("data", {}).get("content", "")
        stream_stats["thinking_chars"] += len(content) if isinstance(content, str) else 0
    elif event_type == "token":
        content = event.get("data", {}).get("content", "")
        stream_stats["token_chars"] += len(content) if isinstance(content, str) else 0
    elif event_type == "tool_start":
        stream_stats["tool_start_count"] += 1
    elif event_type == "tool_result":
        stream_stats["tool_result_count"] += 1
    elif event_type == "chart":
        stream_stats["chart_count"] += 1
    elif event_type == "data_table":
        stream_stats["data_table_count"] += 1
    elif event_type == "citation":
        stream_stats["citation_count"] += 1


def _has_visible_stream_events(stream_stats: dict[str, Any]) -> bool:
    return (
        stream_stats["token_chars"] > 0
        or stream_stats["tool_result_count"] > 0
        or stream_stats["chart_count"] > 0
        or stream_stats["data_table_count"] > 0
    )


def _summarize_model_messages(messages: list[ModelMessage]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "new_messages_count": len(messages),
        "model_request_count": 0,
        "model_response_count": 0,
        "thinking_part_count": 0,
        "thinking_chars": 0,
        "text_part_count": 0,
        "text_chars": 0,
        "tool_call_part_count": 0,
        "tool_return_part_count": 0,
        "tool_names": [],
        "response_part_types": [],
    }
    tool_names: list[str] = []

    for msg in messages:
        parts = getattr(msg, "parts", [])
        if isinstance(msg, ModelRequest):
            summary["model_request_count"] += 1
        elif isinstance(msg, ModelResponse):
            summary["model_response_count"] += 1
            summary["response_part_types"].append([part.__class__.__name__ for part in parts])

        for part in parts:
            if isinstance(part, ThinkingPart):
                summary["thinking_part_count"] += 1
                summary["thinking_chars"] += len(part.content or "")
            elif isinstance(part, TextPart):
                summary["text_part_count"] += 1
                summary["text_chars"] += len(part.content or "")
            elif isinstance(part, ToolCallPart):
                summary["tool_call_part_count"] += 1
                tool_names.append(part.tool_name)
            elif isinstance(part, ToolReturnPart):
                summary["tool_return_part_count"] += 1
                tool_names.append(part.tool_name)

    summary["tool_names"] = sorted(set(tool_names))
    summary["response_part_types"] = summary["response_part_types"][:10]
    return summary


def _build_empty_response_retry_message(message: str) -> str:
    return f"{message}\n\n[系统恢复提示] {_EMPTY_RESPONSE_RETRY_HINT}"


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
        import anthropic
        from pydantic_ai.providers.anthropic import AnthropicProvider
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

        # 6. event_stream_handler — captures text and thinking deltas in real-time.
        # DeepSeek can send thinking as native Anthropic thinking parts or as
        # <think> tags inside text deltas; build a fresh parser per run.

        def make_stream_handler():
            think_parser = _ThinkTagStreamParser()

            async def stream_handler(run_ctx, event_stream):
                async for event in event_stream:
                    await _handle_agent_stream_event(event, think_parser, event_queue)
                for event_type, content in think_parser.flush():
                    await event_queue.put({
                        "event": event_type,
                        "data": {"content": content},
                    })

            return stream_handler

        # 7. Run agent in background task
        result_text = ""
        agent_error = None
        collected_charts: list[dict] = []
        new_messages: list[ModelMessage] = []
        stream_stats = _new_stream_stats()
        retry_attempted = False
        retry_skipped = False
        first_empty_summary: dict[str, Any] = {}
        first_empty_stream_stats: dict[str, Any] = {}

        async def run_agent(run_message: str, retry_attempt: int = 0):
            nonlocal result_text, agent_error, new_messages
            result_text = ""
            agent_error = None
            new_messages = []
            try:
                result = await agent.run(
                    run_message,
                    deps=deps,
                    message_history=message_history,
                    model_settings={
                        "temperature": self._settings.llm_temperature,
                        "max_tokens": self._settings.llm_max_tokens,
                    },
                    usage_limits=UsageLimits(tool_calls_limit=8),
                    event_stream_handler=make_stream_handler(),
                )
                result_text = result.response.text or ""
                new_messages = result.new_messages()
                logger.info("agent_run_complete", text_len=len(result_text), retry_attempt=retry_attempt)
            except Exception as e:
                logger.error("agent_run_error", error=str(e), retry_attempt=retry_attempt)
                agent_error = str(e)
            finally:
                await event_queue.put(None)  # signal done

        agent_task = asyncio.create_task(run_agent(message))

        # 8. Yield all events from queue until agent completes
        try:
            while True:
                event = await event_queue.get()
                if event is None:
                    break
                _record_stream_event(stream_stats, event)
                if event["event"] == "chart":
                    collected_charts.append(event["data"])
                yield event
        except (asyncio.CancelledError, GeneratorExit):
            # Client disconnected — cancel the agent task to free resources
            agent_task.cancel()
            logger.info("agent_task_cancelled_on_disconnect", session_id=str(session_id))
            return

        await agent_task

        first_run_stream_stats = dict(stream_stats)
        first_run_summary = _summarize_model_messages(new_messages)
        if first_run_stream_stats["token_chars"] == 0:
            logger.warning(
                "agent_stream_no_answer_tokens",
                session_id=str(session_id),
                message_preview=message[:80],
                has_thinking=first_run_stream_stats["thinking_chars"] > 0,
                thinking_chars=first_run_stream_stats["thinking_chars"],
                token_chars=first_run_stream_stats["token_chars"],
                tool_call_count=first_run_stream_stats["tool_start_count"],
                agent_error=agent_error,
                retry_attempt=0,
            )

        if not agent_error and not result_text:
            first_empty_summary = first_run_summary
            first_empty_stream_stats = first_run_stream_stats
            logger.warning(
                "agent_empty_response_diagnostic",
                session_id=str(session_id),
                message_preview=message[:80],
                result_text_len=len(result_text),
                stream_stats=first_empty_stream_stats,
                message_summary=first_empty_summary,
            )

            if _has_visible_stream_events(first_run_stream_stats):
                retry_skipped = True
                logger.info(
                    "agent_empty_response_retry_skipped",
                    session_id=str(session_id),
                    reason="visible_events_already_emitted",
                    stream_stats=first_run_stream_stats,
                    message_summary=first_empty_summary,
                )
            else:
                retry_attempted = True
                logger.info(
                    "agent_empty_response_retry_start",
                    session_id=str(session_id),
                    message_preview=message[:80],
                    reason="empty_result_text",
                    stream_stats=first_run_stream_stats,
                    message_summary=first_empty_summary,
                )
                event_queue = asyncio.Queue()
                retry_message = _build_empty_response_retry_message(message)
                agent_task = asyncio.create_task(run_agent(retry_message, retry_attempt=1))

                try:
                    while True:
                        event = await event_queue.get()
                        if event is None:
                            break
                        _record_stream_event(stream_stats, event)
                        if event["event"] == "chart":
                            collected_charts.append(event["data"])
                        yield event
                except (asyncio.CancelledError, GeneratorExit):
                    agent_task.cancel()
                    logger.info(
                        "agent_task_cancelled_on_disconnect",
                        session_id=str(session_id),
                        retry_attempt=1,
                    )
                    return

                await agent_task
                retry_summary = _summarize_model_messages(new_messages)
                retry_stream_stats = {
                    key: stream_stats[key] - first_run_stream_stats.get(key, 0)
                    for key in (
                        "thinking_chars",
                        "token_chars",
                        "tool_start_count",
                        "tool_result_count",
                        "chart_count",
                        "data_table_count",
                        "citation_count",
                    )
                }
                retry_stream_stats["cumulative_first_event_type"] = stream_stats["first_event_type"]
                retry_stream_stats["cumulative_last_event_type"] = stream_stats["last_event_type"]
                logger.info(
                    "agent_empty_response_retry_result",
                    session_id=str(session_id),
                    recovered=bool(result_text),
                    retry_text_len=len(result_text),
                    retry_error=agent_error,
                    retry_stream_stats=retry_stream_stats,
                    retry_message_summary=retry_summary,
                )
                if retry_stream_stats["token_chars"] == 0:
                    logger.warning(
                        "agent_stream_no_answer_tokens",
                        session_id=str(session_id),
                        message_preview=message[:80],
                        has_thinking=retry_stream_stats["thinking_chars"] > 0,
                        thinking_chars=retry_stream_stats["thinking_chars"],
                        token_chars=retry_stream_stats["token_chars"],
                        tool_call_count=retry_stream_stats["tool_start_count"],
                        agent_error=agent_error,
                        retry_attempt=1,
                    )

        # 9. Save assistant message + tool call history
        if result_text:
            cleaned_text = _clean_think_tags(result_text)
            try:
                tool_calls_meta, final_thinking = self._extract_tool_calls_meta(new_messages)
                from app.common.db.models import ChatMessage
                from app.common.db.session import async_session_factory
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

        # 10. Emit error, fallback, or citations
        if agent_error:
            logger.info(
                "agent_error_emitted",
                session_id=str(session_id),
                error=agent_error,
                retry_attempted=retry_attempted,
                stream_stats=stream_stats,
                message_summary=_summarize_model_messages(new_messages),
            )
            yield {"event": "error", "data": {"message": f"Agent 执行失败: {agent_error}"}}
        elif not result_text:
            # Model returned empty text (e.g. only thinking, no output)
            fallback = "抱歉，模型未能生成有效回复，请重新提问或换一种问法。"
            logger.warning(
                "agent_empty_response",
                session_id=str(session_id),
                message_preview=message[:80],
                retry_attempted=retry_attempted,
                retry_skipped=retry_skipped,
                stream_stats=stream_stats,
                first_message_summary=first_empty_summary,
                first_stream_stats=first_empty_stream_stats,
                message_summary=_summarize_model_messages(new_messages),
            )
            yield {"event": "token", "data": {"content": fallback}}
        else:
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
                        stream_stats["citation_count"] += 1
                        yield {"event": "citation", "data": cit}
                        emitted.add(key)
                    else:
                        for cite_key, cit in deps.collected_citations.items():
                            if cite_key in key or key in cite_key:
                                if cite_key not in emitted:
                                    cit["index"] = len(emitted) + 1
                                    stream_stats["citation_count"] += 1
                                    yield {"event": "citation", "data": cit}
                                    emitted.add(cite_key)
                                break

        # 11. Done
        _chat_duration = round((_time.monotonic() - _chat_start) * 1000)
        logger.info("agent_chat_complete",
                     session_id=str(session_id),
                     duration_ms=_chat_duration,
                     has_error=bool(agent_error),
                     text_len=len(result_text),
                     retry_attempted=retry_attempted,
                     retry_skipped=retry_skipped)
        logger.info(
            "agent_stream_lifecycle",
            session_id=str(session_id),
            first_event_type=stream_stats["first_event_type"],
            last_event_type=stream_stats["last_event_type"],
            thinking_chars=stream_stats["thinking_chars"],
            token_chars=stream_stats["token_chars"],
            tool_start_count=stream_stats["tool_start_count"],
            tool_result_count=stream_stats["tool_result_count"],
            chart_count=stream_stats["chart_count"],
            data_table_count=stream_stats["data_table_count"],
            citation_count=stream_stats["citation_count"],
            retry_attempted=retry_attempted,
            retry_skipped=retry_skipped,
            ended_by="error" if agent_error else "done",
        )
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
