from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.schemas.documents import DocumentChunkPreviewResponse, DocumentDetailResponse, DocumentJobResponse, DocumentUploadResponse
from app.core.dependencies import DbSessionDep, IndexingQueueDep, IngestionQueueDep, SettingsDep
from app.services.admin import AdminDocumentService
from app.services.chunks import ChunkPreviewService
from app.services.documents import DocumentUploadService


router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
def upload_document(
    settings: SettingsDep,
    db_session: DbSessionDep,
    ingestion_queue: IngestionQueueDep,
    file: UploadFile = File(...),
    document_type: str = "unknown",
    knowledge_base_name: str = "default",
) -> DocumentUploadResponse:
    service = DocumentUploadService(db_session, settings, ingestion_queue)
    try:
        document = service.upload(file=file, document_type=document_type, knowledge_base_name=knowledge_base_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DocumentUploadResponse.model_validate(document)


@router.get("", response_model=list[DocumentUploadResponse])
def list_documents(
    db_session: DbSessionDep,
    settings: SettingsDep,
    knowledge_base_name: str = "default",
) -> list[DocumentUploadResponse]:
    documents = AdminDocumentService(db_session, settings).list_documents(knowledge_base_name).documents
    return [DocumentUploadResponse.model_validate(item.document) for item in documents]


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(document_id: UUID, db_session: DbSessionDep, settings: SettingsDep) -> DocumentDetailResponse:
    service = AdminDocumentService(db_session, settings)
    try:
        document = service.get_document(document_id)
        jobs = service.list_jobs(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    return DocumentDetailResponse.model_validate(
        {
            **DocumentUploadResponse.model_validate(document).model_dump(),
            "jobs": [DocumentJobResponse.model_validate(job).model_dump() for job in jobs],
        }
    )


@router.post("/{document_id}/enable", response_model=DocumentUploadResponse)
def enable_document(document_id: UUID, db_session: DbSessionDep, settings: SettingsDep) -> DocumentUploadResponse:
    try:
        document = AdminDocumentService(db_session, settings).set_enabled(document_id, True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    return DocumentUploadResponse.model_validate(document)


@router.post("/{document_id}/disable", response_model=DocumentUploadResponse)
def disable_document(document_id: UUID, db_session: DbSessionDep, settings: SettingsDep) -> DocumentUploadResponse:
    try:
        document = AdminDocumentService(db_session, settings).set_enabled(document_id, False)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    return DocumentUploadResponse.model_validate(document)


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: UUID, db_session: DbSessionDep, settings: SettingsDep) -> None:
    try:
        AdminDocumentService(db_session, settings).delete_document(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc


@router.post("/{document_id}/reindex", response_model=DocumentJobResponse, status_code=202)
def reindex_document(
    document_id: UUID,
    db_session: DbSessionDep,
    indexing_queue: IndexingQueueDep,
    settings: SettingsDep,
) -> DocumentJobResponse:
    try:
        job = AdminDocumentService(db_session, settings).enqueue_index_rebuild(document_id, indexing_queue)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    return DocumentJobResponse.model_validate(job)


@router.post("/{document_id}/jobs/{job_id}/retry", response_model=DocumentJobResponse, status_code=202)
def retry_document_job(
    document_id: UUID,
    job_id: UUID,
    db_session: DbSessionDep,
    ingestion_queue: IngestionQueueDep,
    indexing_queue: IndexingQueueDep,
    settings: SettingsDep,
) -> DocumentJobResponse:
    try:
        job = AdminDocumentService(db_session, settings).retry_failed_job(job_id, document_id, ingestion_queue, indexing_queue)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail in {"Document not found", "Job not found for document"} else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return DocumentJobResponse.model_validate(job)


@router.get("/{document_id}/chunks", response_model=DocumentChunkPreviewResponse)
def list_document_chunks(
    document_id: UUID,
    db_session: DbSessionDep,
    chunk_type: str | None = None,
) -> DocumentChunkPreviewResponse:
    service = ChunkPreviewService(db_session)
    try:
        result = service.list_document_chunks(document_id=document_id, chunk_type=chunk_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    return DocumentChunkPreviewResponse.model_validate(result)
