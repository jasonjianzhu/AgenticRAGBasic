"""Tests for VectorStore interface and data models (S7-03, S7-04).

Uses an InMemoryVectorStore for unit testing without real Qdrant.
"""
from __future__ import annotations

import math

import pytest

from app.rag.vector_store.base import SearchResult, VectorPoint, VectorStore


# --- In-memory implementation for testing ---

class InMemoryVectorStore(VectorStore):
    """In-memory vector store for unit testing.

    Stores points in a dict and performs brute-force cosine similarity search.
    """

    def __init__(self) -> None:
        self._points: dict[str, VectorPoint] = {}
        self._collection_created = False

    async def ensure_collection(self) -> None:
        self._collection_created = True

    async def upsert(self, points: list[VectorPoint]) -> None:
        for p in points:
            self._points[p.id] = p

    async def delete(self, point_ids: list[str]) -> None:
        for pid in point_ids:
            self._points.pop(pid, None)

    async def search_dense(
        self,
        vector: list[float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        results = []
        for p in self._points.values():
            if filters and not self._matches_filter(p.payload, filters):
                continue
            score = self._cosine_similarity(vector, p.dense_vector)
            results.append(SearchResult(id=p.id, score=score, payload=p.payload))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    async def search_sparse(
        self,
        sparse_vector: dict[int, float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        if not sparse_vector:
            return []
        results = []
        for p in self._points.values():
            if filters and not self._matches_filter(p.payload, filters):
                continue
            score = self._sparse_dot_product(sparse_vector, p.sparse_vector)
            results.append(SearchResult(id=p.id, score=score, payload=p.payload))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _sparse_dot_product(a: dict[int, float], b: dict[int, float]) -> float:
        score = 0.0
        for k, v in a.items():
            if k in b:
                score += v * b[k]
        return score

    @staticmethod
    def _matches_filter(payload: dict, filters: dict) -> bool:
        for key, value in filters.items():
            if value is not None and payload.get(key) != value:
                return False
        return True


@pytest.mark.unit
class TestVectorPoint:
    """Tests for VectorPoint dataclass."""

    def test_create_minimal(self):
        """Should create with required fields only."""
        point = VectorPoint(id="p1", dense_vector=[0.1, 0.2])
        assert point.id == "p1"
        assert point.dense_vector == [0.1, 0.2]
        assert point.sparse_vector == {}
        assert point.payload == {}

    def test_create_full(self):
        """Should create with all fields."""
        point = VectorPoint(
            id="p1",
            dense_vector=[0.1, 0.2],
            sparse_vector={1: 0.5, 2: 0.3},
            payload={"kb_id": "kb1", "document_id": "doc1"},
        )
        assert point.sparse_vector == {1: 0.5, 2: 0.3}
        assert point.payload["kb_id"] == "kb1"


@pytest.mark.unit
class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_create(self):
        """Should create with all fields."""
        result = SearchResult(id="p1", score=0.95, payload={"key": "value"})
        assert result.id == "p1"
        assert result.score == 0.95
        assert result.payload == {"key": "value"}

    def test_default_payload(self):
        """Should default to empty payload."""
        result = SearchResult(id="p1", score=0.5)
        assert result.payload == {}


@pytest.mark.unit
class TestVectorStoreABC:
    """Tests for VectorStore abstract base class."""

    def test_cannot_instantiate_abc(self):
        """Should not be able to instantiate the ABC directly."""
        with pytest.raises(TypeError):
            VectorStore()

    def test_incomplete_subclass(self):
        """Incomplete subclass should raise TypeError."""
        class IncompleteStore(VectorStore):
            async def ensure_collection(self):
                pass

        with pytest.raises(TypeError):
            IncompleteStore()

    def test_in_memory_store_is_valid(self):
        """InMemoryVectorStore should be a valid VectorStore."""
        store = InMemoryVectorStore()
        assert isinstance(store, VectorStore)


@pytest.mark.unit
class TestInMemoryVectorStore:
    """Tests for the InMemoryVectorStore test helper."""

    @pytest.mark.asyncio
    async def test_ensure_collection(self):
        """Should mark collection as created."""
        store = InMemoryVectorStore()
        assert not store._collection_created
        await store.ensure_collection()
        assert store._collection_created

    @pytest.mark.asyncio
    async def test_upsert_and_count(self):
        """Should store points."""
        store = InMemoryVectorStore()
        points = [
            VectorPoint(id="p1", dense_vector=[1.0, 0.0]),
            VectorPoint(id="p2", dense_vector=[0.0, 1.0]),
        ]
        await store.upsert(points)
        assert len(store._points) == 2

    @pytest.mark.asyncio
    async def test_upsert_overwrites(self):
        """Upserting same ID should overwrite."""
        store = InMemoryVectorStore()
        await store.upsert([VectorPoint(id="p1", dense_vector=[1.0, 0.0], payload={"v": 1})])
        await store.upsert([VectorPoint(id="p1", dense_vector=[0.0, 1.0], payload={"v": 2})])
        assert len(store._points) == 1
        assert store._points["p1"].payload["v"] == 2

    @pytest.mark.asyncio
    async def test_delete(self):
        """Should remove points by ID."""
        store = InMemoryVectorStore()
        await store.upsert([
            VectorPoint(id="p1", dense_vector=[1.0, 0.0]),
            VectorPoint(id="p2", dense_vector=[0.0, 1.0]),
        ])
        await store.delete(["p1"])
        assert len(store._points) == 1
        assert "p2" in store._points

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        """Deleting non-existent ID should not raise."""
        store = InMemoryVectorStore()
        await store.delete(["nonexistent"])

    @pytest.mark.asyncio
    async def test_search_dense_returns_sorted(self):
        """Dense search should return results sorted by score descending."""
        store = InMemoryVectorStore()
        await store.upsert([
            VectorPoint(id="p1", dense_vector=[1.0, 0.0]),
            VectorPoint(id="p2", dense_vector=[0.7, 0.7]),
            VectorPoint(id="p3", dense_vector=[0.0, 1.0]),
        ])

        results = await store.search_dense([1.0, 0.0], limit=3)
        assert len(results) == 3
        assert results[0].id == "p1"  # Most similar to [1, 0]
        # Scores should be descending
        assert results[0].score >= results[1].score >= results[2].score

    @pytest.mark.asyncio
    async def test_search_dense_with_limit(self):
        """Should respect limit parameter."""
        store = InMemoryVectorStore()
        for i in range(10):
            await store.upsert([VectorPoint(id=f"p{i}", dense_vector=[float(i), 1.0])])

        results = await store.search_dense([5.0, 1.0], limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_search_dense_with_filter(self):
        """Should filter results by payload."""
        store = InMemoryVectorStore()
        await store.upsert([
            VectorPoint(id="p1", dense_vector=[1.0, 0.0], payload={"kb_id": "kb1"}),
            VectorPoint(id="p2", dense_vector=[0.9, 0.1], payload={"kb_id": "kb2"}),
            VectorPoint(id="p3", dense_vector=[0.8, 0.2], payload={"kb_id": "kb1"}),
        ])

        results = await store.search_dense([1.0, 0.0], limit=10, filters={"kb_id": "kb1"})
        assert len(results) == 2
        assert all(r.payload["kb_id"] == "kb1" for r in results)

    @pytest.mark.asyncio
    async def test_search_sparse(self):
        """Sparse search should use dot product scoring."""
        store = InMemoryVectorStore()
        await store.upsert([
            VectorPoint(id="p1", dense_vector=[], sparse_vector={1: 1.0, 2: 0.5}),
            VectorPoint(id="p2", dense_vector=[], sparse_vector={1: 0.1, 3: 0.9}),
        ])

        results = await store.search_sparse({1: 1.0, 2: 1.0}, limit=2)
        assert len(results) == 2
        # p1 should score higher: 1*1 + 0.5*1 = 1.5 vs p2: 0.1*1 = 0.1
        assert results[0].id == "p1"

    @pytest.mark.asyncio
    async def test_search_sparse_empty_query(self):
        """Empty sparse query should return empty results."""
        store = InMemoryVectorStore()
        await store.upsert([VectorPoint(id="p1", dense_vector=[], sparse_vector={1: 1.0})])
        results = await store.search_sparse({}, limit=10)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_sparse_with_filter(self):
        """Sparse search should respect filters."""
        store = InMemoryVectorStore()
        await store.upsert([
            VectorPoint(id="p1", dense_vector=[], sparse_vector={1: 1.0}, payload={"type": "manual"}),
            VectorPoint(id="p2", dense_vector=[], sparse_vector={1: 0.5}, payload={"type": "faq"}),
        ])

        results = await store.search_sparse({1: 1.0}, limit=10, filters={"type": "faq"})
        assert len(results) == 1
        assert results[0].id == "p2"

    @pytest.mark.asyncio
    async def test_search_empty_store(self):
        """Searching empty store should return empty results."""
        store = InMemoryVectorStore()
        results = await store.search_dense([1.0, 0.0], limit=10)
        assert results == []


@pytest.mark.unit
class TestQdrantVectorStoreStructure:
    """Tests for QdrantVectorStore class structure (no real Qdrant connection)."""

    def test_qdrant_store_instantiation(self):
        """QdrantVectorStore should be instantiable."""
        from app.rag.vector_store.qdrant import QdrantVectorStore
        store = QdrantVectorStore(
            url="http://localhost:6333",
            collection_name="test_collection",
            dense_dim=1024,
        )
        assert isinstance(store, VectorStore)

    def test_qdrant_store_with_api_key(self):
        """Should accept optional API key."""
        from app.rag.vector_store.qdrant import QdrantVectorStore
        store = QdrantVectorStore(
            url="http://localhost:6333",
            collection_name="test",
            api_key="test-key",
        )
        assert store._collection_name == "test"
