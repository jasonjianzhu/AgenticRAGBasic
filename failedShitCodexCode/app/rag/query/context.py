from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalContext:
    knowledge_base_id: str | None = None
    language: str | None = None
    document_type: str | None = None
    product_model: str | None = None
    fault_code: str | None = None


def merge_retrieval_context(previous: RetrievalContext, current: RetrievalContext) -> RetrievalContext:
    return RetrievalContext(
        knowledge_base_id=current.knowledge_base_id or previous.knowledge_base_id,
        language=current.language or previous.language,
        document_type=current.document_type or previous.document_type,
        product_model=current.product_model or previous.product_model,
        fault_code=current.fault_code or previous.fault_code,
    )
