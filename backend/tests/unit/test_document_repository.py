"""Tests for document repository (S3-01 through S3-06)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, DocumentVersion, KnowledgeBase
from app.db.repositories.chunks import ChunkRepository
from app.db.repositories.documents import DocumentRepository


async def _create_kb(session: AsyncSession, name: str | None = None) -> KnowledgeBase:
    """Helper to create a knowledge base."""
    kb = KnowledgeBase(
        name=name or f"Test KB {uuid.uuid4().hex[:8]}",
        settings={},
    )
    session.add(kb)
    await session.flush()
    return kb


async def _create_doc(
    session: AsyncSession,
    kb: KnowledgeBase,
    *,
    title: str = "test.pdf",
    content_hash: str | None = None,
    status: str = "uploaded",
    is_deleted: bool = False,
    is_enabled: bool = True,
) -> Document:
    """Helper to create a document directly in DB."""
    doc = Document(
        knowledge_base_id=kb.id,
        title=title,
        source_filename=title,
        storage_path=f"{kb.id}/{uuid.uuid4()}/{title}",
        content_hash=content_hash or uuid.uuid4().hex,
        mime_type="application/pdf",
        file_size_bytes=1024,
        document_type="unknown",
        status=status,
        is_deleted=is_deleted,
        is_enabled=is_enabled,
    )
    session.add(doc)
    await session.flush()
    return doc


@pytest.mark.unit
class TestDocumentRepositoryCreate:
    """Tests for DocumentRepository.create."""

    @pytest.mark.asyncio
    async def test_create_document(self, db_session: AsyncSession):
        """Should create a document with all fields."""
        kb = await _create_kb(db_session)
        repo = DocumentRepository(db_session)

        doc = await repo.create(
            knowledge_base_id=kb.id,
            title="产品手册.pdf",
            source_filename="产品手册.pdf",
            storage_path=f"{kb.id}/doc1/产品手册.pdf",
            content_hash="abc123",
            mime_type="application/pdf",
            file_size_bytes=12345,
            document_type="manual",
        )

        assert doc.id is not None
        assert doc.knowledge_base_id == kb.id
        assert doc.title == "产品手册.pdf"
        assert doc.source_filename == "产品手册.pdf"
        assert doc.content_hash == "abc123"
        assert doc.mime_type == "application/pdf"
        assert doc.file_size_bytes == 12345
        assert doc.document_type == "manual"
        assert doc.status == "uploaded"
        assert doc.is_enabled is True
        assert doc.is_deleted is False

    @pytest.mark.asyncio
    async def test_create_document_defaults(self, db_session: AsyncSession):
        """Should use default values for optional fields."""
        kb = await _create_kb(db_session)
        repo = DocumentRepository(db_session)

        doc = await repo.create(
            knowledge_base_id=kb.id,
            title="test.pdf",
            source_filename="test.pdf",
            storage_path="path/test.pdf",
            content_hash="hash123",
            mime_type="application/pdf",
            file_size_bytes=100,
        )

        assert doc.document_type == "unknown"
        assert doc.status == "uploaded"
        assert doc.metadata_ == {}


@pytest.mark.unit
class TestDocumentRepositoryRead:
    """Tests for DocumentRepository read operations."""

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, db_session: AsyncSession):
        """Should return document when found."""
        kb = await _create_kb(db_session)
        doc = await _create_doc(db_session, kb)
        repo = DocumentRepository(db_session)

        found = await repo.get_by_id(doc.id)
        assert found is not None
        assert found.id == doc.id

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db_session: AsyncSession):
        """Should return None when not found."""
        repo = DocumentRepository(db_session)
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_excludes_deleted(self, db_session: AsyncSession):
        """Should not return soft-deleted documents."""
        kb = await _create_kb(db_session)
        doc = await _create_doc(db_session, kb, is_deleted=True)
        repo = DocumentRepository(db_session)

        result = await repo.get_by_id(doc.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_include_deleted(self, db_session: AsyncSession):
        """Should return soft-deleted documents when using include_deleted."""
        kb = await _create_kb(db_session)
        doc = await _create_doc(db_session, kb, is_deleted=True)
        repo = DocumentRepository(db_session)

        result = await repo.get_by_id_include_deleted(doc.id)
        assert result is not None
        assert result.id == doc.id


@pytest.mark.unit
class TestDocumentRepositoryDedup:
    """Tests for SHA-256 dedup lookup (S3-02)."""

    @pytest.mark.asyncio
    async def test_get_by_kb_and_hash_found(self, db_session: AsyncSession):
        """Should find document by KB + content hash."""
        kb = await _create_kb(db_session)
        doc = await _create_doc(db_session, kb, content_hash="sha256_abc")
        repo = DocumentRepository(db_session)

        found = await repo.get_by_kb_and_hash(kb.id, "sha256_abc")
        assert found is not None
        assert found.id == doc.id

    @pytest.mark.asyncio
    async def test_get_by_kb_and_hash_not_found(self, db_session: AsyncSession):
        """Should return None when no match."""
        kb = await _create_kb(db_session)
        repo = DocumentRepository(db_session)

        result = await repo.get_by_kb_and_hash(kb.id, "nonexistent_hash")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_kb_and_hash_different_kb(self, db_session: AsyncSession):
        """Same hash in different KB should not match."""
        kb1 = await _create_kb(db_session, name="KB1")
        kb2 = await _create_kb(db_session, name="KB2")
        await _create_doc(db_session, kb1, content_hash="same_hash")
        repo = DocumentRepository(db_session)

        result = await repo.get_by_kb_and_hash(kb2.id, "same_hash")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_kb_and_hash_excludes_deleted(self, db_session: AsyncSession):
        """Should not match soft-deleted documents."""
        kb = await _create_kb(db_session)
        await _create_doc(db_session, kb, content_hash="deleted_hash", is_deleted=True)
        repo = DocumentRepository(db_session)

        result = await repo.get_by_kb_and_hash(kb.id, "deleted_hash")
        assert result is None


@pytest.mark.unit
class TestDocumentRepositoryList:
    """Tests for DocumentRepository.list_documents (S3-04)."""

    @pytest.mark.asyncio
    async def test_list_empty(self, db_session: AsyncSession):
        """Should return empty list when no documents."""
        repo = DocumentRepository(db_session)
        docs = await repo.list_documents()
        assert len(docs) == 0

    @pytest.mark.asyncio
    async def test_list_excludes_deleted(self, db_session: AsyncSession):
        """Should exclude soft-deleted documents."""
        kb = await _create_kb(db_session)
        await _create_doc(db_session, kb, title="active.pdf")
        await _create_doc(db_session, kb, title="deleted.pdf", is_deleted=True)
        repo = DocumentRepository(db_session)

        docs = await repo.list_documents()
        assert len(docs) == 1
        assert docs[0].title == "active.pdf"

    @pytest.mark.asyncio
    async def test_list_filter_by_kb(self, db_session: AsyncSession):
        """Should filter by knowledge_base_id."""
        kb1 = await _create_kb(db_session, name="KB Filter 1")
        kb2 = await _create_kb(db_session, name="KB Filter 2")
        await _create_doc(db_session, kb1, title="doc1.pdf")
        await _create_doc(db_session, kb2, title="doc2.pdf")
        repo = DocumentRepository(db_session)

        docs = await repo.list_documents(knowledge_base_id=kb1.id)
        assert len(docs) == 1
        assert docs[0].title == "doc1.pdf"

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self, db_session: AsyncSession):
        """Should filter by status."""
        kb = await _create_kb(db_session)
        await _create_doc(db_session, kb, title="uploaded.pdf", status="uploaded")
        await _create_doc(db_session, kb, title="ready.pdf", status="ready")
        repo = DocumentRepository(db_session)

        docs = await repo.list_documents(status="ready")
        assert len(docs) == 1
        assert docs[0].title == "ready.pdf"

    @pytest.mark.asyncio
    async def test_list_pagination(self, db_session: AsyncSession):
        """Should support skip and limit."""
        kb = await _create_kb(db_session)
        for i in range(5):
            await _create_doc(db_session, kb, title=f"doc{i}.pdf")
        repo = DocumentRepository(db_session)

        docs = await repo.list_documents(skip=2, limit=2)
        assert len(docs) == 2


@pytest.mark.unit
class TestDocumentRepositoryUpdate:
    """Tests for DocumentRepository.update (S3-05)."""

    @pytest.mark.asyncio
    async def test_update_is_enabled(self, db_session: AsyncSession):
        """Should toggle is_enabled field."""
        kb = await _create_kb(db_session)
        doc = await _create_doc(db_session, kb)
        repo = DocumentRepository(db_session)

        updated = await repo.update(doc, is_enabled=False)
        assert updated.is_enabled is False

        updated = await repo.update(doc, is_enabled=True)
        assert updated.is_enabled is True

    @pytest.mark.asyncio
    async def test_update_status(self, db_session: AsyncSession):
        """Should update document status."""
        kb = await _create_kb(db_session)
        doc = await _create_doc(db_session, kb)
        repo = DocumentRepository(db_session)

        updated = await repo.update(doc, status="parsing")
        assert updated.status == "parsing"


@pytest.mark.unit
class TestDocumentRepositorySoftDelete:
    """Tests for DocumentRepository.soft_delete (S3-06)."""

    @pytest.mark.asyncio
    async def test_soft_delete(self, db_session: AsyncSession):
        """Should set is_deleted=True."""
        kb = await _create_kb(db_session)
        doc = await _create_doc(db_session, kb)
        repo = DocumentRepository(db_session)

        deleted = await repo.soft_delete(doc)
        assert deleted.is_deleted is True

        # Should not appear in normal get
        result = await repo.get_by_id(doc.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_soft_delete_excluded_from_list(self, db_session: AsyncSession):
        """Soft-deleted docs should not appear in list."""
        kb = await _create_kb(db_session)
        doc = await _create_doc(db_session, kb)
        repo = DocumentRepository(db_session)

        await repo.soft_delete(doc)
        docs = await repo.list_documents()
        assert len(docs) == 0


@pytest.mark.unit
class TestChunkRepository:
    """Tests for ChunkRepository (S3-07)."""

    @pytest.mark.asyncio
    async def test_list_by_document_empty(self, db_session: AsyncSession):
        """Should return empty list when no chunks."""
        kb = await _create_kb(db_session)
        doc = await _create_doc(db_session, kb)
        repo = ChunkRepository(db_session)

        chunks = await repo.list_by_document(doc.id)
        assert len(chunks) == 0

    @pytest.mark.asyncio
    async def test_list_by_document_with_chunks(self, db_session: AsyncSession):
        """Should return chunks ordered by ordinal."""
        kb = await _create_kb(db_session)
        doc = await _create_doc(db_session, kb)

        version = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            parser_profile="balanced",
        )
        db_session.add(version)
        await db_session.flush()

        for i in range(3):
            chunk = Chunk(
                knowledge_base_id=kb.id,
                document_id=doc.id,
                document_version_id=version.id,
                ordinal=i,
                content=f"Chunk content {i}",
                content_hash=f"chunkhash{i}",
                token_count=50 + i * 10,
                page_start=i + 1,
                page_end=i + 1,
                chunk_type="text",
                section_path=f"Chapter {i + 1}",
            )
            db_session.add(chunk)
        await db_session.flush()

        repo = ChunkRepository(db_session)
        chunks = await repo.list_by_document(doc.id)
        assert len(chunks) == 3
        assert chunks[0].ordinal == 0
        assert chunks[1].ordinal == 1
        assert chunks[2].ordinal == 2
        assert chunks[0].content == "Chunk content 0"
        assert chunks[0].token_count == 50
        assert chunks[0].page_start == 1
        assert chunks[0].section_path == "Chapter 1"

    @pytest.mark.asyncio
    async def test_list_by_document_pagination(self, db_session: AsyncSession):
        """Should support pagination."""
        kb = await _create_kb(db_session)
        doc = await _create_doc(db_session, kb)

        version = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            parser_profile="balanced",
        )
        db_session.add(version)
        await db_session.flush()

        for i in range(5):
            chunk = Chunk(
                knowledge_base_id=kb.id,
                document_id=doc.id,
                document_version_id=version.id,
                ordinal=i,
                content=f"Chunk {i}",
                content_hash=f"pchash{i}",
            )
            db_session.add(chunk)
        await db_session.flush()

        repo = ChunkRepository(db_session)
        chunks = await repo.list_by_document(doc.id, skip=1, limit=2)
        assert len(chunks) == 2
        assert chunks[0].ordinal == 1
        assert chunks[1].ordinal == 2
