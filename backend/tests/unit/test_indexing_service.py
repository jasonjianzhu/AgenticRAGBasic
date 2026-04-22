"""Tests for IndexingService (S7-05, S7-06, S7-07).

Uses InMemoryEmbeddingProvider and InMemoryVectorStore for unit testing.
"""
from __future__ import annotations

import hashlib
import math
import random
import uuid

import pytest

from app.common.db.base import Base
from app.common.db.models import Chunk, Document, DocumentVersion, KnowledgeBase
from app.common.rag.embedding.base import EmbeddingProvider, EmbeddingResult
from app.common.rag.vector_store.base import SearchResult, VectorPoint, VectorStore
from app.knowledge.services.indexing import IndexingService, IndexingServiceError


# --- In-memory implementations ---

class InMemoryEmbeddingProvider(EmbeddingProvider):
    """In-memory embedding provider for testing."""

    def __init__(self, dim: int = 1024, seed: int = 42) -> None:
        self._dim = dim
        self._seed = seed
        self.call_count = 0
        self.texts_embedded: list[str] = []

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        self.call_count += 1
        self.texts_embedded.extend(texts)
        results = []
        for text in texts:
            rng = random.Random(hash(text) + self._seed)
            dense = [rng.gauss(0, 1) for _ in range(self._dim)]
            sparse = {rng.randint(0, 30000): rng.random() for _ in range(5)}
            results.append(EmbeddingResult(dense=dense, sparse=sparse))
        return results

    async def embed_query(self, query: str) -> EmbeddingResult:
        results = await self.embed_texts([query])
        return results[0]


class InMemoryVectorStore(VectorStore):
    """In-memory vector store for testing."""

    def __init__(self) -> None:
        self._points: dict[str, VectorPoint] = {}
        self.upsert_calls: list[list[VectorPoint]] = []
        self.delete_calls: list[list[str]] = []

    async def ensure_collection(self) -> None:
        pass

    async def upsert(self, points: list[VectorPoint]) -> None:
        self.upsert_calls.append(points)
        for p in points:
            self._points[p.id] = p

    async def delete(self, point_ids: list[str]) -> None:
        self.delete_calls.append(point_ids)
        for pid in point_ids:
            self._points.pop(pid, None)

    async def search_dense(self, vector, limit=10, filters=None):
        return []

    async def search_sparse(self, sparse_vector, limit=10, filters=None):
        return []


