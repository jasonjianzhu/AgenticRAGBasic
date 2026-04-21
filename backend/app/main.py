"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.kb import router as kb_router
from app.api.routes.documents import router as documents_router
from app.api.routes.search_debug import router as search_debug_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger


def _init_job_queues(settings) -> None:
    """Initialize real RQ job queues for production use."""
    from app.jobs.queue import RQJobQueue

    rq_queue = RQJobQueue(
        redis_url=settings.redis_url,
        ingestion_queue=settings.rq_ingestion_queue,
        indexing_queue=settings.rq_indexing_queue,
        ingestion_timeout=settings.rq_ingestion_timeout,
        indexing_timeout=settings.rq_indexing_timeout,
    )

    # Inject into route modules
    import app.api.routes.documents as doc_routes
    import app.api.routes.jobs as job_routes
    import app.api.routes.kb as kb_routes

    doc_routes._default_job_queue = rq_queue
    job_routes._job_queue = rq_queue
    kb_routes._default_kb_job_queue = rq_queue


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger(__name__)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="AgenticRAG - 面向储能行业的智能知识库与问答平台",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize real RQ queues (skip in testing)
    if settings.app_env != "testing":
        try:
            _init_job_queues(settings)
            logger.info("rq_queues_initialized", redis_url=settings.redis_url)
        except Exception as e:
            logger.warning("rq_queues_init_failed", error=str(e))

    # Register routers
    app.include_router(health_router)
    app.include_router(kb_router)
    app.include_router(jobs_router)
    app.include_router(documents_router)
    app.include_router(search_debug_router)

    logger.info("application_started", app_name=settings.app_name, env=settings.app_env)
    return app


app = create_app()
