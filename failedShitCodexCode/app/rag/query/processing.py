from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.rag.query.context import RetrievalContext, merge_retrieval_context
from app.rag.query.rewrite import QueryRewriteResult, SimpleQueryRewriter


@dataclass(frozen=True)
class QueryProcessingResult:
    original_query: str
    normalized_query: str
    rewrite: QueryRewriteResult
    context: RetrievalContext
    retrieval_queries: list[str] = field(default_factory=list)


class QueryProcessor:
    def __init__(
        self,
        llm_client=None,
        fallback_rewriter: SimpleQueryRewriter | None = None,
        query_limit: int = 5,
        history_limit: int = 3,
    ):
        self.llm_client = llm_client
        self.fallback_rewriter = fallback_rewriter or SimpleQueryRewriter()
        self.query_limit = query_limit
        self.history_limit = history_limit

    def process(
        self,
        query: str,
        language: str | None = None,
        knowledge_base_id: str | None = None,
        previous_contexts: list[RetrievalContext] | None = None,
    ) -> QueryProcessingResult:
        normalized_query = normalize_query(query)
        fallback = self.fallback_rewriter.rewrite(normalized_query)
        rewrite = fallback
        if self.llm_client is not None:
            llm_rewrite = self.llm_client.rewrite_query(normalized_query)
            rewrite = QueryRewriteResult(
                original_query=query,
                rewritten_query=llm_rewrite.rewritten_query or fallback.rewritten_query,
                expanded_queries=_merge_queries(fallback.expanded_queries, llm_rewrite.expanded_queries, limit=self.query_limit),
                knowledge_base_id=llm_rewrite.knowledge_base_id or fallback.knowledge_base_id,
                language=llm_rewrite.language or fallback.language,
                fault_code=llm_rewrite.fault_code or fallback.fault_code,
                product_model=llm_rewrite.product_model or fallback.product_model,
                document_type=llm_rewrite.document_type or fallback.document_type,
            )

        history_context = _merge_history_context(previous_contexts or [], limit=self.history_limit)
        merged_context = merge_retrieval_context(
            history_context,
            RetrievalContext(
                knowledge_base_id=knowledge_base_id or rewrite.knowledge_base_id,
                language=language or rewrite.language,
                document_type=rewrite.document_type,
                product_model=rewrite.product_model,
                fault_code=rewrite.fault_code,
            ),
        )
        retrieval_queries = _merge_queries(
            [normalized_query, rewrite.rewritten_query],
            rewrite.expanded_queries,
            limit=self.query_limit,
        )
        return QueryProcessingResult(
            original_query=query,
            normalized_query=normalized_query,
            rewrite=rewrite,
            context=merged_context,
            retrieval_queries=retrieval_queries,
        )


def normalize_query(query: str) -> str:
    normalized = " ".join(query.strip().split())
    normalized = normalized.replace("？", "?").replace("，", ",").replace("：", ":")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def pack_context_blocks(chunks: list[dict], max_items: int, max_chars: int) -> list[str]:
    packed: list[str] = []
    total_chars = 0
    for chunk in chunks[:max_items]:
        source = chunk.get("source_filename") or chunk.get("metadata", {}).get("source_filename") or "unknown"
        section = chunk.get("section_path") or "Unsectioned"
        page = chunk.get("page_start") or "-"
        block = f"[source={source} section={section} page={page}]\n{chunk['content']}".strip()
        if packed and total_chars + len(block) > max_chars:
            break
        packed.append(block)
        total_chars += len(block)
    return packed


def _merge_queries(primary: list[str], secondary: list[str], limit: int = 5) -> list[str]:
    merged: list[str] = []
    for item in [*primary, *secondary]:
        normalized = item.strip()
        if normalized and normalized not in merged:
            merged.append(normalized)
        if len(merged) >= limit:
            break
    return merged


def _merge_history_context(contexts: list[RetrievalContext], limit: int) -> RetrievalContext:
    merged = RetrievalContext()
    for context in contexts[-limit:]:
        merged = merge_retrieval_context(merged, context)
    return merged
