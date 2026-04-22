"""Job queue abstraction layer.

Provides a protocol-based interface for enqueuing jobs, with an in-memory
implementation for testing and an RQ-backed implementation for production.
"""
from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class JobQueue(Protocol):
    """Protocol for job queue operations.

    Implementations must provide methods to enqueue ingestion and indexing jobs.
    Each method returns a job_id string that can be used to track the job.
    """

    async def enqueue_ingestion(self, document_id: uuid.UUID, **kwargs: Any) -> str:
        """Enqueue a document ingestion job.

        Args:
            document_id: The document to ingest.
            **kwargs: Additional job parameters.

        Returns:
            A unique job ID string.
        """
        ...

    async def enqueue_indexing(self, document_id: uuid.UUID, **kwargs: Any) -> str:
        """Enqueue a document indexing job.

        Args:
            document_id: The document to index.
            **kwargs: Additional job parameters.

        Returns:
            A unique job ID string.
        """
        ...


class InMemoryJobQueue:
    """In-memory job queue for testing.

    Stores enqueued jobs in a list so tests can inspect what was enqueued
    without needing a real Redis connection.
    """

    def __init__(self) -> None:
        self.jobs: list[dict[str, Any]] = []

    async def enqueue_ingestion(self, document_id: uuid.UUID, **kwargs: Any) -> str:
        job_id = str(uuid.uuid4())
        self.jobs.append({
            "job_id": job_id,
            "queue_name": "ingestion",
            "job_type": "ingest",
            "document_id": document_id,
            **kwargs,
        })
        return job_id

    async def enqueue_indexing(self, document_id: uuid.UUID, **kwargs: Any) -> str:
        job_id = str(uuid.uuid4())
        self.jobs.append({
            "job_id": job_id,
            "queue_name": "indexing",
            "job_type": "index",
            "document_id": document_id,
            **kwargs,
        })
        return job_id


class RQJobQueue:
    """RQ-backed job queue for production use.

    Wraps Redis Queue (RQ) to enqueue jobs on the ingestion and indexing queues.
    Not tested in unit tests — requires a live Redis connection.
    """

    def __init__(self, redis_url: str, ingestion_queue: str = "ingestion", indexing_queue: str = "indexing",
                 ingestion_timeout: int = 300, indexing_timeout: int = 300) -> None:
        from redis import Redis
        from rq import Queue

        self._redis = Redis.from_url(redis_url)
        self._ingestion_queue = Queue(ingestion_queue, connection=self._redis)
        self._indexing_queue = Queue(indexing_queue, connection=self._redis)
        self._ingestion_timeout = ingestion_timeout
        self._indexing_timeout = indexing_timeout

    async def enqueue_ingestion(self, document_id: uuid.UUID, **kwargs: Any) -> str:
        job = self._ingestion_queue.enqueue(
            "app.knowledge.jobs.tasks.run_ingestion",
            document_id=str(document_id),
            job_timeout=self._ingestion_timeout,
            **kwargs,
        )
        return job.id

    async def enqueue_indexing(self, document_id: uuid.UUID, **kwargs: Any) -> str:
        job = self._indexing_queue.enqueue(
            "app.knowledge.jobs.tasks.run_indexing",
            document_id=str(document_id),
            job_timeout=self._indexing_timeout,
            **kwargs,
        )
        return job.id
