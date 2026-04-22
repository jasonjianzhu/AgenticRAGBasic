"""Retrieval context extraction from queries.

Identifies structured metadata (product model, language, fault code,
document type) from user queries to use as search filters.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.common.core.logging import get_logger

logger = get_logger(__name__)

# Common product model patterns (e.g. ESS-5000, PCS-100, BMS-200)
_PRODUCT_MODEL_RE = re.compile(
    r"\b([A-Z]{2,5}[-\s]?\d{2,5}[A-Za-z]?)\b"
)

# Fault/alarm code patterns (e.g. E003, A001, F102, ERR-001)
_FAULT_CODE_RE = re.compile(
    r"([EAF]\d{3}|ERR[-\s]?\d{3})", re.IGNORECASE
)

# Chinese-heavy → zh, otherwise en
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# Document type keywords
_DOC_TYPE_KEYWORDS = {
    "manual": ["手册", "指南", "manual", "guide"],
    "faq": ["FAQ", "常见问题", "frequently"],
    "spec": ["规格", "参数", "specification", "datasheet"],
}


@dataclass
class RetrievalContext:
    """Structured context extracted from a query for search filtering."""

    product_model: str | None = None
    language: str | None = None
    fault_code: str | None = None
    document_type: str | None = None

    def to_filters(self) -> dict[str, str]:
        """Convert to a filter dict (non-None values only)."""
        filters = {}
        if self.product_model:
            filters["product_model"] = self.product_model
        if self.language:
            filters["language"] = self.language
        if self.document_type:
            filters["document_type"] = self.document_type
        return filters


class ContextExtractor:
    """Extract retrieval context from user queries using rules.

    Identifies:
    - Product model (e.g. ESS-5000)
    - Language (zh/en based on CJK character ratio)
    - Fault/alarm code (e.g. E003)
    - Document type (manual/faq/spec)
    """

    def extract(self, query: str) -> RetrievalContext:
        """Extract structured context from a query."""
        ctx = RetrievalContext(
            product_model=self._extract_product_model(query),
            language=self._detect_language(query),
            fault_code=self._extract_fault_code(query),
            document_type=self._extract_document_type(query),
        )
        logger.info(
            "context_extracted",
            product_model=ctx.product_model,
            language=ctx.language,
            fault_code=ctx.fault_code,
            document_type=ctx.document_type,
        )
        return ctx

    def merge(self, current: RetrievalContext, previous: RetrievalContext | None) -> RetrievalContext:
        """Merge current context with previous context (history inheritance).

        Current values take precedence; previous fills in gaps.
        """
        if previous is None:
            return current
        return RetrievalContext(
            product_model=current.product_model or previous.product_model,
            language=current.language or previous.language,
            fault_code=current.fault_code or previous.fault_code,
            document_type=current.document_type or previous.document_type,
        )

    def _extract_product_model(self, query: str) -> str | None:
        match = _PRODUCT_MODEL_RE.search(query)
        return match.group(1) if match else None

    def _detect_language(self, query: str) -> str | None:
        cjk_count = len(_CJK_RE.findall(query))
        total = len(query.strip())
        if total == 0:
            return None
        ratio = cjk_count / total
        return "zh" if ratio > 0.3 else "en"

    def _extract_fault_code(self, query: str) -> str | None:
        match = _FAULT_CODE_RE.search(query)
        return match.group(1).upper() if match else None

    def _extract_document_type(self, query: str) -> str | None:
        query_lower = query.lower()
        for doc_type, keywords in _DOC_TYPE_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in query_lower:
                    return doc_type
        return None
