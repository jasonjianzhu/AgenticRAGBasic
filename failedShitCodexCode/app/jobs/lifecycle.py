from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session

from app.db.repositories import DocumentRepository, JobLogRepository


T = TypeVar("T")
logger = logging.getLogger(__name__)


def run_with_job_lifecycle(session: Session, job_log_id: str | uuid.UUID, operation: Callable[[], T]) -> T:
    repository = JobLogRepository(session)
    job_id = uuid.UUID(str(job_log_id))
    job = repository.mark_started(job_id)
    session.commit()
    logger.info(
        "Job started: job_log_id=%s queue=%s job_type=%s document_id=%s attempt=%s",
        job.id,
        job.queue_name,
        job.job_type,
        job.document_id,
        job.attempts,
    )
    try:
        result = operation()
    except Exception as exc:
        session.rollback()
        failed_job = None
        try:
            failed_job = repository.mark_failed(job_id, str(exc))
            if failed_job.document_id is not None:
                DocumentRepository(session).update_status(failed_job.document_id, "failed")
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to persist failed job state: job_log_id=%s", job_id)

        if failed_job is not None:
            logger.exception(
                "Job failed: job_log_id=%s queue=%s job_type=%s document_id=%s",
                failed_job.id,
                failed_job.queue_name,
                failed_job.job_type,
                failed_job.document_id,
            )
        else:
            logger.exception("Job failed before failure state could be persisted: job_log_id=%s", job_id)
        raise

    finished_job = repository.mark_finished(job_id)
    session.commit()
    logger.info(
        "Job finished: job_log_id=%s queue=%s job_type=%s document_id=%s",
        finished_job.id,
        finished_job.queue_name,
        finished_job.job_type,
        finished_job.document_id,
    )
    return result
