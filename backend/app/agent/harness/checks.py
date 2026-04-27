"""Harness check — lightweight, deterministic verification.

Design principle: harness should never interfere with normal conversation.
It only acts when there is clear evidence of fabrication — Agent called
sql_query, got data back, but the answer contains values not in the data.

For all other quality concerns (knowledge QA accuracy, speculation, etc.),
we rely on prompt engineering + evaluation framework.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.common.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class HarnessResult:
    """Result of harness verification."""

    passed: bool
    reason: str = ""
