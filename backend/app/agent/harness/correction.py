"""Harness correction — re-generate answer when verification fails.

Strategy:
1. Give LLM the raw tool data and ask it to answer directly
2. Verify the corrected answer
3. If still fails, fall back to raw data display
"""
from __future__ import annotations

import re
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import UsageLimits

from app.common.core.logging import get_logger
from app.agent.harness.checks import HarnessResult, verify_answer

logger = get_logger(__name__)


def _clean_think_tags(text: str) -> str:
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>[\s\S]*", "", cleaned).strip()
    return cleaned


async def correct_answer(
    answer: str,
    verification: HarnessResult,
    tool_outputs: list[str],
    agent: Agent,
    deps: Any,
    message_history: list[ModelMessage],
    llm_client: Any,
    max_tokens: int = 8192,
) -> str:
    """Attempt to correct a failed answer.

    1. Re-run LLM with raw data only, no mention of previous errors
    2. Verify the corrected answer
    3. If still fails, show raw data
    """
    raw_data = "\n---\n".join(tool_outputs) if tool_outputs else ""

    if not raw_data:
        return "抱歉，暂时无法获取相关数据，请尝试重新提问。"

    correction_prompt = (
        "请基于以下数据回答用户的问题。"
        "直接给出答案，只使用数据中的原始数值，"
        "不要自行计算、换算或推测。\n\n"
        f"数据：\n{raw_data}"
    )

    try:
        result = await agent.run(
            correction_prompt,
            deps=deps,
            message_history=message_history,
            model_settings={"temperature": 0.0, "max_tokens": max_tokens},
            usage_limits=UsageLimits(tool_calls_limit=0),
        )
        corrected = _clean_think_tags(result.response.text or "")

        if corrected:
            # Verify the corrected answer
            recheck = await verify_answer(corrected, tool_outputs, llm_client)
            if recheck.passed:
                logger.info("harness_correction_applied",
                            original_len=len(answer),
                            corrected_len=len(corrected))
                return corrected
            else:
                logger.warning("harness_correction_still_failed",
                               reason=recheck.reason)
    except Exception as e:
        logger.warning("harness_correction_error", error=str(e))

    # All correction attempts failed — show raw data
    logger.warning("harness_fallback_to_raw_data")
    raw_display = "\n\n---\n\n".join(tool_outputs)
    return f"以下是查询到的原始数据，供您参考：\n\n{raw_display}"
