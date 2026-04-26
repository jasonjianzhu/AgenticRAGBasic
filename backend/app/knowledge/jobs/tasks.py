"""RQ task functions for async job execution.

These functions are called by RQ workers. They use synchronous DB sessions
since RQ workers run synchronous code.
"""
from __future__ import annotations

import traceback
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.common.core.logging import get_logger
from app.common.db.models import JobLog

logger = get_logger(__name__)


def _update_job_log(session, document_id: uuid.UUID, job_type: str, **kwargs) -> None:
    """Find the latest JobLog for a document+job_type and update it.

    Args:
        session: Sync SQLAlchemy session.
        document_id: The document UUID.
        job_type: "ingest" or "index".
        **kwargs: Fields to update (status, error_message, started_at, finished_at).
    """
    stmt = (
        select(JobLog)
        .where(JobLog.document_id == document_id, JobLog.job_type == job_type)
        .order_by(JobLog.created_at.desc())
        .limit(1)
    )
    result = session.execute(stmt)
    job_log = result.scalar_one_or_none()
    if job_log is None:
        logger.warning("job_log_not_found", document_id=str(document_id), job_type=job_type)
        return

    for key, value in kwargs.items():
        if hasattr(job_log, key):
            setattr(job_log, key, value)
    session.flush()


def run_ingestion(document_id: str, **kwargs) -> None:
    """Execute document ingestion (parse + chunk), then auto-enqueue indexing.

    Called by RQ worker from the ingestion queue.
    """
    logger.info("run_ingestion_called", document_id=document_id, kwargs=kwargs)

    import time as _time
    _task_start = _time.monotonic()

    from app.common.core.config import get_settings
    from app.common.db.session_sync import sync_session_scope
    from app.knowledge.services.ingestion_task import IngestionTaskService
    from app.common.storage.local import LocalStorage

    settings = get_settings()
    storage = LocalStorage(base_dir=settings.upload_dir)
    parser_profile = kwargs.get("parser_profile", "balanced")

    doc_uuid = uuid.UUID(document_id)

    with sync_session_scope() as session:
        # Mark job as started
        now = datetime.now(timezone.utc)
        _update_job_log(session, doc_uuid, "ingest", status="started", started_at=now)

        service = IngestionTaskService(session, storage, settings)
        try:
            service.run(doc_uuid, parser_profile=parser_profile)
            # Mark job as finished
            _update_job_log(session, doc_uuid, "ingest", status="finished", finished_at=datetime.now(timezone.utc))
            logger.info("ingestion_task_complete", document_id=document_id,
                        duration_ms=round((_time.monotonic() - _task_start) * 1000))
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            _update_job_log(
                session, doc_uuid, "ingest",
                status="failed",
                error_message=error_msg,
                finished_at=datetime.now(timezone.utc),
            )
            logger.exception("ingestion_task_failed", document_id=document_id, error=str(e))
            raise

    # Auto-enqueue indexing after successful ingestion
    try:
        from redis import Redis
        from rq import Queue

        redis_conn = Redis.from_url(settings.redis_url)
        indexing_queue = Queue(settings.rq_indexing_queue, connection=redis_conn)
        job = indexing_queue.enqueue(
            "app.knowledge.jobs.tasks.run_indexing",
            document_id=document_id,
            job_timeout=settings.rq_indexing_timeout,
        )
        logger.info("indexing_auto_enqueued", document_id=document_id, rq_job_id=job.id)

        # Create JobLog for the indexing task
        from app.common.db.session_sync import sync_session_scope
        from app.common.db.models import JobLog
        with sync_session_scope() as session:
            job_log = JobLog(
                rq_job_id=job.id,
                queue_name=settings.rq_indexing_queue,
                job_type="index",
                status="queued",
                document_id=doc_uuid,
                attempts=0,
                payload={"document_id": document_id},
            )
            session.add(job_log)
            session.flush()
    except Exception as e:
        logger.exception("indexing_auto_enqueue_failed", document_id=document_id, error=str(e))


def run_indexing(document_id: str, **kwargs) -> None:
    """Execute document indexing (embed + write to Qdrant).

    Called by RQ worker from the indexing queue.
    """
    logger.info("run_indexing_called", document_id=document_id, kwargs=kwargs)

    import time as _time
    _task_start = _time.monotonic()

    from app.common.core.config import get_settings
    from app.common.db.session_sync import sync_session_scope
    from app.knowledge.services.indexing import IndexingService

    settings = get_settings()
    doc_uuid = uuid.UUID(document_id)

    with sync_session_scope() as session:
        # Mark job as started
        now = datetime.now(timezone.utc)
        _update_job_log(session, doc_uuid, "index", status="started", started_at=now)

        service = IndexingService(session, settings)
        try:
            service.run(doc_uuid)
            # Mark job as finished
            _update_job_log(session, doc_uuid, "index", status="finished", finished_at=datetime.now(timezone.utc))
            logger.info("indexing_task_complete", document_id=document_id,
                        duration_ms=round((_time.monotonic() - _task_start) * 1000))
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            _update_job_log(
                session, doc_uuid, "index",
                status="failed",
                error_message=error_msg,
                finished_at=datetime.now(timezone.utc),
            )
            logger.exception("indexing_task_failed", document_id=document_id, error=str(e))
            raise
