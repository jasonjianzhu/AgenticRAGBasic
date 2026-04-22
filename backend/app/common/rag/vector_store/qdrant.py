"""Qdrant vector store implementation."""
from __future__ import annotations

from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.common.core.logging import get_logger
from app.common.rag.vector_store.base import SearchResult, VectorPoint, VectorStore

logger = get_logger(__name__)

# Named vector keys
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


class QdrantVectorStore(VectorStore):
    """Qdrant-backed vector store with dense + sparse vector support.

    Args:
        url: Qdrant server URL.
        collection_name: Name of the Qdrant collection.
        api_key: Optional API key.
        dense_dim: Dense vector dimension (default 1024 for BGE-M3).
    """

    def __init__(
        self,
        url: str,
        collection_name: str,
        api_key: str | None = None,
        dense_dim: int = 1024,
    ) -> None:
        self._url = url
        self._collection_name = collection_name
        self._dense_dim = dense_dim
        self._client = AsyncQdrantClient(url=url, api_key=api_key)

    async def ensure_collection(self) -> None:
        """Create collection with dense (cosine) + sparse vector config."""
        collections = await self._client.get_collections()
        existing_names = [c.name for c in collections.collections]

        if self._collection_name in existing_names:
            logger.info("qdrant_collection_exists", collection=self._collection_name)
            return

        await self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config={
                DENSE_VECTOR_NAME: models.VectorParams(
                    size=self._dense_dim,
                    distance=models.Distance.COSINE,
                ),
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: models.SparseVectorParams(),
            },
        )

        # Create payload indexes for common filter fields
        for field_name in ["kb_id", "document_id", "document_type", "language", "is_enabled", "status"]:
            await self._client.create_payload_index(
                collection_name=self._collection_name,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

        logger.info(
            "qdrant_collection_created",
            collection=self._collection_name,
            dense_dim=self._dense_dim,
        )

    async def upsert(self, points: list[VectorPoint]) -> None:
        """Upsert points with dense + sparse vectors and payload."""
        if not points:
            return

        qdrant_points = []
        for p in points:
            vectors: dict[str, Any] = {
                DENSE_VECTOR_NAME: p.dense_vector,
            }
            if p.sparse_vector:
                indices = list(p.sparse_vector.keys())
                values = list(p.sparse_vector.values())
                vectors[SPARSE_VECTOR_NAME] = models.SparseVector(
                    indices=indices,
                    values=values,
                )

            qdrant_points.append(
                models.PointStruct(
                    id=p.id,
                    vector=vectors,
                    payload=p.payload,
                )
            )

        await self._client.upsert(
            collection_name=self._collection_name,
            points=qdrant_points,
        )

        logger.info("qdrant_upserted", count=len(points))

    async def delete(self, point_ids: list[str]) -> None:
        """Delete points by ID."""
        if not point_ids:
            return

        await self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.PointIdsList(points=point_ids),
        )

        logger.info("qdrant_deleted", count=len(point_ids))

    async def search_dense(
        self,
        vector: list[float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """Search using dense vector similarity."""
        query_filter = self._build_filter(filters) if filters else None

        results = await self._client.query_points(
            collection_name=self._collection_name,
            query=vector,
            using=DENSE_VECTOR_NAME,
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
        )

        return [
            SearchResult(
                id=str(hit.id),
                score=hit.score if hit.score is not None else 0.0,
                payload=hit.payload or {},
            )
            for hit in results.points
        ]

    async def search_sparse(
        self,
        sparse_vector: dict[int, float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """Search using sparse vector similarity."""
        if not sparse_vector:
            return []

        query_filter = self._build_filter(filters) if filters else None

        indices = list(sparse_vector.keys())
        values = list(sparse_vector.values())

        results = await self._client.query_points(
            collection_name=self._collection_name,
            query=models.SparseVector(indices=indices, values=values),
            using=SPARSE_VECTOR_NAME,
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
        )

        return [
            SearchResult(
                id=str(hit.id),
                score=hit.score if hit.score is not None else 0.0,
                payload=hit.payload or {},
            )
            for hit in results.points
        ]

    def _build_filter(self, filters: dict) -> models.Filter:
        """Build a Qdrant filter from a dict of field -> value conditions."""
        must_conditions: list[models.FieldCondition] = []
        for key, value in filters.items():
            if value is not None:
                must_conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value),
                    )
                )
        return models.Filter(must=must_conditions)

    async def close(self) -> None:
        """Close the Qdrant client connection."""
        await self._client.close()
