"""Harness check — lightweight, deterministic verification.

Only one hard constraint: Agent must call a tool before outputting data.
All other quality controls are handled by prompt engineering.
No LLM calls, no regex thresholds, no pattern matching.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.common.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class HarnessResult:
    """Result of harness verification."""

    passed: bool
    reason: str = ""


def check_tool_grounding(
    has_tool_calls: bool,
    has_numeric_sql: bool,
) -> HarnessResult:
    """Check that Agent called at least one tool before answering.

    This is the only hard constraint. If the user asked a data question
    and Agent answered without calling any tool, the answer is ungrounded.

    Args:
        has_tool_calls: Whether any tool (rag_search or sql_query) was called.
        has_numeric_sql: Whether sql_query returned numeric data.

    Returns:
        HarnessResult — passed if tools were called, failed if not.
    """
    if has_tool_calls:
        return HarnessResult(passed=True)

    logger.warning("harness_no_tool_called")
    return HarnessResult(
        passed=False,
        reason="Agent answered without calling any tool",
    )
