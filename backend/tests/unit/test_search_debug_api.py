"""Tests for search debug API endpoint (S8-03).

Tests POST /kb/{kb_id}/search_debug with dependency overrides.
"""
from __future__ import annotations

import hashlib
import random
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.knowledge.api.routes.search_debug import _get_embedding_provider, _get_vector_store
from app.common.core.config import Settings, get_settings
from app.common.core.dependencies import get_db
from app.common.db.base import Base
from app.common.db.models import Chunk, Document, DocumentVersion, KnowledgeBase
from app.main_knowledge import app as _test_app
from app.common.rag.embedding.base import EmbeddingProvider, EmbeddingResult
from app.common.rag.vector_store.base import SearchResult, VectorPoint, VectorStore


# --- In-memory implementations ---


class InMemoryEmbeddingProvider(EmbeddingProvider):
    """In-memory embedding provider for API testing."""

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        results = []
        for text in texts:
            rng = random.Random(hash(text))
            dense = [rng.gauss(0, 1) for _ in range(self._dim)]
            sparse = {rng.randint(0, 30000): rng.random() for _ in range(5)}
            results.append(EmbeddingResult(dense=dense, sparse=sparse))
        return results

    async def embed_query(self, query: str) -> EmbeddingResult:
        results = await self.embed_texts([query])
        return results[0]


class InMemoryVectorStore(VectorStore):
    """In-memory vector store for API testing with pre-configured results."""

    def __init__(self) -> None:
        self._points: dict[str, VectorPoint] = {}
        self._dense_results: list[SearchResult] = []
        self._sparse_results: list[SearchResult] = []

    def set_dense_results(self, results: list[SearchResult]) -> None:
        self._dense_results = results

    def set_sparse_results(self, results: list[SearchResult]) -> None:
        self._sparse_results = results

    async def ensure_collection(self) -> None:
        pass

    async def upsert(self, points: list[VectorPoint]) -> None:
        for p in points:
            self._points[p.id] = p

    async def delete(self, point_ids: list[str]) -> None:
        for pid in point_ids:
            self._points.pop(pid, None)

    async def search_dense(self, vector, limit=10, filters=None) -> list[SearchResult]:
        return self._dense_results[:limit]

    async def search_sparse(self, sparse_vector, limit=10, filters=None) -> list[SearchResult]:
        return self._sparse_results[:limit]


# --- Fixtures ---


@pytest_asyncio.fixture
async def api_engine():
    """Create an isolated async engine for API tests."""
    engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def api_session(api_engine) -> AsyncSession:
    """Provide a transactional database session for API tests."""
    factory = async_sessionmaker(api_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def in_memory_embedding() -> InMemoryEmbeddingProvider:
    return InMemoryEmbeddingProvider(dim=64)


@pytest.fixture
def in_memory_vector_store() -> InMemoryVectorStore:
    return InMemoryVectorStore()


@pytest_asyncio.fixture
async def api_client(
    api_session: AsyncSession,
    in_memory_embedding: InMemoryEmbeddingProvider,
    in_memory_vector_store: InMemoryVectorStore,
) -> AsyncClient:
    """Provide an async HTTP test client with dependency overrides."""
    app = _test_app

    async def _override_get_db():
        try:
            yield api_session
            await api_session.commit()
        except Exception:
            await api_session.rollback()
            raise

    def _override_get_embedding():
        return in_memory_embedding

    def _override_get_vector_store():
        return in_memory_vector_store

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_get_embedding_provider] = _override_get_embedding
    app.dependency_overrides[_get_vector_store] = _override_get_vector_store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def _setup_kb_with_chunks(
    session: AsyncSession,
    num_chunks: int = 3,
) -> tuple[KnowledgeBase, Document, list[Chunk]]:
    """Create a KB with a document and chunks for testing."""
    kb = KnowledgeBase(name=f"Search KB {uuid.uuid4().hex[:8]}", settings={})
    session.add(kb)
    await session.flush()

    doc = Document(
        knowledge_base_id=kb.id,
        title="储能系统维护手册",
        source_filename="maintenance.pdf",
        storage_path=f"{kb.id}/maintenance.pdf",
        content_hash=f"hash_{uuid.uuid4().hex[:8]}",
        mime_type="application/pdf",
        file_size_bytes=5000,
        document_type="manual",
        status="ready",
    )
    session.add(doc)
    await session.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        parser_profile="balanced",
        status="ready",
    )
    session.add(version)
    await session.flush()

    chunks: list[Chunk] = []
    contents = [
        "当出现E003过温告警时，应立即检查电池模组温度传感器",
        "电池管理系统BMS负责监控电池组的充放电状态",
        "储能系统日常维护包括定期检查电缆连接和绝缘状态",
    ]
    for i in range(num_chunks):
        content = contents[i] if i < len(contents) else f"Chunk content {i}"
        chunk = Chunk(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=version.id,
            ordinal=i,
            content=content,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            chunk_type="text",
            section_path=f"第{i + 1}章 > 告警处理 > 温度告警",
            page_start=i * 10 + 1,
            page_end=i * 10 + 5,
            token_count=50,
            language="zh",
            product_model="ESS-5000",
            qdrant_point_id=str(uuid.uuid4()),
        )
        session.add(chunk)
        await session.flush()
        chunks.append(chunk)

    await session.commit()
    return kb, doc, chunks


