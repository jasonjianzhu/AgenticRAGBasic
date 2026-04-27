"""Harness check functions — detect fabrication patterns in Agent answers.

Each check function takes the answer text and context (tool_outputs, etc.),
returns a HarnessResult indicating whether the answer passed or failed,
with details about what was detected.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.common.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class HarnessResult:
    """Result of a single harness check."""

    check_name: str
    passed: bool
    details: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Number patterns
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(
    r'-?\d+(?:\.\d+)?'
    r'(?:%|(?:\s*(?:kW|kWh|MW|MWh|V|A|Ah|°C|℃|Hz|Ω|W|h|台|个|次|条)))?'
)

# Speculative / predictive language patterns
_SPECULATION_PATTERNS = [
    r'预计[^，。]*(?:将|会|可能)',
    r'预测[^，。]*(?:将|会|可能)',
    r'趋势表明',
    r'(?:可能|大概|估计)(?:将|会)[^，。]*(?:达到|超过|下降|上升)',
    r'(?:未来|下周|下月|明天)[^，。]*(?:将|会|可能)',
    r'按此趋势',
    r'如果.*(?:继续|持续).*(?:将|会)',
]
_SPECULATION_RE = re.compile('|'.join(_SPECULATION_PATTERNS))


def check_no_tool_fabrication(
    answer: str,
    tool_outputs: list[str],
) -> HarnessResult:
    """Check 1: Agent answered with numbers but never called any tool.

    Detects when Agent fabricates data without querying any data source.
    """
    if tool_outputs:
        return HarnessResult(check_name="no_tool_fabrication", passed=True)

    numbers = _NUMBER_RE.findall(answer)
    # Filter out trivially small numbers
    significant = []
    for num in numbers:
        match = re.match(r'-?\d+(?:\.\d+)?', num)
        if match:
            try:
                if abs(float(match.group())) >= 10:
                    significant.append(num.strip())
            except ValueError:
                continue

    if not significant:
        return HarnessResult(check_name="no_tool_fabrication", passed=True)

    logger.warning("harness_no_tool_fabrication",
                    numbers=significant)
    return HarnessResult(
        check_name="no_tool_fabrication",
        passed=False,
        details={"fabricated_numbers": significant},
    )


def check_unverified_numbers(
    answer: str,
    tool_outputs: list[str],
) -> HarnessResult:
    """Check 2: Numbers in answer that cannot be traced to tool outputs.

    Detects when Agent computes/converts data incorrectly.
    """
    if not tool_outputs:
        return HarnessResult(check_name="unverified_numbers", passed=True)

    answer_numbers = _NUMBER_RE.findall(answer)
    if not answer_numbers:
        return HarnessResult(check_name="unverified_numbers", passed=True)

    combined_outputs = "\n".join(tool_outputs)

    unverified = []
    for num in answer_numbers:
        num_value = re.match(r'-?\d+(?:\.\d+)?', num)
        if not num_value:
            continue
        value = num_value.group()
        try:
            if abs(float(value)) < 10:
                continue
        except ValueError:
            continue
        if value not in combined_outputs:
            unverified.append(num.strip())

    unverified = list(set(unverified))
    if not unverified:
        return HarnessResult(check_name="unverified_numbers", passed=True)

    logger.warning("harness_unverified_numbers",
                    numbers=unverified,
                    tool_output_count=len(tool_outputs))
    return HarnessResult(
        check_name="unverified_numbers",
        passed=False,
        details={"unverified_numbers": unverified},
    )


def check_speculation(
    answer: str,
    tool_outputs: list[str],
) -> HarnessResult:
    """Check 4: Speculative or predictive statements not supported by data.

    Detects when Agent makes predictions or extrapolations beyond the data.
    """
    matches = _SPECULATION_RE.findall(answer)
    if not matches:
        return HarnessResult(check_name="speculation", passed=True)

    # Deduplicate
    unique_matches = list(set(matches))
    logger.warning("harness_speculation_detected", patterns=unique_matches)
    return HarnessResult(
        check_name="speculation",
        passed=False,
        details={"speculative_phrases": unique_matches},
    )


def run_all_checks(
    answer: str,
    tool_outputs: list[str],
) -> list[HarnessResult]:
    """Run all harness checks and return results."""
    return [
        check_no_tool_fabrication(answer, tool_outputs),
        check_unverified_numbers(answer, tool_outputs),
        check_speculation(answer, tool_outputs),
    ]
