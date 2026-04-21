from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from qdrant_client.http import models

from app.rag.vector_store.base import SearchResult, SparseVector, VectorPoint


class DistanceMetric(StrEnum):
    COSINE = "cosine"
    DOT = "dot"
    EUCLID = "euclid"


@dataclass(frozen=True)
class CollectionConfig:
    name: str
    vector_size: int
    distance: str = DistanceMetric.COSINE
    dense_vector_name: str = "dense"
    sparse_vector_name: str = "sparse"


@dataclass(frozen=True)
class CollectionEnsureResult:
    name: str
    created: bool
    payload_indexes_created: list[str]


class QdrantCollectionManager:
    PAYLOAD_INDEX_FIELDS: dict[str, models.PayloadSchemaType] = {
        "knowledge_base_id": models.PayloadSchemaType.KEYWORD,
        "document_id": models.PayloadSchemaType.KEYWORD,
        "chunk_id": models.PayloadSchemaType.KEYWORD,
        "chunk_type": models.PayloadSchemaType.KEYWORD,
        "language": models.PayloadSchemaType.KEYWORD,
        "product_model": models.PayloadSchemaType.KEYWORD,
        "document_type": models.PayloadSchemaType.KEYWORD,
        "document_status": models.PayloadSchemaType.KEYWORD,
        "is_enabled": models.PayloadSchemaType.BOOL,
    }

    def __init__(self, client):
        self.client = client

    def ensure_collection(self, config: CollectionConfig) -> CollectionEnsureResult:
        created = False
        if not self.client.collection_exists(config.name):
            self.client.create_collection(
                collection_name=config.name,
                vectors_config={
                    config.dense_vector_name: models.VectorParams(
                        size=config.vector_size,
                        distance=models.Distance(str(config.distance).capitalize()),
                    ),
                },
                sparse_vectors_config={
                    config.sparse_vector_name: models.SparseVectorParams(
                        index=models.SparseIndexParams(),
                    )
                },
            )
            created = True

        payload_indexes_created: list[str] = []
        existing_indexes = set(self._get_existing_payload_indexes(config.name))
        for field_name, field_schema in self.PAYLOAD_INDEX_FIELDS.items():
            if field_name in existing_indexes:
                continue
            self.client.create_payload_index(
                collection_name=config.name,
                field_name=field_name,
                field_schema=field_schema,
            )
            payload_indexes_created.append(field_name)

        return CollectionEnsureResult(
            name=config.name,
            created=created,
            payload_indexes_created=payload_indexes_created,
        )

    def _get_existing_payload_indexes(self, collection_name: str) -> list[str]:
        get_collection = getattr(self.client, "get_collection", None)
        if get_collection is None:
            return []
        details = get_collection(collection_name)
        payload_schema = getattr(details, "payload_schema", None)
        if isinstance(payload_schema, dict):
            return list(payload_schema.keys())
        return []


class QdrantVectorStore:
    def __init__(
        self,
        client,
        *,
        collection_name: str,
        vector_size: int,
        dense_vector_name: str = "dense",
        sparse_vector_name: str = "sparse",
        distance: str = DistanceMetric.COSINE,
    ) -> None:
        self.client = client
        self.collection_name = collection_name
        self.dense_vector_name = dense_vector_name
        self.sparse_vector_name = sparse_vector_name
        self.collection_manager = QdrantCollectionManager(client)
        self.collection_manager.ensure_collection(
            CollectionConfig(
                name=collection_name,
                vector_size=vector_size,
                distance=distance,
                dense_vector_name=dense_vector_name,
                sparse_vector_name=sparse_vector_name,
            )
        )

    def upsert(self, collection_name: str, points: list[VectorPoint]) -> None:
        assert collection_name == self.collection_name
        point_structs = []
        for point in points:
            vector_payload: dict[str, Any] = {self.dense_vector_name: point.vector}
            if point.sparse_vector is not None:
                vector_payload[self.sparse_vector_name] = models.SparseVector(
                    indices=point.sparse_vector.indices,
                    values=point.sparse_vector.values,
                )
            point_structs.append(
                models.PointStruct(
                    id=point.id,
                    vector=vector_payload,
                    payload=point.payload,
                )
            )
        self.client.upsert(collection_name=collection_name, points=point_structs, wait=True)

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        assert collection_name == self.collection_name
        hits = self.client.query_points(
            collection_name=collection_name,
            using=self.dense_vector_name,
            query=query_vector,
            limit=limit,
            query_filter=_to_qdrant_filter(filters),
            with_payload=True,
        ).points
        return [_to_search_result(hit) for hit in hits]

    def sparse_search(
        self,
        collection_name: str,
        sparse_vector: SparseVector,
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        assert collection_name == self.collection_name
        hits = self.client.query_points(
            collection_name=collection_name,
            using=self.sparse_vector_name,
            query=models.SparseVector(
                indices=sparse_vector.indices,
                values=sparse_vector.values,
            ),
            limit=limit,
            query_filter=_to_qdrant_filter(filters),
            with_payload=True,
        ).points
        return [_to_search_result(hit) for hit in hits]

    def delete_by_payload(self, collection_name: str, filters: dict[str, Any]) -> None:
        assert collection_name == self.collection_name
        self.client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(filter=_to_qdrant_filter(filters)),
            wait=True,
        )


def _to_search_result(hit) -> SearchResult:
    return SearchResult(
        id=str(getattr(hit, "id", "")),
        score=float(getattr(hit, "score", 0.0)),
        payload=dict(getattr(hit, "payload", {}) or {}),
    )


def _to_qdrant_filter(filters: dict[str, Any] | None) -> models.Filter | None:
    if not filters:
        return None
    return models.Filter(
        must=[
            models.FieldCondition(
                key=key,
                match=models.MatchValue(value=value),
            )
            for key, value in filters.items()
        ]
    )
