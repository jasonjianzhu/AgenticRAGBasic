"""Tests for token estimation utilities."""
from __future__ import annotations

import pytest

from app.knowledge.rag.chunking.utils import estimate_tokens


class TestEstimateTokens:
    """Tests for the estimate_tokens function."""

    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_single_english_word(self):
        result = estimate_tokens("hello")
        assert result >= 1

    def test_english_sentence(self):
        text = "The quick brown fox jumps over the lazy dog"
        result = estimate_tokens(text)
        # 9 words -> ~9 tokens
        assert 7 <= result <= 12

    def test_chinese_text(self):
        text = "电池过温告警处理方法"
        result = estimate_tokens(text)
        # 9 CJK chars / 1.5 = 6 tokens
        assert 4 <= result <= 8

    def test_mixed_chinese_english(self):
        text = "电池温度超过 threshold 时触发告警"
        result = estimate_tokens(text)
        # CJK chars + English words
        assert result >= 3

    def test_whitespace_only(self):
        result = estimate_tokens("   \n\t  ")
        assert result == 0

    def test_long_english_text(self):
        words = ["word"] * 100
        text = " ".join(words)
        result = estimate_tokens(text)
        # ~100 words -> ~100 tokens
        assert 80 <= result <= 120

    def test_long_chinese_text(self):
        text = "中" * 150
        result = estimate_tokens(text)
        # 150 CJK chars / 1.5 = 100 tokens
        assert 80 <= result <= 120

    def test_numbers_and_punctuation(self):
        text = "Version 3.14.159 released on 2024-01-15!"
        result = estimate_tokens(text)
        assert result >= 3

    def test_returns_non_negative(self):
        assert estimate_tokens("") >= 0
        assert estimate_tokens("a") >= 0
        assert estimate_tokens("中") >= 0
