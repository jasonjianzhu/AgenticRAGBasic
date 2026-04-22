"""Tests for chunk batch persistence in the database."""
from __future__ import annotations

import hashlib
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.models import Chunk, Document, DocumentVersion, KnowledgeBase
from app.common.db.repositories.chunks import ChunkRepository


@pytest_asyncio.fixture
async def kb(db_session: AsyncSession) -> KnowledgeBase:
    """Create a test knowledge base."""
    kb = KnowledgeBase(name=f"test-kb-{uuid.uuid4().hex[:8]}", description="Test KB")
    db_session.add(kb)
    await db_session.flush()
    return kb


@pytest_asyncio.fixture
async def doc(db_session: AsyncSession, kb: KnowledgeBase) -> Document:
    """Create a test document."""
    doc = Document(
        knowledge_base_id=kb.id,
        title="test.pdf",
        source_filename="test.pdf",
        storage_path="/tmp/test.pdf",
        content_hash="abc123",
        mime_type="application/pdf",
        file_size_bytes=1024,
    )
    db_session.add(doc)
    await db_session.flush()
    return doc


@pytest_asyncio.fixture
async def doc_version(db_session: AsyncSession, doc: Document) -> DocumentVersion:
    """Create a test document version."""
    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        parser_profile="balanced",
        status="parsed",
    )
    db_session.add(version)
    await db_session.flush()
    return version


@pytest_asyncio.fixture
def chunk_repo(db_session: AsyncSession) -> ChunkRepository:
    return ChunkRepository(db_session)


class TestCreateChunksBatch:
    """Tests for the create_chunks_batch method."""

    async def test_create_single_chunk(
        self, chunk_repo, kb, doc, doc_version, db_session
    ):
        chunks = await chunk_repo.create_chunks_batch(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=doc_version.id,
            chunks_data=[
                {
                    "content": "Hello world",
                    "ordinal": 0,
                    "chunk_type": "text",
                    "token_count": 2,
                }
            ],
        )
        assert len(chunks) == 1
        assert chunks[0].content == "Hello world"
        assert chunks[0].ordinal == 0
        assert chunks[0].chunk_type == "text"
        assert chunks[0].token_count == 2
        assert chunks[0].knowledge_base_id == kb.id
        assert chunks[0].document_id == doc.id
        assert chunks[0].document_version_id == doc_version.id

    async def test_content_hash_is_sha256(
        self, chunk_repo, kb, doc, doc_version
    ):
        content = "Test content for hashing"
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        chunks = await chunk_repo.create_chunks_batch(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=doc_version.id,
            chunks_data=[{"content": content, "ordinal": 0}],
        )
        assert chunks[0].content_hash == expected_hash

    async def test_create_multiple_chunks(
        self, chunk_repo, kb, doc, doc_version
    ):
        chunks_data = [
            {"content": f"Chunk {i}", "ordinal": i, "chunk_type": "text"}
            for i in range(5)
        ]
        chunks = await chunk_repo.create_chunks_batch(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=doc_version.id,
            chunks_data=chunks_data,
        )
        assert len(chunks) == 5
        for i, chunk in enumerate(chunks):
            assert chunk.ordinal == i
            assert chunk.content == f"Chunk {i}"

    async def test_empty_batch(self, chunk_repo, kb, doc, doc_version):
        chunks = await chunk_repo.create_chunks_batch(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=doc_version.id,
            chunks_data=[],
        )
        assert chunks == []

    async def test_chunk_with_all_fields(
        self, chunk_repo, kb, doc, doc_version
    ):
        chunks = await chunk_repo.create_chunks_batch(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=doc_version.id,
            chunks_data=[
                {
                    "content": "Table data",
                    "ordinal": 0,
                    "chunk_type": "table",
                    "section_path": "Chapter 1 > Tables",
                    "page_start": 5,
                    "page_end": 6,
                    "token_count": 10,
                    "metadata": {"caption": "Table 1"},
                }
            ],
        )
        chunk = chunks[0]
        assert chunk.chunk_type == "table"
        assert chunk.section_path == "Chapter 1 > Tables"
        assert chunk.page_start == 5
        assert chunk.page_end == 6
        assert chunk.token_count == 10
        assert chunk.metadata_ == {"caption": "Table 1"}

    async def test_chunks_persisted_in_db(
        self, chunk_repo, kb, doc, doc_version, db_session
    ):
        await chunk_repo.create_chunks_batch(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=doc_version.id,
            chunks_data=[
                {"content": "Persisted chunk", "ordinal": 0},
            ],
        )
        # Query directly
        stmt = select(Chunk).where(Chunk.document_id == doc.id)
        result = await db_session.execute(stmt)
        db_chunks = result.scalars().all()
        assert len(db_chunks) == 1
        assert db_chunks[0].content == "Persisted chunk"

    async def test_default_chunk_type(
        self, chunk_repo, kb, doc, doc_version
    ):
        chunks = await chunk_repo.create_chunks_batch(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=doc_version.id,
            chunks_data=[{"content": "No type specified", "ordinal": 0}],
        )
        assert chunks[0].chunk_type == "text"

    async def test_default_metadata(
        self, chunk_repo, kb, doc, doc_version
    ):
        chunks = await chunk_repo.create_chunks_batch(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=doc_version.id,
            chunks_data=[{"content": "No metadata", "ordinal": 0}],
        )
        assert chunks[0].metadata_ == {}


class TestDeleteByDocumentVersion:
    """Tests for the delete_by_document_version method."""

    async def test_delete_removes_chunks(
        self, chunk_repo, kb, doc, doc_version, db_session
    ):
        await chunk_repo.create_chunks_batch(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=doc_version.id,
            chunks_data=[
                {"content": f"Chunk {i}", "ordinal": i} for i in range(3)
            ],
        )
        deleted = await chunk_repo.delete_by_document_version(doc_version.id)
        assert deleted == 3

        remaining = await chunk_repo.list_by_document(doc.id)
        assert len(remaining) == 0

    async def test_delete_nonexistent_returns_zero(self, chunk_repo):
        deleted = await chunk_repo.delete_by_document_version(uuid.uuid4())
        assert deleted == 0


class TestListByDocument:
    """Tests for the existing list_by_document method."""

    async def test_list_ordered_by_ordinal(
        self, chunk_repo, kb, doc, doc_version
    ):
        # Insert in reverse order
        await chunk_repo.create_chunks_batch(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=doc_version.id,
            chunks_data=[
                {"content": "Third", "ordinal": 2},
                {"content": "First", "ordinal": 0},
                {"content": "Second", "ordinal": 1},
            ],
        )
        chunks = await chunk_repo.list_by_document(doc.id)
        assert [c.ordinal for c in chunks] == [0, 1, 2]
        assert [c.content for c in chunks] == ["First", "Second", "Third"]
