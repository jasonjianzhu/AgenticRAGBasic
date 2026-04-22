"""Abstract base class for LLM clients."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class LLMMessage:
    """A single message in a conversation."""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    """Response from a non-streaming LLM call."""

    content: str
    model: str = ""
    usage: dict = field(default_factory=dict)  # prompt_tokens, completion_tokens, total_tokens


@dataclass
class LLMStreamChunk:
    """A single chunk from a streaming LLM call."""

    content: str  # delta text
    finish_reason: str | None = None  # None, "stop", "length"


class BaseLLMClient(abc.ABC):
    """Abstract base class for LLM clients.

    Implementations must support both synchronous (complete) and
    streaming (stream) generation modes.
    """

    @abc.abstractmethod
    async def complete(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        """Generate a complete response from the LLM.

        Args:
            messages: Conversation messages (system + user + assistant history).
            **kwargs: Additional parameters (temperature, max_tokens, etc.).

        Returns:
            LLMResponse with the full generated text.
        """

    @abc.abstractmethod
    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[LLMStreamChunk]:
        """Generate a streaming response from the LLM.

        Args:
            messages: Conversation messages.
            **kwargs: Additional parameters.

        Yields:
            LLMStreamChunk with delta text for each token.
        """

    @property
    @abc.abstractmethod
    def model_name(self) -> str:
        """Return the model identifier."""
