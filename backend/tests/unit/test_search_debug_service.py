"""Tests for SearchDebugService (S8-01, S8-02).

Tests RRF fusion logic, hybrid search, and metadata filtering.
Uses InMemoryEmbeddingProvider and InMemoryVectorStore.
"""
from __future__ import annotations

import hashlib
import random
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.common.core.config import Settings
from app.common.db.base import Base
from app.common.db.models import Chunk, Document, DocumentVersion, KnowledgeBase
from app.common.rag.embedding.base import EmbeddingProvider, EmbeddingResult
from app.common.rag.vector_store.base import SearchResult, VectorPoint, VectorStore
from app.knowledge.services.search_debug import FusedResult, SearchDebugService


# --- In-memory implementations ---


class InMemoryEmbeddingProvider(EmbeddingProvider):
    """In-memory embedding provider for testing."""

    def __init__(self, dim: int = 64, seed: int = 42) -> None:
        self._dim = dim
        self._seed = seed
        self.call_count = 0
        self.queries_embedded: list[str] = []

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        self.call_count += 1
        results = []
        for text in texts:
            rng = random.Random(hash(text) + self._seed)
            dense = [rng.gauss(0, 1) for _ in range(self._dim)]
            sparse = {rng.randint(0, 30000): rng.random() for _ in range(5)}
            results.append(EmbeddingResult(dense=dense, sparse=sparse))
        return results

    async def embed_query(self, query: str) -> EmbeddingResult:
        self.queries_embedded.append(query)
        results = await self.embed_texts([query])
        return results[0]


class InMemoryVectorStore(VectorStore):
    """In-memory vector store for testing with configurable search results."""

    def __init__(self) -> None:
        self._points: dict[str, VectorPoint] = {}
        self._dense_results: list[SearchResult] = []
        self._sparse_results: list[SearchResult] = []
        self.dense_search_calls: list[dict] = []
        self.sparse_search_calls: list[dict] = []

    def set_dense_results(self, results: list[SearchResult]) -> None:
        """Configure results returned by search_dense."""
        self._dense_results = results

    def set_sparse_results(self, results: list[SearchResult]) -> None:
        """Configure results returned by search_sparse."""
        self._sparse_results = results

    async def ensure_collection(self) -> None:
        pass

    async def upsert(self, points: list[VectorPoint]) -> None:
        for p in points:
            self._points[p.id] = p

    async def delete(self, point_ids: list[str]) -> None:
        for pid in point_ids:
            self._points.pop(pid, None)

    async def search_dense(
        self, vector, limit=10, filters=None
    ) -> list[SearchResult]:
        self.dense_search_calls.append({"vector": vector, "limit": limit, "filters": filters})
        return self._dense_results[:limit]

    async def search_sparse(
        self, sparse_vector, limit=10, filters=None
    ) -> list[SearchResult]:
        self.sparse_search_calls.append(
            {"sparse_vector": sparse_vector, "limit": limit, "filters": filters}
        )
        return self._sparse_results[:limit]


# --- Fixtures ---


@pytest_asyncio.fixture
async def async_engine():
    """Create an isolated async engine for tests."""
    engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncSession:
    """Provide a transactional database session for tests."""
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def test_settings() -> Settings:
    """Test settings with known RRF k value."""
    return Settings(
        DATABASE_URL="sqlite+aiosqlite:///",
        DATABASE_URL_SYNC="sqlite:///",
        APP_ENV="testing",
        RETRIEVAL_RRF_K=60,
    )


@pytest.fixture
def embedding_provider() -> InMemoryEmbeddingProvider:
    return InMemoryEmbeddingProvider(dim=64)


@pytest.fixture
def vector_store() -> InMemoryVectorStore:
    return InMemoryVectorStore()


