"""Tests for JobLog repository (S4-03, S4-04, S4-05).

Tests CRUD operations, status transitions, and filtering.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.models import Document, JobLog, KnowledgeBase
from app.common.db.repositories.jobs import JobRepository


async def _create_kb_and_doc(session: AsyncSession) -> tuple[KnowledgeBase, Document]:
    """Helper to create a KB and document for job tests."""
    kb = KnowledgeBase(name=f"Job Test KB {uuid.uuid4().hex[:8]}", settings={})
    session.add(kb)
    await session.flush()

    doc = Document(
        knowledge_base_id=kb.id,
        title="Test Doc",
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
class TestJobRepositoryCreate:
    """Tests for JobRepository.create_job_log."""

    @pytest.mark.asyncio
    async def test_create_job_log_minimal(self, db_session: AsyncSession):
        """Should create a job log with required fields only."""
        repo = JobRepository(db_session)
        job = await repo.create_job_log(
            queue_name="ingestion",
            job_type="ingest",
        )

        assert job.id is not None
        assert isinstance(job.id, uuid.UUID)
        assert job.queue_name == "ingestion"
        assert job.job_type == "ingest"
        assert job.status == "queued"
        assert job.attempts == 0
        assert job.document_id is None
        assert job.rq_job_id is None
        assert job.payload == {}
        assert job.error_message is None
        assert job.started_at is None
        assert job.finished_at is None

    @pytest.mark.asyncio
    async def test_create_job_log_with_all_fields(self, db_session: AsyncSession):
        """Should create a job log with all optional fields."""
        _, doc = await _create_kb_and_doc(db_session)
        repo = JobRepository(db_session)

        job = await repo.create_job_log(
            queue_name="indexing",
            job_type="index",
            document_id=doc.id,
            rq_job_id="rq-12345",
            payload={"document_id": str(doc.id), "batch_size": 32},
        )

        assert job.queue_name == "indexing"
        assert job.job_type == "index"
        assert job.document_id == doc.id
        assert job.rq_job_id == "rq-12345"
        assert job.payload["batch_size"] == 32

    @pytest.mark.asyncio
    async def test_create_multiple_jobs(self, db_session: AsyncSession):
        """Should create multiple independent job logs."""
        repo = JobRepository(db_session)

        job1 = await repo.create_job_log(queue_name="ingestion", job_type="ingest")
        job2 = await repo.create_job_log(queue_name="indexing", job_type="index")

        assert job1.id != job2.id
        assert job1.queue_name == "ingestion"
        assert job2.queue_name == "indexing"


@pytest.mark.unit
class TestJobRepositoryRead:
    """Tests for JobRepository read operations."""

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, db_session: AsyncSession):
        """Should return job when found by ID."""
        repo = JobRepository(db_session)
        job = await repo.create_job_log(queue_name="ingestion", job_type="ingest")

        found = await repo.get_by_id(job.id)
        assert found is not None
        assert found.id == job.id

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db_session: AsyncSession):
        """Should return None when job not found."""
        repo = JobRepository(db_session)
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_document_id(self, db_session: AsyncSession):
        """Should return all jobs for a document."""
        _, doc = await _create_kb_and_doc(db_session)
        repo = JobRepository(db_session)

        await repo.create_job_log(queue_name="ingestion", job_type="ingest", document_id=doc.id)
        await repo.create_job_log(queue_name="indexing", job_type="index", document_id=doc.id)
        # Job for a different document (no document_id)
        await repo.create_job_log(queue_name="ingestion", job_type="ingest")

        jobs = await repo.get_by_document_id(doc.id)
        assert len(jobs) == 2
        assert all(j.document_id == doc.id for j in jobs)

    @pytest.mark.asyncio
    async def test_get_by_document_id_empty(self, db_session: AsyncSession):
        """Should return empty list when no jobs for document."""
        repo = JobRepository(db_session)
        jobs = await repo.get_by_document_id(uuid.uuid4())
        assert len(jobs) == 0


@pytest.mark.unit
class TestJobRepositoryListJobs:
    """Tests for JobRepository.list_jobs with filters."""

    @pytest.mark.asyncio
    async def test_list_jobs_no_filter(self, db_session: AsyncSession):
        """Should return all jobs when no filter applied."""
        repo = JobRepository(db_session)
        await repo.create_job_log(queue_name="ingestion", job_type="ingest")
        await repo.create_job_log(queue_name="indexing", job_type="index")

        jobs = await repo.list_jobs()
        assert len(jobs) == 2

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_status(self, db_session: AsyncSession):
        """Should filter jobs by status."""
        repo = JobRepository(db_session)
        job1 = await repo.create_job_log(queue_name="ingestion", job_type="ingest")
        job2 = await repo.create_job_log(queue_name="ingestion", job_type="ingest")
        await repo.update_status(job1, "started")

        queued_jobs = await repo.list_jobs(status="queued")
        assert len(queued_jobs) == 1
        assert queued_jobs[0].id == job2.id

        started_jobs = await repo.list_jobs(status="started")
        assert len(started_jobs) == 1
        assert started_jobs[0].id == job1.id

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_queue_name(self, db_session: AsyncSession):
        """Should filter jobs by queue name."""
        repo = JobRepository(db_session)
        await repo.create_job_log(queue_name="ingestion", job_type="ingest")
        await repo.create_job_log(queue_name="indexing", job_type="index")

        ingestion_jobs = await repo.list_jobs(queue_name="ingestion")
        assert len(ingestion_jobs) == 1
        assert ingestion_jobs[0].queue_name == "ingestion"

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_document_id(self, db_session: AsyncSession):
        """Should filter jobs by document_id."""
        _, doc = await _create_kb_and_doc(db_session)
        repo = JobRepository(db_session)

        await repo.create_job_log(queue_name="ingestion", job_type="ingest", document_id=doc.id)
        await repo.create_job_log(queue_name="ingestion", job_type="ingest")

        jobs = await repo.list_jobs(document_id=doc.id)
        assert len(jobs) == 1
        assert jobs[0].document_id == doc.id

    @pytest.mark.asyncio
    async def test_list_jobs_combined_filters(self, db_session: AsyncSession):
        """Should support combining multiple filters."""
        _, doc = await _create_kb_and_doc(db_session)
        repo = JobRepository(db_session)

        job1 = await repo.create_job_log(queue_name="ingestion", job_type="ingest", document_id=doc.id)
        await repo.create_job_log(queue_name="indexing", job_type="index", document_id=doc.id)
        await repo.create_job_log(queue_name="ingestion", job_type="ingest")

        jobs = await repo.list_jobs(queue_name="ingestion", document_id=doc.id)
        assert len(jobs) == 1
        assert jobs[0].id == job1.id

    @pytest.mark.asyncio
    async def test_list_jobs_pagination(self, db_session: AsyncSession):
        """Should support skip and limit."""
        repo = JobRepository(db_session)
        for _ in range(5):
            await repo.create_job_log(queue_name="ingestion", job_type="ingest")

        page = await repo.list_jobs(skip=2, limit=2)
        assert len(page) == 2

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, db_session: AsyncSession):
        """Should return empty list when no jobs exist."""
        repo = JobRepository(db_session)
        jobs = await repo.list_jobs()
        assert len(jobs) == 0


@pytest.mark.unit
class TestJobRepositoryStatusTransitions:
    """Tests for status transitions (S4-03, S4-04, S4-05)."""

    @pytest.mark.asyncio
    async def test_queued_to_started(self, db_session: AsyncSession):
        """queued → started should set started_at and increment attempts."""
        repo = JobRepository(db_session)
        job = await repo.create_job_log(queue_name="ingestion", job_type="ingest")
        assert job.status == "queued"
        assert job.attempts == 0

        job = await repo.update_status(job, "started")

        assert job.status == "started"
        assert job.attempts == 1
        assert job.started_at is not None
        assert job.finished_at is None

    @pytest.mark.asyncio
    async def test_started_to_finished(self, db_session: AsyncSession):
        """started → finished should set finished_at and clear error."""
        repo = JobRepository(db_session)
        job = await repo.create_job_log(queue_name="ingestion", job_type="ingest")
        job = await repo.update_status(job, "started")

        job = await repo.update_status(job, "finished")

        assert job.status == "finished"
        assert job.finished_at is not None
        assert job.error_message is None

    @pytest.mark.asyncio
    async def test_started_to_failed(self, db_session: AsyncSession):
        """started → failed should set finished_at and error_message."""
        repo = JobRepository(db_session)
        job = await repo.create_job_log(queue_name="ingestion", job_type="ingest")
        job = await repo.update_status(job, "started")

        job = await repo.update_status(job, "failed", error_message="Timeout after 300s")

        assert job.status == "failed"
        assert job.finished_at is not None
        assert job.error_message == "Timeout after 300s"

    @pytest.mark.asyncio
    async def test_queued_to_failed_direct(self, db_session: AsyncSession):
        """queued → failed should work (e.g., enqueue failure)."""
        repo = JobRepository(db_session)
        job = await repo.create_job_log(queue_name="ingestion", job_type="ingest")

        job = await repo.update_status(job, "failed", error_message="Queue unavailable")

        assert job.status == "failed"
        assert job.error_message == "Queue unavailable"

    @pytest.mark.asyncio
    async def test_failed_to_retrying(self, db_session: AsyncSession):
        """failed → retrying should reset timestamps and error."""
        repo = JobRepository(db_session)
        job = await repo.create_job_log(queue_name="ingestion", job_type="ingest")
        job = await repo.update_status(job, "started")
        job = await repo.update_status(job, "failed", error_message="Some error")

        job = await repo.update_status(job, "retrying")

        assert job.status == "retrying"
        assert job.error_message is None
        assert job.started_at is None
        assert job.finished_at is None

    @pytest.mark.asyncio
    async def test_retrying_to_queued(self, db_session: AsyncSession):
        """retrying → queued should work (re-enqueue)."""
        repo = JobRepository(db_session)
        job = await repo.create_job_log(queue_name="ingestion", job_type="ingest")
        job = await repo.update_status(job, "started")
        job = await repo.update_status(job, "failed", error_message="Error")
        job = await repo.update_status(job, "retrying")

        job = await repo.update_status(job, "queued")

        assert job.status == "queued"

    @pytest.mark.asyncio
    async def test_attempts_increment_on_start(self, db_session: AsyncSession):
        """Attempts should increment each time status goes to 'started'."""
        repo = JobRepository(db_session)
        job = await repo.create_job_log(queue_name="ingestion", job_type="ingest")

        # First attempt
        job = await repo.update_status(job, "started")
        assert job.attempts == 1

        # Simulate failure and retry
        job = await repo.update_status(job, "failed", error_message="Error")
        job = await repo.update_status(job, "retrying")
        job = await repo.update_status(job, "queued")

        # Second attempt
        job = await repo.update_status(job, "started")
        assert job.attempts == 2


@pytest.mark.unit
class TestJobRepositoryHelpers:
    """Tests for helper methods."""

    @pytest.mark.asyncio
    async def test_increment_attempts(self, db_session: AsyncSession):
        """Should increment attempts counter."""
        repo = JobRepository(db_session)
        job = await repo.create_job_log(queue_name="ingestion", job_type="ingest")
        assert job.attempts == 0

        job = await repo.increment_attempts(job)
        assert job.attempts == 1

        job = await repo.increment_attempts(job)
        assert job.attempts == 2

    @pytest.mark.asyncio
    async def test_update_rq_job_id(self, db_session: AsyncSession):
        """Should update the RQ job ID."""
        repo = JobRepository(db_session)
        job = await repo.create_job_log(queue_name="ingestion", job_type="ingest", rq_job_id="old-id")

        job = await repo.update_rq_job_id(job, "new-id")
        assert job.rq_job_id == "new-id"
