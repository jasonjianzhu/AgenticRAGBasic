"""Tests for ORM models (S1-03)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.models import (
    Chunk,
    Document,
    DocumentVersion,
    JobLog,
    KnowledgeBase,
)


@pytest.mark.unit
class TestKnowledgeBaseModel:
    """KnowledgeBase ORM model tests."""

    @pytest.mark.asyncio
    async def test_create_knowledge_base(self, db_session: AsyncSession):
        """Should create a knowledge base with defaults."""
        kb = KnowledgeBase(
            name="Test KB",
            description="A test knowledge base",
            settings={"default_chunker": "docling_hybrid"},
        )
        db_session.add(kb)
        await db_session.flush()

        assert kb.id is not None
        assert kb.is_active is True
        assert kb.settings["default_chunker"] == "docling_hybrid"

    @pytest.mark.asyncio
    async def test_kb_name_unique(self, db_session: AsyncSession):
        """Knowledge base names must be unique."""
        kb1 = KnowledgeBase(name="Unique KB", settings={})
        kb2 = KnowledgeBase(name="Unique KB", settings={})
        db_session.add(kb1)
        await db_session.flush()
        db_session.add(kb2)
        with pytest.raises(Exception):  # IntegrityError
            await db_session.flush()


@pytest.mark.unit
class TestDocumentModel:
    """Document ORM model tests."""

    @pytest.mark.asyncio
    async def test_create_document(self, db_session: AsyncSession):
        """Should create a document linked to a knowledge base."""
        kb = KnowledgeBase(name="Doc Test KB", settings={})
        db_session.add(kb)
        await db_session.flush()

        doc = Document(
            knowledge_base_id=kb.id,
            title="Test Document",
            source_filename="test.pdf",
            storage_path="/var/uploads/test.pdf",
            content_hash="abc123",
            mime_type="application/pdf",
            file_size_bytes=1024,
        )
        db_session.add(doc)
        await db_session.flush()

        assert doc.id is not None
        assert doc.status == "uploaded"
        assert doc.is_enabled is True
        assert doc.is_deleted is False
        assert doc.document_type == "unknown"

    @pytest.mark.asyncio
    async def test_document_kb_hash_unique(self, db_session: AsyncSession):
        """(kb_id, content_hash) must be unique."""
        kb = KnowledgeBase(name="Hash Test KB", settings={})
        db_session.add(kb)
        await db_session.flush()

        doc1 = Document(
            knowledge_base_id=kb.id,
            title="Doc 1",
            source_filename="a.pdf",
            storage_path="/a",
            content_hash="samehash",
            mime_type="application/pdf",
            file_size_bytes=100,
        )
        doc2 = Document(
            knowledge_base_id=kb.id,
            title="Doc 2",
            source_filename="b.pdf",
            storage_path="/b",
            content_hash="samehash",
            mime_type="application/pdf",
            file_size_bytes=200,
        )
        db_session.add(doc1)
        await db_session.flush()
        db_session.add(doc2)
        with pytest.raises(Exception):
            await db_session.flush()


@pytest.mark.unit
class TestChunkModel:
    """Chunk ORM model tests."""

    @pytest.mark.asyncio
    async def test_create_chunk(self, db_session: AsyncSession):
        """Should create a chunk linked to document version."""
        kb = KnowledgeBase(name="Chunk Test KB", settings={})
        db_session.add(kb)
        await db_session.flush()

        doc = Document(
            knowledge_base_id=kb.id,
            title="Chunk Doc",
            source_filename="c.pdf",
            storage_path="/c",
            content_hash="chunkhash",
            mime_type="application/pdf",
            file_size_bytes=500,
        )
        db_session.add(doc)
        await db_session.flush()

        version = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            parser_profile="balanced",
        )
        db_session.add(version)
        await db_session.flush()

        chunk = Chunk(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=version.id,
            ordinal=0,
            content="This is a test chunk.",
            content_hash="chunkcontent123",
            token_count=5,
            chunk_type="text",
        )
        db_session.add(chunk)
        await db_session.flush()

        assert chunk.id is not None
        assert chunk.ordinal == 0
        assert chunk.chunk_type == "text"


@pytest.mark.unit
class TestJobLogModel:
    """JobLog ORM model tests."""

    @pytest.mark.asyncio
    async def test_create_job_log(self, db_session: AsyncSession):
        """Should create a job log entry."""
        job = JobLog(
            queue_name="ingestion",
            job_type="ingest",
            status="queued",
            payload={"document_id": str(uuid.uuid4())},
        )
        db_session.add(job)
        await db_session.flush()

        assert job.id is not None
        assert job.status == "queued"
        assert job.attempts == 0