async def _create_kb_with_chunks(
    session: AsyncSession,
    num_docs: int = 1,
    chunks_per_doc: int = 3,
    doc_type: str = "manual",
    language: str = "zh",
    product_model: str | None = None,
) -> tuple[KnowledgeBase, list[Document], list[Chunk]]:
    """Helper to create a KB with documents and chunks."""
    kb = KnowledgeBase(name=f"Test KB {uuid.uuid4().hex[:8]}", settings={})
    session.add(kb)
    await session.flush()

    all_docs: list[Document] = []
    all_chunks: list[Chunk] = []

    for d in range(num_docs):
        doc = Document(
            knowledge_base_id=kb.id,
            title=f"Test Document {d}",
            source_filename=f"doc{d}.pdf",
            storage_path=f"{kb.id}/doc{d}.pdf",
            content_hash=f"hash{d}_{uuid.uuid4().hex[:8]}",
            mime_type="application/pdf",
            file_size_bytes=1000,
            document_type=doc_type,
            status="ready",
        )
        session.add(doc)
        await session.flush()
        all_docs.append(doc)

        version = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            parser_profile="balanced",
            status="ready",
        )
        session.add(version)
        await session.flush()

        for c in range(chunks_per_doc):
            content = f"Chunk content doc{d} chunk{c} about battery temperature alarm"
            chunk = Chunk(
                knowledge_base_id=kb.id,
                document_id=doc.id,
                document_version_id=version.id,
                ordinal=c,
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                chunk_type="text",
                section_path=f"Chapter {c + 1} > Section {c + 1}",
                page_start=c + 1,
                page_end=c + 1,
                token_count=50,
                language=language,
                product_model=product_model,
                qdrant_point_id=str(uuid.uuid4()),
            )
            session.add(chunk)
            await session.flush()
            all_chunks.append(chunk)

    await session.commit()
    return kb, all_docs, all_chunks


def _make_search_results(chunks: list[Chunk], scores: list[float] | None = None) -> list[SearchResult]:
    """Build SearchResult list from chunks with optional scores."""
    if scores is None:
        scores = [0.9 - i * 0.05 for i in range(len(chunks))]
    results = []
    for chunk, score in zip(chunks, scores):
        results.append(
            SearchResult(
                id=chunk.qdrant_point_id or str(uuid.uuid4()),
                score=score,
                payload={
                    "kb_id": str(chunk.knowledge_base_id),
                    "document_id": str(chunk.document_id),
                    "chunk_id": str(chunk.id),
                    "document_type": "manual",
                    "language": chunk.language,
                    "product_model": chunk.product_model,
                },
            )
        )
    return results


# --- RRF Fusion Tests ---


