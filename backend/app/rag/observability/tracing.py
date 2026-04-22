"""Langfuse tracing integration for RAG pipeline.

Provides a thin wrapper around the Langfuse SDK. When Langfuse is not
configured (no host/keys), all operations are no-ops.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

from app.common.core.config import get_settings
from app.common.core.logging import get_logger

logger = get_logger(__name__)

_langfuse_client = None
_initialized = False


def _get_langfuse():
    """Lazily initialize the Langfuse client singleton."""
    global _langfuse_client, _initialized

    if _initialized:
        return _langfuse_client

    _initialized = True
    settings = get_settings()

    if not settings.langfuse_host or not settings.langfuse_public_key:
        logger.info("langfuse_disabled", reason="no host or public key configured")
        return None

    try:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            host=settings.langfuse_host,
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
        )
        logger.info("langfuse_initialized", host=settings.langfuse_host)
    except Exception as e:
        logger.warning("langfuse_init_failed", error=str(e))
        _langfuse_client = None

    return _langfuse_client


class RAGTrace:
    """Trace a single RAG request through the pipeline.

    Usage::

        trace = RAGTrace(query="电池过温告警")
        trace.span_start("rewrite")
        # ... do rewrite ...
        trace.span_end("rewrite", output={"rewritten": "..."})
        trace.span_start("search")
        # ... do search ...
        trace.span_end("search", output={"hits": 15})
        trace.generation(model="minimax-m2.7", input=messages, output=answer)
        trace.finish()

    When Langfuse is not configured, all methods are no-ops.
    """

    def __init__(self, query: str, user_id: str | None = None, metadata: dict | None = None) -> None:
        self._query = query
        self._trace = None
        self._spans: dict[str, Any] = {}

        client = _get_langfuse()
        if client is not None:
            try:
                self._trace = client.trace(
                    name="rag-pipeline",
                    input={"query": query},
                    user_id=user_id,
                    metadata=metadata or {},
                )
            except Exception as e:
                logger.debug("langfuse_trace_create_failed", error=str(e))

    def span_start(self, name: str, input: dict | None = None) -> None:
        """Start a named span (e.g. 'rewrite', 'search', 'rerank', 'generate')."""
        if self._trace is None:
            return
        try:
            span = self._trace.span(name=name, input=input or {})
            self._spans[name] = span
        except Exception as e:
            logger.debug("langfuse_span_start_failed", name=name, error=str(e))

    def span_end(self, name: str, output: dict | None = None) -> None:
        """End a named span with output data."""
        span = self._spans.pop(name, None)
        if span is None:
            return
        try:
            span.end(output=output or {})
        except Exception as e:
            logger.debug("langfuse_span_end_failed", name=name, error=str(e))

    def generation(
        self,
        model: str,
        input: Any = None,
        output: str = "",
        usage: dict | None = None,
    ) -> None:
        """Record an LLM generation event."""
        if self._trace is None:
            return
        try:
            self._trace.generation(
                name="answer-generation",
                model=model,
                input=input,
                output=output,
                usage=usage or {},
            )
        except Exception as e:
            logger.debug("langfuse_generation_failed", error=str(e))

    def finish(self, output: dict | None = None) -> None:
        """Finish the trace."""
        if self._trace is None:
            return
        try:
            self._trace.update(output=output or {})
        except Exception as e:
            logger.debug("langfuse_trace_finish_failed", error=str(e))


def flush() -> None:
    """Flush pending Langfuse events (call on shutdown)."""
    client = _get_langfuse()
    if client is not None:
        try:
            client.flush()
        except Exception:
            pass
