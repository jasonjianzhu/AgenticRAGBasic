"""Tests for EmbeddingProvider interface and EmbeddingResult (S7-01, S7-02).

Uses an InMemoryEmbeddingProvider for unit testing without real TEI.
"""
from __future__ import annotations

import random

import pytest

from app.common.rag.embedding.base import EmbeddingProvider, EmbeddingResult


# --- In-memory implementation for testing ---

class InMemoryEmbeddingProvider(EmbeddingProvider):
    """In-memory embedding provider that returns deterministic random vectors.

    Useful for unit testing without a real TEI server.
    """

    def __init__(self, dim: int = 1024, seed: int = 42) -> None:
        self._dim = dim
        self._seed = seed

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        results = []
        for i, text in enumerate(texts):
            rng = random.Random(hash(text) + self._seed)
            dense = [rng.gauss(0, 1) for _ in range(self._dim)]
            # Generate sparse vector: a few non-zero entries
            sparse = {rng.randint(0, 30000): rng.random() for _ in range(10)}
            results.append(EmbeddingResult(dense=dense, sparse=sparse))
        return results

    async def embed_query(self, query: str) -> EmbeddingResult:
        results = await self.embed_texts([query])
        return results[0]


@pytest.mark.unit
class TestEmbeddingResult:
    """Tests for EmbeddingResult dataclass."""

    def test_create_with_dense_only(self):
        """Should create with dense vector and empty sparse."""
        result = EmbeddingResult(dense=[0.1, 0.2, 0.3])
        assert result.dense == [0.1, 0.2, 0.3]
        assert result.sparse == {}

    def test_create_with_dense_and_sparse(self):
        """Should create with both dense and sparse vectors."""
        sparse = {100: 0.5, 200: 0.3}
        result = EmbeddingResult(dense=[0.1, 0.2], sparse=sparse)
        assert result.dense == [0.1, 0.2]
        assert result.sparse == {100: 0.5, 200: 0.3}

    def test_dense_vector_is_list_of_floats(self):
        """Dense vector should be a list of floats."""
        result = EmbeddingResult(dense=[1.0, 2.0, 3.0])
        assert all(isinstance(v, float) for v in result.dense)

    def test_sparse_vector_is_dict(self):
        """Sparse vector should be a dict of int -> float."""
        sparse = {1: 0.5, 2: 0.3, 3: 0.1}
        result = EmbeddingResult(dense=[], sparse=sparse)
        assert isinstance(result.sparse, dict)

    def test_empty_vectors(self):
        """Should handle empty vectors."""
        result = EmbeddingResult(dense=[], sparse={})
        assert result.dense == []
        assert result.sparse == {}


@pytest.mark.unit
class TestEmbeddingProviderABC:
    """Tests for EmbeddingProvider abstract base class."""

    def test_cannot_instantiate_abc(self):
        """Should not be able to instantiate the ABC directly."""
        with pytest.raises(TypeError):
            EmbeddingProvider()

    def test_concrete_subclass_must_implement_all(self):
        """Incomplete subclass should raise TypeError."""
        class IncompleteProvider(EmbeddingProvider):
            async def embed_texts(self, texts):
                return []

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_in_memory_provider_is_valid(self):
        """InMemoryEmbeddingProvider should be a valid EmbeddingProvider."""
        provider = InMemoryEmbeddingProvider()
        assert isinstance(provider, EmbeddingProvider)


@pytest.mark.unit
class TestInMemoryEmbeddingProvider:
    """Tests for the InMemoryEmbeddingProvider test helper."""

    @pytest.mark.asyncio
    async def test_embed_texts_returns_correct_count(self):
        """Should return one result per input text."""
        provider = InMemoryEmbeddingProvider(dim=128)
        results = await provider.embed_texts(["hello", "world", "test"])
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_embed_texts_dense_dimension(self):
        """Dense vectors should have the configured dimension."""
        provider = InMemoryEmbeddingProvider(dim=1024)
        results = await provider.embed_texts(["test text"])
        assert len(results[0].dense) == 1024

    @pytest.mark.asyncio
    async def test_embed_texts_sparse_non_empty(self):
        """Sparse vectors should have some entries."""
        provider = InMemoryEmbeddingProvider(dim=128)
        results = await provider.embed_texts(["test text"])
        assert len(results[0].sparse) > 0

    @pytest.mark.asyncio
    async def test_embed_query_returns_single_result(self):
        """embed_query should return a single EmbeddingResult."""
        provider = InMemoryEmbeddingProvider(dim=128)
        result = await provider.embed_query("test query")
        assert isinstance(result, EmbeddingResult)
        assert len(result.dense) == 128

    @pytest.mark.asyncio
    async def test_deterministic_for_same_input(self):
        """Same input should produce same output (deterministic)."""
        provider = InMemoryEmbeddingProvider(dim=64, seed=42)
        r1 = await provider.embed_texts(["hello"])
        r2 = await provider.embed_texts(["hello"])
        assert r1[0].dense == r2[0].dense

    @pytest.mark.asyncio
    async def test_different_inputs_different_vectors(self):
        """Different inputs should produce different vectors."""
        provider = InMemoryEmbeddingProvider(dim=64)
        results = await provider.embed_texts(["hello", "world"])
        assert results[0].dense != results[1].dense

    @pytest.mark.asyncio
    async def test_dimension_property(self):
        """dimension property should return configured dim."""
        provider = InMemoryEmbeddingProvider(dim=512)
        assert provider.dimension == 512

    @pytest.mark.asyncio
    async def test_empty_input(self):
        """Should handle empty input list."""
        provider = InMemoryEmbeddingProvider(dim=64)
        results = await provider.embed_texts([])
        assert results == []

    @pytest.mark.asyncio
    async def test_batch_embedding(self):
        """Should handle large batches."""
        provider = InMemoryEmbeddingProvider(dim=64)
        texts = [f"text {i}" for i in range(100)]
        results = await provider.embed_texts(texts)
        assert len(results) == 100


@pytest.mark.unit
class TestTEIEmbeddingProviderStructure:
    """Tests for TEIEmbeddingProvider class structure (no real HTTP calls)."""

    def test_tei_provider_instantiation(self):
        """TEIEmbeddingProvider should be instantiable."""
        from app.common.rag.embedding.tei import TEIEmbeddingProvider
        provider = TEIEmbeddingProvider(
            base_url="http://localhost:8080",
            batch_size=32,
            dim=1024,
        )
        assert isinstance(provider, EmbeddingProvider)
        assert provider.dimension == 1024

    def test_tei_provider_with_api_key(self):
        """Should accept optional API key."""
        from app.common.rag.embedding.tei import TEIEmbeddingProvider
        provider = TEIEmbeddingProvider(
            base_url="http://localhost:8080",
            api_key="test-key",
        )
        headers = provider._headers()
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test-key"

    def test_tei_provider_without_api_key(self):
        """Should work without API key."""
        from app.common.rag.embedding.tei import TEIEmbeddingProvider
        provider = TEIEmbeddingProvider(base_url="http://localhost:8080")
        headers = provider._headers()
        assert "Authorization" not in headers
