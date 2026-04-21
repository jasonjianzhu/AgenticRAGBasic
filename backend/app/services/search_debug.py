"""Search debug service — hybrid search with RRF fusion.

Executes dense + sparse search against the vector store,
fuses results using Reciprocal Rank Fusion (RRF), and
enriches results with document/chunk metadata from the DB.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.models import Chunk, Document
from app.rag.embedding.base import EmbeddingProvider
from app.rag.vector_store.base import SearchResult, VectorStore

logger = get_logger(__name__)

# Number of candidates to fetch from each search method before fusion
_CANDIDATE_LIMIT = 20


@dataclass
class FusedResult:
    """A single fused search result with RRF score."""

    point_id: str
    score: float
    payload: dict = field(default_factory=dict)


@dataclass
class SearchDebugResult:
    """Complete search debug result with trace information."""

    query: str
    results: list[dict[str, Any]]
    dense_hits: int
    sparse_hits: int
    fused_total: int
    returned: int


class SearchDebugService:
    """Hybrid search service with RRF fusion and metadata enrichment.

    Args:
        embedding_provider: Provider for query embedding (dense + sparse).
        vector_store: Vector store for similarity search.
        session: Async SQLAlchemy session for DB enrichment.
        settings: Application settings (for RRF k parameter).
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        session: AsyncSession,
        settings: Settings | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._session = session
        self._settings = settings or get_settings()

    async def search(
        self,
        kb_id: uuid.UUID,
        query: str,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> SearchDebugResult:
        """Execute hybrid search and return debug results.

        Steps:
        1. Embed the query to get dense + sparse vectors
        2. Run dense search (top 20 candidates)
        3. Run sparse search (top 20 candidates)
        4. Fuse results using RRF
        5. Enrich top_k results with DB metadata

        Args:
            kb_id: Knowledge base ID to search within.
            query: Search query text.
            top_k: Number of results to return.
            filters: Optional metadata filters (document_type, language, product_model).

        Returns:
            SearchDebugResult with enriched results and trace info.
        """
        # 1. Embed the query
        query_embedding = await self._embedding_provider.embed_query(query)

        # Build payload filters including kb_id
        payload_filters = {"kb_id": str(kb_id)}
        if filters:
            for key, value in filters.items():
                if value is not None:
                    payload_filters[key] = value

        # 2. Dense search
        dense_results = await self._vector_store.search_dense(
            vector=query_embedding.dense,
            limit=_CANDIDATE_LIMIT,
            filters=payload_filters,
        )

        # 3. Sparse search
        sparse_results = await self._vector_store.search_sparse(
            sparse_vector=query_embedding.sparse,
            limit=_CANDIDATE_LIMIT,
            filters=payload_filters,
        )

        # 4. RRF fusion
        rrf_k = self._settings.retrieval_rrf_k
        fused = self._rrf_fusion(dense_results, sparse_results, k=rrf_k)

        # 5. Take top_k and enrich
        top_results = fused[:top_k]
        enriched = await self._enrich_results(top_results)

        return SearchDebugResult(
            query=query,
            results=enriched,
            dense_hits=len(dense_results),
            sparse_hits=len(sparse_results),
            fused_total=len(fused),
            returned=len(enriched),
        )

    def _rrf_fusion(
        self,
        dense_results: list[SearchResult],
        sparse_results: list[SearchResult],
        k: int = 60,
    ) -> list[FusedResult]:
        """Merge dense and sparse results using Reciprocal Rank Fusion.

        RRF score = sum(1 / (k + rank)) for each ranking list
        where rank is 1-based position in the list.

        Args:
            dense_results: Results from dense search (ordered by score desc).
            sparse_results: Results from sparse search (ordered by score desc).
            k: RRF constant (default 60).

        Returns:
            List of FusedResult sorted by fused score descending.
        """
        scores: dict[str, float] = {}
        payloads: dict[str, dict] = {}

        # Process dense results
        for rank, result in enumerate(dense_results, start=1):
            scores[result.id] = scores.get(result.id, 0.0) + 1.0 / (k + rank)
            payloads[result.id] = result.payload

        # Process sparse results
        for rank, result in enumerate(sparse_results, start=1):
            scores[result.id] = scores.get(result.id, 0.0) + 1.0 / (k + rank)
            if result.id not in payloads:
                payloads[result.id] = result.payload

        # Build fused results and sort by score descending
        fused = [
            FusedResult(point_id=pid, score=score, payload=payloads.get(pid, {}))
            for pid, score in scores.items()
        ]
        fused.sort(key=lambda r: r.score, reverse=True)

        return fused

    async def _enrich_results(
        self,
        fused_results: list[FusedResult],
    ) -> list[dict[str, Any]]:
        """Enrich fused results with document titles and chunk details from DB.

        Uses the chunk_id from the vector payload to look up chunk and document info.
        """
        if not fused_results:
            return []

        # Collect chunk_ids from payloads
        chunk_id_map: dict[str, FusedResult] = {}
        for result in fused_results:
            chunk_id = result.payload.get("chunk_id")
            if chunk_id:
                chunk_id_map[chunk_id] = result

        if not chunk_id_map:
            # No chunk_ids in payloads, return basic results
            return [
                {
                    "chunk_id": r.payload.get("chunk_id", r.point_id),
                    "document_id": r.payload.get("document_id", ""),
                    "document_title": "",
                    "content": "",
                    "score": round(r.score, 6),
                    "chunk_type": "text",
                    "page_start": None,
                    "page_end": None,
                    "section_path": None,
                    "metadata": r.payload,
                }
                for r in fused_results
            ]

        # Query chunks with their documents
        chunk_uuids = [uuid.UUID(cid) for cid in chunk_id_map.keys()]
        stmt = (
            select(Chunk, Document.title)
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.id.in_(chunk_uuids))
        )
        result = await self._session.execute(stmt)
        rows = result.all()

        # Build lookup by chunk_id
        chunk_lookup: dict[str, tuple[Chunk, str]] = {}
        for chunk, doc_title in rows:
            chunk_lookup[str(chunk.id)] = (chunk, doc_title)

        # Build enriched results in fused order
        enriched: list[dict[str, Any]] = []
        for fused in fused_results:
            chunk_id = fused.payload.get("chunk_id", "")
            if chunk_id in chunk_lookup:
                chunk, doc_title = chunk_lookup[chunk_id]
                enriched.append({
                    "chunk_id": str(chunk.id),
                    "document_id": str(chunk.document_id),
                    "document_title": doc_title,
                    "content": chunk.content,
                    "score": round(fused.score, 6),
                    "chunk_type": chunk.chunk_type,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "section_path": chunk.section_path,
                    "metadata": chunk.metadata_,
                })
            else:
                # Chunk not found in DB, return basic info from payload
                enriched.append({
                    "chunk_id": chunk_id or fused.point_id,
                    "document_id": fused.payload.get("document_id", ""),
                    "document_title": "",
                    "content": "",
                    "score": round(fused.score, 6),
                    "chunk_type": "text",
                    "page_start": None,
                    "page_end": None,
                    "section_path": None,
                    "metadata": fused.payload,
                })

        return enriched
