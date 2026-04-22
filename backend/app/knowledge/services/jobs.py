"""Job service - business logic for async job management."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.config import Settings
from app.common.core.logging import get_logger
from app.common.db.models import JobLog
from app.common.db.repositories.jobs import JobRepository
from app.knowledge.jobs.queue import JobQueue

logger = get_logger(__name__)


class JobServiceError(Exception):
    """Base exception for job service errors."""


class JobNotFoundError(JobServiceError):
    """Raised when a job is not found."""


class JobRetryError(JobServiceError):
    """Raised when a job cannot be retried."""


class JobService:
    """Service layer for job operations."""

    def __init__(
        self,
        session: AsyncSession,
        job_queue: JobQueue,
        settings: Settings,
    ) -> None:
        self.repo = JobRepository(session)
        self.session = session
        self.job_queue = job_queue
        self.settings = settings

    async def enqueue_ingestion(self, document_id: uuid.UUID, **kwargs) -> JobLog:
        """Create a JobLog and enqueue an ingestion job."""
        rq_job_id = await self.job_queue.enqueue_ingestion(document_id, **kwargs)

        job_log = await self.repo.create_job_log(
            queue_name=self.settings.rq_ingestion_queue,
            job_type="ingest",
            document_id=document_id,
            rq_job_id=rq_job_id,
            payload={"document_id": str(document_id), **kwargs},
        )
        logger.info(
            "job_enqueued",
            job_id=str(job_log.id),
            rq_job_id=rq_job_id,
            queue="ingestion",
            document_id=str(document_id),
        )
        return job_log

    async def enqueue_indexing(self, document_id: uuid.UUID, **kwargs) -> JobLog:
        """Create a JobLog and enqueue an indexing job."""
        rq_job_id = await self.job_queue.enqueue_indexing(document_id, **kwargs)

        job_log = await self.repo.create_job_log(
            queue_name=self.settings.rq_indexing_queue,
            job_type="index",
            document_id=document_id,
            rq_job_id=rq_job_id,
            payload={"document_id": str(document_id), **kwargs},
        )
        logger.info(
            "job_enqueued",
            job_id=str(job_log.id),
            rq_job_id=rq_job_id,
            queue="indexing",
            document_id=str(document_id),
        )
        return job_log

    async def get_job(self, job_id: uuid.UUID) -> JobLog:
        """Get a job by ID, raising if not found."""
        job = await self.repo.get_by_id(job_id)
        if job is None:
            raise JobNotFoundError(f"Job {job_id} not found")
        return job

    async def list_jobs(
        self,
        *,
        status: str | None = None,
        queue_name: str | None = None,
        document_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[JobLog], int]:
        """List jobs with optional filters. Returns (items, total_count)."""
        jobs = await self.repo.list_jobs(
            status=status,
            queue_name=queue_name,
            document_id=document_id,
            skip=skip,
            limit=limit,
        )
        total = await self.repo.count_jobs(
            status=status,
            queue_name=queue_name,
            document_id=document_id,
        )
        return list(jobs), total

    async def mark_started(self, job_id: uuid.UUID) -> JobLog:
        """Mark a job as started."""
        job = await self.get_job(job_id)
        job = await self.repo.update_status(job, "started")
        logger.info("job_started", job_id=str(job_id))
        return job

    async def mark_finished(self, job_id: uuid.UUID) -> JobLog:
        """Mark a job as finished."""
        job = await self.get_job(job_id)
        job = await self.repo.update_status(job, "finished")
        logger.info("job_finished", job_id=str(job_id))
        return job

    async def mark_failed(self, job_id: uuid.UUID, error_message: str | None = None) -> JobLog:
        """Mark a job as failed."""
        job = await self.get_job(job_id)
        job = await self.repo.update_status(job, "failed", error_message=error_message)
        logger.warning("job_failed", job_id=str(job_id), error=error_message)
        return job

    async def retry_job(self, job_id: uuid.UUID) -> JobLog:
        """Retry a failed job.

        - Only failed jobs can be retried.
        - Respects max retry limit from settings.
        - Re-enqueues the job and updates the JobLog.
        """
        job = await self.get_job(job_id)

        if job.status != "failed":
            raise JobRetryError(f"Cannot retry job {job_id}: status is '{job.status}', expected 'failed'")

        if job.attempts >= self.settings.rq_max_retries:
            raise JobRetryError(
                f"Cannot retry job {job_id}: max retries ({self.settings.rq_max_retries}) reached "
                f"(attempts: {job.attempts})"
            )

        # Mark as retrying
        job = await self.repo.update_status(job, "retrying")

        # Re-enqueue based on queue type
        if job.queue_name == self.settings.rq_ingestion_queue:
            document_id = uuid.UUID(job.payload["document_id"]) if job.payload.get("document_id") else job.document_id
            rq_job_id = await self.job_queue.enqueue_ingestion(document_id)
        elif job.queue_name == self.settings.rq_indexing_queue:
            document_id = uuid.UUID(job.payload["document_id"]) if job.payload.get("document_id") else job.document_id
            rq_job_id = await self.job_queue.enqueue_indexing(document_id)
        else:
            raise JobRetryError(f"Unknown queue: {job.queue_name}")

        # Update job log with new RQ job ID and reset to queued
        await self.repo.update_rq_job_id(job, rq_job_id)
        job = await self.repo.update_status(job, "queued")

        logger.info("job_retried", job_id=str(job_id), new_rq_job_id=rq_job_id)
        return job
