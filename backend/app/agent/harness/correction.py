"""Harness correction — fix fabricated or speculative answers.

When harness checks detect issues, this module attempts to correct
the answer by re-running the LLM with stricter constraints, or
falls back to showing raw tool data.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import UsageLimits

from app.common.core.logging import get_logger
from app.agent.harness.checks import HarnessResult

logger = get_logger(__name__)


def _clean_think_tags(text: str) -> str:
    cleaned = re.sub(r"<think>[\\s\\S]*?</think>", "", text).strip()
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>[\\s\\S]*", "", cleaned).strip()
    return cleaned


async def correct_answer(
    answer: str,
    failed_checks: list[HarnessResult],
    tool_outputs: list[str],
    agent: Agent,
    deps: Any,
    message_history: list[ModelMessage],
    max_tokens: int = 8192,
) -> str:
    """Attempt to correct a fabricated/speculative answer.

    Strategy:
    1. Build a correction prompt describing what went wrong
    2. Re-run LLM with temperature=0, tool_calls_limit=0
    3. If correction succeeds, return corrected answer
    4. If correction fails, return raw tool data
    """
    # Build correction prompt from failed checks
    issues = []
    for check in failed_checks:
        if check.check_name == "no_tool_fabrication":
            nums = check.details.get("fabricated_numbers", [])
            issues.append(
                f"你没有调用任何查询工具就给出了数值 {', '.join(nums)}，这些数据没有来源。"
            )
        elif check.check_name == "unverified_numbers":
            nums = check.details.get("unverified_numbers", [])
            issues.append(
                f"以下数值在数据源中找不到对应：{', '.join(nums)}。"
                f"不要自行计算或换算，直接使用原始数据。"
            )
        elif check.check_name == "speculation":
            phrases = check.details.get("speculative_phrases", [])
            issues.append(
                f"回答中包含推测性表述：{'、'.join(phrases)}。"
                f"只陈述数据事实，不要做预测或推断。"
            )

    raw_data = "\n---\n".join(tool_outputs[-3:]) if tool_outputs else "（无工具返回数据）"

    correction_prompt = (
        "你之前的回答存在以下问题：\n"
        + "\n".join(f"- {issue}" for issue in issues)
        + f"\n\n以下是工具返回的原始数据：\n\n{raw_data}"
        + "\n\n请严格基于以上原始数据重新回答，不要自行计算、换算或推测。"
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
            logger.info("harness_correction_applied",
                        issues=[c.check_name for c in failed_checks],
                        original_len=len(answer),
                        corrected_len=len(corrected))
            return corrected
    except Exception as e:
        logger.warning("harness_correction_failed", error=str(e))

    # Correction failed — fall back to raw data
    if tool_outputs:
        raw_data_display = "\n\n---\n\n".join(tool_outputs[-3:])
        logger.warning("harness_fallback_to_raw_data",
                        issues=[c.check_name for c in failed_checks])
        return f"以下是查询到的原始数据，供您参考：\n\n{raw_data_display}"

    # No tool outputs at all — return a safe message
    return "抱歉，暂时无法获取相关数据，请尝试重新提问。"
