"""RAG Q&A service entry point.

Requires: PostgreSQL + Qdrant + LLM (MiniMax) + Reranker (optional)
Start:    uvicorn app.main_rag:app --port 8001
"""
from __future__ import annotations

from app.knowledge.api.routes.health import router as health_router
from app.rag.api.routes.rag import router as rag_router
from app.rag.api.routes.config import router as config_router
from app.main import create_base_app

app = create_base_app(
    title="AgenticRAG - RAG",
    description="RAG 知识问答服务：混合检索、query 改写、带引用答案生成",
)

app.include_router(health_router)
app.include_router(rag_router)
app.include_router(config_router)


@app.on_event("startup")
async def _preload_models():
    """Preload embedding and reranker models at startup."""
    from app.common.core.logging import get_logger
    logger = get_logger(__name__)

    logger.info("preloading_models")

    # Preload embedding model
    from app.common.rag.embedding import create_embedding_provider
    provider = create_embedding_provider()
    await provider.embed_query("warmup")
    logger.info("embedding_model_ready")

    # Preload reranker model
    from app.rag.api.routes.rag import _get_reranker
    from app.common.core.config import get_settings
    reranker = _get_reranker(get_settings())
    if reranker:
        await reranker.rerank("warmup", ["warmup"], top_n=1)
        logger.info("reranker_model_ready")

    logger.info("all_models_preloaded")
