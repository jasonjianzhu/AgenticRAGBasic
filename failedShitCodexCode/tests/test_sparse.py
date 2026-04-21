from __future__ import annotations

from app.rag.retrieval.sparse import build_sparse_vector


def test_build_sparse_vector_returns_unique_sorted_indices(monkeypatch) -> None:
    monkeypatch.setattr("app.rag.retrieval.sparse.tokenize_for_search", lambda text: ["alpha", "beta", "gamma"])
    monkeypatch.setattr("builtins.hash", lambda token: {"alpha": 1, "beta": 5, "gamma": 9}[token])

    vector = build_sparse_vector("ignored", vector_size=4)

    assert vector.indices == [1]
    assert len(vector.values) == 1
