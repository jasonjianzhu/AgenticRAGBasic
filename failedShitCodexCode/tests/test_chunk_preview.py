from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import Chunk
from app.db.repositories import ChunkRepository, DocumentRepository, DocumentVersionRepository, KnowledgeBaseRepository
from app.services.chunks import ChunkPreviewService


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    with session_factory() as db_session:
        yield db_session


def seed_document_with_chunks(session: Session):
    kb = KnowledgeBaseRepository(session).create(name=f"kb-{uuid.uuid4()}")
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
    return document


def test_chunk_repository_lists_chunks_by_document_with_optional_type_filter(session: Session) -> None:
    document = seed_document_with_chunks(session)
    repository = ChunkRepository(session)

    all_chunks = repository.list_by_document(document.id)
    table_chunks = repository.list_by_document(document.id, chunk_type="table")

    assert [chunk.ordinal for chunk in all_chunks] == [1, 2]
    assert len(table_chunks) == 1
    assert table_chunks[0].chunk_type == "table"


def test_chunk_preview_service_returns_document_preview_payload(session: Session) -> None:
    document = seed_document_with_chunks(session)

    payload = ChunkPreviewService(session).list_document_chunks(document.id)

    assert payload.document_id == document.id
    assert payload.total == 2
    assert payload.items[0].ordinal == 1
    assert payload.items[1].chunk_type == "table"
    assert payload.items[1].metadata["chunker"] == "docling_hybrid"


def test_chunk_preview_service_raises_for_missing_document(session: Session) -> None:
    with pytest.raises(ValueError, match="Document not found"):
        ChunkPreviewService(session).list_document_chunks(uuid.uuid4())
