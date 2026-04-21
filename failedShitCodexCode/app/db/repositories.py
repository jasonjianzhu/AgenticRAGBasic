from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document, DocumentVersion, JobLog, KnowledgeBase, QueryLog


ModelT = TypeVar("ModelT")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: Session):
        self.session = session

    def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        self.session.flush()
        return instance

    def get(self, id_: uuid.UUID) -> ModelT | None:
        return self.session.get(self.model, id_)

    def list(self, statement: Select[tuple[ModelT]] | None = None) -> Sequence[ModelT]:
        query = statement if statement is not None else select(self.model)
        return self.session.scalars(query).all()


class KnowledgeBaseRepository(BaseRepository[KnowledgeBase]):
    model = KnowledgeBase

    def create(self, name: str, description: str | None = None, settings: dict[str, Any] | None = None) -> KnowledgeBase:
        return self.add(
            KnowledgeBase(
                name=name,
                description=description,
                settings=settings or {},
            )
        )

    def get_by_name(self, name: str) -> KnowledgeBase | None:
        return self.session.scalar(select(KnowledgeBase).where(KnowledgeBase.name == name))


class DocumentRepository(BaseRepository[Document]):
    model = Document

    def create_uploaded(
        self,
        *,
        knowledge_base_id: uuid.UUID,
        title: str,
        source_filename: str,
        storage_path: str,
        content_hash: str,
        mime_type: str,
        file_size_bytes: int,
        document_type: str = "unknown",
        metadata: dict[str, Any] | None = None,
    ) -> Document:
        return self.add(
            Document(
                knowledge_base_id=knowledge_base_id,
                title=title,
                source_filename=source_filename,
                storage_path=storage_path,
                content_hash=content_hash,
                mime_type=mime_type,
                file_size_bytes=file_size_bytes,
                document_type=document_type,
                metadata_=metadata or {},
            )
        )

    def get_by_hash(self, *, knowledge_base_id: uuid.UUID, content_hash: str) -> Document | None:
        return self.session.scalar(
            select(Document).where(
                Document.knowledge_base_id == knowledge_base_id,
                Document.content_hash == content_hash,
            )
        )

    def list_by_knowledge_base(self, knowledge_base_id: uuid.UUID) -> Sequence[Document]:
        return self.session.scalars(
            select(Document)
            .where(Document.knowledge_base_id == knowledge_base_id)
            .order_by(Document.created_at.desc())
        ).all()

    def delete(self, document_id: uuid.UUID) -> None:
        document = self._require(document_id)
        self.session.delete(document)
        self.session.flush()

    def update_status(self, document_id: uuid.UUID, status: str) -> Document:
        document = self._require(document_id)
        document.status = status
        document.updated_at = utc_now()
        self.session.flush()
        return document

    def update_document_type(self, document_id: uuid.UUID, document_type: str) -> Document:
        document = self._require(document_id)
        document.document_type = document_type
        document.updated_at = utc_now()
        self.session.flush()
        return document

    def update_upload_storage(
        self,
        document_id: uuid.UUID,
        *,
        source_filename: str,
        storage_path: str,
        mime_type: str,
        file_size_bytes: int,
    ) -> Document:
        document = self._require(document_id)
        document.source_filename = source_filename
        document.storage_path = storage_path
        document.mime_type = mime_type
        document.file_size_bytes = file_size_bytes
        document.updated_at = utc_now()
        self.session.flush()
        return document

    def set_enabled(self, document_id: uuid.UUID, is_enabled: bool) -> Document:
        document = self._require(document_id)
        document.is_enabled = is_enabled
        document.updated_at = utc_now()
        self.session.flush()
        return document

    def _require(self, document_id: uuid.UUID) -> Document:
        document = self.get(document_id)
        if document is None:
            raise ValueError(f"Document not found: {document_id}")
        return document


class DocumentVersionRepository(BaseRepository[DocumentVersion]):
    model = DocumentVersion

    def create(
        self,
        *,
        document_id: uuid.UUID,
        version_number: int,
        parser_profile: str = "balanced",
        parser_name: str | None = None,
        parsed_path: str | None = None,
        status: str = "created",
        metadata: dict[str, Any] | None = None,
    ) -> DocumentVersion:
        return self.add(
            DocumentVersion(
                document_id=document_id,
                version_number=version_number,
                parser_profile=parser_profile,
                parser_name=parser_name,
                parsed_path=parsed_path,
                status=status,
                metadata_=metadata or {},
            )
        )

    def get_latest_for_document(self, document_id: uuid.UUID) -> DocumentVersion | None:
        return self.session.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        )

    def update_status(self, version_id: uuid.UUID, status: str) -> DocumentVersion:
        version = self.get(version_id)
        if version is None:
            raise ValueError(f"Document version not found: {version_id}")
        version.status = status
        version.updated_at = utc_now()
        self.session.flush()
        return version

    def mark_parsed(self, version_id: uuid.UUID, parsed_path: str, metadata: dict[str, Any] | None = None) -> DocumentVersion:
        version = self.get(version_id)
        if version is None:
            raise ValueError(f"Document version not found: {version_id}")
        version.status = "parsed"
        version.parsed_path = parsed_path
        if metadata is not None:
            version.metadata_ = metadata
        version.updated_at = utc_now()
        self.session.flush()
        return version

    def mark_chunked(self, version_id: uuid.UUID, metadata: dict[str, Any] | None = None) -> DocumentVersion:
        version = self.get(version_id)
        if version is None:
            raise ValueError(f"Document version not found: {version_id}")
        version.status = "chunked"
        if metadata is not None:
            version.metadata_ = {**version.metadata_, **metadata}
        version.updated_at = utc_now()
        self.session.flush()
        return version


