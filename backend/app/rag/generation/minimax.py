"""MiniMax LLM client using Anthropic-compatible API.

MiniMax M2.7 exposes an OpenAI-compatible chat completions endpoint.
This client uses httpx to call it directly.
"""
from __future__ import annotations

from typing import Any, AsyncIterator

import httpx

from app.common.core.logging import get_logger
from app.rag.generation.base import BaseLLMClient, LLMMessage, LLMResponse, LLMStreamChunk

logger = get_logger(__name__)


class MiniMaxClient(BaseLLMClient):
    """LLM client for MiniMax M2.7 (OpenAI-compatible chat API).

    Args:
        base_url: API base URL (e.g. "https://api.minimax.chat/v1").
        api_key: API key for authentication.
        model: Model name (default "minimax-m2.7").
        temperature: Generation temperature (default 0.1).
        max_tokens: Maximum tokens to generate (default 2048).
        timeout: HTTP request timeout in seconds (default 60).
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "minimax-m2.7",
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
            "Authorization": f"Bearer {self._api_key}",
        }

    def _build_payload(self, messages: list[LLMMessage], stream: bool = False, **kwargs) -> dict[str, Any]:
        return {
            "model": kwargs.get("model", self._model),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", self._temperature),
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
            "stream": stream,
        }

    async def complete(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        """Generate a complete response via chat completions API."""
        url = f"{self._base_url}/chat/completions"
        payload = self._build_payload(messages, stream=False, **kwargs)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return LLMResponse(
            content=choice["message"]["content"],
            model=data.get("model", self._model),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        )

    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[LLMStreamChunk]:
        """Generate a streaming response via chat completions API with SSE."""
        url = f"{self._base_url}/chat/completions"
        payload = self._build_payload(messages, stream=True, **kwargs)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream("POST", url, json=payload, headers=self._headers()) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        return

                    import json
                    data = json.loads(data_str)
                    choice = data["choices"][0]
                    delta = choice.get("delta", {})
                    content = delta.get("content", "")
                    finish_reason = choice.get("finish_reason")

                    if content:
                        yield LLMStreamChunk(content=content, finish_reason=finish_reason)
                    elif finish_reason:
                        yield LLMStreamChunk(content="", finish_reason=finish_reason)
