"""Knowledge base management service entry point.

Requires: PostgreSQL + Redis + Qdrant + TEI Embedding
Start:    uvicorn app.main_knowledge:app --port 8000
Worker:   python -m app.knowledge.jobs.worker
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from app.common.core.config import get_settings
from app.common.core.logging import get_logger
from app.main import create_base_app


def _init_job_queues(settings) -> None:
    """Initialize real RQ job queues for production use."""
    from app.knowledge.jobs.queue import RQJobQueue

    rq_queue = RQJobQueue(
        redis_url=settings.redis_url,
        ingestion_queue=settings.rq_ingestion_queue,
        indexing_queue=settings.rq_indexing_queue,
        ingestion_timeout=settings.rq_ingestion_timeout,
        indexing_timeout=settings.rq_indexing_timeout,
    )

    import app.knowledge.api.routes.documents as doc_routes
    import app.knowledge.api.routes.jobs as job_routes
    import app.knowledge.api.routes.kb as kb_routes

    doc_routes._default_job_queue = rq_queue
    job_routes._job_queue = rq_queue
    kb_routes._default_kb_job_queue = rq_queue


def create_knowledge_app(settings=None):
    """Create the knowledge management FastAPI app."""
    if settings is None:
        settings = get_settings()
    logger = get_logger(__name__)

    knowledge_app = create_base_app(
        title="AgenticRAG - Knowledge",
        description="知识库管理平台：文档上传、解析、chunk、索引构建",
    )

    # Register knowledge routers
    from app.knowledge.api.routes.health import router as health_router
    from app.knowledge.api.routes.jobs import router as jobs_router
    from app.knowledge.api.routes.kb import router as kb_router
    from app.knowledge.api.routes.documents import router as documents_router
    from app.knowledge.api.routes.search_debug import router as search_debug_router

    knowledge_app.include_router(health_router)
    knowledge_app.include_router(kb_router)
    knowledge_app.include_router(jobs_router)
    knowledge_app.include_router(documents_router)
    knowledge_app.include_router(search_debug_router)

    # Initialize RQ queues (skip in testing)
    if settings.app_env != "testing":
        try:
            _init_job_queues(settings)
            logger.info("rq_queues_initialized", redis_url=settings.redis_url)
        except Exception as e:
            logger.warning("rq_queues_init_failed", error=str(e))

    return knowledge_app


app = create_knowledge_app()
