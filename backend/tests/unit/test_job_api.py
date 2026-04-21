"""Tests for job API endpoints (S4-04, S4-05, S4-06).

Tests list, detail, and retry endpoints using in-memory DB and queue.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.routes.jobs import get_job_queue
from app.core.dependencies import get_db
from app.db.base import Base
from app.db.models import Document, JobLog, KnowledgeBase
from app.db.repositories.jobs import JobRepository
from app.jobs.queue import InMemoryJobQueue
from app.main import create_app


@pytest_asyncio.fixture
async def api_session():
    """Create an isolated async engine and session for API tests."""
    engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_queue():
    """Provide an InMemoryJobQueue for tests."""
    return InMemoryJobQueue()


@pytest_asyncio.fixture
async def api_client(api_session: AsyncSession, test_queue: InMemoryJobQueue):
    """Provide an async HTTP test client with DB and queue dependency overrides."""
    app = create_app()

    async def _override_get_db():
        try:
            yield api_session
            await api_session.commit()
        except Exception:
            await api_session.rollback()
            raise

    def _override_get_job_queue():
        return test_queue

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_job_queue] = _override_get_job_queue

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def _create_job_in_db(
    session: AsyncSession,
    *,
    queue_name: str = "ingestion",
    job_type: str = "ingest",
    status: str = "queued",
    document_id: uuid.UUID | None = None,
    rq_job_id: str | None = None,
    attempts: int = 0,
    error_message: str | None = None,
    payload: dict | None = None,
) -> JobLog:
    """Helper to create a JobLog directly in the DB."""
    job = JobLog(
        queue_name=queue_name,
        job_type=job_type,
        status=status,
        document_id=document_id,
        rq_job_id=rq_job_id,
        attempts=attempts,
        error_message=error_message,
        payload=payload or {},
    )
    session.add(job)
    await session.flush()
    return job


async def _create_kb_and_doc(session: AsyncSession) -> tuple[KnowledgeBase, Document]:
    """Helper to create a KB and document."""
    kb = KnowledgeBase(name=f"API Test KB {uuid.uuid4().hex[:8]}", settings={})
    session.add(kb)
    await session.flush()

    doc = Document(
        knowledge_base_id=kb.id,
        title="API Test Doc",
        source_filename="test.pdf",
        storage_path="/path/test.pdf",
        content_hash=f"hash_{uuid.uuid4().hex[:8]}",
        mime_type="application/pdf",
        file_size_bytes=1024,
    )
    session.add(doc)
    await session.flush()
    return kb, doc


@pytest.mark.unit
class TestListJobs:
    """Tests for GET /jobs."""

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, api_client: AsyncClient):
        """Should return empty list when no jobs exist."""
        response = await api_client.get("/jobs")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_jobs_multiple(self, api_session: AsyncSession, api_client: AsyncClient):
        """Should return all jobs."""
        await _create_job_in_db(api_session, queue_name="ingestion", job_type="ingest")
        await _create_job_in_db(api_session, queue_name="indexing", job_type="index")
        await api_session.commit()

        response = await api_client.get("/jobs")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_status(self, api_session: AsyncSession, api_client: AsyncClient):
        """Should filter by status query param."""
        await _create_job_in_db(api_session, status="queued")
        await _create_job_in_db(api_session, status="failed", error_message="err")
        await api_session.commit()

        response = await api_client.get("/jobs", params={"status": "failed"})

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_queue_name(self, api_session: AsyncSession, api_client: AsyncClient):
        """Should filter by queue_name query param."""
        await _create_job_in_db(api_session, queue_name="ingestion")
        await _create_job_in_db(api_session, queue_name="indexing")
        await api_session.commit()

        response = await api_client.get("/jobs", params={"queue_name": "indexing"})

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["queue_name"] == "indexing"

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_document_id(self, api_session: AsyncSession, api_client: AsyncClient):
        """Should filter by document_id query param."""
        _, doc = await _create_kb_and_doc(api_session)
        await _create_job_in_db(api_session, document_id=doc.id)
        await _create_job_in_db(api_session)
        await api_session.commit()

        response = await api_client.get("/jobs", params={"document_id": str(doc.id)})

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["document_id"] == str(doc.id)

    @pytest.mark.asyncio
    async def test_list_jobs_pagination(self, api_session: AsyncSession, api_client: AsyncClient):
        """Should support skip and limit."""
        for _ in range(5):
            await _create_job_in_db(api_session)
        await api_session.commit()

        response = await api_client.get("/jobs", params={"skip": 2, "limit": 2})

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2


@pytest.mark.unit
class TestGetJob:
    """Tests for GET /jobs/{job_id}."""

    @pytest.mark.asyncio
    async def test_get_job_success(self, api_session: AsyncSession, api_client: AsyncClient):
        """Should return job detail."""
        job = await _create_job_in_db(
            api_session,
            queue_name="ingestion",
            job_type="ingest",
            rq_job_id="rq-abc",
            payload={"document_id": str(uuid.uuid4())},
        )
        await api_session.commit()

        response = await api_client.get(f"/jobs/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(job.id)
        assert data["queue_name"] == "ingestion"
        assert data["job_type"] == "ingest"
        assert data["status"] == "queued"
        assert data["rq_job_id"] == "rq-abc"
        assert data["attempts"] == 0
        assert data["error_message"] is None
        assert data["started_at"] is None
        assert data["finished_at"] is None
        assert "payload" in data
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_get_job_with_error(self, api_session: AsyncSession, api_client: AsyncClient):
        """Should return error info for failed jobs."""
        job = await _create_job_in_db(
            api_session,
            status="failed",
            error_message="Timeout after 300s",
            attempts=1,
        )
        await api_session.commit()

        response = await api_client.get(f"/jobs/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error_message"] == "Timeout after 300s"
        assert data["attempts"] == 1

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, api_client: AsyncClient):
        """Should return 404 for non-existent job."""
        fake_id = str(uuid.uuid4())
        response = await api_client.get(f"/jobs/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_invalid_uuid(self, api_client: AsyncClient):
        """Should return 422 for invalid UUID."""
        response = await api_client.get("/jobs/not-a-uuid")
        assert response.status_code == 422


@pytest.mark.unit
class TestRetryJob:
    """Tests for POST /jobs/{job_id}/retry (S4-04)."""

    @pytest.mark.asyncio
    async def test_retry_failed_job(self, api_session: AsyncSession, api_client: AsyncClient):
        """Should retry a failed job and return updated status."""
        _, doc = await _create_kb_and_doc(api_session)
        job = await _create_job_in_db(
            api_session,
            queue_name="ingestion",
            job_type="ingest",
            status="failed",
            document_id=doc.id,
            error_message="Parse error",
            attempts=1,
            payload={"document_id": str(doc.id)},
        )
        await api_session.commit()

        response = await api_client.post(f"/jobs/{job.id}/retry")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(job.id)
        assert data["status"] == "queued"
        assert data["message"] == "Job re-enqueued successfully"

    @pytest.mark.asyncio
    async def test_retry_non_failed_job_400(self, api_session: AsyncSession, api_client: AsyncClient):
        """Should return 400 when trying to retry a non-failed job."""
        job = await _create_job_in_db(api_session, status="queued")
        await api_session.commit()

        response = await api_client.post(f"/jobs/{job.id}/retry")

        assert response.status_code == 400
        assert "failed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_retry_max_retries_exceeded_400(self, api_session: AsyncSession, api_client: AsyncClient):
        """Should return 400 when max retries reached."""
        _, doc = await _create_kb_and_doc(api_session)
        job = await _create_job_in_db(
            api_session,
            queue_name="ingestion",
            job_type="ingest",
            status="failed",
            document_id=doc.id,
            attempts=2,  # Default max is 2
            error_message="Error",
            payload={"document_id": str(doc.id)},
        )
        await api_session.commit()

        response = await api_client.post(f"/jobs/{job.id}/retry")

        assert response.status_code == 400
        assert "max retries" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_retry_not_found_404(self, api_client: AsyncClient):
        """Should return 404 for non-existent job."""
        fake_id = str(uuid.uuid4())
        response = await api_client.post(f"/jobs/{fake_id}/retry")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_retry_indexing_job(self, api_session: AsyncSession, api_client: AsyncClient):
        """Should retry an indexing job correctly."""
        _, doc = await _create_kb_and_doc(api_session)
        job = await _create_job_in_db(
            api_session,
            queue_name="indexing",
            job_type="index",
            status="failed",
            document_id=doc.id,
            error_message="Embedding error",
            attempts=1,
            payload={"document_id": str(doc.id)},
        )
        await api_session.commit()

        response = await api_client.post(f"/jobs/{job.id}/retry")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"


@pytest.mark.unit
class TestJobResponseSchema:
    """Tests for job response schema completeness."""

    @pytest.mark.asyncio
    async def test_response_has_all_fields(self, api_session: AsyncSession, api_client: AsyncClient):
        """Job response should contain all expected fields."""
        _, doc = await _create_kb_and_doc(api_session)
        job = await _create_job_in_db(
            api_session,
            queue_name="ingestion",
            job_type="ingest",
            document_id=doc.id,
            rq_job_id="rq-test-123",
            payload={"key": "value"},
        )
        await api_session.commit()

        response = await api_client.get(f"/jobs/{job.id}")
        data = response.json()

        expected_fields = [
            "id", "rq_job_id", "queue_name", "job_type", "status",
            "document_id", "attempts", "error_message", "started_at",
            "finished_at", "payload", "created_at", "updated_at",
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
