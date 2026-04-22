"""Tests for knowledge base repository (S2-01, S2-02, S2-03)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.models import Chunk, Document, DocumentVersion, KnowledgeBase
from app.common.db.repositories.kb import KBRepository


@pytest.mark.unit
class TestKBRepositoryCreate:
    """Tests for KBRepository.create."""

    @pytest.mark.asyncio
    async def test_create_kb_minimal(self, db_session: AsyncSession):
        """Should create a KB with just a name."""
        repo = KBRepository(db_session)
        kb = await repo.create(name="Test KB")

        assert kb.id is not None
        assert kb.name == "Test KB"
        assert kb.description is None
        assert kb.settings == {}
        assert kb.is_active is True

    @pytest.mark.asyncio
    async def test_create_kb_with_all_fields(self, db_session: AsyncSession):
        """Should create a KB with all fields populated."""
        repo = KBRepository(db_session)
        settings = {
            "default_chunker": "docling_hybrid",
            "default_parser_profile": "balanced",
            "embedding_model": "BAAI/bge-m3",
        }
        kb = await repo.create(
            name="Full KB",
            description="A complete knowledge base",
            settings=settings,
        )

        assert kb.name == "Full KB"
        assert kb.description == "A complete knowledge base"
        assert kb.settings == settings

    @pytest.mark.asyncio
    async def test_create_kb_generates_uuid(self, db_session: AsyncSession):
        """Created KB should have a valid UUID."""
        repo = KBRepository(db_session)
        kb = await repo.create(name="UUID KB")

        assert isinstance(kb.id, uuid.UUID)


@pytest.mark.unit
class TestKBRepositoryRead:
    """Tests for KBRepository read operations."""

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, db_session: AsyncSession):
        """Should return KB when found by ID."""
        repo = KBRepository(db_session)
        kb = await repo.create(name="Find Me")

        found = await repo.get_by_id(kb.id)
        assert found is not None
        assert found.id == kb.id
        assert found.name == "Find Me"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db_session: AsyncSession):
        """Should return None when KB not found."""
        repo = KBRepository(db_session)
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_name_found(self, db_session: AsyncSession):
        """Should return KB when found by name."""
        repo = KBRepository(db_session)
        await repo.create(name="Named KB")

        found = await repo.get_by_name("Named KB")
        assert found is not None
        assert found.name == "Named KB"

    @pytest.mark.asyncio
    async def test_get_by_name_not_found(self, db_session: AsyncSession):
        """Should return None when name not found."""
        repo = KBRepository(db_session)
        result = await repo.get_by_name("Nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_all_empty(self, db_session: AsyncSession):
        """Should return empty list when no KBs exist."""
        repo = KBRepository(db_session)
        kbs = await repo.list_all()
        assert kbs == []

    @pytest.mark.asyncio
    async def test_list_all_multiple(self, db_session: AsyncSession):
        """Should return all KBs ordered by created_at desc."""
        repo = KBRepository(db_session)
        await repo.create(name="KB 1")
        await repo.create(name="KB 2")
        await repo.create(name="KB 3")

        kbs = await repo.list_all()
        assert len(kbs) == 3

    @pytest.mark.asyncio
    async def test_list_all_pagination(self, db_session: AsyncSession):
        """Should support skip and limit for pagination."""
        repo = KBRepository(db_session)
        for i in range(5):
            await repo.create(name=f"Page KB {i}")

        page = await repo.list_all(skip=2, limit=2)
        assert len(page) == 2


@pytest.mark.unit
class TestKBRepositoryUpdate:
    """Tests for KBRepository.update."""

    @pytest.mark.asyncio
    async def test_update_name(self, db_session: AsyncSession):
        """Should update KB name."""
        repo = KBRepository(db_session)
        kb = await repo.create(name="Old Name")

        updated = await repo.update(kb, name="New Name")
        assert updated.name == "New Name"

    @pytest.mark.asyncio
    async def test_update_settings(self, db_session: AsyncSession):
        """Should update KB settings."""
        repo = KBRepository(db_session)
        kb = await repo.create(name="Settings KB", settings={"default_chunker": "recursive_token"})

        new_settings = {"default_chunker": "docling_hybrid", "default_parser_profile": "accurate"}
        updated = await repo.update(kb, settings=new_settings)
        assert updated.settings == new_settings

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self, db_session: AsyncSession):
        """Should update multiple fields at once."""
        repo = KBRepository(db_session)
        kb = await repo.create(name="Multi Update")

        updated = await repo.update(kb, name="Updated Multi", description="New desc", is_active=False)
        assert updated.name == "Updated Multi"
        assert updated.description == "New desc"
        assert updated.is_active is False


@pytest.mark.unit
class TestKBRepositoryDelete:
    """Tests for KBRepository.delete."""

    @pytest.mark.asyncio
    async def test_delete_kb(self, db_session: AsyncSession):
        """Should delete KB from database."""
        repo = KBRepository(db_session)
        kb = await repo.create(name="Delete Me")
        kb_id = kb.id

        await repo.delete(kb)

        result = await repo.get_by_id(kb_id)
        assert result is None


@pytest.mark.unit
class TestKBRepositoryStatistics:
    """Tests for KBRepository.get_statistics (S2-03)."""

    @pytest.mark.asyncio
    async def test_statistics_empty_kb(self, db_session: AsyncSession):
        """Should return zero counts for empty KB."""
        repo = KBRepository(db_session)
        kb = await repo.create(name="Empty Stats KB")

        stats = await repo.get_statistics(kb.id)
        assert stats == {
            "document_count": 0,
            "chunk_count": 0,
            "ready_doc_count": 0,
            "failed_doc_count": 0,
        }

    @pytest.mark.asyncio
    async def test_statistics_with_documents(self, db_session: AsyncSession):
        """Should count documents by status."""
        repo = KBRepository(db_session)
        kb = await repo.create(name="Stats KB")

        # Add documents with different statuses
        for i, status in enumerate(["ready", "ready", "failed", "uploaded"]):
            doc = Document(
                knowledge_base_id=kb.id,
                title=f"Doc {i}",
                source_filename=f"doc{i}.pdf",
                storage_path=f"/path/doc{i}.pdf",
                content_hash=f"hash{i}_{uuid.uuid4().hex[:8]}",
                mime_type="application/pdf",
                file_size_bytes=1000,
                status=status,
            )
            db_session.add(doc)
        await db_session.flush()

        stats = await repo.get_statistics(kb.id)
        assert stats["document_count"] == 4
        assert stats["ready_doc_count"] == 2
        assert stats["failed_doc_count"] == 1

    @pytest.mark.asyncio
    async def test_statistics_excludes_deleted_documents(self, db_session: AsyncSession):
        """Should not count soft-deleted documents."""
        repo = KBRepository(db_session)
        kb = await repo.create(name="Deleted Stats KB")

        # Add a normal doc and a deleted doc
        doc1 = Document(
            knowledge_base_id=kb.id,
            title="Active Doc",
            source_filename="active.pdf",
            storage_path="/path/active.pdf",
            content_hash="activehash",
            mime_type="application/pdf",
            file_size_bytes=1000,
            status="ready",
        )
        doc2 = Document(
            knowledge_base_id=kb.id,
            title="Deleted Doc",
            source_filename="deleted.pdf",
            storage_path="/path/deleted.pdf",
            content_hash="deletedhash",
            mime_type="application/pdf",
            file_size_bytes=1000,
            status="ready",
            is_deleted=True,
        )
        db_session.add_all([doc1, doc2])
        await db_session.flush()

        stats = await repo.get_statistics(kb.id)
        assert stats["document_count"] == 1
        assert stats["ready_doc_count"] == 1

    @pytest.mark.asyncio
    async def test_statistics_chunk_count(self, db_session: AsyncSession):
        """Should count chunks for the KB."""
        repo = KBRepository(db_session)
        kb = await repo.create(name="Chunk Stats KB")

        doc = Document(
            knowledge_base_id=kb.id,
            title="Chunked Doc",
            source_filename="chunked.pdf",
            storage_path="/path/chunked.pdf",
            content_hash="chunkedhash",
            mime_type="application/pdf",
            file_size_bytes=1000,
            status="ready",
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

        # Add chunks
        for i in range(3):
            chunk = Chunk(
                knowledge_base_id=kb.id,
                document_id=doc.id,
                document_version_id=version.id,
                ordinal=i,
                content=f"Chunk content {i}",
                content_hash=f"chunkhash{i}",
                token_count=50,
            )
            db_session.add(chunk)
        await db_session.flush()

        stats = await repo.get_statistics(kb.id)
        assert stats["chunk_count"] == 3
