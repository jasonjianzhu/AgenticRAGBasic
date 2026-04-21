"""Job log repository - data access layer for async job tracking."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JobLog


class JobRepository:
    """Repository for JobLog CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_job_log(
        self,
        *,
        queue_name: str,
        job_type: str,
        document_id: uuid.UUID | None = None,
        rq_job_id: str | None = None,
        payload: dict | None = None,
    ) -> JobLog:
        """Create a new job log entry with status 'queued'."""
        job_log = JobLog(
            queue_name=queue_name,
            job_type=job_type,
            status="queued",
            document_id=document_id,
            rq_job_id=rq_job_id,
            payload=payload or {},
            attempts=0,
        )
        self.session.add(job_log)
        await self.session.flush()
        return job_log

    async def get_by_id(self, job_id: uuid.UUID) -> JobLog | None:
        """Get a job log by its primary key."""
        stmt = select(JobLog).where(JobLog.id == job_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_document_id(self, document_id: uuid.UUID) -> Sequence[JobLog]:
        """Get all job logs for a given document."""
        stmt = (
            select(JobLog)
            .where(JobLog.document_id == document_id)
            .order_by(JobLog.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_jobs(
        self,
        *,
        status: str | None = None,
        queue_name: str | None = None,
        document_id: uuid.UUID | None = None,
    ) -> int:
        """Count job logs matching filters."""
        stmt = select(func.count(JobLog.id))
        if status is not None:
            stmt = stmt.where(JobLog.status == status)
        if queue_name is not None:
            stmt = stmt.where(JobLog.queue_name == queue_name)
        if document_id is not None:
            stmt = stmt.where(JobLog.document_id == document_id)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def list_jobs(
        self,
        *,
        status: str | None = None,
        queue_name: str | None = None,
        document_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[JobLog]:
        """List job logs with optional filters."""
        stmt = select(JobLog)

        if status is not None:
            stmt = stmt.where(JobLog.status == status)
        if queue_name is not None:
            stmt = stmt.where(JobLog.queue_name == queue_name)
        if document_id is not None:
            stmt = stmt.where(JobLog.document_id == document_id)

        stmt = stmt.order_by(JobLog.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_status(
        self,
        job_log: JobLog,
        status: str,
        *,
        error_message: str | None = None,
    ) -> JobLog:
        """Update job status with appropriate timestamp handling.

        Valid transitions:
            queued → started → finished | failed
            queued → failed (direct failure)
            failed → retrying → queued (retry flow)
        """
        now = datetime.now(timezone.utc)

        job_log.status = status

        if status == "started":
            job_log.started_at = now
            job_log.attempts += 1
        elif status == "finished":
            job_log.finished_at = now
            job_log.error_message = None
        elif status == "failed":
            job_log.finished_at = now
            job_log.error_message = error_message
        elif status == "retrying":
            # Reset for retry
            job_log.error_message = None
            job_log.started_at = None
            job_log.finished_at = None

        await self.session.flush()
        return job_log

    async def increment_attempts(self, job_log: JobLog) -> JobLog:
        """Increment the attempts counter."""
        job_log.attempts += 1
        await self.session.flush()
        return job_log

    async def update_rq_job_id(self, job_log: JobLog, rq_job_id: str) -> JobLog:
        """Update the RQ job ID (e.g., after re-enqueue on retry)."""
        job_log.rq_job_id = rq_job_id
        await self.session.flush()
        return job_log
