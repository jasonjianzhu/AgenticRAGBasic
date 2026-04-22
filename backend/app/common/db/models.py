"""ORM models for AgenticRAG."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Use JSON with JSONB variant for PostgreSQL, plain JSON for SQLite/others
JsonType = JSON().with_variant(JSONB, "postgresql")

from app.common.db.base import Base, TimestampMixin

UUID_TYPE = Uuid(as_uuid=True)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)


class KnowledgeBase(TimestampMixin, Base):
    """Knowledge base entity."""

    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    settings: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)

    documents: Mapped[list[Document]] = relationship(
        back_populates="knowledge_base", cascade="all, delete-orphan"
    )


class Document(TimestampMixin, Base):
    """Document entity within a knowledge base."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded", index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JsonType, nullable=False, default=dict)

    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="documents")
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[Chunk]] = relationship(back_populates="document", cascade="all, delete-orphan")
    job_logs: Mapped[list[JobLog]] = relationship(back_populates="document")

    __table_args__ = (
        UniqueConstraint("knowledge_base_id", "content_hash", name="uq_documents_kb_content_hash"),
    )


class DocumentVersion(TimestampMixin, Base):
    """Versioned parsing result for a document."""

    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parser_profile: Mapped[str] = mapped_column(String(50), nullable=False, default="balanced")
    parsed_path: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="created", index=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JsonType, nullable=False, default=dict)

    document: Mapped[Document] = relationship(back_populates="versions")
    chunks: Mapped[list[Chunk]] = relationship(back_populates="document_version")

    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_docver_doc_version"),
    )


class Chunk(TimestampMixin, Base):
    """Text chunk extracted from a document version."""

    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text", index=True)
    section_path: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(20), index=True)
    product_model: Mapped[str | None] = mapped_column(String(200), index=True)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(128), index=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JsonType, nullable=False, default=dict)

    document: Mapped[Document] = relationship(back_populates="chunks")
    document_version: Mapped[DocumentVersion] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_version_id", "ordinal", name="uq_chunks_version_ordinal"),
    )


class JobLog(TimestampMixin, Base):
    """Async job tracking record."""

    __tablename__ = "job_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    rq_job_id: Mapped[str | None] = mapped_column(String(200), index=True)
    queue_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued", index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID_TYPE, ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)

    document: Mapped[Document | None] = relationship(back_populates="job_logs")
