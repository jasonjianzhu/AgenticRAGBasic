"""Harness correction — force tool usage when Agent skipped tools.

When the harness detects that Agent answered without calling any tool,
this module forces a re-run that requires tool usage.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import UsageLimits

from app.common.core.logging import get_logger

logger = get_logger(__name__)


def _clean_think_tags(text: str) -> str:
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>[\s\S]*", "", cleaned).strip()
    return cleaned


async def force_tool_rerun(
    original_message: str,
    agent: Agent,
    deps: Any,
    message_history: list[ModelMessage],
    max_tokens: int = 8192,
) -> str | None:
    """Re-run Agent with explicit instruction to use tools.

    Returns corrected answer text, or None if re-run also fails.
    """
    rerun_prompt = (
        f"用户问题：{original_message}\n\n"
        "你必须先调用工具（rag_search 或 sql_query）获取数据，"
        "然后基于工具返回的数据回答。不要凭记忆回答。"
    )

    try:
        result = await agent.run(
            rerun_prompt,
            deps=deps,
            message_history=message_history,
            model_settings={"temperature": 0.0, "max_tokens": max_tokens},
            usage_limits=UsageLimits(tool_calls_limit=4),
        )
        corrected = _clean_think_tags(result.response.text or "")

        # Check if tools were actually called this time
        if deps.tool_outputs or deps.has_numeric_sql:
            logger.info("harness_rerun_with_tools",
                        text_len=len(corrected))
            return corrected
        else:
            logger.warning("harness_rerun_still_no_tools")
            return None
    except Exception as e:
        logger.warning("harness_rerun_failed", error=str(e))
        return None
