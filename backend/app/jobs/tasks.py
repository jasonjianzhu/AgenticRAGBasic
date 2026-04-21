"""RQ task functions for async job execution.

These functions are called by RQ workers. They use synchronous DB sessions
since RQ workers run synchronous code.
"""
from __future__ import annotations

import uuid

from app.core.logging import get_logger

logger = get_logger(__name__)


def run_ingestion(document_id: str, **kwargs) -> None:
    """Execute document ingestion (parse + chunk), then auto-enqueue indexing.

    Called by RQ worker from the ingestion queue.
    """
    logger.info("run_ingestion_called", document_id=document_id, kwargs=kwargs)

    from app.core.config import get_settings
    from app.db.session_sync import sync_session_scope
    from app.services.ingestion_task import IngestionTaskService
    from app.storage.local import LocalStorage

    settings = get_settings()
    storage = LocalStorage(base_dir=settings.upload_dir)
    parser_profile = kwargs.get("parser_profile", "balanced")

    doc_uuid = uuid.UUID(document_id)

    with sync_session_scope() as session:
        service = IngestionTaskService(session, storage, settings)
        try:
            service.run(doc_uuid, parser_profile=parser_profile)
        except Exception as e:
            logger.exception("ingestion_task_failed", document_id=document_id, error=str(e))
            raise

    # Auto-enqueue indexing after successful ingestion
    try:
        from redis import Redis
        from rq import Queue

        redis_conn = Redis.from_url(settings.redis_url)
        indexing_queue = Queue(settings.rq_indexing_queue, connection=redis_conn)
        indexing_queue.enqueue(
            "app.jobs.tasks.run_indexing",
            document_id=document_id,
            job_timeout=settings.rq_indexing_timeout,
        )
        logger.info("indexing_auto_enqueued", document_id=document_id)
    except Exception as e:
        logger.exception("indexing_auto_enqueue_failed", document_id=document_id, error=str(e))


def run_indexing(document_id: str, **kwargs) -> None:
    """Execute document indexing (embed + write to Qdrant).

    Called by RQ worker from the indexing queue.
    """
    logger.info("run_indexing_called", document_id=document_id, kwargs=kwargs)

    import asyncio

    from app.core.config import get_settings
    from app.db.session_sync import sync_session_scope
    from app.services.indexing import IndexingService

    settings = get_settings()
    doc_uuid = uuid.UUID(document_id)

    with sync_session_scope() as session:
        service = IndexingService(session, settings)
        try:
            service.run(doc_uuid)
        except Exception as e:
            logger.exception("indexing_task_failed", document_id=document_id, error=str(e))
            raise
