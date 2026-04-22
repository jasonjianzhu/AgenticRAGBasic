"""Knowledge base API routes."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.api.schemas.kb import (
    KBCreate,
    KBDetailResponse,
    KBListResponse,
    KBResponse,
    KBStatistics,
    KBUpdate,
)
from app.common.core.config import Settings, get_settings
from app.common.core.dependencies import get_db
from app.common.db.repositories.documents import DocumentRepository
from app.knowledge.jobs.queue import InMemoryJobQueue, JobQueue
from app.knowledge.services.jobs import JobService
from app.knowledge.services.kb import KBDuplicateNameError, KBNotFoundError, KBService

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

# Module-level default job queue (overridable via dependency)
_default_kb_job_queue: JobQueue = InMemoryJobQueue()


def get_kb_job_queue() -> JobQueue:
    """Dependency to get job queue for KB routes."""
    return _default_kb_job_queue


def _get_service(session: AsyncSession = Depends(get_db)) -> KBService:
    """Dependency to get KB service."""
    return KBService(session)


def _get_job_service(
    session: AsyncSession = Depends(get_db),
    job_queue: JobQueue = Depends(get_kb_job_queue),
    settings: Settings = Depends(get_settings),
) -> JobService:
    """Dependency to get job service for KB routes."""
    return JobService(session, job_queue, settings)


@router.post("", response_model=KBResponse, status_code=status.HTTP_201_CREATED)
async def create_kb(
    payload: KBCreate,
    service: KBService = Depends(_get_service),
) -> KBResponse:
    """Create a new knowledge base."""
    try:
        kb = await service.create_kb(
            name=payload.name,
            description=payload.description,
            settings=payload.settings.model_dump(),
        )
    except KBDuplicateNameError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return KBResponse.model_validate(kb)


@router.get("", response_model=KBListResponse)
async def list_kbs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    service: KBService = Depends(_get_service),
) -> KBListResponse:
    """List all knowledge bases."""
    kbs, total = await service.list_kbs(skip=skip, limit=limit)
    items = [KBResponse.model_validate(kb) for kb in kbs]
    return KBListResponse(items=items, total=total)


@router.get("/{kb_id}", response_model=KBDetailResponse)
async def get_kb(
    kb_id: uuid.UUID,
    service: KBService = Depends(_get_service),
) -> KBDetailResponse:
    """Get knowledge base detail with statistics."""
    try:
        kb, stats = await service.get_kb_with_stats(kb_id)
    except KBNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    response = KBDetailResponse.model_validate(kb)
    response.statistics = KBStatistics(**stats)
    return response


@router.put("/{kb_id}", response_model=KBResponse)
async def update_kb(
    kb_id: uuid.UUID,
    payload: KBUpdate,
    service: KBService = Depends(_get_service),
) -> KBResponse:
    """Update a knowledge base."""
    update_data = {}
    if payload.name is not None:
        update_data["name"] = payload.name
    if payload.description is not None:
        update_data["description"] = payload.description
    if payload.settings is not None:
        update_data["settings"] = payload.settings.model_dump()
    if payload.is_active is not None:
        update_data["is_active"] = payload.is_active

    try:
        kb = await service.update_kb(kb_id, **update_data)
    except KBNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except KBDuplicateNameError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return KBResponse.model_validate(kb)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb(
    kb_id: uuid.UUID,
    service: KBService = Depends(_get_service),
) -> None:
    """Delete a knowledge base."""
    try:
        await service.delete_kb(kb_id)
    except KBNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{kb_id}/build", status_code=status.HTTP_202_ACCEPTED)
async def build_index(
    kb_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    kb_service: KBService = Depends(_get_service),
    job_service: JobService = Depends(_get_job_service),
):
    """Trigger index rebuild for all ready/chunked documents in a KB.

    Enqueues indexing jobs for each eligible document.
    Returns the list of enqueued job IDs.
    """
    # Verify KB exists
    try:
        await kb_service.get_kb(kb_id)
    except KBNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    # Find all documents with status "chunked" or "ready"
    doc_repo = DocumentRepository(session)
    chunked_docs = await doc_repo.list_documents(
        knowledge_base_id=kb_id, status="chunked", limit=10000
    )
    ready_docs = await doc_repo.list_documents(
        knowledge_base_id=kb_id, status="ready", limit=10000
    )

    all_docs = list(chunked_docs) + list(ready_docs)
    job_ids = []

    for doc in all_docs:
        job_log = await job_service.enqueue_indexing(doc.id)
        job_ids.append(str(job_log.id))

    return {
        "kb_id": str(kb_id),
        "jobs_enqueued": len(job_ids),
        "job_ids": job_ids,
    }
