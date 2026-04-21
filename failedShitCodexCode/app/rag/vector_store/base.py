from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class SparseVector:
    indices: list[int]
    values: list[float]


@dataclass(frozen=True)
class VectorPoint:
    id: str
    vector: list[float]
    sparse_vector: SparseVector | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchResult:
    id: str
    score: float
    payload: dict[str, Any]


class VectorStore(Protocol):
    def upsert(self, collection_name: str, points: list[VectorPoint]) -> None: ...

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]: ...

    def sparse_search(
        self,
        collection_name: str,
        sparse_vector: SparseVector,
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]: ...

    def delete_by_payload(self, collection_name: str, filters: dict[str, Any]) -> None: ...
