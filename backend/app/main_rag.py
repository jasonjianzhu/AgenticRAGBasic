"""RAG Q&A service entry point.

Requires: PostgreSQL + Qdrant + LLM (MiniMax) + Reranker (optional)
Start:    uvicorn app.main_rag:app --port 8001
"""
from __future__ import annotations

from app.knowledge.api.routes.health import router as health_router
from app.rag.api.routes.rag import router as rag_router
from app.main import create_base_app

app = create_base_app(
    title="AgenticRAG - RAG",
    description="RAG 知识问答服务：混合检索、query 改写、带引用答案生成",
)

app.include_router(health_router)
app.include_router(rag_router)
