from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import ROOT_DIR
from app.core.dependencies import (
    DbSessionDep,
    EmbeddingProviderDep,
    IndexingQueueDep,
    IngestionQueueDep,
    LLMClientDep,
    SettingsDep,
    VectorStoreDep,
)
from app.db.repositories import KnowledgeBaseRepository
from app.services.admin import AdminDocumentService
from app.services.chunks import ChunkPreviewService
from app.services.documents import DocumentUploadService
from app.services.rag import AnswerGenerationNotConfiguredError, RAGService


templates = Jinja2Templates(directory=str(ROOT_DIR / "templates"))
router = APIRouter(tags=["ui"])


@router.get("/", response_class=HTMLResponse)
def admin_documents_page(request: Request, db_session: DbSessionDep, settings: SettingsDep):
    selected_knowledge_base = request.query_params.get("knowledge_base_name", "default")
    result = AdminDocumentService(db_session, settings).list_documents(selected_knowledge_base)
    return templates.TemplateResponse(
        request,
        "documents.html",
        {
            "documents": result.documents,
            "knowledge_bases": result.knowledge_bases,
            "selected_knowledge_base": selected_knowledge_base,
            "page_title": "文档管理",
            "message": request.query_params.get("message"),
        },
    )


@router.post("/ui/documents/upload", response_class=HTMLResponse)
def upload_document_page(
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form(default="unknown"),
    knowledge_base_name: str = Form(default="default"),
    db_session: DbSessionDep = None,
    settings: SettingsDep = None,
    ingestion_queue: IngestionQueueDep = None,
):
    try:
        DocumentUploadService(db_session, settings, ingestion_queue).upload(
            file=file,
            document_type=document_type,
            knowledge_base_name=knowledge_base_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return admin_documents_page(request, db_session=db_session, settings=settings)


@router.get("/ui/documents/{document_id}", response_class=HTMLResponse)
def document_detail_page(request: Request, document_id: str, db_session: DbSessionDep, settings: SettingsDep):
    admin_service = AdminDocumentService(db_session, settings)
    try:
        document = admin_service.get_document(document_id)
        chunks = ChunkPreviewService(db_session).list_document_chunks(document_id).items
        jobs = admin_service.list_jobs(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    return templates.TemplateResponse(
        request,
        "document_detail.html",
        {
            "document": document,
            "chunks": chunks,
            "jobs": jobs,
            "page_title": "Chunk Preview",
            "message": request.query_params.get("message"),
        },
    )


@router.get("/ui/rag", response_class=HTMLResponse)
def rag_page(request: Request, db_session: DbSessionDep):
    knowledge_base_name = request.query_params.get("knowledge_base_name", "default")
    knowledge_bases = list(KnowledgeBaseRepository(db_session).list())
    knowledge_base_id = _resolve_knowledge_base_id(db_session, knowledge_base_name)
    return templates.TemplateResponse(
        request,
        "rag.html",
        {
            "page_title": "RAG 问答",
            "result": None,
            "query": "",
            "show_rewrite": False,
            "use_reranker": True,
            "knowledge_bases": knowledge_bases,
            "knowledge_base_name": knowledge_base_name,
            "knowledge_base_id": knowledge_base_id or "",
            "session_id": request.query_params.get("session_id", ""),
        },
    )


@router.post("/ui/rag", response_class=HTMLResponse)
def rag_page_submit(
    request: Request,
    query: str = Form(...),
    show_rewrite: str | None = Form(default=None),
    use_reranker: str | None = Form(default=None),
    knowledge_base_name: str = Form(default="default"),
    session_id: str = Form(default=""),
    db_session: DbSessionDep = None,
    settings: SettingsDep = None,
    embedding_provider: EmbeddingProviderDep = None,
    vector_store: VectorStoreDep = None,
    llm_client: LLMClientDep = None,
):
    result = None
    error_message = None
    knowledge_base_id = _resolve_knowledge_base_id(db_session, knowledge_base_name)
    try:
        result = RAGService(
            session=db_session,
            settings=settings,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            llm_client=llm_client,
        ).answer(
            query=query,
            top_k=5,
            knowledge_base_id=knowledge_base_id,
            use_reranker=use_reranker == "on",
            session_id=session_id or None,
        )
    except AnswerGenerationNotConfiguredError as exc:
        error_message = str(exc)
    return templates.TemplateResponse(
        request,
        "rag.html",
        {
            "page_title": "RAG 问答",
            "result": result,
            "error_message": error_message,
            "query": query,
            "show_rewrite": show_rewrite == "on",
            "use_reranker": use_reranker == "on",
            "knowledge_bases": list(KnowledgeBaseRepository(db_session).list()),
            "knowledge_base_name": knowledge_base_name,
            "knowledge_base_id": knowledge_base_id or "",
            "session_id": session_id,
        },
    )


@router.post("/ui/documents/{document_id}/toggle", response_class=HTMLResponse)
def toggle_document(
    request: Request,
    document_id: str,
    action: str = Form(...),
    db_session: DbSessionDep = None,
    settings: SettingsDep = None,
):
    service = AdminDocumentService(db_session, settings)
    try:
        if action == "enable":
            service.set_enabled(document_id, True)
        elif action == "disable":
            service.set_enabled(document_id, False)
        else:
            raise ValueError("Unsupported action")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return document_detail_page(request, document_id=document_id, db_session=db_session, settings=settings)


@router.post("/ui/documents/{document_id}/reindex", response_class=HTMLResponse)
def reindex_document_page(
    request: Request,
    document_id: str,
    db_session: DbSessionDep = None,
    indexing_queue: IndexingQueueDep = None,
    settings: SettingsDep = None,
):
    try:
        AdminDocumentService(db_session, settings).enqueue_index_rebuild(document_id, indexing_queue)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return document_detail_page(request, document_id=document_id, db_session=db_session, settings=settings)


@router.post("/ui/documents/{document_id}/delete", response_class=HTMLResponse)
def delete_document_page(
    request: Request,
    document_id: str,
    db_session: DbSessionDep = None,
    settings: SettingsDep = None,
):
    try:
        AdminDocumentService(db_session, settings).delete_document(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return admin_documents_page(request, db_session=db_session, settings=settings)


@router.post("/ui/documents/{document_id}/retry", response_class=HTMLResponse)
def retry_document_page(
    request: Request,
    document_id: str,
    job_id: str = Form(...),
    db_session: DbSessionDep = None,
    ingestion_queue: IngestionQueueDep = None,
    indexing_queue: IndexingQueueDep = None,
    settings: SettingsDep = None,
):
    try:
        AdminDocumentService(db_session, settings).retry_failed_job(job_id, document_id, ingestion_queue, indexing_queue)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail in {"Document not found", "Job not found for document"} else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return document_detail_page(request, document_id=document_id, db_session=db_session, settings=settings)


def _resolve_knowledge_base_id(db_session, knowledge_base_name: str) -> str | None:
    knowledge_base = KnowledgeBaseRepository(db_session).get_by_name(knowledge_base_name)
    if knowledge_base is None:
        return None
    return str(knowledge_base.id)
