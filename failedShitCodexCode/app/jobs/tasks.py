from __future__ import annotations

import logging
import uuid

from qdrant_client import QdrantClient
from rq import Retry

from app.core.config import Settings
from app.core.config import get_settings
from app.db.repositories import JobLogRepository
from app.db.session import SessionLocal
from app.jobs.lifecycle import run_with_job_lifecycle
from app.jobs.queue import get_indexing_queue
from app.jobs.types import TaskQueue
from app.rag.embedding.factory import build_embedding_provider
from app.rag.parsing.base import DocumentParser
from app.rag.parsing.docling_parser import DoclingParser
from app.rag.parsing.fallback import FallbackParser
from app.rag.parsing.simple_parser import MinimalTextParser
from app.rag.vector_store.memory import InMemoryVectorStore
from app.rag.vector_store.qdrant import QdrantVectorStore
from app.services.ingestion import DocumentIngestionService
from app.services.indexing import DocumentIndexingService


logger = logging.getLogger(__name__)


def ingest_document(document_id: str, job_log_id: str) -> None:
    logger.info("Ingestion task received: document_id=%s job_log_id=%s", document_id, job_log_id)
    with SessionLocal() as session:
        run_with_job_lifecycle(
            session=session,
            job_log_id=job_log_id,
            operation=lambda: _ingest_document(session, document_id),
        )


def _ingest_document(
    session,
    document_id: str,
    parser: DocumentParser | None = None,
    settings: Settings | None = None,
    indexing_queue: TaskQueue | None = None,
) -> None:
    logger.info("Ingestion task started: document_id=%s", document_id)
    app_settings = settings or get_settings()
    DocumentIngestionService(
        session=session,
        settings=app_settings,
        parser=parser or FallbackParser(primary=DoclingParser(), fallback=MinimalTextParser(), prefer_fallback_for_pdf=True),
    ).ingest_document(document_id)
    logger.info("Ingestion completed, preparing indexing job: document_id=%s", document_id)
    resolved_indexing_queue = indexing_queue or get_indexing_queue()
    job_log = JobLogRepository(session).create(
        queue_name=resolved_indexing_queue.name,
        job_type="index_document",
        document_id=uuid.UUID(str(document_id)),
        payload={"document_id": str(document_id), "reason": "ingestion_completed"},
    )
    session.commit()
    logger.info(
        "Enqueuing indexing job: document_id=%s job_log_id=%s queue=%s timeout=%s retries=%s",
        document_id,
        job_log.id,
        resolved_indexing_queue.name,
        app_settings.rq_indexing_timeout_seconds,
        app_settings.rq_max_retries,
    )
    try:
        enqueued_job = resolved_indexing_queue.enqueue(
            index_document,
            str(document_id),
            str(job_log.id),
            job_timeout=app_settings.rq_indexing_timeout_seconds,
            retry=Retry(max=app_settings.rq_max_retries),
        )
    except Exception:
        logger.exception(
            "Failed to enqueue indexing job: document_id=%s job_log_id=%s queue=%s",
            document_id,
            job_log.id,
            resolved_indexing_queue.name,
        )
        raise
    JobLogRepository(session).set_rq_job_id(job_log.id, enqueued_job.id)
    session.commit()
    logger.info(
        "Indexing job enqueued: document_id=%s job_log_id=%s rq_job_id=%s queue=%s",
        document_id,
        job_log.id,
        enqueued_job.id,
        resolved_indexing_queue.name,
    )


def index_document(document_id: str, job_log_id: str) -> None:
    logger.info("Indexing task received: document_id=%s job_log_id=%s", document_id, job_log_id)
    with SessionLocal() as session:
        run_with_job_lifecycle(
            session=session,
            job_log_id=job_log_id,
            operation=lambda: _index_document(session, document_id),
        )


def _index_document(
    session,
    document_id: str,
    settings: Settings | None = None,
    embedding_provider=None,
    vector_store=None,
) -> None:
    logger.info("Indexing task started: document_id=%s", document_id)
    app_settings = settings or get_settings()
    resolved_vector_store = vector_store
    if resolved_vector_store is None:
        if app_settings.vector_store_backend == "memory":
            resolved_vector_store = InMemoryVectorStore()
        else:
            resolved_vector_store = QdrantVectorStore(
                client=QdrantClient(url=app_settings.qdrant_url, api_key=app_settings.qdrant_api_key),
                collection_name=app_settings.qdrant_collection_name,
                vector_size=app_settings.embedding_dimension,
                dense_vector_name=app_settings.qdrant_dense_vector_name,
                sparse_vector_name=app_settings.qdrant_sparse_vector_name,
            )
    DocumentIndexingService(
        session=session,
        settings=app_settings,
        embedding_provider=embedding_provider or build_embedding_provider(app_settings),
        vector_store=resolved_vector_store,
    ).index_document(document_id)
