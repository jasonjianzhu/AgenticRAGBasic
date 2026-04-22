"""RAG Q&A service entry point.

Requires: PostgreSQL + Qdrant + LLM (MiniMax) + Reranker (optional)
Start:    uvicorn app.main_rag:app --port 8001
"""
from __future__ import annotations

from app.knowledge.api.routes.health import router as health_router
from app.main import create_base_app

app = create_base_app(
    title="AgenticRAG - RAG",
    description="RAG 知识问答服务：混合检索、query 改写、带引用答案生成",
)

# Register health check
app.include_router(health_router)

# TODO: Phase 2 — register RAG routers
# from app.rag.api.routes.search import router as search_router
# from app.rag.api.routes.answer import router as answer_router
# from app.rag.api.routes.config import router as config_router
# app.include_router(search_router)
# app.include_router(answer_router)
# app.include_router(config_router)
