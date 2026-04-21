"""Token counting and text utilities for chunking."""
from __future__ import annotations

import re
import unicodedata


def _is_cjk(char: str) -> bool:
    """Check if a character is a CJK ideograph."""
    try:
        name = unicodedata.name(char, "")
    except ValueError:
        return False
    return "CJK" in name


def estimate_tokens(text: str) -> int:
    """Estimate token count for mixed Chinese/English text.

    Heuristic:
    - Chinese characters: ~1.5 chars per token
    - English / other text: ~4 chars per token (approximated by word count)

    Args:
        text: Input text (may contain mixed languages).

    Returns:
        Estimated token count (minimum 0).
    """
    if not text:
        return 0

    cjk_count = 0
    non_cjk_chars: list[str] = []

    for ch in text:
        if _is_cjk(ch):
            cjk_count += 1
        else:
            non_cjk_chars.append(ch)

    # CJK tokens: ~1.5 chars per token
    cjk_tokens = cjk_count / 1.5

    # English / other tokens: count whitespace-separated words
    non_cjk_text = "".join(non_cjk_chars).strip()
    if non_cjk_text:
        english_tokens = len(non_cjk_text.split())
    else:
        english_tokens = 0

    return max(0, round(cjk_tokens + english_tokens))
