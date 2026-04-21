from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session
from rq import Retry

from app.core.config import Settings
from app.db.models import Document
from app.db.repositories import DocumentRepository, JobLogRepository, KnowledgeBaseRepository
from app.jobs.status import ACTIVE_DB_JOB_STATUSES, sync_job_logs_from_rq
from app.jobs.tasks import ingest_document
from app.jobs.types import TaskQueue


DEFAULT_KNOWLEDGE_BASE_NAME = "default"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredUpload:
    source_filename: str
    storage_path: str
    content_hash: str
    mime_type: str
    file_size_bytes: int


def sanitize_filename(filename: str) -> str:
    filename = Path(filename).name.strip()
    if not filename:
        return "document.pdf"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", filename)


def title_from_filename(filename: str) -> str:
    path = Path(filename)
    return path.stem or filename


class DocumentUploadService:
    def __init__(self, session: Session, settings: Settings, ingestion_queue: TaskQueue):
        self.session = session
        self.settings = settings
        self.ingestion_queue = ingestion_queue

    def upload(self, file: UploadFile, document_type: str = "unknown", knowledge_base_name: str = DEFAULT_KNOWLEDGE_BASE_NAME) -> Document:
        logger.info(
            "Upload requested: filename=%s content_type=%s document_type=%s knowledge_base=%s",
            file.filename,
            file.content_type,
            document_type,
            knowledge_base_name,
        )
        stored_upload = self._store_upload(file)
        logger.info(
            "Upload stored: filename=%s path=%s size=%s hash=%s",
            stored_upload.source_filename,
            stored_upload.storage_path,
            stored_upload.file_size_bytes,
            stored_upload.content_hash,
        )
        knowledge_base = self._get_or_create_knowledge_base(knowledge_base_name)
        document_repository = DocumentRepository(self.session)

        existing = document_repository.get_by_hash(
            knowledge_base_id=knowledge_base.id,
            content_hash=stored_upload.content_hash,
        )
        if existing is not None:
            logger.info(
                "Duplicate upload detected: document_id=%s filename=%s hash=%s",
                existing.id,
                stored_upload.source_filename,
                stored_upload.content_hash,
            )
            existing = self._refresh_duplicate_upload_storage(existing, stored_upload, document_repository)
            self._enqueue_if_duplicate_needs_processing(existing)
            return existing

        document = document_repository.create_uploaded(
            knowledge_base_id=knowledge_base.id,
            title=title_from_filename(stored_upload.source_filename),
            source_filename=stored_upload.source_filename,
            storage_path=stored_upload.storage_path,
            content_hash=stored_upload.content_hash,
            mime_type=stored_upload.mime_type,
            file_size_bytes=stored_upload.file_size_bytes,
            document_type=document_type,
        )
        logger.info(
            "Document record created: document_id=%s knowledge_base_id=%s filename=%s",
            document.id,
            knowledge_base.id,
            stored_upload.source_filename,
        )
        self._enqueue_ingestion_job(document=document, reason="upload_created")
        self.session.commit()
        self.session.refresh(document)
        return document

    def _enqueue_ingestion_job(self, document: Document, reason: str) -> None:
        job_log = JobLogRepository(self.session).create(
            queue_name=self.ingestion_queue.name,
            job_type="ingest_document",
            document_id=document.id,
            payload={"document_id": str(document.id), "reason": reason},
        )
        logger.info(
            "Enqueuing ingestion job: document_id=%s job_log_id=%s queue=%s timeout=%s retries=%s",
            document.id,
            job_log.id,
            self.ingestion_queue.name,
            self.settings.rq_ingestion_timeout_seconds,
            self.settings.rq_max_retries,
        )
        try:
            enqueued_job = self.ingestion_queue.enqueue(
                ingest_document,
                str(document.id),
                str(job_log.id),
                job_timeout=self.settings.rq_ingestion_timeout_seconds,
                retry=Retry(max=self.settings.rq_max_retries),
            )
        except Exception:
            logger.exception(
                "Failed to enqueue ingestion job: document_id=%s job_log_id=%s queue=%s",
                document.id,
                job_log.id,
                self.ingestion_queue.name,
            )
            raise
        JobLogRepository(self.session).set_rq_job_id(job_log.id, enqueued_job.id)
        logger.info(
            "Ingestion job enqueued: document_id=%s job_log_id=%s rq_job_id=%s queue=%s",
            document.id,
            job_log.id,
            enqueued_job.id,
            self.ingestion_queue.name,
        )

    def _enqueue_if_duplicate_needs_processing(self, document: Document) -> None:
        if document.status == "ready":
            return

        job_repository = JobLogRepository(self.session)
        jobs = list(job_repository.list_by_document(document.id))
        if sync_job_logs_from_rq(self.session, jobs, self.settings):
            self.session.commit()
            self.session.refresh(document)

        active_jobs = [job for job in jobs if job.status in ACTIVE_DB_JOB_STATUSES]
        if active_jobs:
            logger.info(
                "Duplicate upload has active processing job: document_id=%s job_ids=%s",
                document.id,
                [str(job.id) for job in active_jobs],
            )
            return

        logger.warning(
            "Duplicate upload found unfinished document without active job, re-enqueuing ingestion: document_id=%s status=%s",
            document.id,
            document.status,
        )
        self._enqueue_ingestion_job(document=document, reason="duplicate_upload_requeue")
        self.session.commit()
        self.session.refresh(document)

    def _refresh_duplicate_upload_storage(
        self,
        document: Document,
        stored_upload: StoredUpload,
        document_repository: DocumentRepository,
    ) -> Document:
        if document.status == "ready" and Path(document.storage_path).exists():
            return document

        if (
            document.storage_path == stored_upload.storage_path
            and document.source_filename == stored_upload.source_filename
            and document.file_size_bytes == stored_upload.file_size_bytes
        ):
            return document

        logger.info(
            "Refreshing duplicate upload storage: document_id=%s old_path=%s new_path=%s status=%s",
            document.id,
            document.storage_path,
            stored_upload.storage_path,
            document.status,
        )
        return document_repository.update_upload_storage(
            document.id,
            source_filename=stored_upload.source_filename,
            storage_path=stored_upload.storage_path,
            mime_type=stored_upload.mime_type,
            file_size_bytes=stored_upload.file_size_bytes,
        )

    def _get_or_create_knowledge_base(self, knowledge_base_name: str):
        repository = KnowledgeBaseRepository(self.session)
        knowledge_base = repository.get_by_name(knowledge_base_name)
        if knowledge_base is not None:
            return knowledge_base
        return repository.create(name=knowledge_base_name, description=f"Knowledge base: {knowledge_base_name}")

    def _store_upload(self, file: UploadFile) -> StoredUpload:
        source_filename = sanitize_filename(file.filename or "document.pdf")
        content = file.file.read()
        mime_type = file.content_type or "application/octet-stream"
        if mime_type != "application/pdf":
            logger.warning("Upload rejected: filename=%s content_type=%s reason=non_pdf", source_filename, mime_type)
            raise ValueError("Only PDF uploads are supported in phase 1")
        if len(content) > self.settings.max_upload_size_bytes:
            logger.warning(
                "Upload rejected: filename=%s size=%s max_size=%s reason=too_large",
                source_filename,
                len(content),
                self.settings.max_upload_size_bytes,
            )
            raise ValueError("Uploaded file exceeds MAX_UPLOAD_SIZE_BYTES")
        content_hash = hashlib.sha256(content).hexdigest()
        storage_filename = f"{content_hash[:16]}-{uuid.uuid4().hex}-{source_filename}"
        storage_path = self.settings.upload_dir / storage_filename
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(content)
        return StoredUpload(
            source_filename=source_filename,
            storage_path=str(storage_path),
            content_hash=content_hash,
            mime_type=mime_type,
            file_size_bytes=len(content),
        )
