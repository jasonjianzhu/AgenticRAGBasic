from __future__ import annotations

import math
from typing import Any

from app.rag.vector_store.base import SearchResult, SparseVector, VectorPoint


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._collections: dict[str, dict[str, VectorPoint]] = {}

    def upsert(self, collection_name: str, points: list[VectorPoint]) -> None:
        collection = self._collections.setdefault(collection_name, {})
        for point in points:
            collection[point.id] = point

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        collection = self._collections.get(collection_name, {})
        results: list[SearchResult] = []
        for point in collection.values():
            if filters and not _matches_filters(point.payload, filters):
                continue
            score = _cosine_similarity(query_vector, point.vector)
            results.append(SearchResult(id=point.id, score=score, payload=point.payload))
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    def sparse_search(
        self,
        collection_name: str,
        sparse_vector: SparseVector,
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        if not sparse_vector.indices or not sparse_vector.values:
            return []

        collection = self._collections.get(collection_name, {})
        query_weights = dict(zip(sparse_vector.indices, sparse_vector.values, strict=False))
        results: list[SearchResult] = []
        for point in collection.values():
            if filters and not _matches_filters(point.payload, filters):
                continue
            if point.sparse_vector is None:
                continue
            score = _sparse_dot_product(query_weights, point.sparse_vector)
            if score <= 0.0:
                continue
            results.append(SearchResult(id=point.id, score=score, payload=point.payload))
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    def delete_by_payload(self, collection_name: str, filters: dict[str, Any]) -> None:
        collection = self._collections.get(collection_name, {})
        point_ids = [point_id for point_id, point in collection.items() if _matches_filters(point.payload, filters)]
        for point_id in point_ids:
            collection.pop(point_id, None)


def _matches_filters(payload: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, value in filters.items():
        if payload.get(key) != value:
            return False
    return True


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _sparse_dot_product(query_weights: dict[int, float], sparse_vector: SparseVector) -> float:
    score = 0.0
    for index, value in zip(sparse_vector.indices, sparse_vector.values, strict=False):
        score += query_weights.get(index, 0.0) * value
    return score
