"""RQ Worker entry point.

Run independently with:
    python -m app.jobs.worker

Listens on both ingestion and indexing queues.
"""
from __future__ import annotations

import sys


def start_worker() -> None:
    """Start an RQ worker that listens on ingestion and indexing queues."""
    from redis import Redis
    from rq import Worker

    from app.core.config import get_settings

    settings = get_settings()
    redis_conn = Redis.from_url(settings.redis_url)

    queues = [settings.rq_ingestion_queue, settings.rq_indexing_queue]

    worker = Worker(queues, connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    start_worker()