def _make_sync_session():
    """Create a sync SQLite session for testing."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///", echo=False)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory(), engine


def _setup_doc_with_chunks(session, num_chunks: int = 5):
    """Create a KB, document, version, and chunks in the sync session."""
    kb = KnowledgeBase(name=f"Test KB {uuid.uuid4().hex[:8]}", settings={})
    session.add(kb)
    session.flush()

    doc = Document(
        knowledge_base_id=kb.id,
        title="test.pdf",
        source_filename="test.pdf",
        storage_path=f"{kb.id}/test.pdf",
        content_hash="testhash",
        mime_type="application/pdf",
        file_size_bytes=1000,
        document_type="manual",
        status="chunked",
    )
    session.add(doc)
    session.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        parser_profile="balanced",
        status="chunked",
    )
    session.add(version)
    session.flush()

    for i in range(num_chunks):
        content = f"Chunk content {i} with some text for embedding"
        chunk = Chunk(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=version.id,
            ordinal=i,
            content=content,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            chunk_type="text",
            token_count=10,
        )
        session.add(chunk)

    session.flush()
    session.commit()
    return doc


@pytest.mark.unit
class TestIndexingService:
    """Tests for IndexingService.run()."""

    def test_run_success_updates_status_to_ready(self):
        """Successful indexing should set document status to 'ready'."""
        session, engine = _make_sync_session()
        try:
            doc = _setup_doc_with_chunks(session, num_chunks=3)
            embedding = InMemoryEmbeddingProvider(dim=64)
            vector_store = InMemoryVectorStore()

            from app.common.core.config import Settings
            settings = Settings(
                DATABASE_URL="sqlite+aiosqlite:///",
                DATABASE_URL_SYNC="sqlite:///",
                APP_ENV="testing",
                EMBEDDING_BATCH_SIZE=32,
                QDRANT_WRITE_BATCH_SIZE=100,
            )

            service = IndexingService(
                session=session,
                settings=settings,
                embedding_provider=embedding,
                vector_store=vector_store,
            )
            service.run(doc.id)

            session.refresh(doc)
            assert doc.status == "ready"
        finally:
            session.close()
            engine.dispose()

    def test_run_embeds_all_chunks(self):
        """Should embed all chunks."""
        session, engine = _make_sync_session()
        try:
            doc = _setup_doc_with_chunks(session, num_chunks=5)
            embedding = InMemoryEmbeddingProvider(dim=64)
            vector_store = InMemoryVectorStore()

            from app.common.core.config import Settings
            settings = Settings(
                DATABASE_URL="sqlite+aiosqlite:///",
                DATABASE_URL_SYNC="sqlite:///",
                APP_ENV="testing",
                EMBEDDING_BATCH_SIZE=32,
                QDRANT_WRITE_BATCH_SIZE=100,
            )

            service = IndexingService(
                session=session,
                settings=settings,
                embedding_provider=embedding,
                vector_store=vector_store,
            )
            service.run(doc.id)

            assert len(embedding.texts_embedded) == 5
        finally:
            session.close()
            engine.dispose()

    def test_run_writes_to_vector_store(self):
        """Should write points to vector store."""
        session, engine = _make_sync_session()
        try:
            doc = _setup_doc_with_chunks(session, num_chunks=3)
            embedding = InMemoryEmbeddingProvider(dim=64)
            vector_store = InMemoryVectorStore()

            from app.common.core.config import Settings
            settings = Settings(
                DATABASE_URL="sqlite+aiosqlite:///",
                DATABASE_URL_SYNC="sqlite:///",
                APP_ENV="testing",
                EMBEDDING_BATCH_SIZE=32,
                QDRANT_WRITE_BATCH_SIZE=100,
            )

            service = IndexingService(
                session=session,
                settings=settings,
                embedding_provider=embedding,
                vector_store=vector_store,
            )
            service.run(doc.id)

            # All points should be in the store
            assert len(vector_store._points) == 3
            # Verify payload structure
            for point in vector_store._points.values():
                assert "kb_id" in point.payload
                assert "document_id" in point.payload
                assert "chunk_id" in point.payload
                assert "document_type" in point.payload
        finally:
            session.close()
            engine.dispose()

    def test_run_updates_qdrant_point_ids(self):
        """Should update chunk.qdrant_point_id after writing."""
        session, engine = _make_sync_session()
        try:
            doc = _setup_doc_with_chunks(session, num_chunks=3)
            embedding = InMemoryEmbeddingProvider(dim=64)
            vector_store = InMemoryVectorStore()

            from sqlalchemy import select
            from app.common.core.config import Settings
            settings = Settings(
                DATABASE_URL="sqlite+aiosqlite:///",
                DATABASE_URL_SYNC="sqlite:///",
                APP_ENV="testing",
                EMBEDDING_BATCH_SIZE=32,
                QDRANT_WRITE_BATCH_SIZE=100,
            )

            service = IndexingService(
                session=session,
                settings=settings,
                embedding_provider=embedding,
                vector_store=vector_store,
            )
            service.run(doc.id)

            # Verify all chunks have qdrant_point_id set
            result = session.execute(
                select(Chunk).where(Chunk.document_id == doc.id)
            )
            chunks = list(result.scalars().all())
            for chunk in chunks:
                assert chunk.qdrant_point_id is not None
                # Verify it's a valid UUID
                uuid.UUID(chunk.qdrant_point_id)
        finally:
            session.close()
            engine.dispose()

    def test_run_document_not_found(self):
        """Should raise IndexingServiceError when document not found."""
        session, engine = _make_sync_session()
        try:
            embedding = InMemoryEmbeddingProvider(dim=64)
            vector_store = InMemoryVectorStore()

            from app.common.core.config import Settings
            settings = Settings(
                DATABASE_URL="sqlite+aiosqlite:///",
                DATABASE_URL_SYNC="sqlite:///",
                APP_ENV="testing",
            )

            service = IndexingService(
                session=session,
                settings=settings,
                embedding_provider=embedding,
                vector_store=vector_store,
            )

            with pytest.raises(IndexingServiceError, match="not found"):
                service.run(uuid.uuid4())
        finally:
            session.close()
            engine.dispose()

    def test_run_no_chunks_sets_ready(self):
        """Document with no chunks should still be set to 'ready'."""
        session, engine = _make_sync_session()
        try:
            doc = _setup_doc_with_chunks(session, num_chunks=0)
            embedding = InMemoryEmbeddingProvider(dim=64)
            vector_store = InMemoryVectorStore()

            from app.common.core.config import Settings
            settings = Settings(
                DATABASE_URL="sqlite+aiosqlite:///",
                DATABASE_URL_SYNC="sqlite:///",
                APP_ENV="testing",
            )

            service = IndexingService(
                session=session,
                settings=settings,
                embedding_provider=embedding,
                vector_store=vector_store,
            )
            service.run(doc.id)

            session.refresh(doc)
            assert doc.status == "ready"
            assert len(vector_store._points) == 0
        finally:
            session.close()
            engine.dispose()

    def test_run_failure_sets_status_to_failed(self):
        """On failure, document status should be set to 'failed'."""
        session, engine = _make_sync_session()
        try:
            doc = _setup_doc_with_chunks(session, num_chunks=3)

            # Use a failing embedding provider
            class FailingProvider(EmbeddingProvider):
                @property
                def dimension(self):
                    return 64

                async def embed_texts(self, texts):
                    raise RuntimeError("Embedding failed!")

                async def embed_query(self, query):
                    raise RuntimeError("Embedding failed!")

            embedding = FailingProvider()
            vector_store = InMemoryVectorStore()

            from app.common.core.config import Settings
            settings = Settings(
                DATABASE_URL="sqlite+aiosqlite:///",
                DATABASE_URL_SYNC="sqlite:///",
                APP_ENV="testing",
                EMBEDDING_BATCH_SIZE=32,
                QDRANT_WRITE_BATCH_SIZE=100,
            )

            service = IndexingService(
                session=session,
                settings=settings,
                embedding_provider=embedding,
                vector_store=vector_store,
            )

            with pytest.raises(IndexingServiceError):
                service.run(doc.id)

            session.refresh(doc)
            assert doc.status == "failed"
        finally:
            session.close()
            engine.dispose()

    def test_batch_embedding(self):
        """Should process chunks in batches for embedding."""
        session, engine = _make_sync_session()
        try:
            doc = _setup_doc_with_chunks(session, num_chunks=70)
            embedding = InMemoryEmbeddingProvider(dim=64)
            vector_store = InMemoryVectorStore()

            from app.common.core.config import Settings
            settings = Settings(
                DATABASE_URL="sqlite+aiosqlite:///",
                DATABASE_URL_SYNC="sqlite:///",
                APP_ENV="testing",
                EMBEDDING_BATCH_SIZE=32,
                QDRANT_WRITE_BATCH_SIZE=100,
            )

            service = IndexingService(
                session=session,
                settings=settings,
                embedding_provider=embedding,
                vector_store=vector_store,
            )
            service.run(doc.id)

            # 70 chunks with batch_size=32 → 3 batches (32+32+6)
            assert embedding.call_count == 3
            assert len(embedding.texts_embedded) == 70
            assert len(vector_store._points) == 70
        finally:
            session.close()
            engine.dispose()

    def test_batch_writing(self):
        """Should write to vector store in batches."""
        session, engine = _make_sync_session()
        try:
            doc = _setup_doc_with_chunks(session, num_chunks=250)
            embedding = InMemoryEmbeddingProvider(dim=64)
            vector_store = InMemoryVectorStore()

            from app.common.core.config import Settings
            settings = Settings(
                DATABASE_URL="sqlite+aiosqlite:///",
                DATABASE_URL_SYNC="sqlite:///",
                APP_ENV="testing",
                EMBEDDING_BATCH_SIZE=32,
                QDRANT_WRITE_BATCH_SIZE=100,
            )

            service = IndexingService(
                session=session,
                settings=settings,
                embedding_provider=embedding,
                vector_store=vector_store,
            )
            service.run(doc.id)

            # 250 points with write_batch_size=100 → 3 upsert calls (100+100+50)
            assert len(vector_store.upsert_calls) == 3
            assert len(vector_store.upsert_calls[0]) == 100
            assert len(vector_store.upsert_calls[1]) == 100
            assert len(vector_store.upsert_calls[2]) == 50
            assert len(vector_store._points) == 250
        finally:
            session.close()
            engine.dispose()

    def test_status_flow_chunked_to_indexing_to_ready(self):
        """Should follow chunked → indexing → ready status flow."""
        session, engine = _make_sync_session()
        try:
            doc = _setup_doc_with_chunks(session, num_chunks=3)
            assert doc.status == "chunked"

            # Track status changes
            statuses_seen = []
            original_flush = session.flush

            def tracking_flush(*args, **kwargs):
                statuses_seen.append(doc.status)
                return original_flush(*args, **kwargs)

            session.flush = tracking_flush

            embedding = InMemoryEmbeddingProvider(dim=64)
            vector_store = InMemoryVectorStore()

            from app.common.core.config import Settings
            settings = Settings(
                DATABASE_URL="sqlite+aiosqlite:///",
                DATABASE_URL_SYNC="sqlite:///",
                APP_ENV="testing",
                EMBEDDING_BATCH_SIZE=32,
                QDRANT_WRITE_BATCH_SIZE=100,
            )

            service = IndexingService(
                session=session,
                settings=settings,
                embedding_provider=embedding,
                vector_store=vector_store,
            )
            service.run(doc.id)

            # Should have seen "indexing" and "ready" statuses
            assert "indexing" in statuses_seen
            assert "ready" in statuses_seen

            session.flush = original_flush
        finally:
            session.close()
            engine.dispose()


@pytest.mark.unit
class TestIndexingServicePayload:
    """Tests for vector point payload structure."""

    def test_payload_contains_required_fields(self):
        """Each point payload should contain all required metadata fields."""
        session, engine = _make_sync_session()
        try:
            doc = _setup_doc_with_chunks(session, num_chunks=1)
            embedding = InMemoryEmbeddingProvider(dim=64)
            vector_store = InMemoryVectorStore()

            from app.common.core.config import Settings
            settings = Settings(
                DATABASE_URL="sqlite+aiosqlite:///",
                DATABASE_URL_SYNC="sqlite:///",
                APP_ENV="testing",
                EMBEDDING_BATCH_SIZE=32,
                QDRANT_WRITE_BATCH_SIZE=100,
            )

            service = IndexingService(
                session=session,
                settings=settings,
                embedding_provider=embedding,
                vector_store=vector_store,
            )
            service.run(doc.id)

            point = list(vector_store._points.values())[0]
            required_fields = [
                "kb_id", "document_id", "chunk_id",
                "document_type", "language", "product_model",
                "is_enabled", "status",
            ]
            for field in required_fields:
                assert field in point.payload, f"Missing payload field: {field}"

        finally:
            session.close()
            engine.dispose()
