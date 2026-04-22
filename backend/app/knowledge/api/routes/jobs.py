"""Job API routes for listing, detail, and retry."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.api.schemas.jobs import JobListResponse, JobResponse, JobRetryResponse
from app.common.core.config import Settings, get_settings
from app.common.core.dependencies import get_db
from app.knowledge.jobs.queue import InMemoryJobQueue, JobQueue
from app.knowledge.services.jobs import JobNotFoundError, JobRetryError, JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Module-level job queue instance; overridden in tests via dependency_overrides
_job_queue: JobQueue | None = None


def get_job_queue() -> JobQueue:
    """Get the job queue instance. Uses in-memory queue as default fallback."""
    global _job_queue
    if _job_queue is None:
        # In production, this would be set to RQJobQueue during app startup.
        # Default to InMemoryJobQueue for safety.
        _job_queue = InMemoryJobQueue()
    return _job_queue


def set_job_queue(queue: JobQueue) -> None:
    """Set the job queue instance (used during app startup)."""
    global _job_queue
    _job_queue = queue


def _get_service(
    session: AsyncSession = Depends(get_db),
    job_queue: JobQueue = Depends(get_job_queue),
    settings: Settings = Depends(get_settings),
) -> JobService:
    """Dependency to get Job service."""
    return JobService(session, job_queue, settings)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status_filter: str | None = Query(default=None, alias="status"),
    queue_name: str | None = Query(default=None),
    document_id: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    service: JobService = Depends(_get_service),
) -> JobListResponse:
    """List jobs with optional filters."""
    jobs, total = await service.list_jobs(
        status=status_filter,
        queue_name=queue_name,
        document_id=document_id,
        skip=skip,
        limit=limit,
    )
    items = [JobResponse.model_validate(j) for j in jobs]
    return JobListResponse(items=items, total=total)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    service: JobService = Depends(_get_service),
) -> JobResponse:
    """Get job detail with error info."""
    try:
        job = await service.get_job(job_id)
    except JobNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return JobResponse.model_validate(job)


@router.post("/{job_id}/retry", response_model=JobRetryResponse)
async def retry_job(
    job_id: uuid.UUID,
    service: JobService = Depends(_get_service),
) -> JobRetryResponse:
    """Retry a failed job."""
    try:
        job = await service.retry_job(job_id)
    except JobNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except JobRetryError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return JobRetryResponse(
        id=job.id,
        status=job.status,
        attempts=job.attempts,
        message="Job re-enqueued successfully",
    )
