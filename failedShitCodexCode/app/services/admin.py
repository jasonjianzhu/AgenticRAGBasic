from __future__ import annotations

from pathlib import Path
import uuid
from dataclasses import dataclass

from typing import Any

from qdrant_client import QdrantClient
from rq import Retry
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Document, JobLog
from app.db.repositories import DocumentRepository, JobLogRepository, KnowledgeBaseRepository
from app.jobs.status import sync_job_log_from_rq, sync_job_logs_from_rq
from app.jobs.tasks import ingest_document, index_document
from app.jobs.types import TaskQueue
from app.rag.vector_store.qdrant import QdrantVectorStore


@dataclass(frozen=True)
class DocumentListItem:
    document: Document
    latest_job: JobLog | None


@dataclass(frozen=True)
class DocumentListResult:
    knowledge_bases: list[KnowledgeBase]
    documents: list[DocumentListItem]


class AdminDocumentService:
    def __init__(self, session: Session, settings: Settings | None = None, vector_store: Any | None = None):
        self.session = session
        self.settings = settings or get_settings()
        self.vector_store = vector_store

    def list_documents(self, knowledge_base_name: str = "default") -> DocumentListResult:
        knowledge_bases = list(KnowledgeBaseRepository(self.session).list())
        kb = KnowledgeBaseRepository(self.session).get_by_name(knowledge_base_name)
        if kb is None:
            return DocumentListResult(knowledge_bases=knowledge_bases, documents=[])
        document_repository = DocumentRepository(self.session)
        job_repository = JobLogRepository(self.session)
        documents = []
        for document in document_repository.list_by_knowledge_base(kb.id):
            latest_job = job_repository.get_latest_for_document(document.id)
            if latest_job is not None and sync_job_log_from_rq(self.session, latest_job, self.settings):
                self.session.commit()
                self.session.refresh(document)
                self.session.refresh(latest_job)
            documents.append(
                DocumentListItem(
                    document=document,
                    latest_job=latest_job,
                )
            )
        return DocumentListResult(knowledge_bases=knowledge_bases, documents=documents)

    def get_document(self, document_id: str | uuid.UUID) -> Document:
        document = DocumentRepository(self.session).get(uuid.UUID(str(document_id)))
        if document is None:
            raise ValueError(f"Document not found: {document_id}")
        return document

    def list_jobs(self, document_id: str | uuid.UUID) -> list[JobLog]:
        document_uuid = uuid.UUID(str(document_id))
        self.get_document(document_uuid)
        jobs = list(JobLogRepository(self.session).list_by_document(document_uuid))
        if sync_job_logs_from_rq(self.session, jobs, self.settings):
            self.session.commit()
            jobs = list(JobLogRepository(self.session).list_by_document(document_uuid))
        return jobs

    def set_enabled(self, document_id: str | uuid.UUID, is_enabled: bool) -> Document:
        document_uuid = uuid.UUID(str(document_id))
        document = DocumentRepository(self.session).set_enabled(document_uuid, is_enabled)
        self.session.commit()
        self.session.refresh(document)
        return document

    def enqueue_index_rebuild(self, document_id: str | uuid.UUID, indexing_queue: TaskQueue) -> JobLog:
        document = self.get_document(document_id)
        repository = JobLogRepository(self.session)
        job_log = repository.create(
            queue_name=indexing_queue.name,
            job_type="index_document",
            document_id=document.id,
            payload={"document_id": str(document.id), "reason": "manual_rebuild"},
        )
        enqueued_job = indexing_queue.enqueue(
            index_document,
            str(document.id),
            str(job_log.id),
            job_timeout=self.settings.rq_indexing_timeout_seconds,
            retry=Retry(max=self.settings.rq_max_retries),
        )
        repository.set_rq_job_id(job_log.id, enqueued_job.id)
        self.session.commit()
        self.session.refresh(job_log)
        return job_log

    def retry_failed_job(
        self,
        job_id: str | uuid.UUID,
        document_id: str | uuid.UUID,
        ingestion_queue: TaskQueue,
        indexing_queue: TaskQueue,
    ) -> JobLog:
        document = self.get_document(document_id)
        repository = JobLogRepository(self.session)
        retry_job = repository.get(uuid.UUID(str(job_id)))
        if retry_job is None or retry_job.document_id != document.id:
            raise ValueError("Job not found for document")
        if sync_job_log_from_rq(self.session, retry_job, self.settings):
            self.session.commit()
            self.session.refresh(retry_job)
        if retry_job.status != "failed":
            raise ValueError("Only failed jobs can be retried")

        repository.mark_retrying(retry_job.id, retry_job.error_message)
        if retry_job.job_type == "ingest_document":
            enqueued_job = ingestion_queue.enqueue(
                ingest_document,
                str(document.id),
                str(retry_job.id),
                job_timeout=self.settings.rq_ingestion_timeout_seconds,
                retry=Retry(max=self.settings.rq_max_retries),
            )
        elif retry_job.job_type == "index_document":
            enqueued_job = indexing_queue.enqueue(
                index_document,
                str(document.id),
                str(retry_job.id),
                job_timeout=self.settings.rq_indexing_timeout_seconds,
                retry=Retry(max=self.settings.rq_max_retries),
            )
        else:
            raise ValueError(f"Unsupported job type for retry: {retry_job.job_type}")
        repository.set_rq_job_id(retry_job.id, enqueued_job.id)
        self.session.commit()
        self.session.refresh(retry_job)
        return retry_job

    def delete_document(self, document_id: str | uuid.UUID) -> None:
        document = self.get_document(document_id)
        resolved_vector_store = self.vector_store
        if resolved_vector_store is None and self.settings.vector_store_backend != "memory":
            resolved_vector_store = QdrantVectorStore(
                client=QdrantClient(url=self.settings.qdrant_url, api_key=self.settings.qdrant_api_key),
                collection_name=self.settings.qdrant_collection_name,
                vector_size=self.settings.embedding_dimension,
                dense_vector_name=self.settings.qdrant_dense_vector_name,
                sparse_vector_name=self.settings.qdrant_sparse_vector_name,
            )
        if resolved_vector_store is not None:
            resolved_vector_store.delete_by_payload(self.settings.qdrant_collection_name, {"document_id": str(document.id)})
        storage_path = Path(document.storage_path)
        if storage_path.exists():
            storage_path.unlink()
        DocumentRepository(self.session).delete(document.id)
        self.session.commit()
