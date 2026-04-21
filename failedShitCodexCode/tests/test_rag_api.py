from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.dependencies import _get_embedding_provider, _get_llm_client, _get_settings, _get_vector_store
from app.db.base import Base
from app.db.models import Chunk, QueryLog
from app.db.repositories import ChunkRepository, DocumentRepository, DocumentVersionRepository, KnowledgeBaseRepository
from app.db.session import get_db_session
from app.main import create_app
from app.rag.vector_store.memory import InMemoryVectorStore
from app.services.indexing import DocumentIndexingService
from tests.fakes import DeterministicEmbeddingProvider, FakeLLMClient


@pytest.fixture
def rag_client(tmp_path) -> Iterator[tuple[TestClient, Session]]:
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

    app = create_app()

    def override_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[_get_settings] = lambda: settings
    app.dependency_overrides[_get_vector_store] = lambda: vector_store
    app.dependency_overrides[_get_embedding_provider] = lambda: embedding_provider
    app.dependency_overrides[_get_llm_client] = lambda: llm_client

    with TestClient(app) as test_client:
        yield test_client, db_session

    db_session.close()


def seed_rag_data(session: Session, settings: Settings, vector_store: InMemoryVectorStore, embedding_provider) -> None:
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
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    ).index_document(document.id)


def test_rag_search_api_returns_chunks_and_trace(rag_client) -> None:
    client, db_session = rag_client
    settings = client.app.dependency_overrides[_get_settings]()
    vector_store = client.app.dependency_overrides[_get_vector_store]()
    embedding_provider = client.app.dependency_overrides[_get_embedding_provider]()
    seed_rag_data(db_session, settings, vector_store, embedding_provider)

    response = client.post("/rag/search", json={"query": "E101 overheat alarm", "top_k": 3})

    assert response.status_code == 200
    payload = response.json()
    assert payload["chunks"]
    assert payload["trace"]["retrieval_mode"] == "hybrid_multi_query"
    assert payload["trace"]["rewrite"]["expanded_queries"]
    assert payload["chunks"][0]["content"].startswith("Alarm code E101")


def test_rag_search_api_can_disable_reranker_per_request(rag_client) -> None:
    client, db_session = rag_client
    settings = client.app.dependency_overrides[_get_settings]()
    vector_store = client.app.dependency_overrides[_get_vector_store]()
    embedding_provider = client.app.dependency_overrides[_get_embedding_provider]()
    seed_rag_data(db_session, settings, vector_store, embedding_provider)

    response = client.post(
        "/rag/search",
        json={"query": "E101 overheat alarm", "top_k": 3, "use_reranker": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["trace"]["rerank_enabled"] is False
    assert payload["trace"]["rerank_available"] is True


def test_rag_answer_api_returns_answer_and_citations(rag_client) -> None:
    client, db_session = rag_client
    settings = client.app.dependency_overrides[_get_settings]()
    vector_store = client.app.dependency_overrides[_get_vector_store]()
    embedding_provider = client.app.dependency_overrides[_get_embedding_provider]()
    seed_rag_data(db_session, settings, vector_store, embedding_provider)

    response = client.post("/rag/answer", json={"query": "How to handle E101 alarm?", "top_k": 3})

    assert response.status_code == 200
    payload = response.json()
    assert "E101" in payload["answer"]
    assert payload["answer"].startswith("LLM answer for")
    assert payload["citations"]
    assert payload["citations"][0]["source_filename"] == "pcs.pdf"
    assert payload["trace"]["rewrite"]["rewritten_query"]

    query_log = db_session.scalar(select(QueryLog))
    assert query_log is not None
    assert query_log.user_query == "How to handle E101 alarm?"
