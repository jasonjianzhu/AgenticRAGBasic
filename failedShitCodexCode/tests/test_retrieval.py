from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.models import Chunk
from app.db.repositories import ChunkRepository, DocumentRepository, DocumentVersionRepository, KnowledgeBaseRepository
from app.rag.retrieval.service import HybridRetrievalService
from app.rag.vector_store.memory import InMemoryVectorStore
from app.services.indexing import DocumentIndexingService
from tests.fakes import DeterministicEmbeddingProvider


def seed_ready_indexed_document(session: Session, settings: Settings, vector_store: InMemoryVectorStore) -> str:
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
                section_path="Alarm handling",
                content="Alarm code E101 indicates battery overheat. Check cooling fan status.",
                content_hash="chunk-1",
                language="en",
                page_start=5,
                page_end=5,
            ),
            Chunk(
                knowledge_base_id=kb.id,
                document_id=document.id,
                document_version_id=version.id,
                ordinal=2,
                chunk_type="text",
                section_path="Maintenance",
                content="Routine maintenance should inspect wiring every month.",
                content_hash="chunk-2",
                language="en",
                page_start=7,
                page_end=7,
            ),
        ]
    )
    DocumentIndexingService(
        session=session,
        settings=settings,
        embedding_provider=DeterministicEmbeddingProvider(dimension=settings.embedding_dimension),
        vector_store=vector_store,
    ).index_document(document.id)
    return str(document.id)


def test_hybrid_retrieval_returns_relevant_chunk(tmp_path) -> None:
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
    vector_store = InMemoryVectorStore()

    with session_factory() as session:
        seed_ready_indexed_document(session, settings, vector_store)
        result = HybridRetrievalService(
            session=session,
            settings=settings,
            embedding_provider=DeterministicEmbeddingProvider(dimension=8),
            vector_store=vector_store,
        ).search(query="How to handle E101 overheat alarm?", top_k=3)

        assert result.rewritten_query
        assert result.trace["retrieval_mode"] == "hybrid"
        assert result.trace["dense_hit_count"] >= 1
        assert result.trace["sparse_hit_count"] >= 1
        assert result.trace["fused_hit_count"] >= 1
        assert result.items
        assert result.items[0].content.startswith("Alarm code E101")


def test_hybrid_retrieval_respects_language_filter(tmp_path) -> None:
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
    vector_store = InMemoryVectorStore()

    with session_factory() as session:
        seed_ready_indexed_document(session, settings, vector_store)
        result = HybridRetrievalService(
            session=session,
            settings=settings,
            embedding_provider=DeterministicEmbeddingProvider(dimension=8),
            vector_store=vector_store,
        ).search(query="E101", top_k=3, language="zh")

        assert result.items == []


def test_hybrid_retrieval_supports_chinese_sparse_matching(tmp_path) -> None:
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
    vector_store = InMemoryVectorStore()

    with session_factory() as session:
        kb = KnowledgeBaseRepository(session).create(name="default")
        document = DocumentRepository(session).create_uploaded(
            knowledge_base_id=kb.id,
            title="中文手册",
            source_filename="cn.pdf",
            storage_path="var/uploads/cn.pdf",
            content_hash="hash-cn",
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
                    section_path="告警处理",
                    content="E101 告警表示电池过热，请检查散热风扇与通风条件。",
                    content_hash="cn-1",
                    language="zh",
                    page_start=2,
                    page_end=2,
                )
            ]
        )
        DocumentIndexingService(
            session=session,
            settings=settings,
            embedding_provider=DeterministicEmbeddingProvider(dimension=8),
            vector_store=vector_store,
        ).index_document(document.id)

        result = HybridRetrievalService(
            session=session,
            settings=settings,
            embedding_provider=DeterministicEmbeddingProvider(dimension=8),
            vector_store=vector_store,
        ).search(query="E101 告警怎么处理", top_k=3, language="zh")

        assert result.items
        assert "电池过热" in result.items[0].content