class ChunkRepository(BaseRepository[Chunk]):
    model = Chunk

    def create_many(self, chunks: Sequence[Chunk]) -> Sequence[Chunk]:
        self.session.add_all(chunks)
        self.session.flush()
        return chunks

    def list_by_document(
        self,
        document_id: uuid.UUID,
        chunk_type: str | None = None,
        document_version_id: uuid.UUID | None = None,
    ) -> Sequence[Chunk]:
        statement = select(Chunk).where(Chunk.document_id == document_id)
        if document_version_id is not None:
            statement = statement.where(Chunk.document_version_id == document_version_id)
        if chunk_type is not None:
            statement = statement.where(Chunk.chunk_type == chunk_type)
        return self.session.scalars(statement.order_by(Chunk.ordinal.asc())).all()

    def delete_by_document_version(self, document_version_id: uuid.UUID) -> int:
        chunks = self.session.scalars(select(Chunk).where(Chunk.document_version_id == document_version_id)).all()
        count = len(chunks)
        for chunk in chunks:
            self.session.delete(chunk)
        self.session.flush()
        return count


class JobLogRepository(BaseRepository[JobLog]):
    model = JobLog

    def create(
        self,
        *,
        queue_name: str,
        job_type: str,
        document_id: uuid.UUID | None = None,
        rq_job_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> JobLog:
        return self.add(
            JobLog(
                queue_name=queue_name,
                job_type=job_type,
                document_id=document_id,
                rq_job_id=rq_job_id,
                payload=payload or {},
            )
        )

    def set_rq_job_id(self, job_id: uuid.UUID, rq_job_id: str) -> JobLog:
        job = self._require(job_id)
        job.rq_job_id = rq_job_id
        job.updated_at = utc_now()
        self.session.flush()
        return job

    def mark_started(self, job_id: uuid.UUID) -> JobLog:
        job = self._require(job_id)
        job.status = "started"
        job.started_at = utc_now()
        job.attempts += 1
        job.updated_at = utc_now()
        self.session.flush()
        return job

    def mark_finished(self, job_id: uuid.UUID) -> JobLog:
        job = self._require(job_id)
        job.status = "finished"
        job.finished_at = utc_now()
        job.updated_at = utc_now()
        self.session.flush()
        return job

    def mark_failed(self, job_id: uuid.UUID, error_message: str) -> JobLog:
        job = self._require(job_id)
        job.status = "failed"
        job.error_message = error_message
        job.finished_at = utc_now()
        job.updated_at = utc_now()
        self.session.flush()
        return job

    def mark_retrying(self, job_id: uuid.UUID, error_message: str | None = None) -> JobLog:
        job = self._require(job_id)
        job.status = "retrying"
        job.error_message = error_message
        job.updated_at = utc_now()
        self.session.flush()
        return job

    def list_by_document(self, document_id: uuid.UUID) -> Sequence[JobLog]:
        return self.session.scalars(
            select(JobLog)
            .where(JobLog.document_id == document_id)
            .order_by(JobLog.created_at.desc())
        ).all()

    def get_latest_for_document(self, document_id: uuid.UUID, job_type: str | None = None) -> JobLog | None:
        statement = select(JobLog).where(JobLog.document_id == document_id)
        if job_type is not None:
            statement = statement.where(JobLog.job_type == job_type)
        return self.session.scalar(statement.order_by(JobLog.created_at.desc()).limit(1))

    def _require(self, job_id: uuid.UUID) -> JobLog:
        job = self.get(job_id)
        if job is None:
            raise ValueError(f"Job log not found: {job_id}")
        return job


class QueryLogRepository(BaseRepository[QueryLog]):
    model = QueryLog

    def create(
        self,
        *,
        user_query: str,
        knowledge_base_id: uuid.UUID | None = None,
        session_id: str | None = None,
        rewritten_query: str | None = None,
        answer: str | None = None,
        retrieval_mode: str = "hybrid",
        latency_ms: int | None = None,
        confidence: float | None = None,
        trace: dict[str, Any] | None = None,
    ) -> QueryLog:
        return self.add(
            QueryLog(
                knowledge_base_id=knowledge_base_id,
                session_id=session_id,
                user_query=user_query,
                rewritten_query=rewritten_query,
                answer=answer,
                retrieval_mode=retrieval_mode,
                latency_ms=latency_ms,
                confidence=confidence,
                trace=trace or {},
            )
        )

    def list_by_session(self, session_id: str, limit: int = 10) -> Sequence[QueryLog]:
        return self.session.scalars(
            select(QueryLog)
            .where(QueryLog.session_id == session_id)
            .order_by(QueryLog.created_at.desc())
            .limit(limit)
        ).all()
