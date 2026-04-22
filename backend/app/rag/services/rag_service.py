"""RAG service — orchestrates the full search → rerank → generate pipeline.

This is the core service for Phase 2 RAG Q&A.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.config import Settings, get_settings
from app.common.core.logging import get_logger
from app.common.db.models import Chunk, Document
from app.common.rag.embedding.base import EmbeddingProvider
from app.common.rag.vector_store.base import SearchResult, VectorStore
from app.rag.generation.base import BaseLLMClient, LLMMessage, LLMStreamChunk
from app.rag.query.context_extractor import ContextExtractor, RetrievalContext
from app.rag.query.normalizer import QueryNormalizer
from app.rag.query.rewriter import QueryRewriter, RewriteResult
from app.rag.reranking.base import BaseReranker

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SearchResultItem:
    """A single enriched search result."""

    chunk_id: str
    document_id: str
    document_title: str
    content: str
    score: float
    rerank_score: float | None = None
    chunk_type: str = "text"
    page_start: int | None = None
    page_end: int | None = None
    section_path: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchTrace:
    """Trace information for a search operation."""

    query_normalized: str
    query_rewritten: str | None = None
    retrieval_context: dict = field(default_factory=dict)
    dense_hits: int = 0
    sparse_hits: int = 0
    fused_total: int = 0
    reranked: bool = False
    returned: int = 0
    latency_ms: dict = field(default_factory=dict)


@dataclass
class RAGSearchResult:
    """Complete search result with trace."""

    query: str
    rewritten_query: str | None
    results: list[SearchResultItem]
    trace: SearchTrace


@dataclass
class Citation:
    """A citation reference for an answer."""

    index: int
    document_title: str
    page: int | None
    chunk_id: str
    snippet: str


# ---------------------------------------------------------------------------
# RRF fusion (reused from search_debug, but standalone here)
# ---------------------------------------------------------------------------

def _rrf_fusion(
    dense_results: list[SearchResult],
    sparse_results: list[SearchResult],
    k: int = 60,
) -> list[tuple[str, float, dict]]:
    """RRF fusion returning (point_id, score, payload) tuples sorted desc."""
    scores: dict[str, float] = {}
    payloads: dict[str, dict] = {}

    for rank, r in enumerate(dense_results, start=1):
        scores[r.id] = scores.get(r.id, 0.0) + 1.0 / (k + rank)
        payloads[r.id] = r.payload

    for rank, r in enumerate(sparse_results, start=1):
        scores[r.id] = scores.get(r.id, 0.0) + 1.0 / (k + rank)
        if r.id not in payloads:
            payloads[r.id] = r.payload

    fused = [(pid, score, payloads.get(pid, {})) for pid, score in scores.items()]
    fused.sort(key=lambda x: x[1], reverse=True)
    return fused


# ---------------------------------------------------------------------------
# RAG Service
# ---------------------------------------------------------------------------

class RAGService:
    """Orchestrates the RAG pipeline: query → search → rerank → generate.

    Args:
        embedding_provider: For query embedding.
        vector_store: For similarity search.
        session: Async DB session for metadata enrichment.
        llm_client: For query rewrite and answer generation.
        reranker: Optional reranker (None = skip reranking).
        settings: Application settings.
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        session: AsyncSession,
        llm_client: BaseLLMClient,
        reranker: BaseReranker | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._embedding = embedding_provider
        self._vector_store = vector_store
        self._session = session
        self._llm = llm_client
        self._reranker = reranker
        self._settings = settings or get_settings()
        self._normalizer = QueryNormalizer()
        self._rewriter = QueryRewriter(llm_client)
        self._context_extractor = ContextExtractor()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        kb_ids: list[uuid.UUID],
        top_k: int | None = None,
        filters: dict | None = None,
        enable_rewrite: bool | None = None,
        previous_context: RetrievalContext | None = None,
    ) -> RAGSearchResult:
        """Execute the full search pipeline.

        Steps:
        1. Normalize query
        2. Extract retrieval context
        3. Optionally rewrite query
        4. Embed query (dense + sparse)
        5. Search each KB (dense + sparse + RRF)
        6. Optionally rerank
        7. Enrich with DB metadata
        """
        top_k = top_k or self._settings.rag_search_top_k
        enable_rewrite = enable_rewrite if enable_rewrite is not None else self._settings.rag_rewrite_enabled
        timings: dict[str, float] = {}

        # 1. Normalize
        normalized = self._normalizer.normalize(query)

        # 2. Extract context
        ctx = self._context_extractor.extract(normalized)
        ctx = self._context_extractor.merge(ctx, previous_context)

        # 3. Rewrite
        rewritten_query = normalized
        t0 = time.monotonic()
        rewrite_result: RewriteResult | None = None
        if enable_rewrite:
            try:
                rewrite_result = await self._rewriter.rewrite(normalized)
                rewritten_query = rewrite_result.rewritten_query
            except Exception as e:
                logger.warning("rewrite_failed_using_original", error=str(e))
        timings["rewrite"] = round((time.monotonic() - t0) * 1000)

        # 4. Embed
        query_embedding = await self._embedding.embed_query(rewritten_query)

        # 5. Search across all KBs
        t0 = time.monotonic()
        all_dense: list[SearchResult] = []
        all_sparse: list[SearchResult] = []

        # Build filters — only use explicitly provided filters
        # Context-derived filters are stored in trace for reference but not applied
        # to avoid filtering out results when chunk metadata is incomplete
        payload_filters = {}
        if filters:
            payload_filters.update({k: v for k, v in filters.items() if v is not None})

        candidate_limit = self._settings.reranker_top_n if self._reranker else top_k * 2

        for kb_id in kb_ids:
            kb_filters = {"kb_id": str(kb_id), **payload_filters}

            dense = await self._vector_store.search_dense(
                vector=query_embedding.dense,
                limit=candidate_limit,
                filters=kb_filters,
            )
            sparse = await self._vector_store.search_sparse(
                sparse_vector=query_embedding.sparse,
                limit=candidate_limit,
                filters=kb_filters,
            )
            all_dense.extend(dense)
            all_sparse.extend(sparse)

        timings["search"] = round((time.monotonic() - t0) * 1000)

        # RRF fusion
        fused = _rrf_fusion(all_dense, all_sparse, k=self._settings.retrieval_rrf_k)

        # 6. Rerank
        reranked = False
        rerank_scores: dict[str, float] = {}
        if self._reranker and fused:
            t0 = time.monotonic()
            try:
                candidates = fused[:self._settings.reranker_top_n]
                # Need chunk content for reranking — fetch from payloads or DB
                chunk_ids = [p.get("chunk_id", "") for _, _, p in candidates]
                contents = await self._get_chunk_contents(chunk_ids)

                rerank_results = await self._reranker.rerank(
                    query=rewritten_query,
                    documents=contents,
                    top_n=top_k,
                )
                # Rebuild fused order based on rerank
                reranked_ids = set()
                new_fused = []
                for rr in rerank_results:
                    if rr.index < len(candidates):
                        pid, score, payload = candidates[rr.index]
                        new_fused.append((pid, score, payload))
                        rerank_scores[pid] = rr.score
                        reranked_ids.add(pid)
                fused = new_fused
                reranked = True
            except Exception as e:
                logger.warning("rerank_failed", error=str(e))
            timings["rerank"] = round((time.monotonic() - t0) * 1000)

        # Take top_k
        top_results = fused[:top_k]

        # 7. Enrich
        enriched = await self._enrich_results(top_results, rerank_scores)

        # Filter by score threshold
        threshold = self._settings.rag_score_threshold
        enriched = [r for r in enriched if r.score >= threshold]

        timings["total"] = sum(timings.values())

        trace = SearchTrace(
            query_normalized=normalized,
            query_rewritten=rewritten_query if enable_rewrite else None,
            retrieval_context=ctx.to_filters(),
            dense_hits=len(all_dense),
            sparse_hits=len(all_sparse),
            fused_total=len(fused),
            reranked=reranked,
            returned=len(enriched),
            latency_ms=timings,
        )

        return RAGSearchResult(
            query=query,
            rewritten_query=rewritten_query if enable_rewrite else None,
            results=enriched,
            trace=trace,
        )

    # ------------------------------------------------------------------
    # Answer (streaming)
    # ------------------------------------------------------------------

    async def answer_stream(
        self,
        query: str,
        kb_ids: list[uuid.UUID],
        top_k: int | None = None,
        filters: dict | None = None,
        enable_rewrite: bool | None = None,
        enable_rerank: bool | None = None,
    ) -> AsyncIterator[dict]:
        """Execute search + generate, yielding SSE events.

        Event types: trace, citation, token, done, error
        """
        top_k = top_k or self._settings.rag_answer_top_k

        # Search
        try:
            search_result = await self.search(
                query=query,
                kb_ids=kb_ids,
                top_k=top_k,
                filters=filters,
                enable_rewrite=enable_rewrite,
            )
        except Exception as e:
            yield {"event": "error", "data": {"message": f"Search failed: {e}"}}
            return

        # Emit trace
        yield {
            "event": "trace",
            "data": {
                "query_rewritten": search_result.rewritten_query,
                "search_mode": "hybrid",
                "hits": search_result.trace.fused_total,
                "latency_ms": search_result.trace.latency_ms,
            },
        }

        # Check refusal
        if not search_result.results:
            yield {"event": "token", "data": {"content": "未找到相关信息，请尝试换一种方式提问。"}}
            yield {"event": "done", "data": {"total_tokens": 0, "refused": True}}
            return

        max_score = max(r.score for r in search_result.results)
        if max_score < self._settings.rag_refusal_threshold:
            yield {"event": "token", "data": {"content": "未找到足够相关的信息来回答您的问题。"}}
            yield {"event": "done", "data": {"total_tokens": 0, "refused": True}}
            return

        # Emit citations
        citations = self._build_citations(search_result.results)
        for cit in citations:
            yield {
                "event": "citation",
                "data": {
                    "index": cit.index,
                    "document_title": cit.document_title,
                    "page": cit.page,
                    "chunk_id": cit.chunk_id,
                    "snippet": cit.snippet,
                },
            }

        # Build context and generate
        context = self._pack_context(search_result.results)
        messages = self._build_answer_messages(query, context)

        total_tokens = 0
        try:
            async for chunk in self._llm.stream(messages):
                if chunk.content:
                    total_tokens += 1  # approximate
                    yield {"event": "token", "data": {"content": chunk.content}}
                if chunk.finish_reason == "stop":
                    break
        except Exception as e:
            yield {"event": "error", "data": {"message": f"Generation failed: {e}"}}
            return

        yield {"event": "done", "data": {"total_tokens": total_tokens}}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pack_context(self, results: list[SearchResultItem]) -> str:
        """Pack search results into LLM context string."""
        parts = []
        for i, r in enumerate(results, start=1):
            source = f"[{i}] {r.document_title}"
            if r.page_start:
                source += f" (p.{r.page_start})"
            parts.append(f"{source}\n{r.content}")
        return "\n\n---\n\n".join(parts)

    def _build_answer_messages(self, query: str, context: str) -> list[LLMMessage]:
        """Build messages for answer generation."""
        system_prompt = (
            "你是一个专业的储能行业知识问答助手。请根据以下检索到的参考资料回答用户问题。\n\n"
            "规则：\n"
            "1. 只基于提供的参考资料回答，不要编造信息\n"
            "2. 在回答中用 [1] [2] 等标注引用来源\n"
            "3. 如果参考资料不足以回答问题，请明确告知\n"
            "4. 回答要简洁准确\n\n"
            f"参考资料：\n{context}"
        )
        return [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=query),
        ]

    def _build_citations(self, results: list[SearchResultItem]) -> list[Citation]:
        """Build citation list from search results."""
        citations = []
        for i, r in enumerate(results, start=1):
            snippet = r.content[:200] + "..." if len(r.content) > 200 else r.content
            citations.append(Citation(
                index=i,
                document_title=r.document_title,
                page=r.page_start,
                chunk_id=r.chunk_id,
                snippet=snippet,
            ))
        return citations

    async def _get_chunk_contents(self, chunk_ids: list[str]) -> list[str]:
        """Fetch chunk contents from DB by IDs."""
        if not chunk_ids:
            return []
        valid_ids = [uuid.UUID(cid) for cid in chunk_ids if cid]
        if not valid_ids:
            return [""] * len(chunk_ids)

        stmt = select(Chunk.id, Chunk.content).where(Chunk.id.in_(valid_ids))
        result = await self._session.execute(stmt)
        lookup = {str(row.id): row.content for row in result}
        return [lookup.get(cid, "") for cid in chunk_ids]

    async def _enrich_results(
        self,
        fused: list[tuple[str, float, dict]],
        rerank_scores: dict[str, float],
    ) -> list[SearchResultItem]:
        """Enrich fused results with DB metadata."""
        if not fused:
            return []

        chunk_id_map: dict[str, tuple[str, float, dict]] = {}
        for pid, score, payload in fused:
            cid = payload.get("chunk_id", "")
            if cid:
                chunk_id_map[cid] = (pid, score, payload)

        if not chunk_id_map:
            return [
                SearchResultItem(
                    chunk_id=p.get("chunk_id", pid),
                    document_id=p.get("document_id", ""),
                    document_title="",
                    content="",
                    score=round(score, 6),
                    rerank_score=rerank_scores.get(pid),
                )
                for pid, score, p in fused
            ]

        chunk_uuids = [uuid.UUID(cid) for cid in chunk_id_map.keys()]
        stmt = (
            select(Chunk, Document.title)
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.id.in_(chunk_uuids))
        )
        result = await self._session.execute(stmt)
        rows = result.all()

        chunk_lookup: dict[str, tuple[Chunk, str]] = {}
        for chunk, doc_title in rows:
            chunk_lookup[str(chunk.id)] = (chunk, doc_title)

        enriched: list[SearchResultItem] = []
        for pid, score, payload in fused:
            cid = payload.get("chunk_id", "")
            if cid in chunk_lookup:
                chunk, doc_title = chunk_lookup[cid]
                enriched.append(SearchResultItem(
                    chunk_id=str(chunk.id),
                    document_id=str(chunk.document_id),
                    document_title=doc_title,
                    content=chunk.content,
                    score=round(score, 6),
                    rerank_score=rerank_scores.get(pid),
                    chunk_type=chunk.chunk_type,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section_path=chunk.section_path,
                    metadata=chunk.metadata_,
                ))
            else:
                enriched.append(SearchResultItem(
                    chunk_id=cid or pid,
                    document_id=payload.get("document_id", ""),
                    document_title="",
                    content="",
                    score=round(score, 6),
                    rerank_score=rerank_scores.get(pid),
                ))

        return enriched