@pytest.mark.unit
class TestRRFFusion:
    """Tests for the RRF fusion algorithm."""

    def test_rrf_single_dense_result(self, embedding_provider, vector_store, test_settings):
        """Single dense result should get correct RRF score."""
        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=None,  # type: ignore  # Not needed for _rrf_fusion
            settings=test_settings,
        )

        dense = [SearchResult(id="a", score=0.9, payload={"key": "val"})]
        sparse: list[SearchResult] = []

        fused = service._rrf_fusion(dense, sparse, k=60)

        assert len(fused) == 1
        assert fused[0].point_id == "a"
        # rank=1, score = 1/(60+1) = 1/61
        expected = 1.0 / 61
        assert abs(fused[0].score - expected) < 1e-9

    def test_rrf_single_sparse_result(self, embedding_provider, vector_store, test_settings):
        """Single sparse result should get correct RRF score."""
        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=None,  # type: ignore
            settings=test_settings,
        )

        dense: list[SearchResult] = []
        sparse = [SearchResult(id="b", score=0.8, payload={})]

        fused = service._rrf_fusion(dense, sparse, k=60)

        assert len(fused) == 1
        assert fused[0].point_id == "b"
        expected = 1.0 / 61
        assert abs(fused[0].score - expected) < 1e-9

    def test_rrf_overlapping_results_get_higher_score(
        self, embedding_provider, vector_store, test_settings
    ):
        """Results appearing in both dense and sparse should score higher."""
        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=None,  # type: ignore
            settings=test_settings,
        )

        # "a" appears in both, "b" only in dense, "c" only in sparse
        dense = [
            SearchResult(id="a", score=0.9, payload={}),
            SearchResult(id="b", score=0.8, payload={}),
        ]
        sparse = [
            SearchResult(id="a", score=0.7, payload={}),
            SearchResult(id="c", score=0.6, payload={}),
        ]

        fused = service._rrf_fusion(dense, sparse, k=60)

        assert len(fused) == 3
        # "a" should be first (appears in both)
        assert fused[0].point_id == "a"
        # Score for "a": 1/(60+1) + 1/(60+1) = 2/61
        expected_a = 1.0 / 61 + 1.0 / 61
        assert abs(fused[0].score - expected_a) < 1e-9

        # "b" and "c" should have equal scores (both rank 2 in their respective lists)
        # But "b" is rank 2 in dense: 1/(60+2) = 1/62
        # "c" is rank 2 in sparse: 1/(60+2) = 1/62
        assert abs(fused[1].score - 1.0 / 62) < 1e-9
        assert abs(fused[2].score - 1.0 / 62) < 1e-9

    def test_rrf_sorted_by_score_descending(self, embedding_provider, vector_store, test_settings):
        """Results should be sorted by fused score descending."""
        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=None,  # type: ignore
            settings=test_settings,
        )

        dense = [
            SearchResult(id="x", score=0.9, payload={}),
            SearchResult(id="y", score=0.8, payload={}),
            SearchResult(id="z", score=0.7, payload={}),
        ]
        sparse = [
            SearchResult(id="z", score=0.9, payload={}),
            SearchResult(id="y", score=0.8, payload={}),
        ]

        fused = service._rrf_fusion(dense, sparse, k=60)

        scores = [r.score for r in fused]
        assert scores == sorted(scores, reverse=True)

    def test_rrf_empty_inputs(self, embedding_provider, vector_store, test_settings):
        """Empty inputs should return empty results."""
        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=None,  # type: ignore
            settings=test_settings,
        )

        fused = service._rrf_fusion([], [], k=60)
        assert fused == []

    def test_rrf_custom_k_value(self, embedding_provider, vector_store, test_settings):
        """Different k values should produce different scores."""
        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=None,  # type: ignore
            settings=test_settings,
        )

        dense = [SearchResult(id="a", score=0.9, payload={})]

        fused_k10 = service._rrf_fusion(dense, [], k=10)
        fused_k60 = service._rrf_fusion(dense, [], k=60)

        # k=10: score = 1/(10+1) = 1/11
        # k=60: score = 1/(60+1) = 1/61
        assert abs(fused_k10[0].score - 1.0 / 11) < 1e-9
        assert abs(fused_k60[0].score - 1.0 / 61) < 1e-9
        assert fused_k10[0].score > fused_k60[0].score

    def test_rrf_preserves_payload(self, embedding_provider, vector_store, test_settings):
        """Payload from the first occurrence should be preserved."""
        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=None,  # type: ignore
            settings=test_settings,
        )

        dense = [SearchResult(id="a", score=0.9, payload={"source": "dense", "chunk_id": "c1"})]
        sparse = [SearchResult(id="a", score=0.8, payload={"source": "sparse", "chunk_id": "c1"})]

        fused = service._rrf_fusion(dense, sparse, k=60)

        assert fused[0].payload["source"] == "dense"  # Dense payload takes precedence
        assert fused[0].payload["chunk_id"] == "c1"

    def test_rrf_many_results(self, embedding_provider, vector_store, test_settings):
        """Should handle many results correctly."""
        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=None,  # type: ignore
            settings=test_settings,
        )

        dense = [
            SearchResult(id=f"d{i}", score=1.0 - i * 0.01, payload={})
            for i in range(20)
        ]
        sparse = [
            SearchResult(id=f"s{i}", score=1.0 - i * 0.01, payload={})
            for i in range(20)
        ]

        fused = service._rrf_fusion(dense, sparse, k=60)

        # 20 unique dense + 20 unique sparse = 40 total
        assert len(fused) == 40
        # All scores should be positive
        assert all(r.score > 0 for r in fused)
        # Should be sorted
        scores = [r.score for r in fused]
        assert scores == sorted(scores, reverse=True)


# --- Hybrid Search Tests ---


