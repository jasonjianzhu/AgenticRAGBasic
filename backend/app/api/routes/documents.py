"""Document API routes for upload, list, detail, enable/disable, delete, and chunk preview."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.documents import (
    ChunkListResponse,
    ChunkResponse,
    DocumentListResponse,
    DocumentResponse,
)
from app.core.config import Settings, get_settings
from app.core.dependencies import get_db
from app.db.repositories.chunks import ChunkRepository
from app.db.repositories.documents import DocumentRepository
from app.services.ingestion import (
    FileTooLargeError,
    IngestionService,
    InvalidFileError,
    KBNotFoundError,
)
from app.storage.base import StorageBackend
from app.storage.local import LocalStorage

router = APIRouter(prefix="/documents", tags=["documents"])


def get_storage(settings: Settings = Depends(get_settings)) -> StorageBackend:
    """Dependency to get storage backend."""
    return LocalStorage(base_dir=settings.upload_dir)


def _get_ingestion_service(
    session: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> IngestionService:
    """Dependency to get ingestion service."""
    return IngestionService(session, storage, settings)


@router.post("/upload", response_model=DocumentResponse, responses={200: {"model": DocumentResponse}, 201: {"model": DocumentResponse}})
async def upload_document(
    file: UploadFile = File(...),
    knowledge_base_id: uuid.UUID = Form(...),
    document_type: str = Form(default="unknown"),
    parser_profile: str | None = Form(default=None),
    service: IngestionService = Depends(_get_ingestion_service),
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

    response_data = DocumentResponse.model_validate(doc)
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
) -> None:
    """Soft-delete a document."""
    repo = DocumentRepository(session)
    doc = await repo.get_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {doc_id} not found")
    await repo.soft_delete(doc)


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
