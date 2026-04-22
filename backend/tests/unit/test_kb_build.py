"""Tests for POST /kb/{kb_id}/build endpoint (S7-08)."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.knowledge.api.routes.documents import get_storage
from app.knowledge.api.routes.kb import get_kb_job_queue
from app.common.core.dependencies import get_db
from app.common.db.base import Base
from app.common.db.models import Document, KnowledgeBase
from app.knowledge.jobs.queue import InMemoryJobQueue
from app.common.core.config import Settings
from app.main_knowledge import create_knowledge_app
_test_app = create_knowledge_app(settings=Settings(APP_ENV="testing"))
from app.common.storage.local import LocalStorage


@pytest_asyncio.fixture
async def build_engine():
    engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def build_session(build_engine):
    factory = async_sessionmaker(build_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def build_client(build_engine, tmp_path):
    factory = async_sessionmaker(build_engine, class_=AsyncSession, expire_on_commit=False)
    app = _test_app
    job_queue = InMemoryJobQueue()

    async def _override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_kb_job_queue] = lambda: job_queue

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac._job_queue = job_queue  # type: ignore
        yield ac

    app.dependency_overrides.clear()


async def _create_kb(session: AsyncSession, name: str | None = None) -> KnowledgeBase:
    kb = KnowledgeBase(
        name=name or f"Build KB {uuid.uuid4().hex[:8]}",
        settings={},
    )
    session.add(kb)
    await session.flush()
    return kb


async def _create_doc(
    session: AsyncSession,
    kb: KnowledgeBase,
    *,
    status: str = "chunked",
    title: str = "test.pdf",
) -> Document:
    doc = Document(
        knowledge_base_id=kb.id,
        title=title,
        source_filename=title,
        storage_path=f"{kb.id}/{uuid.uuid4()}/{title}",
        content_hash=uuid.uuid4().hex,
        mime_type="application/pdf",
        file_size_bytes=1000,
        document_type="unknown",
        status=status,
    )
    session.add(doc)
    await session.flush()
    return doc


@pytest.mark.unit
class TestBuildIndex:
    """Tests for POST /kb/{kb_id}/build (S7-08)."""

    @pytest.mark.asyncio
    async def test_build_enqueues_jobs_for_chunked_docs(
        self, build_session: AsyncSession, build_client: AsyncClient
    ):
        """Should enqueue indexing jobs for chunked documents."""
        kb = await _create_kb(build_session)
        doc1 = await _create_doc(build_session, kb, status="chunked")
        doc2 = await _create_doc(build_session, kb, status="chunked", title="doc2.pdf")
        await build_session.commit()

        response = await build_client.post(f"/kb/{kb.id}/build")

        assert response.status_code == 202
        data = response.json()
        assert data["jobs_enqueued"] == 2
        assert len(data["job_ids"]) == 2

    @pytest.mark.asyncio
    async def test_build_enqueues_jobs_for_ready_docs(
        self, build_session: AsyncSession, build_client: AsyncClient
    ):
        """Should enqueue indexing jobs for ready documents (re-index)."""
        kb = await _create_kb(build_session)
        await _create_doc(build_session, kb, status="ready")
        await build_session.commit()

        response = await build_client.post(f"/kb/{kb.id}/build")

        assert response.status_code == 202
        data = response.json()
        assert data["jobs_enqueued"] == 1

    @pytest.mark.asyncio
    async def test_build_skips_uploaded_docs(
        self, build_session: AsyncSession, build_client: AsyncClient
    ):
        """Should not enqueue jobs for uploaded (not yet chunked) documents."""
        kb = await _create_kb(build_session)
        await _create_doc(build_session, kb, status="uploaded")
        await _create_doc(build_session, kb, status="chunked")
        await build_session.commit()

        response = await build_client.post(f"/kb/{kb.id}/build")

        assert response.status_code == 202
        data = response.json()
        assert data["jobs_enqueued"] == 1

    @pytest.mark.asyncio
    async def test_build_empty_kb(
        self, build_session: AsyncSession, build_client: AsyncClient
    ):
        """Should return 0 jobs for empty KB."""
        kb = await _create_kb(build_session)
        await build_session.commit()

        response = await build_client.post(f"/kb/{kb.id}/build")

        assert response.status_code == 202
        data = response.json()
        assert data["jobs_enqueued"] == 0
        assert data["job_ids"] == []

    @pytest.mark.asyncio
    async def test_build_kb_not_found(self, build_client: AsyncClient):
        """Should return 404 for non-existent KB."""
        fake_id = str(uuid.uuid4())
        response = await build_client.post(f"/kb/{fake_id}/build")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_build_returns_kb_id(
        self, build_session: AsyncSession, build_client: AsyncClient
    ):
        """Response should include the KB ID."""
        kb = await _create_kb(build_session)
        await build_session.commit()

        response = await build_client.post(f"/kb/{kb.id}/build")

        assert response.status_code == 202
        assert response.json()["kb_id"] == str(kb.id)

    @pytest.mark.asyncio
    async def test_build_mixed_statuses(
        self, build_session: AsyncSession, build_client: AsyncClient
    ):
        """Should handle mix of chunked, ready, failed, uploaded docs."""
        kb = await _create_kb(build_session)
        await _create_doc(build_session, kb, status="chunked", title="c1.pdf")
        await _create_doc(build_session, kb, status="ready", title="r1.pdf")
        await _create_doc(build_session, kb, status="failed", title="f1.pdf")
        await _create_doc(build_session, kb, status="uploaded", title="u1.pdf")
        await build_session.commit()

        response = await build_client.post(f"/kb/{kb.id}/build")

        assert response.status_code == 202
        data = response.json()
        # Only chunked + ready = 2
        assert data["jobs_enqueued"] == 2
