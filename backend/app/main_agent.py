"""Agent service entry point.

Requires: PostgreSQL + Qdrant + LLM (MiniMax) + Business DB (read-only)
Start:    uvicorn app.main_agent:app --port 8002
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from app.common.core.logging import get_logger
from app.knowledge.api.routes.health import router as health_router
from app.agent.api.routes.chat import router as chat_router
from app.agent.api.routes.sessions import router as sessions_router
from app.agent.api.routes.db_admin import router as db_admin_router
from app.main import create_base_app

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app):
    """Startup: pre-load embedding model, reranker, and Agent singleton."""
    logger.info("agent_startup_warmup_begin")

    # 1. Embedding model (BGE-M3)
    logger.info("loading_embedding_model")
    from app.agent.api.routes.chat import _get_embedding_provider
    _get_embedding_provider()
    logger.info("embedding_model_loaded")

    # 2. Reranker
    logger.info("loading_reranker")
    from app.agent.api.routes.chat import _get_reranker
    from app.common.core.config import get_settings
    settings = get_settings()
    _get_reranker(settings)
    logger.info("reranker_loaded")

    # 3. PydanticAI Agent singleton (loads business DB schema)
    logger.info("loading_agent")
    from app.agent.services.chat import _get_or_create_agent
    try:
        await _get_or_create_agent(settings)
        logger.info("agent_loaded")
    except Exception as e:
        logger.warning("agent_preload_failed", error=str(e))

    logger.info("agent_startup_warmup_done")
    yield


app = create_base_app(
    title="AgenticRAG - Agent",
    description="Agent 对话服务：多轮对话、工具调用、数据分析、图表生成",
)
app.router.lifespan_context = lifespan

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(sessions_router)
app.include_router(db_admin_router)