@pytest.mark.unit
class TestHybridSearch:
    """Tests for the full hybrid search flow."""

    @pytest.mark.asyncio
    async def test_search_embeds_query(
        self, db_session, embedding_provider, vector_store, test_settings
    ):
        """Should embed the query text."""
        kb, docs, chunks = await _create_kb_with_chunks(db_session)

        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=db_session,
            settings=test_settings,
        )

        await service.search(kb.id, "battery alarm", top_k=5)

        assert "battery alarm" in embedding_provider.queries_embedded

    @pytest.mark.asyncio
    async def test_search_calls_dense_and_sparse(
        self, db_session, embedding_provider, vector_store, test_settings
    ):
        """Should call both dense and sparse search."""
        kb, docs, chunks = await _create_kb_with_chunks(db_session)

        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=db_session,
            settings=test_settings,
        )

        await service.search(kb.id, "test query", top_k=5)

        assert len(vector_store.dense_search_calls) == 1
        assert len(vector_store.sparse_search_calls) == 1

    @pytest.mark.asyncio
    async def test_search_passes_kb_id_filter(
        self, db_session, embedding_provider, vector_store, test_settings
    ):
        """Should include kb_id in search filters."""
        kb, docs, chunks = await _create_kb_with_chunks(db_session)

        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=db_session,
            settings=test_settings,
        )

        await service.search(kb.id, "test query", top_k=5)

        dense_call = vector_store.dense_search_calls[0]
        assert dense_call["filters"]["kb_id"] == str(kb.id)

        sparse_call = vector_store.sparse_search_calls[0]
        assert sparse_call["filters"]["kb_id"] == str(kb.id)

    @pytest.mark.asyncio
    async def test_search_requests_20_candidates(
        self, db_session, embedding_provider, vector_store, test_settings
    ):
        """Should request 20 candidates from each search method."""
        kb, docs, chunks = await _create_kb_with_chunks(db_session)

        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=db_session,
            settings=test_settings,
        )

        await service.search(kb.id, "test query", top_k=5)

        assert vector_store.dense_search_calls[0]["limit"] == 20
        assert vector_store.sparse_search_calls[0]["limit"] == 20

    @pytest.mark.asyncio
    async def test_search_returns_enriched_results(
        self, db_session, embedding_provider, vector_store, test_settings
    ):
        """Should return results enriched with document titles and chunk details."""
        kb, docs, chunks = await _create_kb_with_chunks(db_session, num_docs=1, chunks_per_doc=3)

        # Set up vector store to return our chunks
        dense_results = _make_search_results(chunks[:2], scores=[0.9, 0.8])
        sparse_results = _make_search_results(chunks[1:3], scores=[0.85, 0.75])
        vector_store.set_dense_results(dense_results)
        vector_store.set_sparse_results(sparse_results)

        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=db_session,
            settings=test_settings,
        )

        result = await service.search(kb.id, "battery alarm", top_k=10)

        assert len(result.results) > 0
        # Check enrichment
        for r in result.results:
            assert r["document_title"] != ""
            assert r["content"] != ""
            assert r["chunk_id"] != ""
            assert r["document_id"] != ""

    @pytest.mark.asyncio
    async def test_search_trace_info(
        self, db_session, embedding_provider, vector_store, test_settings
    ):
        """Should return correct trace information."""
        kb, docs, chunks = await _create_kb_with_chunks(db_session, num_docs=1, chunks_per_doc=5)

        dense_results = _make_search_results(chunks[:3])
        sparse_results = _make_search_results(chunks[2:5])
        vector_store.set_dense_results(dense_results)
        vector_store.set_sparse_results(sparse_results)

        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=db_session,
            settings=test_settings,
        )

        result = await service.search(kb.id, "test", top_k=10)

        assert result.dense_hits == 3
        assert result.sparse_hits == 3
        assert result.query == "test"

    @pytest.mark.asyncio
    async def test_search_top_k_limits_results(
        self, db_session, embedding_provider, vector_store, test_settings
    ):
        """Should respect top_k limit."""
        kb, docs, chunks = await _create_kb_with_chunks(db_session, num_docs=2, chunks_per_doc=5)

        dense_results = _make_search_results(chunks[:5])
        sparse_results = _make_search_results(chunks[3:8])
        vector_store.set_dense_results(dense_results)
        vector_store.set_sparse_results(sparse_results)

        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=db_session,
            settings=test_settings,
        )

        result = await service.search(kb.id, "test", top_k=3)

        assert result.returned <= 3
        assert len(result.results) <= 3

    @pytest.mark.asyncio
    async def test_search_empty_results(
        self, db_session, embedding_provider, vector_store, test_settings
    ):
        """Should handle empty search results gracefully."""
        kb, docs, chunks = await _create_kb_with_chunks(db_session)

        # No results configured (defaults to empty)
        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=db_session,
            settings=test_settings,
        )

        result = await service.search(kb.id, "nonexistent query", top_k=10)

        assert result.results == []
        assert result.dense_hits == 0
        assert result.sparse_hits == 0
        assert result.fused_total == 0
        assert result.returned == 0

    @pytest.mark.asyncio
    async def test_search_result_scores_are_rrf(
        self, db_session, embedding_provider, vector_store, test_settings
    ):
        """Result scores should be RRF scores, not raw similarity scores."""
        kb, docs, chunks = await _create_kb_with_chunks(db_session, num_docs=1, chunks_per_doc=2)

        # chunk[0] in both dense and sparse at rank 1
        dense_results = _make_search_results([chunks[0]], scores=[0.95])
        sparse_results = _make_search_results([chunks[0]], scores=[0.85])
        vector_store.set_dense_results(dense_results)
        vector_store.set_sparse_results(sparse_results)

        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=db_session,
            settings=test_settings,
        )

        result = await service.search(kb.id, "test", top_k=10)

        assert len(result.results) == 1
        # RRF score for rank 1 in both: 2 * 1/(60+1) = 2/61
        expected_score = round(2.0 / 61, 6)
        assert result.results[0]["score"] == expected_score


