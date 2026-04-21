from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.repositories import ChunkRepository, DocumentRepository, DocumentVersionRepository, JobLogRepository, KnowledgeBaseRepository
from app.jobs.tasks import _ingest_document
from app.rag.parsing.simple_parser import SimpleTextParser
from tests.test_document_upload import FakeNamedQueue


def test_ingest_document_task_uses_parser_and_updates_status(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    source_path = tmp_path / "manual.txt"
    source_path.write_text("Intro", encoding="utf-8")

    with session_factory() as session:
        kb = KnowledgeBaseRepository(session).create(name="default")
        document = DocumentRepository(session).create_uploaded(
            knowledge_base_id=kb.id,
            title="PCS Manual",
            source_filename="pcs.pdf",
            storage_path=str(source_path),
            content_hash="hash",
            mime_type="text/plain",
            file_size_bytes=10,
        )
        JobLogRepository(session).create(queue_name="ingestion", job_type="ingest_document", document_id=document.id)

        settings = Settings(
            UPLOAD_DIR=tmp_path / "uploads",
            PARSED_DIR=tmp_path / "parsed",
            INDEX_DIR=tmp_path / "indexes",
        )
        _ingest_document(
            session,
            str(document.id),
            parser=SimpleTextParser(),
            settings=settings,
            indexing_queue=FakeNamedQueue("indexing"),
        )

        updated = DocumentRepository(session).get(document.id)
        latest_version = DocumentVersionRepository(session).get_latest_for_document(document.id)
        chunks = ChunkRepository(session).list_by_document(document.id)
        jobs = JobLogRepository(session).list_by_document(document.id)
        assert updated is not None
        assert updated.status == "chunked"
        assert latest_version is not None
        assert latest_version.status == "chunked"
        assert len(chunks) == 1
        assert len(jobs) == 2
        assert {job.job_type for job in jobs} == {"ingest_document", "index_document"}
