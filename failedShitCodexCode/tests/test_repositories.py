from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import Chunk
from app.db.repositories import (
    ChunkRepository,
    DocumentRepository,
    DocumentVersionRepository,
    JobLogRepository,
    KnowledgeBaseRepository,
    QueryLogRepository,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    with session_factory() as db_session:
        yield db_session


def create_document_fixture(session: Session):
    kb = KnowledgeBaseRepository(session).create(name=f"kb-{uuid.uuid4()}")
    document = DocumentRepository(session).create_uploaded(
        knowledge_base_id=kb.id,
        title="PCS Manual",
        source_filename="pcs.pdf",
        storage_path="var/uploads/pcs.pdf",
        content_hash="hash-1",
        mime_type="application/pdf",
        file_size_bytes=1024,
    )
    version = DocumentVersionRepository(session).create(document_id=document.id, version_number=1)
    return kb, document, version


def test_document_repository_creates_and_finds_document_by_hash(session: Session) -> None:
    kb, document, _version = create_document_fixture(session)

    found = DocumentRepository(session).get_by_hash(knowledge_base_id=kb.id, content_hash="hash-1")

    assert found is not None
    assert found.id == document.id
    assert found.status == "uploaded"


def test_document_repository_updates_status_and_enabled_flag(session: Session) -> None:
    _kb, document, _version = create_document_fixture(session)
    repository = DocumentRepository(session)

    repository.update_status(document.id, "parsing")
    repository.set_enabled(document.id, False)

    updated = repository.get(document.id)
    assert updated is not None
    assert updated.status == "parsing"
    assert updated.is_enabled is False


def test_document_version_repository_returns_latest_version(session: Session) -> None:
    _kb, document, _version = create_document_fixture(session)
    repository = DocumentVersionRepository(session)
    repository.create(document_id=document.id, version_number=2, status="parsed")

    latest = repository.get_latest_for_document(document.id)

    assert latest is not None
    assert latest.version_number == 2


def test_chunk_repository_persists_and_lists_chunks(session: Session) -> None:
    kb, document, version = create_document_fixture(session)
    repository = ChunkRepository(session)

    repository.create_many(
        [
            Chunk(
                knowledge_base_id=kb.id,
                document_id=document.id,
                document_version_id=version.id,
                ordinal=1,
                chunk_type="text",
                content="Battery system overview.",
                content_hash="chunk-1",
                language="en",
            ),
            Chunk(
                knowledge_base_id=kb.id,
                document_id=document.id,
                document_version_id=version.id,
                ordinal=2,
                chunk_type="table",
                content="Alarm code table.",
                content_hash="chunk-2",
                language="en",
            ),
        ]
    )

    chunks = repository.list_by_document(document.id)

    assert [chunk.ordinal for chunk in chunks] == [1, 2]
    assert chunks[1].chunk_type == "table"


def test_job_log_repository_tracks_lifecycle(session: Session) -> None:
    _kb, document, _version = create_document_fixture(session)
    repository = JobLogRepository(session)
    job = repository.create(queue_name="ingestion", job_type="parse", document_id=document.id)

    repository.mark_started(job.id)
    repository.mark_failed(job.id, "parser timeout")

    failed = repository.get(job.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.attempts == 1
    assert failed.error_message == "parser timeout"


def test_query_log_repository_records_trace(session: Session) -> None:
    kb, _document, _version = create_document_fixture(session)
    query_log = QueryLogRepository(session).create(
        knowledge_base_id=kb.id,
        session_id="session-1",
        user_query="E102 怎么处理？",
        rewritten_query="E102 alarm troubleshooting",
        answer="查看告警处理章节。",
        trace={"retrieval_mode": "hybrid"},
    )

    assert query_log.id is not None
    assert query_log.trace["retrieval_mode"] == "hybrid"