# --- Metadata Filter Tests ---


@pytest.mark.unit
class TestMetadataFilters:
    """Tests for metadata filter passthrough (S8-02)."""

    @pytest.mark.asyncio
    async def test_filters_passed_to_dense_search(
        self, db_session, embedding_provider, vector_store, test_settings
    ):
        """Filters should be passed to dense search."""
        kb, docs, chunks = await _create_kb_with_chunks(db_session)

        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=db_session,
            settings=test_settings,
        )

        filters = {"document_type": "manual", "language": "zh"}
        await service.search(kb.id, "test", top_k=5, filters=filters)

        dense_call = vector_store.dense_search_calls[0]
        assert dense_call["filters"]["document_type"] == "manual"
        assert dense_call["filters"]["language"] == "zh"

    @pytest.mark.asyncio
    async def test_filters_passed_to_sparse_search(
        self, db_session, embedding_provider, vector_store, test_settings
    ):
        """Filters should be passed to sparse search."""
        kb, docs, chunks = await _create_kb_with_chunks(db_session)

        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=db_session,
            settings=test_settings,
        )

        filters = {"document_type": "faq", "language": "en"}
        await service.search(kb.id, "test", top_k=5, filters=filters)

        sparse_call = vector_store.sparse_search_calls[0]
        assert sparse_call["filters"]["document_type"] == "faq"
        assert sparse_call["filters"]["language"] == "en"

    @pytest.mark.asyncio
    async def test_product_model_filter(
        self, db_session, embedding_provider, vector_store, test_settings
    ):
        """Product model filter should be passed through."""
        kb, docs, chunks = await _create_kb_with_chunks(db_session)

        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=db_session,
            settings=test_settings,
        )

        filters = {"product_model": "ESS-5000"}
        await service.search(kb.id, "test", top_k=5, filters=filters)

        dense_call = vector_store.dense_search_calls[0]
        assert dense_call["filters"]["product_model"] == "ESS-5000"

    @pytest.mark.asyncio
    async def test_no_filters(
        self, db_session, embedding_provider, vector_store, test_settings
    ):
        """When no filters, only kb_id should be in the filter."""
        kb, docs, chunks = await _create_kb_with_chunks(db_session)

        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=db_session,
            settings=test_settings,
        )

        await service.search(kb.id, "test", top_k=5, filters=None)

        dense_call = vector_store.dense_search_calls[0]
        assert dense_call["filters"] == {"kb_id": str(kb.id)}

    @pytest.mark.asyncio
    async def test_combined_filters(
        self, db_session, embedding_provider, vector_store, test_settings
    ):
        """Multiple filters should all be passed through."""
        kb, docs, chunks = await _create_kb_with_chunks(db_session)

        service = SearchDebugService(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            session=db_session,
            settings=test_settings,
        )

        filters = {
            "document_type": "spec",
            "language": "zh",
            "product_model": "BAT-100",
        }
        await service.search(kb.id, "test", top_k=5, filters=filters)

        dense_call = vector_store.dense_search_calls[0]
        assert dense_call["filters"]["kb_id"] == str(kb.id)
        assert dense_call["filters"]["document_type"] == "spec"
        assert dense_call["filters"]["language"] == "zh"
        assert dense_call["filters"]["product_model"] == "BAT-100"
