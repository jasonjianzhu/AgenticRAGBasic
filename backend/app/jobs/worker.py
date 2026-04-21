"""RQ Worker entry point.

Run independently with:
    python -m app.jobs.worker

Listens on both ingestion and indexing queues.
"""
from __future__ import annotations

import os
import sys


def start_worker() -> None:
    """Start an RQ worker that listens on ingestion and indexing queues.

    Uses SimpleWorker (no fork) on macOS to avoid MPS/fork() crash.
    Sets PYTORCH_MPS_DISABLE=1 and OMP_NUM_THREADS=1 for safety.
    """
    # Prevent MPS and OpenMP fork issues on macOS
    os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    from redis import Redis
    from rq import SimpleWorker, Worker

    from app.core.config import get_settings

    settings = get_settings()
    redis_conn = Redis.from_url(settings.redis_url)

    queues = [settings.rq_ingestion_queue, settings.rq_indexing_queue]

    # SimpleWorker runs tasks in the main process (no fork)
    # Required on macOS to avoid MPS/CoreML fork crashes
    if sys.platform == "darwin":
        worker = SimpleWorker(queues, connection=redis_conn)
    else:
        worker = Worker(queues, connection=redis_conn)

    worker.work()


if __name__ == "__main__":
    start_worker()
