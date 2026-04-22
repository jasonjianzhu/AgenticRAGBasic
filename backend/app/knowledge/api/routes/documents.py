"""Document API routes for upload, list, detail, enable/disable, delete, and chunk preview."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.api.schemas.documents import (
    ChunkListResponse,
    ChunkResponse,
    DocumentListResponse,
    DocumentResponse,
)
from app.common.core.config import Settings, get_settings
from app.common.core.dependencies import get_db
from app.common.db.repositories.chunks import ChunkRepository
from app.common.db.repositories.documents import DocumentRepository
from app.knowledge.jobs.queue import InMemoryJobQueue, JobQueue
from app.knowledge.services.ingestion import (
    FileTooLargeError,
    IngestionService,
    InvalidFileError,
    KBNotFoundError,
)
from app.knowledge.services.jobs import JobService
from app.common.storage.base import StorageBackend
from app.common.storage.local import LocalStorage

router = APIRouter(prefix="/documents", tags=["documents"])

# Module-level default job queue (overridable via dependency)
_default_job_queue: JobQueue = InMemoryJobQueue()


def get_storage(settings: Settings = Depends(get_settings)) -> StorageBackend:
    """Dependency to get storage backend."""
    return LocalStorage(base_dir=settings.upload_dir)


def get_job_queue() -> JobQueue:
    """Dependency to get job queue."""
    return _default_job_queue


def _get_ingestion_service(
    session: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> IngestionService:
    """Dependency to get ingestion service."""
    return IngestionService(session, storage, settings)


def _get_job_service(
    session: AsyncSession = Depends(get_db),
    job_queue: JobQueue = Depends(get_job_queue),
    settings: Settings = Depends(get_settings),
) -> JobService:
    """Dependency to get job service."""
    return JobService(session, job_queue, settings)


@router.post("/upload", response_model=DocumentResponse, responses={200: {"model": DocumentResponse}, 201: {"model": DocumentResponse}})
async def upload_document(
    file: UploadFile = File(...),
    knowledge_base_id: uuid.UUID = Form(...),
    document_type: str = Form(default="unknown"),
    parser_profile: str | None = Form(default=None),
    service: IngestionService = Depends(_get_ingestion_service),
    job_service: JobService = Depends(_get_job_service),
):
    """Upload a document to a knowledge base."""
    file_data = await file.read()

    try:
        doc, is_new = await service.upload_document(
            knowledge_base_id=knowledge_base_id,
            filename=file.filename or "unnamed.pdf",
            content_type=file.content_type,
            file_data=file_data,
            document_type=document_type,
            parser_profile=parser_profile,
        )
    except KBNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidFileError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except FileTooLargeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Enqueue ingestion job for new documents
    job_id = None
    if is_new:
        job_log = await job_service.enqueue_ingestion(
            doc.id,
            parser_profile=parser_profile or "balanced",
        )
        job_id = job_log.id

    response_data = DocumentResponse.model_validate(doc)
    response_data.job_id = job_id
    status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
    return JSONResponse(
        content=response_data.model_dump(mode="json"),
        status_code=status_code,
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    knowledge_base_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    """List documents with optional filters."""
    repo = DocumentRepository(session)
    docs = await repo.list_documents(
        knowledge_base_id=knowledge_base_id,
        status=status_filter,
        skip=skip,
        limit=limit,
    )
    total = await repo.count_documents(
        knowledge_base_id=knowledge_base_id,
        status=status_filter,
    )
    items = [DocumentResponse.model_validate(d) for d in docs]
    return DocumentListResponse(items=items, total=total)


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Get document detail."""
    repo = DocumentRepository(session)
    doc = await repo.get_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {doc_id} not found")
    return DocumentResponse.model_validate(doc)


@router.get("/{doc_id}/file")
async def get_document_file(
    doc_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    """Download the original PDF file for preview."""
    from urllib.parse import quote

    from fastapi.responses import Response

    repo = DocumentRepository(session)
    doc = await repo.get_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {doc_id} not found")

    try:
        data = await storage.read(doc.storage_path)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to read file: {e}")

    # URL-encode filename for Content-Disposition header (handles Chinese chars)
    encoded_name = quote(doc.source_filename)

    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}"},
    )


@router.post("/{doc_id}/enable", response_model=DocumentResponse)
async def enable_document(
    doc_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Enable a document."""
    repo = DocumentRepository(session)
    doc = await repo.get_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {doc_id} not found")
    doc = await repo.update(doc, is_enabled=True)
    return DocumentResponse.model_validate(doc)


@router.post("/{doc_id}/disable", response_model=DocumentResponse)
async def disable_document(
    doc_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Disable a document."""
    repo = DocumentRepository(session)
    doc = await repo.get_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {doc_id} not found")
    doc = await repo.update(doc, is_enabled=False)
    return DocumentResponse.model_validate(doc)


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> None:
    """Hard-delete a document and clean up all related data.

    Deletes: DB record + chunks + versions + local files + Qdrant points.
    """
    repo = DocumentRepository(session)
    doc = await repo.get_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {doc_id} not found")

    storage_path = doc.storage_path
    kb_id = doc.knowledge_base_id

    # Collect qdrant_point_ids from chunks before deleting
    chunk_repo = ChunkRepository(session)
    chunks = await chunk_repo.list_by_document(doc_id, limit=100000)
    point_ids = [c.qdrant_point_id for c in chunks if c.qdrant_point_id]

    # Hard delete: cascades to chunks and versions via FK ON DELETE CASCADE
    from sqlalchemy import delete
    from app.common.db.models import Document
    await session.execute(delete(Document).where(Document.id == doc_id))
    await session.flush()

    # Best-effort local file cleanup
    try:
        await storage.delete(storage_path)
    except Exception:
        import structlog
        structlog.get_logger(__name__).warning(
            "file_cleanup_failed",
            doc_id=str(doc_id),
            storage_path=storage_path,
        )

    # Best-effort parsed output cleanup
    try:
        import shutil
        from pathlib import Path
        from app.common.core.config import get_settings

        settings = get_settings()
        parsed_doc_dir = Path(str(settings.parsed_dir)) / str(kb_id) / str(doc_id)
        if parsed_doc_dir.exists():
            shutil.rmtree(parsed_doc_dir)
    except Exception:
        import structlog
        structlog.get_logger(__name__).warning(
            "parsed_cleanup_failed",
            doc_id=str(doc_id),
        )

    # Best-effort Qdrant cleanup
    if point_ids:
        try:
            from app.common.core.config import get_settings
            from app.common.rag.vector_store.qdrant import QdrantVectorStore

            settings = get_settings()
            vs = QdrantVectorStore(
                url=settings.qdrant_url,
                collection_name=settings.qdrant_collection_name,
                api_key=settings.qdrant_api_key,
                dense_dim=settings.embedding_dimension,
            )
            await vs.delete(point_ids)
            await vs.close()
        except Exception:
            import structlog
            structlog.get_logger(__name__).warning(
                "qdrant_cleanup_failed",
                doc_id=str(doc_id),
                point_count=len(point_ids),
            )


@router.get("/{doc_id}/chunks", response_model=ChunkListResponse)
async def list_document_chunks(
    doc_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_db),
) -> ChunkListResponse:
    """List chunks for a document (preview)."""
    doc_repo = DocumentRepository(session)
    doc = await doc_repo.get_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {doc_id} not found")

    chunk_repo = ChunkRepository(session)
    chunks = await chunk_repo.list_by_document(doc_id, skip=skip, limit=limit)
    items = [ChunkResponse.model_validate(c) for c in chunks]
    return ChunkListResponse(items=items, total=len(items))
