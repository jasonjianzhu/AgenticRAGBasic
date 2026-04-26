"""MiniMax LLM client using Anthropic-compatible Messages API.

MiniMax M2.7 exposes an Anthropic-compatible /v1/messages endpoint.
This client uses httpx to call it directly, with thinking content filtered out.
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from app.common.core.logging import get_logger
from app.rag.generation.base import BaseLLMClient, LLMMessage, LLMResponse, LLMStreamChunk

logger = get_logger(__name__)


class MiniMaxClient(BaseLLMClient):
    """LLM client for MiniMax M2.7 (Anthropic-compatible Messages API).

    Args:
        base_url: API base URL (e.g. "https://api.minimaxi.com/anthropic").
        api_key: API key for authentication.
        model: Model name (default "MiniMax-M2.7").
        temperature: Generation temperature (default 0.1).
        max_tokens: Maximum tokens to generate (default 2048).
        timeout: HTTP request timeout in seconds (default 60).
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "MiniMax-M2.7",
        temperature: float = 0.1,
        max_tokens: int = 2048,
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout

    @property
    def model_name(self) -> str:
        return self._model

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
        }

    def _build_payload(self, messages: list[LLMMessage], stream: bool = False, **kwargs) -> dict[str, Any]:
        # Anthropic format: system is separate, messages are user/assistant only
        system_text = ""
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_text = m.content
            else:
                api_messages.append({"role": m.role, "content": m.content})

        payload: dict[str, Any] = {
            "model": kwargs.get("model", self._model),
            "messages": api_messages,
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
            "temperature": kwargs.get("temperature", self._temperature),
            "stream": stream,
        }
        if system_text:
            payload["system"] = system_text
        return payload

    async def complete(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        """Generate a complete response via Anthropic Messages API."""
        import time as _time
        _start = _time.monotonic()
        url = f"{self._base_url}/v1/messages"
        payload = self._build_payload(messages, stream=False, **kwargs)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=self._headers())
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException:
            logger.error("llm_complete_timeout", model=self._model, timeout=self._timeout,
                         duration_ms=round((_time.monotonic() - _start) * 1000))
            raise
        except httpx.HTTPStatusError as e:
            logger.error("llm_complete_http_error", model=self._model, status=e.response.status_code,
                         duration_ms=round((_time.monotonic() - _start) * 1000))
            raise
        except Exception as e:
            logger.error("llm_complete_error", model=self._model, error=str(e),
                         duration_ms=round((_time.monotonic() - _start) * 1000))
            raise

        # Extract text content (skip thinking blocks)
        content_parts = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                content_parts.append(block.get("text", ""))

        content = "".join(content_parts)
        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            model=data.get("model", self._model),
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            },
        )

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[LLMStreamChunk]:
        """Generate a streaming response via Anthropic Messages API with SSE."""
        import time as _time
        _start = _time.monotonic()
        url = f"{self._base_url}/v1/messages"
        payload = self._build_payload(messages, stream=True, **kwargs)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream("POST", url, json=payload, headers=self._headers()) as response:
                    response.raise_for_status()
                    current_type = ""  # track current content block type
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if not data_str:
                            continue

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        event_type = data.get("type", "")

                        if event_type == "content_block_start":
                            block = data.get("content_block", {})
                            current_type = block.get("type", "")

                        elif event_type == "content_block_delta":
                            delta = data.get("delta", {})
                            # Only emit text deltas, skip thinking deltas
                            if current_type == "text" and delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    yield LLMStreamChunk(content=text, finish_reason=None)

                        elif event_type == "content_block_stop":
                            current_type = ""

                        elif event_type == "message_delta":
                            stop_reason = data.get("delta", {}).get("stop_reason")
                            if stop_reason:
                                yield LLMStreamChunk(content="", finish_reason=stop_reason)

                        elif event_type == "message_stop":
                            logger.info("llm_stream_complete", model=self._model,
                                        duration_ms=round((_time.monotonic() - _start) * 1000))
                            return
        except httpx.TimeoutException:
            logger.error("llm_stream_timeout", model=self._model, timeout=self._timeout,
                         duration_ms=round((_time.monotonic() - _start) * 1000))
            raise
        except httpx.HTTPStatusError as e:
            logger.error("llm_stream_http_error", model=self._model, status=e.response.status_code,
                         duration_ms=round((_time.monotonic() - _start) * 1000))
            raise
        except Exception as e:
            logger.error("llm_stream_error", model=self._model, error=str(e),
                         duration_ms=round((_time.monotonic() - _start) * 1000))
            raise
