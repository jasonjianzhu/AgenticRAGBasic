from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.models import Chunk
from app.db.repositories import ChunkRepository, DocumentRepository, DocumentVersionRepository, KnowledgeBaseRepository
from app.rag.vector_store.memory import InMemoryVectorStore
from app.services.indexing import DocumentIndexingService
from tests.fakes import DeterministicEmbeddingProvider


def test_document_indexing_service_indexes_chunks_and_marks_document_ready(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)

    settings = Settings(
        UPLOAD_DIR=tmp_path / "uploads",
        PARSED_DIR=tmp_path / "parsed",
        INDEX_DIR=tmp_path / "indexes",
        QDRANT_COLLECTION_NAME="test_chunks",
        EMBEDDING_DIMENSION=8,
    )

    with session_factory() as session:
        kb = KnowledgeBaseRepository(session).create(name="default")
        document = DocumentRepository(session).create_uploaded(
            knowledge_base_id=kb.id,
            title="PCS Manual",
            source_filename="pcs.pdf",
            storage_path="var/uploads/pcs.pdf",
            content_hash="hash",
            mime_type="application/pdf",
            file_size_bytes=128,
            document_type="manual",
        )
        DocumentRepository(session).update_status(document.id, "chunked")
        version = DocumentVersionRepository(session).create(document_id=document.id, version_number=1, status="chunked")
        ChunkRepository(session).create_many(
            [
                Chunk(
                    knowledge_base_id=kb.id,
                    document_id=document.id,
                    document_version_id=version.id,
                    ordinal=1,
                    chunk_type="text",
                    content="Battery system overview",
                    content_hash="chunk-1",
                    language="en",
                ),
                Chunk(
                    knowledge_base_id=kb.id,
                    document_id=document.id,
                    document_version_id=version.id,
                    ordinal=2,
                    chunk_type="table",
                    content="| Code | Meaning |\n|---|---|\n|E101|Overheat|",
                    content_hash="chunk-2",
                    language="en",
                    page_start=3,
                    page_end=3,
                ),
            ]
        )

        vector_store = InMemoryVectorStore()
        indexed = DocumentIndexingService(
            session=session,
            settings=settings,
            embedding_provider=DeterministicEmbeddingProvider(dimension=8),
            vector_store=vector_store,
        ).index_document(document.id)

        updated_document = DocumentRepository(session).get(document.id)
        updated_version = DocumentVersionRepository(session).get_latest_for_document(document.id)
        stored_chunks = ChunkRepository(session).list_by_document(document.id)
        search_hits = vector_store.search(
            collection_name="test_chunks",
            query_vector=DeterministicEmbeddingProvider(dimension=8).embed_query("overheat"),
            limit=5,
        )

        assert indexed.indexed_chunk_count == 2
        assert updated_document is not None
        assert updated_document.status == "ready"
        assert updated_version is not None
        assert updated_version.status == "ready"
        assert all(chunk.qdrant_point_id for chunk in stored_chunks)
        assert len(search_hits) == 2


def test_document_indexing_service_rebuild_removes_previous_document_points(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)

    settings = Settings(
        UPLOAD_DIR=tmp_path / "uploads",
        PARSED_DIR=tmp_path / "parsed",
        INDEX_DIR=tmp_path / "indexes",
        QDRANT_COLLECTION_NAME="test_chunks",
        EMBEDDING_DIMENSION=8,
    )

    with session_factory() as session:
        kb = KnowledgeBaseRepository(session).create(name="default")
        document = DocumentRepository(session).create_uploaded(
            knowledge_base_id=kb.id,
            title="PCS Manual",
            source_filename="pcs.pdf",
            storage_path="var/uploads/pcs.pdf",
            content_hash="hash",
            mime_type="application/pdf",
            file_size_bytes=128,
            document_type="manual",
        )
        DocumentRepository(session).update_status(document.id, "chunked")
        version = DocumentVersionRepository(session).create(document_id=document.id, version_number=1, status="chunked")
        ChunkRepository(session).create_many(
            [
                Chunk(
                    knowledge_base_id=kb.id,
                    document_id=document.id,
                    document_version_id=version.id,
                    ordinal=1,
                    chunk_type="text",
                    content="Battery system overview",
                    content_hash="chunk-1",
                    language="en",
                )
            ]
        )

        vector_store = InMemoryVectorStore()
        service = DocumentIndexingService(
            session=session,
            settings=settings,
            embedding_provider=DeterministicEmbeddingProvider(dimension=8),
            vector_store=vector_store,
        )
        service.index_document(document.id)
        service.index_document(document.id)

        search_hits = vector_store.search(
            collection_name="test_chunks",
            query_vector=DeterministicEmbeddingProvider(dimension=8).embed_query("battery"),
            limit=10,
            filters={"document_id": str(document.id)},
        )

        assert len(search_hits) == 1


def test_document_indexing_service_only_indexes_latest_version_chunks(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)

    settings = Settings(
        UPLOAD_DIR=tmp_path / "uploads",
        PARSED_DIR=tmp_path / "parsed",
        INDEX_DIR=tmp_path / "indexes",
        QDRANT_COLLECTION_NAME="test_chunks",
        EMBEDDING_DIMENSION=8,
    )

    with session_factory() as session:
        kb = KnowledgeBaseRepository(session).create(name="default")
        document = DocumentRepository(session).create_uploaded(
            knowledge_base_id=kb.id,
            title="PCS Manual",
            source_filename="pcs.pdf",
            storage_path="var/uploads/pcs.pdf",
            content_hash="hash",
            mime_type="application/pdf",
            file_size_bytes=128,
            document_type="manual",
        )
        DocumentRepository(session).update_status(document.id, "chunked")
        older_version = DocumentVersionRepository(session).create(document_id=document.id, version_number=1, status="chunked")
        latest_version = DocumentVersionRepository(session).create(document_id=document.id, version_number=2, status="chunked")
        ChunkRepository(session).create_many(
            [
                Chunk(
                    knowledge_base_id=kb.id,
                    document_id=document.id,
                    document_version_id=older_version.id,
                    ordinal=1,
                    chunk_type="text",
                    content="old content should not be indexed",
                    content_hash="chunk-old",
                    language="en",
                ),
                Chunk(
                    knowledge_base_id=kb.id,
                    document_id=document.id,
                    document_version_id=latest_version.id,
                    ordinal=1,
                    chunk_type="text",
                    content="new content should be indexed",
                    content_hash="chunk-new",
                    language="en",
                ),
            ]
        )

        vector_store = InMemoryVectorStore()
        indexed = DocumentIndexingService(
            session=session,
            settings=settings,
            embedding_provider=DeterministicEmbeddingProvider(dimension=8),
            vector_store=vector_store,
        ).index_document(document.id)

        latest_chunks = ChunkRepository(session).list_by_document(document.id, document_version_id=latest_version.id)
        old_chunks = ChunkRepository(session).list_by_document(document.id, document_version_id=older_version.id)

        assert indexed.indexed_chunk_count == 1
        assert latest_chunks[0].qdrant_point_id is not None
        assert old_chunks[0].qdrant_point_id is None
