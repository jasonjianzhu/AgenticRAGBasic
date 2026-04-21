"""Tests for job queue abstraction (S4-01).

Tests the InMemoryJobQueue implementation and verifies the JobQueue protocol.
No real Redis connection is needed.
"""
from __future__ import annotations

import uuid

import pytest

from app.jobs.queue import InMemoryJobQueue, JobQueue, RQJobQueue


@pytest.mark.unit
class TestJobQueueProtocol:
    """Verify that implementations satisfy the JobQueue protocol."""

    def test_in_memory_queue_is_job_queue(self):
        """InMemoryJobQueue should satisfy the JobQueue protocol."""
        queue = InMemoryJobQueue()
        assert isinstance(queue, JobQueue)

    def test_rq_job_queue_is_job_queue(self):
        """RQJobQueue class should satisfy the JobQueue protocol (structural check)."""
        # We can't instantiate RQJobQueue without Redis, but we can check
        # that the class has the required methods.
        assert hasattr(RQJobQueue, "enqueue_ingestion")
        assert hasattr(RQJobQueue, "enqueue_indexing")


@pytest.mark.unit
class TestInMemoryJobQueueIngestion:
    """Tests for InMemoryJobQueue.enqueue_ingestion."""

    @pytest.mark.asyncio
    async def test_enqueue_ingestion_returns_job_id(self):
        """Should return a valid UUID string as job_id."""
        queue = InMemoryJobQueue()
        doc_id = uuid.uuid4()

        job_id = await queue.enqueue_ingestion(doc_id)

        assert isinstance(job_id, str)
        # Should be a valid UUID
        uuid.UUID(job_id)

    @pytest.mark.asyncio
    async def test_enqueue_ingestion_stores_job(self):
        """Should store the job in the internal jobs list."""
        queue = InMemoryJobQueue()
        doc_id = uuid.uuid4()

        job_id = await queue.enqueue_ingestion(doc_id)

        assert len(queue.jobs) == 1
        job = queue.jobs[0]
        assert job["job_id"] == job_id
        assert job["queue_name"] == "ingestion"
        assert job["job_type"] == "ingest"
        assert job["document_id"] == doc_id

    @pytest.mark.asyncio
    async def test_enqueue_ingestion_with_kwargs(self):
        """Should pass through extra kwargs."""
        queue = InMemoryJobQueue()
        doc_id = uuid.uuid4()

        await queue.enqueue_ingestion(doc_id, parser_profile="accurate")

        job = queue.jobs[0]
        assert job["parser_profile"] == "accurate"

    @pytest.mark.asyncio
    async def test_enqueue_ingestion_unique_ids(self):
        """Each enqueue should produce a unique job_id."""
        queue = InMemoryJobQueue()
        doc_id = uuid.uuid4()

        id1 = await queue.enqueue_ingestion(doc_id)
        id2 = await queue.enqueue_ingestion(doc_id)

        assert id1 != id2
        assert len(queue.jobs) == 2


@pytest.mark.unit
class TestInMemoryJobQueueIndexing:
    """Tests for InMemoryJobQueue.enqueue_indexing."""

    @pytest.mark.asyncio
    async def test_enqueue_indexing_returns_job_id(self):
        """Should return a valid UUID string as job_id."""
        queue = InMemoryJobQueue()
        doc_id = uuid.uuid4()

        job_id = await queue.enqueue_indexing(doc_id)

        assert isinstance(job_id, str)
        uuid.UUID(job_id)

    @pytest.mark.asyncio
    async def test_enqueue_indexing_stores_job(self):
        """Should store the job with indexing queue metadata."""
        queue = InMemoryJobQueue()
        doc_id = uuid.uuid4()

        job_id = await queue.enqueue_indexing(doc_id)

        assert len(queue.jobs) == 1
        job = queue.jobs[0]
        assert job["job_id"] == job_id
        assert job["queue_name"] == "indexing"
        assert job["job_type"] == "index"
        assert job["document_id"] == doc_id

    @pytest.mark.asyncio
    async def test_enqueue_indexing_with_kwargs(self):
        """Should pass through extra kwargs."""
        queue = InMemoryJobQueue()
        doc_id = uuid.uuid4()

        await queue.enqueue_indexing(doc_id, batch_size=64)

        job = queue.jobs[0]
        assert job["batch_size"] == 64


@pytest.mark.unit
class TestInMemoryJobQueueMixed:
    """Tests for mixed ingestion and indexing operations."""

    @pytest.mark.asyncio
    async def test_mixed_enqueue_operations(self):
        """Should track both ingestion and indexing jobs."""
        queue = InMemoryJobQueue()
        doc1 = uuid.uuid4()
        doc2 = uuid.uuid4()

        await queue.enqueue_ingestion(doc1)
        await queue.enqueue_indexing(doc2)

        assert len(queue.jobs) == 2
        assert queue.jobs[0]["queue_name"] == "ingestion"
        assert queue.jobs[1]["queue_name"] == "indexing"

    @pytest.mark.asyncio
    async def test_empty_queue_initially(self):
        """New queue should have no jobs."""
        queue = InMemoryJobQueue()
        assert queue.jobs == []
