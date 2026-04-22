"""Indexing service — batch embed chunks and write to vector store.

Handles the chunked → indexing → ready/failed document status flow.
Designed for synchronous execution inside an RQ worker.
"""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.core.config import Settings, get_settings
from app.common.core.logging import get_logger
from app.common.db.models import Chunk, Document
from app.common.rag.embedding.base import EmbeddingProvider, EmbeddingResult
from app.common.rag.vector_store.base import VectorPoint, VectorStore

logger = get_logger(__name__)


class IndexingServiceError(Exception):
    """Raised when the indexing service encounters an error."""


class IndexingService:
    """Batch embed chunks and write to vector store.

    Processes chunks in batches:
    - Embedding: 32 chunks per batch (configurable)
    - Qdrant write: 100 points per batch (configurable)

    Args:
        session: Synchronous SQLAlchemy session.
        settings: Application settings.
        embedding_provider: Optional embedding provider (created from settings if None).
        vector_store: Optional vector store (created from settings if None).
    """

    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    @property
    def embedding_provider(self) -> EmbeddingProvider:
        if self._embedding_provider is None:
            from app.common.rag.embedding import create_embedding_provider
            self._embedding_provider = create_embedding_provider()
        return self._embedding_provider

    @property
    def vector_store(self) -> VectorStore:
        if self._vector_store is None:
            from app.common.rag.vector_store.qdrant import QdrantVectorStore
            self._vector_store = QdrantVectorStore(
                url=self.settings.qdrant_url,
                collection_name=self.settings.qdrant_collection_name,
                api_key=self.settings.qdrant_api_key,
                dense_dim=self.settings.embedding_dimension,
            )
        return self._vector_store

    def run(self, document_id: uuid.UUID) -> None:
        """Execute indexing for a document (synchronous, called by worker).

        Steps:
        1. Load chunks for the document from DB
        2. Update document status to "indexing"
        3. Batch embed via embedding provider
        4. Batch write to vector store
        5. Update chunk.qdrant_point_id
        6. Update document status to "ready"
        """
        doc = self.session.get(Document, document_id)
        if doc is None:
            raise IndexingServiceError(f"Document {document_id} not found")

        try:
            # 1. Load chunks
            chunks = self._load_chunks(document_id)
            if not chunks:
                logger.warning("no_chunks_to_index", document_id=str(document_id))
                doc.status = "ready"
                self.session.flush()
                return

            # 2. Update status to indexing
            doc.status = "indexing"
            self.session.flush()

            # 3 & 4. Batch embed and write
            loop = _get_or_create_event_loop()
            loop.run_until_complete(self._embed_and_write(doc, chunks))

            # 6. Update status to ready
            doc.status = "ready"
            self.session.flush()

            logger.info(
                "indexing_complete",
                document_id=str(document_id),
                chunk_count=len(chunks),
            )

        except Exception as e:
            doc.status = "failed"
            self.session.flush()
            logger.exception(
                "indexing_failed",
                document_id=str(document_id),
                error=str(e),
            )
            raise IndexingServiceError(
                f"Indexing failed for document {document_id}: {e}"
            ) from e

    def _load_chunks(self, document_id: uuid.UUID) -> list[Chunk]:
        """Load all chunks for a document."""
        stmt = (
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.ordinal.asc())
        )
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    async def _embed_and_write(self, doc: Document, chunks: list[Chunk]) -> None:
        """Batch embed chunks and write to vector store."""
        # Ensure collection exists
        await self.vector_store.ensure_collection()

        embed_batch_size = self.settings.embedding_batch_size
        write_batch_size = self.settings.qdrant_write_batch_size

        # Batch embed
        all_embeddings: list[EmbeddingResult] = []
        texts = [c.content for c in chunks]

        for i in range(0, len(texts), embed_batch_size):
            batch = texts[i : i + embed_batch_size]
            batch_results = await self.embedding_provider.embed_texts(batch)
            all_embeddings.extend(batch_results)

        # Build vector points
        points: list[VectorPoint] = []
        for chunk, embedding in zip(chunks, all_embeddings):
            point_id = str(uuid.uuid4())
            point = VectorPoint(
                id=point_id,
                dense_vector=embedding.dense,
                sparse_vector=embedding.sparse,
                payload={
                    "kb_id": str(doc.knowledge_base_id),
                    "document_id": str(doc.id),
                    "chunk_id": str(chunk.id),
                    "document_type": doc.document_type,
                    "language": chunk.language,
                    "product_model": chunk.product_model,
                    "is_enabled": doc.is_enabled,
                    "status": doc.status,
                },
            )
            points.append(point)

            # 5. Update chunk.qdrant_point_id
            chunk.qdrant_point_id = point_id

        self.session.flush()

        # Batch write to vector store
        for i in range(0, len(points), write_batch_size):
            batch = points[i : i + write_batch_size]
            await self.vector_store.upsert(batch)

        logger.info(
            "vectors_written",
            document_id=str(doc.id),
            point_count=len(points),
        )


def _get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """Get the current event loop or create a new one for sync contexts."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
