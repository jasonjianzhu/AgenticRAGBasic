"""Rule-based document type classifier."""
from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)

# Document type constants
DOC_TYPE_MANUAL = "manual"
DOC_TYPE_FAQ = "faq"
DOC_TYPE_QA = "qa"
DOC_TYPE_SPEC = "spec"
DOC_TYPE_UNKNOWN = "unknown"

VALID_DOC_TYPES = {DOC_TYPE_MANUAL, DOC_TYPE_FAQ, DOC_TYPE_QA, DOC_TYPE_SPEC, DOC_TYPE_UNKNOWN}

# Keyword patterns for each document type (case-insensitive)
_MANUAL_KEYWORDS = [
    "操作手册",
    "维护手册",
    "安装指南",
    "使用说明",
    "用户手册",
    "操作指南",
    "维护指南",
    "user manual",
    "maintenance",
    "installation guide",
    "operation manual",
    "user guide",
]

_FAQ_KEYWORDS = [
    "FAQ",
    "常见问题",
    "Q&A",
    "frequently asked",
    "常见故障",
    "问答",
]

_QA_PATTERNS = [
    # Structured Q/A format patterns
    r"Q\s*[:：]\s*",
    r"A\s*[:：]\s*",
    r"问\s*[:：]\s*",
    r"答\s*[:：]\s*",
    r"问题\s*\d+",
    r"Question\s*\d+",
]

_SPEC_KEYWORDS = [
    "技术规格",
    "specification",
    "参数表",
    "技术参数",
    "性能参数",
    "technical specification",
    "datasheet",
    "data sheet",
    "规格书",
]


class RuleBasedClassifier:
    """Rule-based document type classifier.

    Classifies documents into: manual, faq, qa, spec, unknown.
    Supports human override via the document_type field.
    """

    def classify(
        self,
        content: str,
        filename: str = "",
        human_override: str | None = None,
    ) -> str:
        """Classify a document based on content and filename.

        Args:
            content: The document text content (or first N chars).
            filename: The original filename.
            human_override: If set and valid, this takes precedence.

        Returns:
            One of: "manual", "faq", "qa", "spec", "unknown".
        """
        # Human override takes precedence
        if human_override and human_override in VALID_DOC_TYPES:
            logger.info(
                "classification_human_override",
                doc_type=human_override,
            )
            return human_override

        # Combine content and filename for matching
        text = (content[:5000] + " " + filename).lower()

        # Check each type in priority order
        if self._match_keywords(text, _FAQ_KEYWORDS):
            doc_type = DOC_TYPE_FAQ
        elif self._match_qa_patterns(content[:5000]):
            doc_type = DOC_TYPE_QA
        elif self._match_keywords(text, _SPEC_KEYWORDS):
            doc_type = DOC_TYPE_SPEC
        elif self._match_keywords(text, _MANUAL_KEYWORDS):
            doc_type = DOC_TYPE_MANUAL
        else:
            doc_type = DOC_TYPE_UNKNOWN

        logger.info("classification_result", doc_type=doc_type)
        return doc_type

    def _match_keywords(self, text: str, keywords: list[str]) -> bool:
        """Check if any keyword appears in the text (case-insensitive)."""
        for keyword in keywords:
            if keyword.lower() in text:
                return True
        return False

    def _match_qa_patterns(self, text: str) -> bool:
        """Check if text has structured Q/A format patterns.

        Requires at least 2 Q/A pattern matches to classify as QA.
        """
        match_count = 0
        for pattern in _QA_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            match_count += len(matches)
            if match_count >= 2:
                return True
        return False
