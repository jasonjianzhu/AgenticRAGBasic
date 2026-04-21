from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.dependencies import _get_settings
from app.db.base import Base
from app.db.models import Chunk
from app.db.repositories import ChunkRepository, DocumentRepository, DocumentVersionRepository, KnowledgeBaseRepository
from app.db.session import get_db_session
from app.main import create_app


@pytest.fixture
def chunk_client(tmp_path) -> Iterator[tuple[TestClient, Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    db_session = session_factory()

    app = create_app()

    def override_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[_get_settings] = lambda: _get_settings()

    with TestClient(app) as test_client:
        yield test_client, db_session

    db_session.close()


def seed_preview_data(session: Session) -> str:
    kb = KnowledgeBaseRepository(session).create(name="default")
    document = DocumentRepository(session).create_uploaded(
        knowledge_base_id=kb.id,
        title="PCS Manual",
        source_filename="pcs.pdf",
        storage_path="var/uploads/pcs.pdf",
        content_hash="hash-1",
        mime_type="application/pdf",
        file_size_bytes=1024,
        document_type="manual",
    )
    version = DocumentVersionRepository(session).create(document_id=document.id, version_number=1, status="chunked")
    ChunkRepository(session).create_many(
        [
            Chunk(
                knowledge_base_id=kb.id,
                document_id=document.id,
                document_version_id=version.id,
                ordinal=1,
                chunk_type="text",
                section_path="Overview",
                content="Battery system overview.",
                content_hash="chunk-1",
                token_count=8,
                language="en",
                metadata_={"chunker": "docling_hybrid"},
            ),
            Chunk(
                knowledge_base_id=kb.id,
                document_id=document.id,
                document_version_id=version.id,
                ordinal=2,
                chunk_type="table",
                section_path="Alarm table",
                content="| Code | Meaning |\n|---|---|\n|E101|Overheat|",
                content_hash="chunk-2",
                token_count=12,
                page_start=2,
                page_end=2,
                language="en",
                metadata_={"chunker": "docling_hybrid"},
            ),
        ]
    )
    return str(document.id)


def test_list_document_chunks_returns_preview_payload(chunk_client) -> None:
    client, db_session = chunk_client
    document_id = seed_preview_data(db_session)

    response = client.get(f"/documents/{document_id}/chunks")

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == document_id
    assert payload["total"] == 2
    assert payload["items"][0]["ordinal"] == 1
    assert payload["items"][1]["chunk_type"] == "table"


def test_list_document_chunks_supports_chunk_type_filter(chunk_client) -> None:
    client, db_session = chunk_client
    document_id = seed_preview_data(db_session)

    response = client.get(f"/documents/{document_id}/chunks", params={"chunk_type": "table"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["chunk_type"] == "table"


def test_list_document_chunks_returns_404_for_missing_document(chunk_client) -> None:
    client, _db_session = chunk_client

    response = client.get("/documents/91e0cf13-7b63-45e5-8c1a-21f9d2b9db44/chunks")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"
