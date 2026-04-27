"""Harness check — LLM-based verification of Agent answers.

Uses a single LLM call to verify that the Agent's answer is grounded
in tool outputs. No regex, no thresholds, no pattern matching.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.common.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class HarnessResult:
    """Result of harness verification."""

    passed: bool
    reason: str = ""
    details: dict = field(default_factory=dict)


VERIFY_SYSTEM_PROMPT = """\
你是一个回答质量审核员。你的任务是检查AI助手的回答是否严格基于提供的数据源。

审核规则：
1. 回答中的所有数值（数量、金额、百分比、电压、电流等）必须能在数据源中找到对应
2. 不允许自行计算、换算或推测数值（如把kWh换算成MWh）
3. 不允许做预测性推断（如"预计下周会..."）
4. 如果数据源为空，回答中不应包含任何具体数值

请以JSON格式回复，不要输出其他内容：
{"passed": true} 或 {"passed": false, "reason": "具体问题描述"}"""

VERIFY_USER_TEMPLATE = """\
数据源：
{tool_data}

AI助手的回答：
{answer}"""


async def verify_answer(
    answer: str,
    tool_outputs: list[str],
    llm_client: Any,
) -> HarnessResult:
    """Verify answer groundedness using a single LLM call.

    Args:
        answer: The Agent's answer text.
        tool_outputs: Raw text outputs from all tool calls in this turn.
        llm_client: BaseLLMClient instance for verification.

    Returns:
        HarnessResult with passed/failed and reason.
    """
    tool_data = "\n---\n".join(tool_outputs) if tool_outputs else "（无数据源，未调用任何查询工具）"

    from app.rag.generation.base import LLMMessage
    messages = [
        LLMMessage(role="system", content=VERIFY_SYSTEM_PROMPT),
        LLMMessage(role="user", content=VERIFY_USER_TEMPLATE.format(
            tool_data=tool_data,
            answer=answer,
        )),
    ]

    try:
        response = await llm_client.complete(messages, temperature=0.0, max_tokens=256)
        content = response.content.strip()

        # Parse JSON response
        # Handle cases where LLM wraps in markdown code block
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        result = json.loads(content)
        passed = result.get("passed", True)
        reason = result.get("reason", "")

        if not passed:
            logger.warning("harness_verify_failed", reason=reason)
        else:
            logger.info("harness_verify_passed")

        return HarnessResult(passed=passed, reason=reason)

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("harness_verify_parse_error", error=str(e), raw=content[:200])
        # Parse error — let the answer through (don't block on harness failure)
        return HarnessResult(passed=True, reason="verification parse error")
    except Exception as e:
        logger.warning("harness_verify_error", error=str(e))
        # LLM call failed — let the answer through
        return HarnessResult(passed=True, reason="verification call error")
