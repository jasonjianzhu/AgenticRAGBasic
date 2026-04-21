from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from uuid import UUID

from app.core.config import Settings
from app.core.dependencies import _get_embedding_provider, _get_llm_client, _get_settings, _get_vector_store
from app.db.base import Base
from app.db.models import Chunk, JobLog
from app.db.repositories import ChunkRepository, DocumentRepository, DocumentVersionRepository, KnowledgeBaseRepository
from app.db.session import get_db_session
from app.jobs.queue import get_indexing_queue, get_ingestion_queue
from app.main import create_app
from app.rag.query.rewrite import QueryRewriteResult
from app.rag.vector_store.memory import InMemoryVectorStore
from app.services.indexing import DocumentIndexingService
from tests.fakes import DeterministicEmbeddingProvider


class FakeLLMClient:
    def rewrite_query(self, query: str):
        return QueryRewriteResult(
            original_query=query,
            rewritten_query=query,
            expanded_queries=[],
            language="en",
            document_type="manual",
        )

    def generate_answer(self, query: str, context_blocks: list[str]) -> str:
        return f"Answer: {context_blocks[0]}"


class FakeJob:
    def __init__(self, id_: str):
        self.id = id_


class FakeQueue:
    def __init__(self, name: str):
        self.name = name
        self.enqueued = []

    def enqueue(self, func, *args, **kwargs):
        self.enqueued.append((func, args, kwargs))
        return FakeJob(f"{self.name}-job-{len(self.enqueued)}")


@pytest.fixture
def page_client(tmp_path) -> Iterator[tuple[TestClient, Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    db_session = session_factory()

    settings = Settings(
        UPLOAD_DIR=tmp_path / "uploads",
        PARSED_DIR=tmp_path / "parsed",
        INDEX_DIR=tmp_path / "indexes",
        QDRANT_COLLECTION_NAME="test_chunks",
        EMBEDDING_DIMENSION=8,
    )
    vector_store = InMemoryVectorStore()
    embedding_provider = DeterministicEmbeddingProvider(dimension=8)
    llm_client = FakeLLMClient()
    ingestion_queue = FakeQueue("ingestion")
    indexing_queue = FakeQueue("indexing")

    app = create_app()

    def override_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[_get_settings] = lambda: settings
    app.dependency_overrides[_get_vector_store] = lambda: vector_store
    app.dependency_overrides[_get_embedding_provider] = lambda: embedding_provider
    app.dependency_overrides[_get_llm_client] = lambda: llm_client
    app.dependency_overrides[get_ingestion_queue] = lambda: ingestion_queue
    app.dependency_overrides[get_indexing_queue] = lambda: indexing_queue

    with TestClient(app) as test_client:
        yield test_client, db_session

    db_session.close()


def seed_page_data(session: Session, settings: Settings, vector_store: InMemoryVectorStore, embedding_provider) -> str:
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
                metadata_={"chunker": "docling_hybrid"},
            )
        ]
    )
    DocumentIndexingService(
        session=session,
        settings=settings,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    ).index_document(document.id)
    return str(document.id)


def test_admin_documents_page_renders_document_table(page_client) -> None:
    client, db_session = page_client
    settings = client.app.dependency_overrides[_get_settings]()
    vector_store = client.app.dependency_overrides[_get_vector_store]()
    embedding_provider = client.app.dependency_overrides[_get_embedding_provider]()
    seed_page_data(db_session, settings, vector_store, embedding_provider)

    response = client.get("/")

    assert response.status_code == 200
    assert "PCS Manual" in response.text
    assert "文档管理" in response.text


def test_document_detail_page_renders_chunk_preview(page_client) -> None:
    client, db_session = page_client
    settings = client.app.dependency_overrides[_get_settings]()
    vector_store = client.app.dependency_overrides[_get_vector_store]()
    embedding_provider = client.app.dependency_overrides[_get_embedding_provider]()
    document_id = seed_page_data(db_session, settings, vector_store, embedding_provider)

    response = client.get(f"/ui/documents/{document_id}")

    assert response.status_code == 200
    assert "Chunk Preview" in response.text
    assert "Alarm code E101" in response.text


def test_document_detail_page_supports_management_actions(page_client) -> None:
    client, db_session = page_client
    settings = client.app.dependency_overrides[_get_settings]()
    vector_store = client.app.dependency_overrides[_get_vector_store]()
    embedding_provider = client.app.dependency_overrides[_get_embedding_provider]()
    document_id = seed_page_data(db_session, settings, vector_store, embedding_provider)
    failed_job = JobLog(queue_name="ingestion", job_type="ingest_document", document_id=UUID(document_id), status="failed")
    db_session.add(failed_job)
    db_session.commit()

    disable_response = client.post(f"/ui/documents/{document_id}/toggle", data={"action": "disable"})
    reindex_response = client.post(f"/ui/documents/{document_id}/reindex")
    retry_response = client.post(f"/ui/documents/{document_id}/retry", data={"job_id": str(failed_job.id)})

    assert disable_response.status_code == 200
    assert "文档操作" in disable_response.text
    assert reindex_response.status_code == 200
    assert "任务状态" in reindex_response.text
    assert retry_response.status_code == 200


def test_rag_page_can_submit_question_and_render_answer(page_client) -> None:
    client, db_session = page_client
    settings = client.app.dependency_overrides[_get_settings]()
    vector_store = client.app.dependency_overrides[_get_vector_store]()
    embedding_provider = client.app.dependency_overrides[_get_embedding_provider]()
    seed_page_data(db_session, settings, vector_store, embedding_provider)

    response = client.post("/ui/rag", data={"query": "E101 overheat alarm"})

    assert response.status_code == 200
    assert "RAG 问答" in response.text
    assert "Answer:" in response.text
    assert "Alarm code E101" in response.text
    assert "启用 rerank" in response.text


def test_rag_page_can_render_rewrite_trace(page_client) -> None:
    client, db_session = page_client
    settings = client.app.dependency_overrides[_get_settings]()
    vector_store = client.app.dependency_overrides[_get_vector_store]()
    embedding_provider = client.app.dependency_overrides[_get_embedding_provider]()
    seed_page_data(db_session, settings, vector_store, embedding_provider)

    response = client.post("/ui/rag", data={"query": "E101 overheat alarm", "show_rewrite": "on"})

    assert response.status_code == 200
    assert "Query Trace" in response.text
    assert "Retrieval Queries" in response.text


def test_rag_page_can_toggle_reranker(page_client) -> None:
    client, db_session = page_client
    settings = client.app.dependency_overrides[_get_settings]()
    vector_store = client.app.dependency_overrides[_get_vector_store]()
    embedding_provider = client.app.dependency_overrides[_get_embedding_provider]()
    seed_page_data(db_session, settings, vector_store, embedding_provider)

    disabled_response = client.post("/ui/rag", data={"query": "E101 overheat alarm"})
    enabled_response = client.post("/ui/rag", data={"query": "E101 overheat alarm", "use_reranker": "on"})

    assert disabled_response.status_code == 200
    assert "启用 rerank" in disabled_response.text
    assert 'name="use_reranker"' in disabled_response.text
    assert "checked" not in disabled_response.text.split('name="use_reranker"', 1)[1].split(">", 1)[0]

    assert enabled_response.status_code == 200
    assert "启用 rerank" in enabled_response.text
    assert "checked" in enabled_response.text.split('name="use_reranker"', 1)[1].split(">", 1)[0]
