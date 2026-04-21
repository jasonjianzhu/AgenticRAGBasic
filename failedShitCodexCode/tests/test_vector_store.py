from __future__ import annotations

import uuid

from qdrant_client import QdrantClient

from app.rag.vector_store.base import SparseVector, VectorPoint
from app.rag.vector_store.qdrant import CollectionConfig, QdrantCollectionManager, QdrantVectorStore


class FakeCollectionsApi:
    def __init__(self) -> None:
        self.collections: set[str] = set()
        self.created: list[tuple[str, object]] = []
        self.payload_indexes: list[tuple[str, str, str]] = []
        self.points: dict[str, dict[str, dict]] = {}
        self.deleted_filters: list[tuple[str, object]] = []

    def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def create_collection(self, collection_name: str, vectors_config, sparse_vectors_config=None) -> None:
        self.collections.add(collection_name)
        self.points.setdefault(collection_name, {})
        self.created.append((collection_name, vectors_config))

    def create_payload_index(self, collection_name: str, field_name: str, field_schema: str) -> None:
        self.payload_indexes.append((collection_name, field_name, field_schema))

    def get_collection(self, collection_name: str):
        class Details:
            payload_schema = {}

        return Details()

    def upsert(self, collection_name: str, points, wait: bool = True) -> None:
        collection = self.points.setdefault(collection_name, {})
        for point in points:
            point_id = str(getattr(point, "id", None) or point["id"])
            collection[point_id] = point

    def query_points(self, collection_name: str, using: str, query, limit: int, query_filter=None, with_payload: bool = True):
        collection = self.points.get(collection_name, {})
        must = self._extract_must_conditions(query_filter)
        hits = []
        for point_id, point in collection.items():
            payload = self._extract_payload(point)
            if any(payload.get(key) != value for key, value in must):
                continue
            score = 0.0
            if using == "dense":
                score = 1.0 if payload.get("chunk_id") == "dense-best" else 0.2
            else:
                score = 1.0 if payload.get("chunk_id") == "sparse-best" else 0.1
            hits.append(type("Hit", (), {"id": point_id, "score": score, "payload": payload})())
        hits.sort(key=lambda item: item.score, reverse=True)
        return type("Response", (), {"points": hits[:limit]})()

    def delete(self, collection_name: str, points_selector, wait: bool = True) -> None:
        self.deleted_filters.append((collection_name, points_selector))

    @staticmethod
    def _extract_payload(point) -> dict:
        if isinstance(point, dict):
            return point["payload"]
        return point.payload

    @staticmethod
    def _extract_must_conditions(query_filter) -> list[tuple[str, object]]:
        if query_filter is None:
            return []
        raw_must = getattr(query_filter, "must", None)
        if raw_must is None and isinstance(query_filter, dict):
            raw_must = query_filter.get("must", [])
        conditions = []
        for condition in raw_must or []:
            if isinstance(condition, dict):
                conditions.append((condition["key"], condition["match"]["value"]))
                continue
            conditions.append((condition.key, condition.match.value))
        return conditions


def test_qdrant_collection_manager_creates_collection_when_missing() -> None:
    client = FakeCollectionsApi()
    manager = QdrantCollectionManager(client=client)

    result = manager.ensure_collection(
        CollectionConfig(
            name="agenticrag_chunks",
            vector_size=384,
            distance="cosine",
        )
    )

    assert result.created is True
    assert result.name == "agenticrag_chunks"
    assert result.payload_indexes_created
    assert len(client.created) == 1
    assert {field for _, field, _ in client.payload_indexes} >= {
        "knowledge_base_id",
        "document_id",
        "chunk_id",
        "chunk_type",
        "language",
        "document_type",
        "document_status",
        "is_enabled",
    }


def test_qdrant_collection_manager_skips_existing_collection() -> None:
    client = FakeCollectionsApi()
    client.collections.add("agenticrag_chunks")
    manager = QdrantCollectionManager(client=client)

    result = manager.ensure_collection(
        CollectionConfig(
            name="agenticrag_chunks",
            vector_size=384,
            distance="cosine",
        )
    )

    assert result.created is False
    assert len(client.created) == 0
    assert result.payload_indexes_created


def test_qdrant_vector_store_upsert_search_and_delete_by_payload() -> None:
    client = FakeCollectionsApi()
    store = QdrantVectorStore(
        client=client,
        collection_name="agenticrag_chunks",
        vector_size=8,
    )

    store.upsert(
        "agenticrag_chunks",
        [
            VectorPoint(
                    id=str(uuid.uuid4()),
                vector=[0.1] * 8,
                sparse_vector=SparseVector(indices=[1, 5], values=[0.8, 0.4]),
                payload={
                    "chunk_id": "dense-best",
                    "document_id": "doc-1",
                    "document_status": "ready",
                    "is_enabled": True,
                },
            ),
            VectorPoint(
                    id=str(uuid.uuid4()),
                vector=[0.2] * 8,
                sparse_vector=SparseVector(indices=[2, 6], values=[0.7, 0.3]),
                payload={
                    "chunk_id": "sparse-best",
                    "document_id": "doc-2",
                    "document_status": "ready",
                    "is_enabled": True,
                },
            ),
        ],
    )

    dense_hits = store.search(
        "agenticrag_chunks",
        query_vector=[0.1] * 8,
        limit=2,
        filters={"document_status": "ready", "is_enabled": True},
    )
    sparse_hits = store.sparse_search(
        "agenticrag_chunks",
        sparse_vector=SparseVector(indices=[2, 6], values=[0.7, 0.3]),
        limit=2,
        filters={"document_status": "ready", "is_enabled": True},
    )
    store.delete_by_payload("agenticrag_chunks", {"document_id": "doc-1"})

    assert dense_hits[0].payload["chunk_id"] == "dense-best"
    assert sparse_hits[0].payload["chunk_id"] == "sparse-best"
    assert client.deleted_filters


def test_qdrant_vector_store_supports_real_qdrant_client_in_memory() -> None:
    client = QdrantClient(location=":memory:")
    store = QdrantVectorStore(
        client=client,
        collection_name="agenticrag_chunks",
        vector_size=8,
    )

    store.upsert(
        "agenticrag_chunks",
        [
            VectorPoint(
                id=str(uuid.uuid4()),
                vector=[0.1] * 8,
                sparse_vector=SparseVector(indices=[1, 5], values=[0.8, 0.4]),
                payload={
                    "chunk_id": "dense-best",
                    "document_id": "doc-1",
                    "document_status": "ready",
                    "is_enabled": True,
                },
            )
        ],
    )

    dense_hits = store.search(
        "agenticrag_chunks",
        query_vector=[0.1] * 8,
        limit=2,
        filters={"document_status": "ready", "is_enabled": True},
    )
    sparse_hits = store.sparse_search(
        "agenticrag_chunks",
        sparse_vector=SparseVector(indices=[1, 5], values=[0.8, 0.4]),
        limit=2,
        filters={"document_status": "ready", "is_enabled": True},
    )

    assert dense_hits
    assert sparse_hits
