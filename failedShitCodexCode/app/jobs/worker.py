from __future__ import annotations

import logging

from redis import Redis
from rq import SimpleWorker, Worker

from app.core.config import get_settings
from app.core.logging import configure_logging


logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    logger.info(
        "Starting RQ worker: queues=%s,%s redis_url=%s worker_class=%s",
        settings.rq_ingestion_queue,
        settings.rq_indexing_queue,
        settings.redis_url,
        settings.rq_worker_class,
    )
    connection = Redis.from_url(settings.redis_url)
    worker_class = SimpleWorker if settings.rq_worker_class == "simple" else Worker
    worker = worker_class(
        [settings.rq_ingestion_queue, settings.rq_indexing_queue],
        connection=connection,
    )
    worker.work()


if __name__ == "__main__":
    main()