def _make_search_results_from_chunks(
    chunks: list[Chunk], doc: Document
) -> list[SearchResult]:
    """Build SearchResult list from chunks."""
    results = []
    for i, chunk in enumerate(chunks):
        results.append(
            SearchResult(
                id=chunk.qdrant_point_id or str(uuid.uuid4()),
                score=0.9 - i * 0.05,
                payload={
                    "kb_id": str(chunk.knowledge_base_id),
                    "document_id": str(doc.id),
                    "chunk_id": str(chunk.id),
                    "document_type": doc.document_type,
                    "language": chunk.language,
                    "product_model": chunk.product_model,
                },
            )
        )
    return results


# --- API Tests ---


@pytest.mark.unit
class TestSearchDebugAPI:
    """Tests for POST /kb/{kb_id}/search_debug."""

    @pytest.mark.asyncio
    async def test_search_debug_success(
        self,
        api_session: AsyncSession,
        api_client: AsyncClient,
        in_memory_vector_store: InMemoryVectorStore,
    ):
        """Should return 200 with search results."""
        kb, doc, chunks = await _setup_kb_with_chunks(api_session)

        # Configure vector store results
        results = _make_search_results_from_chunks(chunks[:2], doc)
        in_memory_vector_store.set_dense_results(results)
        in_memory_vector_store.set_sparse_results(results[:1])

        response = await api_client.post(
            f"/kb/{kb.id}/search_debug",
            json={
                "query": "电池过温告警处理",
                "top_k": 10,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "电池过温告警处理"
        assert "results" in data
        assert "trace" in data
        assert isinstance(data["results"], list)

    @pytest.mark.asyncio
    async def test_search_debug_response_structure(
        self,
        api_session: AsyncSession,
        api_client: AsyncClient,
        in_memory_vector_store: InMemoryVectorStore,
    ):
        """Response should have correct structure with all fields."""
        kb, doc, chunks = await _setup_kb_with_chunks(api_session)

        results = _make_search_results_from_chunks(chunks[:1], doc)
        in_memory_vector_store.set_dense_results(results)
        in_memory_vector_store.set_sparse_results(results)

        response = await api_client.post(
            f"/kb/{kb.id}/search_debug",
            json={"query": "test query", "top_k": 10},
        )

        assert response.status_code == 200
        data = response.json()

        # Check result item structure
        assert len(data["results"]) > 0
        item = data["results"][0]
        assert "chunk_id" in item
        assert "document_id" in item
        assert "document_title" in item
        assert "content" in item
        assert "score" in item
        assert "chunk_type" in item
        assert "page_start" in item
        assert "page_end" in item
        assert "section_path" in item
        assert "metadata" in item

        # Check trace structure
        trace = data["trace"]
        assert "dense_hits" in trace
        assert "sparse_hits" in trace
        assert "fused_total" in trace
        assert "returned" in trace

    @pytest.mark.asyncio
    async def test_search_debug_enriched_content(
        self,
        api_session: AsyncSession,
        api_client: AsyncClient,
        in_memory_vector_store: InMemoryVectorStore,
    ):
        """Results should contain enriched document title and chunk content."""
        kb, doc, chunks = await _setup_kb_with_chunks(api_session)

        results = _make_search_results_from_chunks(chunks[:1], doc)
        in_memory_vector_store.set_dense_results(results)
        in_memory_vector_store.set_sparse_results([])

        response = await api_client.post(
            f"/kb/{kb.id}/search_debug",
            json={"query": "过温告警", "top_k": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1

        item = data["results"][0]
        assert item["document_title"] == "储能系统维护手册"
        assert "E003过温告警" in item["content"]
        assert item["chunk_type"] == "text"
        assert item["document_id"] == str(doc.id)

    @pytest.mark.asyncio
    async def test_search_debug_with_filters(
        self,
        api_session: AsyncSession,
        api_client: AsyncClient,
        in_memory_vector_store: InMemoryVectorStore,
    ):
        """Should accept and process filters."""
        kb, doc, chunks = await _setup_kb_with_chunks(api_session)

        results = _make_search_results_from_chunks(chunks[:1], doc)
        in_memory_vector_store.set_dense_results(results)
        in_memory_vector_store.set_sparse_results([])

        response = await api_client.post(
            f"/kb/{kb.id}/search_debug",
            json={
                "query": "电池告警",
                "top_k": 10,
                "filters": {
                    "document_type": "manual",
                    "language": "zh",
                },
            },
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_debug_with_product_model_filter(
        self,
        api_session: AsyncSession,
        api_client: AsyncClient,
        in_memory_vector_store: InMemoryVectorStore,
    ):
        """Should accept product_model filter."""
        kb, doc, chunks = await _setup_kb_with_chunks(api_session)

        response = await api_client.post(
            f"/kb/{kb.id}/search_debug",
            json={
                "query": "电池告警",
                "top_k": 5,
                "filters": {
                    "product_model": "ESS-5000",
                },
            },
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_debug_kb_not_found(self, api_client: AsyncClient):
        """Should return 404 when KB doesn't exist."""
        fake_kb_id = str(uuid.uuid4())
        response = await api_client.post(
            f"/kb/{fake_kb_id}/search_debug",
            json={"query": "test", "top_k": 10},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_search_debug_empty_query_rejected(self, api_client: AsyncClient):
        """Should reject empty query string."""
        fake_kb_id = str(uuid.uuid4())
        response = await api_client.post(
            f"/kb/{fake_kb_id}/search_debug",
            json={"query": "", "top_k": 10},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_debug_invalid_top_k(self, api_client: AsyncClient):
        """Should reject invalid top_k values."""
        fake_kb_id = str(uuid.uuid4())

        # top_k = 0
        response = await api_client.post(
            f"/kb/{fake_kb_id}/search_debug",
            json={"query": "test", "top_k": 0},
        )
        assert response.status_code == 422

        # top_k > 100
        response = await api_client.post(
            f"/kb/{fake_kb_id}/search_debug",
            json={"query": "test", "top_k": 101},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_debug_default_top_k(
        self,
        api_session: AsyncSession,
        api_client: AsyncClient,
        in_memory_vector_store: InMemoryVectorStore,
    ):
        """Should use default top_k=10 when not specified."""
        kb, doc, chunks = await _setup_kb_with_chunks(api_session)

        response = await api_client.post(
            f"/kb/{kb.id}/search_debug",
            json={"query": "test query"},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_debug_empty_results(
        self,
        api_session: AsyncSession,
        api_client: AsyncClient,
        in_memory_vector_store: InMemoryVectorStore,
    ):
        """Should handle empty results gracefully."""
        kb, doc, chunks = await _setup_kb_with_chunks(api_session)

        # No results configured
        response = await api_client.post(
            f"/kb/{kb.id}/search_debug",
            json={"query": "nonexistent topic", "top_k": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        assert data["trace"]["dense_hits"] == 0
        assert data["trace"]["sparse_hits"] == 0
        assert data["trace"]["returned"] == 0

    @pytest.mark.asyncio
    async def test_search_debug_trace_counts(
        self,
        api_session: AsyncSession,
        api_client: AsyncClient,
        in_memory_vector_store: InMemoryVectorStore,
    ):
        """Trace should report correct hit counts."""
        kb, doc, chunks = await _setup_kb_with_chunks(api_session)

        dense_results = _make_search_results_from_chunks(chunks[:2], doc)
        sparse_results = _make_search_results_from_chunks(chunks[1:3], doc)
        in_memory_vector_store.set_dense_results(dense_results)
        in_memory_vector_store.set_sparse_results(sparse_results)

        response = await api_client.post(
            f"/kb/{kb.id}/search_debug",
            json={"query": "test", "top_k": 10},
        )

        assert response.status_code == 200
        trace = response.json()["trace"]
        assert trace["dense_hits"] == 2
        assert trace["sparse_hits"] == 2

    @pytest.mark.asyncio
    async def test_search_debug_invalid_kb_id_format(self, api_client: AsyncClient):
        """Should return 422 for invalid UUID format."""
        response = await api_client.post(
            "/kb/not-a-uuid/search_debug",
            json={"query": "test", "top_k": 10},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_debug_no_filters_field(
        self,
        api_session: AsyncSession,
        api_client: AsyncClient,
        in_memory_vector_store: InMemoryVectorStore,
    ):
        """Should work without filters field in request."""
        kb, doc, chunks = await _setup_kb_with_chunks(api_session)

        response = await api_client.post(
            f"/kb/{kb.id}/search_debug",
            json={"query": "test query", "top_k": 5},
        )

        assert response.status_code == 200
