from __future__ import annotations

import logging

from redis import Redis
from redis.exceptions import RedisError
from rq.exceptions import NoSuchJobError
from rq.job import Job
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import JobLog
from app.db.repositories import DocumentRepository, JobLogRepository


logger = logging.getLogger(__name__)

ACTIVE_DB_JOB_STATUSES = {"queued", "started", "retrying"}
FAILED_RQ_JOB_STATUSES = {"failed", "stopped", "canceled"}


def sync_job_log_from_rq(
    session: Session,
    job_log: JobLog,
    settings: Settings | None = None,
    redis_connection: Redis | None = None,
) -> bool:
    if job_log.rq_job_id is None or job_log.status not in ACTIVE_DB_JOB_STATUSES:
        return False

    resolved_settings = settings or get_settings()
    connection = redis_connection
    try:
        connection = connection or Redis.from_url(resolved_settings.redis_url)
        rq_job = Job.fetch(job_log.rq_job_id, connection=connection)
        rq_status = _status_value(rq_job.get_status(refresh=True))
    except NoSuchJobError:
        logger.warning(
            "RQ job not found while syncing job log: job_log_id=%s rq_job_id=%s",
            job_log.id,
            job_log.rq_job_id,
        )
        return False
    except (RedisError, OSError):
        logger.debug(
            "Unable to sync RQ job status: job_log_id=%s rq_job_id=%s",
            job_log.id,
            job_log.rq_job_id,
            exc_info=True,
        )
        return False

    repository = JobLogRepository(session)
    if rq_status in FAILED_RQ_JOB_STATUSES:
        failed_job = repository.mark_failed(job_log.id, _failure_message(rq_job, rq_status))
        if failed_job.document_id is not None:
            DocumentRepository(session).update_status(failed_job.document_id, "failed")
        logger.warning(
            "Synced failed RQ job to database: job_log_id=%s rq_job_id=%s rq_status=%s",
            job_log.id,
            job_log.rq_job_id,
            rq_status,
        )
        return True

    if rq_status == "finished":
        repository.mark_finished(job_log.id)
        logger.info(
            "Synced finished RQ job to database: job_log_id=%s rq_job_id=%s",
            job_log.id,
            job_log.rq_job_id,
        )
        return True

    return False


def sync_job_logs_from_rq(session: Session, job_logs: list[JobLog], settings: Settings | None = None) -> bool:
    resolved_settings = settings or get_settings()
    connection: Redis | None = None
    changed = False
    for job_log in job_logs:
        changed = sync_job_log_from_rq(session, job_log, resolved_settings, connection) or changed
        if connection is None:
            try:
                connection = Redis.from_url(resolved_settings.redis_url)
            except (RedisError, OSError):
                connection = None
    return changed


def _status_value(status) -> str:
    return getattr(status, "value", str(status))


def _failure_message(rq_job: Job, rq_status: str) -> str:
    if rq_job.exc_info:
        return rq_job.exc_info[:10000]
    return f"RQ job ended with status: {rq_status}"
