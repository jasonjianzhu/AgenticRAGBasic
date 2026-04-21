from __future__ import annotations

import httpx
import pytest
import respx

from app.rag.embedding.tei import TEIEmbeddingProvider
from tests.fakes import DeterministicEmbeddingProvider


def test_deterministic_embedding_provider_returns_fixed_dimension_vectors() -> None:
    provider = DeterministicEmbeddingProvider(dimension=8)

    vector = provider.embed_query("battery alarm")
    vectors = provider.embed_documents(["battery alarm", "pcs manual"])

    assert len(vector) == 8
    assert len(vectors) == 2
    assert all(len(item) == 8 for item in vectors)


def test_deterministic_embedding_provider_is_repeatable() -> None:
    provider = DeterministicEmbeddingProvider(dimension=6)

    first = provider.embed_query("E101 overheat")
    second = provider.embed_query("E101 overheat")

    assert first == second


@respx.mock
def test_tei_embedding_provider_calls_openai_compatible_embeddings_api() -> None:
    route = respx.post("http://127.0.0.1:8080/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"embedding": [0.1, 0.2, 0.3]},
                    {"embedding": [0.4, 0.5, 0.6]},
                ]
            },
        )
    )
    provider = TEIEmbeddingProvider(
        base_url="http://127.0.0.1:8080",
        model_name="BAAI/bge-small-en-v1.5",
        dimension=3,
    )

    vectors = provider.embed_documents(["battery alarm", "pcs manual"])

    assert route.called
    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


@respx.mock
def test_tei_embedding_provider_batches_requests() -> None:
    route = respx.post("http://127.0.0.1:8080/v1/embeddings").mock(
        side_effect=[
            httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]}),
            httpx.Response(200, json={"data": [{"embedding": [0.5, 0.6]}]}),
        ]
    )
    provider = TEIEmbeddingProvider(
        base_url="http://127.0.0.1:8080",
        model_name="BAAI/bge-small-en-v1.5",
        dimension=2,
        batch_size=2,
    )

    vectors = provider.embed_documents(["battery alarm", "pcs manual", "fault code"])

    assert route.call_count == 2
    assert vectors == [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]


@respx.mock
def test_tei_embedding_provider_raises_for_bad_response() -> None:
    respx.post("http://127.0.0.1:8080/v1/embeddings").mock(return_value=httpx.Response(500, json={"error": "boom"}))
    provider = TEIEmbeddingProvider(
        base_url="http://127.0.0.1:8080",
        model_name="BAAI/bge-small-en-v1.5",
        dimension=3,
    )

    with pytest.raises(httpx.HTTPStatusError):
        provider.embed_query("battery alarm")
