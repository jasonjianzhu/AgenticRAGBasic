"""Tests for document delete with Qdrant cleanup (S7-09)."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.knowledge.api.routes.documents import get_storage
from app.common.core.dependencies import get_db
from app.common.db.base import Base
from app.common.db.models import Chunk, Document, DocumentVersion, KnowledgeBase
from app.main_knowledge import app as _test_app
from app.common.storage.local import LocalStorage


@pytest_asyncio.fixture
async def cleanup_engine():
    engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def cleanup_session(cleanup_engine):
    factory = async_sessionmaker(cleanup_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def cleanup_client(cleanup_engine, tmp_path):
    factory = async_sessionmaker(cleanup_engine, class_=AsyncSession, expire_on_commit=False)
    app = _test_app

    async def _override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_storage] = lambda: LocalStorage(base_dir=tmp_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.mark.unit
class TestDocumentDeleteCleanup:
    """Tests for document delete with Qdrant point cleanup (S7-09)."""

    @pytest.mark.asyncio
    async def test_delete_document_with_chunks(
        self, cleanup_session: AsyncSession, cleanup_client: AsyncClient
    ):
        """Deleting a document with chunks should still succeed (soft delete)."""
        kb = KnowledgeBase(name="Cleanup KB", settings={})
        cleanup_session.add(kb)
        await cleanup_session.flush()

        doc = Document(
            knowledge_base_id=kb.id,
            title="test.pdf",
            source_filename="test.pdf",
            storage_path=f"{kb.id}/test.pdf",
            content_hash="testhash",
            mime_type="application/pdf",
            file_size_bytes=1000,
            status="ready",
        )
        cleanup_session.add(doc)
        await cleanup_session.flush()

        version = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            parser_profile="balanced",
        )
        cleanup_session.add(version)
        await cleanup_session.flush()

        # Create chunks with qdrant_point_ids
        for i in range(3):
            chunk = Chunk(
                knowledge_base_id=kb.id,
                document_id=doc.id,
                document_version_id=version.id,
                ordinal=i,
                content=f"Chunk {i}",
                content_hash=f"hash{i}",
                qdrant_point_id=str(uuid.uuid4()),
            )
            cleanup_session.add(chunk)

        await cleanup_session.commit()

        # Delete should succeed (Qdrant cleanup is best-effort)
        response = await cleanup_client.delete(f"/documents/{doc.id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_document_without_chunks(
        self, cleanup_session: AsyncSession, cleanup_client: AsyncClient
    ):
        """Deleting a document without chunks should work fine."""
        kb = KnowledgeBase(name="No Chunks KB", settings={})
        cleanup_session.add(kb)
        await cleanup_session.flush()

        doc = Document(
            knowledge_base_id=kb.id,
            title="empty.pdf",
            source_filename="empty.pdf",
            storage_path=f"{kb.id}/empty.pdf",
            content_hash="emptyhash",
            mime_type="application/pdf",
            file_size_bytes=500,
            status="uploaded",
        )
        cleanup_session.add(doc)
        await cleanup_session.commit()

        response = await cleanup_client.delete(f"/documents/{doc.id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_document_chunks_without_qdrant_ids(
        self, cleanup_session: AsyncSession, cleanup_client: AsyncClient
    ):
        """Deleting doc with chunks that have no qdrant_point_id should work."""
        kb = KnowledgeBase(name="No Qdrant KB", settings={})
        cleanup_session.add(kb)
        await cleanup_session.flush()

        doc = Document(
            knowledge_base_id=kb.id,
            title="noqdrant.pdf",
            source_filename="noqdrant.pdf",
            storage_path=f"{kb.id}/noqdrant.pdf",
            content_hash="noqhash",
            mime_type="application/pdf",
            file_size_bytes=500,
            status="chunked",
        )
        cleanup_session.add(doc)
        await cleanup_session.flush()

        version = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            parser_profile="balanced",
        )
        cleanup_session.add(version)
        await cleanup_session.flush()

        chunk = Chunk(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=version.id,
            ordinal=0,
            content="Test chunk",
            content_hash="chunkhash",
            qdrant_point_id=None,  # No Qdrant point
        )
        cleanup_session.add(chunk)
        await cleanup_session.commit()

        response = await cleanup_client.delete(f"/documents/{doc.id}")
        assert response.status_code == 204
