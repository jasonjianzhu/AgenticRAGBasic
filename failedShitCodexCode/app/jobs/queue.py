from __future__ import annotations

from redis import Redis
from rq import Queue

from app.core.config import get_settings


def get_redis_connection() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url)


def get_ingestion_queue() -> Queue:
    settings = get_settings()
    return Queue(name=settings.rq_ingestion_queue, connection=get_redis_connection())


def get_indexing_queue() -> Queue:
    settings = get_settings()
    return Queue(name=settings.rq_indexing_queue, connection=get_redis_connection())

