from __future__ import annotations

from app.rag.query.context import RetrievalContext, merge_retrieval_context
from app.rag.query.processing import QueryProcessor, normalize_query, pack_context_blocks
from app.rag.query.rewrite import QueryRewriteResult, SimpleQueryRewriter


def test_simple_query_rewriter_extracts_filters_and_expansions() -> None:
    rewriter = SimpleQueryRewriter()

    result = rewriter.rewrite("请问 E101 告警怎么处理，英文手册里怎么说？")

    assert isinstance(result, QueryRewriteResult)
    assert "E101" in result.rewritten_query
    assert result.language == "en"
    assert "E101 troubleshooting" in result.expanded_queries


def test_merge_retrieval_context_prefers_latest_non_empty_values() -> None:
    previous = RetrievalContext(language="en", document_type="manual", product_model="M123")
    current = RetrievalContext(language=None, document_type="faq", product_model=None, fault_code="E101")

    merged = merge_retrieval_context(previous, current)

    assert merged.language == "en"
    assert merged.document_type == "faq"
    assert merged.product_model == "M123"
    assert merged.fault_code == "E101"


def test_query_processor_merges_normalization_rewrite_and_context() -> None:
    class FakeLLM:
        def rewrite_query(self, query: str):
            return QueryRewriteResult(
                original_query=query,
                rewritten_query="E101 troubleshooting",
                expanded_queries=["battery overheat alarm"],
                language="en",
                document_type="manual",
            )

    processor = QueryProcessor(llm_client=FakeLLM(), query_limit=4)

    result = processor.process("  请问   E101  告警怎么处理？ ", language="zh")

    assert result.normalized_query == "请问 E101 告警怎么处理?"
    assert result.rewrite.rewritten_query == "E101 troubleshooting"
    assert result.context.language == "zh"
    assert result.context.document_type == "manual"
    assert len(result.retrieval_queries) <= 4


def test_pack_context_blocks_limits_item_count_and_chars() -> None:
    blocks = pack_context_blocks(
        [
            {"content": "A" * 20, "section_path": "S1", "page_start": 1, "metadata": {"source_filename": "a.pdf"}},
            {"content": "B" * 80, "section_path": "S2", "page_start": 2, "metadata": {"source_filename": "b.pdf"}},
        ],
        max_items=2,
        max_chars=100,
    )

    assert len(blocks) == 1
    assert "source=a.pdf" in blocks[0]


def test_normalize_query_condenses_whitespace_and_punctuation() -> None:
    assert normalize_query("  E101   告警  怎么处理？ ") == "E101 告警 怎么处理?"
