"""Agent service entry point.

Requires: PostgreSQL + Qdrant + LLM (MiniMax) + Business DB (read-only)
Start:    uvicorn app.main_agent:app --port 8002
"""
from __future__ import annotations

from app.knowledge.api.routes.health import router as health_router
from app.agent.api.routes.chat import router as chat_router
from app.agent.api.routes.sessions import router as sessions_router
from app.agent.api.routes.db_admin import router as db_admin_router
from app.main import create_base_app

app = create_base_app(
    title="AgenticRAG - Agent",
    description="Agent 对话服务：多轮对话、工具调用、数据分析、图表生成",
)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(sessions_router)
app.include_router(db_admin_router)
