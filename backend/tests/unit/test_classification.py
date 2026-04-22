"""Tests for rule-based document type classification."""
from __future__ import annotations

import pytest

from app.knowledge.rag.classification.rule_based import (
    DOC_TYPE_FAQ,
    DOC_TYPE_MANUAL,
    DOC_TYPE_QA,
    DOC_TYPE_SPEC,
    DOC_TYPE_UNKNOWN,
    RuleBasedClassifier,
)


@pytest.fixture
def classifier() -> RuleBasedClassifier:
    return RuleBasedClassifier()


class TestClassifierManual:
    """Test manual document type detection."""

    def test_chinese_manual_keyword(self, classifier):
        assert classifier.classify("这是一份操作手册") == DOC_TYPE_MANUAL

    def test_chinese_maintenance_manual(self, classifier):
        assert classifier.classify("维护手册第一章") == DOC_TYPE_MANUAL

    def test_chinese_installation_guide(self, classifier):
        assert classifier.classify("安装指南说明") == DOC_TYPE_MANUAL

    def test_english_user_manual(self, classifier):
        assert classifier.classify("This is a user manual for the product") == DOC_TYPE_MANUAL

    def test_english_maintenance(self, classifier):
        assert classifier.classify("Maintenance procedures for the system") == DOC_TYPE_MANUAL

    def test_filename_detection(self, classifier):
        result = classifier.classify("Some generic content", filename="操作手册.pdf")
        assert result == DOC_TYPE_MANUAL


class TestClassifierFAQ:
    """Test FAQ document type detection."""

    def test_faq_keyword(self, classifier):
        assert classifier.classify("FAQ: Common questions") == DOC_TYPE_FAQ

    def test_chinese_faq(self, classifier):
        assert classifier.classify("常见问题解答") == DOC_TYPE_FAQ

    def test_qa_keyword(self, classifier):
        assert classifier.classify("Q&A section for users") == DOC_TYPE_FAQ

    def test_frequently_asked(self, classifier):
        assert classifier.classify("Frequently asked questions about the product") == DOC_TYPE_FAQ

    def test_faq_takes_priority_over_manual(self, classifier):
        """FAQ should be detected even if manual keywords are also present."""
        content = "操作手册 FAQ 常见问题"
        assert classifier.classify(content) == DOC_TYPE_FAQ


class TestClassifierQA:
    """Test Q/A format detection."""

    def test_chinese_qa_format(self, classifier):
        content = "问：如何操作？\n答：按照以下步骤。\n问：还有其他方法吗？\n答：有的。"
        assert classifier.classify(content) == DOC_TYPE_QA

    def test_english_qa_format(self, classifier):
        content = "Q: How to start?\nA: Press the button.\nQ: How to stop?\nA: Press again."
        assert classifier.classify(content) == DOC_TYPE_QA

    def test_single_qa_not_enough(self, classifier):
        """A single Q/A pair should not trigger QA classification."""
        content = "Q: What is this?\nSome other text without answer format."
        # Only 1 match, needs >= 2
        result = classifier.classify(content)
        assert result != DOC_TYPE_QA


class TestClassifierSpec:
    """Test specification document type detection."""

    def test_chinese_spec(self, classifier):
        assert classifier.classify("技术规格说明书") == DOC_TYPE_SPEC

    def test_english_specification(self, classifier):
        assert classifier.classify("Product specification document") == DOC_TYPE_SPEC

    def test_chinese_parameter_table(self, classifier):
        assert classifier.classify("参数表如下所示") == DOC_TYPE_SPEC

    def test_datasheet(self, classifier):
        assert classifier.classify("Product datasheet v2.0") == DOC_TYPE_SPEC


class TestClassifierUnknown:
    """Test unknown/default classification."""

    def test_generic_content(self, classifier):
        assert classifier.classify("Some random text content") == DOC_TYPE_UNKNOWN

    def test_empty_content(self, classifier):
        assert classifier.classify("") == DOC_TYPE_UNKNOWN

    def test_numbers_only(self, classifier):
        assert classifier.classify("12345 67890") == DOC_TYPE_UNKNOWN


class TestClassifierHumanOverride:
    """Test human override behavior."""

    def test_override_takes_precedence(self, classifier):
        # Content would be classified as manual, but override says faq
        result = classifier.classify("操作手册", human_override="faq")
        assert result == DOC_TYPE_FAQ

    def test_override_with_valid_type(self, classifier):
        for doc_type in ["manual", "faq", "qa", "spec", "unknown"]:
            result = classifier.classify("anything", human_override=doc_type)
            assert result == doc_type

    def test_invalid_override_ignored(self, classifier):
        result = classifier.classify("操作手册", human_override="invalid_type")
        assert result == DOC_TYPE_MANUAL  # Falls back to content-based

    def test_none_override_ignored(self, classifier):
        result = classifier.classify("操作手册", human_override=None)
        assert result == DOC_TYPE_MANUAL

    def test_empty_override_ignored(self, classifier):
        result = classifier.classify("操作手册", human_override="")
        assert result == DOC_TYPE_MANUAL


class TestClassifierPriority:
    """Test classification priority order."""

    def test_faq_over_spec(self, classifier):
        content = "FAQ 技术规格"
        assert classifier.classify(content) == DOC_TYPE_FAQ

    def test_faq_over_manual(self, classifier):
        content = "常见问题 操作手册"
        assert classifier.classify(content) == DOC_TYPE_FAQ

    def test_spec_over_manual(self, classifier):
        content = "技术规格 操作手册"
        assert classifier.classify(content) == DOC_TYPE_SPEC
