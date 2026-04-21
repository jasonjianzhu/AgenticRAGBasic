from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.models import Chunk
from app.db.repositories import ChunkRepository, DocumentRepository, DocumentVersionRepository, JobLogRepository, KnowledgeBaseRepository
from app.jobs.tasks import _index_document
from app.rag.vector_store.memory import InMemoryVectorStore
from tests.fakes import DeterministicEmbeddingProvider


def test_index_document_task_indexes_chunks_and_updates_status(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)

    with session_factory() as session:
        kb = KnowledgeBaseRepository(session).create(name="default")
        document = DocumentRepository(session).create_uploaded(
            knowledge_base_id=kb.id,
            title="PCS Manual",
            source_filename="pcs.pdf",
            storage_path="var/uploads/pcs.pdf",
            content_hash="hash",
            mime_type="application/pdf",
            file_size_bytes=10,
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
                    content="E101 overheat handling",
                    content_hash="chunk-1",
                    language="en",
                )
            ]
        )
        job_log = JobLogRepository(session).create(queue_name="indexing", job_type="index_document", document_id=document.id)
        session.commit()

        settings = Settings(
            UPLOAD_DIR=tmp_path / "uploads",
            PARSED_DIR=tmp_path / "parsed",
            INDEX_DIR=tmp_path / "indexes",
            QDRANT_COLLECTION_NAME="test_chunks",
            EMBEDDING_DIMENSION=8,
        )
        vector_store = InMemoryVectorStore()
        from app.jobs.tasks import index_document
        from app.jobs.lifecycle import run_with_job_lifecycle

        run_with_job_lifecycle(
            session=session,
            job_log_id=job_log.id,
            operation=lambda: _index_document(
                session,
                str(document.id),
                settings=settings,
                embedding_provider=DeterministicEmbeddingProvider(dimension=8),
                vector_store=vector_store,
            ),
        )

        updated = DocumentRepository(session).get(document.id)
        latest_version = DocumentVersionRepository(session).get_latest_for_document(document.id)
        chunks = ChunkRepository(session).list_by_document(document.id)
        updated_job = JobLogRepository(session).get(job_log.id)
        assert updated is not None
        assert updated.status == "ready"
        assert latest_version is not None
        assert latest_version.status == "ready"
        assert chunks[0].qdrant_point_id is not None
        assert updated_job is not None
        assert updated_job.status == "finished"
        assert updated_job.attempts == 1
